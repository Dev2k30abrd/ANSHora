# Evidence & Decision Reporting Reference

This guide specifies the evidence standards, reporting structure, and decision intelligence logging required for deliverables produced by the **ANSHora — Business Intelligence Analyst** skill.

---

## 1. The Evidence Grounding Standard

> **Core Principle**: An analysis is only as credible as its traceability.  
> Every monetary amount, percentage, ratio, and row count must trace directly to the underlying dataset or an explicit mathematical formula.

### Rules for Numerical Evidence:
1. **Source Tracing**: Quote the specific column name, row count, and filter condition supporting any numerical statement.
2. **No Floating Numbers**: Never introduce a number into a summary paragraph that was not calculated in the analytical table or facts section.
3. **Disclosure of Uncertainty**: When estimating impact, state the core assumptions clearly:
   - *"Assumes zero volume churn."*
   - *"Based on 6-month historical baseline of $X."*
4. **No 100% Guarantees**: Never state that a business action is guaranteed to produce a financial outcome. Business environments have external confounders. Frame impacts as *projected opportunities based on current baseline*.

---

## 2. Standard Executive Decision Report Structure

When producing a comprehensive analysis for a business stakeholder, format the deliverable using these 7 structured sections:

### Section 1: Executive Summary
A concise 2–3 sentence executive briefing:
- Headline performance (total revenue, gross profit, overall weighted margin).
- Primary commercial risk or opportunity identified.
- Top recommended immediate action.

### Section 2: Headline Financial KPIs
A clean markdown table presenting:
- Total Revenue.
- Total COGS / Cost.
- Gross Profit.
- Overall Gross Margin (weighted).
- Average Order Value (AOV).
- Return Rate & Discount Rate (if columns present).

### Section 3: Data Quality & Trust Audit
- Data Health Score (0–100).
- Row and column counts.
- Missing values and exact duplicate rows disclosed.
- Outlier warnings.
- Explicit capability boundaries (what the dataset can and cannot prove).

### Section 4: Segment & Category Breakdown
Comparative tables across primary business dimensions:
- Segment name, order count, revenue share %, gross profit, and segment margin %.
- Ranking by total money generated and margin efficiency.

### Section 5: Root-Cause Investigation
- Price vs. Volume vs. Cost driver decomposition.
- Segment contribution to overall revenue or margin shifts.
- Distinctly labeled hypotheses explaining observed variances.

### Section 6: Prioritized Recommendations (Ranked by Money at Stake)
Each recommendation must include:
- **Priority**: High / Medium / Low.
- **Identified Gap / Leakage**: Exact dollar amount at stake.
- **Proposed Operational Action**: Concrete, practical business step.
- **Expected Impact**: Projected financial gain and core assumptions.
- **Assigned Owner**: Role responsible (e.g. Head of Merchandising, Sales Director).
- **Review Date**: Suggested timeline for measurement.

### Section 7: Decision Log Entry
A formal decision tracking record to enable closing the loop:

```markdown
### Decision Log Record
- **Decision Title**: [Actionable summary]
- **Category**: [Pricing / Merchandising / Operations / Channel]
- **Baseline Value**: [Current metric value, e.g. 27.66% margin]
- **Target Value**: [Target metric value, e.g. 31.00% margin]
- **Expected Financial Impact**: [e.g. +$3,590.00 Gross Profit]
- **Owner**: [Role / Department]
- **Review Date**: [Specific date or interval, e.g. 90 days]
- **Verification Method**: [Exact metric column and formula to re-evaluate]
```
