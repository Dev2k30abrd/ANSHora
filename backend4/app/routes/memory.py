"""
Business Memory API Router.
Enables querying, recording, and managing organizational business memory.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import db
from app.core.security import require_user
from app.services.business_memory import (
    get_workspace_memories,
    record_memory,
    search_memory,
)

router = APIRouter(prefix="/api/memory", tags=["Business Memory"])


class MemoryCreateBody(BaseModel):
    category: str = "general"
    key: str
    summary: str
    evidence_ref: dict | None = None


@router.get("")
def list_memories(user: dict = Depends(require_user)):
    """Lists recent business memory entries for caller's workspace."""
    return {"memories": get_workspace_memories(user["workspace_id"])}


@router.post("")
def add_memory(b: MemoryCreateBody, user: dict = Depends(require_user)):
    """Records a business memory entry."""
    if not b.key.strip() or not b.summary.strip():
        raise HTTPException(400, "Key and summary are required.")
    mid = record_memory(
        workspace_id=user["workspace_id"],
        category=b.category.strip(),
        key=b.key.strip(),
        summary=b.summary.strip(),
        evidence_ref=b.evidence_ref,
    )
    return {"id": mid, "message": "Memory recorded."}


@router.get("/search")
def query_memories(q: str, user: dict = Depends(require_user)):
    """Searches organizational memory."""
    if not q.strip():
        return {"memories": []}
    return {"memories": search_memory(user["workspace_id"], q.strip())}


@router.delete("/{memory_id}")
def delete_memory(memory_id: str, user: dict = Depends(require_user)):
    """Deletes a business memory entry."""
    m = db.one("SELECT id FROM business_memory WHERE id=? AND workspace_id=?", (memory_id, user["workspace_id"]))
    if not m:
        raise HTTPException(404, "Memory entry not found.")
    db.execute("DELETE FROM business_memory WHERE id=?", (memory_id,))
    return {"ok": True}
