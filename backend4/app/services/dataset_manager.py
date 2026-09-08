import threading
import uuid
from datetime import datetime, timezone

import pandas as pd


class DatasetNotFoundError(Exception):
    """Raised when a dataset_id doesn't exist (expired, wrong id, restart)."""


class DatasetStore:
    """
    In-memory store for uploaded datasets, keyed by dataset_id.
    Each chat/session on the frontend holds its own dataset_id,
    so multiple datasets can be active at once without clobbering
    each other (fixes the old single-global-dataset bug).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._datasets: dict[str, dict] = {}

    def create(self, df: pd.DataFrame, filename: str) -> str:
        dataset_id = uuid.uuid4().hex

        with self._lock:
            self._datasets[dataset_id] = {
                "id": dataset_id,
                "df": df,
                "filename": filename,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "insights_cache": None,
            }

        return dataset_id

    def get(self, dataset_id: str) -> pd.DataFrame:
        entry = self._get_entry(dataset_id)
        return entry["df"]

    def get_filename(self, dataset_id: str) -> str:
        return self._get_entry(dataset_id)["filename"]

    def get_cached_insights(self, dataset_id: str):
        return self._get_entry(dataset_id).get("insights_cache")

    def set_cached_insights(self, dataset_id: str, insights: dict):
        with self._lock:
            if dataset_id in self._datasets:
                self._datasets[dataset_id]["insights_cache"] = insights

    def replace(self, dataset_id: str, df: pd.DataFrame):
        """Used after a cleaning operation mutates the dataframe."""
        with self._lock:
            entry = self._datasets.get(dataset_id)
            if entry is None:
                raise DatasetNotFoundError(f"Dataset '{dataset_id}' was not found.")
            entry["df"] = df
            entry["insights_cache"] = None

    def exists(self, dataset_id: str) -> bool:
        return dataset_id in self._datasets

    def delete(self, dataset_id: str):
        with self._lock:
            self._datasets.pop(dataset_id, None)

    def _get_entry(self, dataset_id: str) -> dict:
        entry = self._datasets.get(dataset_id)

        if entry is None:
            raise DatasetNotFoundError(
                "Dataset not found. It may have expired or the "
                "server restarted — please re-upload."
            )

        return entry


dataset_store = DatasetStore()
