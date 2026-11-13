"""
Shared deterministic analytics core.

This is the ONLY place trend/period-comparison and segment-comparison
math is implemented. Auto Dashboard, Proactive Insights, Root Cause,
and Executive Reports all call INTO these functions instead of each
re-implementing their own version — that was the root cause of the
Dashboard vs Proactive Insights numbers disagreeing: two independent
implementations of "percent change" and "outperformance ratio" that
used different denominators/aggregations/period splits.

No LLM involved anywhere in this file — every number is pandas/numpy.
"""

import numpy as np
import pandas as pd


def pick_resample_frequency(date_series: pd.Series) -> str:
    """
    The single frequency-selection rule used everywhere a time series
    gets bucketed. Keeping this in one function guarantees the Dashboard
    trend chart and the Proactive Insights trend detector bucket the
    exact same way (both call this), so their numbers can't diverge.

    Tuned for how people actually talk about business trends ("Jan vs
    Mar", "this quarter vs last") rather than for chart-pixel density:
    a ~90 day span should bucket into 3 MONTHS (so "first vs last"
    really does mean Jan vs Mar), not 13 weeks that then need averaging.
    """

    span_days = (date_series.max() - date_series.min()).days
    if span_days <= 31:
        return "D"
    if span_days <= 400:
        return "ME"
    return "QE"


def resample_time_series(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    aggregation: str = "sum",
    freq: str | None = None,
) -> tuple[pd.Series, str]:
    """
    Canonical time-bucketing. Returns (resampled_series, freq_used).
    aggregation defaults to "sum" because that's what a dashboard KPI
    total means, and trend/percent-change claims should agree with the
    dashboard's totals — not silently switch to a per-row average.
    """

    working = df[[date_column, value_column]].copy()
    working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
    working = working.dropna(subset=[date_column, value_column]).sort_values(date_column)

    if working.empty:
        return pd.Series(dtype=float), freq or "D"

    chosen_freq = freq or pick_resample_frequency(working[date_column])
    grouped = working.set_index(date_column)[value_column].resample(chosen_freq)
    series = getattr(grouped, aggregation)()

    return series, chosen_freq


def period_over_period_change(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    aggregation: str = "sum",
) -> dict | None:
    """
    THE canonical "did this metric go up or down, and by how much"
    calculation. Compares actual calendar periods (e.g. Jan vs Mar if
    there are 3 monthly buckets), never a row-count split — a dataset
    with more rows in one period than another would otherwise skew a
    positional 50/50 split into a meaningless number.

    Returns None if there isn't enough time history to compare two
    real periods.
    """

    series, freq = resample_time_series(df, date_column, value_column, aggregation)
    series = series[series.notna()]

    if len(series) < 2:
        return None

    # few buckets (e.g. 3 months of monthly data) -> compare first vs
    # last bucket exactly, which is what "Jan vs Mar" actually means.
    # many buckets (e.g. two years of daily data) -> compare the
    # average of the first half of PERIODS vs the second half of
    # PERIODS (still bucket-based, never row-count based).
    if len(series) <= 6:
        first_value = float(series.iloc[0])
        last_value = float(series.iloc[-1])
        first_label = str(series.index[0])
        last_label = str(series.index[-1])
    else:
        half = len(series) // 2
        first_value = float(series.iloc[:half].mean())
        last_value = float(series.iloc[half:].mean())
        first_label = f"first {half} periods (avg)"
        last_label = f"last {len(series) - half} periods (avg)"

    if first_value == 0:
        change_pct = None
    else:
        change_pct = (last_value - first_value) / abs(first_value) * 100

    return {
        "metric": value_column,
        "frequency": freq,
        "periods_compared": len(series),
        "first_period_label": first_label,
        "first_period_value": round(first_value, 2),
        "last_period_label": last_label,
        "last_period_value": round(last_value, 2),
        "change_percentage": round(change_pct, 2) if change_pct is not None else None,
        "aggregation": aggregation,
    }


def segment_comparison(
    df: pd.DataFrame,
    metric_column: str,
    dimension_column: str,
) -> dict | None:
    """
    THE canonical "how does each segment compare to the overall
    average" calculation — used for root-cause driver ranking AND
    opportunity/risk detection, so both agree on the same ratio.

    Deliberately mean-based (per-row average within the segment vs the
    per-row average overall), not sum-based: a segment with far more
    rows will always have a bigger SUM without necessarily performing
    better per unit, which was the earlier bug (an "outperforms by 7.1x"
    claim that was really just "has more rows").
    """

    if dimension_column not in df.columns or metric_column not in df.columns:
        return None

    overall_mean = df[metric_column].mean()
    if pd.isna(overall_mean) or overall_mean == 0:
        return None

    grouped = df.groupby(dimension_column)[metric_column].agg(["mean", "sum", "count"])
    grouped = grouped[grouped["count"] > 0]

    if grouped.empty:
        return None

    segments = []
    for segment_name, row in grouped.iterrows():
        segment_mean = float(row["mean"])
        segments.append({
            "segment": str(segment_name),
            "mean": round(segment_mean, 2),
            "sum": round(float(row["sum"]), 2),
            "row_count": int(row["count"]),
            "deviation_from_overall_percentage": round((segment_mean - overall_mean) / overall_mean * 100, 2),
            "ratio_vs_overall": round(segment_mean / overall_mean, 2) if overall_mean else None,
        })

    segments.sort(key=lambda s: s["deviation_from_overall_percentage"], reverse=True)

    return {
        "metric": metric_column,
        "dimension": dimension_column,
        "overall_mean": round(float(overall_mean), 2),
        "segments": segments,
    }


def concentration_share(df: pd.DataFrame, metric_column: str, dimension_column: str) -> dict | None:
    """
    THE canonical "how much of the total pie does the top segment hold"
    calculation. Deliberately SUM-based (concentration is genuinely
    about share of the total), kept separate from segment_comparison's
    mean-based performance ratio — these are two different questions
    and were previously conflated into one misleading number.
    """

    if dimension_column not in df.columns or metric_column not in df.columns:
        return None

    grouped = df.groupby(dimension_column)[metric_column].sum().sort_values(ascending=False)
    # denominator = ALL rows, including rows whose segment label is blank, so
    # "X% of total" always agrees with the dashboard total
    total = df[metric_column].sum()
    unassigned = float(total - grouped.sum())

    if total == 0 or len(grouped) == 0:
        return None

    top_segment = grouped.index[0]
    top_share_pct = float(grouped.iloc[0] / total * 100)

    return {
        "metric": metric_column,
        "dimension": dimension_column,
        "top_segment": str(top_segment),
        "top_segment_total": round(float(grouped.iloc[0]), 2),
        "overall_total": round(float(total), 2),
        "top_share_percentage": round(top_share_pct, 2),
        "segment_count": int(len(grouped)),
        "unassigned_total": round(unassigned, 2),
        "unassigned_percentage": round(unassigned / float(total) * 100, 2) if total else 0.0,
    }


def calculate_deterministic_kpis(df: pd.DataFrame, pack_id: str | None = None, ctx: dict | None = None) -> dict:
    """
    Central deterministic calculation for all headline KPIs.
    Strictly enforces weighted margin, missing cost guards, and division-by-zero protection.
    Shared across chat facts, dashboard, reports, exports, and profit engines.
    """
    from app.services.profit_engine import _numeric, detect_financial_columns

    cols = detect_financial_columns(df, pack_id, ctx)
    rows_total = len(df)
    
    rev_col = cols.get("revenue")
    cost_col = cols.get("cost")
    profit_col = cols.get("profit")
    disc_col = cols.get("discount")
    ret_col = cols.get("returns")
    qty_col = cols.get("quantity")

    rev_s = _numeric(df[rev_col]) if rev_col and rev_col in df.columns else None
    cost_s = _numeric(df[cost_col]) if cost_col and cost_col in df.columns else None
    profit_s = _numeric(df[profit_col]) if profit_col and profit_col in df.columns else None
    disc_s = _numeric(df[disc_col]) if disc_col and disc_col in df.columns else None
    ret_s = _numeric(df[ret_col]) if ret_col and ret_col in df.columns else None
    qty_s = _numeric(df[qty_col]) if qty_col and qty_col in df.columns else None

    # Derive profit if rev & cost present
    if profit_s is None and rev_s is not None and cost_s is not None:
        profit_s = rev_s - cost_s
        derived_profit = True
    else:
        derived_profit = False

    # Derive cost if rev & profit present
    if cost_s is None and rev_s is not None and profit_s is not None:
        cost_s = rev_s - profit_s
        derived_cost = True
    else:
        derived_cost = False

    total_rev = float(rev_s.sum()) if rev_s is not None else None
    total_cost = float(cost_s.sum()) if cost_s is not None else None
    total_profit = float(profit_s.sum()) if profit_s is not None else None
    total_disc = float(disc_s.sum()) if disc_s is not None else None
    total_returns = float(ret_s.sum()) if ret_s is not None else None
    total_qty = float(qty_s.sum()) if qty_s is not None else None

    # Weighted margin: profit sum / revenue sum on rows where both are non-null
    margin_pct = None
    if rev_s is not None and profit_s is not None:
        valid_mask = rev_s.notna() & profit_s.notna() & (rev_s != 0)
        valid_rev = rev_s[valid_mask].sum()
        valid_prof = profit_s[valid_mask].sum()
        if valid_rev > 0:
            margin_pct = round(float((valid_prof / valid_rev) * 100), 2)

    # Weighted discount pct: total discount / (total revenue + total discount) or total revenue
    discount_pct = None
    if total_disc is not None and total_rev is not None and (total_rev + total_disc) > 0:
        discount_pct = round(float(total_disc / (total_rev + total_disc) * 100), 2)

    return {
        "columns": {
            "revenue": rev_col,
            "cost": cost_col,
            "profit": profit_col,
            "discount": disc_col,
            "returns": ret_col,
            "quantity": qty_col,
        },
        "capabilities": {
            "has_revenue": total_rev is not None,
            "has_cost": total_cost is not None,
            "has_profit": total_profit is not None,
            "has_discount": total_disc is not None,
            "has_returns": total_returns is not None,
            "can_measure_loss": (total_profit is not None or total_cost is not None),
            "derived_profit": derived_profit,
            "derived_cost": derived_cost,
        },
        "totals": {
            "revenue": total_rev,
            "cost": total_cost,
            "profit": total_profit,
            "margin_pct": margin_pct,
            "discount": total_disc,
            "discount_pct": discount_pct,
            "returns": total_returns,
            "quantity": total_qty,
            "row_count": rows_total,
        },
        "integrity_notes": [
            *(["Cost data is missing; segment profitability or losses cannot be calculated."] if (total_cost is None and total_profit is None) else []),
            *(["Discounts cannot be calculated: no discount column found."] if total_disc is None else []),
            *(["Returns cannot be calculated: no return column found."] if total_returns is None else []),
        ],
    }

