from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import db
from app.core.security import require_user
from app.services import monitors as svc
from app.services.dataset_manager import DatasetNotFoundError, dataset_store

router = APIRouter(prefix="/api/monitors", tags=["Monitors"])


class MonitorBody(BaseModel):
    dataset_id: str
    name: str
    kind: str = "profit_scan"
    config: dict = {}
    interval_minutes: int = 60
    channels: list[str] = ["in_app"]
    enabled: bool = True


def _own(mid, user):
    m = db.one("SELECT * FROM monitors WHERE id=? AND workspace_id=?", (mid, user["workspace_id"]))
    if not m:
        raise HTTPException(404, "Monitor not found.")
    return m


def _out(m):
    m = dict(m)
    m["config"] = {k: v for k, v in (db.loads(m["config"], {}) or {}).items() if not k.startswith("_")}
    m["channels"] = [c.split(":")[0] + (":…" if ":" in c else "") for c in db.loads(m["channels"], [])]
    return m


@router.get("")
def list_monitors(dataset_id: str | None = None, user: dict = Depends(require_user)):
    sql, args = "SELECT * FROM monitors WHERE workspace_id=?", [user["workspace_id"]]
    if dataset_id:
        sql, args = sql + " AND dataset_id=?", args + [dataset_id]
    return {"monitors": [_out(m) for m in db.query(sql + " ORDER BY created_at DESC", tuple(args))]}


@router.post("")
def create(b: MonitorBody, user: dict = Depends(require_user)):
    if b.kind not in svc.KINDS:
        raise HTTPException(400, f"kind must be one of {svc.KINDS}")
    if b.kind == "threshold" and not {"column", "operator", "threshold"} <= set(b.config):
        raise HTTPException(400, "threshold monitors need config: column, operator, threshold.")
    if not (1 <= b.interval_minutes <= 10080):
        raise HTTPException(400, "interval_minutes must be between 1 and 10080.")
    try:
        dataset_store.get(b.dataset_id)
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))
    for c in b.channels:
        if c != "in_app" and c.split(":")[0] not in ("slack", "teams", "webhook", "email"):
            raise HTTPException(400, f"Unknown channel '{c}'. Use in_app, slack:<url>, teams:<url>, webhook:<url>, email:<addr>.")
    mid = db.new_id()
    db.execute("INSERT INTO monitors(id,workspace_id,dataset_id,name,kind,config,interval_minutes,channels,enabled,created_at)"
               " VALUES(?,?,?,?,?,?,?,?,?,?)",
               (mid, user["workspace_id"], b.dataset_id, b.name.strip(), b.kind, db.dumps(b.config), b.interval_minutes,
                db.dumps(b.channels), 1 if b.enabled else 0, db.now()))
    db.audit(user["workspace_id"], user["id"], "monitor.create", b.name)
    return {"monitor": _out(db.one("SELECT * FROM monitors WHERE id=?", (mid,)))}


@router.patch("/{mid}/toggle")
def toggle(mid: str, user: dict = Depends(require_user)):
    m = _own(mid, user)
    db.execute("UPDATE monitors SET enabled=? WHERE id=?", (0 if m["enabled"] else 1, mid))
    return {"monitor": _out(db.one("SELECT * FROM monitors WHERE id=?", (mid,)))}


@router.post("/{mid}/run")
def run_now(mid: str, user: dict = Depends(require_user)):
    _own(mid, user)
    out = svc.run_monitor(mid, force=True)
    return {"result": {k: v for k, v in out.items() if k != "signature"}, "monitor": _out(db.one("SELECT * FROM monitors WHERE id=?", (mid,)))}


@router.delete("/{mid}")
def delete(mid: str, user: dict = Depends(require_user)):
    _own(mid, user)
    db.execute("DELETE FROM monitors WHERE id=?", (mid,))
    return {"ok": True}


@router.get("/notifications/list")
def notifications(unread_only: bool = False, user: dict = Depends(require_user)):
    sql = "SELECT * FROM notifications WHERE workspace_id=?" + (" AND read=0" if unread_only else "")
    rows = db.query(sql + " ORDER BY created_at DESC LIMIT 100", (user["workspace_id"],))
    unread = db.one("SELECT COUNT(*) c FROM notifications WHERE workspace_id=? AND read=0", (user["workspace_id"],))["c"]
    return {"notifications": rows, "unread": unread}


@router.post("/notifications/read-all")
def read_all(user: dict = Depends(require_user)):
    db.execute("UPDATE notifications SET read=1 WHERE workspace_id=?", (user["workspace_id"],))
    return {"ok": True}


@router.post("/notifications/{nid}/read")
def read_one(nid: str, user: dict = Depends(require_user)):
    db.execute("UPDATE notifications SET read=1 WHERE id=? AND workspace_id=?", (nid, user["workspace_id"]))
    return {"ok": True}
