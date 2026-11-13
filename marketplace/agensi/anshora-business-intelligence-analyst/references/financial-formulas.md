# Financial Formulas Reference (v1.0.3)

This document provides the mandatory mathematical definitions for all financial metrics evaluated by the **ANSHora — Business Intelligence Analyst** skill.

---

## 1. Gross Margin: Weighted vs. Unweighted

### The Golden Rule
> **MANDATORY**: Overall gross margin MUST ALWAYS be calculated as total profit divided by total revenue over valid rows.  
> **FORBIDDEN**: Never calculate overall gross margin by taking the unweighted average of row-level margins.

### Mathematical Formulation
$$\text{Overall Gross Margin } \% = \frac{\sum_{i \in \text{paired}} \text{Profit}_i}{\sum_{i \in \text{paired}} \text{Revenue}_i} \times 100$$
Where $\text{paired}$ represents all rows where both Revenue and Profit (or COGS) are present, valid, and finite.

### Zero and Negative Denominator Guardrails
- If $\sum_{i \in \text{paired}} \text{Revenue}_i \le 0$, the weighted margin percentage is mathematically undefined or economically meaningless. It MUST be reported as `null` / `None`, accompanied by an explicit disclosure:
  *"Net revenue is zero or negative; weighted margin cannot be reliably computed."*

### Why Unweighted Averages Are Mathematically Invalid
Consider a business with two transactions:
- **Transaction A (Small order)**: Revenue = $100.00, Cost = $10.00, Profit = $90.00. Row Margin = **90.0%**.
- **Transaction B (Large bulk order)**: Revenue = $10,000.00, Cost = $9,000.00, Profit = $1,000.00. Row Margin = **10.0%**.

- **Incorrect (Unweighted Mean)**:
  $$\frac{90.0\% + 10.0\%}{2} = 50.0\% \quad \text{(Grossly Overstated Hallucination)}$$
- **Correct (Weighted ANSHora Standard)**:
  $$\text{Total Revenue} = \$10,100.00, \quad \text{Total Profit} = \$1,090.00$$
  $$\text{True Gross Margin} = \frac{\$1,090.00}{\$10,100.00} \times 100 = \mathbf{10.79\%}$$

The unweighted average skews results wildly toward low-volume, high-margin outliers. The ANSHora skill strictly enforces weighted margins.

---

## 2. Gross Profit & Paired-Row Integrity

### Consistent Profit Calculation Policy
To eliminate calculation-base distortion, ANSHora enforces a single consistent profit calculation policy across the dataset:
- **Direct Profit Policy (`direct_profit`)**: Selected when direct profit values exist. The KPI engine uses only rows with valid Revenue and direct Profit. Missing direct profit rows are NEVER filled in by synthesizing derived profit ($Revenue - Cost$) on a row-by-row basis.
- **Derived Profit Policy (`derived_profit`)**: Selected when Cost is used to derive profit. The KPI engine pairs only rows with valid Revenue and Cost, computing $\text{Profit} = \text{Revenue} - \text{Cost}$.

### Strict Prohibition Against Mixed Profit Derivation
> **CRITICAL RULE**: Never mix direct-profit and derived-profit methods across different rows in the same KPI calculation.

Consider this adversarial 3-row scenario:
```csv
Revenue,Cost,Profit
100,60,40
200,100,
300,,120
```
- **Flawed mixed approach**: Row 1 uses direct profit (40), Row 2 synthesizes derived profit ($200 - 100 = 100$), Row 3 uses direct profit (120). It reports Profit = 260 on Cost = 160, claiming 3 paired rows. This is mathematically invalid because it switches calculation bases between rows.
- **Correct ANSHora direct policy**: Selects `direct_profit`. Pairs Rows 1 and 3 only ($\text{paired\_valid\_rows} = 2$). Row 2 lacks direct profit and is excluded from profit ($\text{unpaired\_revenue\_rows} = 1$). $\text{Total Profit} = 40 + 120 = 160.0$, $\text{Paired Revenue} = 100 + 300 = 400.0$, $\text{Weighted Margin} = 160 / 400 = 40.0\%$.
- **Correct ANSHora derived policy**: Selects `derived_profit`. Pairs Rows 1 and 2 only ($\text{paired\_valid\_rows} = 2$). Row 3 lacks cost and is excluded ($\text{unpaired\_revenue\_rows} = 1$). $\text{Total Cost} = 60 + 100 = 160.0$, $\text{Total Profit} = 40 + 100 = 140.0$, $\text{Paired Revenue} = 100 + 200 = 300.0$, $\text{Weighted Margin} = 140 / 300 = 46.67\%$.

### Cost and Profit Consistency
`total_cost` within the KPI object reflects costs from the exact paired rows supporting the profit calculation. It never includes costs from rows excluded from profit derivation. Unpaired rows are transparently tracked in `unpaired_revenue_rows` and `unpaired_cost_rows`.

When `direct_profit` is selected and a missing cost is inferred as revenue minus direct profit, the report explicitly discloses `cost_source: "derived (revenue - profit)"` and tracks `inferred_cost_rows`. It never labels the entire cost total as directly sourced from the cost column when values are inferred. If all paired rows have direct cost data, it reports `cost_source: "direct from column '<name>'"`.

---

## 3. Duplicate Handling & Dual Reporting

When exact duplicate rows are detected:
- **Exact Duplicate Count & Percentage**: Counted and reported non-destructively.
- **Duplicate Revenue Exposure**:
  $$\text{Duplicate Revenue Exposure} = \sum_{r \in \text{duplicates}} \text{Revenue}_r$$
- **Dual Reporting**: Report headline KPIs both across all rows (inclusive) and with duplicates isolated (deduplicated baseline). Never silently discard duplicate rows. Duplicate exposure calculations strictly follow the same profit calculation policy as the primary KPIs.

---

## 4. Average Order Value (AOV)

### Unique Order Level (When Order ID is Available)
$$\text{AOV} = \frac{\sum \text{Revenue}}{\text{Total Unique Orders}}$$
- If transactions are logged line-by-line across multiple items, aggregate line-level revenue by `Order_ID` first.
- Report AOV based on unique orders, and disclose the line-item average separately.

### Transaction Line Level (When Order ID is Absent)
$$\text{Line-Item Average} = \frac{\sum \text{Revenue}}{\text{Total Rows}}$$
- Explicitly label as: *"Transaction-line average (Order ID column absent)"*.

---

## 5. Return Rate & Exposure

$$\text{Return Rate } \% = \frac{\text{Count of Returned Orders}}{\text{Total Orders}} \times 100$$
$$\text{Return Value Exposure} = \sum_{i \in \text{returned}} \text{Revenue}_i$$

---

## 6. Discount Rate & Revenue Leakage

$$\text{Average Discount } \% = \frac{\sum \text{Discount Percentage}}{\text{Count of Valid Rows}} \times 100$$
$$\text{Discount Leakage Amount} = \sum \left( \frac{\text{Net Revenue}}{1 - \text{Discount Rate}} - \text{Net Revenue} \right)$$
When only net revenue and discount percentage are recorded:
$$\text{Gross List Price} = \frac{\text{Revenue}}{1 - \text{Discount \%}}$$

---

## 7. Period-over-Period Growth

$$\text{Growth } \% = \frac{\text{Revenue}_{t} - \text{Revenue}_{t-1}}{\text{Revenue}_{t-1}} \times 100$$
- **Zero Denominator Protection**: If $\text{Revenue}_{t-1} = 0$, growth is mathematically undefined. Report as: `"N/A (base period is zero)"` or disclose the absolute dollar increase.
- **Negative Base Protection**: If base period revenue was negative, disclose both the direction and absolute shift rather than a distorted percentage.

---

## 8. Margin Gap (Leakage Opportunity)

To quantify money at stake when a segment underperforms company benchmark:
$$\text{Margin Gap} = \text{Benchmark Margin } \% - \text{Segment Margin } \%$$
$$\text{Money at Stake} = \text{Segment Revenue} \times \left( \frac{\text{Margin Gap}}{100} \right)$$

---

## 9. Currency Integrity Policy

1. **Currency Detection & Normalized Recognition**:
   - Scans string values for currency symbols (`$`, `€`, `₹`, `£`, `¥`) and ISO 4217 3-letter codes (`USD`, `EUR`, `INR`, `GBP`, `CAD`, `AUD`, `JPY`, `CNY`, `CHF`).
   - Normalizes equivalent representations: `₹` and `INR` both normalize to `INR`; `€` and `EUR` normalize to `EUR`; `£` and `GBP` normalize to `GBP`. Datasets with mixed symbol/code representations of the same currency are recognized as a single currency and not blocked.
   - Ambiguous symbols like `$` are handled conservatively and are NEVER automatically assumed to mean `USD`.
2. **Multi-Currency Blocking**:
   - Adding quantities of different currencies (e.g., $100 USD + €200 EUR) without daily conversion rates is mathematically invalid and produces meaningless numbers.
   - When genuinely different currencies are detected (or ambiguous symbol/code pairs such as `$` and `USD`), cross-currency summation is automatically blocked:
     - `total_revenue = null`
     - `total_cost = null`
     - `total_profit = null`
     - `average_order_value = null` (`aov_type = "blocked_mixed_currencies"`)
     - An analytical notice explains: *"Multiple currencies detected. Cross-currency summation blocked without exchange rates."*
3. **Unspecified Currency**:
   - When numeric columns contain raw numbers without currency symbols or codes, the status is set to `"unspecified"` and disclosed as raw unit quantities.
$$\text{Margin Gap} = \text{Benchmark Margin } \% - \text{Segment Margin } \%$$
$$\text{Profit Leakage Amount} = \text{Segment Revenue} \times \left(\frac{\text{Margin Gap}}{100}\right)$$
Example: A $100,000 segment operating at 25% margin when company average is 30% has a 5% margin gap, representing **$5,000.00 in profit leakage**.
