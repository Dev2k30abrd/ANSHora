import json
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core import db
from app.core.security import require_user
from app.services.business_memory import sync_decision_to_memory
from app.services.dataset_manager import DatasetNotFoundError, dataset_store

router = APIRouter(prefix="/api/decisions", tags=["Decision Log"])

VALID_STATUSES = {
    "proposed": "Proposed",
    "approved": "Approved",
    "rejected": "Rejected",
    "in progress": "In progress",
    "in_progress": "In progress",
    "completed": "Completed",
    "done": "Completed",
    "open": "Proposed",
    "dropped": "Rejected",
}


def _norm_status(s: str) -> str:
    cleaned = (s or "").strip().lower()
    if cleaned in VALID_STATUSES:
        return VALID_STATUSES[cleaned]
    raise HTTPException(400, f"Invalid status '{s}'. Supported: Proposed, Approved, Rejected, In progress, Completed.")


class DecisionBody(BaseModel):
    dataset_id: str
    title: str
    action: str = ""
    problem: str = ""
    evidence: str | dict | None = None
    assumptions: str = ""
    risks: str = ""
    confidence: str = "medium"
    justification: str = ""
    priority: str = "medium"
    owner: str = ""
    metric_column: str | None = None
    aggregation: str = "sum"
    direction: str = "up"  # up = higher is better, down = lower is better
    expected_impact: float | None = None
    review_date: str | None = None
    status: str = "Proposed"


class StatusBody(BaseModel):
    status: str


class OutcomeBody(BaseModel):
    actual_outcome: str
    measured_impact: float | None = None
    followed_recommendation: bool | None = None
    status: str | None = None


def _metric(dataset_id, column, agg):
    if not column:
        return 0.0
    df = dataset_store.get(dataset_id)
    if column not in df.columns:
        raise HTTPException(400, f"Column '{column}' not found.")
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    if s.empty:
        raise HTTPException(400, f"Column '{column}' has no numeric values.")
    if agg not in ("sum", "mean", "min", "max", "median", "count"):
        raise HTTPException(400, "Invalid aggregation.")
    return float(getattr(s, agg)())


def _own(did, user):
    d = db.one("SELECT * FROM decisions WHERE id=? AND workspace_id=?", (did, user["workspace_id"]))
    if not d:
        raise HTTPException(404, "Decision not found.")
    return d


@router.get("")
def list_decisions(dataset_id: str | None = None, user: dict = Depends(require_user)):
    sql, args = "SELECT * FROM decisions WHERE workspace_id=?", [user["workspace_id"]]
    if dataset_id:
        sql, args = sql + " AND dataset_id=?", args + [dataset_id]
    return {"decisions": db.query(sql + " ORDER BY created_at DESC", tuple(args))}


@router.get("/summary")
def summary(user: dict = Depends(require_user)):
    rows = db.query("SELECT * FROM decisions WHERE workspace_id=?", (user["workspace_id"],))
    ev = [r for r in rows if r["realized_impact"] is not None or r.get("measured_impact") is not None]
    return {
        "total": len(rows),
        "evaluated": len(ev),
        "expected_total": sum(r["expected_impact"] or 0 for r in rows),
        "realized_total": sum((r.get("measured_impact") if r.get("measured_impact") is not None else r["realized_impact"]) or 0 for r in ev),
        "by_status": {
            "proposed": sum(1 for r in rows if _norm_status(r["status"]) == "Proposed"),
            "approved": sum(1 for r in rows if _norm_status(r["status"]) == "Approved"),
            "rejected": sum(1 for r in rows if _norm_status(r["status"]) == "Rejected"),
            "in_progress": sum(1 for r in rows if _norm_status(r["status"]) == "In progress"),
            "completed": sum(1 for r in rows if _norm_status(r["status"]) == "Completed"),
        },
    }


@router.post("")
def create(b: DecisionBody, user: dict = Depends(require_user)):
    base = 0.0
    if b.metric_column:
        try:
            base = _metric(b.dataset_id, b.metric_column, b.aggregation)
        except DatasetNotFoundError as e:
            raise HTTPException(404, str(e))
        except HTTPException:
            base = 0.0

    did = db.new_id()
    status = _norm_status(b.status)
    ev_str = json.dumps(b.evidence, default=str) if isinstance(b.evidence, (dict, list)) else (b.evidence or "")

    db.execute(
        "INSERT INTO decisions(id,workspace_id,dataset_id,title,action,owner,metric_column,aggregation,direction,"
        "baseline_value,expected_impact,status,created_at,problem,evidence,assumptions,risks,confidence,justification,"
        "priority,review_date) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            did, user["workspace_id"], b.dataset_id, b.title.strip(), b.action, b.owner, b.metric_column or "",
            b.aggregation, "down" if b.direction == "down" else "up", base, b.expected_impact, status, db.now(),
            b.problem, ev_str, b.assumptions, b.risks, b.confidence, b.justification, b.priority, b.review_date,
        ),
    )
    db.audit(user["workspace_id"], user["id"], "decision.create", b.title)
    d = db.one("SELECT * FROM decisions WHERE id=?", (did,))
    try:
        sync_decision_to_memory(d)
    except Exception:
        pass
    return {"decision": d}


@router.post("/from-finding")
def create_from_finding(body: dict, user: dict = Depends(require_user)):
    dataset_id = body.get("dataset_id")
    finding = body.get("finding", {})
    if not dataset_id or not finding:
        raise HTTPException(400, "dataset_id and finding payload required.")

    did = db.new_id()
    title = finding.get("title") or "New Business Decision"
    action = finding.get("how") or finding.get("detail") or ""
    problem = finding.get("detail") or ""
    impact = finding.get("impact_amount")
    confidence = finding.get("confidence") or "medium"
    ev_str = json.dumps(finding, default=str)

    db.execute(
        "INSERT INTO decisions(id,workspace_id,dataset_id,title,action,owner,metric_column,aggregation,direction,"
        "baseline_value,expected_impact,status,created_at,problem,evidence,confidence,priority) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            did, user["workspace_id"], dataset_id, title, action, user.get("name", "Analyst"), "",
            "sum", "up", 0.0, impact, "Proposed", db.now(), problem, ev_str, confidence, "high" if (impact or 0) > 100000 else "medium",
        ),
    )
    db.audit(user["workspace_id"], user["id"], "decision.convert_finding", title)
    d = db.one("SELECT * FROM decisions WHERE id=?", (did,))
    try:
        sync_decision_to_memory(d)
    except Exception:
        pass
    return {"decision": d}


@router.post("/{did}/evaluate")
def evaluate(did: str, user: dict = Depends(require_user)):
    d = _own(did, user)
    if not d.get("metric_column"):
        return {"decision": d}
    try:
        now_v = _metric(d["dataset_id"], d["metric_column"], d["aggregation"])
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))
    realized = (now_v - (d["baseline_value"] or 0.0)) * (-1 if d["direction"] == "down" else 1)
    db.execute(
        "UPDATE decisions SET latest_value=?, realized_impact=?, measured_impact=?, evaluated_at=? WHERE id=?",
        (now_v, realized, realized, db.now(), did),
    )
    return {"decision": db.one("SELECT * FROM decisions WHERE id=?", (did,))}


@router.post("/{did}/outcome")
@router.patch("/{did}/outcome")
def record_outcome(did: str, b: OutcomeBody, user: dict = Depends(require_user)):
    _own(did, user)
    updates = ["actual_outcome=?, evaluated_at=?"]
    params = [b.actual_outcome, db.now()]

    if b.measured_impact is not None:
        updates.append("measured_impact=?, realized_impact=?")
        params.extend([b.measured_impact, b.measured_impact])
    if b.followed_recommendation is not None:
        updates.append("followed_recommendation=?")
        params.append(1 if b.followed_recommendation else 0)
    if b.status:
        updates.append("status=?")
        params.append(_norm_status(b.status))

    params.append(did)
    sql = f"UPDATE decisions SET {', '.join(updates)} WHERE id=?"
    db.execute(sql, tuple(params))
    db.audit(user["workspace_id"], user["id"], "decision.record_outcome", did)

    try:
        oid = db.new_id()
        db.execute(
            "INSERT INTO decision_outcomes(id,decision_id,evaluated_by,actual_outcome,measured_impact,followed_recommendation,evaluated_at) "
            "VALUES(?,?,?,?,?,?,?)",
            (oid, did, user["id"], b.actual_outcome, b.measured_impact, 1 if b.followed_recommendation else 0, db.now()),
        )
        d = db.one("SELECT * FROM decisions WHERE id=?", (did,))
        sync_decision_to_memory(d, outcome=b.model_dump())
    except Exception:
        pass

    return {"decision": db.one("SELECT * FROM decisions WHERE id=?", (did,))}


@router.patch("/{did}")
def set_status(did: str, b: StatusBody, user: dict = Depends(require_user)):
    _own(did, user)
    norm = _norm_status(b.status)
    db.execute("UPDATE decisions SET status=? WHERE id=?", (norm, did))
    return {"decision": db.one("SELECT * FROM decisions WHERE id=?", (did,))}


@router.delete("/{did}")
def delete(did: str, user: dict = Depends(require_user)):
    _own(did, user)
    db.execute("DELETE FROM decisions WHERE id=?", (did,))
    return {"ok": True}
