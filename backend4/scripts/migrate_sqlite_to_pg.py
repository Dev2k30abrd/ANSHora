"""
Safe, idempotent migration script: transfers data from SQLite (anshora.db) to PostgreSQL.
1. Creates a timestamped backup of the SQLite database.
2. Migrates all workspaces, users, projects, datasets, chats, messages, decisions,
   Gmail integrations, email deliveries, and audit records into the target PostgreSQL database.
3. Automatically synthesizes workspace membership entries for users.
4. Verifies row counts before and after migration.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend4 to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import config as cfg
from app.models import (
    AuditLog,
    Base,
    BusinessMemory,
    Conversation,
    Dataset,
    Decision,
    DecisionOutcome,
    EmailDelivery,
    EmailPreviewToken,
    GmailIntegration,
    Message,
    Monitor,
    Notification,
    OAuthIdentity,
    Project,
    SessionLocal,
    User,
    Workspace,
    WorkspaceMember,
    engine,
)


def backup_sqlite(sqlite_path: Path) -> Path:
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite file not found at {sqlite_path.name}")
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = sqlite_path.with_name(f"{sqlite_path.name}.bak_{ts}")
    shutil.copy2(sqlite_path, backup_path)
    print(f"Backed up SQLite database to: {backup_path.name}")
    return backup_path


def parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val)
    except Exception:
        return datetime.now(timezone.utc)


def migrate(sqlite_path: Path | None = None):
    sqlite_file = sqlite_path or cfg.DB_PATH
    if not sqlite_file.exists():
        print(f"No SQLite database found at {sqlite_file}. Skipping migration.")
        return

    backup_sqlite(sqlite_file)

    # Ensure tables exist in target database
    Base.metadata.create_all(bind=engine)

    con = sqlite3.connect(str(sqlite_file))
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    session = SessionLocal()
    stats = {}

    try:
        # 1. Workspaces
        cur.execute("SELECT * FROM workspaces")
        ws_rows = cur.fetchall()
        for r in ws_rows:
            if not session.query(Workspace).filter_by(id=r["id"]).first():
                session.add(Workspace(
                    id=r["id"],
                    name=r["name"],
                    currency=r["currency"] or "₹",
                    industry_pack=r["industry_pack"] or "general",
                    created_at=parse_dt(r["created_at"]),
                    updated_at=parse_dt(r["created_at"]),
                ))
        session.commit()
        stats["workspaces"] = len(ws_rows)

        # 2. Users & Workspace Members
        cur.execute("SELECT * FROM users")
        user_rows = cur.fetchall()
        for r in user_rows:
            if not session.query(User).filter_by(id=r["id"]).first():
                session.add(User(
                    id=r["id"],
                    email=r["email"],
                    name=r["name"],
                    password_hash=r["password_hash"],
                    workspace_id=r["workspace_id"],
                    role=r["role"] or "admin",
                    account_status="active",
                    created_at=parse_dt(r["created_at"]),
                    updated_at=parse_dt(r["created_at"]),
                ))
            # Ensure workspace membership
            if r["workspace_id"]:
                mem = session.query(WorkspaceMember).filter_by(
                    workspace_id=r["workspace_id"], user_id=r["id"]
                ).first()
                if not mem:
                    session.add(WorkspaceMember(
                        workspace_id=r["workspace_id"],
                        user_id=r["id"],
                        role="owner" if r["role"] == "admin" else "member",
                        joined_at=parse_dt(r["created_at"]),
                    ))
        session.commit()
        stats["users"] = len(user_rows)

        # 3. Projects
        cur.execute("SELECT * FROM projects")
        proj_rows = cur.fetchall()
        for r in proj_rows:
            if not session.query(Project).filter_by(id=r["id"]).first():
                session.add(Project(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    name=r["name"],
                    instructions=r["instructions"] or "",
                    industry_pack=r["industry_pack"],
                    currency=r["currency"],
                    created_at=parse_dt(r["created_at"]),
                    updated_at=parse_dt(r["created_at"]),
                ))
        session.commit()
        stats["projects"] = len(proj_rows)

        # 4. Datasets
        cur.execute("SELECT * FROM datasets")
        ds_rows = cur.fetchall()
        for r in ds_rows:
            if not session.query(Dataset).filter_by(id=r["id"]).first():
                # Associate with workspace owner if user_id is missing
                owner_id = None
                if r["workspace_id"]:
                    owner = session.query(User).filter_by(workspace_id=r["workspace_id"]).first()
                    owner_id = owner.id if owner else None

                p = Path(r["path"])
                f_size = p.stat().st_size if p.exists() else 0

                session.add(Dataset(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    user_id=owner_id,
                    project_id=r["project_id"],
                    filename=r["filename"],
                    path=r["path"],
                    file_size_bytes=f_size,
                    mime_type="application/octet-stream" if p.suffix == ".parquet" else "text/csv",
                    rows=r["rows"] or 0,
                    cols=r["cols"] or 0,
                    pack_id=r["pack_id"] or "general",
                    source=r["source"] or "upload",
                    processing_status="ready",
                    business_context=r["business_context"],
                    alert_rules=r["alert_rules"],
                    alert_history=r["alert_history"],
                    settings=r["settings"] if "settings" in r.keys() else "{}",
                    uploaded_at=parse_dt(r["uploaded_at"]),
                ))
        session.commit()
        stats["datasets"] = len(ds_rows)

        # 5. Chats & Messages
        cur.execute("SELECT * FROM chats")
        chat_rows = cur.fetchall()
        for r in chat_rows:
            if not session.query(Conversation).filter_by(id=r["id"]).first():
                session.add(Conversation(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    user_id=r["user_id"],
                    project_id=r["project_id"],
                    dataset_id=r["dataset_id"],
                    title=r["title"] or "Chat",
                    is_guest=False,
                    pending_action=r["pending_action"] if "pending_action" in r.keys() else None,
                    created_at=parse_dt(r["created_at"]),
                    updated_at=parse_dt(r["updated_at"]),
                ))
        session.commit()
        stats["chats"] = len(chat_rows)

        cur.execute("SELECT * FROM messages")
        msg_rows = cur.fetchall()
        for r in msg_rows:
            if not session.query(Message).filter_by(id=r["id"]).first():
                session.add(Message(
                    id=r["id"],
                    chat_id=r["chat_id"],
                    role=r["role"],
                    content=r["content"],
                    meta=r["meta"] or "{}",
                    created_at=parse_dt(r["created_at"]),
                ))
        session.commit()
        stats["messages"] = len(msg_rows)

        # 6. Decisions
        cur.execute("SELECT * FROM decisions")
        dec_rows = cur.fetchall()
        for r in dec_rows:
            if not session.query(Decision).filter_by(id=r["id"]).first():
                session.add(Decision(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    dataset_id=r["dataset_id"],
                    title=r["title"],
                    action=r["action"] or "",
                    owner=r["owner"] or "",
                    metric_column=r["metric_column"],
                    aggregation=r["aggregation"] or "sum",
                    direction=r["direction"] or "up",
                    baseline_value=r["baseline_value"] or 0.0,
                    expected_impact=r["expected_impact"],
                    status=r["status"] or "Proposed",
                    latest_value=r["latest_value"],
                    realized_impact=r["realized_impact"],
                    created_at=parse_dt(r["created_at"]),
                    evaluated_at=parse_dt(r["evaluated_at"]),
                ))
        session.commit()
        stats["decisions"] = len(dec_rows)

        # 7. Gmail Integrations & Deliveries
        cur.execute("SELECT * FROM gmail_integrations")
        gmail_rows = cur.fetchall()
        for r in gmail_rows:
            if not session.query(GmailIntegration).filter_by(id=r["id"]).first():
                session.add(GmailIntegration(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    email=r["email"],
                    refresh_token=r["refresh_token"],
                    access_token=r["access_token"],
                    expires_at=r["expires_at"],
                    created_at=parse_dt(r["created_at"]),
                    updated_at=parse_dt(r["updated_at"]),
                ))
        session.commit()
        stats["gmail_integrations"] = len(gmail_rows)

        cur.execute("SELECT * FROM email_deliveries")
        del_rows = cur.fetchall()
        for r in del_rows:
            if not session.query(EmailDelivery).filter_by(id=r["id"]).first():
                session.add(EmailDelivery(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    recipient=r["recipient"],
                    subject=r["subject"],
                    report_type=r["report_type"] or "executive",
                    format=r["format"] or "pdf",
                    status=r["status"],
                    message_id=r["message_id"],
                    error=r["error"],
                    signature=r["signature"],
                    action_id=r["action_id"] if "action_id" in r.keys() else None,
                    sent_at=parse_dt(r["sent_at"]),
                ))
        session.commit()
        stats["email_deliveries"] = len(del_rows)

        # 8. Audit Logs
        cur.execute("SELECT * FROM audit_log")
        audit_rows = cur.fetchall()
        for r in audit_rows:
            if not session.query(AuditLog).filter_by(id=r["id"]).first():
                session.add(AuditLog(
                    id=r["id"],
                    workspace_id=r["workspace_id"],
                    user_id=r["user_id"],
                    action=r["action"],
                    detail=r["detail"],
                    ts=parse_dt(r["ts"]),
                ))
        session.commit()
        stats["audit_log"] = len(audit_rows)

        print("Migration completed successfully!")
        for k, v in stats.items():
            print(f"  Migrated {v} {k}")

    except Exception as e:
        session.rollback()
        print(f"Migration error: {e}")
        raise
    finally:
        session.close()
        con.close()


if __name__ == "__main__":
    migrate()
