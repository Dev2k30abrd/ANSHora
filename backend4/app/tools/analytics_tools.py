"""
Analytics toolkit for the data analyst agent.

Each function takes a DataFrame (+ args) and returns a plain-dict
result that is JSON-safe (no NaN/Inf/numpy types/Timestamps leaking
through) so it can go straight into an HTTP response or an LLM prompt.
"""

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _clean(value):
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        f = float(value)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(value, float):
        return None if (np.isnan(value) or np.isinf(value)) else value
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def _clean_dict(d: dict) -> dict:
    return {str(k): _clean(v) for k, v in d.items()}


def _clean_records(records: list[dict]) -> list[dict]:
    return [_clean_dict(r) for r in records]


def _require_column(df: pd.DataFrame, column: str):
    if column not in df.columns:
        raise ValueError(
            f"Column '{column}' not found. Available columns: {df.columns.tolist()}"
        )


def _is_numeric(df: pd.DataFrame, column: str) -> bool:
    return pd.api.types.is_numeric_dtype(df[column])


# ---------------------------------------------------------------------------
# 1. overview stats
# ---------------------------------------------------------------------------

def get_basic_statistics(df: pd.DataFrame) -> dict:
    numeric_df = df.select_dtypes(include="number")

    result = {"row_count": int(df.shape[0]), "column_count": int(df.shape[1])}

    if numeric_df.empty:
        result["message"] = "No numerical columns found in the dataset."
    else:
        stats = numeric_df.describe().to_dict()
        result["numeric_columns"] = numeric_df.columns.tolist()
        result["statistics"] = {
            col: _clean_dict(vals) for col, vals in stats.items()
        }

    categorical_df = df.select_dtypes(exclude="number")
    if not categorical_df.empty:
        result["categorical_columns"] = categorical_df.columns.tolist()

    return result


# ---------------------------------------------------------------------------
# 2. single column deep-dive
# ---------------------------------------------------------------------------

def get_column_analysis(df: pd.DataFrame, column: str) -> dict:
    _require_column(df, column)
    series = df[column]

    result = {
        "column": column,
        "data_type": str(series.dtype),
        "missing_values": int(series.isnull().sum()),
        "missing_percentage": round(float(series.isnull().mean() * 100), 2),
        "unique_values": int(series.nunique()),
    }

    if _is_numeric(df, column):
        non_null = series.dropna()
        result["type"] = "numerical"
        result["statistics"] = {
            "mean": _clean(non_null.mean()) if len(non_null) else None,
            "median": _clean(non_null.median()) if len(non_null) else None,
            "min": _clean(non_null.min()) if len(non_null) else None,
            "max": _clean(non_null.max()) if len(non_null) else None,
            "std": _clean(non_null.std()) if len(non_null) else None,
            "sum": _clean(non_null.sum()) if len(non_null) else None,
            "skew": _clean(non_null.skew()) if len(non_null) > 2 else None,
        }
    else:
        result["type"] = "categorical"
        counts = series.value_counts().head(10)
        result["top_values"] = _clean_dict(counts.to_dict())
        result["top_values_percentage"] = _clean_dict(
            (series.value_counts(normalize=True).head(10) * 100).round(2).to_dict()
        )

    return result


# ---------------------------------------------------------------------------
# 3. group / aggregate
# ---------------------------------------------------------------------------

def group_analysis(
    df: pd.DataFrame,
    group_column: str,
    value_column: str,
    operation: str = "sum",
) -> dict:
    _require_column(df, group_column)
    _require_column(df, value_column)

    allowed = ["sum", "mean", "count", "min", "max", "median", "std"]
    if operation not in allowed:
        raise ValueError(f"Operation must be one of: {allowed}")

    grouped = df.groupby(group_column)[value_column]
    result = grouped.count() if operation == "count" else grouped.agg(operation)
    result = result.sort_values(ascending=False)

    return {
        "group_column": group_column,
        "value_column": value_column,
        "operation": operation,
        "result": {str(k): _clean(v) for k, v in result.items()},
        "chart": {
            "type": "bar",
            "title": f"{value_column} by {group_column} ({operation})",
            "labels": [str(k) for k in result.index.tolist()][:20],
            "series": [{"name": operation, "data": [_clean(v) for v in result.tolist()][:20]}],
        },
    }


# ---------------------------------------------------------------------------
# 4. correlation
# ---------------------------------------------------------------------------

def correlation_analysis(df: pd.DataFrame) -> dict:
    numeric_df = df.select_dtypes(include="number")

    if numeric_df.shape[1] < 2:
        return {"message": "At least two numerical columns are required for correlation analysis."}

    correlation = numeric_df.corr().round(4)

    # surface the strongest relationships (excluding self-correlation)
    pairs = []
    cols = correlation.columns.tolist()
    for i, a in enumerate(cols):
        for b in cols[i + 1:]:
            value = correlation.loc[a, b]
            if pd.notna(value):
                pairs.append({"columns": [a, b], "correlation": _clean(value)})

    pairs.sort(key=lambda p: abs(p["correlation"]), reverse=True)

    return {
        "numeric_columns": cols,
        "correlation": {c: _clean_dict(v) for c, v in correlation.to_dict().items()},
        "strongest_relationships": pairs[:8],
    }


# ---------------------------------------------------------------------------
# 5. missing value report
# ---------------------------------------------------------------------------

def missing_value_report(df: pd.DataFrame) -> dict:
    missing = df.isnull().sum()
    missing = missing[missing > 0].sort_values(ascending=False)

    if missing.empty:
        return {"message": "No missing values found in the dataset.", "clean": True}

    total_rows = len(df)
    report = {
        col: {
            "missing_count": int(count),
            "missing_percentage": round(float(count / total_rows * 100), 2),
        }
        for col, count in missing.items()
    }

    rows_with_any_missing = int(df.isnull().any(axis=1).sum())

    return {
        "clean": False,
        "columns_with_missing": report,
        "rows_with_any_missing": rows_with_any_missing,
        "rows_with_any_missing_percentage": round(rows_with_any_missing / total_rows * 100, 2),
        "recommendation": (
            "Consider dropping rows/columns with excessive missing data, "
            "or imputing with mean/median (numeric) or mode (categorical)."
        ),
    }


# ---------------------------------------------------------------------------
# 6. outlier detection (IQR method)
# ---------------------------------------------------------------------------

def outlier_detection(df: pd.DataFrame, column: str | None = None) -> dict:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    if column:
        _require_column(df, column)
        if not _is_numeric(df, column):
            raise ValueError(f"Column '{column}' is not numeric; outlier detection needs a numeric column.")
        target_cols = [column]
    else:
        target_cols = numeric_cols

    if not target_cols:
        return {"message": "No numeric columns available for outlier detection."}

    results = {}
    for col in target_cols:
        series = df[col].dropna()
        if series.empty:
            continue

        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        outliers = series[(series < lower) | (series > upper)]

        results[col] = {
            "lower_bound": _clean(lower),
            "upper_bound": _clean(upper),
            "outlier_count": int(outliers.shape[0]),
            "outlier_percentage": round(float(outliers.shape[0] / series.shape[0] * 100), 2),
            "sample_outlier_values": [_clean(v) for v in outliers.head(10).tolist()],
        }

    return {"method": "IQR (1.5x)", "columns": results}


# ---------------------------------------------------------------------------
# 7. distribution / histogram data (chart-ready)
# ---------------------------------------------------------------------------

def distribution_analysis(df: pd.DataFrame, column: str, bins: int = 10) -> dict:
    _require_column(df, column)
    series = df[column].dropna()

    if series.empty:
        return {"message": f"Column '{column}' has no non-null values."}

    if _is_numeric(df, column):
        counts, edges = np.histogram(series, bins=bins)
        labels = [f"{edges[i]:.2f}–{edges[i+1]:.2f}" for i in range(len(edges) - 1)]

        return {
            "column": column,
            "type": "numerical",
            "chart": {
                "type": "bar",
                "title": f"Distribution of {column}",
                "labels": labels,
                "series": [{"name": "frequency", "data": [int(c) for c in counts]}],
            },
        }

    counts = series.value_counts().head(15)
    return {
        "column": column,
        "type": "categorical",
        "chart": {
            "type": "bar",
            "title": f"Distribution of {column}",
            "labels": [str(v) for v in counts.index.tolist()],
            "series": [{"name": "count", "data": [int(v) for v in counts.tolist()]}],
        },
    }


# ---------------------------------------------------------------------------
# 8. pivot table
# ---------------------------------------------------------------------------

def pivot_table_analysis(
    df: pd.DataFrame,
    index: str,
    values: str,
    columns: str | None = None,
    aggfunc: str = "sum",
) -> dict:
    _require_column(df, index)
    _require_column(df, values)
    if columns:
        _require_column(df, columns)

    allowed = ["sum", "mean", "count", "min", "max", "median"]
    if aggfunc not in allowed:
        raise ValueError(f"aggfunc must be one of: {allowed}")

    pivot = pd.pivot_table(
        df, index=index, columns=columns, values=values, aggfunc=aggfunc, fill_value=0
    )

    if isinstance(pivot, pd.Series):
        pivot = pivot.to_frame()

    return {
        "index": index,
        "columns": columns,
        "values": values,
        "aggfunc": aggfunc,
        "table": {
            str(row): _clean_dict(pivot.loc[row].to_dict())
            for row in pivot.index.tolist()
        },
    }


# ---------------------------------------------------------------------------
# 9. trend / time-series analysis
# ---------------------------------------------------------------------------

_FREQ_ALIASES = {"M": "ME", "Y": "YE", "A": "YE", "W": "W", "D": "D"}


def trend_analysis(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    freq: str = "M",
) -> dict:
    _require_column(df, date_column)
    _require_column(df, value_column)

    freq = _FREQ_ALIASES.get(freq.upper(), freq)

    working = df[[date_column, value_column]].copy()
    working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
    working = working.dropna(subset=[date_column])

    if working.empty:
        raise ValueError(f"Column '{date_column}' could not be parsed as dates.")

    working = working.set_index(date_column).sort_index()
    resampled = working[value_column].resample(freq).sum()

    values = resampled.tolist()
    trend_direction = "insufficient data"
    if len(values) >= 2:
        first_half_avg = np.mean(values[: len(values) // 2]) if len(values) > 2 else values[0]
        second_half_avg = np.mean(values[len(values) // 2:])
        if second_half_avg > first_half_avg * 1.05:
            trend_direction = "upward"
        elif second_half_avg < first_half_avg * 0.95:
            trend_direction = "downward"
        else:
            trend_direction = "flat"

    return {
        "date_column": date_column,
        "value_column": value_column,
        "frequency": freq,
        "trend_direction": trend_direction,
        "chart": {
            "type": "line",
            "title": f"{value_column} over time",
            "labels": [str(idx.date()) for idx in resampled.index],
            "series": [{"name": value_column, "data": [_clean(v) for v in values]}],
        },
    }


# ---------------------------------------------------------------------------
# 10. top / bottom N rows
# ---------------------------------------------------------------------------

def top_n_analysis(
    df: pd.DataFrame,
    column: str,
    n: int = 10,
    ascending: bool = False,
) -> dict:
    _require_column(df, column)

    sorted_df = df.sort_values(by=column, ascending=ascending).head(n)

    return {
        "column": column,
        "n": n,
        "order": "ascending" if ascending else "descending",
        "rows": _clean_records(sorted_df.to_dict(orient="records")),
    }


# ---------------------------------------------------------------------------
# 11. filter / query
# ---------------------------------------------------------------------------

_OPERATORS = {
    ">": lambda s, v: s > v,
    "<": lambda s, v: s < v,
    ">=": lambda s, v: s >= v,
    "<=": lambda s, v: s <= v,
    "==": lambda s, v: s == v,
    "!=": lambda s, v: s != v,
    "contains": lambda s, v: s.astype(str).str.contains(str(v), case=False, na=False),
}


def filter_analysis(
    df: pd.DataFrame,
    column: str,
    operator: str,
    value,
    limit: int = 20,
) -> dict:
    _require_column(df, column)

    if operator not in _OPERATORS:
        raise ValueError(f"operator must be one of: {list(_OPERATORS.keys())}")

    series = df[column]

    if operator != "contains" and _is_numeric(df, column):
        try:
            value = float(value)
        except (TypeError, ValueError):
            pass

    mask = _OPERATORS[operator](series, value)
    filtered = df[mask]

    return {
        "column": column,
        "operator": operator,
        "value": value,
        "matching_rows": int(filtered.shape[0]),
        "matching_percentage": round(float(filtered.shape[0] / len(df) * 100), 2) if len(df) else 0,
        "preview": _clean_records(filtered.head(limit).to_dict(orient="records")),
    }


# ---------------------------------------------------------------------------
# 12. full automatic EDA sweep (deterministic — no LLM needed to compute it)
# ---------------------------------------------------------------------------

def full_eda_summary(df: pd.DataFrame) -> dict:
    from app.services.dataset_service import classify_columns

    column_types = classify_columns(df)
    numeric_cols = column_types["numeric"]
    categorical_cols = column_types["categorical"]

    summary = {
        "shape": {"rows": int(df.shape[0]), "columns": int(df.shape[1])},
        "column_types": column_types,
        "missing": missing_value_report(df),
        "duplicate_rows": int(df.duplicated().sum()),
    }

    if numeric_cols:
        summary["numeric_overview"] = get_basic_statistics(df)
        outliers = outlier_detection(df)
        summary["outliers"] = outliers
        if len(numeric_cols) >= 2:
            summary["top_correlations"] = correlation_analysis(df).get(
                "strongest_relationships", []
            )

    if categorical_cols:
        summary["categorical_overview"] = {
            col: {
                "unique_values": int(df[col].nunique()),
                "top_value": (
                    str(df[col].mode().iloc[0]) if not df[col].mode().empty else None
                ),
            }
            for col in categorical_cols[:8]
        }

    return summary
