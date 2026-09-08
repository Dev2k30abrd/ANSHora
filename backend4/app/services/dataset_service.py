import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi import UploadFile

UPLOAD_DIR = Path("uploads")

SUPPORTED_EXTENSIONS = [
    ".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet",
]


def save_uploaded_file(file: UploadFile) -> Path:
    """Save the uploaded dataset locally."""

    UPLOAD_DIR.mkdir(exist_ok=True)

    safe_name = Path(file.filename).name
    file_path = UPLOAD_DIR / safe_name

    with open(file_path, "wb") as buffer:
        buffer.write(file.file.read())

    return file_path


def load_dataset(file_path: Path) -> pd.DataFrame:
    """
    Load a dataset of almost any common tabular format into a
    Pandas DataFrame. Falls back gracefully on encoding issues.
    """

    ext = file_path.suffix.lower()

    if ext == ".csv":
        return _read_csv_robust(file_path, sep=",")

    if ext == ".tsv":
        return _read_csv_robust(file_path, sep="\t")

    if ext in (".xlsx", ".xls"):
        return pd.read_excel(file_path)

    if ext == ".json":
        try:
            return pd.read_json(file_path)
        except ValueError:
            # newline-delimited JSON
            return pd.read_json(file_path, lines=True)

    if ext == ".parquet":
        return pd.read_parquet(file_path)

    raise ValueError(
        f"Unsupported file format '{ext}'. Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


def _read_csv_robust(file_path: Path, sep: str) -> pd.DataFrame:
    encodings = ["utf-8", "utf-8-sig", "latin-1", "cp1252"]
    last_error = None

    for encoding in encodings:
        try:
            return pd.read_csv(file_path, sep=sep, encoding=encoding)
        except (UnicodeDecodeError, UnicodeError) as error:
            last_error = error
            continue

    raise ValueError(f"Could not decode file with common encodings: {last_error}")


def _clean_for_json(value):
    """Make a value JSON-safe (handles NaN/Inf/Timestamps/numpy types)."""

    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()

    if isinstance(value, (np.integer,)):
        return int(value)

    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if (np.isnan(f) or np.isinf(f)) else f

    if isinstance(value, float):
        return None if (np.isnan(value) or np.isinf(value)) else value

    return value


def _clean_records(records: list[dict]) -> list[dict]:
    return [
        {k: _clean_for_json(v) for k, v in record.items()}
        for record in records
    ]


def classify_columns(df: pd.DataFrame) -> dict:
    """Split columns into numeric / categorical / datetime / boolean buckets."""

    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    bool_cols = df.select_dtypes(include="bool").columns.tolist()
    datetime_cols = df.select_dtypes(include="datetime").columns.tolist()

    remaining = [
        c for c in df.columns
        if c not in numeric_cols and c not in bool_cols and c not in datetime_cols
    ]

    # try to detect datetime-looking text columns (cheap heuristic)
    detected_datetime = []
    categorical_cols = []

    for col in remaining:
        sample = df[col].dropna().head(20)

        if len(sample) > 0 and _looks_like_datetime(sample):
            detected_datetime.append(col)
        else:
            categorical_cols.append(col)

    return {
        "numeric": numeric_cols,
        "categorical": categorical_cols,
        "datetime": datetime_cols + detected_datetime,
        "boolean": bool_cols,
    }


def _looks_like_datetime(sample: pd.Series) -> bool:
    import warnings

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(sample, errors="coerce")
        return parsed.notna().mean() > 0.85
    except Exception:
        return False


def get_dataset_summary(df: pd.DataFrame) -> dict:
    """Generate a rich profiling summary of the dataset."""

    column_types = classify_columns(df)

    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2) if len(df) else missing

    summary = {
        "rows": int(df.shape[0]),
        "columns": int(df.shape[1]),
        "column_names": df.columns.tolist(),
        "column_types": column_types,
        "data_types": {c: str(dt) for c, dt in df.dtypes.items()},
        "missing_values": {c: int(v) for c, v in missing.items()},
        "missing_percentage": {c: float(v) for c, v in missing_pct.items()},
        "duplicate_rows": int(df.duplicated().sum()),
        "memory_usage_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
        "preview": _clean_records(df.head(5).to_dict(orient="records")),
    }

    return summary
