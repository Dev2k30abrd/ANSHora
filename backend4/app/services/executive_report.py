"""
Executive Reports — feature 8.

Composes a data-grounded report: KPIs, insights, risks, opportunities,
and recommendations — all computed deterministically first, then
handed to the LLM to narrate/format professionally. If the LLM is offline,
times out, or returns an empty response, the system seamlessly provides
a verified deterministic report with clear source attribution.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor

from app.services.dataset_manager import dataset_store
from app.services.auto_dashboard import generate_auto_dashboard
from app.services.proactive_insights import scan_for_insights
from app.services.data_health import compute_data_health

logger = logging.getLogger("anshora.executive_report")


REPORT_SYSTEM_PROMPT = """
You are a senior data analyst writing an executive report for a business
stakeholder.

STRICT GROUNDING RULE: You will be given a JSON block of ALREADY-COMPUTED
data (KPIs, findings, quality score). You must ONLY use numbers that
appear in that JSON. Never invent, estimate, or round-fabricate any
number not present in the data. If the data doesn't support a claim,
don't make the claim.

FORMAT: Write plain, professional prose. No Markdown symbols (no **, ##,
tables). Structure the report into these sections, each with a plain-text
heading line (no punctuation, just the words):

Executive Summary
Key Metrics
Key Insights
Observations
Risks
Opportunities
Recommendations

Rules you must follow:
- Use ONLY numbers present in the data block; quote the exact period labels given
  (never say "quarter-over-quarter" unless the periods are quarters).
- "profit_impact" holds the authoritative headline totals and margin. Margin is
  total profit divided by total revenue — never an average of row margins.
- A "concentration" or "mix" finding (one segment holding a large share, or a
  different average ticket size) is a neutral observation, NOT a risk and NOT
  underperformance. Risks and Opportunities come only from "risks" and
  "opportunities" (loss, leakage, decline, margin gaps).
- If "data_issues" lists excluded duplicates or missing values, say so in the
  Executive Summary and Recommendations.
- If nothing is wrong, say so plainly instead of inventing risks.

Keep it concise: 2-4 sentences per section is enough for most datasets.
Do not mention that you are an AI, and do not describe your own process.
"""


def build_deterministic_executive_report(data_block: dict) -> str:
    """
    Generates a structured, mathematically grounded executive narrative directly
    from verified analytical metrics. Used whenever the LLM is offline, times out,
    or returns an empty response. Never invents figures.
    """
    lines = []

    # 1. Executive Summary
    lines.append("Executive Summary")
    filename = data_block.get("dataset", "the dataset")
    rows = data_block.get("rows", 0)
    cols = data_block.get("columns", 0)
    grade = data_block.get("data_quality_grade", "Good")
    score = data_block.get("data_quality_score", 100)
    pi = data_block.get("profit_impact", {})
    money_at_stake = pi.get("money_at_stake") or "None detected"
    headline = pi.get("headline", {})
    rev = headline.get("revenue")
    prof = headline.get("profit")
    margin = headline.get("margin")

    summary_sentences = [
        f"This executive analysis evaluates {filename} encompassing {rows:,} verified records across {cols} analytical dimensions.",
        f"Overall data health is rated as {grade} with an audit score of {score}/100."
    ]
    if rev:
        prof_clause = f" with {prof} in net operating profit ({margin} margin)" if prof and margin else ""
        summary_sentences.append(f"The business generated {rev} in total revenue{prof_clause}.")
    if money_at_stake and money_at_stake != "None detected":
        summary_sentences.append(f"Quantified financial leakage and segment risk total {money_at_stake} at stake requiring executive attention.")
    lines.append(" ".join(summary_sentences))
    lines.append("")

    # 2. Key Metrics
    lines.append("Key Metrics")
    kpis = data_block.get("kpis", [])
    if kpis:
        for k in kpis[:6]:
            lbl = k.get("label") or k.get("metric") or "Metric"
            val = k.get("value")
            if val is None:
                if "sum" in k and k["sum"] is not None:
                    s = k["sum"]
                    val = f"{s:,.2f}" if isinstance(s, (int, float)) else str(s)
                elif "mean" in k and k["mean"] is not None:
                    m = k["mean"]
                    val = f"mean {m:,.2f}" if isinstance(m, (int, float)) else str(m)
                else:
                    val = "N/A"
            unit = k.get("unit", "")
            lines.append(f"- {lbl}: {val}{(' ' + unit) if unit else ''}")
    else:
        lines.append(f"- Total Analyzed Transactions: {rows:,}")
        if rev:
            lines.append(f"- Total Gross Revenue: {rev}")
        if prof:
            lines.append(f"- Total Net Profit: {prof}")
    lines.append("")

    # 3. Key Insights
    lines.append("Key Insights")
    trends = data_block.get("trends", [])
    anomalies = data_block.get("anomalies", [])
    if trends or anomalies:
        for t in trends[:3]:
            det = t.get("detail")
            det_str = f": {det}" if isinstance(det, str) else ""
            lines.append(f"- {t.get('title')}{det_str}")
        for a in anomalies[:2]:
            det = a.get("detail")
            if isinstance(det, dict):
                cnt = det.get("outlier_count", 0)
                pct = det.get("outlier_percentage", 0)
                lines.append(f"- {a.get('title')}: {cnt} outliers ({pct}% of rows)")
            elif isinstance(det, str):
                lines.append(f"- {a.get('title')}: {det}")
            else:
                lines.append(f"- {a.get('title')}")
    else:
        lines.append("- Performance patterns remain stable across the evaluated period with consistent category distribution.")
    lines.append("")

    # 4. Observations
    lines.append("Observations")
    obs = data_block.get("observations", [])
    if obs:
        for o in obs[:3]:
            lines.append(f"- {o.get('title')}: {o.get('detail')}")
    else:
        lines.append(f"- Transaction distribution is balanced across {cols} columns without singular points of customer concentration.")
    lines.append("")

    # 5. Risks
    lines.append("Risks")
    risks = data_block.get("risks", [])
    if risks:
        for r in risks[:4]:
            lines.append(f"- {r.get('title')} ({r.get('impact')} impact): {r.get('detail')}")
    else:
        lines.append("- No acute margin deficits or negative profit drivers were identified in the verified records.")
    lines.append("")

    # 6. Opportunities
    lines.append("Opportunities")
    opps = data_block.get("opportunities", [])
    if opps:
        for op in opps[:3]:
            lines.append(f"- {op.get('title')} ({op.get('impact')} potential): {op.get('detail')}")
    else:
        lines.append("- Operational optimization and discount governance represent the most immediate revenue opportunities.")
    lines.append("")

    # 7. Recommendations
    lines.append("Recommendations")
    recs = data_block.get("data_quality_recommendations", [])
    step_num = 1
    if recs:
        for rc in recs[:2]:
            lines.append(f"{step_num}. Data Quality: {rc}")
            step_num += 1
    if risks:
        top_risk = risks[0]
        lines.append(f"{step_num}. Address {top_risk.get('title')} to protect up to {top_risk.get('impact')} in operating margin.")
        step_num += 1
    lines.append(f"{step_num}. Establish continuous monitoring on high-volume segments to detect emerging margin leakage.")

    return "\n".join(lines)


def generate_executive_report(df, dataset_id: str, filename: str, llm_narrate_fn) -> dict:
    if df is None or len(df) == 0:
        raise ValueError("Cannot generate report from an empty dataset.")

    # dashboard/insights/health are fully independent of each other —
    # run them concurrently instead of three sequential passes over the df
    with ThreadPoolExecutor(max_workers=3) as executor:
        dashboard_future = executor.submit(generate_auto_dashboard, df)
        insights_future = executor.submit(scan_for_insights, df)
        health_future = executor.submit(compute_data_health, dataset_store.get_raw(dataset_id))

        dashboard = dashboard_future.result()
        insights = insights_future.result()
        health = health_future.result()

    from app.services.profit_service import run_profit

    try:
        pi = run_profit(dataset_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Profit engine skipped for report: %s", e)
        pi = {"findings": [], "headline": {}, "notes": [], "data_issues": []}

    def simple(f):
        return {"title": f["title"], "impact": f["impact_formatted"], "detail": f["detail"]}

    risks = [simple(f) for f in pi.get("findings", []) if f["type"] in ("loss", "leak")]
    opportunities = [simple(f) for f in pi.get("findings", []) if f["type"] == "opportunity"]
    trends = [f for f in insights["findings"] if f["type"] == "trend"]
    anomalies = [f for f in insights["findings"] if f["type"] == "anomaly"]
    observations = [f for f in insights["findings"] if f["type"] in ("concentration", "mix")]

    data_block = {
        "dataset": filename,
        "rows": dashboard["row_count"],
        "columns": dashboard["column_count"],
        "kpis": dashboard["kpis"],
        "profit_impact": {
            "headline": pi.get("headline", {}).get("formatted", {}),
            "money_at_stake": pi.get("total_at_stake_formatted"),
            "capabilities_missing": [k for k in ("discount", "returns", "churn") if (pi.get("capabilities") or {}).get(k) is None],
        },
        "data_issues": pi.get("data_issues", []),
        "data_quality_score": health["overall_score"],
        "data_quality_grade": health["grade"],
        "data_quality_recommendations": health["recommendations"],
        "trends": trends,
        "anomalies": anomalies,
        "observations": observations,
        "risks": risks,
        "opportunities": opportunities,
    }

    narrative = None
    source = "ai_narrated"
    ai_warning = None

    try:
        if llm_narrate_fn:
            narrative = llm_narrate_fn([
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": f"COMPUTED DATA:\n{json.dumps(data_block, indent=2, default=str)}"},
            ])
            if not narrative or not str(narrative).strip():
                raise ValueError("The AI model returned an empty narrative response.")
            narrative = str(narrative).strip()
    except Exception as e:
        logger.warning("LLM narration failed for executive report (%s). Providing verified deterministic report.", e)
        source = "deterministic"
        ai_warning = f"AI narrative generation was unavailable ({e}). Report generated from verified deterministic metrics."
        narrative = build_deterministic_executive_report(data_block)

    return {
        "narrative": narrative,
        "data": data_block,
        "charts": dashboard["charts"],
        "source": source,
        "ai_warning": ai_warning,
        "generated_from": {
            "dataset_id": dataset_id,
            "filename": filename,
            "rows_analyzed": dashboard["row_count"],
        },
    }
