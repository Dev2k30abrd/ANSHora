import os
import re
import time
from collections import defaultdict
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core import config as cfg
from app.core import db
from app.core.security import create_token, create_user, public_user, require_user, verify_password
from app.packs import PACKS
from app.services.google_auth_service import (
    create_google_authorization_url,
    process_google_callback,
    verify_id_token_claims,
)

router = APIRouter(prefix="/api/auth", tags=["Auth"])
_attempts: dict[str, list[float]] = defaultdict(list)


class RegisterBody(BaseModel):
    email: str
    name: str
    password: str
    workspace_name: str | None = None


class LoginBody(BaseModel):
    email: str
    password: str


class GoogleVerifyBody(BaseModel):
    id_token: str


class WorkspaceBody(BaseModel):
    name: str | None = None
    currency: str | None = None
    industry_pack: str | None = None


@router.post("/register")
def register(b: RegisterBody):
    if not cfg.ALLOW_REGISTRATION:
        raise HTTPException(403, "Registration is disabled.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", b.email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(b.password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    if not b.name.strip():
        raise HTTPException(400, "Name is required.")
    user = create_user(b.email, b.name.strip(), b.password, b.workspace_name)
    return {"token": create_token(user), "user": public_user(user)}


@router.post("/login")
def login(b: LoginBody):
    key = b.email.strip().lower()
    now = time.time()
    _attempts[key] = [t for t in _attempts[key] if now - t < 300]
    if len(_attempts[key]) >= 8:
        raise HTTPException(429, "Too many attempts. Try again in a few minutes.")
    user = db.one("SELECT * FROM users WHERE email=?", (key,))
    if not user or not verify_password(b.password, user["password_hash"]):
        _attempts[key].append(now)
        raise HTTPException(401, "Incorrect email or password.")
    db.audit(user["workspace_id"], user["id"], "user.login")
    return {"token": create_token(user), "user": public_user(user)}


@router.get("/google/authorize")
def google_authorize(return_to: str | None = None, include_gmail: bool = True):
    """Generates the Google OAuth 2.0 authorization URL for Google Sign-In with optional Gmail onboarding."""
    return create_google_authorization_url(return_to=return_to, include_gmail=include_gmail)


@router.get("/google/callback")
def google_callback(
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
    request: Request = None,
):
    """
    Handles Google OAuth 2.0 authorization callback.
    Validates identity, issues session token, and redirects back to React SPA.
    """
    if error:
        frontend_url = cfg.FRONTEND_URL.rstrip("/")
        return RedirectResponse(f"{frontend_url}?auth_error={error}")

    result = process_google_callback(code, state)
    target = result.get("redirect_url") or cfg.FRONTEND_URL
    token = result["token"]

    # If API client requested JSON
    if request and "application/json" in request.headers.get("accept", ""):
        return result

    # Standard browser flow: redirect with session token in query
    separator = "&" if "?" in target else "?"
    redirect_target = f"{target}{separator}token={token}"
    return RedirectResponse(redirect_target, status_code=302)


@router.post("/google/verify")
def google_verify_token(b: GoogleVerifyBody):
    """Directly verifies Google ID token from frontend popup/One-Tap."""
    client_id = cfg.GOOGLE_SIGNIN_CLIENT_ID or cfg.GOOGLE_CLIENT_ID
    claims = verify_id_token_claims(b.id_token, client_id)
    google_sub = str(claims["sub"]).strip()
    email = str(claims["email"]).strip().lower()
    name = str(claims.get("name") or email.split("@")[0]).strip()
    picture = claims.get("picture")

    from app.models import OAuthIdentity, SessionLocal, User, Workspace, WorkspaceMember
    from app.models.base import utc_now

    session = SessionLocal()
    try:
        user = session.query(User).filter_by(google_subject_id=google_sub).first()
        if not user:
            user = session.query(User).filter_by(email=email).first()
            if user:
                user.google_subject_id = google_sub
                user.email_verified = True
                if picture and not user.profile_image_url:
                    user.profile_image_url = picture
                session.add(OAuthIdentity(
                    user_id=user.id,
                    provider="google",
                    provider_user_id=google_sub,
                    email=email,
                ))
            else:
                ws_id = db.new_id()
                ws = Workspace(
                    id=ws_id,
                    name=f"{name}'s workspace",
                    currency=cfg.DEFAULT_CURRENCY,
                    industry_pack="general",
                )
                session.add(ws)
                session.flush()

                user = User(
                    email=email,
                    name=name,
                    google_subject_id=google_sub,
                    email_verified=True,
                    profile_image_url=picture,
                    workspace_id=ws_id,
                    role="admin",
                )
                session.add(user)
                session.flush()

                ws.created_by = user.id
                session.add(WorkspaceMember(workspace_id=ws_id, user_id=user.id, role="owner"))
                session.add(OAuthIdentity(user_id=user.id, provider="google", provider_user_id=google_sub, email=email))

        user.last_login_at = utc_now()
        session.commit()

        user_dict = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "workspace_id": user.workspace_id,
            "profile_image_url": user.profile_image_url,
        }
        return {"token": create_token(user_dict), "user": public_user(user_dict)}
    finally:
        session.close()


@router.post("/guest")
def guest_session():
    """
    Creates an isolated temporary guest session.
    Guest conversations do not persist to permanent chat history.
    """
    guest_id = db.new_id()
    email = f"guest_{guest_id[:8]}@guest.anshora.local"
    ws_id = db.new_id()

    db.execute(
        "INSERT INTO workspaces(id,name,currency,industry_pack,created_at) VALUES(?,?,?,?,?)",
        (ws_id, "Guest workspace", cfg.DEFAULT_CURRENCY, "general", db.now()),
    )
    db.execute(
        "INSERT INTO users(id,email,name,password_hash,workspace_id,role,created_at) VALUES(?,?,?,?,?,?,?)",
        (guest_id, email, "Guest User", os.urandom(8).hex(), ws_id, "guest", db.now()),
    )
    user = db.one("SELECT * FROM users WHERE id=?", (guest_id,))
    return {"token": create_token(user), "user": public_user(user)}


@router.post("/logout")
def logout(user: dict = Depends(require_user)):
    """Logs out and records audit event."""
    db.audit(user["workspace_id"], user["id"], "user.logout")
    return {"message": "Logged out successfully"}


@router.get("/me")
def me(user: dict = Depends(require_user)):
    return {"user": public_user(user)}


@router.patch("/workspace")
def update_workspace(b: WorkspaceBody, user: dict = Depends(require_user)):
    if b.industry_pack and b.industry_pack not in PACKS:
        raise HTTPException(400, "Unknown industry pack.")
    if b.currency is not None and not (1 <= len(b.currency.strip()) <= 4):
        raise HTTPException(400, "Currency symbol must be 1-4 characters.")
    ws = user["workspace_id"]
    if b.name:
        db.execute("UPDATE workspaces SET name=? WHERE id=?", (b.name.strip(), ws))
    if b.currency:
        db.execute("UPDATE workspaces SET currency=? WHERE id=?", (b.currency.strip(), ws))
    if b.industry_pack:
        db.execute("UPDATE workspaces SET industry_pack=? WHERE id=?", (b.industry_pack, ws))
    db.audit(ws, user["id"], "workspace.update", b.model_dump_json())
    return {"user": public_user(user)}

