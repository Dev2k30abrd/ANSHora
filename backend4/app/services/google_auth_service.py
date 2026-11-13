"""
Google OAuth 2.0 Sign-In Service (Server-side Authorization Code Flow).
Implements secure identity verification, ID token validation, CSRF state protection,
and stable account resolution.
"""
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import jwt
import requests
from fastapi import HTTPException

from app.core import config as cfg
from app.core import db
from app.core.security import create_token, public_user
from app.models import OAuthIdentity, SessionLocal, User, Workspace, WorkspaceMember
from app.models.base import utc_now

logger = logging.getLogger("anshora.google_auth")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
SIGNIN_SCOPES = "openid email profile"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"


def create_google_authorization_url(return_to: str | None = None, include_gmail: bool = True) -> dict:
    """
    Initiates Google Sign-In authorization flow with optional incremental Gmail authorization.
    Generates a secure state token and returns the Google OAuth consent URL.
    """
    client_id = cfg.GOOGLE_SIGNIN_CLIENT_ID or cfg.GOOGLE_CLIENT_ID
    redirect_uri = cfg.GOOGLE_SIGNIN_REDIRECT_URI

    if not client_id:
        raise HTTPException(
            status_code=500,
            detail="Google Sign-In is not configured. Missing GOOGLE_CLIENT_ID on server.",
        )

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(16)
    target = return_to or cfg.FRONTEND_URL

    db.execute(
        "INSERT INTO oauth_states(state,workspace_id,user_id,redirect_url,created_at) VALUES(?,?,?,?,?)",
        (state, None, None, target, db.now()),
    )

    scopes = f"{SIGNIN_SCOPES} {GMAIL_SEND_SCOPE}" if include_gmail else SIGNIN_SCOPES

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scopes,
        "state": state,
        "nonce": nonce,
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent select_account" if include_gmail else "select_account",
    }
    auth_url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return {"url": auth_url, "state": state, "gmail_requested": include_gmail}


def verify_id_token_claims(id_token: str, client_id: str) -> dict:
    """
    Decodes and validates Google ID token claims:
    - Issuer: accounts.google.com or https://accounts.google.com
    - Audience: matching server's Google Client ID
    - Expiration: not expired
    - Email verification: email_verified must be True
    """
    try:
        claims = jwt.decode(id_token, options={"verify_signature": False})
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid ID token format: {e}")

    # Verify issuer
    iss = claims.get("iss", "")
    if iss not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(status_code=401, detail=f"Untrusted token issuer: {iss}")

    # Verify audience
    aud = claims.get("aud", "")
    if aud != client_id:
        raise HTTPException(status_code=401, detail=f"Token audience mismatch: expected {client_id}, got {aud}")

    # Verify expiration
    exp = claims.get("exp", 0)
    if exp < time.time() - 30:  # 30s clock skew tolerance
        raise HTTPException(status_code=401, detail="ID token has expired.")

    # Verify email verified
    if not claims.get("email_verified", False):
        raise HTTPException(status_code=403, detail="Google account email is not verified.")

    return claims


def process_google_callback(code: str, state: str) -> dict:
    """
    Exchanges code for tokens, verifies claims, creates or resolves user,
    and returns a signed Anshora application session token.
    """
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing authorization code or state.")

    # 1. Validate CSRF state
    st = db.one("SELECT * FROM oauth_states WHERE state=?", (state,))
    if not st:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state parameter.")

    # Delete state token (single-use protection)
    db.execute("DELETE FROM oauth_states WHERE state=?", (state,))
    redirect_url = st.get("redirect_url") or cfg.FRONTEND_URL

    client_id = cfg.GOOGLE_SIGNIN_CLIENT_ID or cfg.GOOGLE_CLIENT_ID
    client_secret = cfg.GOOGLE_SIGNIN_CLIENT_SECRET or cfg.GOOGLE_CLIENT_SECRET
    redirect_uri = cfg.GOOGLE_SIGNIN_REDIRECT_URI

    # 2. Server-side token exchange
    token_resp = requests.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=15,
    )

    if not token_resp.ok:
        logger.error("Google token exchange failed: %s %s", token_resp.status_code, token_resp.text)
        raise HTTPException(status_code=502, detail="Failed to exchange authorization code with Google.")

    token_data = token_resp.json()
    id_token = token_data.get("id_token")
    if not id_token:
        raise HTTPException(status_code=502, detail="Google response did not include an ID token.")

    # 3. Validate claims
    claims = verify_id_token_claims(id_token, client_id)
    google_sub = str(claims["sub"]).strip()
    email = str(claims["email"]).strip().lower()
    name = str(claims.get("name") or email.split("@")[0]).strip()
    picture = claims.get("picture")

    # 4. Resolve or create user in database
    session = SessionLocal()
    try:
        user = session.query(User).filter_by(google_subject_id=google_sub).first()
        if not user:
            # Check by OAuth identity
            identity = session.query(OAuthIdentity).filter_by(
                provider="google", provider_user_id=google_sub
            ).first()
            if identity:
                user = identity.user

        if not user:
            # Check if user with same email exists
            user = session.query(User).filter_by(email=email).first()
            if user:
                # Safely link Google subject to existing verified user
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
                # Create brand new user + personal workspace
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
                    password_hash=None,
                    google_subject_id=google_sub,
                    email_verified=True,
                    profile_image_url=picture,
                    workspace_id=ws_id,
                    role="admin",
                    account_status="active",
                )
                session.add(user)
                session.flush()

                ws.created_by = user.id
                session.add(WorkspaceMember(
                    workspace_id=ws_id,
                    user_id=user.id,
                    role="owner",
                ))
                session.add(OAuthIdentity(
                    user_id=user.id,
                    provider="google",
                    provider_user_id=google_sub,
                    email=email,
                ))

        # Update last login timestamp
        user.last_login_at = utc_now()
        session.commit()

        # Step 5: If Gmail authorization was consented by the user, securely store it
        granted_scope = str(token_data.get("scope", ""))
        has_gmail_scope = GMAIL_SEND_SCOPE in granted_scope or "gmail.send" in granted_scope
        refresh_token = token_data.get("refresh_token")
        access_token = token_data.get("access_token")
        expires_in = token_data.get("expires_in", 3600)
        expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

        if has_gmail_scope:
            existing_gmail = db.one("SELECT refresh_token FROM gmail_integrations WHERE workspace_id=?", (user.workspace_id,))
            stored_refresh = refresh_token or (existing_gmail.get("refresh_token") if existing_gmail else None)
            if stored_refresh:
                db.execute(
                    "INSERT INTO gmail_integrations(id, workspace_id, email, refresh_token, access_token, expires_at, created_at, updated_at) "
                    "VALUES(?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(workspace_id) DO UPDATE SET "
                    "email=excluded.email, refresh_token=excluded.refresh_token, access_token=excluded.access_token, "
                    "expires_at=excluded.expires_at, updated_at=excluded.updated_at",
                    (
                        db.new_id(),
                        user.workspace_id,
                        email,
                        stored_refresh,
                        access_token,
                        expires_at,
                        db.now(),
                        db.now(),
                    ),
                )
                db.audit(user.workspace_id, user.id, "gmail.oauth_connected", f"Google Sign-In linked Gmail: {email}")
                logger.info("Gmail integration securely linked during Google Sign-In for workspace %s (%s)", user.workspace_id, email)

        user_dict = {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "role": user.role,
            "workspace_id": user.workspace_id,
            "profile_image_url": user.profile_image_url,
        }
        app_token = create_token(user_dict)
        pub_user = public_user(user_dict)
        db.audit(user.workspace_id, user.id, "user.google_signin", email)

        return {
            "token": app_token,
            "user": pub_user,
            "redirect_url": redirect_url,
            "gmail_connected": bool(has_gmail_scope),
        }

    except Exception as e:
        session.rollback()
        logger.exception("Error processing Google Sign-In user resolution: %s", e)
        raise HTTPException(status_code=500, detail="Failed to initialize user session.")
    finally:
        session.close()
