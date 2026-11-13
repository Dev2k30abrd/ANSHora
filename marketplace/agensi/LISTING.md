# Marketplace Listing: ANSHora — Business Intelligence Analyst

**Turn business data into evidence-backed decisions.**

---

## Overview

| Field | Detail |
| :--- | :--- |
| **Product Title** | **ANSHora — Business Intelligence Analyst** |
| **Slug** | `anshora-business-intelligence-analyst` |
| **Version** | `1.0.3` |
| **Category** | Business Intelligence / Data Analytics / Decision Intelligence |
| **Price** | **\$9 USD (One-time purchase)** |
| **Skill Type** | Agent Skill Package (Claude Desktop, Claude Code, Antigravity, OpenClaw) |
| **Dependencies** | Python 3.8+ (Standard Library only; zero pip dependencies) |
| **Tags** | `business-intelligence`, `decision-intelligence`, `data-analytics`, `profit-analysis`, `executive-reporting`, `kpi-engine`, `data-health` |

---

## Short Summary (Search Card & Marketplace Header)

**ANSHora — Business Intelligence Analyst** transforms raw business spreadsheets and CSV files into deterministic, evidence-backed executive briefings, profit driver analyses, what-if simulations, and decision logs. Built with zero external dependencies, 100% mathematical auditability, and defense against unweighted margin hallucinations.

---

## Full Product Description

Most AI agents hallucinate when analyzing numbers. When handed a 10,000-row business CSV, generic LLMs frequently:
- Take an unweighted average of row-level margins (producing errors of up to 40 percentage points).
- Invent plausible-sounding costs when columns are missing.
- Confuse correlational drops with causal root causes.
- Provide vague advice instead of prioritized, quantified actions.

**ANSHora — Business Intelligence Analyst** solves this by embedding the deterministic analytical core of ANSHora directly into an autonomous agent skill.

Whenever you point your agent at a sales export, subscription manifest, or financial ledger, the skill executes a battle-tested 6-stage analytical lifecycle:
1. **Non-Destructive Ingestion & Profiling:** Sniffs delimiters, detects UTF-8 BOMs, audits missing values, and identifies exact duplicate rows without mutating your source file.
2. **0–100 Data Health Scoring:** Computes objective data reliability before any conclusions are drawn.
3. **Deterministic Financial KPI Engine:** Computes revenue, COGS, gross profit, and overall weighted gross margin ($(\sum \text{Profit} / \sum \text{Revenue}) \times 100$) using a single consistent profit calculation policy (direct vs. derived; never mixed across rows). Enforces currency integrity by detecting currency symbols/codes and blocking cross-currency summation when mixed currencies are detected. If cost data is absent, it clearly flags revenue-only mode rather than fabricating expenses.
4. **Driver Decomposition:** Breaks down segment performance across products, regions, and channels, separating volume changes from price and cost variances.
5. **What-If Scenario Simulation:** Simulates realistic pricing adjustments, discount reductions, and return mitigations with explicit sensitivity bounds.
6. **Executive Briefing & Decision Log:** Delivers a 7-section executive report with strict epistemic separation between **Verified Facts**, **Analytical Hypotheses**, and **Actionable Recommendations**, complete with a structured Decision Log ready for leadership review.

---

## What Buyer Gets (Deliverables)

When you download the package, you receive a production-grade, self-contained ZIP archive:
1. **`SKILL.md`**: The complete skill instruction specification with YAML frontmatter, 8-stage operational execution rules, and anti-hallucination guardrails.
2. **`scripts/analyze_csv.py`**: A high-performance, deterministic Python analysis helper (<20 KB). Uses **only standard library modules** (`csv`, `json`, `math`, `datetime`, `collections`, `re`). Runs locally in milliseconds with zero `pip install` requirements and zero network access.
3. **`references/` Suite (6 Modular Deep-Dives)**:
   - `analytical-methodology.md`: Epistemic separation, 6-stage analytical flow, and price/volume/cost driver decomposition.
   - `financial-formulas.md`: Mathematical definitions and proofs for weighted margins, derived profit, AOV, return rates, and discount leakage.
   - `data-quality-rules.md`: Delimiter sniffing, duplicate audits, missing value metrics, and 0–100 health scoring formulas.
   - `evidence-and-reporting.md`: Numerical traceability rules, 7-section report blueprint, and Decision Log JSON schema.
   - `optional-agensi-tools.md`: Guidelines for discovering and quoting optional Agensi marketplace MCP tools safely and transparently.
   - `privacy-and-safety.md`: Local-first execution architecture, sandboxing guarantees, and prompt injection defenses against malicious data cells.
4. **`examples/` Fixtures & Gold Standard**:
   - `sample-business-data.csv`: Synthetic 25-row retail dataset with returns, discounts, and intentional duplicate rows for testing.
   - `expected-analysis.md`: Complete end-to-end reference report showing the exact caliber of output your agent will generate.
5. **`README.md` & `requirements.txt`**: Quickstart guide and environment verification.

---

## Supported Inputs

- **Delimiters:** Comma (`,`), Semicolon (`;`), Tab (`\t`), Pipe (`|`).
- **Encodings:** UTF-8, UTF-8 with BOM (`\xef\xbb\xbf`), ASCII, Latin-1.
- **Data Domains:**
  - E-commerce order manifests (Shopify, WooCommerce, Amazon).
  - B2B SaaS subscription and billing logs (Stripe, Chargebee).
  - Retail point-of-sale (POS) and inventory ledgers.
  - Marketing spend, attribution, and customer acquisition tables.
  - Multi-regional sales performance and quota spreadsheets.

---

## Sample Output Preview

```markdown
# Executive Business Intelligence Briefing: H1 Sales Performance

## 1. Executive Summary
- Net Revenue reached $276,000.00 across 24 unique orders ($255,000.00 deduplicated).
- Total Gross Profit landed at $86,700.00, delivering a verified Weighted Gross Margin of 31.41% (31.73% deduplicated).
- One exact duplicate transaction identified (ORD-1024), representing $21,000.00 in revenue exposure.

## 2. Data Health & Integrity Audit
- Data Health Score: 91.0 / 100 [High Reliability]
- Completeness: 100% across all 10 columns (0 missing values).
- Penalties: Duplicates 8.0 pts (4.0%), Outliers 1.0 pt (1.0%), Missing 0.0 pts, Type Contamination 0.0 pts.
- Deduplication Notice: 1 exact duplicate transaction identified (ORD-1024; $21,000.00 exposure).

## 3. Financial Performance Dashboard
| Metric | All Rows (Inclusive) | Deduplicated (Isolated) | Status |
| :--- | :---: | :---: | :--- |
| Total Revenue | $276,000.00 | $255,000.00 | [PASS] |
| Total COGS | $189,300.00 | $174,100.00 | [PASS] |
| Gross Profit | $86,700.00 | $80,900.00 | [PASS] |
| Weighted Margin | 31.41% | 31.73% | [HEALTHY] |
| Average Order Value (AOV) | $11,500.00 | $10,625.00 | [UNIQUE ORDERS] |
| Return Rate | 8.00% | 8.33% | [2 ORDERS] |

## 4. Segment Deep-Dive
- Electronics: $165,800.00 Revenue (60.07% share) | 32.15% Margin | Core volume driver.
- Furniture: $95,800.00 Revenue (34.71% share) | 27.66% Margin | 3.75% margin gap vs average.
- Office Supplies: $14,400.00 Revenue (5.22% share) | 47.92% Margin | High-margin niche.

## 5. What-If Scenario Modeling (Hypothetical)
- Action: Cap discretionary Furniture discounts at 8%, lifting category margin to 31.41%.
- Projected Impact: +$3,590.78 additional gross profit ($3,593.70 unrounded).
- Caveat: Assumes zero price elasticity (no order volume decline).

## 6. Prioritized Action Plan
1. Cap sales rep discretionary discounts in Furniture to 8% to recover ~$3,590.00 in margin leakage.
2. Investigate duplicate transaction ORD-1024 with billing/ERP team to confirm true revenue baseline.
3. Review supplier return rates on ORD-1008 and ORD-1020.

## 7. Decision Log Entry
- Decision ID: DEC-202506-01
- Target Metric: Furniture Gross Margin (+234 bps)
- Owner: Head of Merchandising
- Review Cadence: End of Q3 2025
```

---

## System Requirements

- **Agent Host:** Claude Desktop, Claude Code, Google Antigravity, OpenClaw, Cursor, or any agent host supporting markdown skills.
- **Runtime:** Python 3.8, 3.9, 3.10, 3.11, or 3.12.
- **Dependencies:** **Zero external dependencies.** Operates entirely with the Python Standard Library (`csv`, `json`, `math`, `datetime`, `collections`, `re`, `pathlib`).
- **Network / Database:** Zero network access required. No PostgreSQL, SQLite, or cloud credentials needed.

---

## Optional Agensi Marketplace Tools

This skill is 100% complete and fully functional out of the box with zero external tools. 

If your agent has access to optional Agensi tools (such as automated web research, chart image generation, or advanced reporting plugins):
- The skill will automatically discover them via the platform protocol.
- The agent will **always state the pricing and capability upfront** and request explicit confirmation before invoking any billed tool.
- If optional tools are absent or declined, the skill seamlessly delivers complete ASCII, markdown table, and structured text analyses with zero degradation.

---

## Limitations (What It Does NOT Do)

To ensure accurate customer expectations, please note:
- **Not a Live Database Driver:** The skill analyzes exported CSV/TSV/tabular files; it does not connect directly to live production PostgreSQL, MySQL, or Snowflake instances (export your query results to CSV first).
- **Not an Automated Email Spooler:** The skill formats executive briefings and decision logs in markdown; it does not dispatch emails via SMTP/Gmail OAuth.
- **Not an ML Deep Learning Library:** It computes deterministic aggregations, quantiles, and what-if sensitivities; it does not train neural networks or black-box predictive models.

---

## Frequently Asked Questions (FAQ)

### Q: Why does this skill compute weighted margins instead of averaging row percentages?
**A:** Averaging percentage columns is a classic mathematical fallacy that leads to severe errors. A \$10 order with a 90% margin averaged with a \$10,000 order with a 10% margin produces an unweighted average of 50%. In reality, the business only made \$1,009 profit on \$10,010 revenue—an actual margin of 10.08%. ANSHora strictly calculates $(\sum \text{Profit} / \sum \text{Revenue}) \times 100$ so you never make decisions on distorted figures.

### Q: Do I need to install pandas, numpy, or scipy?
**A:** No. `scripts/analyze_csv.py` was purposefully engineered to use only the Python standard library. It works out of the box in restricted virtual environments, containers, and agent sandboxes without running `pip install`.

### Q: What happens if my CSV has missing columns or cost data is missing?
**A:** The skill automatically adapts. If cost or profit columns are not present, it computes revenue KPIs, order distributions, and temporal trends while explicitly alerting the user that cost data is unavailable. It never fabricates numbers.

### Q: Does the skill modify my original CSV file?
**A:** Never. All operations are strictly read-only. The input file's byte hash before and after execution remains identical. Exact duplicates and outliers are reported for your visibility without mutating the underlying data.

### Q: Is my business data private?
**A:** Yes. The analysis runs 100% locally on your machine within your agent runtime. No data is transmitted to third-party analytics servers or external APIs.

---

## Support & Version Updates

- **Current Release:** v1.0.0 (Production Stable)
- **Maintainer:** ANSHora Team / Agensi Verified Creator
- **Bug Reports & Inquiries:** Support documentation included in `README.md`.
