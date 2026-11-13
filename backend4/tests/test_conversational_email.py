import pytest
from app.core import db
from app.core.context import workspace_scope
from app.services import email_agent_service, gmail_service
from app.agents.agent import run_agent_stream


@pytest.fixture
def dataset_scope(dataset):
    row = db.one("SELECT workspace_id FROM datasets WHERE id=?", (dataset,))
    ws = row["workspace_id"] if row else "ws_test"
    with workspace_scope(ws):
        yield dataset, ws


def test_intent_detection():
    # Should detect action intent
    assert email_agent_service.is_email_intent("Send this report to my manager.") is True
    assert email_agent_service.is_email_intent("Email this analysis to manager@example.com.") is True
    assert email_agent_service.is_email_intent("Can you send the profit analysis as a PDF?") is True
    assert email_agent_service.is_email_intent("Email the November sales summary as a CSV.") is True
    assert email_agent_service.is_email_intent("Send the executive report to these two recipients.") is True
    assert email_agent_service.is_email_intent("Send to alice@example.com and bob@example.com") is True

    # Should NOT trigger for informational questions
    assert email_agent_service.is_email_intent("What is an email open rate?") is False
    assert email_agent_service.is_email_intent("What is an email bounce rate?") is False
    assert email_agent_service.is_email_intent("Do we have email column in the customer data?") is False
    assert email_agent_service.is_email_intent("How many customers have email addresses?") is False


def test_details_parsing():
    d1 = email_agent_service.parse_email_intent_details("Can you send the profit analysis as a PDF?")
    assert d1["format"] == "pdf"
    assert d1["report_type"] == "profit"
    assert len(d1["recipients"]) == 0

    d2 = email_agent_service.parse_email_intent_details("Email the November sales summary as a CSV to finance@acme.com")
    assert d2["format"] == "csv"
    assert d2["recipients"] == ["finance@acme.com"]

    d3 = email_agent_service.parse_email_intent_details("Send report to alice@corp.com and bob@corp.com")
    assert set(d3["recipients"]) == {"alice@corp.com", "bob@corp.com"}


def test_multi_turn_recipient_collection(dataset_scope):
    dataset_id, ws_id = dataset_scope

    # Turn 1: User requests email without recipient
    res1 = email_agent_service.handle_conversational_email(
        "Send this report to my manager.",
        dataset_id=dataset_id,
        workspace_id=ws_id,
        pending_action=None,
    )
    assert res1["status"] == "need_recipient"
    assert "Which email address should I send" in res1["message"]
    assert res1["pending_action"]["type"] == "email_delivery"
    assert res1["pending_action"]["stage"] == "awaiting_recipient"
    assert res1["preview"] is None

    # Turn 2: User provides recipient in follow-up message
    pending = res1["pending_action"]
    res2 = email_agent_service.handle_conversational_email(
        "manager@example.com",
        dataset_id=dataset_id,
        workspace_id=ws_id,
        pending_action=pending,
    )
    assert res2["status"] == "preview_ready"
    assert "manager@example.com" in res2["message"]
    assert res2["preview"] is not None
    assert res2["preview"]["recipient"] == "manager@example.com"
    assert res2["preview"]["preview_token"] is not None
    assert res2["pending_action"]["stage"] == "preview_ready"


def test_conversational_cancellation(dataset_scope):
    dataset_id, ws_id = dataset_scope
    pending = {"type": "email_delivery", "stage": "awaiting_recipient", "format": "pdf", "report_type": "executive"}

    res = email_agent_service.handle_conversational_email(
        "Never mind, cancel that",
        dataset_id=dataset_id,
        workspace_id=ws_id,
        pending_action=pending,
    )
    assert res["status"] == "cancelled"
    assert res["pending_action"] is None
    assert "cancelled" in res["message"].lower()


def test_preview_token_validation_and_security(dataset_scope):
    dataset_id, ws_id = dataset_scope
    preview = gmail_service.prepare_email_preview(
        dataset_id=dataset_id,
        recipient="manager@example.com",
        report_type="executive",
        format_type="pdf",
        workspace_id=ws_id,
    )
    token = preview["preview_token"]
    assert token is not None

    # Calling send without confirmation fails
    with pytest.raises(ValueError, match="Explicit user confirmation is required"):
        gmail_service.send_email_report(
            workspace_id=ws_id,
            dataset_id=dataset_id,
            recipient="manager@example.com",
            confirmation=False,
            preview_token=token,
        )

    # Calling send with altered/forged token fails
    with pytest.raises(ValueError, match="Invalid or unrecognized email preview token"):
        gmail_service.send_email_report(
            workspace_id=ws_id,
            dataset_id=dataset_id,
            recipient="manager@example.com",
            confirmation=True,
            preview_token="forged_token_12345",
        )


def test_agent_stream_conversational_email(dataset_scope):
    dataset_id, _ = dataset_scope

    # Run stream with email intent lacking recipient
    events1 = list(run_agent_stream("Send this report to my manager", dataset_id=dataset_id))
    done1 = next(e for e in events1 if e["type"] == "done")
    assert "Which email address" in done1["answer"]
    assert done1["pending_action"] is not None
    assert done1["pending_action"]["stage"] == "awaiting_recipient"

    # Run second turn with recipient provided
    events2 = list(run_agent_stream(
        "manager@example.com",
        dataset_id=dataset_id,
        pending_action=done1["pending_action"],
    ))
    done2 = next(e for e in events2 if e["type"] == "done")
    assert done2["email_preview"] is not None
    assert done2["email_preview"]["recipient"] == "manager@example.com"
    assert done2["email_preview"]["preview_token"] is not None
    assert any(e["type"] == "tool_result" and e["name"] == "prepare_email_delivery" for e in events2)
