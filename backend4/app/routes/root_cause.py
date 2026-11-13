from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.services.root_cause import analyze_root_cause
from app.services.evidence import build_evidence


router = APIRouter(prefix="/api/root-cause", tags=["Root Cause Analysis"])


class RootCauseRequest(BaseModel):
    dataset_id: str
    metric_column: str
    date_column: str | None = None
    dimensions: list[str] | None = None


@router.post("/analyze")
def root_cause_analyze(request: RootCauseRequest):
    try:
        df = dataset_store.get(request.dataset_id)
        filename = dataset_store.get_filename(request.dataset_id)

        result = analyze_root_cause(
            df,
            metric_column=request.metric_column,
            date_column=request.date_column,
            dimensions=request.dimensions,
        )

        result["evidence"] = build_evidence(
            "root_cause_analysis",
            {
                "metric_column": request.metric_column,
                "date_column": request.date_column,
                "dimensions": result.get("dimensions_analyzed", []),
            },
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
