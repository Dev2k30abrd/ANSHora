from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.services.what_if import simulate_scenario
from app.services.evidence import build_evidence


router = APIRouter(prefix="/api/whatif", tags=["What-If Analysis"])


class WhatIfRequest(BaseModel):
    dataset_id: str
    metric_column: str
    adjustment_type: str = "percentage"
    adjustment_value: float
    aggregation: str = "sum"
    filter_column: Optional[str] = None
    filter_value: Optional[str] = None


@router.post("/simulate")
def whatif_simulate(request: WhatIfRequest):
    try:
        df = dataset_store.get(request.dataset_id)
        filename = dataset_store.get_filename(request.dataset_id)

        result = simulate_scenario(
            df,
            metric_column=request.metric_column,
            adjustment_type=request.adjustment_type,
            adjustment_value=request.adjustment_value,
            aggregation=request.aggregation,
            filter_column=request.filter_column,
            filter_value=request.filter_value,
        )

        result["evidence"] = build_evidence(
            "what_if_analysis",
            {"metric_column": request.metric_column, "filter_column": request.filter_column},
            df,
            request.dataset_id,
            filename,
        )

        return result

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))
