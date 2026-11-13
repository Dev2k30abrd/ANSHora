"""
Independent Ground Truth Calculator for Anshora Benchmark Suite.
Calculates ground truth using standard mathematical and statistical definitions
(via Pandas and NumPy) completely independent of Anshora application code.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "test_data" / "benchmark"
OUTPUT_FILE = Path(__file__).resolve().parent / "ground_truth.json"


def _calc_data_health(df: pd.DataFrame) -> dict:
    rows = len(df)
    cols = len(df.columns)
    dup_count = int(df.duplicated().sum())
    dup_pct = round(dup_count / rows * 100, 2) if rows > 0 else 0.0
    missing_pct = round(float(df.isnull().mean().mean() * 100), 2)
    missing_by_col = {c: int(df[c].isnull().sum()) for c in df.columns if df[c].isnull().sum() > 0}
    
    # IQR outliers across numeric columns
    num_df = df.select_dtypes(include="number")
    outlier_counts = {}
    for c in num_df.columns:
        s = num_df[c].dropna()
        if len(s) < 4:
            continue
        q1, q3 = s.quantile(0.25), s.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            n_outliers = int(((s < lower) | (s > upper)).sum())
            if n_outliers > 0:
                outlier_counts[c] = n_outliers

    return {
        "rows": rows,
        "columns": cols,
        "duplicate_rows": dup_count,
        "duplicate_percentage": dup_pct,
        "overall_missing_percentage": missing_pct,
        "missing_columns": missing_by_col,
        "outlier_counts": outlier_counts
    }


def _calc_descriptive(df: pd.DataFrame, metric_col: str, group_cols: list[str] = None) -> dict:
    s = pd.to_numeric(df[metric_col], errors="coerce").dropna()
    res = {
        "metric": metric_col,
        "count": int(len(s)),
        "sum": round(float(s.sum()), 2),
        "mean": round(float(s.mean()), 2),
        "median": round(float(s.median()), 2),
        "std": round(float(s.std()), 2) if len(s) > 1 else 0.0,
        "min": round(float(s.min()), 2),
        "max": round(float(s.max()), 2),
    }
    if group_cols:
        res["groups"] = {}
        for gc in group_cols:
            if gc in df.columns:
                g = df.groupby(gc)[metric_col].sum().round(2).to_dict()
                res["groups"][gc] = {str(k): float(v) for k, v in g.items()}
    return res


def compute_ground_truth() -> dict:
    gt = {}

    # -------------------------------------------------------------
    # 1. Retail Sales
    # -------------------------------------------------------------
    df_retail = pd.read_csv(BENCHMARK_DIR / "01_retail_sales.csv")
    gt["01_retail_sales"] = {
        "data_health": _calc_data_health(df_retail),
        "descriptive": _calc_descriptive(df_retail, "revenue", ["category", "region"]),
        "diagnostic": {},
        "decision_intelligence": {}
    }
    # Diagnostics: Category profit analysis
    cat_profit = df_retail.groupby("category")["profit"].sum().round(2).to_dict()
    gt["01_retail_sales"]["diagnostic"]["category_profit"] = {str(k): float(v) for k, v in cat_profit.items()}
    gt["01_retail_sales"]["diagnostic"]["lowest_profit_category"] = min(cat_profit, key=cat_profit.get)
    # Decision: Return leakage & discount leakage
    returns_loss = round(float(df_retail[df_retail["returned"] == 1]["revenue"].sum()), 2)
    tot_discounts = round(float(df_retail["discount"].sum()), 2)
    tot_profit = round(float(df_retail["profit"].sum()), 2)
    gt["01_retail_sales"]["decision_intelligence"]["returns_revenue_loss"] = returns_loss
    gt["01_retail_sales"]["decision_intelligence"]["total_discounts_granted"] = tot_discounts
    gt["01_retail_sales"]["decision_intelligence"]["total_profit"] = tot_profit

    # -------------------------------------------------------------
    # 2. Financial P&L
    # -------------------------------------------------------------
    df_pnl = pd.read_csv(BENCHMARK_DIR / "02_financial_pnl.csv")
    tot_rev = round(float(df_pnl["revenue"].sum()), 2)
    tot_cogs = round(float(df_pnl["cogs"].sum()), 2)
    tot_gp = round(float(df_pnl["gross_profit"].sum()), 2)
    tot_opex = round(float(df_pnl["opex"].sum()), 2)
    tot_ebitda = round(float(df_pnl["ebitda"].sum()), 2)
    tot_np = round(float(df_pnl["net_profit"].sum()), 2)
    
    gt["02_financial_pnl"] = {
        "data_health": _calc_data_health(df_pnl),
        "financial": {
            "total_revenue": tot_rev,
            "total_cogs": tot_cogs,
            "total_gross_profit": tot_gp,
            "gross_margin_pct": round(tot_gp / tot_rev * 100, 2),
            "total_opex": tot_opex,
            "total_ebitda": tot_ebitda,
            "ebitda_margin_pct": round(tot_ebitda / tot_rev * 100, 2),
            "total_net_profit": tot_np,
            "net_margin_pct": round(tot_np / tot_rev * 100, 2),
        },
        "descriptive": _calc_descriptive(df_pnl, "net_profit")
    }

    # -------------------------------------------------------------
    # 3. Customer E-commerce
    # -------------------------------------------------------------
    df_cust = pd.read_csv(BENCHMARK_DIR / "03_customer_ecommerce.csv")
    churned = df_cust[df_cust["churn_flag"] == 1]
    churn_loss = round(float(churned["total_spend"].sum()), 2)
    churn_rate_pct = round(len(churned) / len(df_cust) * 100, 2)
    gt["03_customer_ecommerce"] = {
        "data_health": _calc_data_health(df_cust),
        "descriptive": _calc_descriptive(df_cust, "total_spend", ["acquisition_channel"]),
        "decision_intelligence": {
            "churned_customers_count": int(len(churned)),
            "churn_rate_percentage": churn_rate_pct,
            "revenue_at_risk_churn": churn_loss,
            "total_customer_revenue": round(float(df_cust["total_spend"].sum()), 2)
        }
    }

    # -------------------------------------------------------------
    # 4. Inventory Supply Chain
    # -------------------------------------------------------------
    df_inv = pd.read_csv(BENCHMARK_DIR / "04_inventory_supply_chain.csv")
    tot_holding = round(float(df_inv["total_holding_cost"].sum()), 2)
    tot_lost_sales = round(float(df_inv["lost_sales_estimate"].sum()), 2)
    stockout_skus = int((df_inv["stockout_events"] > 0).sum())
    gt["04_inventory_supply_chain"] = {
        "data_health": _calc_data_health(df_inv),
        "descriptive": _calc_descriptive(df_inv, "stock_on_hand", ["category", "warehouse"]),
        "decision_intelligence": {
            "total_holding_cost": tot_holding,
            "total_lost_sales_stockout": tot_lost_sales,
            "stockout_sku_count": stockout_skus
        }
    }

    # -------------------------------------------------------------
    # 5. Time-Series Monthly
    # -------------------------------------------------------------
    df_ts = pd.read_csv(BENCHMARK_DIR / "05_timeseries_monthly.csv")
    x = np.arange(len(df_ts))
    y = df_ts["revenue"].values
    slope, intercept = np.polyfit(x, y, 1)
    fitted = slope * x + intercept
    residuals = y - fitted
    std_resid = float(np.std(residuals)) if len(residuals) > 1 else 0.0
    
    # 6-period ahead forecasts
    next_x = np.arange(len(df_ts), len(df_ts) + 6)
    forecast_points = [round(float(slope * nx + intercept), 2) for nx in next_x]
    
    gt["05_timeseries_monthly"] = {
        "data_health": _calc_data_health(df_ts),
        "descriptive": _calc_descriptive(df_ts, "revenue"),
        "forecasting": {
            "historical_periods": len(df_ts),
            "trend_slope": round(float(slope), 2),
            "trend_intercept": round(float(intercept), 2),
            "residual_std": round(std_resid, 2),
            "next_period_forecast": forecast_points[0],
            "forecast_6_periods": forecast_points,
            "confidence_band_half_width": round(1.96 * std_resid, 2)
        }
    }

    # -------------------------------------------------------------
    # 6. Data Quality Challenge
    # -------------------------------------------------------------
    df_dq = pd.read_csv(BENCHMARK_DIR / "06_data_quality_challenge.csv")
    gt["06_data_quality_challenge"] = {
        "data_health": _calc_data_health(df_dq)
    }

    return gt


def main():
    gt = compute_ground_truth()
    OUTPUT_FILE.write_text(json.dumps(gt, indent=2), encoding="utf-8")
    print(f"Ground truth written successfully to ground_truth.json ({len(gt)} datasets computed).")


if __name__ == "__main__":
    main()
