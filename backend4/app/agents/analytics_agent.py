import os
import json
import time
import requests
import logging

from dotenv import load_dotenv

from app.services.dataset_manager import dataset_store
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


load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL")
OPENROUTER_FALLBACK_MODEL = os.getenv("OPENROUTER_FALLBACK_MODEL")

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 8


class AIServiceError(Exception):
    """Raised when the LLM backend is unreachable or returns a bad response."""


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
"""


def get_dataset_context(df):
    from app.services.dataset_service import classify_columns

    return {
        "columns": df.columns.tolist(),
        "column_types": classify_columns(df),
        "data_types": {c: str(dt) for c, dt in df.dtypes.items()},
        "rows": int(df.shape[0]),
        "sample_data": df.head(3).fillna("").to_dict(orient="records"),
    }


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------

def ask_llm(messages):
    if not OPENROUTER_API_KEY:
        raise AIServiceError("OPENROUTER_API_KEY is not configured.")
    if not OPENROUTER_MODEL:
        raise AIServiceError("OPENROUTER_MODEL is not configured.")

    models = [OPENROUTER_MODEL]
    if OPENROUTER_FALLBACK_MODEL:
        models.append(OPENROUTER_FALLBACK_MODEL)

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "models": models,
        "messages": messages,
        "temperature": 0.2,
        "provider": {"allow_fallbacks": True},
    }

    max_retries = 3
    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=90)

            if not response.ok:
                try:
                    error_data = response.json()
                    error_message = error_data.get("error", {}).get("message", response.text)
                except Exception:
                    error_message = response.text

                last_error = f"OpenRouter error {response.status_code}: {error_message}"

                if response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue

                raise AIServiceError(last_error)

            data = response.json()
            choices = data.get("choices", [])

            if not choices:
                last_error = "OpenRouter returned an empty choices response."
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise AIServiceError(last_error)

            content = choices[0].get("message", {}).get("content")

            if not content:
                last_error = "The AI model returned an empty response."
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise AIServiceError(last_error)

            return content.strip()

        except requests.exceptions.Timeout:
            last_error = "AI request timed out."
        except requests.exceptions.RequestException as error:
            last_error = f"Network error: {str(error)}"
        except AIServiceError:
            raise
        except Exception as error:
            last_error = str(error)

        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)

    raise AIServiceError(f"AI service is temporarily unavailable. Last error: {last_error}")


def stream_llm(messages):
    if not OPENROUTER_API_KEY:
        raise AIServiceError("OPENROUTER_API_KEY is not configured.")
    if not OPENROUTER_MODEL:
        raise AIServiceError("OPENROUTER_MODEL is not configured.")

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": messages,
        "temperature": 0,
        "stream": True,
    }

    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=120, stream=True)
    response.raise_for_status()

    for line in response.iter_lines():
        if not line:
            continue

        decoded_line = line.decode("utf-8")
        if not decoded_line.startswith("data: "):
            continue

        data_string = decoded_line[6:]
        if data_string == "[DONE]":
            break

        try:
            data = json.loads(data_string)
            choices = data.get("choices", [])
            if not choices:
                continue
            content = choices[0].get("delta", {}).get("content", "")
            if content:
                yield content
        except json.JSONDecodeError:
            continue


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


def create_analysis_plan(question: str, dataset_context: dict, history: list[dict] | None = None):
    system_prompt = f"""
You are a senior data analyst's planning module.

Your job is to select the single best analytics tool for answering the
user's question, given the dataset and the recent conversation.

Available tools:
{TOOL_SPECS}

Return ONLY valid JSON, no markdown, no commentary:
{{
    "tool": "tool_name",
    "arguments": {{}}
}}

Rules:
- Use ONLY column names that exist in the dataset. Never invent columns.
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

    raise ValueError(f"Unknown tool: {tool_name}")


ANALYST_VOICE_RULES = """
You are a senior data analyst speaking directly to a client.

IMPORTANT RESPONSE RULES:
- Write naturally, like a professional analyst explaining findings out loud.
- Do NOT use Markdown symbols: no **, no ##, no pipes, no tables.
- Use plain paragraphs and numbered points only when genuinely helpful.
- Always ground claims in the actual numbers from the analysis result.
- Call out the single most important insight explicitly (start it with "Key insight:").
- If something in the data looks like a data-quality problem (missing values,
  outliers, duplicates), mention it briefly and suggest a next step.
- Do not mention tools, JSON, or that you are an AI.
- Do not invent information not present in the analysis result.
"""


def generate_final_answer(question: str, tool_result: dict):
    user_prompt = f"""
USER QUESTION:
{question}

ANALYSIS RESULT:
{json.dumps(tool_result, indent=2, default=str)}
"""

    return ask_llm([
        {"role": "system", "content": ANALYST_VOICE_RULES},
        {"role": "user", "content": user_prompt},
    ])


def run_analytics_agent(question: str, dataset_id: str, history: list[dict] | None = None):
    df = dataset_store.get(dataset_id)
    dataset_context = get_dataset_context(df)

    plan = create_analysis_plan(question, dataset_context, history)
    tool_name = plan["tool"]
    arguments = plan.get("arguments", {})

    tool_result = execute_tool(tool_name, arguments, df)
    final_answer = generate_final_answer(question, tool_result)

    return {
        "question": question,
        "tool_used": tool_name,
        "tool_arguments": arguments,
        "analysis_result": tool_result,
        "answer": final_answer,
    }


def stream_analytics_agent(question: str, dataset_id: str, history: list[dict] | None = None):
    df = dataset_store.get(dataset_id)
    dataset_context = get_dataset_context(df)

    yield {"type": "status", "message": "Analyzing your data..."}

    plan = create_analysis_plan(question, dataset_context, history)
    tool_name = plan["tool"]
    arguments = plan.get("arguments", {})

    yield {"type": "status", "message": "Exploring the data..."}

    tool_result = execute_tool(tool_name, arguments, df)

    yield {"type": "metadata", "tool_used": tool_name, "analysis_result": tool_result}
    yield {"type": "status", "message": "Preparing insights..."}

    for chunk in stream_final_answer(question, tool_result):
        yield {"type": "chunk", "content": chunk}

    yield {"type": "done"}


def stream_final_answer(question: str, tool_result: dict):
    user_prompt = f"""
USER QUESTION:
{question}

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

    narrative = ask_llm([
        {"role": "system", "content": AUTO_INSIGHTS_RULES},
        {
            "role": "user",
            "content": f"AUTOMATIC EDA RESULT:\n{json.dumps(eda, indent=2, default=str)}",
        },
    ])

    result = {"analysis_result": eda, "answer": narrative}
    dataset_store.set_cached_insights(dataset_id, result)
    return result
