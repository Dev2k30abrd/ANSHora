"""
Run LLM-written pandas code for questions the fixed tools can't answer.

Defense in depth, NOT a perfect jail: AST allow-list (no file/network/OS
access, no dunder tricks), restricted builtins, isolated subprocess with
CPU/memory/file limits and a hard timeout. For production multi-tenant use,
run the worker inside a container/gVisor/Firecracker with no network.
"""
import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from app.core.config import ENABLE_PYTHON_SANDBOX, SANDBOX_TIMEOUT

ALLOWED_IMPORTS = {"pandas", "numpy", "math", "statistics", "json", "datetime", "re", "collections",
                    "itertools", "functools", "decimal", "fractions"}
BLOCKED_NAMES = {"open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars",
                 "getattr", "setattr", "delattr", "breakpoint", "exit", "quit", "help", "memoryview",
                 "os", "sys", "subprocess", "socket", "shutil", "pathlib", "importlib", "builtins"}
BLOCKED_ATTRS = {"read_csv", "read_parquet", "read_pickle", "read_sql", "read_sql_query", "read_excel",
                 "read_json", "read_html", "read_clipboard", "read_table", "read_feather", "read_hdf",
                 "read_orc", "read_xml", "read_fwf", "to_csv", "to_parquet", "to_pickle", "to_sql",
                 "to_excel", "to_clipboard", "to_hdf", "to_feather", "to_json", "to_html", "to_xml",
                 "to_orc", "fromfile", "tofile", "load", "save", "savez", "loadtxt", "savetxt",
                 "genfromtxt", "memmap", "system", "popen", "environ", "eval", "query_engine"}

RUNNER = r'''
import sys, json, io, math, statistics, datetime, re, collections, itertools, functools, decimal, fractions
import builtins as _b
import numpy as np, pandas as pd
ALLOWED = set(%(allowed)r)
_real_import = _b.__import__
def _imp(name, globals=None, locals=None, fromlist=(), level=0):
    if name.split(".")[0] not in ALLOWED:
        raise ImportError("import of '%%s' is not allowed" %% name)
    return _real_import(name, globals, locals, fromlist, level)
SAFE = {k: getattr(_b, k) for k in ("abs all any bool dict enumerate filter float int isinstance issubclass "
    "len list map max min pow range reversed round set slice sorted str sum tuple zip print repr divmod "
    "format hash iter next chr ord bin hex oct callable id type frozenset bytes complex "
    "ValueError TypeError KeyError IndexError ZeroDivisionError Exception ArithmeticError StopIteration "
    "True False None").split() if hasattr(_b, k)}
SAFE["__import__"] = _imp
df = pd.read_parquet(sys.argv[1])
code = open(sys.argv[2]).read()
buf = io.StringIO()
real_out = sys.stdout
sys.stdout = buf
g = {"__builtins__": SAFE, "pd": pd, "np": np, "math": math, "statistics": statistics, "df": df.copy(), "result": None, "chart": None}
err = None
try:
    exec(compile(code, "<analysis>", "exec"), g)
except Exception as e:
    err = "%%s: %%s" %% (type(e).__name__, e)
sys.stdout = real_out

def conv(v, depth=0):
    if depth > 6: return str(v)
    if isinstance(v, pd.DataFrame):
        v = v.head(200)
        return {"columns": [str(c) for c in v.columns], "rows": [conv(r, depth+1) for r in v.to_dict(orient="records")]}
    if isinstance(v, pd.Series):
        return conv(v.head(200).to_dict(), depth+1)
    if isinstance(v, dict): return {str(k): conv(x, depth+1) for k, x in list(v.items())[:200]}
    if isinstance(v, (list, tuple, set)): return [conv(x, depth+1) for x in list(v)[:200]]
    if isinstance(v, (np.integer,)): return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v); return None if (math.isnan(f) or math.isinf(f)) else round(f, 6)
    if isinstance(v, (np.bool_,)): return bool(v)
    if v is None or isinstance(v, (bool, int, str)): return v
    return str(v)

out = {"error": err, "stdout": buf.getvalue()[:4000], "result": conv(g.get("result")), "chart": conv(g.get("chart"))}
sys.stdout.write("\n@@RESULT@@" + json.dumps(out, default=str))
'''


def validate_code(code: str):
    if len(code) > 8000:
        raise ValueError("Code too long (max 8000 chars). Simplify the analysis.")
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        raise ValueError(f"Syntax error in code: {e.msg} (line {e.lineno})")
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] not in ALLOWED_IMPORTS:
                    raise ValueError(f"Import '{a.name}' is not allowed. Allowed: {sorted(ALLOWED_IMPORTS)}")
        elif isinstance(node, ast.ImportFrom):
            if (node.module or "").split(".")[0] not in ALLOWED_IMPORTS:
                raise ValueError(f"Import from '{node.module}' is not allowed.")
        elif isinstance(node, ast.Name) and node.id in BLOCKED_NAMES:
            raise ValueError(f"Use of '{node.id}' is not allowed.")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__") or node.attr in BLOCKED_ATTRS:
                raise ValueError(f"Attribute '.{node.attr}' is not allowed.")
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            raise ValueError("global/nonlocal are not allowed.")


def _limits():
    try:
        import resource

        resource.setrlimit(resource.RLIMIT_CPU, (SANDBOX_TIMEOUT, SANDBOX_TIMEOUT))
        resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE, (10 * 1024**2, 10 * 1024**2))
        resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    except Exception:
        pass


def run_python(df: pd.DataFrame, code: str) -> dict:
    if not ENABLE_PYTHON_SANDBOX:
        raise ValueError("The Python analysis tool is disabled on this server (ENABLE_PYTHON_SANDBOX=false).")
    validate_code(code)
    with tempfile.TemporaryDirectory() as tmp:
        data_p, code_p, run_p = (Path(tmp) / n for n in ("d.parquet", "c.py", "r.py"))
        try:
            df.to_parquet(data_p, index=False)
        except Exception:
            safe = df.copy()
            for c in safe.columns:
                if safe[c].dtype == object:
                    safe[c] = safe[c].astype(str)
            safe.to_parquet(data_p, index=False)
        code_p.write_text(code)
        run_p.write_text(RUNNER % {"allowed": sorted(ALLOWED_IMPORTS)})
        env = {"PATH": os.environ.get("PATH", ""), "PYTHONHASHSEED": "0", "HOME": tmp}
        kw = {"preexec_fn": _limits} if os.name == "posix" else {}
        try:
            p = subprocess.run([sys.executable, "-I", str(run_p), str(data_p), str(code_p)], cwd=tmp, env=env,
                               capture_output=True, text=True, timeout=SANDBOX_TIMEOUT + 5, **kw)
        except subprocess.TimeoutExpired:
            raise ValueError(f"Analysis code timed out after {SANDBOX_TIMEOUT}s. Make it cheaper.")
    marker = "@@RESULT@@"
    if marker not in p.stdout and p.returncode in (-24, -9, -11, 137, 152):
        raise ValueError("Analysis code hit the CPU/memory limit. Make it cheaper (avoid huge loops/joins).")
    if marker not in p.stdout:
        tail = (p.stderr or p.stdout)[-400:]
        raise ValueError(f"Analysis code failed to run: {tail.strip() or 'no output'}")
    out = json.loads(p.stdout.split(marker, 1)[1])
    if out.get("error"):
        raise ValueError(f"Your code raised: {out['error']}. Columns: {', '.join(map(str, df.columns))}")
    res = {"code": code, "result": out["result"], "stdout": out["stdout"]}
    ch = out.get("chart")
    if isinstance(ch, dict) and ch.get("x") is not None and ch.get("y") is not None:
        res["charts"] = [{"type": ch.get("type", "bar"), "title": ch.get("title", "Analysis"),
                          "x": ch["x"], "y": ch["y"]}]
    return res
