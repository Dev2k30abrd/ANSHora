"""
Profit Impact Engine.

Turns generic analytics into money: every finding is ranked by how much
profit/revenue is at stake in the user's currency. All numbers are computed
deterministically from the data — the LLM only narrates them.
"""
import re

import numpy as np
import pandas as pd

from app.core.config import DEFAULT_CURRENCY
from app.packs import get_pack
from app.services.column_roles import detect_column_roles

# ----------------------------------------------------------------- formatting


def fmt_money(x, cur: str = DEFAULT_CURRENCY) -> str:
    if x is None or (isinstance(x, float) and (np.isnan(x) or np.isinf(x))):
        return "n/a"
    a, sign = abs(float(x)), "-" if x < 0 else ""
    if cur == "₹":
        if a >= 1e7:
            s = f"{a / 1e7:.2f} Cr"
        elif a >= 1e5:
            s = f"{a / 1e5:.2f} L"
        elif a >= 1e3:
            s = f"{a / 1e3:.1f}K"
        else:
            s = f"{a:,.0f}"
    else:
        if a >= 1e9:
            s = f"{a / 1e9:.2f}B"
        elif a >= 1e6:
            s = f"{a / 1e6:.2f}M"
        elif a >= 1e3:
            s = f"{a / 1e3:.1f}K"
        else:
            s = f"{a:,.0f}"
    return f"{sign}{cur}{s}"


# ------------------------------------------------------------ column detection


def _tokens(name: str) -> list[str]:
    name = re.sub(r"([a-z])([A-Z])", r"\1_\2", str(name))
    return [t for t in re.split(r"[^a-zA-Z0-9&]+", name.lower()) if t]


def _numeric(series: pd.Series) -> pd.Series | None:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(float)
    if pd.api.types.is_numeric_dtype(series):
        return series.astype(float)
    conv = pd.to_numeric(series.astype(str).str.replace(r"[,\s₹$€£%]", "", regex=True), errors="coerce")
    if series.notna().sum() and conv.notna().sum() / max(series.notna().sum(), 1) > 0.9:
        return conv
    return None


def _score(column: str, hints: list[str]) -> float:
    norm = "_".join(_tokens(column))
    toks = _tokens(column)
    best = 0.0
    for i, h in enumerate(hints):
        h_norm = h.lower().replace(" ", "_")
        bonus = (len(hints) - i) / (len(hints) * 100)
        if norm == h_norm:
            best = max(best, 3 + bonus)
        elif h_norm in toks:
            best = max(best, 2 + bonus)
        elif h_norm in norm:
            best = max(best, 1 + bonus)
    return best


_ROLE_ORDER = ["profit", "revenue", "cost", "discount", "returns", "churn", "quantity", "price"]


def detect_financial_columns(df: pd.DataFrame, pack_id: str | None = None, ctx: dict | None = None) -> dict:
    """Map business roles (revenue, cost, ...) to dataframe columns."""
    pack = get_pack(pack_id)
    hints = pack["hints"]
    ctx = ctx or {}
    found: dict[str, str | None] = {r: None for r in _ROLE_ORDER}
    used: set[str] = set()
    cols = [str(c) for c in df.columns]

    # 1) the user's semantic layer wins (explicit metrics and synonyms)
    for role in _ROLE_ORDER:
        m = (ctx.get("metrics") or {}).get(role)
        if m and m.get("column") in cols:
            found[role] = m["column"]
            used.add(m["column"])
    for alias, canonical in (ctx.get("synonyms") or {}).items():
        a = alias.lower()
        if a in _ROLE_ORDER and found[a] is None and canonical in cols:
            found[a] = canonical
            used.add(canonical)
    for alias, canonical in (pack.get("synonyms") or {}).items():
        pass  # pack synonyms feed prompt context; column detection uses hints

    # 2) name-based scoring over numeric columns
    for role in _ROLE_ORDER:
        if found[role]:
            continue
        best, best_score = None, 0.0
        for c in cols:
            if c in used:
                continue
            s = _score(c, hints.get(role, []))
            if s <= 0:
                continue
            if _numeric(df[c]) is None:
                continue
            if s > best_score:
                best, best_score = c, s
        if best:
            found[role] = best
            used.add(best)

    # 3) date column
    found["date"] = _detect_date(df, hints.get("date", []), used)
    return found


def _detect_date(df, hint_tokens, used):
    cands = []
    for c in df.columns:
        c = str(c)
        if c in used:
            continue
        s = df[c]
        if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_datetime64_any_dtype(s):
            continue
        if pd.api.types.is_datetime64_any_dtype(s):
            cands.append((10 + _score(c, hint_tokens), c))
            continue
        sample = s.dropna().astype(str).head(200)
        if sample.empty:
            continue
        try:
            import warnings

            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(sample, errors="coerce")
            if parsed.notna().mean() > 0.85:
                cands.append((5 + _score(c, hint_tokens), c))
        except Exception:
            continue
    return max(cands)[1] if cands else None


# ------------------------------------------------------------------- engine


def _confidence(n: int) -> str:
    return "high" if n >= 30 else "medium" if n >= 10 else "low"


def _pick_dimensions(df, roles, pack, exclude: set, limit=4):
    dims = [c for c in roles["by_role"]["dimension"] if c not in exclude and 2 <= df[c].nunique() <= 60]
    hint = [h.lower() for h in pack.get("dimensions", [])]
    dims.sort(key=lambda c: (0 if any(h in c.lower() for h in hint) else 1, df[c].nunique()))
    return dims[:limit]


def _period_series(df, date_col, value):
    """Bucket `value` by calendar period. Months when >=3 distinct months exist (the natural grain for
    business data), weeks only for >=8 weeks of history, otherwise days."""
    d = pd.to_datetime(df[date_col], errors="coerce")
    ok = d.notna() & value.notna()
    if ok.sum() < 6:
        return None
    span = (d[ok].max() - d[ok].min()).days
    months = d[ok].dt.to_period("M").nunique()
    freq = "M" if months >= 3 else "W" if span >= 56 else "D"
    per = d[ok].dt.to_period(freq)
    s = value[ok].groupby(per).sum().sort_index()
    cnt = per.groupby(per).size().sort_index()
    return s, cnt, freq, per, ok, d[ok].max()


def analyze_profit_impact(df: pd.DataFrame, pack_id: str | None = None, ctx: dict | None = None,
                          currency: str = DEFAULT_CURRENCY, max_findings: int = 12,
                          raw_df: pd.DataFrame | None = None) -> dict:
    cols = detect_financial_columns(df, pack_id, ctx)
    pack = get_pack(pack_id)
    notes: list[str] = []
    cur = currency

    rev = _numeric(df[cols["revenue"]]) if cols["revenue"] else None
    cost = _numeric(df[cols["cost"]]) if cols["cost"] else None
    prof_col = _numeric(df[cols["profit"]]) if cols["profit"] else None

    if prof_col is not None:
        profit = prof_col
    elif rev is not None and cost is not None:
        profit = rev - cost
    else:
        profit = None

    capabilities = {k: v for k, v in cols.items()}

    # Derive revenue when explicit revenue column is missing but quantity and price exist
    if rev is None and cols.get("quantity") and cols.get("price"):
        q = _numeric(df[cols["quantity"]])
        p = _numeric(df[cols["price"]])
        if q is not None and p is not None:
            rev = q * p
            cols["revenue"] = f"{cols['quantity']} × {cols['price']} (derived)"
            capabilities["revenue"] = cols["revenue"]
            notes.append(f"Revenue computed as {cols['quantity']} × {cols['price']}.")
            if prof_col is None and profit is None and cost is not None:
                profit = rev - cost

    if capabilities.get("cost") is None and rev is not None and profit is not None:
        capabilities["cost"] = f"{cols['revenue']} − {cols['profit']} (derived)"

    if rev is None and profit is None:
        return {
            "mode": "none", "currency": cur, "detected": cols, "capabilities": capabilities, "headline": {}, "findings": [],
            "total_at_stake": 0, "total_at_stake_formatted": fmt_money(0, cur),
            "notes": ["No revenue/cost/profit-like numeric columns were found. Map them in Business Context "
                      "(metrics named 'revenue', 'cost' or 'profit') and run again."],
        }

    mode = "full" if profit is not None else "revenue_only"
    if mode == "revenue_only":
        notes.append("No cost or profit column found — impact is measured in revenue, not profit.")
    if prof_col is None and profit is not None:
        notes.append(f"Profit computed as {cols['revenue']} − {cols['cost']}.")

    measure = profit if profit is not None else rev
    measure_name = "profit" if profit is not None else "revenue"
    total_rev = float(rev.sum()) if rev is not None else None
    total_profit = float(profit.sum()) if profit is not None else None

    # margin is a WEIGHTED ratio (total profit / total revenue) over rows where BOTH exist.
    # Never the average of row-level margins, never mixing rows that only have one of the two.
    both = (rev.notna() & profit.notna()) if (rev is not None and profit is not None) else None
    base_rev = float(rev[both].sum()) if both is not None else total_rev
    margin = (float(profit[both].sum()) / base_rev * 100) if (both is not None and base_rev) else None

    issues: list[str] = []
    if raw_df is not None and len(raw_df) > len(df):
        n = len(raw_df) - len(df)
        dropped = raw_df[raw_df.duplicated()]
        amt = ""
        if cols["revenue"] and len(dropped):
            r_amt = _numeric(dropped[cols["revenue"]])
            if r_amt is not None and r_amt.sum():
                amt = f" (worth {fmt_money(float(r_amt.sum()), cur)} {cols['revenue']})"
        issues.append(f"{n} exact duplicate row(s) excluded from every figure{amt}.")
    if both is not None:
        mr, mp = int(rev.isna().sum()), int(profit.isna().sum())
        if mr or mp:
            issues.append(f"{mr} row(s) have no {cols['revenue']} and {mp} have no {cols['profit'] or 'profit'}; "
                          "margins use only rows where both exist.")

    headline = {
        "revenue": total_rev, "cost": float(cost.sum()) if cost is not None else None,
        "profit": total_profit, "margin_pct": margin, "rows": int(len(df)),
        "margin_basis_rows": int(both.sum()) if both is not None else None,
        "formatted": {
            "revenue": fmt_money(total_rev, cur) if total_rev is not None else None,
            "cost": fmt_money(float(cost.sum()), cur) if cost is not None else None,
            "profit": fmt_money(total_profit, cur) if total_profit is not None else None,
            "margin": f"{margin:.1f}%" if margin is not None else None,
        },
    }

    roles = detect_column_roles(df)
    exclude = {c for c in cols.values() if c}
    dims = _pick_dimensions(df, roles, pack, exclude)
    findings: list[dict] = []

    def add(**f):
        f.setdefault("counts_toward_total", True)
        f["impact_formatted"] = fmt_money(f["impact_amount"], cur)
        findings.append(f)

    # ---- 1. segment losses + margin gaps -----------------------------------
    seg_m = profit.where(both) if (mode == "full" and both is not None) else measure
    seg_r = rev.where(both) if (mode == "full" and both is not None) else (rev if rev is not None else measure)
    for dim in dims:
        g = pd.DataFrame({"k": df[dim].astype(str), "m": seg_m, "r": seg_r}).groupby("k").agg(
            m=("m", "sum"), r=("r", "sum"), n=("m", "size"))
        if mode == "full":
            for seg, row in g[g["m"] < 0].sort_values("m").head(3).iterrows():
                add(id=f"loss::{dim}::{seg}", family="segment_profit", type="loss", dimension=dim, segment=seg,
                    title=f"{dim} '{seg}' loses money",
                    impact_amount=abs(float(row["m"])), confidence=_confidence(int(row["n"])),
                    detail=f"{seg} ({dim}) has a net {measure_name} of {fmt_money(row['m'], cur)} over {int(row['n'])} rows.",
                    how=f"Sum of {measure_name} grouped by {dim}; negative segments flagged.")
            if margin is not None and base_rev:
                g["mg"] = np.where(g["r"] != 0, g["m"] / g["r"] * 100, np.nan)
                weak = g[(g["mg"] < margin - 5) & (g["m"] >= 0) & (g["r"] / base_rev >= 0.03)]
                for seg, row in weak.sort_values("mg").head(3).iterrows():
                    gap = (margin - row["mg"]) / 100 * row["r"]
                    add(id=f"gap::{dim}::{seg}", family="segment_profit", type="opportunity", dimension=dim,
                        segment=seg, title=f"{dim} '{seg}' margin is {margin - row['mg']:.1f} pts below average",
                        impact_amount=float(gap), confidence=_confidence(int(row["n"])),
                        detail=f"Margin {row['mg']:.1f}% vs overall {margin:.1f}% on {fmt_money(row['r'], cur)} revenue. "
                               f"Reaching the average margin would add {fmt_money(gap, cur)}.",
                        how=f"(overall margin − segment margin) × segment revenue, by {dim}.")
        else:
            share = g["r"] / g["r"].sum() if g["r"].sum() else None
            if share is not None and len(g) > 1 and share.max() > 0.5:
                seg = share.idxmax()
                add(id=f"conc::{dim}::{seg}", family="exposure", type="exposure", dimension=dim, segment=seg,
                    title=f"{share.max() * 100:.0f}% of revenue depends on {dim} '{seg}'",
                    impact_amount=float(g.loc[seg, "r"]), counts_toward_total=False, confidence="high",
                    detail=f"One {dim} holds {share.max() * 100:.0f}% of revenue — a single point of failure.",
                    how=f"Revenue share by {dim}.")

    # ---- 2. discount leakage ------------------------------------------------
    if cols["discount"] and rev is not None:
        d = _numeric(df[cols["discount"]]).fillna(0)
        mx = float(d.max()) if len(d) else 0
        if mx <= 1.0:
            frac, how = d.clip(0, 0.95), "revenue × d / (1 − d), discount as fraction of list price"
            leak = float((rev * frac / (1 - frac)).sum())
        elif mx <= 100:
            frac, how = (d / 100).clip(0, 0.95), "revenue × d / (1 − d), discount as % of list price"
            leak = float((rev * frac / (1 - frac)).sum())
        else:
            frac, how = None, "sum of discount amounts"
            leak = float(d.clip(lower=0).sum())
        if leak > 0.01 * (total_rev or 1):
            detail = f"Discounts gave away about {fmt_money(leak, cur)} ({leak / (total_rev + leak) * 100:.1f}% of list value)."
            if frac is not None and profit is not None:
                hi = frac >= 0.2
                if hi.sum() >= 5 and (~hi).sum() >= 5 and rev[hi].sum() and rev[~hi].sum():
                    m_hi = profit[hi].sum() / rev[hi].sum() * 100
                    m_lo = profit[~hi].sum() / rev[~hi].sum() * 100
                    detail += f" Orders with ≥20% discount earn {m_hi:.1f}% margin vs {m_lo:.1f}% otherwise."
            add(id="leak::discount", family="discount_leak", type="leak", title="Discount leakage",
                impact_amount=leak, confidence=_confidence(len(df)), detail=detail,
                how=f"{how} (column '{cols['discount']}').")

    # ---- 3. returns / refunds ------------------------------------------------
    if cols["returns"]:
        rr = _numeric(df[cols["returns"]]).fillna(0).clip(lower=0)
        if rr.sum() > 0:
            looks_like_amount = rev is not None and rr.sum() > 0.001 * (total_rev or 1)
            if looks_like_amount and rr.max() > 1.5:
                add(id="leak::returns", family="returns_leak", type="leak", title="Returns / refunds / write-offs",
                    impact_amount=float(rr.sum()), confidence=_confidence(len(df)),
                    detail=f"'{cols['returns']}' totals {fmt_money(rr.sum(), cur)} "
                           f"({rr.sum() / (total_rev or 1) * 100:.1f}% of revenue).",
                    how=f"Sum of '{cols['returns']}'.")
            elif rev is not None and rr.max() <= 1.5:
                lost = float((rev * (rr > 0)).sum())
                add(id="leak::returns", family="returns_leak", type="leak", title="Returned / failed orders",
                    impact_amount=lost, confidence=_confidence(len(df)),
                    detail=f"{int((rr > 0).sum())} flagged rows carry {fmt_money(lost, cur)} revenue.",
                    how=f"Revenue on rows where '{cols['returns']}' is set.")
    elif rev is not None and (rev < 0).any():
        neg_mask = rev < 0
        neg_sum = abs(float(rev[neg_mask].sum()))
        pos_sum = float(rev[rev > 0].sum()) if (rev > 0).any() else (total_rev or 1)
        if neg_sum > 0.001 * pos_sum:
            count_neg = int(neg_mask.sum())
            pct_gross = (neg_sum / pos_sum * 100) if pos_sum else 0
            add(
                id="leak::cancellations",
                family="returns_leak",
                type="leak",
                title="Returns and cancellations",
                impact_amount=neg_sum,
                confidence=_confidence(count_neg),
                detail=f"{count_neg:,} return/cancellation transaction(s) total {fmt_money(neg_sum, cur)} ({pct_gross:.1f}% of gross sales).",
                how="Sum of negative transaction values in revenue.",
            )

    # ---- 4. churn loss ---------------------------------------------------------
    if cols["churn"] and rev is not None:
        ch = _numeric(df[cols["churn"]]).fillna(0)
        flag = ch > 0 if ch.max() <= 1 else None
        if flag is not None and flag.any():
            lost = float(rev[flag].sum())
            add(id="loss::churn", family="churn_loss", type="loss", title="Revenue lost to churn",
                impact_amount=lost, confidence=_confidence(int(flag.sum())),
                detail=f"{int(flag.sum())} churned records ({flag.mean() * 100:.1f}%) carried {fmt_money(lost, cur)} revenue.",
                how=f"Revenue on rows flagged in '{cols['churn']}'.")

    # ---- 5. period change + anomalies -------------------------------------------
    if cols["date"]:
        ps = _period_series(df, cols["date"], measure)
        if ps is not None:
            ser, cnt, freq, per, ok, max_date = ps
            lbl = {"M": "month", "W": "week", "D": "day"}[freq]
            if freq == "M" and len(ser) >= 3:
                last_p = ser.index[-1]
                coverage = max_date.day / last_p.days_in_month
                if coverage < 0.6:
                    notes.append(f"Latest {lbl} {last_p} only runs to {max_date.date()} — excluded from the comparison.")
                    ser, cnt = ser.iloc[:-1], cnt.iloc[:-1]
            enough_periods = len(ser) >= (3 if freq == "M" else 6)
            enough_rows = len(ser) >= 2 and cnt.iloc[-1] >= 5 and cnt.iloc[-2] >= 5
            if not enough_periods:
                notes.append(f"Only {len(ser)} {lbl}(s) of history — too short for a reliable period comparison.")
            elif not enough_rows:
                notes.append(f"Fewer than 5 records per {lbl} — period-over-period changes would be noise, so none are reported.")
            else:
                last, prev = float(ser.iloc[-1]), float(ser.iloc[-2])
                delta = last - prev
                conf = "medium" if len(ser) < 6 else "high"
                if delta < 0 and abs(prev) > 0:
                    idx = ok[ok].index
                    best = None
                    for dim in dims:
                        sub = pd.DataFrame({"k": df.loc[idx, dim].astype(str), "m": measure.loc[idx]})
                        a_ = sub[per == ser.index[-1]].groupby("k")["m"].sum()
                        b_ = sub[per == ser.index[-2]].groupby("k")["m"].sum()
                        dd = a_.sub(b_, fill_value=0).sort_values()
                        if len(dd) and dd.iloc[0] < 0 and (best is None or dd.iloc[0] < best[2]):
                            best = (dim, dd.index[0], float(dd.iloc[0]))
                    extra = ""
                    if best:
                        extra = (f" Biggest driver: {best[0]} '{best[1]}' ({fmt_money(best[2], cur)}, "
                                 f"{best[2] / delta * 100:.0f}% of the decline).")
                    add(id="loss::decline", family="decline", type="loss",
                        title=f"{measure_name.title()} fell {abs(delta / prev) * 100:.1f}% vs previous {lbl}",
                        impact_amount=abs(delta), confidence=conf,
                        detail=f"{ser.index[-1]}: {fmt_money(last, cur)} vs {ser.index[-2]}: {fmt_money(prev, cur)}.{extra}",
                        how=f"Latest vs previous {lbl} {measure_name}; driver = largest negative segment change.")
                elif delta > 0 and abs(prev) > 0:
                    add(id="trend::growth", family="trend", type="trend", counts_toward_total=False,
                        title=f"{measure_name.title()} grew {delta / abs(prev) * 100:.1f}% vs previous {lbl}",
                        impact_amount=delta, confidence=conf,
                        detail=f"{ser.index[-2]}: {fmt_money(prev, cur)} → {ser.index[-1]}: {fmt_money(last, cur)}.",
                        how=f"Latest vs previous {lbl} {measure_name}.")
                if len(ser) >= 6:
                    med = float(ser.median())
                    mad = float((ser - med).abs().median()) or float(ser.std() or 1)
                    z = (ser - med) / (1.4826 * mad)
                    for p_ in z[z.abs() > 3.5].index[:2]:
                        v = float(ser[p_])
                        add(id=f"anom::{p_}", family="anomaly", type="anomaly", counts_toward_total=False,
                            title=f"Unusual {measure_name} in {p_}", impact_amount=abs(v - med), confidence="medium",
                            detail=f"{p_} was {fmt_money(v, cur)} vs typical {fmt_money(med, cur)}.",
                            how="Robust z-score (median/MAD) over period totals, |z| > 3.5.")

    # ---- rank + total ----------------------------------------------------------
    findings.sort(key=lambda f: f["impact_amount"], reverse=True)
    findings = findings[:max_findings]
    for i, f in enumerate(findings, 1):
        f["rank"] = i

    fam_max: dict[str, float] = {}
    for f in findings:
        if f["counts_toward_total"]:
            fam_max[f["family"]] = max(fam_max.get(f["family"], 0), f["impact_amount"])
    total = float(sum(fam_max.values()))
    if not findings:
        notes.append("No loss-making segments, leakage or declines detected with the available columns.")
    notes = issues + notes

    return {
        "mode": mode, "currency": cur, "measure": measure_name, "detected": cols, "headline": headline,
        "capabilities": capabilities, "data_issues": issues,
        "findings": findings, "total_at_stake": total, "total_at_stake_formatted": fmt_money(total, cur),
        "total_note": "Upper bound: biggest finding per category (segment, discount, returns, churn, decline) summed.",
        "dimensions_scanned": dims, "notes": notes, "pack": pack["id"],
    }


# -------------------------------------------------------------- sensitivity


def sensitivity_analysis(df: pd.DataFrame, pack_id=None, ctx=None, currency=DEFAULT_CURRENCY,
                         price_changes=None, volume_changes=None, cost_change_pct: float = 0.0,
                         elasticity: float | None = None, variable_cost_share: float = 1.0) -> dict:
    """Profit grid over price × volume. Cost scales with volume (variable_cost_share of it)."""
    cols = detect_financial_columns(df, pack_id, ctx)
    rev = _numeric(df[cols["revenue"]]) if cols["revenue"] else None
    cost = _numeric(df[cols["cost"]]) if cols["cost"] else None
    if cost is None and rev is not None and cols["profit"]:
        cost = rev - _numeric(df[cols["profit"]])
        cols["cost"] = f"{cols['revenue']} - {cols['profit']}"
    if rev is None or cost is None:
        raise ValueError("Sensitivity needs both a revenue-like and a cost-like column. "
                         "Map them in Business Context (metrics 'revenue' and 'cost').")
    R, C = float(rev.sum()), float(cost.sum())
    price_changes = price_changes or [-10, -5, 0, 5, 10]
    volume_changes = volume_changes or [-10, -5, 0, 5, 10]
    vcs = min(max(variable_cost_share, 0), 1)

    def profit(p, v):
        if elasticity is not None:
            v = v + elasticity * p
        rev_n = R * (1 + p / 100) * (1 + v / 100)
        cost_n = C * ((1 - vcs) + vcs * (1 + v / 100)) * (1 + cost_change_pct / 100)
        return rev_n - cost_n

    grid = [[round(profit(p, v), 2) for v in volume_changes] for p in price_changes]
    base = R - C
    flat = [(grid[i][j], price_changes[i], volume_changes[j]) for i in range(len(price_changes))
            for j in range(len(volume_changes))]
    best, worst = max(flat), min(flat)
    # break-even price change at zero volume change
    be = None
    for p in np.linspace(-50, 50, 2001):
        if profit(float(p), 0) >= 0:
            be = float(p)
            break
    return {
        "currency": currency, "revenue_col": cols["revenue"], "cost_col": cols["cost"],
        "base_revenue": R, "base_cost": C, "base_profit": base,
        "base_profit_formatted": fmt_money(base, currency),
        "price_changes_pct": price_changes, "volume_changes_pct": volume_changes,
        "profit_grid": grid, "cost_change_pct": cost_change_pct, "elasticity": elasticity,
        "variable_cost_share": vcs,
        "best_case": {"price_pct": best[1], "volume_pct": best[2], "profit": best[0],
                      "profit_formatted": fmt_money(best[0], currency),
                      "uplift_formatted": fmt_money(best[0] - base, currency)},
        "worst_case": {"price_pct": worst[1], "volume_pct": worst[2], "profit": worst[0],
                       "profit_formatted": fmt_money(worst[0], currency),
                       "change_formatted": fmt_money(worst[0] - base, currency)},
        "break_even_price_change_pct": be,
        "assumptions": f"Cost scales with volume ({vcs * 100:.0f}% variable). "
                       + (f"Volume responds to price with elasticity {elasticity}." if elasticity is not None
                          else "Volume independent of price (no elasticity)."),
        "charts": [{"type": "bar", "title": "Profit by price change (volume unchanged)",
                    "x": [f"{p:+d}%" for p in price_changes],
                    "y": [grid[i][volume_changes.index(0)] if 0 in volume_changes else grid[i][0]
                          for i in range(len(price_changes))]}],
    }
