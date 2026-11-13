"""
Facts sheet — deterministic ground truth handed to the LLM before it answers.

It contains totals, weighted margins, monthly series and segment tables computed
by code (never by the model), plus an explicit list of what the dataset CANNOT
tell us (e.g. no discount column). Weaker models stop inventing numbers/causes
when the right numbers are already on the table, and the verifier treats every
figure in the sheet as legitimate evidence.
"""
import re

import pandas as pd

from app.packs import get_pack
from app.services.column_roles import detect_column_roles
from app.services.dataset_manager import dataset_store
from app.services.profit_engine import (
    _numeric, _period_series, _pick_dimensions, detect_financial_columns, fmt_money,
)
from app.services.profit_service import currency_for

# words in a question that imply a business concept, mapped to the capability role needed to answer it
CONCEPTS = {
    "discount": re.compile(r"\b(discount|discounts|discounted|coupon|coupons|promo|promotion|markdown|rebate)\w*", re.I),
    "returns": re.compile(r"\b(return|returns|returned|refund|refunds|rto|chargeback|chargebacks)\b", re.I),
    "churn": re.compile(r"\b(churn|churned|attrition|cancell?ation|cancell?ed)\w*", re.I),
    "cost": re.compile(r"\b(cost|costs|cogs|expense|expenses|spend)\b", re.I),
    "price": re.compile(r"\b(unit price|price per|pricing)\b", re.I),
}
HUMAN = {"discount": "discount", "returns": "returns/refunds", "churn": "churn", "cost": "cost", "price": "unit price"}


def build_facts(dataset_id: str, max_dims: int = 3, max_segments: int = 8) -> dict:
    df = dataset_store.get(dataset_id)
    raw = dataset_store.get_raw(dataset_id)
    cur = currency_for(dataset_id)
    pack_id = dataset_store.get_pack_id(dataset_id)
    ctx = dataset_store.get_business_context(dataset_id)
    cols = detect_financial_columns(df, pack_id, ctx)
    rev = _numeric(df[cols["revenue"]]) if cols["revenue"] else None
    profit = _numeric(df[cols["profit"]]) if cols["profit"] else None
    cost_col = _numeric(df[cols["cost"]]) if cols["cost"] else None
    if profit is None and rev is not None and cost_col is not None:
        profit = rev - cost_col

    nums: list[float] = []
    lines: list[str] = []

    def keep(*vals):
        for v in vals:
            if v is not None and pd.notna(v):
                nums.append(float(v))

    dup = len(raw) - len(df)
    lines.append(f"Rows analysed: {len(df)}" + (f" ({dup} exact duplicate row(s) excluded from raw {len(raw)})" if dup else ""))
    keep(len(df), len(raw), dup)

    capabilities = {k: v for k, v in cols.items()}
    if capabilities.get("cost") is None and rev is not None and profit is not None:
        capabilities["cost"] = "derived"

    if rev is not None:
        total_rev = float(rev.sum())
        keep(total_rev)
        lines.append(f"Total {cols['revenue']}: {fmt_money(total_rev, cur)} ({total_rev:,.2f})")
    if profit is not None:
        total_p = float(profit.sum())
        keep(total_p)
        lines.append(f"Total {cols['profit'] or 'profit'}: {fmt_money(total_p, cur)} ({total_p:,.2f})")
    both = (rev.notna() & profit.notna()) if (rev is not None and profit is not None) else None
    margin = None
    if both is not None and both.any() and rev[both].sum():
        margin = float(profit[both].sum() / rev[both].sum() * 100)
        keep(margin, int(both.sum()), float(rev[both].sum()), float(profit[both].sum()))
        lines.append(f"OVERALL MARGIN = total profit ÷ total revenue = {margin:.2f}% "
                     f"(weighted, over the {int(both.sum())} rows that have both). "
                     f"Total cost = revenue − profit = {fmt_money(float(rev[both].sum() - profit[both].sum()), cur)}.")
        miss = len(df) - int(both.sum())
        if miss:
            lines.append(f"{miss} row(s) lack a revenue or profit value and are excluded from margins.")

    # monthly series of the headline measure
    measure = profit if profit is not None else rev
    if cols["date"] and measure is not None:
        ps = _period_series(df, cols["date"], measure)
        if ps is not None:
            ser, cnt, freq, _, _, max_date = ps
            keep(*ser.values)
            lines.append(f"{'Profit' if profit is not None else 'Revenue'} by {'month' if freq == 'M' else 'week' if freq == 'W' else 'day'} "
                         f"(data runs to {max_date.date()}): " +
                         ", ".join(f"{p}: {fmt_money(v, cur)} ({int(c)} rows)" for (p, v), c in zip(ser.tail(8).items(), cnt.tail(8))))

    # segment tables with WEIGHTED margins
    if rev is not None:
        roles = detect_column_roles(df)
        exclude = {c for c in cols.values() if c}
        pack = get_pack(pack_id)
        for dim in _pick_dimensions(df, roles, pack, exclude, limit=max_dims):
            frame = pd.DataFrame({"k": df[dim].astype(str), "r": rev})
            if profit is not None:
                frame["p"] = profit
                frame["rm"] = rev.where(both)
                frame["pm"] = profit.where(both)
            agg = frame.groupby("k").agg(r=("r", "sum"), n=("r", "size"))
            if profit is not None:
                g = frame.groupby("k")
                agg["p"] = g["p"].sum()
                agg["m"] = g["pm"].sum() / g["rm"].sum() * 100  # margin on complete rows only
            agg = agg.sort_values("r", ascending=False).head(max_segments)
            tot = float(rev.sum())
            rows = []
            for k, r in agg.iterrows():
                keep(r["r"], r["n"], r.get("p"), r.get("m"), r["r"] / tot * 100 if tot else None)
                part = f"{k}: revenue {fmt_money(r['r'], cur)} ({r['r'] / tot * 100:.1f}% of total)" if tot else f"{k}: revenue {fmt_money(r['r'], cur)}"
                if profit is not None:
                    part += f", profit {fmt_money(r['p'], cur)}, margin {r['m']:.2f}%"
                rows.append(part + f", {int(r['n'])} rows")
            lines.append(f"By {dim} (weighted margins):\n  - " + "\n  - ".join(rows))

    # what the data cannot tell us
    missing = [HUMAN[r] for r in ("discount", "returns", "churn", "price") if capabilities.get(r) is None]
    if capabilities.get("cost") is None:
        missing.append("cost")
    if missing:
        lines.append("NOT AVAILABLE in this dataset (no such column): " + ", ".join(missing) +
                     ". Anything about these can NOT be measured here — do not estimate, proxy or invent it.")
    lines.append("DEFINITIONS: margin% = total profit ÷ total revenue (weighted). NEVER average row-level margins. "
                 "'Underperforming' means lower margin or a falling trend — NOT a lower average ticket size.")

    return {"text": "\n".join(lines), "numbers": nums, "capabilities": capabilities, "currency": cur}


def question_hints(question: str, capabilities: dict) -> str:
    """Pre-answer nudge when the user asks about something the data cannot contain."""
    gaps = []
    for role, rx in CONCEPTS.items():
        if rx.search(question or "") and capabilities.get(role) is None:
            gaps.append(HUMAN[role])
    if not gaps:
        return ""
    return ("[System note — dataset limitation: this dataset has NO " + " / ".join(gaps) +
            " column. Do NOT estimate it, do NOT use another number as a proxy (e.g. 'sales − profit' is total cost, not "
            f"{gaps[0]}), and do NOT speculate about causes. Say plainly it cannot be measured from this data, say which "
            "column to add, then answer what the available data CAN show.]")
