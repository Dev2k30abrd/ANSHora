"""
What-If Analysis — feature 5.

Evaluates a user-defined scenario (e.g. "what if Sales increased 10% in
the North region") against the ACTUAL baseline computed from real data,
then clearly labels which numbers are observed vs simulated. Never
mutates the underlying dataset.
"""

import pandas as pd


def simulate_scenario(
    df: pd.DataFrame,
    metric_column: str,
    adjustment_type: str,       # "percentage" | "absolute"
    adjustment_value: float,
    aggregation: str = "sum",   # "sum" | "mean"
    filter_column: str | None = None,
    filter_value=None,
) -> dict:
    if metric_column not in df.columns:
        raise ValueError(f"Metric column '{metric_column}' not found.")
    if not pd.api.types.is_numeric_dtype(df[metric_column]):
        raise ValueError(f"Metric column '{metric_column}' must be numeric.")
    if adjustment_type not in ("percentage", "absolute"):
        raise ValueError("adjustment_type must be 'percentage' or 'absolute'.")
    if aggregation not in ("sum", "mean"):
        raise ValueError("aggregation must be 'sum' or 'mean'.")

    working = df.copy()
    scope_description = "entire dataset"

    if filter_column:
        if filter_column not in working.columns:
            raise ValueError(f"Filter column '{filter_column}' not found.")
        working = working[working[filter_column].astype(str) == str(filter_value)]
        scope_description = f"rows where {filter_column} = '{filter_value}'"

        if working.empty:
            raise ValueError(
                f"No rows match {filter_column} = '{filter_value}' — cannot simulate on an empty scope."
            )

    baseline_scope_value = (
        working[metric_column].sum() if aggregation == "sum" else working[metric_column].mean()
    )
    baseline_overall_value = (
        df[metric_column].sum() if aggregation == "sum" else df[metric_column].mean()
    )

    if adjustment_type == "percentage":
        simulated_scope_value = baseline_scope_value * (1 + adjustment_value / 100)
        assumption_text = f"{scope_description}: {metric_column} changes by {adjustment_value:+.1f}%"
    else:
        simulated_scope_value = baseline_scope_value + adjustment_value
        assumption_text = f"{scope_description}: {metric_column} changes by {adjustment_value:+.2f} (absolute)"

    delta_in_scope = simulated_scope_value - baseline_scope_value

    # roll the scoped delta into the overall total (sum only — mean doesn't roll up meaningfully)
    simulated_overall_value = (
        baseline_overall_value + delta_in_scope if aggregation == "sum" else None
    )

    return {
        "is_simulation": True,
        "disclaimer": (
            "This is a hypothetical projection based on a user-defined assumption, "
            "not observed data. It should be treated as a what-if scenario only."
        ),
        "assumption": assumption_text,
        "metric": metric_column,
        "aggregation": aggregation,
        "scope": scope_description,
        "actual_baseline": {
            "scope_value": round(float(baseline_scope_value), 2),
            "overall_value": round(float(baseline_overall_value), 2),
        },
        "simulated_result": {
            "scope_value": round(float(simulated_scope_value), 2),
            "overall_value": round(float(simulated_overall_value), 2) if simulated_overall_value is not None else None,
            "delta_in_scope": round(float(delta_in_scope), 2),
            "delta_percentage_of_overall": (
                round(float(delta_in_scope / baseline_overall_value * 100), 2)
                if baseline_overall_value else None
            ),
        },
        "chart": {
            "type": "bar",
            "title": f"Actual vs Simulated — {metric_column} ({scope_description})",
            "labels": ["Actual", "Simulated"],
            "series": [{
                "name": metric_column,
                "data": [round(float(baseline_scope_value), 2), round(float(simulated_scope_value), 2)],
            }],
        },
    }
