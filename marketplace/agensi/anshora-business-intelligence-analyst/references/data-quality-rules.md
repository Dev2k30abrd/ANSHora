# Data Quality & Trust Rules (v1.0.3)

This reference outlines how data quality, anomalies, and trust metrics must be evaluated and reported under the **ANSHora — Business Intelligence Analyst** framework.

---

## 1. Non-Destructive Ingestion Rule

> **MANDATORY**: Never silently clean, mutate, drop, or overwrite source data.  
> All anomalies, missing entries, duplicates, and outliers must be counted, quantified, disclosed, and preserved in the audit log.

When performing analyses:
- Disclose raw row counts vs. valid rows used in calculations.
- If duplicate rows exist, report results both with all rows and with exact duplicates isolated.
- Never impute fabricated numbers for missing financial fields.

---

## 2. The Four Pillars of the Data Health Score (0–100)

The Data Health Score quantifies dataset trustworthiness on a 0 to 100 scale based on four deterministic penalties:

$$\text{Health Score} = \max\left(0.0, \, \min\left(100.0, \, 100.0 - P_{\text{missing}} - P_{\text{duplicates}} - P_{\text{outliers}} - P_{\text{types}}\right)\right)$$

| Penalty Component | Metric Formula | Maximum Deduction |
|---|---|:---:|
| **$P_{\text{missing}}$** | $\text{Overall Missing Value } \% \times 1.5$ | 40.0 points |
| **$P_{\text{duplicates}}$** | $\text{Exact Duplicate Row } \% \times 2.0$ | 30.0 points |
| **$P_{\text{outliers}}$** | $\text{Outlier Ratio across Numerics } \% \times 1.0$ | 20.0 points |
| **$P_{\text{types}}$** | $\text{String Contamination in Numerics } \% \times 1.0$ | 10.0 points |

### Reliability Tiers:
- **$\ge 85.0$**: **High Reliability** — High statistical confidence for decision-making.
- **$70.0 \le \text{Score} < 85.0$**: **Acceptable (Caveats Disclosed)** — Usable with explicit caveats noted.
- **$< 70.0$**: **Needs Review (High Risk of Skewed Findings)** — High risk of distorted metrics; review raw data before committing capital.

---

## 3. Handling Specific Anomalies

### A. Missing Values
- Report missing value percentage per column.
- For financial metrics (Revenue, Cost, Profit), exclude rows with missing values from margin denominators and state:  
  *"X rows lack revenue or cost values and were excluded from margin calculations."*

### B. Exact Duplicate Rows
- An exact duplicate is defined as a row where every single column value matches an existing row identically.
- If exact duplicates are found:
  1. Report the exact count and duplicate percentage.
  2. Compute the total revenue exposure tied to duplicate entries:
     $$\text{Duplicate Revenue Exposure} = \sum_{r \in \text{duplicates}} \text{Revenue}_r$$
  3. Present the headline metrics in dual view: both all-rows (inclusive) and deduplicated (isolated).

### C. Statistical Outlier Detection & The Zero-IQR Guardrail
- For every numeric column with at least 4 values:
  - If $\text{IQR} > 0$:
    $$\text{IQR} = Q_3 - Q_1$$
    $$\text{Lower Bound} = Q_1 - (1.5 \times \text{IQR})$$
    $$\text{Upper Bound} = Q_3 + (1.5 \times \text{IQR})$$
  - If $\text{IQR} == 0$ (central 50% of data is identical):
    - Compute standard deviation $s$ and mean $\mu$.
    - If $s == 0$ (constant column where all values are identical): $\text{outliers} = 0$.
    - If $s > 0$ (repeated values with extreme observations):
      $$\text{Lower Bound} = \mu - (2.5 \times s), \quad \text{Upper Bound} = \mu + (2.5 \times s)$$
- **Crucial Rule**: Do NOT automatically delete outliers. In e-commerce and B2B sales, high outliers frequently represent genuine VIP enterprise orders. Flag them as high-leverage observations for review, never as corrupted data.

### D. String Type Contamination in Numeric Columns
- When a column is identified as numeric, cells containing non-empty text strings that cannot be parsed into numbers (e.g., `"ERROR"`, `"invalid"`, `"corrupt"`) are counted as type contamination.
- Deducted under $P_{\text{types}}$ (capped at 10.0 points).

### E. Currency Detection, Normalization, and Mixed Currency Isolation
- Currency symbols (`$`, `€`, `₹`, `£`, `¥`) and ISO 4217 3-letter codes (`USD`, `EUR`, `INR`, etc.) are detected across financial fields, correctly removed from numeric values (prefix or suffix, with or without spaces).
- **Equivalent Representation Normalization**: Representations such as `₹` and `INR`, or `€` and `EUR`, are recognized as equivalent currencies and normalized so they are not falsely treated as mixed currencies.
- **Ambiguous Symbol Protection**: Ambiguous symbols like `$` are handled conservatively and never assumed to mean `USD`. If both `$` and `USD` appear, they are treated as distinct/ambiguous and blocked from ungrounded summation.
- **Cross-Currency Summation Prevention**: Summing amounts in genuinely different currencies without active conversion rates introduces severe data quality distortion. When mixed currencies are detected, aggregate financial sums are blocked (`total_revenue = null`, `average_order_value = null`) with an explicit disclosure notice.
- **Unspecified Currency Handling**: When numbers lack currency symbols/codes, the data is tagged with status `"unspecified"` to prevent arbitrary currency assumption.
