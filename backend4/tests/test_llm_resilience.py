"""
Unit and integration tests for LLM client resilience, exception classification,
and Executive Report deterministic fallback.
"""
from unittest.mock import MagicMock, patch
import pandas as pd
import pytest
import requests

from app.llm.client import (
    LLMError,
    LLMAuthError,
    LLMQuotaError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMEmptyResponseError,
    complete,
    _post,
)
from app.services.executive_report import (
    generate_executive_report,
    build_deterministic_executive_report,
)
from app.services.dataset_manager import dataset_store


def test_llm_auth_error_no_infinite_retry():
    """Verify HTTP 401/403 raises LLMAuthError immediately without retrying indefinitely."""
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 401
    mock_resp.json.return_value = {"error": {"message": "Invalid API key"}}
    mock_resp.text = '{"error":{"message":"Invalid API key"}}'

    with patch("requests.post", return_value=mock_resp) as mock_post:
        with pytest.raises(LLMAuthError) as exc_info:
            _post({"model": "test", "messages": []}, stream=False)

        assert mock_post.call_count == 1  # Terminal failure: no infinite retry!
        assert "Invalid API key" in str(exc_info.value)
        assert exc_info.value.status_code == 502
        assert exc_info.value.error_code == "LLM_AUTH_FAILED"


def test_llm_quota_error_no_infinite_retry():
    """Verify HTTP 402 or credit exhaustion raises LLMQuotaError immediately."""
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 402
    mock_resp.json.return_value = {"error": {"message": "Insufficient credits in account"}}
    mock_resp.text = "Insufficient credits"

    with patch("requests.post", return_value=mock_resp) as mock_post:
        with pytest.raises(LLMQuotaError) as exc_info:
            _post({"model": "test", "messages": []}, stream=False)

        assert mock_post.call_count == 1  # Terminal failure: no infinite retry
        assert "Insufficient credits" in str(exc_info.value)
        assert exc_info.value.status_code == 402
        assert exc_info.value.error_code == "LLM_QUOTA_EXHAUSTED"


def test_llm_rate_limit_backoff_and_error():
    """Verify HTTP 429 retries with backoff and raises LLMRateLimitError if exhausted."""
    mock_resp = MagicMock()
    mock_resp.ok = False
    mock_resp.status_code = 429
    mock_resp.headers = {"Retry-After": "0.01"}
    mock_resp.json.return_value = {"error": {"message": "Rate limit reached"}}
    mock_resp.text = "Rate limit reached"

    with patch("requests.post", return_value=mock_resp) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMRateLimitError) as exc_info:
            _post({"model": "test", "messages": []}, stream=False, max_retries=3)

        assert mock_post.call_count == 3
        assert "Rate limit" in str(exc_info.value)
        assert exc_info.value.status_code == 429


def test_llm_timeout_backoff_and_error():
    """Verify network timeouts retry and raise LLMTimeoutError."""
    with patch("requests.post", side_effect=requests.exceptions.Timeout("Read timed out")) as mock_post, patch("time.sleep"):
        with pytest.raises(LLMTimeoutError) as exc_info:
            _post({"model": "test", "messages": []}, stream=False, max_retries=3)

        assert mock_post.call_count == 3
        assert "timed out" in str(exc_info.value)
        assert exc_info.value.status_code == 504


def test_complete_empty_response_fallback():
    """Verify that when primary model returns content: null, it falls back to LLM_FALLBACK_MODEL."""
    # First call (primary model) returns content: null
    primary_resp = MagicMock()
    primary_resp.ok = True
    primary_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": None, "reasoning": "thought"}}]
    }

    # Second call (fallback model) returns valid content
    fallback_resp = MagicMock()
    fallback_resp.ok = True
    fallback_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "Here is the fallback response."}}]
    }

    with patch("app.core.config.LLM_FALLBACK_MODEL", "fallback-model"):
        with patch("app.core.config.use_mock_llm", return_value=False):
            with patch("requests.post", side_effect=[primary_resp, fallback_resp]) as mock_post:
                res = complete([{"role": "user", "content": "Hi"}], model="primary-model")
                assert res["content"] == "Here is the fallback response."
                assert mock_post.call_count == 2


def test_complete_empty_response_raises_when_no_fallback():
    """Verify that when all models return empty content, LLMEmptyResponseError is raised."""
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": ""}}]
    }

    with patch("app.core.config.LLM_FALLBACK_MODEL", None):
        with patch("app.core.config.use_mock_llm", return_value=False):
            with patch("requests.post", return_value=mock_resp):
                with pytest.raises(LLMEmptyResponseError):
                    complete([{"role": "user", "content": "Hi"}], model="primary-model")


def test_executive_report_deterministic_fallback(dataset):
    """
    CRITICAL SCREENSHOT BUG FIX VERIFICATION:
    When the AI model throws an error or returns empty response,
    the Executive Report MUST NOT fail with 503!
    It must return verified deterministic calculations with source='deterministic'.
    """
    df = dataset_store.get(dataset)

    # Simulate LLM returning empty response / error
    def failing_llm(_messages):
        raise LLMEmptyResponseError("The AI model returned an empty response.")

    result = generate_executive_report(df, dataset, "sales_data.csv", failing_llm)

    # 1. Report did not crash
    assert result is not None
    # 2. Source is flagged as deterministic
    assert result["source"] == "deterministic"
    # 3. Warning is captured
    assert "AI narrative generation was unavailable" in result["ai_warning"]
    # 4. Verified deterministic narrative was generated
    assert "Executive Summary" in result["narrative"]
    assert "Key Metrics" in result["narrative"]
    assert "Risks" in result["narrative"]
    assert "Recommendations" in result["narrative"]
    # 5. Charts and data are completely preserved
    assert len(result["charts"]) > 0
    assert result["data"]["rows"] == len(df)


def test_executive_report_success_with_ai(dataset):
    """Verify that when AI narrative succeeds, source is 'ai_narrated'."""
    df = dataset_store.get(dataset)

    def working_llm(_messages):
        return "Executive Summary\nThe business produced positive net margins across all lines."

    result = generate_executive_report(df, dataset, "sales_data.csv", working_llm)

    assert result["source"] == "ai_narrated"
    assert result["ai_warning"] is None
    assert "Executive Summary" in result["narrative"]


def test_executive_report_api_endpoint_resilience(client, auth, dataset):
    """Verify that the FastAPI POST /api/reports/{id}/executive endpoint succeeds even with failing LLM."""
    with patch("app.routes.reports.ask_llm", side_effect=LLMEmptyResponseError("Empty AI response")):
        r = client.post(f"/api/reports/{dataset}/executive?refresh=true", headers=auth)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data["source"] == "deterministic"
        assert "Executive Summary" in data["narrative"]
        assert len(data["charts"]) > 0
