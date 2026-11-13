# ANSHora — Business Intelligence Analyst Skill (v1.0.3)

> **Turn business data into evidence-backed decisions.**

ANSHora is an independent AI business intelligence analyst skill designed for AI agents. It equips your agent with deterministic financial analysis, data quality auditing, root-cause decomposition, and executive decision reporting.

---

## What Buyers Receive

- **`SKILL.md`**: The primary operational directive guiding the AI agent through the 8-stage analysis workflow.
- **`scripts/analyze_csv.py`**: A deterministic Python helper script (standard library only, zero dependencies, <20 KB) for fast, secure, read-only data profiling.
- **`references/`**: Comprehensive guides covering analytical methodology, financial formulas, data quality rules, decision log templates, optional tools, and privacy guardrails.
- **`examples/`**: Synthetic sample business data and a reference analysis report showing the expected standard of output.
- **`requirements.txt`**: Minimal requirements documentation confirming standard library operation (Python 3.8+).

---

## Key Capabilities (v1.0.3)

1. **Deterministic Financial Integrity & Consistent Profit Policy**:
   - Single consistent profit methodology (`direct_profit` vs `derived_profit`): zero mixing of calculation bases across rows.
   - Total Revenue, COGS, and Gross Profit calculated across consistently paired valid rows; excluded rows tracked in `unpaired_revenue_rows` and `unpaired_cost_rows`.
   - **Cost-Source Disclosure**: When `direct_profit` is selected and missing cost values are inferred, `cost_source` discloses `"derived (revenue - profit)"` with `inferred_cost_rows`; never mislabels inferred costs as directly sourced.
   - **Weighted Gross Margin**: Strictly calculated as total profit divided by total revenue over valid paired rows; never an unweighted row average.
   - **Currency Integrity & Normalized Detection**:
     - Strips currency symbols (`$`, `€`, `₹`, `£`, `¥`) and ISO codes (`USD`, `EUR`, `INR`, `GBP`, `CAD`, `AUD`) before numeric parsing (prefix/suffix resilient).
     - Normalizes equivalent representations (`₹` and `INR` -> `INR`, `€` and `EUR` -> `EUR`).
     - Ambiguous symbols (`$`) are handled conservatively and never assumed to mean `USD`.
     - Blocks cross-currency summation when genuinely distinct currencies are present.
   - **Average Order Value (AOV)**: Computed using unique order IDs when present (aggregating multi-line orders), or transaction-line average when order IDs are absent.
   - Dual reporting: Headline KPIs provided both across all rows and with exact duplicates isolated under the identical profit methodology.
2. **Data Trust & Quality Auditing**:
   - **0–100 Data Health Score** incorporating all four documented penalty pillars:
     - Missing values ($P_{\text{missing}}$, cap: 40 pts)
     - Exact duplicates ($P_{\text{duplicates}}$, cap: 30 pts)
     - Statistical outliers ($P_{\text{outliers}}$, cap: 20 pts)
     - Type contamination ($P_{\text{types}}$, cap: 10 pts)
   - Exact duplicate row detection and **duplicate revenue exposure** quantification.
   - **Zero-IQR safe Tukey outlier detection**: Handles constant columns, repeated values with extreme observations, and negative transactions without dropping data.
   - Non-destructive processing: never mutates or overwrites source data.
3. **Driver Decomposition (Root-Cause Analysis)**:
   - Price vs. Volume vs. Cost driver decomposition performed by the agent reasoning layer.
   - Segment contribution analysis across product categories, customer segments, and regions.
4. **Scenario Simulation (What-If Analysis)**:
   - Evaluates price, discount, or volume adjustments against historical baselines with explicit elasticity assumptions.
5. **Executive Decision Reports**:
   - Structured 7-section executive reports with designated owners, review dates, and success metrics.

---

## Requirements & Setup

- **Python**: Python 3.8+ (Standard Library only).
- **Supported Formats**: CSV directly (`.csv`, UTF-8, UTF-8 BOM, tab/semicolon/comma/pipe delimited).
- **Spreadsheet Files (`.xlsx`/`.xls`)**: The Python helper processes CSV text files directly; export or save the target sheet as a CSV file prior to analysis.
- **Zero Cloud Dependencies**: Does not require PostgreSQL, external databases, Google Sign-In, or external API keys.

---

## Privacy & Safety

- **Read-Only**: Analyzes datasets in memory; never modifies source files.
- **No Telemetry**: Contains zero tracking, telemetry, or remote API calls.
- **Local Execution**: Data remains within the buyer's permitted execution boundary.
- **Prompt Injection Defense**: Treats text inside data rows strictly as passive string data.
