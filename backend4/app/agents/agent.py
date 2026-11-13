"""
The Anshora agent loop.

question -> [think -> call tool(s) -> read results]* -> grounded answer
          -> claim verification (+ one auto-correction) -> confidence -> follow-ups

Native function calling when the model supports it, JSON-action protocol
otherwise. Everything is emitted as a stream of events for the UI.
"""
import contextvars
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from app.agents import tools_registry as reg
from app.core import config as cfg
from app.core.context import current_workspace
from app.core.jsonutil import jsonable
from app.llm import client as llm
from app.llm.jsonfix import extract_json
from app.packs import get_pack
from app.services.dataset_manager import dataset_store
from app.services.email_agent_service import handle_conversational_email, is_email_intent
from app.services.facts import build_facts, question_hints
from app.services.verifier import confidence_score, unsupported_claims, verify_answer

logger = logging.getLogger("anshora.agent")

MAX_HISTORY = 10

ARTIFACT_KIND = {
    "profit_impact_analysis": "profit_impact", "sensitivity_analysis": "sensitivity",
    "auto_dashboard": "dashboard", "sql_query": "table", "python_analysis": "table",
    "prepare_email_delivery": "email_preview",
}

SYSTEM_PROMPT = """You are Anshora, a senior data analyst for business teams. You work for companies whose \
profit and loss depend on their data, so you always connect findings to MONEY and ACTIONS.

HOW YOU WORK
- Use the tools to compute everything. Never guess, estimate or recall numbers. Call as many tools as \
needed, one after another, and read each result before deciding the next step.
- Money questions (losses, margin, discounts, churn, "what should we fix") -> profit_impact_analysis first.
- Custom slicing the fixed tools cannot do -> sql_query (table `data`). python_analysis is a last resort.
- Pricing / what-if on price, volume, cost -> sensitivity_analysis.
- Email delivery requests (send report, email summary, forward analysis) -> prepare_email_delivery to generate a secure preview.
- Multi-step business analysis (e.g. "Why did profitability decline, which products caused it, what changed, \
and what should management do?"):
  1. Analyze overall business performance and margins (facts sheet / profit_impact_analysis).
  2. Isolate affected segments or products (group_analysis / profit_impact_analysis).
  3. Compare periods to pinpoint timing (trend_analysis / root_cause_analysis).
  4. Quantify root causes and drivers.
  5. Synthesize verified metrics into a coherent action plan with risks and expected outcomes.
- For simple questions (e.g. "Total revenue?", "How many rows?"): answer directly from the facts sheet or \
use a single targeted tool. Do not generate unnecessary multi-tool plans.
- If a tool errors, read the message, fix the arguments (real column names) and retry once. If the data \
cannot answer the question, say so plainly and suggest one concrete alternative.

GROUNDING RULES (most important)
- A FACTS SHEET (below) holds verified totals, weighted margins, monthly series and segment tables. Use it first; \
call tools only for what it does not contain.
- Margin % = total profit ÷ total revenue. NEVER average row-level margins and never quote a margin that is not in \
the facts sheet or a tool result.
- If the facts sheet says something is NOT AVAILABLE (e.g. no discount column), you CANNOT measure it. Say so \
plainly, name the column to add, and answer what the data CAN show. Never use another number as a stand-in \
(total cost is not "discount leakage") and never invent causes (discounts, returns, pricing) the data cannot show; \
a hypothesis must be labelled as one.
- If cost or profit data is absent, you CANNOT measure profitability or claim a segment is operating at a loss. \
State that revenue can be measured, but profit/loss requires cost data.
- "Underperforming" means lower margin or a falling trend. A lower average sale per row only reflects ticket size.
- Name periods exactly as the data has them (e.g. "January to March", "month over month"); never say \
"quarter-over-quarter" unless the periods are quarters.
- When a percentage is a share, state its base ("of total sales").

ANSWER RULES
- Every figure you state must come from tool results or the facts sheet, or be simple arithmetic on them. Keep the currency \
symbol and units the tools used. Never invent a number.
- Start with the answer. Put the single most important point first as "Key insight: ...".
- Rank by money impact. Say what to do next (a concrete action), not only what happened.
- Markdown is fine: short paragraphs, small bullet lists, at most one small table. Be concise (usually \
under 220 words) unless asked for a report.
- Label simulations (what-if, sensitivity, forecast) clearly as hypothetical, separate from real data.
- A forecast with reliable=false must NOT be presented as a prediction; explain why it was refused.
- A "concentration" finding is a neutral observation, not a risk, unless decline is shown too.
- Mention data-quality problems that affect the conclusion (missing values, tiny samples, partial periods).
- Do not mention tool names, JSON, or your internal process. Do not say you are an AI.
"""

JSON_PROTOCOL = """
TOOL PROTOCOL (this model has no native tool calling). Reply with ONE JSON object and nothing else:
{"action":"tool","tool":"<tool name>","arguments":{...},"reason":"<=12 words"}
or, when you have enough results to answer:
{"action":"final"}
Available tools (* = required argument):
%s
"""


# ------------------------------------------------------------------ prompts


def _context_block(dataset_id: str, project: dict | None, facts: dict | None = None) -> str:
    from app.agents.analytics_agent import get_dataset_context

    df = dataset_store.get(dataset_id)
    ctx = get_dataset_context(df, dataset_id)
    roles = {}
    for col, role in (ctx.get("column_roles") or {}).items():
        roles.setdefault(role, []).append(col)
    schema = {"metrics": roles.get("metric", []), "dimensions": roles.get("dimension", []),
              "datetime": roles.get("datetime", [])}
    biz = dataset_store.get_business_context(dataset_id)
    pack = get_pack(dataset_store.get_pack_id(dataset_id))

    lines = [
        f"DATASET: {dataset_store.get_filename(dataset_id)} — {ctx['rows']} rows, {len(ctx['columns'])} columns.",
        f"Columns & types: {json.dumps(ctx['data_types'])}",
        f"Column roles: {json.dumps({k: v for k, v in roles.items()})}",
        f"Sample rows: {json.dumps(ctx['sample_data'], default=str)}",
        f"INDUSTRY PACK: {pack['name']} — money usually leaks via: {', '.join(pack.get('drivers', []))}.",
    ]
    if biz.get("metrics"):
        lines.append("Business metrics: " + json.dumps(biz["metrics"]))
    if biz.get("synonyms"):
        lines.append("Business synonyms (alias->column): " + json.dumps(biz["synonyms"]))
    if biz.get("rules"):
        lines.append("Business rules to honor: " + "; ".join(biz["rules"]))
    if biz.get("notes"):
        lines.append("Notes: " + biz["notes"])
    if project and project.get("instructions"):
        lines.append("PROJECT INSTRUCTIONS (from the user, follow them): " + project["instructions"])
    if facts:
        lines.append("FACTS SHEET (computed by code — trust these numbers):\n" + facts["text"])
    lines.append(f"<schema>{json.dumps(schema)}</schema>")
    return "\n".join(lines)


def build_messages(question, dataset_id, history, project, json_mode, facts=None):
    system = SYSTEM_PROMPT + "\n" + _context_block(dataset_id, project, facts)
    if json_mode:
        system += JSON_PROTOCOL % reg.tool_catalog_text()
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-MAX_HISTORY:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": str(h["content"])[:4000]})
    hint = question_hints(question, (facts or {}).get("capabilities") or {})
    msgs.append({"role": "user", "content": question + ("\n\n" + hint if hint else "")})
    return msgs


# ---------------------------------------------------------------- execution


def _summarize(name, ok, result):
    if not ok:
        return result.get("error", "failed")[:200]
    if name == "profit_impact_analysis":
        return f"{len(result.get('findings', []))} findings, {result.get('total_at_stake_formatted')} at stake"
    if name == "sql_query":
        return f"{result.get('row_count', 0)} rows"
    if name == "sensitivity_analysis":
        return f"base profit {result.get('base_profit_formatted')}"
    if name == "python_analysis":
        return "custom analysis complete"
    if name == "prepare_email_delivery":
        return f"prepared email preview for {result.get('recipient')}"
    return "done"


def _run_calls(calls, dataset_id, step):
    ctx = contextvars.copy_context()

    def one(c):
        return ctx.copy().run(reg.timed_run, c["name"], c.get("arguments") or {}, dataset_id)

    if len(calls) == 1:
        return [one(calls[0])]
    with ThreadPoolExecutor(max_workers=min(4, len(calls))) as ex:
        return list(ex.map(one, calls))


def _followups(tool_runs, pack_id):
    names = [t["name"] for t in tool_runs if t["ok"]]
    out = []
    table = {
        "profit_impact_analysis": ["Which of these should we fix first, and what's the expected gain?",
                                    "What if we cut discounts by 20%?", "Show the trend behind the biggest loss"],
        "sensitivity_analysis": ["Which segment is most sensitive to price changes?", "Where is margin weakest?"],
        "group_analysis": ["Why is the lowest segment underperforming?", "Show this as a monthly trend"],
        "root_cause_analysis": ["How much money does this cost us?", "Forecast the next 3 months"],
        "trend_analysis": ["What is driving the change?", "Forecast the next 3 months"],
        "auto_dashboard": ["Where am I losing money?", "What should I know that I haven't asked?"],
        "sql_query": ["Chart this result", "Where is margin weakest?"],
    }
    for n in names:
        out += table.get(n, [])
    pack = get_pack(pack_id)
    out += pack["starter_questions"]
    seen, res = set(), []
    for q in out:
        if q not in seen:
            seen.add(q)
            res.append(q)
    return res[:3]


def _trim_run(name, args, ok, result, ms):
    safe = jsonable(result)
    size = len(json.dumps(safe, default=str))
    keep = safe if size <= 250_000 else {k: v for k, v in safe.items() if k in ("charts", "chart", "evidence", "error")}
    charts = safe.get("charts") or ([safe["chart"]] if isinstance(safe.get("chart"), dict) else [])
    return {"name": name, "arguments": jsonable(args), "ok": ok, "ms": ms, "summary": _summarize(name, ok, result),
            "artifact_kind": ARTIFACT_KIND.get(name, "analysis"), "result": keep, "charts": charts,
            "evidence": safe.get("evidence") if ok else None}


# --------------------------------------------------------------------- loop


def _llm_step_native(messages):
    """One model turn with native tools. Yields events; returns (text, calls) via final 'end'."""
    text, calls = "", []
    for ev in llm.stream_chat(messages, tools=reg.openai_tools()):
        if ev["type"] == "text":
            text += ev["delta"]
            yield {"type": "chunk", "text": ev["delta"]}
        elif ev["type"] == "thinking":
            yield {"type": "thinking", "text": ev["delta"]}
        elif ev["type"] == "tool_calls":
            calls = ev["calls"]
    yield {"type": "_step_end", "text": text, "calls": calls}


def _llm_step_json(messages):
    out = llm.complete(messages, tools=[])
    if out.get("tool_calls"):  # demo brain
        c = out["tool_calls"][0]
        return {"action": "tool", "tool": c["name"], "arguments": c["arguments"], "reason": ""}, ""
    data = extract_json(out.get("content", ""))
    if not isinstance(data, dict) or data.get("action") not in ("tool", "final"):
        return {"action": "final"}, out.get("content", "")
    return data, out.get("content", "")


def _stream_final(messages, instruction=None):
    msgs = list(messages)
    if instruction:
        msgs.append({"role": "user", "content": instruction})
    text = ""
    for ev in llm.stream_chat(msgs, tools=None):
        if ev["type"] == "text":
            text += ev["delta"]
            yield {"type": "chunk", "text": ev["delta"]}
        elif ev["type"] == "thinking":
            yield {"type": "thinking", "text": ev["delta"]}
    yield {"type": "_final_text", "text": text}


TOOL_STATUS_MESSAGES = {
    "profit_impact_analysis": "Analyzing financial impact and margin leakage…",
    "sensitivity_analysis": "Computing price, volume, and cost sensitivity…",
    "sql_query": "Executing verified analytical query…",
    "python_analysis": "Executing custom Python analysis…",
    "group_analysis": "Segmenting and aggregating performance metrics…",
    "trend_analysis": "Investigating time-series and period trends…",
    "root_cause_analysis": "Decomposing variance and isolating root causes…",
    "forecast_analysis": "Evaluating time-series and generating forecast…",
    "what_if_analysis": "Simulating business scenario…",
    "auto_dashboard": "Compiling executive KPI dashboard…",
    "proactive_insights_scan": "Scanning dataset for risks and opportunities…",
    "data_health_score": "Auditing dataset quality and completeness…",
    "column_analysis": "Analyzing column distribution and statistics…",
    "basic_statistics": "Calculating summary statistics…",
    "correlation_analysis": "Computing correlation matrix…",
    "pivot_table_analysis": "Generating cross-tab pivot analysis…",
    "top_n_analysis": "Extracting top and bottom performers…",
    "filter_analysis": "Filtering and inspecting segment records…",
    "missing_value_report": "Analyzing missing values and completeness…",
    "outlier_detection": "Detecting statistical outliers…",
    "distribution_analysis": "Computing frequency and distributions…",
    "full_eda_summary": "Executing exploratory data sweep…",
    "prepare_email_delivery": "Preparing secure email preview and report attachments…",
}


def _call_signature(name: str, arguments: dict | None) -> str:
    try:
        args_json = json.dumps(arguments or {}, sort_keys=True, default=str)
    except Exception:
        args_json = str(arguments)
    return f"{name}:{args_json}"


def run_agent_stream(
    question: str,
    dataset_id: str,
    history: list | None = None,
    project: dict | None = None,
    pending_action: dict | None = None,
):
    t0 = time.time()
    dataset_store.get(dataset_id)  # permission + existence check (raises)

    # Conversational Email Intent & Multi-Turn State Machine
    if is_email_intent(question, pending_action):
        ws = current_workspace.get() or "ws_default"
        conv = handle_conversational_email(question, dataset_id, ws, pending_action)

        if conv["status"] == "need_recipient":
            yield {"type": "status", "message": "Collecting email recipient…"}
            yield {"type": "chunk", "text": conv["message"]}
            yield {
                "type": "done",
                "answer": conv["message"],
                "tool_runs": [],
                "verification": {"status": "no_numbers", "unverified": [], "unsupported": []},
                "confidence": {"score": 100, "level": "high", "reasons": []},
                "followups": ["manager@example.com", "cfo@example.com", "Cancel email delivery"],
                "pending_action": conv["pending_action"],
                "email_preview": None,
                "mode": "conversational_email",
                "demo": False,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
            return

        if conv["status"] == "sent":
            yield {"type": "status", "message": "Email accepted by Gmail API…"}
            yield {"type": "chunk", "text": conv["message"]}
            yield {
                "type": "done",
                "answer": conv["message"],
                "tool_runs": [],
                "verification": {"status": "verified", "unverified": [], "unsupported": []},
                "confidence": {"score": 100, "level": "high", "reasons": ["Dispatched via Gmail API"]},
                "followups": ["Send another report", "Show profit summary", "What else can you analyze?"],
                "pending_action": None,
                "email_preview": None,
                "mode": "conversational_email",
                "demo": False,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
            return

        if conv["status"] == "failed":
            yield {"type": "status", "message": "Email delivery failed."}
            yield {"type": "chunk", "text": conv["message"]}
            yield {
                "type": "done",
                "answer": conv["message"],
                "tool_runs": [],
                "verification": {"status": "no_numbers", "unverified": [], "unsupported": []},
                "confidence": {"score": 40, "level": "low", "reasons": ["Email delivery error"]},
                "followups": ["Retry sending", "Cancel email delivery"],
                "pending_action": None,
                "email_preview": None,
                "mode": "conversational_email",
                "demo": False,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
            return

        if conv["status"] == "cancelled":
            yield {"type": "status", "message": "Cancelled email delivery."}
            yield {"type": "chunk", "text": conv["message"]}
            yield {
                "type": "done",
                "answer": conv["message"],
                "tool_runs": [],
                "verification": {"status": "no_numbers", "unverified": [], "unsupported": []},
                "confidence": {"score": 100, "level": "high", "reasons": []},
                "followups": ["Show profit summary", "What else can you analyze?"],
                "pending_action": None,
                "email_preview": None,
                "mode": "conversational_email",
                "demo": False,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
            return

        if conv["status"] == "preview_ready":
            yield {"type": "status", "message": "Preparing secure email preview and report attachments…"}
            prev = conv["preview"]
            run_dict = {
                "id": "email_prep_1",
                "name": "prepare_email_delivery",
                "arguments": {
                    "recipient": prev["recipient"],
                    "format": prev["format"],
                    "report_type": prev["report_type"],
                },
                "ok": True,
                "ms": 110,
                "summary": f"Prepared email preview for {prev['recipient']}",
                "artifact_kind": "email_preview",
                "result": prev,
                "charts": [],
                "evidence": None,
            }
            yield {
                "type": "tool_start",
                "id": run_dict["id"],
                "name": run_dict["name"],
                "arguments": run_dict["arguments"],
                "step": 1,
            }
            yield {"type": "tool_result", **run_dict}
            yield {"type": "chunk", "text": conv["message"]}
            yield {
                "type": "done",
                "answer": conv["message"],
                "tool_runs": [run_dict],
                "verification": {"status": "verified", "unverified": [], "unsupported": []},
                "confidence": {
                    "score": 100,
                    "level": "high",
                    "reasons": ["Report generated with deterministic metrics"],
                },
                "followups": ["Confirm and send", "Send to another recipient", "Cancel"],
                "pending_action": conv["pending_action"],
                "email_preview": prev,
                "mode": "conversational_email",
                "demo": False,
                "elapsed_ms": int((time.time() - t0) * 1000),
            }
            return

    yield {"type": "status", "message": "Reading your data…"}

    json_mode = (not llm.model_supports_tools()) and not cfg.use_mock_llm()
    if cfg.TOOL_MODE == "json":
        json_mode = True
    try:
        facts = build_facts(dataset_id)
    except Exception:  # noqa: BLE001  (facts are an accuracy aid, never a reason to fail)
        logger.exception("facts sheet failed")
        facts = None
    messages = build_messages(question, dataset_id, history, project, json_mode, facts)
    tool_runs: list[dict] = []
    answer = ""
    step = 0
    failures: dict[str, int] = {}
    total_failures = 0
    executed_cache: dict[str, tuple[bool, dict, int]] = {}

    while step < cfg.AGENT_MAX_STEPS:
        step += 1
        calls, text = [], ""

        if not json_mode:
            try:
                for ev in _llm_step_native(messages):
                    if ev["type"] == "_step_end":
                        text, calls = ev["text"], ev["calls"]
                    else:
                        yield ev
            except llm.ToolsUnsupported:
                llm.mark_no_tools()
                json_mode = True
                messages = build_messages(question, dataset_id, history, project, True, facts)
                step -= 1
                yield {"type": "status", "message": "Switching to compatibility mode…"}
                continue
        else:
            yield {"type": "status", "message": "Planning the analysis…"}
            action, raw = _llm_step_json(messages)
            if action["action"] == "tool" and action.get("tool"):
                calls = [{"id": f"call_{step}", "name": action["tool"], "arguments": action.get("arguments") or {}}]
                if action.get("reason"):
                    yield {"type": "thought", "text": action["reason"]}
                messages.append({"role": "assistant", "content": json.dumps(action)})

        if not calls:
            if json_mode:
                break  # model said "final" -> stream the answer below
            answer = text.strip()
            break

        if text.strip() and not json_mode:
            yield {"type": "retract"}
            yield {"type": "thought", "text": text.strip()}

        # Filter calls for duplicate detection and circuit breakers
        calls_to_run = []
        cached_results = []
        for c in calls:
            sig = _call_signature(c["name"], c.get("arguments"))
            if sig in executed_cache:
                ok, res, ms = executed_cache[sig]
                cached_results.append((c, ok, res, ms, True))
            else:
                calls_to_run.append(c)

        for c in calls:
            status_msg = TOOL_STATUS_MESSAGES.get(c["name"], f"Running {c['name']}…")
            yield {"type": "status", "message": status_msg}
            yield {"type": "tool_start", "id": c["id"], "name": c["name"], "arguments": jsonable(c["arguments"]),
                   "step": step}

        fresh_results = _run_calls(calls_to_run, dataset_id, step) if calls_to_run else []
        for c, (ok, res, ms) in zip(calls_to_run, fresh_results):
            sig = _call_signature(c["name"], c.get("arguments"))
            executed_cache[sig] = (ok, res, ms)

        # Merge results preserving order
        all_results_map = {}
        for c, ok, res, ms, _ in cached_results:
            all_results_map[c["id"]] = (ok, res, ms, True)
        for c, (ok, res, ms) in zip(calls_to_run, fresh_results):
            all_results_map[c["id"]] = (ok, res, ms, False)

        if not json_mode:
            messages.append({
                "role": "assistant", "content": text or None,
                "tool_calls": [{"id": c["id"], "type": "function",
                                "function": {"name": c["name"], "arguments": json.dumps(c["arguments"] or {})}}
                               for c in calls]})

        for c in calls:
            ok, result, ms, is_duplicate = all_results_map[c["id"]]
            run = _trim_run(c["name"], c["arguments"], ok, result, ms)
            run["id"] = c["id"]
            run["step"] = step
            tool_runs.append({**run, "_raw": result})
            yield {"type": "tool_result", **{k: v for k, v in run.items()}}

            body = reg.compact_for_llm(result) if ok else json.dumps({"error": result.get("error", "execution failed")})
            if is_duplicate:
                body += "\n(Note: This exact calculation was already executed with identical arguments in a previous step. Do not repeat it; proceed to answer or choose another tool.)"

            if not ok:
                failures[c["name"]] = failures.get(c["name"], 0) + 1
                total_failures += 1
                body += "\nFix the arguments using real column names and try again, or choose another approach."
                if failures[c["name"]] >= 2:
                    body += " This tool failed twice; choose a different tool or explain the limitation."
                if total_failures >= 3:
                    body += " Circuit breaker triggered after multiple failures; conclude now using available facts."

            if json_mode:
                messages.append({"role": "user", "content": f"TOOL RESULT ({c['name']}): {body}"})
            else:
                messages.append({"role": "tool", "tool_call_id": c["id"], "name": c["name"], "content": body})

        if total_failures >= 3:
            logger.warning("Agent circuit breaker triggered after 3 tool failures.")
            break

        yield {"type": "status", "message": "Analyzing results…"}

    # ---- final answer (native loop that stopped on text already has it)
    if not answer:
        yield {"type": "status", "message": "Synthesizing business insights & recommendations…"}
        instruction = ("Write the final answer now using only the tool results above."
                       if (step >= cfg.AGENT_MAX_STEPS or json_mode or total_failures >= 3) else None)
        if step >= cfg.AGENT_MAX_STEPS and not json_mode:
            instruction = "You have reached the step limit. Answer now with what you have; state clearly what is missing."
        for ev in _stream_final(messages, instruction):
            if ev["type"] == "_final_text":
                answer = ev["text"].strip()
            else:
                yield ev

    ok_raw = [t["_raw"] for t in tool_runs if t["ok"]]
    if facts:
        ok_raw = ok_raw + [{"facts": facts["numbers"]}]
    caps = (facts or {}).get("capabilities")

    yield {"type": "status", "message": "Verifying claims against ground truth…"}

    def check(text):
        v = verify_answer(text, ok_raw)
        v["unsupported"] = unsupported_claims(text, caps)
        if v["unsupported"] and v["status"] in ("verified", "no_numbers"):
            v["status"] = "partial"
        return v

    verification = check(answer)

    # one automatic correction pass when figures can't be traced or claims go beyond the data
    if verification["status"] == "unverified" or len(verification["unverified"]) >= 3 or verification["unsupported"]:
        problems = []
        if verification["unverified"]:
            problems.append("These figures are NOT in the facts sheet or tool results: "
                            + ", ".join(u["text"] for u in verification["unverified"][:8]) + ".")
        for u in verification["unsupported"][:3]:
            problems.append(f"You made a claim about {u['role']} (\"{u['sentence']}\") but this dataset has NO {u['role']} data.")
        yield {"type": "status", "message": "Double-checking figures…"}
        yield {"type": "retract"}
        messages.append({"role": "assistant", "content": answer})
        fix = (" ".join(problems) + " Rewrite your answer using only figures from the facts sheet / tool results "
               "(or simple arithmetic on them). Remove every claim the data cannot support and state plainly what "
               "cannot be measured and which column would be needed.")
        for ev in _stream_final(messages, fix):
            if ev["type"] == "_final_text":
                answer = ev["text"].strip() or answer
            else:
                yield ev
        verification = check(answer)
        verification["auto_corrected"] = True

    health = None
    try:
        h = dataset_store.get_cache(dataset_id, "data_health_score")
        health = h.get("overall_score") if isinstance(h, dict) else None
    except Exception:
        pass
    rows = len(dataset_store.get(dataset_id))
    confidence = confidence_score(verification, rows, health,
                                  [{"ok": t["ok"], "result": t["_raw"] if t["ok"] else {}} for t in tool_runs])

    runs_out = [{k: v for k, v in t.items() if k != "_raw"} for t in tool_runs]
    last_ok = next((t for t in reversed(runs_out) if t["ok"]), None)
    email_prev = next((t.get("result") for t in runs_out if t.get("name") == "prepare_email_delivery" and t.get("ok")), None)
    yield {"type": "done", "answer": answer, "tool_runs": runs_out, "verification": verification,
           "confidence": confidence, "followups": _followups(runs_out, dataset_store.get_pack_id(dataset_id)),
           "tool_result": last_ok["result"] if last_ok else None,
           "evidence": [t["evidence"] for t in runs_out if t.get("evidence")],
           "pending_action": pending_action,
           "email_preview": email_prev,
           "mode": "json" if json_mode else "native", "demo": cfg.use_mock_llm(),
           "elapsed_ms": int((time.time() - t0) * 1000)}


def run_agent(question, dataset_id, history=None, project=None, pending_action=None) -> dict:
    final = None
    for ev in run_agent_stream(question, dataset_id, history, project, pending_action=pending_action):
        if ev["type"] == "done":
            final = ev
    return final or {"answer": "", "tool_runs": []}
