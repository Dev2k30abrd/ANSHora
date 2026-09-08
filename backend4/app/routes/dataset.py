from fastapi import APIRouter, UploadFile, File, HTTPException

from app.services.dataset_service import (
    save_uploaded_file,
    load_dataset,
    get_dataset_summary,
    SUPPORTED_EXTENSIONS,
)
from app.services.dataset_manager import dataset_store, DatasetNotFoundError
from app.agents.analytics_agent import generate_auto_insights, AIServiceError


router = APIRouter(prefix="/api/dataset", tags=["Dataset"])


@router.post("/upload")
async def upload_dataset(file: UploadFile = File(...)):
    if not any(file.filename.lower().endswith(ext) for ext in SUPPORTED_EXTENSIONS):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Supported: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    try:
        file_path = save_uploaded_file(file)
        df = load_dataset(file_path)

        if df.empty:
            raise HTTPException(status_code=400, detail="The uploaded file has no rows.")

        dataset_id = dataset_store.create(df, file.filename)
        summary = get_dataset_summary(df)

        return {
            "message": "Dataset uploaded successfully",
            "dataset_id": dataset_id,
            "filename": file.filename,
            "summary": summary,
        }

    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/{dataset_id}/insights")
def dataset_insights(dataset_id: str):
    """Automatic 'first look' EDA briefing — no question needed."""

    try:
        return generate_auto_insights(dataset_id)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except AIServiceError as error:
        raise HTTPException(status_code=503, detail=str(error))
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error))


@router.get("/{dataset_id}/summary")
def dataset_summary(dataset_id: str):
    try:
        df = dataset_store.get(dataset_id)
        return get_dataset_summary(df)
    except DatasetNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error))
