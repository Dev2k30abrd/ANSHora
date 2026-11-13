"""
Evidence / explainability layer.

Every analytical answer must be traceable back to: which dataset, which
columns, which filters, and what calculation produced the number. This
module builds that evidence block generically from the tool name +
arguments, so the 12 existing analytics tools don't need to be modified.

IMPORTANT: this only ever describes *what* was computed (dataset, columns,
filters, operation) — never the model's reasoning/chain-of-thought.
"""

from datetime import datetime, timezone


_CALC_TEMPLATES = {
    "basic_statistics": "Descriptive statistics (mean, median, std, min, max) computed over all numeric columns.",
    "column_analysis": "Column-level profiling: summary statistics for numeric columns, or frequency breakdown for categorical columns.",
    "group_analysis": "Grouped {operation} of '{value_column}' by '{group_column}'.",
    "correlation_analysis": "Pearson correlation coefficients across all numeric column pairs.",
    "missing_value_report": "Per-column null/NaN count and percentage across the full dataset.",
    "outlier_detection": "IQR method (values beyond 1.5x the interquartile range flagged as outliers).",
    "distribution_analysis": "Frequency/histogram distribution of '{column}'.",
    "pivot_table_analysis": "Pivot table: '{values}' aggregated by '{index}'{columns_part}, using {aggfunc}.",
    "trend_analysis": "Time-series resample of '{value_column}' over '{date_column}' at {freq} frequency, with trend direction from first-half vs second-half average.",
    "top_n_analysis": "Top {n} rows sorted by '{column}' ({order}).",
    "filter_analysis": "Rows filtered where '{column}' {operator} {value}.",
    "full_eda_summary": "Automated exploratory sweep: shape, column types, missing values, outliers, and top correlations.",
    "root_cause_analysis": "Segment-level decomposition of '{metric_column}' by '{dimensions}' to quantify each segment's contribution to the observed change.",
    "forecast_analysis": "Linear-trend + residual-based forecast of '{value_column}' over '{date_column}', {periods} periods ahead at {freq} frequency.",
    "what_if_analysis": "Simulated scenario recomputation of '{metric_column}' under user-defined assumptions — NOT observed data.",
    "data_health_score": "Composite 0-100 quality score from missing values, duplicates, outliers, and type-consistency checks.",
    "auto_dashboard": "Automatically generated KPI cards and charts from numeric/categorical/datetime column profiling.",
    "profit_impact_analysis": "Profit Impact Engine: revenue/cost/profit detected from columns, segment losses, margin gaps, discount/return/churn leakage and period decline ranked by money at stake.",
    "sensitivity_analysis": "Profit grid over price x volume changes from baseline revenue and cost totals (assumptions stated in result) — a SIMULATION, not observed data.",
    "sql_query": "Read-only SQL (DuckDB) executed on the dataset: {sql}",
    "python_analysis": "Custom pandas analysis executed in an isolated sandbox on the dataset.",
    "proactive_insights_scan": "Automated scan for statistically notable trends, anomalies, concentration risk, and opportunities.",
}


def _columns_for(tool_name: str, arguments: dict) -> list:
    keys_by_tool = {
        "column_analysis": ["column"],
        "group_analysis": ["group_column", "value_column"],
        "distribution_analysis": ["column"],
        "pivot_table_analysis": ["index", "values", "columns"],
        "trend_analysis": ["date_column", "value_column"],
        "top_n_analysis": ["column"],
        "filter_analysis": ["column"],
        "root_cause_analysis": ["metric_column", "date_column", "dimensions"],
        "forecast_analysis": ["date_column", "value_column"],
        "what_if_analysis": ["metric_column", "filter_column"],
    }

    cols = []
    for key in keys_by_tool.get(tool_name, []):
        value = arguments.get(key)
        if isinstance(value, list):
            cols.extend([v for v in value if v])
        elif value:
            cols.append(value)

    return list(dict.fromkeys(cols))  # dedupe, preserve order


def _calculation_description(tool_name: str, arguments: dict) -> str:
    template = _CALC_TEMPLATES.get(tool_name, f"Computed via '{tool_name}'.")

    safe_args = dict(arguments)
    safe_args.setdefault("columns_part", "")
    if tool_name == "pivot_table_analysis" and arguments.get("columns"):
        safe_args["columns_part"] = f" split by '{arguments['columns']}'"

    if isinstance(safe_args.get("dimensions"), list):
        safe_args["dimensions"] = ", ".join(str(d) for d in safe_args["dimensions"])

    try:
        return template.format(**safe_args)
    except (KeyError, IndexError):
        return template


def build_evidence(
    tool_name: str,
    arguments: dict,
    df,
    dataset_id: str,
    filename: str,
    filtered_row_count: int | None = None,
) -> dict:
    return {
        "dataset_id": dataset_id,
        "dataset_filename": filename,
        "rows_analyzed": int(filtered_row_count) if filtered_row_count is not None else int(len(df)),
        "total_rows_in_dataset": int(len(df)),
        "columns_used": _columns_for(tool_name, arguments or {}),
        "calculation": _calculation_description(tool_name, arguments or {}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
