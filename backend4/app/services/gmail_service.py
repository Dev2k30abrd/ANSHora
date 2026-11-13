"""
Anshora Gmail Delivery Service.

Handles Google OAuth 2.0 authorization code flow, secure token refresh,
branded report email generation (PDF/CSV/HTML), preview preparation,
and delivery via the official Gmail REST API.
"""
import base64
import email.utils
import hashlib
import io
import json
import logging
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode

import pandas as pd
import requests

from app.core import config as cfg
from app.core import db
from app.services import exporter
from app.services.dataset_manager import DatasetNotFoundError, dataset_store

logger = logging.getLogger("anshora.gmail")

GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GMAIL_SEND_API = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_recipients(recipient_input: str | list[str]) -> list[str]:
    """
    Validates one or more email recipients.
    Supports comma, semicolon, newline, or 'and' separated strings.
    Returns a cleaned list of valid email addresses.
    """
    if isinstance(recipient_input, list):
        raw_list = recipient_input
    else:
        raw = re.sub(r"\s+and\s+", ",", str(recipient_input or ""), flags=re.IGNORECASE)
        raw_list = re.split(r"[,;\n]+", raw)

    cleaned = []
    for item in raw_list:
        part = item.strip()
        if not part:
            continue
        m = re.search(r"<([^>]+)>", part)
        email_addr = m.group(1).strip() if m else part
        if not EMAIL_REGEX.match(email_addr):
            raise ValueError(f"'{email_addr}' is not a valid email address.")
        if email_addr not in cleaned:
            cleaned.append(email_addr)

    if not cleaned:
        raise ValueError("Please provide at least one valid recipient email address.")
    return cleaned


def validate_email_address(email_str: str) -> str:
    recipients = validate_recipients(email_str)
    return ", ".join(recipients)


def is_oauth_configured() -> bool:
    """True if client ID and secret are set in configuration / env."""
    return bool(cfg.GOOGLE_CLIENT_ID and cfg.GOOGLE_CLIENT_SECRET)


def get_connection_status(workspace_id: str) -> dict:
    """Returns the current Gmail integration status for a workspace."""
    configured = is_oauth_configured()
    row = db.one("SELECT * FROM gmail_integrations WHERE workspace_id=?", (workspace_id,))
    connected = bool(row and row.get("refresh_token"))
    
    return {
        "configured": configured,
        "connected": connected,
        "sender_email": cfg.GMAIL_SENDER_EMAIL,
        "sender_name": cfg.GMAIL_SENDER_NAME,
        "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
        "account_email": row.get("email") if row else (cfg.GMAIL_SENDER_EMAIL if connected else None),
        "connected_at": row.get("created_at") if row else None,
    }


def create_authorization_url(workspace_id: str, user_id: str, return_to: str | None = None) -> dict:
    """Generates a CSRF-protected Google OAuth 2.0 authorization URL."""
    if not is_oauth_configured():
        raise ValueError(
            "Google OAuth is not configured yet. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend4/.env."
        )

    state = secrets.token_hex(24)
    # Store state with creation timestamp for validation (valid for 15 minutes)
    db.execute(
        "INSERT INTO oauth_states(state, workspace_id, user_id, redirect_url, created_at) VALUES(?,?,?,?,?)",
        (state, workspace_id, user_id, return_to or "", db.now()),
    )

    params = {
        "client_id": cfg.GOOGLE_CLIENT_ID,
        "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": GMAIL_SEND_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    auth_url = f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"
    return {"authorization_url": auth_url, "state": state, "redirect_uri": cfg.GOOGLE_REDIRECT_URI}


def exchange_code_for_tokens(code: str, state: str) -> dict:
    """Validates state and exchanges authorization code for tokens via Google OAuth token endpoint."""
    stored = db.one("SELECT * FROM oauth_states WHERE state=?", (state,))
    if not stored:
        raise ValueError("Invalid or unknown OAuth state. CSRF verification failed.")

    # Check state age (15 min window)
    try:
        created_time = datetime.fromisoformat(stored["created_at"])
        if datetime.now(timezone.utc) - created_time.replace(tzinfo=timezone.utc) > timedelta(minutes=15):
            db.execute("DELETE FROM oauth_states WHERE state=?", (state,))
            raise ValueError("OAuth state expired. Please try connecting again.")
    except Exception:
        pass

    # Consume the state
    db.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    workspace_id = stored["workspace_id"]

    payload = {
        "code": code,
        "client_id": cfg.GOOGLE_CLIENT_ID,
        "client_secret": cfg.GOOGLE_CLIENT_SECRET,
        "redirect_uri": cfg.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    resp = requests.post(GOOGLE_TOKEN_ENDPOINT, data=payload, timeout=20)
    if not resp.ok:
        err_msg = resp.text
        try:
            err_msg = resp.json().get("error_description") or resp.json().get("error") or err_msg
        except Exception:
            pass
        raise ValueError(f"Google OAuth code exchange failed: {err_msg}")

    data = resp.json()
    refresh_token = data.get("refresh_token")
    access_token = data.get("access_token")
    expires_in = data.get("expires_in", 3600)
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    # If re-authenticating without a new refresh token, keep existing one
    existing = db.one("SELECT refresh_token FROM gmail_integrations WHERE workspace_id=?", (workspace_id,))
    if not refresh_token and existing:
        refresh_token = existing["refresh_token"]

    if not refresh_token:
        raise ValueError("No refresh token received from Google. Make sure access_type=offline and prompt=consent.")

    # Save to database
    db.execute(
        "INSERT INTO gmail_integrations(id, workspace_id, email, refresh_token, access_token, expires_at, created_at, updated_at) "
        "VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(workspace_id) DO UPDATE SET "
        "refresh_token=excluded.refresh_token, access_token=excluded.access_token, "
        "expires_at=excluded.expires_at, updated_at=excluded.updated_at",
        (
            db.new_id(),
            workspace_id,
            cfg.GMAIL_SENDER_EMAIL,
            refresh_token,
            access_token,
            expires_at,
            db.now(),
            db.now(),
        ),
    )

    return {
        "ok": True,
        "workspace_id": workspace_id,
        "sender_email": cfg.GMAIL_SENDER_EMAIL,
        "redirect_url": stored.get("redirect_url") or "",
    }


def get_valid_access_token(workspace_id: str) -> str:
    """Returns a valid access token for the workspace, refreshing it if needed."""
    row = db.one("SELECT * FROM gmail_integrations WHERE workspace_id=?", (workspace_id,))
    if not row or not row.get("refresh_token"):
        raise ValueError("Gmail is not connected for this workspace. Please authenticate with Google first.")

    # Check if access token is still fresh (with 3-minute grace period)
    if row.get("access_token") and row.get("expires_at"):
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) + timedelta(minutes=3) < exp:
                return row["access_token"]
        except Exception:
            pass

    # Refresh the token
    payload = {
        "client_id": cfg.GOOGLE_CLIENT_ID,
        "client_secret": cfg.GOOGLE_CLIENT_SECRET,
        "refresh_token": row["refresh_token"],
        "grant_type": "refresh_token",
    }
    resp = requests.post(GOOGLE_TOKEN_ENDPOINT, data=payload, timeout=20)
    if not resp.ok:
        err = resp.text
        try:
            err = resp.json().get("error_description") or err
        except Exception:
            pass
        raise ValueError(f"Failed to refresh Google access token: {err}")

    data = resp.json()
    new_access_token = data["access_token"]
    expires_in = data.get("expires_in", 3600)
    new_expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    db.execute(
        "UPDATE gmail_integrations SET access_token=?, expires_at=?, updated_at=? WHERE workspace_id=?",
        (new_access_token, new_expires_at, db.now(), workspace_id),
    )
    return new_access_token


def disconnect_gmail(workspace_id: str) -> bool:
    """Disconnects Gmail integration for the workspace."""
    db.execute("DELETE FROM gmail_integrations WHERE workspace_id=?", (workspace_id,))
    return True


# ---------------------------------------------------------------------------
# Branded Report & Email Generation
# ---------------------------------------------------------------------------

def generate_report_content(dataset_id: str, report_type: str = "executive", custom_notes: str = "") -> dict:
    """
    Builds verified report content without inventing figures.
    Reuses deterministic calculation engines (exporter.build_payload, profit_service).
    """
    df = dataset_store.get(dataset_id)
    filename = dataset_store.get_filename(dataset_id)
    payload = exporter.build_payload(dataset_id)
    
    profit_data = payload.get("profit") or {}
    headline = profit_data.get("headline", {})
    hf = headline.get("formatted", {})
    findings = [f for f in profit_data.get("findings", []) if f.get("counts_toward_total")]
    
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")
    
    # Compose clean executive summary text
    summary_bullets = [
        f"Analyzed {payload.get('rows', len(df))} rows from {filename}.",
        f"Total Revenue: {hf.get('revenue', 'n/a')}",
        *( [f"Total Profit: {hf.get('profit', 'n/a')} ({hf.get('margin', 'n/a')} weighted margin)"] if hf.get("profit") else [] ),
        f"Money at Stake / Addressable Leakage: {profit_data.get('total_at_stake_formatted', 'n/a')}",
    ]
    if custom_notes.strip():
        summary_bullets.append(f"Notes: {custom_notes.strip()}")

    # Narrative from payload
    narrative = payload.get("narrative") or "Executive analysis generated based on verified business metrics."

    # Subject line
    subject = f"Anshora Executive Report: {filename} — {hf.get('revenue', 'Analysis')}"

    # Build branded HTML email body
    findings_html_rows = ""
    for i, f in enumerate(findings[:6], 1):
        findings_html_rows += f"""
        <tr style="border-bottom: 1px solid #e5e7eb;">
            <td style="padding: 10px 12px; font-size: 13px; color: #6b7280; font-weight: 600;">{i}</td>
            <td style="padding: 10px 12px; font-size: 13px; color: #111827;">
                <strong>{f.get('title', '')}</strong><br/>
                <span style="font-size: 12px; color: #4b5563;">{f.get('detail', '')}</span>
            </td>
            <td style="padding: 10px 12px; font-size: 13px; color: #dc2626; font-weight: 700; white-space: nowrap; text-align: right;">
                {f.get('impact_formatted', '')}
            </td>
            <td style="padding: 10px 12px; font-size: 12px; color: #4b5563; text-align: center;">
                <span style="background: #f3f4f6; border-radius: 4px; padding: 2px 6px;">{f.get('confidence', 'medium')}</span>
            </td>
        </tr>
        """

    if not findings_html_rows:
        findings_html_rows = '<tr><td colspan="4" style="padding: 12px; text-align: center; color: #6b7280; font-size: 13px;">No material profit leakage detected in current data.</td></tr>'

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>{subject}</title>
    </head>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f9fafb; margin: 0; padding: 24px; color: #1f2937;">
        <div style="max-width: 680px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e5e7eb; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05);">
            <!-- Header -->
            <div style="background: #111827; padding: 28px 32px; color: #ffffff;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div style="font-size: 22px; font-weight: 800; letter-spacing: -0.5px; color: #ffffff;">ANSHORA</div>
                    <div style="font-size: 12px; color: #9ca3af; text-transform: uppercase; letter-spacing: 1px;">Decision Intelligence</div>
                </div>
                <h1 style="margin: 16px 0 6px 0; font-size: 20px; font-weight: 700; color: #f3f4f6;">{payload.get('title')}</h1>
                <div style="font-size: 13px; color: #9ca3af;">Generated: {now_str} · Dataset: {filename} ({payload.get('rows')} rows)</div>
            </div>

            <!-- Content Area -->
            <div style="padding: 32px;">
                <!-- KPI Highlight Grid -->
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px;">
                    <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px;">
                        <div style="font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase;">Revenue</div>
                        <div style="font-size: 18px; font-weight: 700; color: #1f2937; margin-top: 4px;">{hf.get('revenue', '—')}</div>
                    </div>
                    <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 14px;">
                        <div style="font-size: 11px; font-weight: 600; color: #6b7280; text-transform: uppercase;">Profit</div>
                        <div style="font-size: 18px; font-weight: 700; color: #059669; margin-top: 4px;">{hf.get('profit', '—')}</div>
                        <div style="font-size: 11px; color: #6b7280;">{hf.get('margin', '')} margin</div>
                    </div>
                    <div style="background: #fef2f2; border: 1px solid #fecaca; border-radius: 8px; padding: 14px;">
                        <div style="font-size: 11px; font-weight: 600; color: #b91c1c; text-transform: uppercase;">Money At Stake</div>
                        <div style="font-size: 18px; font-weight: 700; color: #dc2626; margin-top: 4px;">{profit_data.get('total_at_stake_formatted', '—')}</div>
                        <div style="font-size: 11px; color: #b91c1c;">Identified leakage</div>
                    </div>
                </div>

                <!-- Executive Summary -->
                <div style="margin-bottom: 28px;">
                    <h2 style="font-size: 15px; font-weight: 700; color: #111827; margin: 0 0 10px 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px;">Executive Briefing</h2>
                    <p style="font-size: 14px; line-height: 1.6; color: #374151; margin: 0 0 12px 0;">{narrative}</p>
                    <ul style="font-size: 13px; line-height: 1.5; color: #4b5563; padding-left: 20px; margin: 0;">
                        {''.join(f'<li style="margin-bottom: 4px;">{b}</li>' for b in summary_bullets)}
                    </ul>
                </div>

                <!-- Priority Findings Table -->
                <div style="margin-bottom: 28px;">
                    <h2 style="font-size: 15px; font-weight: 700; color: #111827; margin: 0 0 12px 0; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px;">Key Findings Ranked by Impact</h2>
                    <table style="width: 100%; border-collapse: collapse; text-align: left;">
                        <thead>
                            <tr style="background: #f3f4f6; border-bottom: 2px solid #e5e7eb;">
                                <th style="padding: 8px 12px; font-size: 11px; color: #4b5563; text-transform: uppercase;">#</th>
                                <th style="padding: 8px 12px; font-size: 11px; color: #4b5563; text-transform: uppercase;">Finding & Detail</th>
                                <th style="padding: 8px 12px; font-size: 11px; color: #4b5563; text-transform: uppercase; text-align: right;">Impact</th>
                                <th style="padding: 8px 12px; font-size: 11px; color: #4b5563; text-transform: uppercase; text-align: center;">Confidence</th>
                            </tr>
                        </thead>
                        <tbody>
                            {findings_html_rows}
                        </tbody>
                    </table>
                </div>

                <!-- Disclaimer & Footer -->
                <div style="border-top: 1px solid #e5e7eb; padding-top: 16px; font-size: 11px; color: #9ca3af; line-height: 1.5;">
                    <p style="margin: 0 0 4px 0;"><strong>Notice:</strong> This analytical report was generated deterministically by Anshora using verified calculations from your dataset. Numbers are directly traced to source records.</p>
                    <p style="margin: 0;">Sent by Anshora (${cfg.GMAIL_SENDER_EMAIL}) via Gmail API.</p>
                </div>
            </div>
        </div>
    </body>
    </html>
    """

    plain_text = f"""ANSHORA DECISION INTELLIGENCE REPORT
{payload.get('title')}
Generated: {now_str}
Dataset: {filename} ({payload.get('rows')} rows)

HEADLINE METRICS:
- Revenue: {hf.get('revenue', 'n/a')}
- Profit: {hf.get('profit', 'n/a')} ({hf.get('margin', 'n/a')} margin)
- Money at Stake: {profit_data.get('total_at_stake_formatted', 'n/a')}

EXECUTIVE SUMMARY:
{narrative}

KEY FINDINGS:
""" + "\n".join(
        f"{i}. {f.get('title')} — {f.get('impact_formatted')} ({f.get('confidence')} confidence)\n   {f.get('detail')}"
        for i, f in enumerate(findings, 1)
    )

    return {
        "subject": subject,
        "html_body": html_body,
        "text_body": plain_text,
        "payload": payload,
        "filename": filename,
        "summary_bullets": summary_bullets,
    }


def prepare_email_preview(
    dataset_id: str,
    recipient: str,
    report_type: str = "executive",
    format_type: str = "pdf",
    custom_notes: str = "",
    workspace_id: str = "",
    subject: str | None = None,
    action_id: str | None = None,
) -> dict:
    """Prepares the email preview for user review before confirmation."""
    recipients_list = validate_recipients(recipient)
    cleaned_recipient = ", ".join(recipients_list)
    report = generate_report_content(dataset_id, report_type, custom_notes)
    final_subject = (subject or "").strip() or report["subject"]
    aid = action_id or secrets.token_hex(6)

    df = dataset_store.get(dataset_id)
    filename = dataset_store.get_filename(dataset_id)

    attachments = []
    if format_type in ("pdf", "both"):
        pdf_bytes = exporter.to_pdf(report["payload"])
        attachments.append({
            "name": f"anshora-report-{Path(filename).stem}.pdf",
            "type": "application/pdf",
            "size_bytes": len(pdf_bytes),
            "size_formatted": f"{round(len(pdf_bytes) / 1024, 1)} KB",
        })
    if format_type in ("csv", "both"):
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        attachments.append({
            "name": f"data-{Path(filename).stem}.csv",
            "type": "text/csv",
            "size_bytes": len(csv_bytes),
            "size_formatted": f"{round(len(csv_bytes) / 1024, 1)} KB",
        })

    status = get_connection_status(workspace_id) if workspace_id else {"connected": False, "configured": is_oauth_configured()}

    # Cryptographically secure preview token with 15-minute TTL bound to action_id
    token = secrets.token_hex(20)
    created_at = db.now()
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat()

    try:
        db.execute(
            "INSERT INTO email_preview_tokens(token, workspace_id, dataset_id, recipient, subject, format, action_id, created_at, expires_at) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (token, workspace_id, dataset_id, cleaned_recipient, final_subject, format_type, aid, created_at, expires_at),
        )
    except Exception as e:
        logger.warning(f"Could not persist preview token in DB: {e}")

    return {
        "action_id": aid,
        "sender": f"{cfg.GMAIL_SENDER_NAME} <{cfg.GMAIL_SENDER_EMAIL}>",
        "recipient": cleaned_recipient,
        "recipients": recipients_list,
        "subject": final_subject,
        "html_body": report["html_body"],
        "text_body": report["text_body"],
        "attachments": attachments,
        "report_type": report_type,
        "format": format_type,
        "dataset_id": dataset_id,
        "connected": status["connected"],
        "configured": status["configured"],
        "preview_token": token,
        "expires_at": expires_at,
    }


def send_email_report(
    workspace_id: str,
    dataset_id: str,
    recipient: str,
    subject: str | None = None,
    report_type: str = "executive",
    format_type: str = "pdf",
    custom_notes: str = "",
    confirmation: bool = False,
    idempotency_key: str | None = None,
    preview_token: str | None = None,
    action_id: str | None = None,
) -> dict:
    """
    Sends the report email via Gmail API strictly after explicit user confirmation.
    Includes preview-token verification, duplicate send protection and audit logging.
    """
    if not confirmation:
        raise ValueError("Explicit user confirmation is required to send emails.")

    # Validate preview token if provided
    resolved_action_id = action_id
    if preview_token:
        stored_token = db.one("SELECT * FROM email_preview_tokens WHERE token=?", (preview_token,))
        if not stored_token:
            raise ValueError("Invalid or unrecognized email preview token. Please review a new email preview.")
        try:
            exp_time = datetime.fromisoformat(stored_token["expires_at"])
            if datetime.now(timezone.utc) > exp_time.replace(tzinfo=timezone.utc):
                db.execute("DELETE FROM email_preview_tokens WHERE token=?", (preview_token,))
                raise ValueError("Email preview has expired. Please review and generate a new preview.")
        except (ValueError, TypeError):
            pass
        if stored_token.get("dataset_id") and stored_token["dataset_id"] != dataset_id:
            raise ValueError("Preview token was generated for a different dataset.")
        resolved_action_id = resolved_action_id or stored_token.get("action_id")

    recipients_list = validate_recipients(recipient)
    cleaned_recipient = ", ".join(recipients_list)
    report = generate_report_content(dataset_id, report_type, custom_notes)
    final_subject = (subject or report["subject"]).strip()

    # Duplicate send prevention: strictly check if identical email was sent in the last 60 seconds
    send_signature = hashlib.sha256(
        f"{workspace_id}:{cleaned_recipient}:{final_subject}:{idempotency_key or ''}".encode()
    ).hexdigest()

    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()
        recent_dup = db.one(
            "SELECT * FROM email_deliveries WHERE signature=? AND status='sent' AND sent_at > ?",
            (send_signature, cutoff),
        )
    except Exception:
        recent_dup = None

    if recent_dup:
        return {
            "ok": True,
            "deduplicated": True,
            "message_id": recent_dup["message_id"],
            "recipient": cleaned_recipient,
            "subject": final_subject,
            "sent_at": recent_dup["sent_at"],
            "status": "already_sent",
            "note": "Identical report was already sent within the last 60 seconds. Duplicate suppressed.",
        }

    # Fetch fresh Google OAuth access token
    access_token = get_valid_access_token(workspace_id)

    # Build MIME message
    msg = EmailMessage()
    msg["Subject"] = final_subject
    msg["From"] = email.utils.formataddr((cfg.GMAIL_SENDER_NAME, cfg.GMAIL_SENDER_EMAIL))
    msg["To"] = cleaned_recipient
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain="anshora.ai")

    msg.set_content(report["text_body"])
    msg.add_alternative(report["html_body"], subtype="html")

    # Add attachments
    df = dataset_store.get(dataset_id)
    filename = dataset_store.get_filename(dataset_id)
    stem = Path(filename).stem

    if format_type in ("pdf", "both"):
        pdf_bytes = exporter.to_pdf(report["payload"])
        msg.add_attachment(
            pdf_bytes,
            maintype="application",
            subtype="pdf",
            filename=f"anshora-report-{stem}.pdf",
        )
    if format_type in ("csv", "both"):
        csv_bytes = df.to_csv(index=False).encode("utf-8")
        msg.add_attachment(
            csv_bytes,
            maintype="text",
            subtype="csv",
            filename=f"data-{stem}.csv",
        )

    # Base64url encode for Gmail API
    raw_mime = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    gmail_resp = requests.post(GMAIL_SEND_API, headers=headers, json={"raw": raw_mime}, timeout=30)

    delivery_id = db.new_id()
    sent_at = db.now()

    if not gmail_resp.ok:
        err_detail = gmail_resp.text
        try:
            err_detail = gmail_resp.json().get("error", {}).get("message") or err_detail
        except Exception:
            pass
        db.execute(
            "INSERT INTO email_deliveries(id, workspace_id, recipient, subject, report_type, format, status, error, signature, action_id, sent_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                delivery_id,
                workspace_id,
                cleaned_recipient,
                final_subject,
                report_type,
                format_type,
                "failed",
                err_detail,
                send_signature,
                resolved_action_id,
                sent_at,
            ),
        )
        raise ValueError(f"Gmail API delivery failed: {err_detail}")

    gmail_result = gmail_resp.json()
    message_id = gmail_result.get("id") or "sent"

    db.execute(
        "INSERT INTO email_deliveries(id, workspace_id, recipient, subject, report_type, format, status, message_id, signature, action_id, sent_at) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            delivery_id,
            workspace_id,
            cleaned_recipient,
            final_subject,
            report_type,
            format_type,
            "sent",
            message_id,
            send_signature,
            resolved_action_id,
            sent_at,
        ),
    )

    db.audit(workspace_id, "system", "email.send", f"Sent report to {cleaned_recipient} ({message_id})")

    if preview_token:
        try:
            db.execute("DELETE FROM email_preview_tokens WHERE token=?", (preview_token,))
        except Exception:
            pass

    # Clear pending action from active chats for this dataset
    try:
        db.execute("UPDATE chats SET pending_action=NULL, updated_at=? WHERE workspace_id=? AND dataset_id=?",
                   (db.now(), workspace_id, dataset_id))
    except Exception:
        pass

    return {
        "ok": True,
        "message_id": message_id,
        "recipient": cleaned_recipient,
        "subject": final_subject,
        "sent_at": sent_at,
        "status": "accepted_by_gmail",
        "action_id": resolved_action_id,
        "sender": f"{cfg.GMAIL_SENDER_NAME} <{cfg.GMAIL_SENDER_EMAIL}>",
        "notice": "Gmail accepted this message for dispatch. Inbox delivery depends on recipient mailbox provider policies.",
    }
