# Expected Analysis Reference: Sample Business Data (v1.0.1)

This reference document demonstrates the exact analytical standard, structure, and grounding produced by an agent running the **ANSHora — Business Intelligence Analyst** skill on [`sample-business-data.csv`](./sample-business-data.csv).

---

## 1. Dataset Intake & Capabilities Map

- **File Analysed**: `sample-business-data.csv`
- **Total Records**: 25 raw records, 10 columns.
- **Grain**: Transactional order-level records across 6 months (Jan 2025 – Jun 2025).
- **Mapped Columns**:
  - Revenue: `Revenue`
  - Cost / COGS: `Cost`
  - Profit: Derived (`Revenue - Cost`)
  - Date: `Date`
  - Order Identifier: `Order_ID`
  - Dimensions: `Product_Category`, `Customer_Segment`, `Region`
  - Commercial Attributes: `Discount_Pct`, `Returned`
- **Capability Boundaries**:
  - ✅ Revenue, COGS, and derived Gross Profit available across consistently paired rows.
  - ✅ Unique Order ID detected; AOV computed on unique orders as well as line-item average.
  - ✅ Channel/Region/Category/Segment comparisons supported.
  - ✅ Discount rate and Returns tracking supported.
  - ❌ Customer identifiers (e.g. lifetime value, cohort retention) NOT available in dataset.
  - ❌ Operational overheads / marketing spend NOT present; profit refers strictly to Gross Profit.

---

## 2. Data Health & Trust Audit

- **Data Health Score**: **91.0 / 100** (`High Reliability`)
- **Penalty Breakdown (4 Documented Pillars)**:
  - Missing Values Penalty ($P_{\text{missing}}$): **0.00 pts** (0 missing values, 100% completeness across all 10 columns).
  - Exact Duplicates Penalty ($P_{\text{duplicates}}$): **8.00 pts** (1 duplicate row out of 25 = 4.0% $\times$ 2.0).
  - Statistical Outliers Penalty ($P_{\text{outliers}}$): **1.00 pts** (1 outlier across 100 numeric cells = 1.0% $\times$ 1.0).
  - Type Contamination Penalty ($P_{\text{types}}$): **0.00 pts** (0 contaminated string cells in numeric columns).
  - *Total Deductions*: $0.0 + 8.0 + 1.0 + 0.0 = 9.0 \implies 100.0 - 9.0 = \mathbf{91.0}$.
- **Exact Duplicate Rows & Exposure**:
  - Count: **1 exact duplicate row (4.0% of records)**
  - Duplicate Row: `ORD-1024, 2025-06-27, Corporate, Furniture, West, $21,000.00, Cost: $15,200.00`
  - **Duplicate Revenue Exposure**: **$21,000.00** (Cost: $15,200.00, Profit: $5,800.00).
  - *Audit Note*: Duplicates are preserved for audit transparency; both all-rows and deduplicated KPIs are provided below.
- **Outliers Detected**:
  - `Quantity`: 1 upper outlier identified (`Quantity = 25` on order `ORD-1018`, upper Tukey bound = 20.5). Flagged for order batch review, **never silently deleted or pruned**.
- **Data Integrity**: Clean numeric formats; valid ISO dates throughout.

---

## 3. Executive Financial Summary (Headline KPIs)

*All figures calculated deterministically via Python standard library:*

| Financial Metric | All Rows (Inclusive) | Deduplicated (Isolated) | Method / Source |
|---|:---:|:---:|---|
| **Total Revenue** | **$276,000.00** | **$255,000.00** | Sum of `Revenue` column |
| **Total Cost (COGS)** | **$189,300.00** | **$174,100.00** | Sum of `Cost` column |
| **Total Gross Profit** | **$86,700.00** | **$80,900.00** | Derived: `Total Revenue - Total Cost` |
| **Overall Gross Margin** | **31.41%** | **31.73%** | **Weighted**: `Total Profit ÷ Total Revenue × 100` |
| **Average Order Value (AOV)** | **$11,500.00** | **$10,625.00** | `Total Revenue ÷ 24 Unique Orders` (`unique_orders`) |
| **Line-Item Average** | **$11,040.00** | **$10,625.00** | `Total Revenue ÷ Total Line Items` |
| **Return Rate** | **8.00%** | **8.33%** | 2 returned orders out of total orders |
| **Average Discount Given** | **6.20%** | **5.83%** | Mean of `Discount_Pct` |

> ⚠️ **Methodological Notice**:
> The overall gross margin is strictly **31.41%** (weighted across all rows) or **31.73%** (deduplicated). Averaging row-level margins yields an incorrect figure of **34.28%** (a 2.87 percentage point distortion). ANSHora rules strictly forbid row-level margin averaging.

---

## 4. Segment & Category Deep-Dive

### By Product Category
| Product Category | Orders | Revenue | Rev Share | Gross Profit | Category Margin |
|---|:---:|:---:|:---:|:---:|:---:|
| **Electronics** | 11 | $165,800.00 | 60.07% | $53,300.00 | **32.15%** |
| **Furniture** | 8 | $95,800.00 | 34.71% | $26,500.00 | **27.66%** |
| **Office Supplies** | 6 | $14,400.00 | 5.22% | $6,900.00 | **47.92%** |

- **Key Finding**: Electronics drives 60.07% of company revenue with healthy 32.15% margin. Furniture underperforms on margin (27.66%, a 3.75 percentage-point margin gap vs company average), representing approximately $3,593.70 in unrounded margin leakage ($3,590.78 at rounded 31.41%). Office Supplies yields high margins (47.92%) but low volume (5.22% share).

### By Customer Segment
| Customer Segment | Orders | Revenue | Rev Share | Gross Profit | Segment Margin |
|---|:---:|:---:|:---:|:---:|:---:|
| **Corporate** | 10 | $177,400.00 | 64.28% | $55,700.00 | **31.40%** |
| **Consumer** | 8 | $49,450.00 | 17.92% | $15,000.00 | **30.33%** |
| **Small Business** | 7 | $49,150.00 | 17.81% | $16,000.00 | **32.55%** |

- **Key Finding**: Corporate customers constitute the core engine, generating $177,400.00 (64.28% of total revenue) at an average order size of $17,740.00.

---

## 5. Monthly Trend Analysis

| Month | Orders | Revenue | MoM Growth | Gross Profit | Monthly Margin |
|---|:---:|:---:|:---:|:---:|:---:|
| **2025-01** | 3 | $18,200.00 | — | $6,000.00 | 32.97% |
| **2025-02** | 4 | $48,400.00 | +165.93% | $15,400.00 | 31.82% |
| **2025-03** | 4 | $25,100.00 | -48.14% | $7,800.00 | 31.08% |
| **2025-04** | 4 | $62,650.00 | +149.60% | $19,800.00 | 31.60% |
| **2025-05** | 5 | $33,100.00 | -47.17% | $10,500.00 | 31.72% |
| **2025-06** | 5 | $88,550.00 | +167.52% | $27,200.00 | 30.72% |

- **Seasonality Pattern**: Alternating bi-monthly procurement surges (February, April, June) driven by large Corporate bulk orders.

---

## 6. What-If Scenario Simulation (Agent Reasoning Layer)

**Scenario**: *What if Furniture discounts are capped, improving Furniture gross margin from 27.66% to the 31.41% company average?*

- **Baseline Furniture Revenue**: $95,800.00
- **Baseline Furniture Profit**: $26,500.00 (27.66%)
- **Simulated Furniture Profit (at 31.41%)**: $30,090.78
- **Projected Profit Impact**: **+$3,590.78 additional gross profit** ($3,593.70 at exact unrounded 31.4130% floating precision).
- *Explicit Assumption & Sensitivity Caveat*: This simulation assumes zero price elasticity ($\epsilon = 0$). In commercial practice, capping discounts may cause a slight decline in order volume; if volume drops by >3.8%, net profit gain will be eroded.

---

## 7. Actionable Recommendations & Decision Log Entry

1. **Investigate Furniture Margin Leakage (Priority 1)**:
   - *Observation*: Furniture margin lags at 27.66% with highest average discount (up to 15% on orders `ORD-1005` and `ORD-1024`).
   - *Action*: Review vendor supply agreements for Furniture and cap sales rep discretionary discounts at 8%.
   - *Owner*: Head of Merchandising / Sales Director.
   - *Review Date*: End of Q3 2025.
   - *Success Metric*: Furniture margin exceeding 30.0%.

2. **Deduplicate Transaction Log (Priority 2)**:
   - *Observation*: Order `ORD-1024` is logged twice on 2025-06-27 ($21,000.00 duplicate exposure).
   - *Action*: Confirm with ERP/billing whether this was a duplicate charge or a logging artifact. If duplicate entry, true revenue is $255,000.00 with 31.73% margin.
