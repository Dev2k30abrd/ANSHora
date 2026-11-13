"""
Comprehensive Unit & Integration Test Suite for ANSHora CSV Analysis Helper.
Validates all 15 required test scenarios from the Agensi skill specification.
Uses synthetic test fixtures in isolated temporary directories.
"""

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Prevent bytecode generation in source folder
sys.dont_write_bytecode = True

# Add script directory to path
SCRIPT_PATH = Path(__file__).resolve().parents[1] / "anshora-business-intelligence-analyst" / "scripts" / "analyze_csv.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))

from analyze_csv import analyze  # noqa: E402


def test_1_valid_csv():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Region,Sales,Cost\nNorth,100,60\nSouth,200,120\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        assert res["row_count"] == 2
        assert res["column_count"] == 3
        assert res["financial_kpis"]["total_revenue"] == 300.0
        assert res["financial_kpis"]["total_cost"] == 180.0
        assert res["financial_kpis"]["total_profit"] == 120.0
        assert res["financial_kpis"]["weighted_margin_pct"] == 40.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_2_utf8_bom():
    with tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False) as f:
        # Write UTF-8 BOM followed by CSV content
        f.write(b"\xef\xbb\xbfRegion,Revenue,Cost\nEast,500,300\nWest,500,300\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        assert res["has_utf8_bom"] is True
        assert res["columns"][0] == "Region"
        assert res["financial_kpis"]["total_revenue"] == 1000.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_3_missing_values():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Product,Revenue,Cost\nA,100,50\nB,,60\nC,200,null\nD,N/A,-\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        assert res["row_count"] == 4
        assert res["data_quality"]["missing_values_by_column"]["Revenue"] == 2
        assert res["data_quality"]["missing_values_by_column"]["Cost"] == 2
        assert res["data_quality"]["missing_percentages"]["Revenue"] == 50.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_4_exact_duplicate_rows():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Price\nWidget,10\nWidget,10\nWidget,10\nGadget,20\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        assert res["row_count"] == 4
        # 3 identical Widget rows = 2 duplicates
        assert res["data_quality"]["exact_duplicate_rows"] == 2
        assert res["data_quality"]["duplicate_percentage"] == 50.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_5_empty_file():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        pass  # 0 bytes
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        assert res["row_count"] == 0
        assert res["data_quality"]["empty"] is True
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_6_malformed_rows():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Rows with too few or too many delimiters
        f.write("ColA,ColB,ColC\n1,2\n4,5,6,extra\n7,8,9\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        assert res["row_count"] == 3
        assert res["column_count"] == 3
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_7_numeric_parsing():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Currency signs, commas, percent signs for a single currency ($) per RFC 4180
        f.write('Item,Revenue\nA,"$1,250.50"\nB,"$2,500.00"\nC,"$5,000"\nD,"$10"\n')
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        assert res["financial_kpis"]["total_revenue"] == 8760.50
        assert res["financial_kpis"]["currency_status"] == "single_currency_detected"
        assert "$" in res["financial_kpis"]["currencies_detected"]
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_8_revenue_cost_profit_calculations():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Sales,Cost\n1000,600\n2000,1100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["financial_kpis"]["total_revenue"] == 3000.0
        assert res["financial_kpis"]["total_cost"] == 1700.0
        assert res["financial_kpis"]["total_profit"] == 1300.0
        assert res["financial_kpis"]["profit_source"] == "derived (revenue - cost)"
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_9_weighted_margin_calculation():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Row 1: Rev 100, Cost 10 -> Margin 90%
        # Row 2: Rev 10000, Cost 9000 -> Margin 10%
        # Unweighted average = 50%
        # Weighted = (10000 - 9000 + 100 - 10) / (10100) = 1090 / 10100 = 10.79%
        f.write("Revenue,Cost\n100,10\n10000,9000\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        weighted_margin = res["financial_kpis"]["weighted_margin_pct"]
        assert weighted_margin == 10.79
        assert weighted_margin != 50.0  # Must NEVER be unweighted average!
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_10_zero_revenue():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Revenue,Cost\n0,50\n0,50\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["financial_kpis"]["total_revenue"] == 0.0
        assert res["financial_kpis"]["weighted_margin_pct"] is None
        assert res["financial_kpis"]["zero_revenue_rows"] == 2
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_11_missing_cost_column():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Category,Sales,Quantity\nElectronics,5000,2\nFurniture,3000,1\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["financial_kpis"]["total_revenue"] == 8000.0
        assert res["financial_kpis"]["total_cost"] is None
        assert res["financial_kpis"]["total_profit"] is None
        assert res["capabilities"]["cost_available"] is False
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_12_date_grouping():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Date,Revenue\n2025-01-10,1000\n2025-01-20,1500\n2025-02-05,3000\n2025-03-01,2000\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert len(res["time_series"]) == 3
        assert res["time_series"][0]["period"] == "2025-01"
        assert res["time_series"][0]["revenue"] == 2500.0
        assert res["time_series"][1]["period"] == "2025-02"
        assert res["time_series"][1]["revenue"] == 3000.0
        assert res["time_series"][1]["growth_vs_previous_period_pct"] == 20.0
        assert res["time_series"][2]["period"] == "2025-03"
        assert res["time_series"][2]["growth_vs_previous_period_pct"] == -33.33
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_13_segment_grouping():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Category,Revenue,Cost\nSaaS,6000,2000\nSaaS,4000,1000\nServices,2000,1500\n")
        f_path = f.name
    try:
        res = analyze(f_path, dimensions=["Category"])
        assert "Category" in res["segment_breakdowns"]
        cats = res["segment_breakdowns"]["Category"]
        assert cats[0]["segment_value"] == "SaaS"
        assert cats[0]["revenue"] == 10000.0
        assert cats[0]["revenue_share_pct"] == 83.33
        assert cats[0]["margin_pct"] == 70.0
        assert cats[1]["segment_value"] == "Services"
        assert cats[1]["revenue"] == 2000.0
        assert cats[1]["margin_pct"] == 25.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_14_invalid_column_mapping():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("A,B\n10,20\n")
        f_path = f.name
    try:
        res = analyze(f_path, revenue_col="NonExistentColumn")
        assert res["status"] == "success"
        # Since NonExistentColumn wasn't found, revenue_column should be None
        assert res["financial_kpis"]["revenue_column"] is None
        assert res["financial_kpis"]["total_revenue"] is None
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_15_no_source_file_modification():
    content = "ID,Name,Amount\n1,Alice,100.50\n2,Bob,200.75\n"
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write(content)
        f_path = f.name

    initial_hash = hashlib.sha256(Path(f_path).read_bytes()).hexdigest()
    initial_mtime = os.path.getmtime(f_path)

    try:
        res = analyze(f_path)
        assert res["status"] == "success"

        post_hash = hashlib.sha256(Path(f_path).read_bytes()).hexdigest()
        post_mtime = os.path.getmtime(f_path)

        assert initial_hash == post_hash, "Source file content was mutated!"
        assert initial_mtime == post_mtime, "Source file timestamp was altered!"
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_16_type_contamination_penalty():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # 10 rows: 8 valid numbers, 2 contaminated text strings in numeric column
        f.write("ID,Revenue\n1,100\n2,200\n3,300\n4,400\n5,500\n6,600\n7,700\n8,800\n9,CORRUPT\n10,INVALID\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        penalties = res["data_quality"]["penalties"]
        assert penalties["type_contamination"]["contaminated_cells"] == 2
        assert penalties["type_contamination"]["percentage"] == 20.0
        # Capped at 10.0
        assert penalties["type_contamination"]["penalty"] == 10.0
        assert res["data_quality"]["health_score"] == 90.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_17_health_score_all_four_penalties_and_boundaries():
    # Test all 4 penalties simultaneously
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("ID,Revenue,Cost\n1,100,50\n1,100,50\n2,,60\n3,BAD,70\n4,5000,80\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        p = res["data_quality"]["penalties"]
        assert "missing_values" in p
        assert "exact_duplicates" in p
        assert "statistical_outliers" in p
        assert "type_contamination" in p
        assert 0.0 <= res["data_quality"]["health_score"] <= 100.0
    finally:
        Path(f_path).unlink(missing_ok=True)

    # Test boundary floor at 0.0
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("A,B\n,\n,\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["data_quality"]["health_score"] >= 0.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_18_duplicate_revenue_exposure_and_deduplicated_kpis():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Order_ID,Revenue,Cost\nORD-1,1000,600\nORD-2,2000,1200\nORD-2,2000,1200\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        kpis = res["financial_kpis"]
        dup_exp = kpis["duplicate_exposure"]
        assert dup_exp["exact_duplicate_rows"] == 1
        assert dup_exp["duplicate_revenue"] == 2000.0
        assert dup_exp["duplicate_cost"] == 1200.0
        assert dup_exp["duplicate_profit"] == 800.0

        # All rows vs Deduplicated
        assert kpis["all_rows"]["total_revenue"] == 5000.0
        assert kpis["all_rows"]["row_count"] == 3
        assert kpis["deduplicated"]["total_revenue"] == 3000.0
        assert kpis["deduplicated"]["row_count"] == 2
        assert kpis["deduplicated"]["total_profit"] == 1200.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_19_aov_unique_orders_multi_line():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # ORD-1 has 2 lines (100 + 200 = 300), ORD-2 has 1 line (300) -> Total = 600 across 2 orders
        f.write("Order_ID,Item,Revenue\nORD-1,Widget A,100\nORD-1,Widget B,200\nORD-2,Widget C,300\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["aov_type"] == "unique_orders"
        assert k["all_rows"]["unique_orders_count"] == 2
        assert k["average_order_value"] == 300.0  # 600 / 2 orders
        assert k["line_item_average"] == 200.0   # 600 / 3 lines
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_20_aov_fallback_line_level_without_order_id():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # No order ID column present
        f.write("Product,Revenue\nAlpha,400\nBeta,600\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["aov_type"] == "line_item_average"
        assert k["all_rows"]["unique_orders_count"] is None
        assert k["average_order_value"] == 500.0  # 1000 / 2 lines
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_21_outlier_zero_iqr_constant_column():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Score\n10\n10\n10\n10\n10\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        num_s = res["numeric_summaries"]["Score"]
        assert num_s["quantiles"]["iqr"] == 0.0
        assert num_s["outliers_count"] == 0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_22_outlier_zero_iqr_repeated_with_extreme():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # 9 values of 10, one extreme of 50 -> IQR=0, 50 must be flagged
        f.write("Val\n" + "\n".join(["10"] * 9) + "\n50\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        num_s = res["numeric_summaries"]["Val"]
        assert num_s["quantiles"]["iqr"] == 0.0
        assert num_s["outliers_count"] == 1
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_23_outlier_small_dataset_and_negatives():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Small dataset n < 4: fences bypassed
        f.write("X\n10\n20\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["numeric_summaries"]["X"]["outliers_count"] == 0
    finally:
        Path(f_path).unlink(missing_ok=True)

    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Repeated zeros with extreme negative value
        f.write("P\n" + "\n".join(["0"] * 9) + "\n-100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["numeric_summaries"]["P"]["outliers_count"] == 1
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_24_financial_integrity_unpaired_rows():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Row 1: paired (Rev 100, Cost 40 -> Prof 60)
        # Row 2: unpaired rev (Rev 200, Cost missing)
        # Row 3: unpaired cost (Rev missing, Cost 50)
        f.write("Sales,Cost\n100,40\n200,\n,50\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]["all_rows"]
        assert k["paired_valid_rows"] == 1
        assert k["unpaired_revenue_rows"] == 1
        assert k["unpaired_cost_rows"] == 1
        assert k["total_profit"] == 60.0  # derived only from paired row
        assert k["weighted_margin_pct"] == 60.0  # 60 / 100 on paired rev
        assert any("excluded from profit/margin calculations" in n for n in res["analytical_notices"])
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_25_financial_integrity_negative_and_zero_revenue():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        # Net negative revenue: weighted margin must be None to prevent misleading inverted %
        f.write("Sales,Cost\n100,60\n-300,-100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["total_revenue"] == -200.0
        assert k["negative_revenue_rows"] == 1
        assert k["weighted_margin_pct"] is None
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_26_three_row_reproduction_direct_profit():
    # Exact adversarial reproduction from directive
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Revenue,Cost,Profit\n100,60,40\n200,100,\n300,,120\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        # Selected policy must be direct_profit without mixing derived profit on row 2
        assert k["profit_calculation_policy"] == "direct_profit"
        assert k["paired_valid_rows"] == 2  # Rows 1 and 3 only (never 3!)
        assert k["unpaired_revenue_rows"] == 1  # Row 2 excluded from profit
        assert k["total_profit"] == 160.0  # 40 + 120 (never 260!)
        # Weighted margin = 160 / (100 + 300) = 40.0% (never 43.33%!)
        assert k["weighted_margin_pct"] == 40.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_27_three_row_reproduction_derived_profit():
    # Explicit derived profit policy on the same 3-row dataset
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Revenue,Cost,Profit\n100,60,40\n200,100,\n300,,120\n")
        f_path = f.name
    try:
        res = analyze(f_path, method="derived")
        k = res["financial_kpis"]
        assert k["profit_calculation_policy"] == "derived_profit"
        assert k["paired_valid_rows"] == 2  # Rows 1 and 2 only
        assert k["unpaired_revenue_rows"] == 1  # Row 3 excluded (cost missing)
        assert k["total_cost"] == 160.0  # 60 + 100
        assert k["total_profit"] == 140.0  # (100 - 60) + (200 - 100) = 40 + 100 = 140
        # Weighted margin = 140 / (100 + 200) = 46.67%
        assert k["weighted_margin_pct"] == 46.67
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_28_mixed_currencies_blocking():
    # When multiple currencies are detected, cross-currency totals must be blocked
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Revenue,Cost\nAlpha,$100,$50\nBeta,€200,€100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["currency_status"] == "mixed_currencies_detected"
        assert set(k["currencies_detected"]) == {"$", "EUR"}
        assert k["total_revenue"] is None
        assert k["total_cost"] is None
        assert k["total_profit"] is None
        assert k["average_order_value"] is None
        assert k["aov_type"] == "blocked_mixed_currencies"
        assert any("Multiple currencies detected" in n for n in res["analytical_notices"])
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_29_unspecified_currency():
    # Pure numbers without symbols or ISO codes
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Revenue,Cost\nItem1,500,200\nItem2,300,100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["currency_status"] == "unspecified"
        assert k["currencies_detected"] == []
        assert k["total_revenue"] == 800.0
        assert k["total_cost"] == 300.0
        assert k["total_profit"] == 500.0
        assert any("Currency is unspecified" in n for n in res["analytical_notices"])
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_30_missing_direct_profit_rows():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Sales,Profit\n100,20\n200,\n300,60\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["profit_calculation_policy"] == "direct_profit"
        assert k["paired_valid_rows"] == 2
        assert k["unpaired_revenue_rows"] == 1
        assert k["total_profit"] == 80.0
        # 80 / (100 + 300) = 20.0%
        assert k["weighted_margin_pct"] == 20.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_31_duplicate_exposure_uses_same_method():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Revenue,Cost,Profit\n100,60,40\n100,60,40\n200,100,\n")
        f_path = f.name
    try:
        # Under explicit direct method
        res_dir = analyze(f_path, method="direct")
        k_dir = res_dir["financial_kpis"]
        assert k_dir["profit_calculation_policy"] == "direct_profit"
        dup_dir = k_dir["duplicate_exposure"]
        assert dup_dir["exact_duplicate_rows"] == 1
        assert dup_dir["duplicate_revenue"] == 100.0
        assert dup_dir["duplicate_cost"] == 60.0
        assert dup_dir["duplicate_profit"] == 40.0

        # Under derived method (auto-selected because cost has 3 valid rows vs 2 profit)
        res_der = analyze(f_path)
        k_der = res_der["financial_kpis"]
        assert k_der["profit_calculation_policy"] == "derived_profit"
        dup_der = k_der["duplicate_exposure"]
        assert dup_der["exact_duplicate_rows"] == 1
        assert dup_der["duplicate_revenue"] == 100.0
        assert dup_der["duplicate_cost"] == 60.0
        assert dup_der["duplicate_profit"] == 40.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_32_consistency_all_rows_and_deduplicated():
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Revenue,Cost,Profit\n100,60,40\n100,60,40\n300,,120\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        all_r = k["all_rows"]
        dedup = k["deduplicated"]
        assert all_r["profit_method"] == dedup["profit_method"] == "direct_profit"
        assert all_r["profit_source"] == dedup["profit_source"]
        assert all_r["paired_valid_rows"] == 3
        assert dedup["paired_valid_rows"] == 2
        assert dedup["total_revenue"] == 400.0
        assert dedup["total_profit"] == 160.0
        assert dedup["weighted_margin_pct"] == 40.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_33_currency_iso_codes_prefix_and_suffix():
    # USD 100 and 100 USD correctly parsed
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Revenue\nAlpha,USD 100\nBeta,100 USD\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        assert res["status"] == "success"
        k = res["financial_kpis"]
        assert k["total_revenue"] == 200.0
        assert k["currency_status"] == "single_currency_detected"
        assert k["detected_currency"] == "USD"
        assert k["currencies_detected"] == ["USD"]
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_34_currency_normalization_equivalent_representations():
    # INR 100 and ₹100 normalized to INR, not treated as mixed
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Revenue\nAlpha,INR 100\nBeta,₹100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["currency_status"] == "single_currency_detected"
        assert k["detected_currency"] == "INR"
        assert k["currencies_detected"] == ["INR"]
        assert k["total_revenue"] == 200.0
    finally:
        Path(f_path).unlink(missing_ok=True)

    # EUR 100 and €100 normalized to EUR, not treated as mixed
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Revenue\nAlpha,EUR 100\nBeta,€100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["currency_status"] == "single_currency_detected"
        assert k["detected_currency"] == "EUR"
        assert k["currencies_detected"] == ["EUR"]
        assert k["total_revenue"] == 200.0
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_35_currency_symbol_code_ambiguity():
    # $ is ambiguous and never automatically assumed to mean USD
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Revenue\nAlpha,$100\nBeta,USD 100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        # $ and USD together are treated as distinct/ambiguous representations -> mixed currencies detected
        assert k["currency_status"] == "mixed_currencies_detected"
        assert set(k["currencies_detected"]) == {"$", "USD"}
        assert k["total_revenue"] is None
        assert k["aov_type"] == "blocked_mixed_currencies"
    finally:
        Path(f_path).unlink(missing_ok=True)

    # $ and CAD together also blocked
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Item,Revenue\nAlpha,$100\nBeta,CAD 100\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["currency_status"] == "mixed_currencies_detected"
        assert set(k["currencies_detected"]) == {"$", "CAD"}
        assert k["total_revenue"] is None
    finally:
        Path(f_path).unlink(missing_ok=True)


def test_36_cost_source_disclosure_when_inferred():
    # When direct_profit is selected and a missing cost is inferred, cost_source must be disclosed as derived
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Revenue,Cost,Profit\n100,60,40\n200,100,\n300,,120\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["profit_calculation_policy"] == "direct_profit"
        assert k["cost_source"] == "derived (revenue - profit)"
        assert k["cost_source"] != "direct from column 'Cost'"
        assert k["inferred_cost_rows"] == 1
        assert any("Cost derived as (revenue - profit)" in n for n in res["analytical_notices"])
    finally:
        Path(f_path).unlink(missing_ok=True)

    # When all paired rows have direct cost values, cost_source is directly from column
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("Revenue,Cost,Profit\n100,60,40\n200,120,80\n")
        f_path = f.name
    try:
        res = analyze(f_path)
        k = res["financial_kpis"]
        assert k["profit_calculation_policy"] == "direct_profit"
        assert k["cost_source"] == "direct from column 'Cost'"
        assert k["inferred_cost_rows"] == 0
    finally:
        Path(f_path).unlink(missing_ok=True)


if __name__ == "__main__":
    tests = [
        test_1_valid_csv, test_2_utf8_bom, test_3_missing_values, test_4_exact_duplicate_rows,
        test_5_empty_file, test_6_malformed_rows, test_7_numeric_parsing,
        test_8_revenue_cost_profit_calculations, test_9_weighted_margin_calculation,
        test_10_zero_revenue, test_11_missing_cost_column, test_12_date_grouping,
        test_13_segment_grouping, test_14_invalid_column_mapping, test_15_no_source_file_modification,
        test_16_type_contamination_penalty, test_17_health_score_all_four_penalties_and_boundaries,
        test_18_duplicate_revenue_exposure_and_deduplicated_kpis, test_19_aov_unique_orders_multi_line,
        test_20_aov_fallback_line_level_without_order_id, test_21_outlier_zero_iqr_constant_column,
        test_22_outlier_zero_iqr_repeated_with_extreme, test_23_outlier_small_dataset_and_negatives,
        test_24_financial_integrity_unpaired_rows, test_25_financial_integrity_negative_and_zero_revenue,
        test_26_three_row_reproduction_direct_profit, test_27_three_row_reproduction_derived_profit,
        test_28_mixed_currencies_blocking, test_29_unspecified_currency,
        test_30_missing_direct_profit_rows, test_31_duplicate_exposure_uses_same_method,
        test_32_consistency_all_rows_and_deduplicated,
        test_33_currency_iso_codes_prefix_and_suffix,
        test_34_currency_normalization_equivalent_representations,
        test_35_currency_symbol_code_ambiguity,
        test_36_cost_source_disclosure_when_inferred
    ]
    passed = 0
    print(f"Running {len(tests)} test cases for analyze_csv.py...")
    for t in tests:
        try:
            t()
            passed += 1
            print(f"  PASS: {t.__name__}")
        except Exception as e:
            print(f"  FAIL: {t.__name__} - {e}")
            sys.exit(1)
    print(f"\nAll {passed}/{len(tests)} tests passed successfully!")
    pycache = SCRIPT_PATH.parent / "__pycache__"
    if pycache.exists():
        shutil.rmtree(pycache, ignore_errors=True)
