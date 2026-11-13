"""Suggest the best industry pack for a dataframe from its column names."""
import re

from app.packs import PACKS


def _toks(name):
    return set(t for t in re.split(r"[^a-z0-9&]+", re.sub(r"([a-z])([A-Z])", r"\1_\2", str(name)).lower()) if t)


def suggest_pack(df) -> dict:
    col_toks = [_toks(c) for c in df.columns]
    all_toks = set().union(*col_toks) if col_toks else set()
    scores = {}
    for pid, p in PACKS.items():
        if pid == "general":
            continue
        s = 0
        for role in ("revenue", "cost", "returns", "churn", "quantity", "discount"):
            for h in p["hints"].get(role, [])[:6]:
                if h in all_toks:
                    s += 1
        for d in p.get("dimensions", []):
            if d in all_toks:
                s += 1.5
        scores[pid] = s
    best = max(scores, key=scores.get) if scores else "general"
    if scores.get(best, 0) < 3:
        return {"pack_id": "general", "score": scores.get(best, 0), "scores": scores}
    return {"pack_id": best, "score": scores[best], "scores": scores}
