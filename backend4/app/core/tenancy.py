"""
Multi-Tenant Access Control & Reusable Authorization Guards.
Enforces strict workspace scoping and resource ownership, preventing IDOR vulnerabilities.
"""
from fastapi import Depends, HTTPException

from app.core import db
from app.core.security import require_user


def get_current_workspace_id(user: dict = Depends(require_user)) -> str:
    ws_id = user.get("workspace_id")
    if not ws_id:
        raise HTTPException(status_code=403, detail="User is not assigned to a workspace.")
    return ws_id


def verify_workspace_access(workspace_id: str, user: dict = Depends(require_user)) -> dict:
    """Verifies that the caller has access to the specified workspace."""
    if user.get("workspace_id") == workspace_id:
        ws = db.one("SELECT * FROM workspaces WHERE id=?", (workspace_id,))
        if ws:
            return ws

    ws = db.one("SELECT * FROM workspaces WHERE id=?", (workspace_id,))
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found.")

    if ws.get("created_by") == user["id"]:
        return ws

    # Check workspace_members
    mem = db.one(
        "SELECT * FROM workspace_members WHERE workspace_id=? AND user_id=?",
        (workspace_id, user["id"]),
    )
    if not mem:
        raise HTTPException(status_code=403, detail="Access denied to this workspace.")

    return ws


def verify_dataset_access(dataset_id: str, user: dict = Depends(require_user)) -> dict:
    """Verifies that dataset belongs to the caller's authorized workspace."""
    ds = db.one(
        "SELECT * FROM datasets WHERE id=? AND workspace_id=?",
        (dataset_id, user["workspace_id"]),
    )
    if not ds:
        raise HTTPException(
            status_code=404,
            detail="Dataset not found or access denied.",
        )
    return ds


def verify_chat_access(chat_id: str, user: dict = Depends(require_user)) -> dict:
    """Verifies that chat belongs to the caller's authorized workspace and user."""
    chat = db.one(
        "SELECT * FROM chats WHERE id=? AND workspace_id=?",
        (chat_id, user["workspace_id"]),
    )
    if not chat:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found or access denied.",
        )
    return chat


def verify_project_access(project_id: str, user: dict = Depends(require_user)) -> dict:
    """Verifies that project belongs to the caller's authorized workspace."""
    proj = db.one(
        "SELECT * FROM projects WHERE id=? AND workspace_id=?",
        (project_id, user["workspace_id"]),
    )
    if not proj:
        raise HTTPException(
            status_code=404,
            detail="Project not found or access denied.",
        )
    return proj


def verify_decision_access(decision_id: str, user: dict = Depends(require_user)) -> dict:
    """Verifies that decision belongs to the caller's authorized workspace."""
    dec = db.one(
        "SELECT * FROM decisions WHERE id=? AND workspace_id=?",
        (decision_id, user["workspace_id"]),
    )
    if not dec:
        raise HTTPException(
            status_code=404,
            detail="Decision not found or access denied.",
        )
    return dec
