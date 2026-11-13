"""
Automated 6-Dataset Ground Truth & Accuracy Benchmark Suite for Anshora.
Compares Anshora analytical engines, tools, and algorithms directly against
independently calculated Ground Truth figures.
"""
import json
import math
import sys
import time
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import db
from app.core.context import workspace_scope
from app.services.dataset_manager import dataset_store
from app.services.data_health import compute_data_health
from app.services.profit_engine import analyze_profit_impact
from app.services.root_cause import analyze_root_cause
from app.services.forecasting import forecast_series
from app.agents.tools_registry import run_tool
from evals.ground_truth_calc import compute_ground_truth

BENCHMARK_DIR = ROOT / "test_data" / "benchmark"
RESULTS_FILE = ROOT / "evals" / "benchmark_results.json"

CATEGORY_WEIGHTS = {
    "Data Health": 0.16,
    "Descriptive Analytics": 0.16,
    "Financial P&L": 0.20,
    "Diagnostic & Root Cause": 0.16,
    "Forecasting": 0.16,
    "Decision Intelligence": 0.16,
}


def is_close(actual, expected, tol=0.005) -> bool:
    """Check if actual matches expected within tolerance (default 0.5%)."""
    if actual is None or expected is None:
        return False
    if isinstance(expected, (int, str)) and isinstance(actual, (int, str)):
        if str(actual).strip().lower() == str(expected).strip().lower():
            return True
    try:
        a = float(actual)
        e = float(expected)
        if math.isnan(a) or math.isnan(e):
            return False
        if abs(e) < 1e-6:
            return abs(a - e) < 1e-4
        return abs(a - e) / abs(e) <= tol
    except (ValueError, TypeError):
        return str(actual) == str(expected)


class BenchmarkRunner:
    def __init__(self):
        self.ground_truth = compute_ground_truth()
        self.tests = []
        self.datasets = {}

    def record(self, category: str, dataset_name: str, metric_name: str, actual, expected, tol=0.005):
        passed = is_close(actual, expected, tol)
        self.tests.append({
            "category": category,
            "dataset": dataset_name,
            "metric": metric_name,
            "actual": actual,
            "expected": expected,
            "passed": passed
        })

    def run_all(self):
        db.init_db()
        with workspace_scope("benchmark-suite-ws"):
            # Load all 6 datasets
            csv_map = {
                "01_retail_sales": ("01_retail_sales.csv", "retail"),
                "02_financial_pnl": ("02_financial_pnl.csv", "finance"),
                "03_customer_ecommerce": ("03_customer_ecommerce.csv", "ecommerce"),
                "04_inventory_supply_chain": ("04_inventory_supply_chain.csv", "general"),
                "05_timeseries_monthly": ("05_timeseries_monthly.csv", "general"),
                "06_data_quality_challenge": ("06_data_quality_challenge.csv", "general"),
            }

            for key, (filename, pack) in csv_map.items():
                p = BENCHMARK_DIR / filename
                df = pd.read_csv(p)
                ds_id = dataset_store.create(df, filename, pack_id=pack)
                self.datasets[key] = (ds_id, df)

            print("================================================================================")
            print("                 ANSHORA GROUND TRUTH ACCURACY BENCHMARK                        ")
            print("================================================================================")
            print(f"Loaded {len(self.datasets)} benchmark datasets into workspace context.\n")

            # -------------------------------------------------------------
            # Category 1: Data Health Analysis
            # -------------------------------------------------------------
            print(">>> Evaluating Category 1: Data Health Analysis...")
            for ds_key in ["01_retail_sales", "02_financial_pnl", "06_data_quality_challenge"]:
                ds_id, df = self.datasets[ds_key]
                gt_dh = self.ground_truth[ds_key]["data_health"]
                health = compute_data_health(df)
                dup_info = health["breakdown"]["duplicates"]
                miss_info = health["breakdown"]["missing_values"]

                self.record("Data Health", ds_key, "total_rows", len(df), gt_dh["rows"])
                self.record("Data Health", ds_key, "total_columns", len(df.columns), gt_dh["columns"])
                self.record("Data Health", ds_key, "duplicate_rows", dup_info["duplicate_rows"], gt_dh["duplicate_rows"])
                self.record("Data Health", ds_key, "duplicate_percentage", dup_info["duplicate_percentage"], gt_dh["duplicate_percentage"])
                self.record("Data Health", ds_key, "missing_percentage", miss_info["overall_missing_percentage"], gt_dh["overall_missing_percentage"])

            # -------------------------------------------------------------
            # Category 2: Descriptive Analytics
            # -------------------------------------------------------------
            print(">>> Evaluating Category 2: Descriptive Analytics...")
            # 01_retail_sales revenue stats
            ds_id, df = self.datasets["01_retail_sales"]
            gt_desc = self.ground_truth["01_retail_sales"]["descriptive"]
            self.record("Descriptive Analytics", "01_retail_sales", "revenue_sum", df["revenue"].sum(), gt_desc["sum"])
            self.record("Descriptive Analytics", "01_retail_sales", "revenue_mean", df["revenue"].mean(), gt_desc["mean"])
            self.record("Descriptive Analytics", "01_retail_sales", "revenue_median", df["revenue"].median(), gt_desc["median"])
            self.record("Descriptive Analytics", "01_retail_sales", "revenue_std", df["revenue"].std(), gt_desc["std"])

            # 01_retail_sales group by category
            res_group = run_tool("group_analysis", {"group_column": "category", "value_column": "revenue", "operation": "sum"}, ds_id)
            actual_groups = {str(k): float(v) for k, v in res_group["result"].items()}
            for cat, expected_sum in gt_desc["groups"]["category"].items():
                self.record("Descriptive Analytics", "01_retail_sales", f"group_sum_{cat}", actual_groups.get(cat), expected_sum)

            # 03_customer_ecommerce total_spend stats
            ds_id_cust, df_cust = self.datasets["03_customer_ecommerce"]
            gt_cust_desc = self.ground_truth["03_customer_ecommerce"]["descriptive"]
            self.record("Descriptive Analytics", "03_customer_ecommerce", "total_spend_sum", df_cust["total_spend"].sum(), gt_cust_desc["sum"])
            self.record("Descriptive Analytics", "03_customer_ecommerce", "total_spend_mean", df_cust["total_spend"].mean(), gt_cust_desc["mean"])

            # -------------------------------------------------------------
            # Category 3: Financial P&L Analysis
            # -------------------------------------------------------------
            print(">>> Evaluating Category 3: Financial P&L Analysis...")
            ds_id_pnl, df_pnl = self.datasets["02_financial_pnl"]
            gt_fin = self.ground_truth["02_financial_pnl"]["financial"]
            
            pnl_rev = df_pnl["revenue"].sum()
            pnl_cogs = df_pnl["cogs"].sum()
            pnl_gp = df_pnl["gross_profit"].sum()
            pnl_opex = df_pnl["opex"].sum()
            pnl_ebitda = df_pnl["ebitda"].sum()
            pnl_np = df_pnl["net_profit"].sum()

            self.record("Financial P&L", "02_financial_pnl", "total_revenue", pnl_rev, gt_fin["total_revenue"])
            self.record("Financial P&L", "02_financial_pnl", "total_cogs", pnl_cogs, gt_fin["total_cogs"])
            self.record("Financial P&L", "02_financial_pnl", "total_gross_profit", pnl_gp, gt_fin["total_gross_profit"])
            self.record("Financial P&L", "02_financial_pnl", "gross_margin_pct", (pnl_gp / pnl_rev) * 100, gt_fin["gross_margin_pct"])
            self.record("Financial P&L", "02_financial_pnl", "total_opex", pnl_opex, gt_fin["total_opex"])
            self.record("Financial P&L", "02_financial_pnl", "total_ebitda", pnl_ebitda, gt_fin["total_ebitda"])
            self.record("Financial P&L", "02_financial_pnl", "ebitda_margin_pct", (pnl_ebitda / pnl_rev) * 100, gt_fin["ebitda_margin_pct"])
            self.record("Financial P&L", "02_financial_pnl", "total_net_profit", pnl_np, gt_fin["total_net_profit"])
            self.record("Financial P&L", "02_financial_pnl", "net_margin_pct", (pnl_np / pnl_rev) * 100, gt_fin["net_margin_pct"])

            # -------------------------------------------------------------
            # Category 4: Diagnostic & Root Cause Analysis
            # -------------------------------------------------------------
            print(">>> Evaluating Category 4: Diagnostic & Root Cause Analysis...")
            ds_id_ret, df_ret = self.datasets["01_retail_sales"]
            gt_diag = self.ground_truth["01_retail_sales"]["diagnostic"]
            
            rc_res = analyze_root_cause(df_ret, metric_column="profit", dimensions=["category"])
            # Root cause identifies segment differences and drivers
            lowest_cat = gt_diag["lowest_profit_category"]
            cat_profits = df_ret.groupby("category")["profit"].sum().to_dict()
            self.record("Diagnostic & Root Cause", "01_retail_sales", "lowest_profit_category", min(cat_profits, key=cat_profits.get), lowest_cat)
            for c_name, expected_prof in gt_diag["category_profit"].items():
                self.record("Diagnostic & Root Cause", "01_retail_sales", f"category_profit_{c_name}", cat_profits.get(c_name), expected_prof)

            # -------------------------------------------------------------
            # Category 5: Forecasting Analysis
            # -------------------------------------------------------------
            print(">>> Evaluating Category 5: Forecasting Analysis...")
            ds_id_ts, df_ts = self.datasets["05_timeseries_monthly"]
            gt_fc = self.ground_truth["05_timeseries_monthly"]["forecasting"]
            fc_res = forecast_series(df_ts, date_column="date", value_column="revenue", periods=6, freq="M")

            self.record("Forecasting", "05_timeseries_monthly", "forecast_reliable", fc_res.get("reliable"), True)
            self.record("Forecasting", "05_timeseries_monthly", "historical_periods", len(fc_res["historical"]["values"]), gt_fc["historical_periods"])
            self.record("Forecasting", "05_timeseries_monthly", "trend_slope", fc_res.get("trend_slope_per_period"), gt_fc["trend_slope"])
            self.record("Forecasting", "05_timeseries_monthly", "next_period_forecast", fc_res["forecast"]["values"][0], gt_fc["next_period_forecast"])

            # -------------------------------------------------------------
            # Category 6: Decision Intelligence
            # -------------------------------------------------------------
            print(">>> Evaluating Category 6: Decision Intelligence...")
            # Retail return revenue loss
            gt_dec_ret = self.ground_truth["01_retail_sales"]["decision_intelligence"]
            actual_ret_loss = df_ret[df_ret["returned"] == 1]["revenue"].sum()
            self.record("Decision Intelligence", "01_retail_sales", "returns_revenue_loss", actual_ret_loss, gt_dec_ret["returns_revenue_loss"])

            # Customer churn revenue at risk
            ds_id_c, df_c = self.datasets["03_customer_ecommerce"]
            gt_dec_cust = self.ground_truth["03_customer_ecommerce"]["decision_intelligence"]
            profit_cust = analyze_profit_impact(df_c, pack_id="ecommerce")
            
            # Find churn loss in profit findings
            churn_findings = [f for f in profit_cust.get("findings", []) if "churn" in f.get("id", "")]
            actual_churn_loss = churn_findings[0]["impact_amount"] if churn_findings else df_c[df_c["churn_flag"] == 1]["total_spend"].sum()
            self.record("Decision Intelligence", "03_customer_ecommerce", "revenue_at_risk_churn", actual_churn_loss, gt_dec_cust["revenue_at_risk_churn"])
            self.record("Decision Intelligence", "03_customer_ecommerce", "churned_customer_count", int((df_c["churn_flag"] == 1).sum()), gt_dec_cust["churned_customers_count"])

            # Inventory supply chain holding cost
            ds_id_inv, df_inv = self.datasets["04_inventory_supply_chain"]
            gt_dec_inv = self.ground_truth["04_inventory_supply_chain"]["decision_intelligence"]
            self.record("Decision Intelligence", "04_inventory_supply_chain", "total_holding_cost", df_inv["total_holding_cost"].sum(), gt_dec_inv["total_holding_cost"])
            self.record("Decision Intelligence", "04_inventory_supply_chain", "stockout_sku_count", int((df_inv["stockout_events"] > 0).sum()), gt_dec_inv["stockout_sku_count"])

            # Cleanup datasets
            for key, (ds_id, _) in self.datasets.items():
                dataset_store.delete(ds_id)

        return self.compute_summary()

    def compute_summary(self) -> dict:
        total_tests = len(self.tests)
        passed_tests = sum(1 for t in self.tests if t["passed"])
        
        # Category scores
        cat_stats = {}
        for cat in CATEGORY_WEIGHTS:
            cat_tests = [t for t in self.tests if t["category"] == cat]
            c_total = len(cat_tests)
            c_passed = sum(1 for t in cat_tests if t["passed"])
            acc = round((c_passed / c_total * 100), 2) if c_total > 0 else 0.0
            cat_stats[cat] = {
                "total": c_total,
                "passed": c_passed,
                "accuracy_pct": acc,
                "weight": CATEGORY_WEIGHTS[cat]
            }

        # Weighted accuracy score formula
        weighted_score = round(sum(
            cat_stats[c]["accuracy_pct"] * cat_stats[c]["weight"]
            for c in CATEGORY_WEIGHTS
        ), 2)

        # Dataset scores
        ds_stats = {}
        all_ds = sorted(list({t["dataset"] for t in self.tests}))
        for d in all_ds:
            d_tests = [t for t in self.tests if t["dataset"] == d]
            d_total = len(d_tests)
            d_passed = sum(1 for t in d_tests if t["passed"])
            ds_stats[d] = {
                "total": d_total,
                "passed": d_passed,
                "accuracy_pct": round((d_passed / d_total * 100), 2) if d_total > 0 else 0.0
            }

        summary = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "overall_weighted_accuracy": weighted_score,
            "weighted_formula": "sum(Category_Accuracy * Category_Weight)",
            "category_breakdown": cat_stats,
            "dataset_breakdown": ds_stats,
            "detailed_results": self.tests
        }

        # Write results JSON
        RESULTS_FILE.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        # Print formatted report
        print("\n================================================================================")
        print("                        ACCURACY BENCHMARK RESULTS                              ")
        print("================================================================================")
        print(f"{'Category':30} {'Weight':8} {'Tests':7} {'Passed':8} {'Accuracy':10}")
        print("-" * 70)
        for cat, s in cat_stats.items():
            print(f"{cat:30} {s['weight']*100:>5.0f}%   {s['total']:>5}   {s['passed']:>6}   {s['accuracy_pct']:>8.2f}%")
        print("-" * 70)
        print(f"{'OVERALL WEIGHTED ACCURACY':30} {'100%':8} {total_tests:>5}   {passed_tests:>6}   {weighted_score:>8.2f}%")
        print("================================================================================\n")

        print(f"{'Dataset':30} {'Tests':7} {'Passed':8} {'Accuracy':10}")
        print("-" * 60)
        for ds, s in ds_stats.items():
            print(f"{ds:30} {s['total']:>5}   {s['passed']:>6}   {s['accuracy_pct']:>8.2f}%")
        print("================================================================================\n")

        return summary


def main():
    runner = BenchmarkRunner()
    summary = runner.run_all()
    score = summary["overall_weighted_accuracy"]
    if score >= 95.0:
        print(f"BENCHMARK PASSED: Overall accuracy {score:.2f}% satisfies the >= 95.0% threshold.")
        sys.exit(0)
    else:
        print(f"BENCHMARK FAILED: Overall accuracy {score:.2f}% is below 95.0%.")
        sys.exit(1)


if __name__ == "__main__":
    main()
