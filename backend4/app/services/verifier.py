"""
Claim verifier — the 'Verified Analyst' core.

Every number in the model's answer is matched against numbers that actually
appear in the tool results (including formatted forms such as ₹1.26 L, 12.5%,
1,234). Numbers the model derived (sums, differences, ratios of two tool
numbers) count as 'derived'. Anything else is flagged as unverified.
Fully deterministic: no LLM involved.
"""
import itertools
import math
import re

_UNIT = {"k": 1e3, "l": 1e5, "lakh": 1e5, "lakhs": 1e5, "cr": 1e7, "crore": 1e7, "crores": 1e7,
         "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}

_NUM = re.compile(
    r"(?P<cur>[₹$€£])?\s?(?P<neg>[-−–])?\s?(?P<num>\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"\s?(?P<unit>cr(?:ore)?s?|lakhs?|mn|million|bn|billion|[klmb](?![a-z]))?(?P<pct>\s?%)?",
    re.I,
)
_DATEISH = re.compile(r"\b(19|20)\d{2}[-/]\d{1,2}([-/]\d{1,2})?\b|\b\d{1,2}[-/]\d{1,2}[-/](19|20)?\d{2}\b")


def _to_float(num: str, unit: str | None) -> float:
    v = float(num.replace(",", ""))
    if unit:
        v *= _UNIT.get(unit.lower(), 1)
    return v


def numbers_in_text(text: str) -> list[dict]:
    text = _DATEISH.sub(" ", text or "")
    out = []
    for m in _NUM.finditer(text):
        raw = m.group(0).strip()
        try:
            val = _to_float(m.group("num"), m.group("unit"))
        except ValueError:
            continue
        if m.group("neg"):
            val = -val
        # ignore list ordinals like "1." at line start and small bare integers
        start = m.start()
        line_start = text.rfind("\n", 0, start) + 1
        if re.fullmatch(r"\s*\d{1,2}[.)]\s*", text[line_start:m.end() + 1] or "") and not m.group("pct") and not m.group("cur"):
            continue
        bare_small = (not m.group("cur") and not m.group("pct") and not m.group("unit")
                      and "." not in m.group("num") and abs(val) <= 10)
        year = (not m.group("cur") and not m.group("pct") and "," not in m.group("num")
                and "." not in m.group("num") and 1900 <= abs(val) <= 2100)
        if bare_small or year:
            continue
        dec = len(m.group("num").split(".")[1]) if "." in m.group("num") else 0
        out.append({"text": raw, "value": val, "decimals": dec, "pct": bool(m.group("pct")),
                    "scaled": bool(m.group("unit"))})
    return out


def collect_numbers(obj, out=None, depth=0) -> set:
    if out is None:
        out = set()
    if depth > 8:
        return out
    if isinstance(obj, bool) or obj is None:
        return out
    if isinstance(obj, (int, float)):
        f = float(obj)
        if math.isfinite(f):
            out.add(f)
    elif isinstance(obj, str):
        for n in numbers_in_text(obj) if len(obj) < 400 else []:
            out.add(n["value"])
        for m in re.finditer(r"\d+(?:\.\d+)?", obj if len(obj) < 400 else ""):
            out.add(float(m.group(0)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k in ("evidence",):
                continue
            collect_numbers(v, out, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj[:1500]:
            collect_numbers(v, out, depth + 1)
    return out


def _close(a: float, t: float, decimals: int, scaled: bool, strict: bool = False) -> bool:
    if t == a:
        return True
    tol_abs = 0.5 * (10 ** -decimals) * 1.001
    if abs(a - t) <= tol_abs:
        return True
    if strict:  # derived numbers (sums/ratios of two results) must match tightly to count
        rel = 0.02 if scaled else 0.004
    else:
        rel = 0.06 if scaled else 0.012  # unit-abbreviated numbers are coarser (₹1.26 L)
    return abs(t) > 0 and abs(a - t) / abs(t) <= rel


def verify_answer(answer: str, tool_results: list[dict]) -> dict:
    claims = numbers_in_text(answer)
    if not claims:
        return {"status": "no_numbers", "checked": 0, "verified": 0, "derived": 0, "unverified": [], "score": 1.0}

    pool: set[float] = set()
    for r in tool_results:
        collect_numbers(r, pool)
    base = [v for v in pool if math.isfinite(v)]
    # percent view of ratios (0.125 -> 12.5) and absolute values
    views = set(base) | {abs(v) for v in base} | {v * 100 for v in base if abs(v) <= 1.5}
    derived_pool = sorted((v for v in views if abs(v) >= 1), key=abs, reverse=True)[:90]

    verified = derived = 0
    unverified = []
    for c in claims:
        a = c["value"]
        cands = (a, abs(a)) if a < 0 else (a,)
        if any(_close(x, t, c["decimals"], c["scaled"]) for x in cands for t in views):
            verified += 1
            continue
        hit = False
        for t1, t2 in itertools.combinations(derived_pool, 2):
            for d in (t1 + t2, abs(t1 - t2)):
                if _close(abs(a), d, c["decimals"], c["scaled"], strict=True):
                    hit = True
                    break
            if not hit and t2 != 0 and (c["pct"] or True):
                for d in (t1 / t2 * 100, t2 / t1 * 100 if t1 else None, t1 / t2):
                    if d is not None and _close(abs(a), abs(d), c["decimals"], c["scaled"], strict=True):
                        hit = True
                        break
            if hit:
                break
        if hit:
            derived += 1
        else:
            unverified.append({"text": c["text"], "value": a})

    n = len(claims)
    score = (verified + 0.7 * derived) / n
    status = "verified" if not unverified else ("partial" if score >= 0.6 else "unverified")
    return {"status": status, "checked": n, "verified": verified, "derived": derived,
            "unverified": unverified[:12], "score": round(score, 3)}


def confidence_score(verification: dict, rows: int, health_score: float | None,
                     tool_runs: list[dict]) -> dict:
    reasons = []
    v = verification["score"] if verification["status"] != "no_numbers" else 0.85
    if verification["status"] == "no_numbers":
        reasons.append("Answer states no figures to verify.")
    elif verification["status"] == "verified":
        reasons.append("Every figure traced to the computed results.")
    else:
        reasons.append(f"{len(verification['unverified'])} figure(s) could not be traced to the results.")

    size = 1.0 if rows >= 1000 else 0.8 if rows >= 100 else 0.6 if rows >= 30 else 0.3
    if rows < 100:
        reasons.append(f"Small sample ({rows} rows).")

    health = (health_score / 100) if health_score is not None else 0.8
    if health_score is not None and health_score < 70:
        reasons.append(f"Data quality score is {health_score:.0f}/100.")

    if verification.get("unsupported"):
        v = min(v, 0.4)
        reasons.append("The answer discusses something this dataset has no column for.")
    errs = sum(1 for t in tool_runs if not t.get("ok"))
    recov = sum(1 for t in tool_runs if t.get("ok") and t.get("result", {}).get("_guard_notes"))
    clean = max(0.0, 1.0 - 0.35 * errs - 0.15 * recov)
    if errs:
        reasons.append(f"{errs} analysis step(s) failed and were worked around.")
    if recov:
        reasons.append("Column choices were auto-corrected.")

    score = round(100 * (0.45 * v + 0.2 * size + 0.2 * health + 0.15 * clean))
    label = "High" if score >= 80 else "Medium" if score >= 60 else "Low"
    return {"score": score, "label": label, "reasons": reasons}


# ----------------------------------------------------------------- unsupported claims
_ROLE_WORDS = {
    "discount": re.compile(r"\b(discount\w*|coupon\w*|promo\w*|markdown\w*|rebate\w*)\b", re.I),
    "returns": re.compile(r"\b(returns?|returned|refunds?|rto|chargebacks?)\b", re.I),
    "churn": re.compile(r"\b(churn\w*|attrition|cancell?ations?)\b", re.I),
    "cost": re.compile(r"\b(loss(?:es)?|negative profit|operating at a loss|net loss|cost of goods|cogs)\b", re.I),
}
_NEGATION = re.compile(
    r"\b(no|not|none|cannot|can't|can not|isn't|aren't|doesn't|don't|without|missing|lack\w*|unavailable|absent|"
    r"unable|never|nor|add a|would need|if you add|once you add)\b|n't", re.I)
_HAS_FIGURE = re.compile(r"[₹$€£]\s?\d|\d+(?:[.,]\d+)?\s?(?:%|k\b|l\b|lakh|cr\b|crore|m\b|mn|bn)|\d{3,}", re.I)


def unsupported_claims(answer: str, capabilities: dict | None) -> list[dict]:
    """Sentences that quantify discount/returns/churn although the dataset has no such column.
    A negation only excuses the claim when it sits right next to the concept word
    ("no discount column", "discount leakage cannot be measured")."""
    if not capabilities:
        return []
    out = []
    for sent in re.split(r"(?<=[.!?])\s+|\n+", answer or ""):
        if not sent.strip() or not _HAS_FIGURE.search(sent):
            continue
        for role, rx in _ROLE_WORDS.items():
            if role == "cost":
                if capabilities.get("cost") is not None or capabilities.get("profit") is not None:
                    continue
            elif capabilities.get(role) is not None:
                continue
            flagged = False
            for m in rx.finditer(sent):
                window = sent[max(0, m.start() - 35): m.end() + 35]
                if not _NEGATION.search(window):
                    flagged = True
                    break
            if flagged:
                out.append({"role": role, "sentence": sent.strip()[:240]})
                break
    return out
