"""
Forecasting — feature 4.

Linear-trend forecast with residual-based confidence intervals. Kept
dependency-free (numpy/pandas only, no statsmodels/prophet) for a
reliable, fast MVP. Uses:
  - a linear regression trend line (numpy.polyfit) as the point forecast
  - the standard deviation of historical residuals to build a
    95% confidence band (±1.96 * residual_std, widening slightly
    further out to reflect growing uncertainty)
"""

import numpy as np
import pandas as pd


_FREQ_ALIASES = {"M": "ME", "Y": "YE", "A": "YE", "W": "W", "D": "D"}

MIN_RELIABLE_PERIODS = 6


def forecast_series(
    df: pd.DataFrame,
    date_column: str,
    value_column: str,
    periods: int = 6,
    freq: str = "M",
    exploratory: bool = False,
) -> dict:
    if date_column not in df.columns:
        raise ValueError(f"Column '{date_column}' not found.")
    if value_column not in df.columns:
        raise ValueError(f"Column '{value_column}' not found.")
    if not pd.api.types.is_numeric_dtype(df[value_column]):
        raise ValueError(f"Column '{value_column}' must be numeric.")

    freq = _FREQ_ALIASES.get(freq.upper(), freq)

    working = df[[date_column, value_column]].copy()
    working[date_column] = pd.to_datetime(working[date_column], errors="coerce")
    working = working.dropna().sort_values(date_column)

    if len(working) < 4:
        raise ValueError("Need at least 4 historical data points to build a forecast.")

    series = working.set_index(date_column)[value_column].resample(freq).sum()
    series = series.fillna(0)

    if len(series) < 3:
        raise ValueError("Not enough historical periods at this frequency to forecast reliably.")

    is_reliable = len(series) >= MIN_RELIABLE_PERIODS

    if not is_reliable and not exploratory:
        return {
            "reliable": False,
            "forecast_generated": False,
            "periods_available": len(series),
            "minimum_required_for_reliable_forecast": MIN_RELIABLE_PERIODS,
            "frequency": freq,
            "message": (
                f"Only {len(series)} historical period(s) are available at {freq} frequency — "
                f"that's too sparse for a reliable forecast (at least {MIN_RELIABLE_PERIODS} are "
                "recommended). Ask for an exploratory/rough estimate if you want a projection "
                "anyway, understanding it carries high uncertainty."
            ),
        }

    x = np.arange(len(series))
    y = series.values.astype(float)

    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residuals = y - fitted
    residual_std = float(np.std(residuals)) if len(residuals) > 1 else 0.0

    future_x = np.arange(len(series), len(series) + periods)
    forecast_values = slope * future_x + intercept

    forecast_labels = pd.date_range(start=series.index[-1], periods=periods + 1, freq=freq)[1:]

    lower_bound = []
    upper_bound = []
    for i, value in enumerate(forecast_values):
        widening = 1 + (i * 0.15)
        margin = 1.96 * residual_std * widening
        lower_bound.append(round(float(value - margin), 2))
        upper_bound.append(round(float(value + margin), 2))

    trend_direction = "upward" if slope > 0 else ("downward" if slope < 0 else "flat")

    result = {
        "reliable": is_reliable,
        "forecast_generated": True,
        "date_column": date_column,
        "value_column": value_column,
        "frequency": freq,
        "periods_forecasted": periods,
        "trend_direction": trend_direction,
        "trend_slope_per_period": round(float(slope), 4),
        "historical": {
            "labels": [str(idx.date()) for idx in series.index],
            "values": [round(float(v), 2) for v in y.tolist()],
        },
        "forecast": {
            "labels": [str(d.date()) for d in forecast_labels],
            "values": [round(float(v), 2) for v in forecast_values.tolist()],
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
        },
        "confidence_level": "95%",
        "method": "Linear trend regression with residual-based confidence interval",
        "chart": {
            "type": "line",
            "title": f"{value_column} forecast ({periods} periods ahead)",
            "labels": [str(idx.date()) for idx in series.index] + [str(d.date()) for d in forecast_labels],
            "series": [
                {
                    "name": "historical",
                    "data": [round(float(v), 2) for v in y.tolist()] + [None] * periods,
                },
                {
                    "name": "forecast",
                    "data": [None] * len(y) + [round(float(v), 2) for v in forecast_values.tolist()],
                },
            ],
        },
    }

    if not is_reliable:
        result["caveat"] = (
            f"This is an EXPLORATORY estimate only — just {len(series)} historical periods are "
            f"available, below the {MIN_RELIABLE_PERIODS} normally recommended for a reliable "
            "forecast. Treat this as a rough directional projection, not a dependable prediction."
        )

    return result
