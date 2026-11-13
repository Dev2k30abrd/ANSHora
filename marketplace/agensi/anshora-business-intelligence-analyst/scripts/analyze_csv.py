#!/usr/bin/env python3
"""ANSHora — BI Analyst CSV Helper (v1.0.3). Pure stdlib. Read-only JSON output."""

import argparse, csv, json, math, re, sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HINTS = {k: v.split() for k, v in [("rev", "revenue sales turnover gmv amount"), ("cost", "cost cogs expense purchase"),
    ("prof", "profit margin"), ("disc", "discount"), ("ret", "return refund"), ("date", "date invoice time created"),
    ("ord", "order invoice transaction"), ("id", "id uuid sku code")]}
NULL_WORDS = {"null", "none", "nan", "n/a", "na", "-", ""}
CURR_SYMS = ("$", "€", "₹", "£", "¥")
CURR_CODES = "USD EUR INR GBP CAD AUD JPY CNY CHF".split()
CURR_NORM = {"€": "EUR", "₹": "INR", "£": "GBP"}
CURR_RE = re.compile(r"[,\s$€₹£¥%]|(?<![a-zA-Z])(?:USD|EUR|INR|GBP|CAD|AUD|JPY|CNY|CHF)(?![a-zA-Z])", re.I)
DATE_FMTS = ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m")
r2 = lambda x: round(x, 2) if x is not None else None
r4 = lambda x: round(x, 4) if x is not None else None


def detect_currencies_in_strings(strings):
    found = set()
    for s in strings:
        if not s: continue
        st = str(s)
        for sym in CURR_SYMS:
            if sym in st: found.add(CURR_NORM.get(sym, sym))
        for code in CURR_CODES:
            if re.search(r"(?<![a-zA-Z])" + code + r"(?![a-zA-Z])", st, re.I): found.add(code)
    return sorted(found)


def clean_number(val):
    if val is None: return None
    s = str(val).strip()
    if not s or s.lower() in NULL_WORDS: return None
    try:
        f = float(CURR_RE.sub("", s).strip())
        return f if math.isfinite(f) else None
    except ValueError:
        return None


def parse_date(val):
    if not val: return None
    s = str(val).strip()
    if not s: return None
    for fmt in DATE_FMTS:
        try: return datetime.strptime(s, fmt)
        except (ValueError, TypeError): continue
    m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    return datetime(int(m[1]), int(m[2]), int(m[3])) if m else None


def detect_delimiter(sample):
    if not sample: return ","
    try: return csv.Sniffer().sniff(sample[:4096], delimiters=",;\t|").delimiter
    except Exception:
        c = {d: sample.count(d) for d in (",", "\t", ";", "|")}
        return max(c, key=c.get) if max(c.values()) > 0 else ","


def calculate_quantiles(s):
    n = len(s)
    if not n: return {k: None for k in "min q1 median q3 max iqr".split()}
    def q(p):
        k = (n - 1) * p
        f, c = int(k), math.ceil(k)
        return s[f] if f == c else s[f] * (c - k) + s[c] * (k - f)
    q1, med, q3 = q(0.25), q(0.5), q(0.75)
    return {"min": r4(s[0]), "q1": r4(q1), "median": r4(med), "q3": r4(q3), "max": r4(s[-1]), "iqr": r4(q3 - q1)}


def find_column_match(headers, hints, exp=None):
    if exp: return next((h for h in headers if h.strip().lower() == exp.strip().lower()), None)
    norm = {re.sub(r"\W", "", h.lower()): h for h in headers}
    for hint in hints:
        ch = re.sub(r"\W", "", hint.lower())
        if ch in norm: return norm[ch]
        m = next((orig for nh, orig in norm.items() if ch in nh), None)
        if m: return m
    return None


def select_profit_method(rows, rev_c, cst_c, prf_c, exp=None):
    if exp in ("direct", "direct_profit"): return "direct_profit"
    if exp in ("derived", "derived_profit"): return "derived_profit"
    if prf_c and not cst_c: return "direct_profit"
    if cst_c and not prf_c: return "derived_profit"
    if prf_c and cst_c:
        nd = sum(1 for r in rows if clean_number(r.get(rev_c)) is not None and clean_number(r.get(prf_c)) is not None)
        nc = sum(1 for r in rows if clean_number(r.get(rev_c)) is not None and clean_number(r.get(cst_c)) is not None)
        return "direct_profit" if nd >= nc and nd > 0 else ("derived_profit" if nc > 0 else None)
    return None


def compute_kpis_for_rows(rows, rev_c, cst_c, prf_c, ord_c, method=None):
    raw_fin = [r[c] for c in (rev_c, cst_c, prf_c) if c for r in rows if r.get(c)]
    curr = detect_currencies_in_strings(raw_fin)
    mixed = len(curr) > 1

    v_revs = [clean_number(r[rev_c]) for r in rows if clean_number(r.get(rev_c)) is not None] if rev_c else []
    tot_rev = sum(v_revs) if v_revs else (0.0 if rev_c and rows else None)

    res = {
        "unique_orders_count": None, "total_revenue": None, "total_cost": None, "total_profit": None,
        "weighted_margin_pct": None, "average_order_value": None, "line_item_average": None,
        "profit_method": None, "cost_source": None, "profit_source": None, "row_count": len(rows),
        "aov_type": "line_item_average", "paired_valid_rows": 0, "unpaired_revenue_rows": len(v_revs),
        "unpaired_cost_rows": 0, "inferred_cost_rows": 0, "currencies_detected": curr,
        "detected_currency": curr[0] if len(curr) == 1 else None,
        "currency_status": "mixed_currencies_detected" if mixed else ("single_currency_detected" if len(curr) == 1 else "unspecified"),
        "zero_revenue_rows": sum(1 for v in v_revs if v == 0), "negative_revenue_rows": sum(1 for v in v_revs if v < 0),
    }
    if mixed:
        res["aov_type"] = "blocked_mixed_currencies"
        return res

    res["total_revenue"] = r2(tot_rev)
    res["line_item_average"] = res["average_order_value"] = r2(tot_rev / max(len(v_revs), 1)) if tot_rev is not None else None

    chosen_m = method or select_profit_method(rows, rev_c, cst_c, prf_c)
    res["profit_method"] = chosen_m
    p_rev, p_prof, p_cost = [], [], []
    unp_r, unp_c, inf_c = 0, 0, 0

    for r in rows:
        rv, pv, cv = (clean_number(r.get(c)) if c else None for c in (rev_c, prf_c, cst_c))
        if rv is not None:
            if chosen_m == "direct_profit" and pv is not None:
                p_rev.append(rv); p_prof.append(pv)
                if cv is not None: p_cost.append(cv)
                else: p_cost.append(rv - pv); inf_c += 1
            elif chosen_m == "derived_profit" and cv is not None:
                p_rev.append(rv); p_cost.append(cv); p_prof.append(rv - cv)
            elif chosen_m is not None:
                unp_r += 1
        elif (chosen_m == "direct_profit" and pv is not None) or (chosen_m == "derived_profit" and cv is not None):
            unp_c += 1

    n_p = len(p_rev)
    res["paired_valid_rows"], res["unpaired_revenue_rows"], res["unpaired_cost_rows"], res["inferred_cost_rows"] = n_p, unp_r, unp_c, inf_c

    if chosen_m and n_p > 0:
        res["total_profit"], res["total_cost"] = r2(sum(p_prof)), r2(sum(p_cost))
        s_r = sum(p_rev)
        res["weighted_margin_pct"] = r2((res["total_profit"] / s_r) * 100) if s_r > 0 else None
        if chosen_m == "direct_profit":
            res["profit_source"] = f"direct from column '{prf_c}'"
            res["cost_source"] = "derived (revenue - profit)" if (not cst_c or inf_c > 0) else f"direct from column '{cst_c}'"
        else:
            res["profit_source"] = "derived (revenue - cost)"
            res["cost_source"] = f"direct from column '{cst_c}'"

    if ord_c and rev_c:
        o_tot = defaultdict(float)
        for r in rows:
            if r.get(ord_c):
                rv = clean_number(r.get(rev_c))
                if rv is not None: o_tot[r[ord_c]] += rv
        if o_tot:
            res["unique_orders_count"] = len(o_tot)
            res["average_order_value"] = r2(sum(o_tot.values()) / max(len(o_tot), 1))
            res["aov_type"] = "unique_orders"

    return res


def analyze(file_path, revenue_col=None, cost_col=None, profit_col=None, date_col=None, order_id_col=None, method=None, dimensions=None, top_n=10):
    path = Path(file_path)
    if not path.exists() or not path.is_file():
        return {"error": f"File not found or not regular file: {file_path}", "status": "failed"}

    empty_res = lambda m: {"status": "success", "file_name": path.name, "row_count": 0, "column_count": 0, "columns": [],
                          "message": m, "data_quality": {"empty": True, "health_score": 0.0, "health_status": "Empty Dataset"}}
    try:
        with open(path, "rb") as bf:
            sample = bf.read(16384)
        if not sample: return empty_res("File is empty (0 bytes).")
        has_bom = sample.startswith(b"\xef\xbb\xbf")
        enc = "utf-8-sig" if has_bom else "utf-8"
        delim = detect_delimiter(sample.decode(enc, errors="replace"))
    except Exception as e:
        return {"error": f"Could not read file: {e}", "status": "failed"}

    rows, seen, dup_rows, u_rows = [], set(), [], []
    try:
        with open(path, "r", encoding=enc, errors="replace") as f:
            reader = csv.reader(f, delimiter=delim)
            first = next(reader, None)
            if first is None: return empty_res("File contains no rows.")
            headers = [h.strip() for h in first if h.strip()]
            if not headers: return {"error": "CSV contains no valid non-empty headers.", "status": "failed"}
            ncols = len(headers)
            for raw in reader:
                pad = tuple((raw + [""] * ncols)[:ncols])
                rd = {headers[i]: pad[i].strip() for i in range(ncols)}
                (dup_rows if pad in seen else u_rows).append(rd)
                seen.add(pad)
                rows.append(rd)
    except Exception as e:
        return {"error": f"CSV read error: {e}", "status": "failed"}

    rcnt = len(rows)
    miss_cnt, miss_pct, num_cols, date_cols, cat_cols, type_contam = {}, {}, {}, {}, {}, {}

    for h in headers:
        vals = [r[h] for r in rows]
        ecnt = sum(1 for v in vals if not v or v.lower() in NULL_WORDS)
        miss_cnt[h], miss_pct[h] = ecnt, r2((ecnt / max(rcnt, 1)) * 100)
        nums = [clean_number(v) for v in vals]
        v_nums = [n for n in nums if n is not None]
        vn = max(len(vals) - ecnt, 1)
        dates = [d for d in (parse_date(v) for v in vals) if d is not None]
        is_id = any(hint in h.lower() for hint in HINTS["id"])
        type_contam[h] = sum(1 for v, n in zip(vals, nums) if n is None and v and v.lower() not in NULL_WORDS)
        if len(dates) / vn >= 0.75 and not is_id: date_cols[h] = dates
        elif (len(v_nums) / vn >= 0.65 or (revenue_col and h.lower() == revenue_col.lower())) and not is_id: num_cols[h] = v_nums
        else: cat_cols[h] = vals

    rev_c = find_column_match(headers, HINTS["rev"], revenue_col)
    cst_c = find_column_match(headers, HINTS["cost"], cost_col)
    prf_c = find_column_match(headers, HINTS["prof"], profit_col)
    dt_c = find_column_match(headers, HINTS["date"], date_col)
    ord_c = find_column_match(headers, HINTS["ord"], order_id_col)
    disc_c = find_column_match(headers, HINTS["disc"])
    ret_c = find_column_match(headers, HINTS["ret"])

    if prf_c == rev_c: prf_c = None
    if cst_c == rev_c: cst_c = None

    num_sums, tot_outliers = {}, 0
    for col, nums in num_cols.items():
        if not nums: continue
        n_c, s_nums = len(nums), sorted(nums)
        q = calculate_quantiles(s_nums)
        iqr = q["iqr"]
        if n_c < 4: lb = ub = None
        elif iqr > 0: lb, ub = q["q1"] - 1.5 * iqr, q["q3"] + 1.5 * iqr
        else:
            mu = sum(nums) / n_c
            sd = math.sqrt(sum((x - mu) ** 2 for x in nums) / max(n_c - 1, 1))
            lb, ub = (s_nums[0], s_nums[-1]) if sd == 0 else (mu - 2.5 * sd, mu + 2.5 * sd)
        ocnt = sum(1 for n in nums if (n < lb or n > ub)) if lb is not None else 0
        tot_outliers += ocnt
        num_sums[col] = {"valid_count": n_c, "missing_count": miss_cnt[col], "sum": r4(sum(nums)),
            "mean": r4(sum(nums) / n_c), "quantiles": q, "outliers_count": ocnt, "outlier_bounds": {"lower": r4(lb), "upper": r4(ub)}}

    avg_m, dup_cnt = sum(miss_pct.values()) / max(len(miss_pct), 1), len(dup_rows)
    dup_pct, out_pct = (dup_cnt / max(rcnt, 1)) * 100, (tot_outliers / max(rcnt * max(len(num_sums), 1), 1)) * 100
    contam_cells = sum(type_contam[c] for c in num_cols)
    contam_pct = (contam_cells / max(rcnt * max(len(num_cols), 1), 1)) * 100
    p_m, p_d, p_o, p_t = min(40.0, round(avg_m * 1.5, 2)), min(30.0, round(dup_pct * 2.0, 2)), min(20.0, round(out_pct * 1.0, 2)), min(10.0, round(contam_pct * 1.0, 2))
    score = max(0.0, min(100.0, round(100.0 - (p_m + p_d + p_o + p_t), 1)))
    status = "High Reliability" if score >= 85 else ("Acceptable (Caveats Disclosed)" if score >= 70 else "Needs Review (High Risk of Skewed Findings)")

    chosen_method = select_profit_method(rows, rev_c, cst_c, prf_c, method)
    kpi_all = compute_kpis_for_rows(rows, rev_c, cst_c, prf_c, ord_c, chosen_method)
    kpi_dedup = compute_kpis_for_rows(u_rows, rev_c, cst_c, prf_c, ord_c, chosen_method) if dup_cnt > 0 else kpi_all
    kpi_dups = compute_kpis_for_rows(dup_rows, rev_c, cst_c, prf_c, ord_c, chosen_method) if dup_cnt > 0 else None

    d_r, d_c, d_p = (kpi_dups["total_revenue"] or 0.0, kpi_dups["total_cost"] or 0.0, kpi_dups["total_profit"] or 0.0) if kpi_dups else (0.0, 0.0, 0.0)

    fin_kpis = {
        "revenue_column": rev_c, "cost_column": cst_c, "profit_column": prf_c,
        "date_column": dt_c, "order_id_column": ord_c, "discount_column": disc_c, "return_column": ret_c,
        "profit_calculation_policy": chosen_method, "all_rows": kpi_all, "deduplicated": kpi_dedup,
        "duplicate_exposure": {
            "exact_duplicate_rows": dup_cnt, "duplicate_revenue": r2(d_r),
            "duplicate_cost": r2(d_c), "duplicate_profit": r2(d_p),
        },
        **{k: kpi_all[k] for k in "currencies_detected currency_status detected_currency total_revenue total_cost total_profit weighted_margin_pct average_order_value aov_type line_item_average cost_source profit_source paired_valid_rows unpaired_revenue_rows unpaired_cost_rows inferred_cost_rows zero_revenue_rows negative_revenue_rows".split()}
    }

    def row_p(r):
        rv, pv, cv = (clean_number(r.get(c)) if c else None for c in (rev_c, prf_c, cst_c))
        if rv is None: return None, None
        if chosen_method == "direct_profit" and pv is not None:
            return pv, cv if cv is not None else rv - pv
        if chosen_method == "derived_profit" and cv is not None:
            return rv - cv, cv
        return None, None

    def sub_kpis(subset):
        r_tot = sum(clean_number(r[rev_c]) for r in subset if clean_number(r.get(rev_c)) is not None) if rev_c else None
        vp = [p for p, _ in (row_p(r) for r in subset) if p is not None]
        vc = [c for _, c in (row_p(r) for r in subset) if c is not None]
        p_tot = r2(sum(vp)) if vp else None
        c_tot = r2(sum(vc)) if (chosen_method == "derived_profit" and vc) else None
        m_pct = r2((p_tot / r_tot) * 100) if (p_tot is not None and r_tot and r_tot > 0) else None
        return r_tot, c_tot, p_tot, m_pct

    t_dims = [h for d in dimensions for h in headers if h.strip().lower() == d.strip().lower()] if dimensions else [
        h for h, vals in cat_cols.items() if 2 <= len(set(filter(None, vals))) <= 25 and not any(w in h.lower() for w in HINTS["id"])
    ][:3]

    cs = kpi_all["currency_status"]
    seg_bd = {}
    tot_v_rev = fin_kpis["total_revenue"] or 1.0
    for dim in t_dims:
        d_items = []
        for cat, cnt in Counter(r[dim] for r in rows if r[dim]).most_common(top_n):
            c_rows = [r for r in rows if r[dim] == cat]
            cr, cc, cp, cm = sub_kpis(c_rows)
            item = {"segment_value": cat, "row_count": cnt, "row_share_pct": r2((cnt / max(rcnt, 1)) * 100)}
            if cr is not None and cs != "mixed_currencies_detected":
                item["revenue"] = r2(cr); item["revenue_share_pct"] = r2((cr / max(tot_v_rev, 1e-9)) * 100)
            for k, v in (("cost", cc), ("profit", cp), ("margin_pct", cm)):
                if v is not None: item[k] = v
            d_items.append(item)
        seg_bd[dim] = d_items

    t_series = []
    if dt_c and cs != "mixed_currencies_detected":
        p_grp = defaultdict(list)
        for r in rows:
            dto = parse_date(r.get(dt_c))
            if dto: p_grp[dto.strftime("%Y-%m")].append(r)
        prev_r = None
        for p in sorted(p_grp):
            pr_rows = p_grp[p]
            pr, pc, pp, pm = sub_kpis(pr_rows)
            p_grw = r2(((pr - prev_r) / prev_r) * 100) if (prev_r and prev_r > 0 and pr is not None) else None
            ent = {"period": p, "rows": len(pr_rows)}
            for k, v in [("revenue", r2(pr)), ("growth_vs_previous_period_pct", p_grw), ("cost", pc), ("profit", pp), ("margin_pct", pm)]:
                if v is not None: ent[k] = v
            t_series.append(ent)
            if pr is not None: prev_r = pr

    notices = [
        f"Dataset contains {rcnt:,} rows and {ncols} columns.",
        f"Financial calculation policy: Consistent '{chosen_method}' methodology applied without mixing row calculation bases.",
        "Overall weighted margin = (Total Profit ÷ Total Revenue × 100); row margins are never averaged.",
        f"Exact duplicate rows ({dup_cnt}) identified for audit transparency and not silently removed.",
    ]
    if cs == "mixed_currencies_detected":
        notices.append(f"Multiple currencies detected ({', '.join(kpi_all['currencies_detected'])}). Cross-currency summation blocked without exchange rates.")
    elif cs == "unspecified":
        notices.append("Currency is unspecified in source data; numerical totals represent raw unit amounts without assumed currency.")
    if dup_cnt and rev_c and d_r:
        notices.append(f"Duplicate revenue exposure: ${d_r:,.2f}. All-rows and deduplicated KPIs provided.")
    if kpi_all["unpaired_revenue_rows"]:
        notices.append(f"{kpi_all['unpaired_revenue_rows']} rows with revenue lacked supporting data under '{chosen_method}' and were excluded from profit/margin calculations.")
    if kpi_all.get("inferred_cost_rows"):
        notices.append(f"Cost derived as (revenue - profit) for {kpi_all['inferred_cost_rows']} row{'s' if kpi_all['inferred_cost_rows'] > 1 else ''} with missing cost data.")

    pen_dict = lambda pct, pen, cap, **kw: {"percentage": r2(pct), "penalty": pen, "cap": cap, **kw}
    return {
        "status": "success", "file_name": path.name, "delimiter": delim, "has_utf8_bom": has_bom,
        "row_count": rcnt, "total_raw_rows": rcnt, "column_count": ncols, "columns": headers,
        "data_quality": {
            "health_score": score, "health_status": status,
            "penalties": {"missing_values": pen_dict(avg_m, p_m, 40.0), "exact_duplicates": pen_dict(dup_pct, p_d, 30.0),
                          "statistical_outliers": pen_dict(out_pct, p_o, 20.0), "type_contamination": pen_dict(contam_pct, p_t, 10.0, contaminated_cells=contam_cells)},
            "exact_duplicate_rows": dup_cnt, "duplicate_percentage": r2(dup_pct),
            "duplicate_revenue_exposure": r2(d_r), "missing_values_by_column": miss_cnt,
            "missing_percentages": miss_pct, "total_outliers_detected": tot_outliers,
        },
        "capabilities": {
            "revenue_available": rev_c is not None, "cost_available": bool(cst_c or (rev_c and prf_c)),
            "profit_available": bool(prf_c or (rev_c and cst_c)), "date_timeline_available": bool(dt_c and len(t_series) >= 2),
            "order_id_available": ord_c is not None, "discount_available": disc_c is not None,
            "returns_available": ret_c is not None, "customer_segments_available": bool(seg_bd),
        },
        "financial_kpis": fin_kpis, "numeric_summaries": num_sums,
        "segment_breakdowns": seg_bd, "time_series": t_series, "analytical_notices": notices,
    }


def main():
    p = argparse.ArgumentParser(description="CSV Analysis Helper (v1.0.3)")
    p.add_argument("file_path")
    for f in "revenue cost profit date order-id dimensions".split(): p.add_argument(f"--{f}")
    p.add_argument("--method", choices=["direct", "derived"])
    p.add_argument("--top", type=int, default=10)
    a = p.parse_args()
    d = [x.strip() for x in a.dimensions.split(",")] if a.dimensions else None
    res = analyze(a.file_path, a.revenue, a.cost, a.profit, a.date, getattr(a, "order_id", None), a.method, d, a.top)
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
