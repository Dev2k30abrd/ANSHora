from pathlib import Path

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.analytics_agent import AIServiceError, generate_auto_insights
from app.core import config as cfg
from app.core import db
from app.core.security import require_user
from app.packs import PACKS
from app.packs.detect import suggest_pack
from app.services.connectors import fetch_url_dataframe, sql_dataframe
from app.services.dataset_manager import DatasetNotFoundError, dataset_store
from app.services.dataset_service import SUPPORTED_EXTENSIONS, get_dataset_summary, load_dataset, save_uploaded_file

router = APIRouter(prefix="/api/dataset", tags=["Dataset"])
SAMPLES = Path(__file__).resolve().parents[2] / "test_data"


def _register(df, filename, user, project_id=None, pack_id=None, source="upload"):
    if df.empty:
        raise HTTPException(400, "The dataset has no rows.")
    df.columns = [str(c).strip() for c in df.columns]
    sug = suggest_pack(df)
    if pack_id and pack_id not in PACKS:
        raise HTTPException(400, "Unknown industry pack.")
    if not pack_id and project_id:
        p = db.one("SELECT industry_pack FROM projects WHERE id=? AND workspace_id=?", (project_id, user["workspace_id"]))
        pack_id = (p or {}).get("industry_pack")
    pack_id = pack_id or sug["pack_id"]
    ds = dataset_store.create(df, filename, project_id=project_id, pack_id=pack_id, source=source)
    db.audit(user["workspace_id"], user["id"], "dataset.create", f"{filename} ({len(df)} rows)")
    summary = get_dataset_summary(df)
    summary["duplicates_excluded"] = dataset_store.duplicates_excluded(ds)
    return {"message": "Dataset ready", "dataset_id": ds, "filename": filename, "pack_id": pack_id,
            "suggested_pack": sug["pack_id"], "summary": summary}


@router.post("/upload")
async def upload(file: UploadFile = File(...), project_id: str | None = Form(None), pack_id: str | None = Form(None),
                 user: dict = Depends(require_user)):
    if not any(file.filename.lower().endswith(e) for e in SUPPORTED_EXTENSIONS):
        raise HTTPException(400, f"Unsupported file type. Supported: {', '.join(SUPPORTED_EXTENSIONS)}")
    path = None
    try:
        path = save_uploaded_file(file)
        df = load_dataset(path)
        return _register(df, file.filename, user, project_id, pack_id)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Could not read the file: {e}")
    finally:
        if path:
            Path(path).unlink(missing_ok=True)


class UrlBody(BaseModel):
    url: str
    project_id: str | None = None
    pack_id: str | None = None


@router.post("/import-url")
def import_url(b: UrlBody, user: dict = Depends(require_user)):
    try:
        df = fetch_url_dataframe(b.url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Could not fetch that URL: {str(e)[:150]}")
    name = b.url.split("?")[0].rstrip("/").split("/")[-1] or "remote-data"
    out = _register(df, name, user, b.project_id, b.pack_id, source=f"url:{b.url}")
    return out


class SqlBody(BaseModel):
    connection_url: str
    query: str
    name: str = "sql-import"
    project_id: str | None = None
    pack_id: str | None = None


@router.post("/import-sql")
def import_sql(b: SqlBody, user: dict = Depends(require_user)):
    try:
        df = sql_dataframe(b.connection_url, b.query)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except ImportError as e:
        raise HTTPException(400, f"Database driver missing: {e}. Install it (e.g. pip install psycopg2-binary).")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Database query failed: {str(e)[:200]}")
    return _register(df, b.name, user, b.project_id, b.pack_id, source="sql")


@router.get("/samples")
def samples():
    return {"samples": [{"name": f.name, "size_kb": round(f.stat().st_size / 1024, 1)}
                        for f in sorted(SAMPLES.glob("*.csv"))]} if SAMPLES.exists() else {"samples": []}


@router.post("/sample/{name}")
def load_sample(name: str, user: dict = Depends(require_user)):
    f = SAMPLES / Path(name).name
    if not f.exists() or f.suffix != ".csv":
        raise HTTPException(404, "Sample not found.")
    return _register(pd.read_csv(f), f.name, user)


@router.get("/")
def list_datasets(user: dict = Depends(require_user)):
    return {"datasets": dataset_store.list_for_workspace()}


class PackBody(BaseModel):
    pack_id: str


@router.patch("/{dataset_id}/pack")
def set_pack(dataset_id: str, b: PackBody):
    if b.pack_id not in PACKS:
        raise HTTPException(400, "Unknown industry pack.")
    try:
        dataset_store.set_pack_id(dataset_id, b.pack_id)
        dataset_store.clear_cache(dataset_id)
        return {"pack_id": b.pack_id}
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))


class SettingsBody(BaseModel):
    exclude_duplicates: bool


@router.patch("/{dataset_id}/settings")
def dataset_settings(dataset_id: str, b: SettingsBody):
    try:
        dataset_store.set_settings(dataset_id, exclude_duplicates=b.exclude_duplicates)
        return {"settings": dataset_store.get_settings(dataset_id),
                "duplicates_excluded": dataset_store.duplicates_excluded(dataset_id)}
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: str, user: dict = Depends(require_user)):
    try:
        dataset_store.delete(dataset_id)
        db.audit(user["workspace_id"], user["id"], "dataset.delete", dataset_id)
        return {"message": "Deleted"}
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))


@router.get("/{dataset_id}/insights")
def dataset_insights(dataset_id: str):
    try:
        return generate_auto_insights(dataset_id)
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, str(e))


@router.get("/{dataset_id}/summary")
def dataset_summary(dataset_id: str):
    try:
        meta = dataset_store.get_meta(dataset_id)
        return {**get_dataset_summary(dataset_store.get_raw(dataset_id)), "pack_id": meta["pack_id"],
                "filename": meta["filename"], "duplicates_excluded": meta["duplicates_excluded"],
                "settings": dataset_store.get_settings(dataset_id)}
    except DatasetNotFoundError as e:
        raise HTTPException(404, str(e))
