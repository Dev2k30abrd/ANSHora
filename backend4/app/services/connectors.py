"""Data connectors: URL (CSV/JSON/Parquet/Google Sheets) and SQL (SQLAlchemy, read-only)."""
import io
import re
from urllib.parse import urlparse

import pandas as pd
import requests

from app.core.config import MAX_UPLOAD_MB
from app.core.netguard import assert_public_url
from app.tools.sql_tool import validate_sql

MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024


def _normalize_url(url: str) -> str:
    m = re.match(r"https://docs\.google\.com/spreadsheets/d/([^/]+)", url)
    if m:
        gid = re.search(r"[#&?]gid=(\d+)", url)
        return f"https://docs.google.com/spreadsheets/d/{m.group(1)}/export?format=csv" + (f"&gid={gid.group(1)}" if gid else "")
    return url


def fetch_url_dataframe(url: str) -> pd.DataFrame:
    url = _normalize_url(url)
    assert_public_url(url)
    r = requests.get(url, timeout=30, stream=True, allow_redirects=False)
    if 300 <= r.status_code < 400:
        loc = r.headers.get("location", "")
        assert_public_url(loc)
        r = requests.get(loc, timeout=30, stream=True, allow_redirects=False)
    r.raise_for_status()
    buf, size = io.BytesIO(), 0
    for chunk in r.iter_content(1024 * 256):
        size += len(chunk)
        if size > MAX_BYTES:
            raise ValueError(f"Remote file too large (limit {MAX_UPLOAD_MB} MB).")
        buf.write(chunk)
    buf.seek(0)
    path = urlparse(url).path.lower()
    if path.endswith(".parquet"):
        return pd.read_parquet(buf)
    if path.endswith(".json"):
        try:
            return pd.read_json(buf)
        except ValueError:
            buf.seek(0)
            return pd.read_json(buf, lines=True)
    if path.endswith((".xlsx", ".xls")):
        return pd.read_excel(buf)
    for enc in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            buf.seek(0)
            return pd.read_csv(buf, encoding=enc, sep=None, engine="python")
        except UnicodeDecodeError:
            continue
    raise ValueError("Could not parse the remote file as CSV/JSON/Parquet/Excel.")


def sql_dataframe(connection_url: str, query: str, max_rows: int = 500_000) -> pd.DataFrame:
    """Import a query result from Postgres/MySQL/SQLite/etc. SELECT-only; credentials are NOT stored."""
    from sqlalchemy import create_engine, text

    q = validate_sql(query)
    engine = create_engine(connection_url, connect_args={"connect_timeout": 10} if "sqlite" not in connection_url else {})
    try:
        with engine.connect() as conn:
            try:
                conn.execute(text("SET TRANSACTION READ ONLY")) if connection_url.startswith("postgres") else None
            except Exception:
                pass
            df = pd.read_sql_query(text(q), conn)
    finally:
        engine.dispose()
    if len(df) > max_rows:
        df = df.head(max_rows)
    return df
