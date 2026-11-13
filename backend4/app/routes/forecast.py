from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.services.forecasting import forecast_series
from app.services.evidence import build_evidence


router = APIRouter(prefix="/api/forecast", tags=["Forecasting"])


class ForecastRequest(BaseModel):
    dataset_id: str
    date_column: str
    value_column: str
    periods: int = 6
    freq: str = "M"
    exploratory: bool = False


@router.post("/analyze")
def forecast_analyze(request: ForecastRequest):
    try:
        df = dataset_store.get(request.dataset_id)
        filename = dataset_store.get_filename(request.dataset_id)

        result = forecast_series(
            df,
            date_column=request.date_column,
            value_column=request.value_column,
            periods=request.periods,
            freq=request.freq,
            exploratory=request.exploratory,
        )

        result["evidence"] = build_evidence(
            "forecast_analysis",
            {
                "date_column": request.date_column,
                "value_column": request.value_column,
                "periods": request.periods,
                "freq": result.get("frequency", request.freq),
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
