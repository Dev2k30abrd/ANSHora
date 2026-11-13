from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.profit_service import run_profit, run_sensitivity
from app.core.jsonutil import jsonable
from app.services.dataset_manager import DatasetNotFoundError, dataset_store

router = APIRouter(prefix="/api/profit", tags=["Profit Impact"])


@router.get("/{dataset_id}")
def profit_impact(dataset_id: str):
    try:
        return jsonable(run_profit(dataset_id))
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))


class SensBody(BaseModel):
    price_changes: list[float] | None = None
    volume_changes: list[float] | None = None
    cost_change_pct: float = 0
    elasticity: float | None = None
    variable_cost_share: float = 1.0


@router.post("/{dataset_id}/sensitivity")
def sensitivity(dataset_id: str, b: SensBody):
    try:
        return jsonable(run_sensitivity(dataset_id, price_changes=b.price_changes, volume_changes=b.volume_changes,
                                        cost_change_pct=b.cost_change_pct, elasticity=b.elasticity,
                                        variable_cost_share=b.variable_cost_share))
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
