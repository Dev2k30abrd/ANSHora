"""
Workspace Management API.
Supports creating, renaming, listing, switching, and deleting multi-tenant workspaces.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import config as cfg
from app.core import db
from app.core.security import create_token, public_user, require_user
from app.core.tenancy import verify_workspace_access
from app.packs import PACKS

router = APIRouter(prefix="/api/workspaces", tags=["Workspaces"])


class CreateWorkspaceBody(BaseModel):
    name: str
    currency: str = cfg.DEFAULT_CURRENCY
    industry_pack: str = "general"


class UpdateWorkspaceBody(BaseModel):
    name: str | None = None
    currency: str | None = None
    industry_pack: str | None = None


@router.get("")
def list_workspaces(user: dict = Depends(require_user)):
    """Lists all workspaces accessible to the user."""
    # Find workspaces via membership or direct workspace_id
    workspaces = db.query(
        "SELECT DISTINCT w.*, COALESCE(wm.role, 'owner') as member_role FROM workspaces w "
        "LEFT JOIN workspace_members wm ON wm.workspace_id = w.id "
        "WHERE wm.user_id = ? OR w.id = ? ORDER BY w.created_at DESC",
        (user["id"], user["workspace_id"]),
    )
    return {"workspaces": workspaces, "active_workspace_id": user["workspace_id"]}


@router.post("")
def create_workspace(b: CreateWorkspaceBody, user: dict = Depends(require_user)):
    """Creates a new workspace and sets caller as owner."""
    if not b.name.strip():
        raise HTTPException(400, "Workspace name is required.")
    if b.industry_pack not in PACKS:
        raise HTTPException(400, "Unknown industry pack.")
    if not (1 <= len(b.currency.strip()) <= 4):
        raise HTTPException(400, "Currency must be 1-4 characters.")

    ws_id, now = db.new_id(), db.now()
    db.execute(
        "INSERT INTO workspaces(id,name,currency,industry_pack,created_by,created_at,updated_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (ws_id, b.name.strip(), b.currency.strip(), b.industry_pack, user["id"], now, now),
    )
    # Add member
    db.execute(
        "INSERT INTO workspace_members(id,workspace_id,user_id,role,joined_at) VALUES(?,?,?,?,?)",
        (db.new_id(), ws_id, user["id"], "owner", now),
    )
    db.audit(ws_id, user["id"], "workspace.create", b.name.strip())
    return {"workspace": db.one("SELECT * FROM workspaces WHERE id=?", (ws_id,))}


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str, user: dict = Depends(require_user)):
    """Gets details and stats for a workspace."""
    ws = verify_workspace_access(workspace_id, user)
    datasets_count = db.one("SELECT COUNT(*) as cnt FROM datasets WHERE workspace_id=?", (workspace_id,))["cnt"]
    projects_count = db.one("SELECT COUNT(*) as cnt FROM projects WHERE workspace_id=?", (workspace_id,))["cnt"]
    members_count = db.one("SELECT COUNT(*) as cnt FROM workspace_members WHERE workspace_id=?", (workspace_id,))["cnt"]

    return {
        "workspace": ws,
        "stats": {
            "datasets": datasets_count,
            "projects": projects_count,
            "members": max(members_count, 1),
        },
    }


@router.patch("/{workspace_id}")
def update_workspace(workspace_id: str, b: UpdateWorkspaceBody, user: dict = Depends(require_user)):
    """Renames or updates configuration of an authorized workspace."""
    verify_workspace_access(workspace_id, user)

    if b.industry_pack and b.industry_pack not in PACKS:
        raise HTTPException(400, "Unknown industry pack.")
    if b.currency is not None and not (1 <= len(b.currency.strip()) <= 4):
        raise HTTPException(400, "Currency must be 1-4 characters.")

    now = db.now()
    if b.name:
        db.execute("UPDATE workspaces SET name=?, updated_at=? WHERE id=?", (b.name.strip(), now, workspace_id))
    if b.currency:
        db.execute("UPDATE workspaces SET currency=?, updated_at=? WHERE id=?", (b.currency.strip(), now, workspace_id))
    if b.industry_pack:
        db.execute("UPDATE workspaces SET industry_pack=?, updated_at=? WHERE id=?", (b.industry_pack, now, workspace_id))

    db.audit(workspace_id, user["id"], "workspace.update", b.model_dump_json())
    return {"workspace": db.one("SELECT * FROM workspaces WHERE id=?", (workspace_id,))}


@router.post("/{workspace_id}/switch")
def switch_workspace(workspace_id: str, user: dict = Depends(require_user)):
    """Switches the caller's active workspace and issues a new session token."""
    ws = verify_workspace_access(workspace_id, user)
    db.execute("UPDATE users SET workspace_id=?, updated_at=? WHERE id=?", (workspace_id, db.now(), user["id"]))

    updated_user = db.one("SELECT * FROM users WHERE id=?", (user["id"],))
    new_token = create_token(updated_user)
    db.audit(workspace_id, user["id"], "workspace.switch", ws["name"])

    return {
        "token": new_token,
        "user": public_user(updated_user),
        "workspace": ws,
    }


@router.delete("/{workspace_id}")
def delete_workspace(workspace_id: str, user: dict = Depends(require_user)):
    """Safely deletes a workspace if caller is owner and has another workspace."""
    verify_workspace_access(workspace_id, user)

    # Check that caller has at least one other workspace
    other = db.one(
        "SELECT id FROM workspaces WHERE id != ? AND (created_by = ? OR id IN "
        "(SELECT workspace_id FROM workspace_members WHERE user_id = ?))",
        (workspace_id, user["id"], user["id"]),
    )
    if not other:
        raise HTTPException(400, "Cannot delete your only workspace. Create another one first.")

    # Cleanup associated records
    db.execute("DELETE FROM messages WHERE chat_id IN (SELECT id FROM chats WHERE workspace_id=?)", (workspace_id,))
    db.execute("DELETE FROM chats WHERE workspace_id=?", (workspace_id,))
    db.execute("DELETE FROM decisions WHERE workspace_id=?", (workspace_id,))
    db.execute("DELETE FROM projects WHERE workspace_id=?", (workspace_id,))
    db.execute("DELETE FROM datasets WHERE workspace_id=?", (workspace_id,))
    db.execute("DELETE FROM workspace_members WHERE workspace_id=?", (workspace_id,))
    db.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))

    # If deleted workspace was active, switch to other
    if user["workspace_id"] == workspace_id:
        db.execute("UPDATE users SET workspace_id=? WHERE id=?", (other["id"], user["id"]))

    db.audit(other["id"], user["id"], "workspace.delete", workspace_id)
    return {"ok": True, "active_workspace_id": other["id"]}
