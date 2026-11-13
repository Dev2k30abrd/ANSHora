"""
Unit and integration tests for Gmail delivery and Google OAuth 2.0 flow.
"""
import pytest
from app.core import config as cfg
from app.core import db
from app.core.context import workspace_scope
from app.services import gmail_service


@pytest.fixture
def scope(client, dataset):
    ws = db.one("SELECT workspace_id FROM datasets WHERE id=?", (dataset,))["workspace_id"]
    with workspace_scope(ws):
        yield dataset, ws


def test_gmail_status_unconnected(client, auth, scope):
    dataset_id, ws_id = scope
    r = client.get("/api/gmail/status", headers=auth)
    assert r.status_code == 200
    j = r.json()
    assert j["connected"] is False
    assert j["sender_email"] == "anshora.ai.agent@gmail.com"
    assert "Anshora" in j["sender_name"]
    assert "oauth/callback" in j["redirect_uri"]


def test_email_validation():
    assert gmail_service.validate_email_address("test@example.com") == "test@example.com"
    with pytest.raises(ValueError):
        gmail_service.validate_email_address("invalid-email")
    with pytest.raises(ValueError):
        gmail_service.validate_email_address("")


def test_email_preview_generation(client, auth, scope):
    dataset_id, ws_id = scope
    r = client.post(
        "/api/gmail/preview",
        json={
            "dataset_id": dataset_id,
            "recipient": "manager@company.com",
            "report_type": "executive",
            "format": "pdf",
            "custom_notes": "Please review this month's numbers.",
        },
        headers=auth,
    )
    assert r.status_code == 200
    j = r.json()
    assert j["recipient"] == "manager@company.com"
    assert "Anshora" in j["sender"]
    assert "anshora.ai.agent@gmail.com" in j["sender"]
    assert "Executive Report" in j["subject"]
    assert "ANSHORA" in j["html_body"]
    assert len(j["attachments"]) == 1
    assert j["attachments"][0]["name"].endswith(".pdf")
    assert j["attachments"][0]["size_bytes"] > 0
    assert j["preview_token"]


def test_send_requires_explicit_confirmation(client, auth, scope):
    dataset_id, ws_id = scope
    # Attempting to send with confirmation=False MUST fail with 400
    r = client.post(
        "/api/gmail/send",
        json={
            "dataset_id": dataset_id,
            "recipient": "manager@company.com",
            "confirmation": False,
        },
        headers=auth,
    )
    assert r.status_code == 400
    assert "confirmation" in r.text.lower()


def test_send_fails_gracefully_when_oauth_not_connected(client, auth, scope):
    dataset_id, ws_id = scope
    # Attempting to send when OAuth is not connected MUST report that clearly
    r = client.post(
        "/api/gmail/send",
        json={
            "dataset_id": dataset_id,
            "recipient": "manager@company.com",
            "confirmation": True,
        },
        headers=auth,
    )
    assert r.status_code == 400
    assert "not connected" in r.text.lower() or "authenticate" in r.text.lower()


def test_oauth_state_validation():
    # Invalid state must fail
    with pytest.raises(ValueError) as exc:
        gmail_service.exchange_code_for_tokens("fake_code", "fake_state_12345")
    assert "CSRF" in str(exc.value) or "state" in str(exc.value).lower()


def test_duplicate_send_protection(monkeypatch, scope):
    dataset_id, ws_id = scope
    # Insert a record into email_deliveries simulating an already sent email
    sig = "simulated_unique_signature_123"
    db.execute(
        "INSERT INTO email_deliveries(id, workspace_id, recipient, subject, report_type, format, status, message_id, signature, sent_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?)",
        (db.new_id(), ws_id, "boss@company.com", "Test Report", "executive", "pdf", "sent", "msg_abc", sig, db.now()),
    )
    
    # Mock hashlib to produce this exact signature
    monkeypatch.setattr(
        "hashlib.sha256",
        lambda *args: type("MockHash", (), {"hexdigest": lambda self: sig})(),
    )

    res = gmail_service.send_email_report(
        workspace_id=ws_id,
        dataset_id=dataset_id,
        recipient="boss@company.com",
        subject="Test Report",
        confirmation=True,
    )
    assert res["ok"] is True
    assert res.get("deduplicated") is True
    assert res["message_id"] == "msg_abc"
