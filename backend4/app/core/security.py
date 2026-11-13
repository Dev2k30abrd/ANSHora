"""Password hashing (scrypt, stdlib) + JWT auth dependency."""
import hashlib
import hmac
import os
import time

import jwt
from fastapi import Depends, HTTPException, Request

from app.core import db
from app.core.config import (
    AUTH_REQUIRED,
    DEFAULT_CURRENCY,
    TOKEN_TTL_HOURS,
    get_jwt_secret,
)
from app.core.context import current_user_id, current_workspace


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        calc = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(calc.hex(), h)
    except Exception:
        return False


def create_token(user: dict) -> str:
    payload = {
        "sub": user["id"],
        "ws": user["workspace_id"],
        "exp": int(time.time()) + TOKEN_TTL_HOURS * 3600,
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm="HS256")


def create_user(email: str, name: str, password: str, workspace_name: str | None = None) -> dict:
    email = email.strip().lower()
    if db.one("SELECT id FROM users WHERE email=?", (email,)):
        raise HTTPException(status_code=409, detail="Email already registered.")
    ws_id, uid = db.new_id(), db.new_id()
    now_ts = db.now()
    db.execute(
        "INSERT INTO workspaces(id,name,currency,industry_pack,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
        (ws_id, workspace_name or f"{name}'s workspace", DEFAULT_CURRENCY, "general", uid, now_ts, now_ts),
    )
    db.execute(
        "INSERT INTO users(id,email,name,password_hash,workspace_id,role,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (uid, email, name, hash_password(password), ws_id, "admin", now_ts, now_ts),
    )
    db.execute(
        "INSERT INTO workspace_members(id,workspace_id,user_id,role,joined_at) VALUES(?,?,?,?,?)",
        (db.new_id(), ws_id, uid, "owner", now_ts),
    )
    db.audit(ws_id, uid, "user.register", email)
    return db.one("SELECT * FROM users WHERE id=?", (uid,))


def _local_user() -> dict:
    u = db.one("SELECT * FROM users WHERE email=?", ("local@anshora.local",))
    if u:
        return u
    return create_user("local@anshora.local", "Local User", os.urandom(8).hex(), "Local workspace")


async def require_user(request: Request) -> dict:
    """Async on purpose: it sets contextvars that sync endpoints (threadpool) inherit."""
    header = request.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else request.query_params.get("token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    try:
        data = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token.")
    user = db.one("SELECT * FROM users WHERE id=?", (data.get("sub"),))
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    current_workspace.set(user["workspace_id"])
    current_user_id.set(user["id"])
    return user


def public_user(user: dict) -> dict:
    ws = db.one("SELECT * FROM workspaces WHERE id=?", (user["workspace_id"],)) or {}
    is_guest = user.get("role") == "guest" or user.get("email", "").startswith("guest_")
    return {
        "id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user.get("role", "admin"),
        "is_guest": is_guest,
        "profile_image_url": user.get("profile_image_url"),
        "workspace": {
            "id": user["workspace_id"],
            "name": ws.get("name"),
            "currency": ws.get("currency") or DEFAULT_CURRENCY,
            "industry_pack": ws.get("industry_pack") or "general",
        },
    }
