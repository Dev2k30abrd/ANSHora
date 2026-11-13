"""
Root Cause Analysis — feature 3.

When a metric changes, decompose it across dimensions to quantify each
segment's contribution to that change. Two modes, chosen automatically:

  - time-based: if a date column exists, split into "before" and
    "after" periods and compute each segment's contribution to the
    delta (classic driver-analysis decomposition).
  - segment-based: if no usable date column, compare each segment
    against the overall average to find the largest deviations.

Deterministic pandas only — no LLM.
"""

import pandas as pd

from app.services.column_roles import detect_column_roles
from app.services.analytics_core import segment_comparison


def _time_based_root_cause(df, metric_column, date_column, dimensions):
    working = df.copy()
    working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
    working = working.dropna(subset=[date_column, metric_column]).sort_values(date_column)

    if len(working) < 4:
        return None

    midpoint = working[date_column].iloc[len(working) // 2]
    before = working[working[date_column] < midpoint]
    after = working[working[date_column] >= midpoint]

    if before.empty or after.empty:
        return None

    total_before = before[metric_column].sum()
    total_after = after[metric_column].sum()
    total_change = total_after - total_before

    drivers = {}

    for dim in dimensions:
        if dim not in working.columns:
            continue

        before_by_seg = before.groupby(dim)[metric_column].sum()
        after_by_seg = after.groupby(dim)[metric_column].sum()

        all_segments = set(before_by_seg.index) | set(after_by_seg.index)
        segment_deltas = []

        for seg in all_segments:
            b = float(before_by_seg.get(seg, 0))
            a = float(after_by_seg.get(seg, 0))
            delta = a - b
            contribution_pct = (delta / total_change * 100) if total_change != 0 else 0

            segment_deltas.append({
                "segment": str(seg),
                "before": round(b, 2),
                "after": round(a, 2),
                "delta": round(delta, 2),
                "contribution_percentage": round(float(contribution_pct), 2),
            })

        segment_deltas.sort(key=lambda x: abs(x["delta"]), reverse=True)
        drivers[dim] = segment_deltas[:8]

    return {
        "mode": "time_based",
        "metric": metric_column,
        "period_split_date": str(midpoint.date()),
        "before_total": round(float(total_before), 2),
        "after_total": round(float(total_after), 2),
        "total_change": round(float(total_change), 2),
        "total_change_percentage": round(
            float(total_change / total_before * 100) if total_before else 0, 2
        ),
        "drivers_by_dimension": drivers,
    }


def _segment_based_root_cause(df, metric_column, dimensions):
    overall_avg = df[metric_column].mean()
    drivers = {}

    for dim in dimensions:
        if dim not in df.columns:
            continue

        # delegates to the SAME canonical function proactive_insights and
        # everything else uses — guarantees identical deviation/ratio
        # numbers across features for the same metric+dimension
        comparison = segment_comparison(df, metric_column, dim)
        if not comparison:
            continue

        segments_by_deviation = sorted(
            comparison["segments"], key=lambda s: abs(s["deviation_from_overall_percentage"]), reverse=True
        )

        drivers[dim] = [
            {
                "segment": s["segment"],
                "segment_mean": s["mean"],
                "segment_sum": s["sum"],
                "row_count": s["row_count"],
                "deviation_from_overall_percentage": s["deviation_from_overall_percentage"],
            }
            for s in segments_by_deviation[:8]
        ]

    return {
        "mode": "segment_based",
        "metric": metric_column,
        "overall_average": round(float(overall_avg), 2) if pd.notna(overall_avg) else None,
        "drivers_by_dimension": drivers,
    }


def analyze_root_cause(
    df: pd.DataFrame,
    metric_column: str,
    date_column: str | None = None,
    dimensions: list | None = None,
) -> dict:
    if metric_column not in df.columns:
        raise ValueError(f"Metric column '{metric_column}' not found.")
    if not pd.api.types.is_numeric_dtype(df[metric_column]):
        raise ValueError(f"Metric column '{metric_column}' must be numeric.")

    roles = detect_column_roles(df)

    if metric_column in roles["by_column"] and roles["by_column"][metric_column] == "identifier":
        raise ValueError(
            f"'{metric_column}' looks like an identifier column, not a measurable metric — "
            "root cause analysis needs a genuine numeric measure (e.g. sales, revenue, count)."
        )

    # auto-detect dimensions if not provided — deterministic fallback,
    # avoids needing another LLM round-trip just to pick columns
    if not dimensions:
        dimensions = roles["by_role"]["dimension"][:4]
    else:
        # even user/LLM-supplied dimensions get filtered against the role
        # detector — never let an identifier column be used as a driver dimension
        dimensions = [
            d for d in dimensions
            if d in df.columns and roles["by_column"].get(d) in ("dimension", "boolean")
        ]

    if not dimensions:
        raise ValueError(
            "No suitable categorical dimensions found to decompose this metric by "
            "(only identifier/free-text/metric columns are available)."
        )

    if date_column and date_column in df.columns:
        result = _time_based_root_cause(df, metric_column, date_column, dimensions)
        if result:
            result["dimensions_analyzed"] = dimensions
            return result

    result = _segment_based_root_cause(df, metric_column, dimensions)
    result["dimensions_analyzed"] = dimensions
    return result
