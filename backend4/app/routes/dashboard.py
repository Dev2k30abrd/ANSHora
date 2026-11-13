from fastapi import APIRouter, HTTPException

from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.services.auto_dashboard import generate_auto_dashboard


router = APIRouter(prefix="/api/dashboard", tags=["Auto Dashboard"])


@router.get("/{dataset_id}/auto")
def auto_dashboard(dataset_id: str, refresh: bool = False):
    try:
        if not refresh:
            cached = dataset_store.get_cache(dataset_id, "auto_dashboard")
            if cached is not None:
                return cached

        df = dataset_store.get(dataset_id)
        result = generate_auto_dashboard(df)
        dataset_store.set_cache(dataset_id, "auto_dashboard", result)
        return result

    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=400, detail=str(error))
