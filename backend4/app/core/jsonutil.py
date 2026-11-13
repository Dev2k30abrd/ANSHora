"""Make arbitrary analysis results JSON-safe (numpy, pandas, NaN, inf, datetimes)."""
import math

import numpy as np
import pandas as pd


def jsonable(v, depth=0):
    if depth > 12:
        return str(v)
    if v is None or isinstance(v, (bool, str)):
        return v
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (int,)):
        return v
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, (pd.Timestamp, np.datetime64)):
        return str(v)
    if isinstance(v, pd.Period):
        return str(v)
    if isinstance(v, pd.DataFrame):
        return jsonable(v.head(500).to_dict(orient="records"), depth + 1)
    if isinstance(v, pd.Series):
        return jsonable(v.head(500).to_dict(), depth + 1)
    if isinstance(v, dict):
        return {str(k): jsonable(x, depth + 1) for k, x in v.items()}
    if isinstance(v, (list, tuple, set)):
        return [jsonable(x, depth + 1) for x in v]
    return str(v)
