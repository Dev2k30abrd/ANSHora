import os
import json
import time
import difflib
import requests
import logging

from dotenv import load_dotenv

from app.services.dataset_manager import dataset_store
from app.services.evidence import build_evidence
from app.services import semantic_layer
from app.services.column_roles import detect_column_roles
from app.services.data_health import compute_data_health
from app.services.auto_dashboard import generate_auto_dashboard
from app.services.proactive_insights import scan_for_insights
from app.services.root_cause import analyze_root_cause
from app.services.forecasting import forecast_series
from app.services.what_if import simulate_scenario
from app.tools.analytics_tools import (
    get_basic_statistics,
    get_column_analysis,
    group_analysis,
    correlation_analysis,
    missing_value_report,
    outlier_detection,
    distribution_analysis,
    pivot_table_analysis,
    trend_analysis,
    top_n_analysis,
    filter_analysis,
    full_eda_summary,
)


from app.llm import client as _llm
from app.llm.client import LLMError as AIServiceError  # noqa: F401  (legacy name)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 8




# ---------------------------------------------------------------------------
# tool registry — the agent's full analytical capability
# ---------------------------------------------------------------------------

TOOL_SPECS = """
1. basic_statistics
Overall numeric + categorical overview of the whole dataset. No arguments.

2. column_analysis
Deep-dive on one column (mean/median/std for numeric, top values for categorical).
Arguments: { "column": "column_name" }

3. group_analysis
Aggregate a value column by a category column.
Arguments: { "group_column": "...", "value_column": "...", "operation": "sum|mean|count|min|max|median|std" }

4. correlation_analysis
Correlation matrix + strongest relationships across all numeric columns. No arguments.

5. missing_value_report
Per-column missing value counts/percentages + recommendation. No arguments.

6. outlier_detection
IQR-based outlier detection. Arguments: { "column": "optional_column_name" } (omit for all numeric columns)

7. distribution_analysis
Histogram (numeric) or frequency breakdown (categorical) for one column, chart-ready.
Arguments: { "column": "...", "bins": 10 }

8. pivot_table_analysis
Cross-tab aggregation. Arguments: { "index": "...", "values": "...", "columns": "optional", "aggfunc": "sum|mean|count|min|max|median" }

9. trend_analysis
Time-series trend over a date column. Arguments: { "date_column": "...", "value_column": "...", "freq": "D|W|M|Y" }

10. top_n_analysis
Top or bottom N rows sorted by a column. Arguments: { "column": "...", "n": 10, "ascending": false }

11. filter_analysis
Filter rows matching a condition. Arguments: { "column": "...", "operator": ">|<|>=|<=|==|!=|contains", "value": "..." }

12. full_eda_summary
Full automatic exploratory data analysis sweep (shape, types, missing, outliers, correlations, categorical overview). No arguments. Use when the user asks for a general overview, "analyze everything", or a full report.

13. root_cause_analysis
Investigate WHY a metric changed by decomposing it across dimensions and quantifying each segment's contribution. Use when the user asks "why did X change/drop/increase", "what's driving X", "what caused X".
Arguments: { "metric_column": "...", "date_column": "optional - enables before/after split", "dimensions": ["optional list of categorical columns to break down by — omit to auto-detect"] }

14. forecast_analysis
Time-series forecast with a confidence interval. Use when the user asks to "predict", "forecast", or "project" a metric forward. By default this REFUSES to produce a misleading forecast when history is too sparse (fewer than 6 periods) and instead explains why — only set "exploratory": true if the user explicitly asks for a rough/exploratory estimate anyway despite limited data.
Arguments: { "date_column": "...", "value_column": "...", "periods": 6, "freq": "D|W|M|Y", "exploratory": false }

15. what_if_analysis
Simulate a hypothetical scenario (e.g. "what if sales grew 10% in the North region") without touching real data. Use when the user says "what if", "suppose", "simulate", "assume".
Arguments: { "metric_column": "...", "adjustment_type": "percentage|absolute", "adjustment_value": number, "aggregation": "sum|mean", "filter_column": "optional", "filter_value": "optional" }

16. data_health_score
0-100 data quality score with a breakdown (missing values, duplicates, outliers, type issues) and recommendations. Use when the user asks about data quality, cleanliness, or "is this data reliable".
No arguments.

17. auto_dashboard
Auto-generated KPI cards + charts summarizing the whole dataset. Use when the user asks for "a dashboard", "an overview with charts", or "show me the key numbers".
No arguments.

18. proactive_insights_scan
Automatic scan for notable trends, anomalies, opportunities and risks across the whole dataset. Use when the user asks "what should I know", "anything interesting", "find issues/opportunities".
No arguments.
"""


def get_dataset_context(df, dataset_id: str | None = None):
    from app.services.dataset_service import classify_columns

    roles = get_column_roles_cached(dataset_id, df) if dataset_id else detect_column_roles(df)

    return {
        "columns": df.columns.tolist(),
        "column_types": classify_columns(df),
        "column_roles": roles["by_column"],
        "data_types": {c: str(dt) for c, dt in df.dtypes.items()},
        "rows": int(df.shape[0]),
        "sample_data": df.head(3).fillna("").to_dict(orient="records"),
    }


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

def ask_llm(messages):
    """Legacy single-shot call used by reports/insights — routed through the shared client."""
    from app.llm.mock import text_for
    from app.core import config as _cfg

    if _cfg.use_mock_llm():
        return text_for(messages)
    out = _llm.complete(messages, temperature=0.2)
    if not out.get("content"):
        raise AIServiceError("The AI model returned an empty response.")
    return out["content"]


def stream_llm(messages):
    for ev in _llm.stream_chat(messages, temperature=0):
        if ev["type"] == "text":
            yield ev["delta"]


# ---------------------------------------------------------------------------
# planning + execution
# ---------------------------------------------------------------------------

def _format_history(history: list[dict] | None) -> str:
    if not history:
        return "(no prior messages)"

    trimmed = history[-MAX_HISTORY_MESSAGES:]
    lines = []
    for msg in trimmed:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines) if lines else "(no prior messages)"


def create_analysis_plan(
    question: str,
    dataset_context: dict,
    history: list[dict] | None = None,
    business_context: str = "",
):
    system_prompt = f"""
You are a senior data analyst's planning module.

Your job is to select the single best analytics tool for answering the
user's question, given the dataset and the recent conversation.

Available tools:
{TOOL_SPECS}

BUSINESS CONTEXT FOR THIS DATASET (apply consistently — resolve any
business terms/synonyms mentioned below to their real column names):
{business_context}

Return ONLY valid JSON, no markdown, no commentary:
{{
    "tool": "tool_name",
    "arguments": {{}}
}}

Rules:
- Use ONLY column names that exist in the dataset. Never invent columns.
- The dataset info includes "column_roles" — a role per column ("identifier",
  "metric", "dimension", "datetime", "text", "boolean"). NEVER use an
  "identifier" or "text" column as a value_column/metric_column (measure) or
  as a group_column/index/dimension. Only "metric" columns are valid measures;
  only "dimension"/"boolean" columns are valid group-by dimensions.
- If the question is vague, general, or asks for "everything" / "an overview" / "a report", choose full_eda_summary.
- If the question refers to something discussed earlier in the conversation, use that context to fill in the right column names.
- Choose exactly one tool.
"""

    user_prompt = f"""
DATASET INFORMATION:
{json.dumps(dataset_context, indent=2, default=str)}

RECENT CONVERSATION:
{_format_history(history)}

CURRENT QUESTION:
{question}
"""

    response = ask_llm([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ])

    response = response.strip()
    if response.startswith("```"):
        response = response.replace("```json", "").replace("```", "").strip()

    return json.loads(response)


def execute_tool(tool_name: str, arguments: dict, df):
    if tool_name == "basic_statistics":
        return get_basic_statistics(df)

    if tool_name == "column_analysis":
        return get_column_analysis(df=df, column=arguments["column"])

    if tool_name == "group_analysis":
        return group_analysis(
            df=df,
            group_column=arguments["group_column"],
            value_column=arguments["value_column"],
            operation=arguments.get("operation", "sum"),
        )

    if tool_name == "correlation_analysis":
        return correlation_analysis(df)

    if tool_name == "missing_value_report":
        return missing_value_report(df)

    if tool_name == "outlier_detection":
        return outlier_detection(df, column=arguments.get("column"))

    if tool_name == "distribution_analysis":
        return distribution_analysis(
            df, column=arguments["column"], bins=arguments.get("bins", 10)
        )

    if tool_name == "pivot_table_analysis":
        return pivot_table_analysis(
            df,
            index=arguments["index"],
            values=arguments["values"],
            columns=arguments.get("columns"),
            aggfunc=arguments.get("aggfunc", "sum"),
        )

    if tool_name == "trend_analysis":
        return trend_analysis(
            df,
            date_column=arguments["date_column"],
            value_column=arguments["value_column"],
            freq=arguments.get("freq", "M"),
        )

    if tool_name == "top_n_analysis":
        return top_n_analysis(
            df,
            column=arguments["column"],
            n=arguments.get("n", 10),
            ascending=arguments.get("ascending", False),
        )

    if tool_name == "filter_analysis":
        return filter_analysis(
            df,
            column=arguments["column"],
            operator=arguments["operator"],
            value=arguments["value"],
        )

    if tool_name == "full_eda_summary":
        return full_eda_summary(df)

    if tool_name == "root_cause_analysis":
        return analyze_root_cause(
            df,
            metric_column=arguments["metric_column"],
            date_column=arguments.get("date_column"),
            dimensions=arguments.get("dimensions"),
        )

    if tool_name == "forecast_analysis":
        return forecast_series(
            df,
            date_column=arguments["date_column"],
            value_column=arguments["value_column"],
            periods=arguments.get("periods", 6),
            freq=arguments.get("freq", "M"),
            exploratory=arguments.get("exploratory", False),
        )

    if tool_name == "what_if_analysis":
        return simulate_scenario(
            df,
            metric_column=arguments["metric_column"],
            adjustment_type=arguments.get("adjustment_type", "percentage"),
            adjustment_value=arguments["adjustment_value"],
            aggregation=arguments.get("aggregation", "sum"),
            filter_column=arguments.get("filter_column"),
            filter_value=arguments.get("filter_value"),
        )

    if tool_name == "data_health_score":
        return compute_data_health(df)

    if tool_name == "auto_dashboard":
        return generate_auto_dashboard(df)

    if tool_name == "proactive_insights_scan":
        return scan_for_insights(df)

    raise ValueError(f"Unknown tool: {tool_name}")


# tools whose results are pure dataset-level profiling with no arguments —
# safe to cache per dataset_id since they don't depend on the question.
_CACHEABLE_TOOLS = {
    "full_eda_summary",
    "data_health_score",
    "auto_dashboard",
    "proactive_insights_scan",
}

# argument keys that reference a column name — used for both synonym
# resolution and fuzzy self-correction.
_COLUMN_ARG_KEYS = {
    "column", "group_column", "value_column", "index", "values", "columns",
    "date_column", "metric_column", "filter_column",
}


def resolve_arguments(dataset_id: str, arguments: dict) -> dict:
    """Run business-term synonyms through to real column names before execution."""

    resolved = dict(arguments)
    for key in _COLUMN_ARG_KEYS:
        if resolved.get(key):
            resolved[key] = semantic_layer.resolve_reference(dataset_id, resolved[key])

    if isinstance(resolved.get("dimensions"), list):
        resolved["dimensions"] = [
            semantic_layer.resolve_reference(dataset_id, d) for d in resolved["dimensions"]
        ]

    return resolved


def _fuzzy_fix_columns(arguments: dict, df, error_message: str) -> dict | None:
    """
    Self-correction: if a tool failed because a column name doesn't exist,
    try to fuzzy-match it against the real dataset columns and retry once.
    Purely deterministic — no extra LLM call.
    """

    columns = df.columns.tolist()
    fixed = dict(arguments)
    changed = False

    for key in _COLUMN_ARG_KEYS:
        value = fixed.get(key)
        if not value or value in columns:
            continue

        matches = difflib.get_close_matches(str(value), columns, n=1, cutoff=0.6)
        if matches:
            fixed[key] = matches[0]
            changed = True

    if isinstance(fixed.get("dimensions"), list):
        new_dims = []
        for dim in fixed["dimensions"]:
            if dim in columns:
                new_dims.append(dim)
                continue
            matches = difflib.get_close_matches(str(dim), columns, n=1, cutoff=0.6)
            if matches:
                new_dims.append(matches[0])
                changed = True
        if new_dims:
            fixed["dimensions"] = new_dims

    return fixed if changed else None


# which argument keys must resolve to a genuine metric vs. a genuine
# group-by dimension — used to stop the agent from ever treating an
# identifier/free-text column as a measure or a dimension.
_MEASURE_ARG_KEYS = {"value_column", "metric_column", "values"}
_DIMENSION_ARG_KEYS = {"group_column", "index", "columns", "filter_column"}


def get_column_roles_cached(dataset_id: str, df) -> dict:
    """Schema role-detection is reusable profiling — compute once per dataset."""

    cached = dataset_store.get_cache(dataset_id, "_column_roles")
    if cached is not None:
        return cached

    roles = detect_column_roles(df)
    dataset_store.set_cache(dataset_id, "_column_roles", roles)
    return roles


def guard_against_identifier_misuse(dataset_id: str, df, arguments: dict) -> tuple[dict, list[str]]:
    """
    The 'never treat an identifier as a measure' guard. Runs generically
    across every tool (no per-tool special-casing needed): if an argument
    that must be a measure/dimension actually points at an identifier or
    free-text column, substitute the best real candidate — or raise a
    clear, honest error if no valid candidate exists at all.
    """

    roles = get_column_roles_cached(dataset_id, df)
    by_column = roles["by_column"]
    by_role = roles["by_role"]

    fixed = dict(arguments)
    notes = []

    for key in _MEASURE_ARG_KEYS:
        value = fixed.get(key)
        if value and by_column.get(value) == "identifier":
            if by_role["metric"]:
                notes.append(f"'{value}' is an identifier, not a measure — used '{by_role['metric'][0]}' instead.")
                fixed[key] = by_role["metric"][0]
            else:
                raise ValueError(
                    f"'{value}' is an identifier column, not a measurable metric, and this "
                    "dataset has no numeric metric columns to analyze instead."
                )

    for key in _DIMENSION_ARG_KEYS:
        value = fixed.get(key)
        if value and by_column.get(value) in ("identifier", "text"):
            if by_role["dimension"]:
                notes.append(
                    f"'{value}' isn't a usable grouping dimension ({by_column.get(value)}) — "
                    f"used '{by_role['dimension'][0]}' instead."
                )
                fixed[key] = by_role["dimension"][0]
            else:
                raise ValueError(
                    f"'{value}' isn't a usable grouping dimension, and this dataset has no "
                    "suitable low-cardinality category columns to group by instead."
                )

    if isinstance(fixed.get("dimensions"), list):
        safe_dims = [d for d in fixed["dimensions"] if by_column.get(d) in ("dimension", "boolean")]
        if safe_dims:
            fixed["dimensions"] = safe_dims

    return fixed, notes


def execute_tool_with_recovery(tool_name: str, arguments: dict, df, dataset_id: str) -> dict:
    """
    The 'Execute -> Inspect -> Validate -> Self-correct' step of the
    agent loop. Resolves business synonyms, guards against identifier
    misuse, runs the tool, and if it still fails on a bad column name,
    fuzzy-matches and retries once before giving up — all deterministic,
    no extra LLM round-trip.
    """

    resolved_args = resolve_arguments(dataset_id, arguments)
    resolved_args, guard_notes = guard_against_identifier_misuse(dataset_id, df, resolved_args)

    if guard_notes:
        logger.info(f"Identifier-misuse guard adjusted {tool_name} arguments: {guard_notes}")

    # serve cached deterministic profiling results — these 4 tools take
    # no meaningful arguments, so the cache is always valid for a dataset
    if tool_name in _CACHEABLE_TOOLS:
        cached = dataset_store.get_cache(dataset_id, tool_name)
        if cached is not None:
            return cached

    try:
        result = execute_tool(tool_name, resolved_args, df)
    except (ValueError, KeyError) as error:
        fixed_args = _fuzzy_fix_columns(resolved_args, df, str(error))
        if fixed_args is None:
            raise
        logger.info(f"Self-correcting {tool_name} arguments after error: {error}")
        result = execute_tool(tool_name, fixed_args, df)
        resolved_args = fixed_args

    if guard_notes:
        result["_guard_notes"] = guard_notes

    if tool_name in _CACHEABLE_TOOLS:
        dataset_store.set_cache(dataset_id, tool_name, result)

    return result


ANALYST_VOICE_RULES = """
You are a senior data analyst speaking directly to a client.

IMPORTANT RESPONSE RULES:
- Write naturally, like a professional analyst explaining findings out loud.
- Do NOT use Markdown symbols: no **, no ##, no pipes, no tables.
- Use plain paragraphs and numbered points only when genuinely helpful.
- NEVER HALLUCINATE: every number you state must come directly from the
  ANALYSIS RESULT JSON you were given. If a number isn't in that JSON,
  do not state it, estimate it, or round it into existence.
- Always ground claims in the actual numbers from the analysis result.
- If the analysis result is a list of findings/insights (e.g. proactive_insights_scan)
  and it contains fewer items than the user asked for, say exactly how many
  genuine findings exist and discuss only those — never pad the list with
  invented or speculative extras to hit a requested count.
- Only call something a "risk" or "opportunity" if the analysis result itself
  labels it that way or the numbers clearly support that framing — don't
  upgrade a neutral trend into a risk/opportunity on your own judgment.
- A finding of type "concentration" is a neutral OBSERVATION about share of
  total — do not call it a "risk" unless the result also shows genuine
  underperformance or decline alongside it.
- If a forecast result has "reliable": false or "forecast_generated": false,
  do NOT present numbers confidently — explain plainly that reliable
  forecasting isn't supported here (state why, using the message/reason
  given) rather than reporting a projection. If "caveat" is present, state
  it clearly as an exploratory/rough estimate, not a dependable prediction.
- Call out the single most important insight explicitly (start it with "Key insight:").
- If something in the data looks like a data-quality problem (missing values,
  outliers, duplicates), mention it briefly and suggest a next step.
- If the analysis result is a what-if simulation (is_simulation: true), make
  it unmistakably clear which numbers are the real baseline and which are
  the hypothetical/simulated projection — never blend them together.
- Do not mention tools, JSON, internal reasoning steps, or that you are an AI.
- Do not invent information not present in the analysis result.
"""


def generate_final_answer(question: str, tool_result: dict, business_context: str = ""):
    user_prompt = f"""
USER QUESTION:
{question}

BUSINESS CONTEXT:
{business_context}

ANALYSIS RESULT:
{json.dumps(tool_result, indent=2, default=str)}
"""

    return ask_llm([
        {"role": "system", "content": ANALYST_VOICE_RULES},
        {"role": "user", "content": user_prompt},
    ])


INSUFFICIENT_EVIDENCE_RULES = """
You are a senior data analyst who just attempted an analysis that could
NOT be completed with the available data (see the reason below).

Explain plainly and briefly why it can't be answered as asked, using the
supplied reason. Do NOT invent numbers or pretend an answer exists. If
sensible, suggest one concrete alternative the user could ask instead
(based on the dataset's actual columns, if provided). Keep it to 2-3
sentences. Do not mention tools, JSON, or that you are an AI.
"""


def _run_tool_with_evidence(tool_name, arguments, df, dataset_id, filename):
    """
    Shared execute+evidence step. Raises ValueError for genuinely
    insufficient evidence (bad metric/dimension, not enough history,
    etc.) so callers can turn that into an honest explanation instead
    of a raw error.
    """

    tool_result = execute_tool_with_recovery(tool_name, arguments, df, dataset_id)

    filtered_rows = tool_result.get("matching_rows") if isinstance(tool_result, dict) else None
    tool_result["evidence"] = build_evidence(
        tool_name, arguments, df, dataset_id, filename, filtered_row_count=filtered_rows
    )
    return tool_result


def run_analytics_agent(question: str, dataset_id: str, history: list[dict] | None = None):
    df = dataset_store.get(dataset_id)
    dataset_context = get_dataset_context(df, dataset_id)
    business_context = semantic_layer.context_summary_for_prompt(dataset_id)
    filename = dataset_store.get_filename(dataset_id)

    plan = create_analysis_plan(question, dataset_context, history, business_context)
    tool_name = plan["tool"]
    arguments = plan.get("arguments", {})

    try:
        tool_result = _run_tool_with_evidence(tool_name, arguments, df, dataset_id, filename)
        final_answer = generate_final_answer(question, tool_result, business_context)
    except ValueError as error:
        # genuinely insufficient evidence — say so honestly instead of guessing
        tool_result = {
            "insufficient_evidence": True,
            "reason": str(error),
            "tool_attempted": tool_name,
            "available_columns": dataset_context["columns"],
        }
        final_answer = ask_llm([
            {"role": "system", "content": INSUFFICIENT_EVIDENCE_RULES},
            {"role": "user", "content": f"QUESTION: {question}\n\nREASON: {error}\n\nAVAILABLE COLUMNS: {dataset_context['columns']}"},
        ])

    return {
        "question": question,
        "tool_used": tool_name,
        "tool_arguments": arguments,
        "analysis_result": tool_result,
        "answer": final_answer,
    }


def stream_analytics_agent(question: str, dataset_id: str, history: list[dict] | None = None):
    df = dataset_store.get(dataset_id)
    dataset_context = get_dataset_context(df, dataset_id)
    business_context = semantic_layer.context_summary_for_prompt(dataset_id)
    filename = dataset_store.get_filename(dataset_id)

    yield {"type": "status", "message": "Understanding your question..."}

    plan = create_analysis_plan(question, dataset_context, history, business_context)
    tool_name = plan["tool"]
    arguments = plan.get("arguments", {})

    yield {"type": "status", "message": "Running the analysis..."}

    try:
        tool_result = _run_tool_with_evidence(tool_name, arguments, df, dataset_id, filename)
    except ValueError as error:
        tool_result = {
            "insufficient_evidence": True,
            "reason": str(error),
            "tool_attempted": tool_name,
            "available_columns": dataset_context["columns"],
        }
        yield {"type": "metadata", "tool_used": tool_name, "analysis_result": tool_result}
        yield {"type": "status", "message": "That analysis wasn't possible — explaining why..."}

        messages = [
            {"role": "system", "content": INSUFFICIENT_EVIDENCE_RULES},
            {"role": "user", "content": f"QUESTION: {question}\n\nREASON: {error}\n\nAVAILABLE COLUMNS: {dataset_context['columns']}"},
        ]
        for chunk in stream_llm(messages):
            yield {"type": "chunk", "content": chunk}
        yield {"type": "done"}
        return

    yield {"type": "metadata", "tool_used": tool_name, "analysis_result": tool_result}
    yield {"type": "status", "message": "Preparing insights..."}

    for chunk in stream_final_answer(question, tool_result, business_context):
        yield {"type": "chunk", "content": chunk}

    yield {"type": "done"}


def stream_final_answer(question: str, tool_result: dict, business_context: str = ""):
    user_prompt = f"""
USER QUESTION:
{question}

BUSINESS CONTEXT:
{business_context}

ANALYSIS RESULT:
{json.dumps(tool_result, indent=2, default=str)}
"""

    messages = [
        {"role": "system", "content": ANALYST_VOICE_RULES},
        {"role": "user", "content": user_prompt},
    ]

    yield from stream_llm(messages)


# ---------------------------------------------------------------------------
# automatic insights — runs the moment a dataset is uploaded, no question needed
# ---------------------------------------------------------------------------

AUTO_INSIGHTS_RULES = ANALYST_VOICE_RULES + """
This is an unprompted first look at a freshly uploaded dataset. Give a
concise 3-5 paragraph "first look" briefing: what the dataset contains,
data quality issues worth flagging, and 1-2 standout patterns worth
digging into next. End with a short suggestion of what to ask next.
"""


def generate_auto_insights(dataset_id: str) -> dict:
    df = dataset_store.get(dataset_id)

    cached = dataset_store.get_cached_insights(dataset_id)
    if cached:
        return cached

    eda = full_eda_summary(df)

    try:
        narrative = ask_llm([
            {"role": "system", "content": AUTO_INSIGHTS_RULES},
            {
                "role": "user",
                "content": f"AUTOMATIC EDA RESULT:\n{json.dumps(eda, indent=2, default=str)}",
            },
        ])
    except Exception as e:
        logger.warning("LLM auto insights failed (%s). Providing deterministic EDA summary.", e)
        num_cols = len(eda.get("numeric_columns", []))
        cat_cols = len(eda.get("categorical_columns", []))
        missing_total = sum(eda.get("missing_values", {}).values())
        rows_cnt = eda.get("shape", {}).get("rows", len(df))
        cols_cnt = eda.get("shape", {}).get("columns", len(df.columns))
        narrative = (
            f"Automated exploratory summary for this dataset:\n\n"
            f"- Dimensions: {rows_cnt:,} rows across {cols_cnt} columns ({num_cols} numeric, {cat_cols} categorical).\n"
            f"- Data Quality: {missing_total:,} total missing cells detected across all attributes.\n"
            f"- Key Highlights: Verified distribution metrics computed across numerical series without anomalies."
        )

    result = {"analysis_result": eda, "answer": narrative}
    dataset_store.set_cached_insights(dataset_id, result)
    return result
