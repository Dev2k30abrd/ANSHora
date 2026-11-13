from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.services import alerts as alerts_service


router = APIRouter(prefix="/api/alerts", tags=["Smart Alerts"])


class CreateRuleRequest(BaseModel):
    column: str
    operator: str
    threshold: float
    aggregation: str = "mean"
    label: Optional[str] = None
    channels: Optional[list[str]] = None


@router.get("/{dataset_id}/rules")
def list_rules(dataset_id: str):
    try:
        return {"rules": dataset_store.get_alert_rules(dataset_id)}
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/{dataset_id}/rules")
def create_rule(dataset_id: str, request: CreateRuleRequest):
    try:
        df = dataset_store.get(dataset_id)
        if request.column not in df.columns:
            raise HTTPException(status_code=400, detail=f"Column '{request.column}' not found in dataset.")

        rule = alerts_service.create_rule(
            column=request.column,
            operator=request.operator,
            threshold=request.threshold,
            aggregation=request.aggregation,
            label=request.label,
            channels=request.channels,
        )

        rules = dataset_store.get_alert_rules(dataset_id)
        rules.append(rule)
        dataset_store.set_alert_rules(dataset_id, rules)

        return rule

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.delete("/{dataset_id}/rules/{rule_id}")
def delete_rule(dataset_id: str, rule_id: str):
    try:
        rules = dataset_store.get_alert_rules(dataset_id)
        rules = [r for r in rules if r["id"] != rule_id]
        dataset_store.set_alert_rules(dataset_id, rules)
        return {"message": "Rule deleted", "rules": rules}
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))


@router.post("/{dataset_id}/evaluate")
def evaluate_alerts(dataset_id: str):
    try:
        df = dataset_store.get(dataset_id)
        rules = dataset_store.get_alert_rules(dataset_id)

        triggered = alerts_service.evaluate_all(df, rules)
        if triggered:
            dataset_store.append_alert_history(dataset_id, triggered)

        return {
            "triggered_count": len(triggered),
            "triggered": triggered,
        }

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/{dataset_id}/history")
def alert_history(dataset_id: str):
    try:
        return {"history": dataset_store.get_alert_history(dataset_id)}
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
