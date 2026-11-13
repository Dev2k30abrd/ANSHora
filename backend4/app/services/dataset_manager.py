"""
Persistent, tenant-aware dataset store.

- DataFrames live in memory for speed AND on disk (parquet) so a server
  restart no longer wipes everything.
- Metadata / semantic layer / alert rules live in SQLite.
- Every read is checked against the caller's workspace (contextvar), so one
  company can never open another company's dataset id.
"""
import threading
from pathlib import Path

import pandas as pd

from app.core import db
from app.core.config import DATASET_DIR
from app.core.context import current_workspace


class DatasetNotFoundError(Exception):
    """Raised when a dataset_id doesn't exist or isn't visible to the caller."""


def _default_context() -> dict:
    return {"metrics": {}, "synonyms": {}, "rules": [], "notes": ""}


def _write_parquet(df: pd.DataFrame, path: Path):
    try:
        df.to_parquet(path, index=False)
    except Exception:
        safe = df.copy()
        for c in safe.columns:
            if safe[c].dtype == object:
                safe[c] = safe[c].astype(str)
        safe.columns = [str(c) for c in safe.columns]
        safe.to_parquet(path, index=False)


class DatasetStore:
    def __init__(self):
        self._lock = threading.RLock()
        self._mem: dict[str, dict] = {}

    # ------------------------------------------------------------ create
    def create(self, df, filename, workspace_id=None, project_id=None, pack_id=None, source="upload", user_id=None) -> str:
        dataset_id = db.new_id()
        ws = workspace_id or current_workspace.get()
        from app.core.context import current_user_id
        uid = user_id or current_user_id.get()
        path = DATASET_DIR / f"{dataset_id}.parquet"
        _write_parquet(df, path)
        ctx = _default_context()
        f_size = path.stat().st_size if path.exists() else 0
        db.execute(
            "INSERT INTO datasets(id,workspace_id,user_id,project_id,filename,path,file_size_bytes,mime_type,rows,cols,uploaded_at,pack_id,source,"
            "processing_status,business_context,alert_rules,alert_history) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (dataset_id, ws, uid, project_id, filename, str(path), f_size, "application/octet-stream",
             int(len(df)), int(df.shape[1]), db.now(), pack_id, source, "ready", db.dumps(ctx), "[]", "[]"),
        )
        with self._lock:
            self._mem[dataset_id] = self._entry(dataset_id, ws, df, filename, ctx, [], [], pack_id, project_id, user_id=uid)
        return dataset_id

    @staticmethod
    def _entry(dataset_id, ws, df, filename, ctx, rules, history, pack_id=None, project_id=None, uploaded_at=None,
               settings=None, user_id=None):
        return {
            "settings": settings or {"exclude_duplicates": True},
            "clean": None,
            "id": dataset_id,
            "workspace_id": ws,
            "user_id": user_id,
            "df": df,
            "filename": filename,
            "uploaded_at": uploaded_at or db.now(),
            "insights_cache": None,
            "cache": {},
            "business_context": ctx,
            "alert_rules": rules,
            "alert_history": history,
            "pack_id": pack_id,
            "project_id": project_id,
        }

    # -------------------------------------------------------------- read
    def get(self, dataset_id):
        """The ANALYSIS view: exact duplicate rows are excluded (unless the user opted out)."""
        e = self._get_entry(dataset_id)
        if not e["settings"].get("exclude_duplicates", True):
            return e["df"]
        if e["clean"] is None:
            e["clean"] = e["df"].drop_duplicates().reset_index(drop=True) if e["df"].duplicated().any() else e["df"]
        return e["clean"]

    def get_raw(self, dataset_id):
        """The dataset exactly as uploaded (used for data-quality reporting)."""
        return self._get_entry(dataset_id)["df"]

    def get_settings(self, dataset_id) -> dict:
        return dict(self._get_entry(dataset_id)["settings"])

    def set_settings(self, dataset_id, **changes):
        e = self._get_entry(dataset_id)
        e["settings"].update(changes)
        e["clean"] = None
        e["cache"] = {}
        e["insights_cache"] = None
        db.execute("UPDATE datasets SET settings=? WHERE id=?", (db.dumps(e["settings"]), dataset_id))

    def duplicates_excluded(self, dataset_id) -> int:
        e = self._get_entry(dataset_id)
        if not e["settings"].get("exclude_duplicates", True):
            return 0
        return int(e["df"].duplicated().sum())

    def get_filename(self, dataset_id):
        return self._get_entry(dataset_id)["filename"]

    def get_meta(self, dataset_id) -> dict:
        e = self._get_entry(dataset_id)
        return {
            "id": e["id"], "filename": e["filename"], "uploaded_at": e["uploaded_at"],
            "rows": int(len(e["df"])), "cols": int(e["df"].shape[1]),
            "duplicates_excluded": self.duplicates_excluded(dataset_id),
            "pack_id": e.get("pack_id"), "project_id": e.get("project_id"),
            "user_id": e.get("user_id"),
        }

    def get_pack_id(self, dataset_id):
        return self._get_entry(dataset_id).get("pack_id")

    def set_pack_id(self, dataset_id, pack_id):
        self._get_entry(dataset_id)["pack_id"] = pack_id
        db.execute("UPDATE datasets SET pack_id=? WHERE id=?", (pack_id, dataset_id))

    def list_for_workspace(self, workspace_id=None) -> list[dict]:
        ws = workspace_id or current_workspace.get()
        if ws is None:
            return []
        rows = db.query("SELECT * FROM datasets WHERE workspace_id=? ORDER BY uploaded_at DESC", (ws,))
        return [
            {"id": r["id"], "filename": r["filename"], "rows": r["rows"], "cols": r["cols"],
             "uploaded_at": r["uploaded_at"], "pack_id": r["pack_id"], "project_id": r["project_id"],
             "source": r["source"]}
            for r in rows
        ]

    # ----------------------------------------------------------- caches
    def get_cached_insights(self, dataset_id):
        return self._get_entry(dataset_id).get("insights_cache")

    def set_cached_insights(self, dataset_id, insights):
        with self._lock:
            if dataset_id in self._mem:
                self._mem[dataset_id]["insights_cache"] = insights

    def get_cache(self, dataset_id, key):
        return self._get_entry(dataset_id)["cache"].get(key)

    def set_cache(self, dataset_id, key, value):
        with self._lock:
            e = self._mem.get(dataset_id)
            if e is not None:
                e["cache"][key] = value

    def clear_cache(self, dataset_id):
        with self._lock:
            e = self._mem.get(dataset_id)
            if e is not None:
                e["cache"] = {}
                e["insights_cache"] = None

    # ------------------------------------------- business context (semantic)
    def get_business_context(self, dataset_id) -> dict:
        return self._get_entry(dataset_id)["business_context"]

    def set_business_context(self, dataset_id, context):
        with self._lock:
            e = self._mem.get(dataset_id)
            if e is not None:
                e["business_context"] = context
        db.execute("UPDATE datasets SET business_context=? WHERE id=?", (db.dumps(context), dataset_id))

    # ------------------------------------------------------------ alerts
    def get_alert_rules(self, dataset_id) -> list:
        return self._get_entry(dataset_id)["alert_rules"]

    def set_alert_rules(self, dataset_id, rules):
        with self._lock:
            e = self._mem.get(dataset_id)
            if e is not None:
                e["alert_rules"] = rules
        db.execute("UPDATE datasets SET alert_rules=? WHERE id=?", (db.dumps(rules), dataset_id))

    def get_alert_history(self, dataset_id) -> list:
        return self._get_entry(dataset_id)["alert_history"]

    def append_alert_history(self, dataset_id, events):
        with self._lock:
            e = self._mem.get(dataset_id)
            if e is not None:
                e["alert_history"] = (events + e["alert_history"])[:200]
                hist = e["alert_history"]
            else:
                return
        db.execute("UPDATE datasets SET alert_history=? WHERE id=?", (db.dumps(hist), dataset_id))

    # ----------------------------------------------------------- mutate
    def replace(self, dataset_id, df):
        with self._lock:
            e = self._mem.get(dataset_id) or self._get_entry(dataset_id)
            e.update({"df": df, "insights_cache": None, "cache": {}, "clean": None})
        _write_parquet(df, DATASET_DIR / f"{dataset_id}.parquet")
        db.execute("UPDATE datasets SET rows=?, cols=? WHERE id=?", (int(len(df)), int(df.shape[1]), dataset_id))

    def exists(self, dataset_id) -> bool:
        try:
            self._get_entry(dataset_id)
            return True
        except DatasetNotFoundError:
            return False

    def delete(self, dataset_id):
        self._get_entry(dataset_id)  # permission check
        with self._lock:
            self._mem.pop(dataset_id, None)
        p = DATASET_DIR / f"{dataset_id}.parquet"
        if p.exists():
            p.unlink()
        db.execute("DELETE FROM datasets WHERE id=?", (dataset_id,))

    # ---------------------------------------------------------- internal
    def _get_entry(self, dataset_id) -> dict:
        ws = current_workspace.get()
        e = self._mem.get(dataset_id)
        if e is None:
            e = self._load_from_disk(dataset_id)
        if e is None or (ws is not None and e.get("workspace_id") != ws):
            raise DatasetNotFoundError("Dataset not found. It may have been deleted or you may not have access.")
        return e

    def _load_from_disk(self, dataset_id):
        row = db.one("SELECT * FROM datasets WHERE id=?", (dataset_id,))
        if not row:
            return None
        path = Path(row["path"])
        if not path.exists():
            return None
        df = pd.read_parquet(path)
        entry = self._entry(
            dataset_id, row["workspace_id"], df, row["filename"],
            db.loads(row["business_context"], _default_context()),
            db.loads(row["alert_rules"], []), db.loads(row["alert_history"], []),
            row["pack_id"], row["project_id"], row["uploaded_at"], db.loads(row.get("settings"), None),
            user_id=row["user_id"] if "user_id" in row.keys() else None,
        )
        with self._lock:
            self._mem[dataset_id] = entry
        return entry


dataset_store = DatasetStore()
