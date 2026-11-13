"""
OpenAI-compatible chat client (OpenRouter by default) with:
  - native tool calling (streamed), JSON-mode fallback for models without it
  - bounded retries with exponential backoff and jitter
  - multi-model fallback on error or empty model response
  - robust error classification (auth, quota, rate limit, timeout, empty content)
  - offline demo brain when no API key is configured
"""
import json
import logging
import random
import time

import requests

from app.core import config as cfg

logger = logging.getLogger("anshora.llm")


# ===========================================================================
# Structured Exception Hierarchy
# ===========================================================================

class LLMError(Exception):
    """Base exception for all AI provider communication and response errors."""

    def __init__(self, message: str, status_code: int = 502, error_code: str = "LLM_ERROR"):
        super().__init__(message)
        self.message = str(message)
        self.status_code = status_code
        self.error_code = error_code

    def __str__(self):
        return self.message


class LLMAuthError(LLMError):
    """401/403: Provider authentication failed (invalid or missing API key)."""

    def __init__(self, message: str = "AI provider authentication failed. Please verify your API key."):
        super().__init__(message, status_code=502, error_code="LLM_AUTH_FAILED")


class LLMQuotaError(LLMError):
    """402 or quota exceeded: Insufficient provider credits or billing issue."""

    def __init__(self, message: str = "AI provider credit limit reached or quota exhausted."):
        super().__init__(message, status_code=402, error_code="LLM_QUOTA_EXHAUSTED")


class LLMRateLimitError(LLMError):
    """429: Rate limit hit after retries exhausted."""

    def __init__(self, message: str = "AI service rate limit exceeded. Please try again shortly."):
        super().__init__(message, status_code=429, error_code="LLM_RATE_LIMITED")


class LLMTimeoutError(LLMError):
    """Request timed out after bounded retries."""

    def __init__(self, message: str = "AI provider request timed out. Please try again."):
        super().__init__(message, status_code=504, error_code="LLM_TIMEOUT")


class LLMEmptyResponseError(LLMError):
    """The AI model returned empty or null content without any tool calls."""

    def __init__(self, message: str = "The AI model returned an empty response."):
        super().__init__(message, status_code=502, error_code="LLM_EMPTY_RESPONSE")


class ToolsUnsupported(LLMError):
    """The selected model/provider does not support native tool calling."""

    def __init__(self, message: str = "The selected AI model does not support native tool calling."):
        super().__init__(message, status_code=400, error_code="TOOLS_UNSUPPORTED")


# Legacy alias for backward compatibility
AIServiceError = LLMError

_NO_TOOL_MODELS: set[str] = set()


def _headers():
    h = {"Authorization": f"Bearer {cfg.LLM_API_KEY}", "Content-Type": "application/json"}
    if "openrouter" in cfg.LLM_BASE_URL:
        h["X-Title"] = "Anshora Analyst"
    return h


def model_supports_tools(model: str | None = None) -> bool:
    return (model or cfg.LLM_MODEL) not in _NO_TOOL_MODELS and cfg.TOOL_MODE != "json"


def mark_no_tools(model: str | None = None):
    _NO_TOOL_MODELS.add(model or cfg.LLM_MODEL)


def _payload(messages, tools, stream, model, temperature):
    p = {"messages": messages, "temperature": temperature, "stream": stream}
    if "openrouter" in cfg.LLM_BASE_URL and cfg.LLM_FALLBACK_MODEL and model != cfg.LLM_FALLBACK_MODEL:
        p["models"] = [model, cfg.LLM_FALLBACK_MODEL]
    else:
        p["model"] = model
    if tools:
        p["tools"] = tools
        p["tool_choice"] = "auto"
    return p


def _post(payload, stream, max_retries: int = 3):
    """
    Executes POST request to the completions API with bounded exponential backoff
    and random jitter. Differentiates terminal errors (auth, quota) from transient errors.
    """
    last_err = None
    for attempt in range(max_retries):
        try:
            r = requests.post(
                f"{cfg.LLM_BASE_URL}/chat/completions",
                headers=_headers(),
                json=payload,
                timeout=cfg.LLM_TIMEOUT,
                stream=stream,
            )
        except requests.exceptions.Timeout as e:
            last_err = f"Timeout ({e})"
            if attempt < max_retries - 1:
                jitter = random.uniform(0.1, 0.4)
                time.sleep((2 ** attempt) + jitter)
                continue
            raise LLMTimeoutError(f"AI service request timed out after {max_retries} attempts.") from e
        except requests.exceptions.RequestException as e:
            last_err = f"Network error ({e})"
            if attempt < max_retries - 1:
                jitter = random.uniform(0.1, 0.4)
                time.sleep((2 ** attempt) + jitter)
                continue
            raise LLMTimeoutError(f"Network error connecting to AI provider: {e}") from e

        if r.ok:
            return r

        # Extract provider error message safely
        try:
            err_json = r.json().get("error", {})
            err_msg = err_json.get("message", r.text) if isinstance(err_json, dict) else str(err_json)
        except Exception:
            err_msg = r.text or f"HTTP {r.status_code}"

        low_msg = str(err_msg).lower()
        last_err = f"HTTP {r.status_code}: {err_msg}"

        # 1. Authentication / Permission errors -> NEVER retry indefinitely
        if r.status_code in (401, 403):
            raise LLMAuthError(f"AI provider authentication failed: {err_msg}")

        # 2. Insufficient credits / Billing -> NEVER retry indefinitely
        if r.status_code == 402 or "credit" in low_msg or "balance" in low_msg or "payment" in low_msg:
            raise LLMQuotaError(f"AI provider quota or credits exhausted: {err_msg}")

        # 3. Unsupported tool calling
        if r.status_code in (400, 404) and "tool" in low_msg and payload.get("tools"):
            raise ToolsUnsupported(err_msg)

        # 4. Rate limits (429) -> wait with backoff/jitter
        if r.status_code == 429:
            if attempt < max_retries - 1:
                retry_after = r.headers.get("Retry-After")
                try:
                    sleep_sec = float(retry_after) if retry_after else (2 ** attempt) + random.uniform(0.2, 0.6)
                except ValueError:
                    sleep_sec = (2 ** attempt) + random.uniform(0.2, 0.6)
                time.sleep(min(sleep_sec, 8.0))
                continue
            raise LLMRateLimitError(f"AI service rate limit exceeded: {err_msg}")

        # 5. Upstream server errors (500, 502, 503, 504) -> transient retry
        if r.status_code in (500, 502, 503, 504):
            if attempt < max_retries - 1:
                jitter = random.uniform(0.1, 0.5)
                time.sleep((2 ** attempt) + jitter)
                continue
            raise LLMError(f"AI provider temporarily unavailable: {err_msg}", status_code=502)

        # Other 4xx client errors
        raise LLMError(f"AI request rejected ({r.status_code}): {err_msg}", status_code=r.status_code)

    raise LLMError(f"AI service unavailable. Last error: {last_err}", status_code=502)


def _parse_args(raw):
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        from app.llm.jsonfix import extract_json

        return extract_json(raw) or {}


def complete(messages, model=None, temperature=0.2, tools=None, allow_fallback: bool = True) -> dict:
    """
    Non-streaming chat completion.
    Returns: {"content": str, "tool_calls": list[dict]}
    Includes client-side fallback when primary model returns null/empty content.
    """
    target_model = model or cfg.LLM_MODEL
    if cfg.use_mock_llm():
        from app.llm.mock import MockBrain

        return MockBrain.complete(messages, tools)

    try:
        r = _post(_payload(messages, tools, False, target_model, temperature), False)
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMEmptyResponseError("The AI model returned no choices.")

        msg = choices[0].get("message") or {}
        raw_content = msg.get("content")
        calls = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            calls.append({
                "id": tc.get("id") or f"call_{len(calls)}",
                "name": fn.get("name"),
                "arguments": _parse_args(fn.get("arguments")),
            })

        cleaned_content = (raw_content or "").strip()

        # Handle models that return empty/null content without tool calls
        if not cleaned_content and not calls:
            fallback = cfg.LLM_FALLBACK_MODEL
            if allow_fallback and fallback and fallback != target_model:
                logger.warning(
                    "Model '%s' returned empty content. Falling back to '%s'.",
                    target_model, fallback
                )
                return complete(messages, model=fallback, temperature=temperature, tools=tools, allow_fallback=False)

            raise LLMEmptyResponseError("The AI model returned an empty response.")

        return {"content": cleaned_content, "tool_calls": calls}

    except (LLMEmptyResponseError, LLMRateLimitError, LLMTimeoutError) as err:
        fallback = cfg.LLM_FALLBACK_MODEL
        if allow_fallback and fallback and fallback != target_model:
            logger.warning(
                "Primary model '%s' failed (%s). Attempting fallback model '%s'.",
                target_model, err, fallback
            )
            return complete(messages, model=fallback, temperature=temperature, tools=tools, allow_fallback=False)
        raise


def stream_chat(messages, model=None, temperature=0.1, tools=None):
    """
    Streams chat completion events:
      {"type":"thinking","delta"} | {"type":"text","delta"} |
      {"type":"tool_calls","calls":[{id,name,arguments}]} | {"type":"end","content"}
    """
    target_model = model or cfg.LLM_MODEL
    if cfg.use_mock_llm():
        from app.llm.mock import MockBrain

        yield from MockBrain.stream(messages, tools)
        return

    resp = _post(_payload(messages, tools, True, target_model, temperature), True)
    content, acc = "", {}
    try:
        for raw in resp.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8", "ignore")
            if not line.startswith("data:"):
                continue
            body = line[5:].strip()
            if body == "[DONE]":
                break
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                continue
            if data.get("error"):
                raise LLMError(str(data["error"].get("message", data["error"])))
            ch = (data.get("choices") or [{}])[0]
            delta = ch.get("delta") or {}
            think = delta.get("reasoning") or delta.get("reasoning_content")
            if think:
                yield {"type": "thinking", "delta": think}
            if delta.get("content"):
                content += delta["content"]
                yield {"type": "text", "delta": delta["content"]}
            for tc in delta.get("tool_calls") or []:
                slot = acc.setdefault(tc.get("index", 0), {"id": None, "name": "", "args": ""})
                if tc.get("id"):
                    slot["id"] = tc["id"]
                fn = tc.get("function") or {}
                if fn.get("name"):
                    slot["name"] += fn["name"]
                if fn.get("arguments"):
                    slot["args"] += fn["arguments"]
    finally:
        resp.close()

    if acc:
        calls = [
            {"id": s["id"] or f"call_{i}", "name": s["name"], "arguments": _parse_args(s["args"])}
            for i, s in sorted(acc.items())
        ]
        yield {"type": "tool_calls", "calls": calls}
    yield {"type": "end", "content": content}
