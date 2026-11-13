"""
Tool registry: one place that defines every tool as a native function-calling
schema (JSON Schema) AND how to run it. Existing 18 analytics tools are reused;
four new ones (profit impact, sensitivity, SQL, python) are added.
"""
import json
import time

from app.core import db
from app.core.config import ENABLE_PYTHON_SANDBOX
from app.core.context import current_workspace
from app.services.dataset_manager import dataset_store
from app.services.evidence import build_evidence

S = lambda **kw: {"type": "string", **kw}  # noqa: E731
N = lambda **kw: {"type": "number", **kw}  # noqa: E731
B = lambda **kw: {"type": "boolean", **kw}  # noqa: E731


def _t(name, description, props=None, required=None):
    return {
        "name": name,
        "description": description,
        "parameters": {"type": "object", "properties": props or {}, "required": required or []},
    }


TOOLS = [
    _t("profit_impact_analysis",
       "BEST FIRST CHOICE for 'where am I losing money', profit, margin, leakage, discounts, churn loss, what "
       "to fix first. Detects revenue/cost/profit, ranks findings by money at stake (segment losses, margin "
       "gaps, discount/returns leakage, churn, period decline)."),
    _t("sensitivity_analysis",
       "Profit grid for price x volume (and cost) changes; break-even price move. Use for pricing / 'what if "
       "price/volume/cost changes' questions.",
       {"price_changes": {"type": "array", "items": N(), "description": "price changes in %, e.g. [-10,-5,0,5,10]"},
        "volume_changes": {"type": "array", "items": N(), "description": "volume changes in %"},
        "cost_change_pct": N(description="unit cost change in %"),
        "elasticity": N(description="optional price elasticity of demand, e.g. -1.2"),
        "variable_cost_share": N(description="0-1 share of cost that scales with volume (default 1)")}),
    _t("sql_query",
       "Run ONE read-only DuckDB SELECT on the dataset. Table is named `data`. Use for custom aggregations, "
       "joins-with-self, window functions, ranking, filters the other tools cannot express.",
       {"query": S(description="a single SELECT/WITH statement over table `data`")}, ["query"]),
    _t("basic_statistics", "Overall numeric + categorical overview of the dataset."),
    _t("column_analysis", "Deep-dive on one column (stats for numeric, top values for categorical).",
       {"column": S()}, ["column"]),
    _t("group_analysis", "Aggregate a value column by a category column.",
       {"group_column": S(), "value_column": S(),
        "operation": S(enum=["sum", "mean", "count", "min", "max", "median", "std"])},
       ["group_column", "value_column"]),
    _t("correlation_analysis", "Correlation matrix and strongest relationships across numeric columns."),
    _t("missing_value_report", "Per-column missing value counts/percentages."),
    _t("outlier_detection", "IQR outlier detection (one column, or all numeric if omitted).", {"column": S()}),
    _t("distribution_analysis", "Histogram (numeric) or frequency breakdown (categorical) for one column.",
       {"column": S(), "bins": N()}, ["column"]),
    _t("pivot_table_analysis", "Cross-tab aggregation.",
       {"index": S(), "values": S(), "columns": S(),
        "aggfunc": S(enum=["sum", "mean", "count", "min", "max", "median"])}, ["index", "values"]),
    _t("trend_analysis", "Time-series trend of a value over a date column.",
       {"date_column": S(), "value_column": S(), "freq": S(enum=["D", "W", "M", "Y"])},
       ["date_column", "value_column"]),
    _t("top_n_analysis", "Top or bottom N rows sorted by a column.",
       {"column": S(), "n": N(), "ascending": B()}, ["column"]),
    _t("filter_analysis", "Filter rows matching one condition.",
       {"column": S(), "operator": S(enum=[">", "<", ">=", "<=", "==", "!=", "contains"]), "value": S()},
       ["column", "operator", "value"]),
    _t("full_eda_summary", "Full exploratory data analysis sweep. Use for 'analyze everything'."),
    _t("root_cause_analysis", "WHY did a metric change? Decomposes by dimensions and quantifies each segment.",
       {"metric_column": S(), "date_column": S(), "dimensions": {"type": "array", "items": S()}},
       ["metric_column"]),
    _t("forecast_analysis", "Forecast a metric with confidence interval. Refuses on sparse history.",
       {"date_column": S(), "value_column": S(), "periods": N(),
        "freq": S(enum=["D", "W", "M", "Y"]), "exploratory": B()}, ["date_column", "value_column"]),
    _t("what_if_analysis", "Simulate a single-metric scenario (e.g. sales +10% in one region).",
       {"metric_column": S(), "adjustment_type": S(enum=["percentage", "absolute"]), "adjustment_value": N(),
        "aggregation": S(enum=["sum", "mean"]), "filter_column": S(), "filter_value": S()},
       ["metric_column", "adjustment_value"]),
    _t("data_health_score", "0-100 data quality score with breakdown."),
    _t("auto_dashboard", "Auto KPI cards + charts for the whole dataset."),
    _t("proactive_insights_scan", "Scan for notable trends, anomalies, opportunities and risks."),
    _t("prepare_email_delivery",
       "Prepares an executive or analytical report email with attachments and generates a secure preview token for explicit user confirmation. Does NOT send the email automatically.",
       {"recipient": S(description="Recipient email address(es), comma-separated if multiple"),
        "report_type": S(enum=["executive", "profit", "data_health", "dashboard"], description="Type of report"),
        "format": S(enum=["pdf", "csv", "both", "inline"], description="Attachment format"),
        "subject": S(description="Optional custom subject line"),
        "custom_notes": S(description="Optional custom executive notes to include in email body")},
       ["recipient"]),
]

if ENABLE_PYTHON_SANDBOX:
    TOOLS.append(_t(
        "python_analysis",
        "LAST RESORT for analysis no other tool can do. Write pandas code on DataFrame `df` (pd, np, math, "
        "statistics available; no file/network access). Put the answer in variable `result`; optionally "
        "`chart = {'type':'bar|line','title':..,'x':[..],'y':[..]}`.",
        {"code": S(description="python code; must set `result`")}, ["code"]))

TOOL_NAMES = {t["name"] for t in TOOLS}


def openai_tools() -> list[dict]:
    return [{"type": "function", "function": t} for t in TOOLS]


def tool_catalog_text() -> str:
    lines = []
    for t in TOOLS:
        props = t["parameters"]["properties"]
        args = ", ".join(f'{k}{"*" if k in t["parameters"]["required"] else ""}' for k in props) or "none"
        lines.append(f"- {t['name']}({args}): {t['description']}")
    return "\n".join(lines)


def _workspace_currency(dataset_id) -> str:
    from app.core.config import DEFAULT_CURRENCY

    ws = current_workspace.get()
    row = db.one("SELECT currency FROM workspaces WHERE id=?", (ws,)) if ws else None
    meta = db.one("SELECT project_id FROM datasets WHERE id=?", (dataset_id,))
    if meta and meta.get("project_id"):
        p = db.one("SELECT currency FROM projects WHERE id=?", (meta["project_id"],))
        if p and p.get("currency"):
            return p["currency"]
    return (row or {}).get("currency") or DEFAULT_CURRENCY


def run_tool(name: str, arguments: dict, dataset_id: str) -> dict:
    """Execute any registered tool. Raises ValueError with an honest message on failure."""
    if name not in TOOL_NAMES:
        raise ValueError(f"Unknown tool '{name}'. Available: {', '.join(sorted(TOOL_NAMES))}")
    arguments = arguments or {}
    df = dataset_store.get(dataset_id)
    filename = dataset_store.get_filename(dataset_id)
    ctx = dataset_store.get_business_context(dataset_id)
    pack_id = dataset_store.get_pack_id(dataset_id)

    if name == "profit_impact_analysis":
        from app.services.profit_service import run_profit

        result = run_profit(dataset_id)
    elif name == "sensitivity_analysis":
        from app.services.profit_service import run_sensitivity

        result = run_sensitivity(
            dataset_id,
            price_changes=arguments.get("price_changes"), volume_changes=arguments.get("volume_changes"),
            cost_change_pct=float(arguments.get("cost_change_pct") or 0),
            elasticity=arguments.get("elasticity"),
            variable_cost_share=float(arguments.get("variable_cost_share", 1.0)))
    elif name == "sql_query":
        from app.tools.sql_tool import run_sql

        result = run_sql(df, arguments.get("query", ""))
    elif name == "python_analysis":
        from app.tools.python_sandbox import run_python

        result = run_python(df, arguments.get("code", ""))
    elif name == "prepare_email_delivery":
        from app.services import gmail_service

        ws = current_workspace.get() or "ws_default"
        result = gmail_service.prepare_email_preview(
            dataset_id=dataset_id,
            recipient=arguments.get("recipient", ""),
            report_type=arguments.get("report_type", "executive"),
            format_type=arguments.get("format", "pdf"),
            custom_notes=arguments.get("custom_notes", ""),
            workspace_id=ws,
            subject=arguments.get("subject"),
            action_id=arguments.get("action_id"),
        )
    else:
        from app.agents.analytics_agent import execute_tool_with_recovery

        # data-quality tools must see the data exactly as uploaded (duplicates included)
        use_df = dataset_store.get_raw(dataset_id) if name in ("data_health_score", "missing_value_report") else df
        result = dict(execute_tool_with_recovery(name, arguments, use_df, dataset_id))

    filtered = result.get("matching_rows") if isinstance(result, dict) else None
    result["evidence"] = build_evidence(name, arguments, df, dataset_id, filename, filtered_row_count=filtered)
    return result


def compact_for_llm(result: dict, limit: int = 9000) -> str:
    """Shrink a tool result for the model context: drop bulky chart payloads first."""
    slim = {k: v for k, v in result.items() if k not in ("charts",)}
    s = json.dumps(slim, default=str)
    if len(s) <= limit:
        return s
    slim.pop("evidence", None)
    for key in sorted(slim, key=lambda k: -len(json.dumps(slim[k], default=str))):
        if len(json.dumps(slim, default=str)) <= limit:
            break
        v = slim[key]
        if isinstance(v, list) and len(v) > 8:
            slim[key] = v[:8] + [f"... {len(v) - 8} more omitted"]
        elif isinstance(v, dict) and len(json.dumps(v, default=str)) > limit // 2:
            slim[key] = "(omitted: too large)"
    s = json.dumps(slim, default=str)
    return s[:limit]


def timed_run(name, arguments, dataset_id):
    t0 = time.time()
    try:
        return True, run_tool(name, arguments, dataset_id), int((time.time() - t0) * 1000)
    except Exception as e:  # noqa: BLE001
        return False, {"error": str(e)}, int((time.time() - t0) * 1000)
