"""
Business Memory Engine for Anshora.
Provides persistent organizational memory across decisions, outcomes, insights, and lessons learned.
Strictly isolated per workspace to prevent cross-tenant information leakage.
"""
import json
import logging
from typing import Any

from app.core import db
from app.core.jsonutil import jsonable

logger = logging.getLogger("anshora.business_memory")


def record_memory(
    workspace_id: str,
    category: str,
    key: str,
    summary: str,
    evidence_ref: Any = None,
) -> str:
    """Records or updates a business memory entry scoped strictly to workspace_id."""
    existing = db.one(
        "SELECT id FROM business_memory WHERE workspace_id=? AND category=? AND key=?",
        (workspace_id, category, key),
    )
    now = db.now()
    ev_str = db.dumps(jsonable(evidence_ref)) if evidence_ref is not None else None

    if existing:
        mid = existing["id"]
        db.execute(
            "UPDATE business_memory SET summary=?, evidence_ref=?, created_at=? WHERE id=?",
            (summary, ev_str, now, mid),
        )
        return mid

    mid = db.new_id()
    db.execute(
        "INSERT INTO business_memory(id,workspace_id,category,key,summary,evidence_ref,created_at) "
        "VALUES(?,?,?,?,?,?,?)",
        (mid, workspace_id, category, key, summary, ev_str, now),
    )
    return mid


def search_memory(workspace_id: str, query_term: str) -> list[dict]:
    """Searches workspace business memory for relevant entries."""
    term = f"%{query_term.strip()}%"
    rows = db.query(
        "SELECT * FROM business_memory WHERE workspace_id=? "
        "AND (key LIKE ? OR summary LIKE ? OR category LIKE ?) "
        "ORDER BY created_at DESC LIMIT 20",
        (workspace_id, term, term, term),
    )
    for r in rows:
        r["evidence_ref"] = db.loads(r.get("evidence_ref"))
    return rows


def get_workspace_memories(workspace_id: str, limit: int = 50) -> list[dict]:
    """Retrieves all memory items for the workspace."""
    rows = db.query(
        "SELECT * FROM business_memory WHERE workspace_id=? ORDER BY created_at DESC LIMIT ?",
        (workspace_id, limit),
    )
    for r in rows:
        r["evidence_ref"] = db.loads(r.get("evidence_ref"))
    return rows


def sync_decision_to_memory(decision: dict, outcome: dict | None = None) -> str:
    """Automatically records or updates business memory from logged decisions & outcomes."""
    ws_id = decision["workspace_id"]
    title = decision["title"]
    status = decision.get("status", "Proposed")
    impact = decision.get("expected_impact")
    action = decision.get("action", "")

    summary_parts = [f"Decision: {title} (Status: {status})."]
    if action:
        summary_parts.append(f"Action: {action}")
    if impact:
        summary_parts.append(f"Expected Impact: ₹{impact:,.2f}" if isinstance(impact, (int, float)) else f"Expected Impact: {impact}")

    if outcome:
        act = outcome.get("actual_outcome", "")
        m_imp = outcome.get("measured_impact")
        summary_parts.append(f"Outcome: {act}")
        if m_imp:
            summary_parts.append(f"Measured Impact: ₹{m_imp:,.2f}" if isinstance(m_imp, (int, float)) else f"Measured Impact: {m_imp}")

    evidence = {
        "decision_id": decision["id"],
        "dataset_id": decision.get("dataset_id"),
        "metric_column": decision.get("metric_column"),
        "owner": decision.get("owner"),
    }

    return record_memory(
        workspace_id=ws_id,
        category="decision",
        key=f"decision_{decision['id']}",
        summary=" ".join(summary_parts),
        evidence_ref=evidence,
    )
