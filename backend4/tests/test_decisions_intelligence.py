"""
Tests for Decision Intelligence, status workflows, finding conversions,
and outcome tracking.
"""
import pytest
from app.core import db
from app.core.context import workspace_scope


@pytest.fixture
def scope(client, dataset):
    ws = db.one("SELECT workspace_id FROM datasets WHERE id=?", (dataset,))["workspace_id"]
    with workspace_scope(ws):
        yield dataset, ws


def test_decision_full_lifecycle(client, auth, scope):
    dataset_id, ws_id = scope

    # 1. Create a structured decision record
    payload = {
        "dataset_id": dataset_id,
        "title": "Reduce high discount on Consumer segment",
        "problem": "Consumer segment has 22% average discount causing margin leakage",
        "action": "Cap maximum discount at 12% across Consumer accounts",
        "assumptions": "Order volume will remain stable within +-3%",
        "risks": "Risk of minor churn on price-sensitive accounts",
        "confidence": "high",
        "justification": "Sensitivity analysis indicates net profit gain of ₹45,000",
        "priority": "high",
        "owner": "Finance Team",
        "expected_impact": 45000.0,
        "review_date": "2026-12-01",
        "status": "Proposed",
    }
    r = client.post("/api/decisions", json=payload, headers=auth)
    assert r.status_code == 200
    dec = r.json()["decision"]
    did = dec["id"]
    assert dec["status"] == "Proposed"
    assert dec["priority"] == "high"
    assert dec["problem"] == payload["problem"]
    assert dec["expected_impact"] == 45000.0

    # 2. Update status to Approved then In progress
    r = client.patch(f"/api/decisions/{did}", json={"status": "Approved"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["decision"]["status"] == "Approved"

    r = client.patch(f"/api/decisions/{did}", json={"status": "In progress"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["decision"]["status"] == "In progress"

    # 3. Record actual outcome and measured impact
    outcome_payload = {
        "actual_outcome": "Discount capped successfully; margin improved by 3.2% with zero customer churn.",
        "measured_impact": 48200.0,
        "followed_recommendation": True,
        "status": "Completed",
    }
    r = client.post(f"/api/decisions/{did}/outcome", json=outcome_payload, headers=auth)
    assert r.status_code == 200
    updated = r.json()["decision"]
    assert updated["status"] == "Completed"
    assert updated["actual_outcome"] == outcome_payload["actual_outcome"]
    assert updated["measured_impact"] == 48200.0
    assert updated["followed_recommendation"] == 1

    # 4. Check summary endpoint aggregates
    r = client.get("/api/decisions/summary", headers=auth)
    assert r.status_code == 200
    summ = r.json()
    assert summ["total"] >= 1
    assert summ["evaluated"] >= 1
    assert summ["realized_total"] >= 48200.0
    assert summ["by_status"]["completed"] >= 1


def test_convert_analytical_finding_to_decision(client, auth, scope):
    dataset_id, ws_id = scope
    finding = {
        "id": "f_1",
        "title": "Severe discount leakage in West region",
        "detail": "Discounts in West exceeded 28% of net sales",
        "how": "Eliminate unapproved discretionary sales manager discounts",
        "impact_amount": 75000.0,
        "confidence": "high",
    }
    r = client.post("/api/decisions/from-finding", json={"dataset_id": dataset_id, "finding": finding}, headers=auth)
    assert r.status_code == 200
    dec = r.json()["decision"]
    assert dec["title"] == finding["title"]
    assert dec["expected_impact"] == 75000.0
    assert dec["status"] == "Proposed"
    assert dec["confidence"] == "high"
