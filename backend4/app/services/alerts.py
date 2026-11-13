"""
Smart Alerts — feature 9.

Two kinds of rules, evaluated deterministically against the current
dataframe:
  - threshold rules: user-defined "column {operator} value" checks
  - anomaly rules: automatic z-score based spike/drop detection

Each alert rule carries a `channels` field (currently only "in_app" is
actually delivered) so the schema is ready for email/Slack delivery
later without a breaking change — no fake buttons, just an honest
placeholder field the API already returns and accepts.
"""

import uuid
from datetime import datetime, timezone

import pandas as pd


_OPERATORS = {
    ">": lambda v, t: v > t,
    "<": lambda v, t: v < t,
    ">=": lambda v, t: v >= t,
    "<=": lambda v, t: v <= t,
    "==": lambda v, t: v == t,
    "!=": lambda v, t: v != t,
}


def create_rule(
    column: str,
    operator: str,
    threshold: float,
    aggregation: str = "mean",
    label: str | None = None,
    channels: list | None = None,
) -> dict:
    if operator not in _OPERATORS:
        raise ValueError(f"operator must be one of: {list(_OPERATORS.keys())}")
    if aggregation not in ("mean", "sum", "min", "max", "count"):
        raise ValueError("aggregation must be one of: mean, sum, min, max, count")

    return {
        "id": uuid.uuid4().hex[:10],
        "column": column,
        "operator": operator,
        "threshold": threshold,
        "aggregation": aggregation,
        "label": label or f"{aggregation}({column}) {operator} {threshold}",
        "channels": channels or ["in_app"],  # email/slack reserved for future use
        "created_at": datetime.now(timezone.utc).isoformat(),
        "enabled": True,
    }


def evaluate_threshold_rules(df: pd.DataFrame, rules: list) -> list:
    triggered = []

    for rule in rules:
        if not rule.get("enabled", True):
            continue
        if rule["column"] not in df.columns:
            continue

        series = df[rule["column"]].dropna()
        if series.empty:
            continue

        agg = rule.get("aggregation", "mean")
        current_value = float(getattr(series, agg)()) if agg != "count" else int(series.count())

        check = _OPERATORS[rule["operator"]]
        if check(current_value, rule["threshold"]):
            triggered.append({
                "rule_id": rule["id"],
                "type": "threshold",
                "label": rule["label"],
                "column": rule["column"],
                "current_value": round(current_value, 2) if isinstance(current_value, float) else current_value,
                "threshold": rule["threshold"],
                "operator": rule["operator"],
                "channels": rule.get("channels", ["in_app"]),
                "triggered_at": datetime.now(timezone.utc).isoformat(),
            })

    return triggered


def evaluate_anomaly_rules(df: pd.DataFrame, columns: list | None = None, z_threshold: float = 3.0) -> list:
    """Automatic anomaly monitoring — no rule setup required."""

    triggered = []
    numeric_cols = columns or df.select_dtypes(include="number").columns.tolist()

    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) < 5 or series.std() == 0:
            continue

        z_scores = (series - series.mean()) / series.std()
        extreme = series[z_scores.abs() > z_threshold]

        if len(extreme) == 0:
            continue

        triggered.append({
            "rule_id": f"auto-anomaly-{col}",
            "type": "anomaly",
            "label": f"Automatic anomaly monitor: {col}",
            "column": col,
            "outlier_count": int(len(extreme)),
            "sample_values": [float(v) for v in extreme.head(3).tolist()],
            "channels": ["in_app"],
            "triggered_at": datetime.now(timezone.utc).isoformat(),
        })

    return triggered


def evaluate_all(df: pd.DataFrame, rules: list) -> list:
    return evaluate_threshold_rules(df, rules) + evaluate_anomaly_rules(df)
