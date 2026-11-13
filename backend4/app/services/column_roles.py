"""
Semantic column role detection.

Every analytics module (dashboard, insights, root-cause, agent planner)
needs to agree on what a column IS before touching it — an identifier
column must never be averaged, charted as a metric, or used as a
group-by dimension pretending to be a measure. This module is the
single source of truth for that classification so the logic lives in
one place instead of being re-implemented (and re-buggy) per feature.

Roles:
  - identifier : row/entity IDs — never a metric, never a chart axis
  - metric     : numeric, meaningful magnitude — safe to sum/average
  - dimension  : low/medium-cardinality category — safe to group by
  - datetime   : parseable as a timestamp
  - text       : high-cardinality free text — not a group-by dimension
  - boolean    : true/false flag
"""

import re

import numpy as np
import pandas as pd


_ID_NAME_PATTERN = re.compile(r"(^id$|id$|_id$|^id_|uuid|guid)", re.IGNORECASE)


def _looks_like_datetime(sample: pd.Series) -> bool:
    import warnings

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(sample, errors="coerce")
        return parsed.notna().mean() > 0.85
    except Exception:
        return False


def _is_sequential_id(series: pd.Series) -> bool:
    """True for near-perfectly sequential integers (classic auto-increment ID)."""

    if len(series) < 5:
        return False

    sorted_vals = series.sort_values().reset_index(drop=True)
    diffs = sorted_vals.diff().dropna()

    if diffs.empty or diffs.iloc[0] == 0:
        return False

    # if the vast majority of consecutive gaps are identical -> sequential
    return bool((diffs == diffs.iloc[0]).mean() > 0.9)


def infer_column_role(df: pd.DataFrame, column: str) -> str:
    series = df[column].dropna()

    if series.empty:
        return "unknown"

    if pd.api.types.is_bool_dtype(df[column]):
        return "boolean"

    if pd.api.types.is_datetime64_any_dtype(df[column]):
        return "datetime"

    name = column.lower()
    id_name_match = bool(_ID_NAME_PATTERN.search(name))
    uniqueness_ratio = series.nunique() / len(series)

    if pd.api.types.is_numeric_dtype(df[column]):
        # a numeric column only counts as an identifier if BOTH the name
        # hints at it AND the values are mostly unique — this avoids
        # misclassifying a genuinely numeric metric that just happens to
        # have "id" somewhere unrelated, or a low-cardinality numeric code
        if id_name_match and uniqueness_ratio > 0.5:
            return "identifier"

        if uniqueness_ratio > 0.95 and _is_sequential_id(series):
            return "identifier"

        return "metric"

    # non-numeric (object/string) column
    if _looks_like_datetime(series):
        return "datetime"

    # same double-check for text columns: name pattern alone isn't enough —
    # "region_code" or "product_key" are legitimate low-cardinality
    # dimensions even though the name contains a common ID-ish token
    if id_name_match and uniqueness_ratio > 0.5:
        return "identifier"

    if uniqueness_ratio > 0.9:
        return "text"  # free text / high-cardinality — not a group-by dimension

    # cardinality alone misses "sentence-shaped" text with moderate
    # cardinality (e.g. notes/comments where phrasing repeats a bit) —
    # catch that by average word count / length, not just uniqueness
    sample = series.astype(str).head(200)
    avg_word_count = sample.str.split().str.len().mean()
    avg_char_length = sample.str.len().mean()

    if avg_word_count and avg_word_count > 5 or (avg_char_length and avg_char_length > 40):
        return "text"

    return "dimension"


def detect_column_roles(df: pd.DataFrame) -> dict:
    """Returns {role: [column names]} plus a flat column->role lookup."""

    roles = {
        "identifier": [],
        "metric": [],
        "dimension": [],
        "datetime": [],
        "text": [],
        "boolean": [],
        "unknown": [],
    }
    by_column = {}

    for column in df.columns:
        role = infer_column_role(df, column)
        roles[role].append(column)
        by_column[column] = role

    return {"by_role": roles, "by_column": by_column}


def schema_summary_for_prompt(df: pd.DataFrame, roles: dict | None = None) -> str:
    """Compact text block describing column roles, for LLM planner context."""

    roles = roles or detect_column_roles(df)
    by_role = roles["by_role"]

    lines = ["Column roles (use this to pick correct arguments — never use an"
             " identifier column as a metric or a chart axis):"]

    if by_role["metric"]:
        lines.append(f"  metrics (safe to sum/average/chart): {', '.join(by_role['metric'])}")
    if by_role["dimension"]:
        lines.append(f"  dimensions (safe to group by): {', '.join(by_role['dimension'])}")
    if by_role["datetime"]:
        lines.append(f"  datetime columns: {', '.join(by_role['datetime'])}")
    if by_role["identifier"]:
        lines.append(f"  identifiers (NEVER use as a metric or dimension): {', '.join(by_role['identifier'])}")
    if by_role["text"]:
        lines.append(f"  free text (not group-by friendly): {', '.join(by_role['text'])}")
    if by_role["boolean"]:
        lines.append(f"  boolean flags: {', '.join(by_role['boolean'])}")

    return "\n".join(lines)
