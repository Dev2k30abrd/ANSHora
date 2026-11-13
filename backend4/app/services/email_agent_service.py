"""
Conversational Email Agent Service.

Implements the reliable email action state machine:
IDLE -> EMAIL_INTENT_DETECTED -> COLLECTING_RECIPIENT -> PREPARING_REPORT
-> PREVIEW_READY -> AWAITING_CONFIRMATION -> SENDING -> SENT / FAILED -> IDLE

Key architectural rules:
- Each email request has a unique action_id and independent lifecycle.
- A completed or cancelled action is immediately cleared to IDLE.
- A new email request always creates a new action_id and never reuses a previous recipient.
- An explicit recipient in a new prompt always overrides any previous recipient.
- Stale pending actions (>15 min) expire automatically.
- Handles conversational cancellation ("cancel that email") and confirmation ("send it", "confirm").
"""
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone

from app.core import db
from app.services import gmail_service

logger = logging.getLogger("anshora.email_agent")

EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# Action trigger patterns
NEW_REQUEST_PATTERNS = [
    r"\b(?:send|email|mail|forward)\b.*?\b(?:report|analysis|summary|findings|csv|pdf|dashboard|profit|snapshot|data)\b",
    r"\b(?:can\s+you|please|could\s+you)\s+(?:send|email|mail)\b",
    r"\b(?:email|send)\s+(?:this|it|sales|profit|executive)\b",
    r"\b(?:send|email)\s+another\b",
]

NON_ACTION_PATTERNS = [
    r"\b(?:what\s+is|what's|how\s+does|explain|define)\b.*?\b(?:email|open\s+rate|bounce\s+rate|click\s+rate)\b",
    r"\b(?:column|table|field|metric)\b.*?\bemail\b",
    r"\bhow\s+many\s+customers\s+have\s+email",
    r"\bdo\s+we\s+have\s+email",
]

CANCEL_WORDS = {"cancel", "never mind", "nevermind", "stop", "don't send", "dont send", "forget it", "abort"}
CONFIRM_WORDS = {"confirm", "send it", "yes send", "yes, send", "approve", "go ahead and send", "please send", "send now"}
CHANGE_RECIPIENT_PATTERNS = [
    r"\b(?:change|switch|update|set)\s+(?:the\s+)?recipient\s+to\b",
    r"\b(?:send\s+to|send\s+instead\s+to|change\s+to)\b",
]


def extract_recipients_from_text(text: str) -> list[str]:
    """Extracts all RFC-compliant email addresses found in the text string."""
    found = EMAIL_REGEX.findall(text or "")
    cleaned = []
    for email in found:
        addr = email.strip(".,;:<>(){}[]'\"")
        if addr and addr not in cleaned:
            cleaned.append(addr)
    return cleaned


def is_action_expired(pending_action: dict | None) -> bool:
    """Returns True if the pending action is stale (> 15 minutes old)."""
    if not pending_action or not isinstance(pending_action, dict):
        return True
    created = pending_action.get("created_at")
    if not created:
        return False
    try:
        dt = datetime.fromisoformat(created)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - dt > timedelta(minutes=15)
    except Exception:
        return False


def is_new_email_request(question: str) -> bool:
    """Checks whether the query is initiating a fresh email request."""
    q = (question or "").strip().lower()
    for pat in NEW_REQUEST_PATTERNS:
        if re.search(pat, q):
            return True
    if re.search(r"\b(?:send|email)\s+(?:to\s+)?[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", q):
        return True
    return False


def is_email_intent(question: str, pending_action: dict | None = None) -> bool:
    """
    Determines whether a user query represents a conversational email request
    or a continuation/cancellation/confirmation of an active pending email action.
    """
    q = (question or "").strip().lower()
    if not q:
        return False

    # Filter out informational queries
    for non_act in NON_ACTION_PATTERNS:
        if re.search(non_act, q):
            return False

    # Check active pending action
    if pending_action and isinstance(pending_action, dict) and not is_action_expired(pending_action):
        stage = pending_action.get("stage") or pending_action.get("state")
        if stage in ("COLLECTING_RECIPIENT", "awaiting_recipient", "PREVIEW_READY", "AWAITING_CONFIRMATION", "awaiting_confirmation"):
            # Check for cancellation, confirmation, recipient input, or format change
            if any(w in q for w in CANCEL_WORDS) or any(w in q for w in CONFIRM_WORDS):
                return True
            if extract_recipients_from_text(q):
                return True
            if re.search(r"\b(?:csv|pdf|both|excel)\b", q):
                return True
            if stage in ("COLLECTING_RECIPIENT", "awaiting_recipient"):
                return True

    # Check if this is a new email action trigger
    return is_new_email_request(q)


def parse_email_intent_details(question: str, pending_action: dict | None = None) -> dict:
    """Extracts structured intent parameters and intent classification."""
    q = (question or "").strip()
    q_lower = q.lower()

    is_cancel = any(w in q_lower for w in CANCEL_WORDS)
    is_confirm = any(w in q_lower for w in CONFIRM_WORDS)
    is_new = is_new_email_request(q_lower)

    recipients = extract_recipients_from_text(q)

    # Format detection
    fmt = None
    if re.search(r"\b(?:csv|spreadsheet|excel|table)\b", q_lower):
        fmt = "csv"
    elif re.search(r"\b(?:both|pdf\s+and\s+csv|csv\s+and\s+pdf)\b", q_lower):
        fmt = "both"
    elif re.search(r"\b(?:pdf|document)\b", q_lower):
        fmt = "pdf"

    # Report type detection
    report_type = None
    if re.search(r"\b(?:profit|margin|loss|leakage)\b", q_lower):
        report_type = "profit"
    elif re.search(r"\b(?:health|quality|missing)\b", q_lower):
        report_type = "data_health"
    elif re.search(r"\b(?:dashboard|kpi)\b", q_lower):
        report_type = "dashboard"
    elif re.search(r"\b(?:sales|executive|summary|overview)\b", q_lower):
        report_type = "executive"

    # Subject detection if explicitly specified
    subject = None
    subj_match = re.search(r'(?:subject|titled|with\s+title)\s*[:"“]([^"”\n]+)', q, re.IGNORECASE)
    if subj_match:
        subject = subj_match.group(1).strip()

    return {
        "is_action": is_email_intent(question, pending_action),
        "is_new_request": is_new,
        "is_cancel": is_cancel,
        "is_confirm": is_confirm,
        "recipients": recipients,
        "format": fmt,
        "report_type": report_type,
        "subject": subject,
    }


def handle_conversational_email(
    question: str,
    dataset_id: str,
    workspace_id: str,
    pending_action: dict | None = None,
) -> dict:
    """
    Executes the conversational email state machine.

    Lifecycle:
    IDLE -> EMAIL_INTENT_DETECTED -> COLLECTING_RECIPIENT -> PREVIEW_READY -> AWAITING_CONFIRMATION -> SENT / IDLE
    """
    # Clean stale pending action (> 15m)
    active_pending = None if is_action_expired(pending_action) else pending_action

    details = parse_email_intent_details(question, active_pending)

    # 1. Cancellation Handler
    if details["is_cancel"]:
        if active_pending and active_pending.get("preview_token"):
            try:
                db.execute("DELETE FROM email_preview_tokens WHERE token=?", (active_pending["preview_token"],))
            except Exception:
                pass
        return {
            "status": "cancelled",
            "message": "Understood. The email delivery request has been cancelled.",
            "pending_action": None,
            "preview": None,
        }

    # 2. Confirmation Handler (User types "Confirm", "Send it", "Yes send", "Approve")
    if details["is_confirm"] and active_pending and active_pending.get("preview_token"):
        try:
            res = gmail_service.send_email_report(
                workspace_id=workspace_id,
                dataset_id=dataset_id,
                recipient=active_pending["recipient"],
                subject=active_pending.get("subject"),
                report_type=active_pending.get("report_type", "executive"),
                format_type=active_pending.get("format", "pdf"),
                confirmation=True,
                preview_token=active_pending["preview_token"],
                action_id=active_pending.get("action_id"),
            )
            msg_id = res.get("message_id") or "accepted"
            recipient = active_pending["recipient"]
            msg = (
                f"✓ Gmail accepted the report message for **{recipient}** (Message ID: `{msg_id}`).\n\n"
                "*Notice: Gmail API acceptance indicates the message was handed off to Google's mail servers for delivery; "
                "inbox placement depends on recipient mail provider policies.*"
            )
            return {
                "status": "sent",
                "message": msg,
                "pending_action": None,  # Immediately transition back to IDLE
                "preview": None,
                "delivery": res,
            }
        except ValueError as e:
            return {
                "status": "failed",
                "message": f"Gmail delivery could not be completed: {e}",
                "pending_action": None,  # Failed action cleared from reuse
                "preview": None,
            }

    # 3. New Request vs Continuation
    # A new request (e.g. "Send another report to ...", "Send my profit report") ALWAYS resets state!
    if details["is_new_request"] or not active_pending:
        action_id = uuid.uuid4().hex[:12]
        recipients = details["recipients"]
        fmt = details["format"] or "pdf"
        report_type = details["report_type"] or "executive"
        subject = details["subject"]
    else:
        # Continuing active pending action (e.g. supplying recipient or changing format)
        action_id = active_pending.get("action_id") or uuid.uuid4().hex[:12]
        # An explicit recipient in this message overrides any previous recipient
        recipients = details["recipients"] if details["recipients"] else []
        fmt = details["format"] or active_pending.get("format") or "pdf"
        report_type = details["report_type"] or active_pending.get("report_type") or "executive"
        subject = details["subject"] or active_pending.get("subject")

    # 4. If no recipients found, transition to COLLECTING_RECIPIENT
    if not recipients:
        new_pending = {
            "type": "email_delivery",
            "action_id": action_id,
            "stage": "awaiting_recipient",
            "state": "COLLECTING_RECIPIENT",
            "format": fmt,
            "report_type": report_type,
            "subject": subject,
            "created_at": db.now(),
        }
        fmt_label = " as a CSV" if fmt == "csv" else (" with both PDF and CSV" if fmt == "both" else "")
        return {
            "status": "need_recipient",
            "message": f"Sure! Which email address should I send the {report_type} report{fmt_label} to?",
            "pending_action": new_pending,
            "preview": None,
        }

    # 5. We have valid recipient(s) -> prepare preview & transition to PREVIEW_READY / AWAITING_CONFIRMATION
    try:
        recipient_str = ", ".join(recipients)
        preview = gmail_service.prepare_email_preview(
            dataset_id=dataset_id,
            recipient=recipient_str,
            report_type=report_type,
            format_type=fmt,
            custom_notes="",
            workspace_id=workspace_id,
            subject=subject,
            action_id=action_id,
        )
    except ValueError as e:
        new_pending = {
            "type": "email_delivery",
            "action_id": action_id,
            "stage": "awaiting_recipient",
            "state": "COLLECTING_RECIPIENT",
            "format": fmt,
            "report_type": report_type,
            "subject": subject,
            "created_at": db.now(),
        }
        return {
            "status": "need_recipient",
            "message": f"Could not process the recipient address ({e}). Which email address should I send it to?",
            "pending_action": new_pending,
            "preview": None,
        }

    recipients_display = ", ".join(preview.get("recipients", [preview["recipient"]]))
    format_label = "PDF attachment" if preview["format"] == "pdf" else ("CSV data export" if preview["format"] == "csv" else "PDF and CSV attachments")

    new_pending = {
        "type": "email_delivery",
        "action_id": action_id,
        "stage": "preview_ready",
        "state": "AWAITING_CONFIRMATION",
        "preview_token": preview["preview_token"],
        "recipient": preview["recipient"],
        "format": preview["format"],
        "report_type": preview["report_type"],
        "subject": preview["subject"],
        "created_at": db.now(),
    }

    message = (
        f"I have prepared your {report_type} report email for **{recipients_display}** including the {format_label}. "
        "Please review the preview card below and confirm to deliver it via Gmail."
    )

    return {
        "status": "preview_ready",
        "message": message,
        "pending_action": new_pending,
        "preview": preview,
    }
