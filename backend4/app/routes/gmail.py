"""
FastAPI router for Gmail Report Delivery & Google OAuth 2.0.
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core import config as cfg
from app.core import db
from app.core.security import require_user
from app.services import gmail_service

router = APIRouter(prefix="/api/gmail", tags=["Gmail Delivery"])


class PreviewRequest(BaseModel):
    dataset_id: str
    recipient: str
    subject: str | None = None
    report_type: str = "executive"
    format: str = "pdf"
    custom_notes: str = ""


class SendRequest(BaseModel):
    dataset_id: str
    recipient: str
    confirmation: bool = False
    subject: str | None = None
    report_type: str = "executive"
    format: str = "pdf"
    custom_notes: str = ""
    idempotency_key: str | None = None
    preview_token: str | None = None
    action_id: str | None = None


@router.get("/status")
def get_status(user: dict = Depends(require_user)):
    """Returns whether Gmail is connected and configured for this workspace."""
    return gmail_service.get_connection_status(user["workspace_id"])


@router.get("/oauth/authorize")
def authorize_gmail(return_to: str | None = None, user: dict = Depends(require_user)):
    """Generates the Google OAuth 2.0 consent URL."""
    try:
        return gmail_service.create_authorization_url(
            user["workspace_id"], user["id"], return_to or cfg.FRONTEND_URL
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/oauth/callback")
def oauth_callback(code: str = Query(None), state: str = Query(None), error: str = Query(None)):
    """
    Exact Google Cloud OAuth 2.0 redirect callback endpoint.
    Redirect URI registered in Google Cloud Console:
    http://localhost:8000/api/gmail/oauth/callback
    """
    if error:
        frontend_err = f"{cfg.FRONTEND_URL}/?gmail_error={error}"
        return RedirectResponse(frontend_err)

    if not code or not state:
        raise HTTPException(400, "Missing authorization code or state parameter.")

    try:
        res = gmail_service.exchange_code_for_tokens(code, state)
        redirect_base = res.get("redirect_url") or cfg.FRONTEND_URL
        sep = "&" if "?" in redirect_base else "?"
        return RedirectResponse(f"{redirect_base}{sep}gmail=connected")
    except ValueError as e:
        sep = "&" if "?" in cfg.FRONTEND_URL else "?"
        return RedirectResponse(f"{cfg.FRONTEND_URL}{sep}gmail_error={str(e)}")


@router.post("/disconnect")
def disconnect(user: dict = Depends(require_user)):
    """Disconnects the Gmail integration."""
    gmail_service.disconnect_gmail(user["workspace_id"])
    db.audit(user["workspace_id"], user["id"], "gmail.disconnect", "Disconnected Gmail integration")
    return {"ok": True, "message": "Gmail integration disconnected."}


@router.post("/preview")
def preview_email(body: PreviewRequest, user: dict = Depends(require_user)):
    """Generates a complete email preview for explicit user confirmation."""
    try:
        preview = gmail_service.prepare_email_preview(
            dataset_id=body.dataset_id,
            recipient=body.recipient,
            report_type=body.report_type,
            format_type=body.format,
            custom_notes=body.custom_notes,
            workspace_id=user["workspace_id"],
            subject=body.subject,
        )
        return preview
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to generate email preview: {e}")


@router.post("/send")
def send_email(body: SendRequest, user: dict = Depends(require_user)):
    """
    Explicitly confirmed email sending endpoint.
    Strictly requires confirmation=True.
    """
    if not body.confirmation:
        raise HTTPException(
            400,
            "Explicit user confirmation is required to deliver reports. Please review the email preview and confirm.",
        )

    try:
        result = gmail_service.send_email_report(
            workspace_id=user["workspace_id"],
            dataset_id=body.dataset_id,
            recipient=body.recipient,
            subject=body.subject,
            report_type=body.report_type,
            format_type=body.format,
            custom_notes=body.custom_notes,
            confirmation=True,
            idempotency_key=body.idempotency_key,
            preview_token=body.preview_token,
            action_id=body.action_id,
        )
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Delivery error: {e}")


@router.get("/deliveries")
def list_deliveries(limit: int = 50, user: dict = Depends(require_user)):
    """Lists email delivery history for audit and transparency."""
    rows = db.query(
        "SELECT * FROM email_deliveries WHERE workspace_id=? ORDER BY sent_at DESC LIMIT ?",
        (user["workspace_id"], min(limit, 100)),
    )
    return {"deliveries": rows}
