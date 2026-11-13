from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import db
from app.core.security import require_user
from app.packs import PACKS

router = APIRouter(prefix="/api/projects", tags=["Projects"])


class ProjectBody(BaseModel):
    name: str
    instructions: str = ""
    industry_pack: str | None = None
    currency: str | None = None


def _own(pid, user):
    p = db.one("SELECT * FROM projects WHERE id=? AND workspace_id=?", (pid, user["workspace_id"]))
    if not p:
        raise HTTPException(404, "Project not found.")
    return p


def _check(b):
    if b.industry_pack and b.industry_pack not in PACKS:
        raise HTTPException(400, "Unknown industry pack.")
    if not b.name.strip():
        raise HTTPException(400, "Name is required.")


@router.get("")
def list_projects(user: dict = Depends(require_user)):
    return {"projects": db.query("SELECT * FROM projects WHERE workspace_id=? ORDER BY created_at DESC", (user["workspace_id"],))}


@router.get("/{pid}")
def get_project(pid: str, user: dict = Depends(require_user)):
    return {"project": _own(pid, user)}


@router.post("")
def create(b: ProjectBody, user: dict = Depends(require_user)):
    _check(b)
    pid = db.new_id()
    db.execute("INSERT INTO projects(id,workspace_id,name,instructions,industry_pack,currency,created_at) VALUES(?,?,?,?,?,?,?)",
               (pid, user["workspace_id"], b.name.strip(), b.instructions[:4000], b.industry_pack, b.currency, db.now()))
    return {"project": db.one("SELECT * FROM projects WHERE id=?", (pid,))}


@router.put("/{pid}")
def update(pid: str, b: ProjectBody, user: dict = Depends(require_user)):
    _own(pid, user)
    _check(b)
    db.execute("UPDATE projects SET name=?, instructions=?, industry_pack=?, currency=? WHERE id=?",
               (b.name.strip(), b.instructions[:4000], b.industry_pack, b.currency, pid))
    return {"project": db.one("SELECT * FROM projects WHERE id=?", (pid,))}


@router.delete("/{pid}")
def delete(pid: str, user: dict = Depends(require_user)):
    _own(pid, user)
    db.execute("UPDATE datasets SET project_id=NULL WHERE project_id=?", (pid,))
    db.execute("DELETE FROM projects WHERE id=?", (pid,))
    return {"ok": True}
