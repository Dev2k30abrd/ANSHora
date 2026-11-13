"""
Auto Dashboard — feature 1.

Given ANY uploaded dataset, deterministically pick the most relevant
KPIs (numeric column summaries) and charts (top categorical breakdowns,
time trends if a date column exists) without any LLM call. Pure
pandas/numpy profiling — fast and hallucination-free.
"""

import numpy as np
import pandas as pd

from app.services.column_roles import detect_column_roles
from app.services.analytics_core import resample_time_series


MAX_KPIS = 6
MAX_CHARTS = 4


def _build_kpi(df: pd.DataFrame, column: str) -> dict:
    series = df[column].dropna()

    if series.empty:
        return None

    return {
        "metric": column,
        "sum": float(series.sum()),
        "mean": round(float(series.mean()), 2),
        "min": float(series.min()),
        "max": float(series.max()),
        "count": int(series.count()),
    }


def _build_category_chart(df: pd.DataFrame, column: str) -> dict:
    counts = df[column].value_counts().head(10)

    return {
        "type": "bar",
        "title": f"Breakdown by {column}",
        "labels": [str(v) for v in counts.index.tolist()],
        "series": [{"name": "count", "data": [int(v) for v in counts.tolist()]}],
    }


def _build_numeric_by_category_chart(df: pd.DataFrame, num_col: str, cat_col: str) -> dict:
    grouped = df.groupby(cat_col)[num_col].sum().sort_values(ascending=False).head(10)

    return {
        "type": "bar",
        "title": f"Total {num_col} by {cat_col}",
        "labels": [str(v) for v in grouped.index.tolist()],
        "series": [{"name": num_col, "data": [round(float(v), 2) for v in grouped.tolist()]}],
    }


def _build_trend_chart(df: pd.DataFrame, date_col: str, value_col: str) -> dict:
    resampled, _freq = resample_time_series(df, date_col, value_col, aggregation="sum")

    if resampled.empty:
        return None

    return {
        "type": "line",
        "title": f"{value_col} over time",
        "labels": [str(idx.date()) for idx in resampled.index],
        "series": [{"name": value_col, "data": [round(float(v), 2) for v in resampled.tolist()]}],
    }


def _is_identifier_like(df: pd.DataFrame, column: str) -> bool:
    """Kept for backward compatibility; delegates to the shared role detector."""

    from app.services.column_roles import infer_column_role

    return infer_column_role(df, column) == "identifier"


def generate_auto_dashboard(df: pd.DataFrame) -> dict:
    roles = detect_column_roles(df)
    numeric_cols = roles["by_role"]["metric"]
    categorical_cols = roles["by_role"]["dimension"]
    datetime_cols = roles["by_role"]["datetime"]

    # --- KPIs: pick numeric columns with the widest dynamic range / most variance signal first
    kpi_candidates = []
    for col in numeric_cols:
        series = df[col].dropna()
        if series.empty or series.nunique() <= 1:
            continue
        kpi_candidates.append((col, float(series.std() or 0)))

    kpi_candidates.sort(key=lambda x: x[1], reverse=True)
    kpis = []
    for col, _ in kpi_candidates[:MAX_KPIS]:
        kpi = _build_kpi(df, col)
        if kpi:
            kpis.append(kpi)

    # --- Charts: prioritize numeric-by-category (most informative), then trend, then plain category counts
    charts = []

    best_numeric = kpi_candidates[0][0] if kpi_candidates else None

    if datetime_cols and best_numeric:
        trend = _build_trend_chart(df, datetime_cols[0], best_numeric)
        if trend:
            charts.append(trend)

    for cat_col in categorical_cols:
        if len(charts) >= MAX_CHARTS:
            break
        if df[cat_col].nunique() > 30 or df[cat_col].nunique() < 2:
            continue  # too granular (like free-text/IDs) or constant, not chart-worthy

        if best_numeric:
            charts.append(_build_numeric_by_category_chart(df, best_numeric, cat_col))
        else:
            charts.append(_build_category_chart(df, cat_col))

    while len(charts) < MAX_CHARTS and numeric_cols:
        # fall back to distributions of remaining numeric KPIs
        remaining = [c for c in numeric_cols if c != best_numeric]
        if not remaining:
            break
        col = remaining[0]
        counts, edges = np.histogram(df[col].dropna(), bins=8)
        charts.append({
            "type": "bar",
            "title": f"Distribution of {col}",
            "labels": [f"{edges[i]:.1f}–{edges[i+1]:.1f}" for i in range(len(edges) - 1)],
            "series": [{"name": "frequency", "data": [int(c) for c in counts]}],
        })
        numeric_cols = [c for c in numeric_cols if c != col]

    return {
        "row_count": int(df.shape[0]),
        "column_count": int(df.shape[1]),
        "kpis": kpis,
        "charts": charts[:MAX_CHARTS],
    }
