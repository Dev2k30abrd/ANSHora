"""
Data Health Center — feature 6.

Computes a deterministic 0-100 data quality score from four weighted
factors: missing values, duplicate rows, outlier prevalence, and
type-consistency issues. Every number here is computed directly from
the dataframe — no LLM involved.
"""

import numpy as np
import pandas as pd


def _score_missing(df: pd.DataFrame) -> tuple[float, dict]:
    if df.empty:
        return 100.0, {}

    missing_pct = df.isnull().mean().mean() * 100
    score = max(0.0, 100 - missing_pct * 2.5)  # 40% missing -> 0 score

    worst_columns = (
        df.isnull().mean().sort_values(ascending=False).head(5) * 100
    ).round(2)
    worst_columns = worst_columns[worst_columns > 0]

    return score, {
        "overall_missing_percentage": round(float(missing_pct), 2),
        "worst_columns": {k: float(v) for k, v in worst_columns.items()},
    }


def _score_duplicates(df: pd.DataFrame) -> tuple[float, dict]:
    if df.empty:
        return 100.0, {}

    dup_count = int(df.duplicated().sum())
    dup_pct = dup_count / len(df) * 100
    score = max(0.0, 100 - dup_pct * 3)  # ~33% dupes -> 0 score

    return score, {
        "duplicate_rows": dup_count,
        "duplicate_percentage": round(float(dup_pct), 2),
    }


def _score_outliers(df: pd.DataFrame) -> tuple[float, dict]:
    numeric_df = df.select_dtypes(include="number")

    if numeric_df.empty:
        return 100.0, {"message": "No numeric columns to check."}

    total_outlier_ratio = []
    per_column = {}

    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        if series.empty:
            continue

        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr == 0:
            continue

        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outliers = series[(series < lower) | (series > upper)]
        ratio = len(outliers) / len(series)

        total_outlier_ratio.append(ratio)
        if ratio > 0:
            per_column[col] = round(float(ratio * 100), 2)

    avg_ratio = float(np.mean(total_outlier_ratio)) if total_outlier_ratio else 0.0
    score = max(0.0, 100 - avg_ratio * 100 * 4)  # ~25% outliers -> 0 score

    return score, {
        "average_outlier_percentage": round(avg_ratio * 100, 2),
        "columns_with_outliers": per_column,
    }


def _score_type_consistency(df: pd.DataFrame) -> tuple[float, dict]:
    """
    Flags 'object' columns that are actually mostly-numeric or
    mostly-date but stored as text (a common real-world data-entry
    problem), and mixed-type columns.
    """

    issues = {}
    penalty = 0.0

    for col in df.select_dtypes(include="object").columns:
        series = df[col].dropna()
        if series.empty:
            continue

        numeric_coerced = pd.to_numeric(series, errors="coerce")
        numeric_ratio = numeric_coerced.notna().mean()

        if 0.5 < numeric_ratio < 1.0:
            issues[col] = f"{round(numeric_ratio * 100, 1)}% of values look numeric but column is stored as text."
            penalty += 8

        type_names = series.map(lambda v: type(v).__name__).nunique()
        if type_names > 1:
            issues[col] = issues.get(col, "") + f" Mixed Python types detected ({type_names} distinct types)."
            penalty += 5

    score = max(0.0, 100 - penalty)
    return score, {"issues": issues}


def compute_data_health(df: pd.DataFrame) -> dict:
    missing_score, missing_detail = _score_missing(df)
    dup_score, dup_detail = _score_duplicates(df)
    outlier_score, outlier_detail = _score_outliers(df)
    type_score, type_detail = _score_type_consistency(df)

    weights = {"missing": 0.35, "duplicates": 0.20, "outliers": 0.25, "types": 0.20}

    overall = (
        missing_score * weights["missing"]
        + dup_score * weights["duplicates"]
        + outlier_score * weights["outliers"]
        + type_score * weights["types"]
    )

    if overall >= 90:
        grade = "Excellent"
    elif overall >= 75:
        grade = "Good"
    elif overall >= 55:
        grade = "Fair"
    else:
        grade = "Needs attention"

    recommendations = []

    if missing_detail.get("overall_missing_percentage", 0) > 5:
        recommendations.append(
            "Impute or drop columns with high missing rates before deeper analysis "
            "(mean/median for numeric, mode for categorical)."
        )
    if dup_detail.get("duplicate_rows", 0) > 0:
        recommendations.append(
            f"Remove {dup_detail['duplicate_rows']} duplicate row(s) to avoid double-counting in aggregates."
        )
    if outlier_detail.get("average_outlier_percentage", 0) > 5:
        recommendations.append(
            "Investigate outlier-heavy columns — they may be data-entry errors or genuine extreme events worth flagging separately."
        )
    if type_detail.get("issues"):
        recommendations.append(
            "Convert text columns that are actually numeric/date into proper types for correct aggregation and sorting."
        )
    if not recommendations:
        recommendations.append("No major data quality issues detected. Dataset is ready for analysis.")

    return {
        "overall_score": round(float(overall), 1),
        "grade": grade,
        "breakdown": {
            "missing_values": {"score": round(missing_score, 1), **missing_detail},
            "duplicates": {"score": round(dup_score, 1), **dup_detail},
            "outliers": {"score": round(outlier_score, 1), **outlier_detail},
            "type_consistency": {"score": round(type_score, 1), **type_detail},
        },
        "recommendations": recommendations,
    }
