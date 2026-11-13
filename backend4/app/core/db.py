"""Tiny SQLite persistence layer (stdlib only). Swap for Postgres in production."""
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from app.core.config import DB_PATH

_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS workspaces(
  id TEXT PRIMARY KEY, name TEXT, currency TEXT, industry_pack TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY, email TEXT UNIQUE, name TEXT, password_hash TEXT,
  workspace_id TEXT, role TEXT DEFAULT 'admin', created_at TEXT);
CREATE TABLE IF NOT EXISTS projects(
  id TEXT PRIMARY KEY, workspace_id TEXT, name TEXT, instructions TEXT DEFAULT '',
  industry_pack TEXT, currency TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS datasets(
  id TEXT PRIMARY KEY, workspace_id TEXT, project_id TEXT, filename TEXT, path TEXT,
  rows INTEGER, cols INTEGER, uploaded_at TEXT, pack_id TEXT, source TEXT DEFAULT 'upload',
  business_context TEXT, alert_rules TEXT, alert_history TEXT);
CREATE TABLE IF NOT EXISTS chats(
  id TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT, project_id TEXT, dataset_id TEXT,
  title TEXT, pending_action TEXT, created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS messages(
  id TEXT PRIMARY KEY, chat_id TEXT, role TEXT, content TEXT, meta TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decisions(
  id TEXT PRIMARY KEY, workspace_id TEXT, dataset_id TEXT, title TEXT, action TEXT,
  owner TEXT, metric_column TEXT, aggregation TEXT, direction TEXT DEFAULT 'up', baseline_value REAL,
  expected_impact REAL, status TEXT DEFAULT 'open', latest_value REAL,
  realized_impact REAL, created_at TEXT, evaluated_at TEXT);
CREATE TABLE IF NOT EXISTS monitors(
  id TEXT PRIMARY KEY, workspace_id TEXT, dataset_id TEXT, name TEXT, kind TEXT,
  config TEXT, interval_minutes INTEGER DEFAULT 60, channels TEXT, enabled INTEGER DEFAULT 1,
  last_run TEXT, last_status TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS notifications(
  id TEXT PRIMARY KEY, workspace_id TEXT, monitor_id TEXT, dataset_id TEXT, title TEXT,
  body TEXT, severity TEXT, impact REAL, read INTEGER DEFAULT 0, created_at TEXT);
CREATE TABLE IF NOT EXISTS audit_log(
  id TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT, action TEXT, detail TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS gmail_integrations(
  id TEXT PRIMARY KEY, workspace_id TEXT UNIQUE, email TEXT,
  refresh_token TEXT, access_token TEXT, expires_at TEXT,
  created_at TEXT, updated_at TEXT);
CREATE TABLE IF NOT EXISTS oauth_states(
  state TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT, redirect_url TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS email_deliveries(
  id TEXT PRIMARY KEY, workspace_id TEXT, recipient TEXT, subject TEXT,
  report_type TEXT, format TEXT, status TEXT, message_id TEXT, error TEXT,
  signature TEXT, action_id TEXT, sent_at TEXT);
CREATE TABLE IF NOT EXISTS email_preview_tokens(
  token TEXT PRIMARY KEY, workspace_id TEXT, dataset_id TEXT, recipient TEXT,
  subject TEXT, format TEXT, action_id TEXT, created_at TEXT, expires_at TEXT);
CREATE TABLE IF NOT EXISTS workspace_members(
  id TEXT PRIMARY KEY, workspace_id TEXT, user_id TEXT, role TEXT DEFAULT 'owner', joined_at TEXT);
CREATE TABLE IF NOT EXISTS oauth_identities(
  id TEXT PRIMARY KEY, user_id TEXT, provider TEXT DEFAULT 'google', provider_user_id TEXT, email TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS reports(
  id TEXT PRIMARY KEY, workspace_id TEXT, dataset_id TEXT, created_by TEXT, title TEXT,
  report_type TEXT DEFAULT 'executive', source TEXT DEFAULT 'ai_narrated', narrative TEXT,
  data_block TEXT, charts TEXT, ai_warning TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS business_memory(
  id TEXT PRIMARY KEY, workspace_id TEXT, category TEXT, key TEXT, summary TEXT, evidence_ref TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS decision_outcomes(
  id TEXT PRIMARY KEY, decision_id TEXT, evaluated_by TEXT, actual_outcome TEXT,
  measured_impact REAL, followed_recommendation INTEGER, evaluated_at TEXT);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


@contextmanager
def conn():
    with _lock:
        c = sqlite3.connect(str(DB_PATH), timeout=30)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA foreign_keys=ON")
        try:
            yield c
            c.commit()
        finally:
            c.close()


def init_db():
    with conn() as c:
        c.executescript(SCHEMA)
        # lightweight migrations for databases created by older versions
        cols = {r["name"] for r in c.execute("PRAGMA table_info(datasets)").fetchall()}
        if "settings" not in cols:
            c.execute("ALTER TABLE datasets ADD COLUMN settings TEXT")

        chat_cols = {r["name"] for r in c.execute("PRAGMA table_info(chats)").fetchall()}
        if "pending_action" not in chat_cols:
            c.execute("ALTER TABLE chats ADD COLUMN pending_action TEXT")

        delivery_cols = {r["name"] for r in c.execute("PRAGMA table_info(email_deliveries)").fetchall()}
        if "action_id" not in delivery_cols:
            c.execute("ALTER TABLE email_deliveries ADD COLUMN action_id TEXT")
        if "user_id" not in delivery_cols:
            c.execute("ALTER TABLE email_deliveries ADD COLUMN user_id TEXT")

        token_cols = {r["name"] for r in c.execute("PRAGMA table_info(email_preview_tokens)").fetchall()}
        if "action_id" not in token_cols:
            c.execute("ALTER TABLE email_preview_tokens ADD COLUMN action_id TEXT")

        dec_cols = {r["name"] for r in c.execute("PRAGMA table_info(decisions)").fetchall()}
        new_dec_cols = {
            "problem": "TEXT",
            "evidence": "TEXT",
            "assumptions": "TEXT",
            "risks": "TEXT",
            "confidence": "TEXT DEFAULT 'medium'",
            "justification": "TEXT",
            "priority": "TEXT DEFAULT 'medium'",
            "review_date": "TEXT",
            "actual_outcome": "TEXT",
            "measured_impact": "REAL",
            "followed_recommendation": "INTEGER",
        }
        for col_name, col_type in new_dec_cols.items():
            if col_name not in dec_cols:
                c.execute(f"ALTER TABLE decisions ADD COLUMN {col_name} {col_type}")

        # Phase 2 migrations
        ws_cols = {r["name"] for r in c.execute("PRAGMA table_info(workspaces)").fetchall()}
        if "created_by" not in ws_cols:
            c.execute("ALTER TABLE workspaces ADD COLUMN created_by TEXT")
        if "updated_at" not in ws_cols:
            c.execute("ALTER TABLE workspaces ADD COLUMN updated_at TEXT")

        user_cols = {r["name"] for r in c.execute("PRAGMA table_info(users)").fetchall()}
        for col, ctype in [
            ("google_subject_id", "TEXT"),
            ("email_verified", "INTEGER DEFAULT 0"),
            ("profile_image_url", "TEXT"),
            ("account_status", "TEXT DEFAULT 'active'"),
            ("updated_at", "TEXT"),
            ("last_login_at", "TEXT"),
        ]:
            if col not in user_cols:
                c.execute(f"ALTER TABLE users ADD COLUMN {col} {ctype}")

        ds_cols = {r["name"] for r in c.execute("PRAGMA table_info(datasets)").fetchall()}
        for col, ctype in [
            ("user_id", "TEXT"),
            ("file_size_bytes", "INTEGER DEFAULT 0"),
            ("mime_type", "TEXT DEFAULT 'text/csv'"),
            ("processing_status", "TEXT DEFAULT 'ready'"),
        ]:
            if col not in ds_cols:
                c.execute(f"ALTER TABLE datasets ADD COLUMN {col} {ctype}")

        if "is_guest" not in chat_cols:
            c.execute("ALTER TABLE chats ADD COLUMN is_guest INTEGER DEFAULT 0")


def execute(sql, params=()):
    with conn() as c:
        cur = c.execute(sql, params)
        return cur.rowcount


def query(sql, params=()):
    with conn() as c:
        return [dict(r) for r in c.execute(sql, params).fetchall()]


def one(sql, params=()):
    rows = query(sql, params)
    return rows[0] if rows else None


def dumps(v) -> str:
    return json.dumps(v, default=str)


def loads(s, default=None):
    if s is None or s == "":
        return default
    try:
        return json.loads(s)
    except Exception:
        return default


def audit(workspace_id, user_id, action, detail=""):
    try:
        execute(
            "INSERT INTO audit_log(id,workspace_id,user_id,action,detail,ts) VALUES(?,?,?,?,?,?)",
            (new_id(), workspace_id, user_id, action, str(detail)[:500], now()),
        )
    except Exception:
        pass
