from fastapi import APIRouter, HTTPException

from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.services.proactive_insights import scan_for_insights
from app.services.data_health import compute_data_health


router = APIRouter(tags=["Insights & Data Health"])


@router.get("/api/insights/{dataset_id}/proactive")
def proactive_insights(dataset_id: str, refresh: bool = False):
    try:
        if not refresh:
            cached = dataset_store.get_cache(dataset_id, "proactive_insights_scan")
            if cached is not None:
                return cached

        df = dataset_store.get(dataset_id)
        result = scan_for_insights(df)
        dataset_store.set_cache(dataset_id, "proactive_insights_scan", result)
        return result

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))


@router.get("/api/data-health/{dataset_id}")
def data_health(dataset_id: str, refresh: bool = False):
    try:
        if not refresh:
            cached = dataset_store.get_cache(dataset_id, "data_health_score")
            if cached is not None:
                return cached

        df = dataset_store.get_raw(dataset_id)  # quality is judged on the data as uploaded
        result = compute_data_health(df)
        dataset_store.set_cache(dataset_id, "data_health_score", result)
        return result

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
