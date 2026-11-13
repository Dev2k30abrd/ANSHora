"""Guarded read-only SQL over the dataset using DuckDB (table name: data)."""
import re

import duckdb
import numpy as np
import pandas as pd

from app.core.config import SQL_MAX_ROWS

_FORBIDDEN = re.compile(
    r"\b(attach|detach|copy|pragma|install|export|import|read_csv\w*|read_parquet|read_json\w*|read_text|"
    r"read_blob|glob|http_get|httpfs|sniff_csv|parquet_scan|csv_scan|json_scan|iceberg_scan|delta_scan|"
    r"sqlite_scan|postgres_scan|mysql_scan)\b",
    re.I,
)


def _strip_literals(q: str) -> str:
    q = re.sub(r"'(?:[^']|'')*'", "''", q)
    return re.sub(r'"(?:[^"]|"")*"', '""', q)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else round(f, 6)
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return str(v)
    if isinstance(v, (bool, int, str)):
        return v
    return str(v)


def validate_sql(query: str) -> str:
    q = (query or "").strip().rstrip(";").strip()
    if not q:
        raise ValueError("Empty SQL query.")
    bare = _strip_literals(q)
    if ";" in bare:
        raise ValueError("Only a single SQL statement is allowed.")
    if not re.match(r"^(select|with)\b", bare, re.I):
        raise ValueError("Only read-only SELECT / WITH queries are allowed.")
    if _FORBIDDEN.search(bare):
        raise ValueError("That SQL uses a function or statement that is not allowed (read-only mode).")
    return q


def run_sql(df: pd.DataFrame, query: str, max_rows: int | None = None) -> dict:
    max_rows = max_rows or SQL_MAX_ROWS
    q = validate_sql(query)
    con = duckdb.connect(":memory:")
    try:
        try:
            con.execute("SET enable_external_access=false")
        except Exception:
            pass
        con.register("data", df)
        try:
            out = con.execute(f"SELECT * FROM ({q}) AS _q LIMIT {max_rows + 1}").df()
        except duckdb.Error as e:
            raise ValueError(f"SQL error: {str(e).splitlines()[0]}. Table is named `data`; "
                             f"columns: {', '.join(map(str, df.columns))}")
    finally:
        con.close()
    truncated = len(out) > max_rows
    out = out.head(max_rows)
    rows = [{str(c): _clean(v) for c, v in r.items()} for r in out.to_dict(orient="records")]
    result = {
        "sql": q, "columns": [str(c) for c in out.columns], "rows": rows,
        "row_count": len(rows), "truncated": truncated,
    }
    # auto chart: one text/category column + one numeric column, small result
    num = [c for c in out.columns if pd.api.types.is_numeric_dtype(out[c])]
    cat = [c for c in out.columns if c not in num]
    if num and 1 < len(out) <= 30:
        xcol = cat[0] if cat else None
        result["charts"] = [{
            "type": "bar", "title": f"{num[0]}" + (f" by {xcol}" if xcol else ""),
            "x": [str(v) for v in (out[xcol] if xcol else range(len(out)))],
            "y": [_clean(v) for v in out[num[0]]],
        }]
    return result
