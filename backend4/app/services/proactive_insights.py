"""
Proactive Insights — feature 2.

Deterministically scans a dataset for FIVE categories of findings:
  - trend         : sustained directional movement over time
  - anomaly       : statistical outliers / z-score spikes
  - concentration : a neutral observation about share-of-total — NOT
                    automatically a risk; concentration by itself can
                    be perfectly healthy (e.g. your best segment)
  - opportunity   : a segment genuinely outperforming the per-row average
  - risk          : a segment genuinely underperforming, or a strong
                    negative trend

All trend and segment math is delegated to services.analytics_core so
these numbers are IDENTICAL to what Auto Dashboard, Root Cause, and
Executive Reports compute — no independent re-implementation, no
LLM involved anywhere here.
"""

import numpy as np
import pandas as pd

from app.services.column_roles import detect_column_roles
from app.services.analytics_core import (
    period_over_period_change,
    segment_comparison,
    concentration_share,
)


def _trend_findings(df: pd.DataFrame, datetime_cols: list, numeric_cols: list) -> list:
    findings = []
    if not datetime_cols or not numeric_cols:
        return findings

    date_col = datetime_cols[0]

    for value_col in numeric_cols[:5]:
        comparison = period_over_period_change(df, date_col, value_col, aggregation="sum")

        if comparison is None or comparison["change_percentage"] is None:
            continue

        change_pct = comparison["change_percentage"]

        if abs(change_pct) >= 10:
            direction = "increased" if change_pct > 0 else "decreased"

            # only call it a risk/opportunity when the magnitude genuinely
            # supports that label — otherwise it's just a neutral "trend"
            if change_pct <= -20:
                finding_type = "risk"
            elif change_pct >= 20:
                finding_type = "opportunity"
            else:
                finding_type = "trend"

            findings.append({
                "type": finding_type,
                "severity": "high" if abs(change_pct) >= 30 else "medium",
                "title": (
                    f"{value_col} has {direction} {abs(round(change_pct, 1))}% from "
                    f"{comparison['first_period_label']} to {comparison['last_period_label']}"
                ),
                "metric": value_col,
                "detail": comparison,
            })

    return findings


def _anomaly_findings(df: pd.DataFrame, numeric_cols: list) -> list:
    findings = []

    for col in numeric_cols[:8]:
        series = df[col].dropna()
        if len(series) < 5 or series.std() == 0:
            continue

        z_scores = (series - series.mean()) / series.std()
        extreme = series[z_scores.abs() > 3]

        if len(extreme) == 0:
            continue

        findings.append({
            "type": "anomaly",
            "severity": "high" if len(extreme) / len(series) > 0.02 else "medium",
            "title": f"{len(extreme)} extreme outlier(s) detected in {col}",
            "metric": col,
            "detail": {
                "outlier_count": int(len(extreme)),
                "outlier_percentage": round(float(len(extreme) / len(series) * 100), 2),
                "sample_values": [float(v) for v in extreme.head(5).tolist()],
                "normal_range": [
                    round(float(series.mean() - 3 * series.std()), 2),
                    round(float(series.mean() + 3 * series.std()), 2),
                ],
            },
        })

    return findings


def _segment_findings(df: pd.DataFrame, categorical_cols: list, numeric_cols: list) -> list:
    findings = []

    if not categorical_cols or not numeric_cols:
        return findings

    value_col = numeric_cols[0]

    for cat_col in categorical_cols[:5]:
        nunique = df[cat_col].nunique()
        if nunique < 2 or nunique > 25:
            continue

        # --- concentration: a neutral OBSERVATION about share of total,
        # never automatically a "risk" — that label requires more evidence
        concentration = concentration_share(df, value_col, cat_col)
        if concentration and concentration["top_share_percentage"] >= 50:
            findings.append({
                "type": "concentration",
                "severity": "medium",
                "title": (
                    f"'{concentration['top_segment']}' accounts for "
                    f"{concentration['top_share_percentage']}% of total {value_col} in {cat_col}"
                    + (f" ({concentration['unassigned_percentage']}% of {value_col} has no {cat_col} label)"
                       if concentration.get("unassigned_percentage", 0) >= 0.5 else "")
                ),
                "metric": value_col,
                "detail": concentration,
            })

        if nunique < 3:
            continue

        # --- opportunity / risk: genuine per-row-average outperformance,
        # NOT a raw sum ratio (which is inflated by segment row-count)
        comparison = segment_comparison(df, value_col, cat_col)
        if not comparison:
            continue

        segments = comparison["segments"]
        top = segments[0]
        bottom = segments[-1]

        # NOTE: a per-row average gap mostly reflects TICKET SIZE / product mix
        # (a laptop sells for more than a mouse), not performance. So these are
        # neutral "mix" observations; real risks/opportunities come from the
        # Profit Impact Engine (margin gaps, losses, leakage, declines).
        if top["ratio_vs_overall"] and top["ratio_vs_overall"] >= 2:
            findings.append({
                "type": "mix",
                "severity": "low",
                "title": (
                    f"'{top['segment']}' has an average {value_col} per row {top['ratio_vs_overall']}x the overall "
                    f"average in {cat_col} (larger ticket size — says nothing about profitability)"
                ),
                "metric": value_col,
                "detail": {
                    "dimension": cat_col,
                    "segment": top["segment"],
                    "segment_average": top["mean"],
                    "overall_average": comparison["overall_mean"],
                    "ratio_vs_overall": top["ratio_vs_overall"],
                },
            })

        if bottom["ratio_vs_overall"] and bottom["ratio_vs_overall"] <= 0.3:
            findings.append({
                "type": "mix",
                "severity": "low",
                "title": (
                    f"'{bottom['segment']}' has an average {value_col} per row only {bottom['ratio_vs_overall']}x the "
                    f"overall average in {cat_col} (smaller ticket size — not necessarily weak performance)"
                ),
                "metric": value_col,
                "detail": {
                    "dimension": cat_col,
                    "segment": bottom["segment"],
                    "segment_average": bottom["mean"],
                    "overall_average": comparison["overall_mean"],
                    "ratio_vs_overall": bottom["ratio_vs_overall"],
                },
            })

    return findings


def scan_for_insights(df: pd.DataFrame) -> dict:
    roles = detect_column_roles(df)
    numeric_cols = roles["by_role"]["metric"]
    categorical_cols = roles["by_role"]["dimension"]
    datetime_cols = roles["by_role"]["datetime"]

    findings = []
    findings += _trend_findings(df, datetime_cols, numeric_cols)
    findings += _anomaly_findings(df, numeric_cols)
    findings += _segment_findings(df, categorical_cols, numeric_cols)

    severity_order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: severity_order.get(f["severity"], 3))

    return {
        "total_findings": len(findings),
        "by_type": {
            t: len([f for f in findings if f["type"] == t])
            for t in ["trend", "anomaly", "concentration", "opportunity", "risk"]
        },
        "findings": findings[:20],
    }
