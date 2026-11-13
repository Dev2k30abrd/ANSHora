# Optional External Data Tools Reference

The **ANSHora — Business Intelligence Analyst** skill operates independently using the buyer's local compute and deterministic Python calculations. However, when deployed in environments with access to extended tools (e.g. MCP servers, marketplace data plugins), the skill can optionally leverage external context to enrich internal findings.

---

## 1. Non-Negotiable Operational Rules

1. **Independent Core**: The primary dataset analysis, data quality audit, deterministic financial calculations, root-cause decomposition, and decision reporting **must always function completely without external or paid tools**.
2. **No Data Leakage**: **NEVER** transmit private customer records, PII (Personally Identifiable Information), or confidential business datasets to third-party tools or external APIs without explicit, informed user confirmation.
3. **No Assumed Pricing**: Never assume an external tool or API call is free.
4. **Mandatory Price Quote & Confirmation**: If a tool has an associated cost or consumes paid credits, the agent must:
   - State the exact tool name and provider.
   - Quote the price or credit cost upfront.
   - Ask for explicit user approval before executing the tool call.
5. **Clear Attribution**: When external data (market trends, competitor traffic, industry benchmarks) is used, cite the provider, retrieval date, and sample limitations.

---

## 2. Potential Integration Categories

When available in the user's host environment, the following categories of external tools can complement internal business intelligence:

| Tool Category | Analytical Purpose | Permitted Input | Prohibited Input |
|---|---|---|---|
| **Market & Search Trends** (e.g. Semrush, Search Tools) | Validate whether category revenue declines align with broader industry search demand or macroeconomic contraction. | Public product categories, general industry keywords, competitor domain names. | Proprietary sales numbers, internal SKU codes, customer lists. |
| **Web Research & Browsing** (e.g. Browserbase) | Research competitor pricing changes, product launches, or supply chain disruptions. | Public product URLs, competitor marketing campaigns. | Internal margin spreadsheets, confidential supplier contracts. |
| **Enterprise BI & Data Warehouses** (e.g. Looker, Databricks) | Connect directly to governed central data warehouse models or query expanded historical partitions. | SQL queries against authorized warehouse schemas. | Unauthorized export of raw unmasked PII. |

---

## 3. Disconnected / Offline Mode Behavior

If the host environment does not have external MCP tools or marketplace plugins connected:
- Rely strictly on the dataset provided by the user.
- Acknowledge that macroeconomic or competitor context is unobserved in the local file.
- Formulate testable internal hypotheses rather than fabricating external market claims.
- Do not fabricate tool schemas, mock external APIs, or present simulated web data as real market intelligence.
