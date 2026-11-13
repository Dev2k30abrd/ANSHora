"""
Offline 'demo brain'. Used when no LLM key is configured so the whole product
(UI, tools, verifier, profit engine) works locally and in tests. It routes by
keywords and writes grounded, template-based answers from tool results.
"""
import json
import re

_SCHEMA_RE = re.compile(r"<schema>(.*?)</schema>", re.S)


def _schema(messages):
    for m in messages:
        if m.get("role") == "system":
            mt = _SCHEMA_RE.search(m.get("content") or "")
            if mt:
                try:
                    return json.loads(mt.group(1))
                except Exception:
                    pass
    return {"metrics": [], "dimensions": [], "datetime": []}


def _last_user(messages):
    for m in reversed(messages):
        if m.get("role") == "user":
            return m.get("content") or ""
    return ""


def _tool_msgs_since_user(messages):
    out = []
    for m in reversed(messages):
        if m.get("role") == "user":
            break
        if m.get("role") == "tool":
            out.append(m)
    return list(reversed(out))


def _plan(q: str, sch: dict) -> list[tuple[str, dict]]:
    ql = q.lower()
    metrics, dims, dts = sch.get("metrics") or [], sch.get("dimensions") or [], sch.get("datetime") or []
    mcol = next((m for m in metrics if m.lower() in ql), None) or (metrics[0] if metrics else None)
    dcol = next((d for d in dims if d.lower() in ql), None) or (dims[0] if dims else None)
    tcol = dts[0] if dts else None

    if re.search(r"\bsql\b|select .* from", ql):
        return [("sql_query", {"query": "SELECT * FROM data LIMIT 5"})]
    if re.search(r"sensitiv|break-?even|pricing|price (cut|rise|increase|change)|what if.*(price|volume|cost|discount)", ql):
        return [("sensitivity_analysis", {})]
    if re.search(r"forecast|predict|project", ql) and tcol and mcol:
        return [("forecast_analysis", {"date_column": tcol, "value_column": mcol, "periods": 3, "freq": "M"})]
    if re.search(r"\bwhy\b|root cause|what (is )?driving|what caused", ql) and mcol:
        plan = [("root_cause_analysis", {"metric_column": mcol, **({"date_column": tcol} if tcol else {})})]
        if tcol:
            plan.append(("trend_analysis", {"date_column": tcol, "value_column": mcol, "freq": "M"}))
        return plan
    if re.search(r"losing|loss|leak|margin|profit|discount|churn|at stake|fix first|money|revenue", ql):
        return [("profit_impact_analysis", {})]
    if re.search(r"dashboard|key numbers|kpi", ql):
        return [("auto_dashboard", {})]
    if re.search(r"quality|clean|reliable|health", ql):
        return [("data_health_score", {})]
    if re.search(r"correlat|relationship", ql):
        return [("correlation_analysis", {})]
    if re.search(r"outlier|anomal", ql):
        return [("outlier_detection", {})]
    if re.search(r"should i know|interesting|insight|opportunit|risk", ql):
        return [("proactive_insights_scan", {})]
    if re.search(r"trend|over time|monthly|growth", ql) and tcol and mcol:
        return [("trend_analysis", {"date_column": tcol, "value_column": mcol, "freq": "M"})]
    if re.search(r"\bby\b|top|best|worst|highest|lowest|compare|per ", ql) and dcol and mcol:
        return [("group_analysis", {"group_column": dcol, "value_column": mcol, "operation": "sum"})]
    return [("basic_statistics", {})]


def _flat(obj, depth=0):
    """Pick a few headline scalars + the first list of rows."""
    lines = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("evidence", "charts", "chart", "_guard_notes"):
                continue
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                lines.append(f"- {k.replace('_', ' ')}: {v}")
            elif isinstance(v, str) and len(v) < 160:
                lines.append(f"- {k.replace('_', ' ')}: {v}")
            if len(lines) >= 8:
                break
        for k, v in obj.items():
            if isinstance(v, list) and v and isinstance(v[0], dict) and k not in ("charts",):
                lines.append(f"\n{k.replace('_', ' ').title()} (first {min(5, len(v))}):")
                for row in v[:5]:
                    lines.append("- " + ", ".join(f"{a}: {b}" for a, b in list(row.items())[:4]))
                break
            if isinstance(v, dict) and k == "result" and v:
                lines.append("\nResult:")
                for a, b in list(v.items())[:6]:
                    lines.append(f"- {a}: {b}")
                break
    return "\n".join(lines)


def _compose(messages) -> str:
    results = []
    for m in _tool_msgs_since_user(messages):
        try:
            results.append(json.loads(m.get("content") or "{}"))
        except Exception:
            results.append({})
    if not results:
        return "I could not run any analysis for that question."
    last = results[-1]
    if last.get("error"):
        return f"I could not complete that analysis: {last['error']}"
    parts = []
    first = results[0]
    if "findings" in first and "headline" in first and "total_at_stake_formatted" in first:
        h = first["headline"].get("formatted", {})
        parts.append(f"Revenue is {h.get('revenue')}, profit {h.get('profit')}"
                     + (f" at a {h.get('margin')} margin." if h.get("margin") else "."))
        fs = first["findings"][:3]
        if fs:
            parts.append(f"Key insight: {fs[0]['title']} — about {fs[0]['impact_formatted']} at stake. {fs[0]['detail']}")
            if len(fs) > 1:
                parts.append("Next biggest items:\n" + "\n".join(
                    f"{i}. {f['title']} — {f['impact_formatted']}" for i, f in enumerate(fs[1:], 1)))
            parts.append(f"Total money at stake (upper bound): {first['total_at_stake_formatted']}.")
        else:
            parts.append("No material money-impacting findings were detected with the available columns.")
        for n in first.get("notes", [])[:2]:
            parts.append(n)
    elif "profit_grid" in first:
        parts.append(f"Baseline profit is {first['base_profit_formatted']}. Best tested case is a "
                     f"{first['best_case']['price_pct']}% price and {first['best_case']['volume_pct']}% volume move, "
                     f"giving {first['best_case']['profit_formatted']}; worst case gives {first['worst_case']['profit_formatted']}.")
        if first.get("break_even_price_change_pct") is not None:
            parts.append(f"Break-even price change: {first['break_even_price_change_pct']:.1f}%.")
        parts.append(first["assumptions"])
    else:
        for r in results:
            parts.append(_flat(r))
    parts.append("\n_Demo mode: set LLM_API_KEY in .env for full natural-language reasoning._")
    return "\n\n".join(p for p in parts if p)


class MockBrain:
    @staticmethod
    def decide(messages, tools=None):
        q, sch = _last_user(messages), _schema(messages)
        done = _tool_msgs_since_user(messages)
        plan = _plan(q, sch)
        if tools is not None and not tools:
            return None
        if len(done) < len(plan) and not any('"error"' in (m.get("content") or "")[:12] for m in done):
            name, args = plan[len(done)]
            return {"id": f"call_{len(done)}", "name": name, "arguments": args}
        return None

    @staticmethod
    def complete(messages, tools=None):
        call = MockBrain.decide(messages, tools if tools is not None else [1])
        if call:
            return {"content": "", "tool_calls": [call]}
        return {"content": _compose(messages), "tool_calls": []}

    @staticmethod
    def stream(messages, tools=None):
        call = MockBrain.decide(messages, tools if tools is not None else [1])
        if call:
            yield {"type": "tool_calls", "calls": [call]}
            yield {"type": "end", "content": ""}
            return
        text = _compose(messages)
        for i in range(0, len(text), 24):
            yield {"type": "text", "delta": text[i:i + 24]}
        yield {"type": "end", "content": text}


def _item(f):
    if isinstance(f, dict):
        return f.get("title") or f.get("message") or f.get("summary") or f.get("description") or str(f)
    return str(f)


def text_for(messages) -> str:
    """Template narration for legacy one-shot prompts (executive report, first-look insights)."""
    system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
    user = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    body = user.split("\n", 1)[1] if "\n" in user else user
    try:
        data = json.loads(body)
    except Exception:
        data = {}
    if "executive report" in system.lower() and isinstance(data, dict):
        def sec(title, items):
            items = [_item(i) for i in (items or [])][:4]
            return f"{title}\n" + (" ".join(items) if items else "Nothing notable detected.")
        kpis = data.get("kpis") or []
        k_txt = ", ".join(f"{k.get('metric')}: total {k.get('sum'):,}" for k in kpis[:6]
                          if isinstance(k, dict) and isinstance(k.get("sum"), (int, float)))
        parts = [
            f"Executive Summary\nThis report covers {data.get('rows')} rows and {data.get('columns')} columns from "
            f"{data.get('dataset')}. Data quality scores {data.get('data_quality_score')} out of 100.",
            f"Key Metrics\n{k_txt or 'See the dashboard for headline metrics.'}",
            sec("Key Insights", data.get("trends")), sec("Observations", data.get("observations")),
            sec("Risks", data.get("risks")), sec("Opportunities", data.get("opportunities")),
            "Recommendations\nAddress the largest risks first, then pursue the listed opportunities. "
            "(Demo mode narration — set LLM_API_KEY for a fully written report.)",
        ]
        return "\n\n".join(parts)
    shape = data.get("shape") or {}
    return ("First look: " + (f"{shape.get('rows')} rows x {shape.get('columns')} columns. " if shape else "")
            + "Ask where you are losing money, or request a dashboard to start. "
            "(Demo mode — set LLM_API_KEY for a written briefing.)")
