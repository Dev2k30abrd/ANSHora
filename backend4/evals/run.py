"""
Golden-question regression suite.  Usage:   python -m evals.run  [--file evals/golden.json]
Runs each question against the bundled sample dataset using whatever LLM is configured
(demo brain if no key) and reports: tool routing, figure verification rate, latency.
Exit code 1 if any case fails — wire it into CI before changing prompts or models.
"""
import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from app.agents.agent import run_agent  # noqa: E402
from app.core import db  # noqa: E402
from app.core.context import workspace_scope  # noqa: E402
from app.services.dataset_manager import dataset_store  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(ROOT / "evals" / "golden.json"))
    ap.add_argument("--csv", default=str(ROOT / "test_data" / "sales_data.csv"))
    ap.add_argument("--pack", default="retail")
    a = ap.parse_args()

    db.init_db()
    cases = json.loads(Path(a.file).read_text())
    failures = 0
    with workspace_scope("eval-workspace"):
        ds = dataset_store.create(pd.read_csv(a.csv), "eval.csv", pack_id=a.pack)
        print(f"{'question':44} {'tools':32} {'verified':9} {'conf':5} ms")
        for c in cases:
            t0 = time.time()
            try:
                r = run_agent(c["q"], ds)
                tools = [t["name"] for t in r["tool_runs"] if t["ok"]]
                score = r["verification"]["score"]
                ok = all(t in tools for t in c.get("expect_tools", [])) and score >= c.get("min_verified", 0)
                row = (c["q"][:43], ",".join(tools)[:31], f"{score:.2f}", r["confidence"]["score"])
            except Exception as e:  # noqa: BLE001
                ok, row = False, (c["q"][:43], f"ERROR {str(e)[:25]}", "-", "-")
            failures += 0 if ok else 1
            print(f"{row[0]:44} {row[1]:32} {row[2]:9} {str(row[3]):5} {int((time.time() - t0) * 1000)} {'PASS' if ok else 'FAIL'}")
        dataset_store.delete(ds)
    print(f"\n{len(cases) - failures}/{len(cases)} passed")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
