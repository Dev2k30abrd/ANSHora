import { useCallback, useEffect, useState } from "react";

import {
  createDecision, deleteDecision, errorText, evaluateDecision, getDecisionSummary, listDecisions, recordDecisionOutcome, setDecisionStatus,
} from "../../services/api";

const STATUSES = ["Proposed", "Approved", "In progress", "Completed", "Rejected"];
const PRIORITIES = ["critical", "high", "medium", "low"];
const CONFIDENCES = ["high", "medium", "low"];

function DecisionsPanel({ datasetId, columns = [], prefill, currency = "₹" }) {
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState(null);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("all");
  const [outcomeModal, setOutcomeModal] = useState(null); // decision being evaluated
  const [outcomeForm, setOutcomeForm] = useState({ actual_outcome: "", measured_impact: "", followed_recommendation: true, status: "Completed" });

  const [form, setForm] = useState({
    title: prefill?.title || "",
    problem: prefill?.detail || "",
    action: prefill?.how || prefill?.detail || "",
    assumptions: "",
    risks: "",
    confidence: prefill?.confidence || "medium",
    justification: "",
    priority: (prefill?.impact_amount || 0) > 100000 ? "high" : "medium",
    owner: "",
    metric_column: columns[0] || "",
    aggregation: "sum",
    direction: "up",
    expected_impact: prefill?.impact_amount ?? "",
    review_date: "",
    status: "Proposed",
  });

  const load = useCallback(async () => {
    try {
      setItems(await listDecisions(datasetId));
      setSummary(await getDecisionSummary());
    } catch (e) {
      setError(errorText(e));
    }
  }, [datasetId]);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch on mount / dataset change
  useEffect(() => { load(); }, [load]);

  const add = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await createDecision({
        ...form,
        dataset_id: datasetId,
        expected_impact: form.expected_impact === "" ? null : Number(form.expected_impact),
        evidence: prefill ? JSON.stringify(prefill) : null,
      });
      setForm({
        title: "", problem: "", action: "", assumptions: "", risks: "", confidence: "medium",
        justification: "", priority: "medium", owner: "", metric_column: columns[0] || "",
        aggregation: "sum", direction: "up", expected_impact: "", review_date: "", status: "Proposed",
      });
      load();
    } catch (err) {
      setError(errorText(err));
    }
  };

  const submitOutcome = async (e) => {
    e.preventDefault();
    if (!outcomeModal) return;
    try {
      await recordDecisionOutcome(outcomeModal.id, {
        actual_outcome: outcomeForm.actual_outcome,
        measured_impact: outcomeForm.measured_impact === "" ? null : Number(outcomeForm.measured_impact),
        followed_recommendation: outcomeForm.followed_recommendation,
        status: outcomeForm.status,
      });
      setOutcomeModal(null);
      load();
    } catch (err) {
      setError(errorText(err));
    }
  };

  const money = (n) => (n == null ? "—" : `${currency}${Math.round(n).toLocaleString()}`);

  const filtered = items.filter((d) => {
    if (activeTab === "all") return true;
    const st = (d.status || "").toLowerCase();
    if (activeTab === "active") return st === "proposed" || st === "approved" || st === "in progress" || st === "open" || st === "in_progress";
    if (activeTab === "completed") return st === "completed" || st === "done";
    return true;
  });

  return (
    <div className="decisions-panel">
      <div className="decisions-header">
        <p className="context-hint">
          Connect analysis to execution. Turn analytical findings into structured decisions, define owners and expected returns, and track whether your actions delivered the measured ROI.
        </p>
      </div>

      {summary && summary.total > 0 && (
        <div className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-label">Logged Decisions</div>
            <div className="kpi-value">{summary.total}</div>
            <div className="kpi-sub">{summary.by_status?.completed || 0} completed</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">Estimated Impact (Goal)</div>
            <div className="kpi-value">{money(summary.expected_total)}</div>
            <div className="kpi-sub">projected benefit</div>
          </div>
          <div className="kpi-card at-stake" style={{ borderColor: "#10b981" }}>
            <div className="kpi-label">Measured Realized Impact</div>
            <div className="kpi-value" style={{ color: "#10b981" }}>{money(summary.realized_total)}</div>
            <div className="kpi-sub">{summary.evaluated} verified outcomes</div>
          </div>
        </div>
      )}

      {error && <div className="panel-error">{error}</div>}

      <details className="decision-form-accordion" open={!!prefill}>
        <summary className="accordion-summary">
          <strong>+ Create New Structured Decision</strong>
          {prefill && <span className="prefill-tag">Prefilled from finding</span>}
        </summary>
        <form className="stack-form" onSubmit={add} style={{ marginTop: 12 }}>
          <div className="form-row">
            <label>
              <span>Decision Title *</span>
              <input
                placeholder="e.g. Cap Consumer segment discount to 10%"
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
                required
              />
            </label>
          </div>

          <div className="form-row-grid">
            <label>
              <span>Business Problem</span>
              <input
                placeholder="What leak, cost, or inefficiency triggered this?"
                value={form.problem}
                onChange={(e) => setForm({ ...form, problem: e.target.value })}
              />
            </label>
            <label>
              <span>Recommended Action *</span>
              <input
                placeholder="What concrete operational action will be taken?"
                value={form.action}
                onChange={(e) => setForm({ ...form, action: e.target.value })}
                required
              />
            </label>
          </div>

          <div className="form-row-grid">
            <label>
              <span>Estimated Impact ({currency})</span>
              <input
                type="number"
                placeholder="Expected profit improvement"
                value={form.expected_impact}
                onChange={(e) => setForm({ ...form, expected_impact: e.target.value })}
              />
            </label>
            <label>
              <span>Owner</span>
              <input
                placeholder="Person or team accountable"
                value={form.owner}
                onChange={(e) => setForm({ ...form, owner: e.target.value })}
              />
            </label>
          </div>

          <div className="form-row-grid" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
            <label>
              <span>Status</span>
              <select value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </label>
            <label>
              <span>Priority</span>
              <select value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })}>
                {PRIORITIES.map((p) => <option key={p} value={p}>{p.toUpperCase()}</option>)}
              </select>
            </label>
            <label>
              <span>Confidence</span>
              <select value={form.confidence} onChange={(e) => setForm({ ...form, confidence: e.target.value })}>
                {CONFIDENCES.map((c) => <option key={c} value={c}>{c.toUpperCase()}</option>)}
              </select>
            </label>
          </div>

          <div className="form-row-grid">
            <label>
              <span>Assumptions</span>
              <input
                placeholder="e.g. Demand volume remains constant"
                value={form.assumptions}
                onChange={(e) => setForm({ ...form, assumptions: e.target.value })}
              />
            </label>
            <label>
              <span>Risks</span>
              <input
                placeholder="e.g. Competitor matching pricing"
                value={form.risks}
                onChange={(e) => setForm({ ...form, risks: e.target.value })}
              />
            </label>
          </div>

          <div className="row">
            <select value={form.metric_column} onChange={(e) => setForm({ ...form, metric_column: e.target.value })}>
              <option value="">Baseline Metric (Optional)</option>
              {columns.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select value={form.aggregation} onChange={(e) => setForm({ ...form, aggregation: e.target.value })}>
              {["sum", "mean", "min", "max", "median", "count"].map((a) => <option key={a}>{a}</option>)}
            </select>
            <select value={form.direction} onChange={(e) => setForm({ ...form, direction: e.target.value })}>
              <option value="up">Higher is better</option>
              <option value="down">Lower is better</option>
            </select>
          </div>

          <button className="upload-button">Log Decision Record</button>
        </form>
      </details>

      <div className="decision-filter-tabs">
        <button className={`tab-pill ${activeTab === "all" ? "active" : ""}`} onClick={() => setActiveTab("all")}>All ({items.length})</button>
        <button className={`tab-pill ${activeTab === "active" ? "active" : ""}`} onClick={() => setActiveTab("active")}>In Flight</button>
        <button className={`tab-pill ${activeTab === "completed" ? "active" : ""}`} onClick={() => setActiveTab("completed")}>Completed & Measured</button>
      </div>

      <div className="decision-list">
        {filtered.map((d) => (
          <div key={d.id} className="decision-card">
            <div className="decision-top">
              <div className="decision-heading">
                <span className={`priority-badge ${d.priority || "medium"}`}>{d.priority || "medium"}</span>
                <b>{d.title}</b>
              </div>
              <div className="decision-status-box">
                <select
                  value={d.status || "Proposed"}
                  onChange={async (e) => { await setDecisionStatus(d.id, e.target.value); load(); }}
                >
                  {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
            </div>

            {d.problem && <div className="decision-problem"><strong>Problem:</strong> {d.problem}</div>}
            {d.action && <div className="decision-action"><strong>Action:</strong> {d.action}</div>}

            <div className="decision-meta-grid">
              <div><span>Owner:</span> <strong>{d.owner || "Unassigned"}</strong></div>
              <div><span>Confidence:</span> <strong>{d.confidence || "medium"}</strong></div>
              <div><span>Expected Impact:</span> <strong className="good">{money(d.expected_impact)} (est.)</strong></div>
              <div><span>Measured Impact:</span> <strong className={d.measured_impact != null && d.measured_impact >= 0 ? "good" : "subtle"}>{money(d.measured_impact != null ? d.measured_impact : d.realized_impact)} (actual)</strong></div>
            </div>

            {d.actual_outcome && (
              <div className="decision-outcome-box">
                <div className="outcome-title">
                  <span>Actual Measured Result</span>
                  {d.followed_recommendation !== null && (
                    <span className="followed-pill">{d.followed_recommendation ? "✓ Followed recommendation" : "✗ Did not follow"}</span>
                  )}
                </div>
                <p>{d.actual_outcome}</p>
              </div>
            )}

            <div className="decision-actions">
              <button
                type="button"
                className="mini-btn primary"
                onClick={() => {
                  setOutcomeModal(d);
                  setOutcomeForm({
                    actual_outcome: d.actual_outcome || "",
                    measured_impact: d.measured_impact != null ? d.measured_impact : "",
                    followed_recommendation: d.followed_recommendation ?? true,
                    status: "Completed",
                  });
                }}
              >
                📝 Record Actual Outcome
              </button>
              {d.metric_column && (
                <button type="button" className="mini-btn" onClick={async () => { await evaluateDecision(d.id); load(); }}>
                  Re-measure Baseline
                </button>
              )}
              <button type="button" className="mini-btn danger" onClick={async () => { await deleteDecision(d.id); load(); }}>
                Delete
              </button>
            </div>
          </div>
        ))}
        {filtered.length === 0 && <div className="panel-empty">No decisions match this filter.</div>}
      </div>

      {/* Outcome Recording Modal */}
      {outcomeModal && (
        <div className="mini-modal-overlay">
          <div className="mini-modal">
            <h4>Record Actual Decision Outcome: {outcomeModal.title}</h4>
            <form onSubmit={submitOutcome} className="stack-form">
              <label>
                <span>Was the recommended action followed?</span>
                <select
                  value={outcomeForm.followed_recommendation ? "yes" : "no"}
                  onChange={(e) => setOutcomeForm({ ...outcomeForm, followed_recommendation: e.target.value === "yes" })}
                >
                  <option value="yes">Yes, we followed the recommendation</option>
                  <option value="no">No, we took a different action or rejected it</option>
                </select>
              </label>

              <label>
                <span>Actual Business Outcome Narrative *</span>
                <textarea
                  rows={3}
                  required
                  placeholder="Describe what occurred after executing or rejecting this decision..."
                  value={outcomeForm.actual_outcome}
                  onChange={(e) => setOutcomeForm({ ...outcomeForm, actual_outcome: e.target.value })}
                />
              </label>

              <label>
                <span>Measured Financial Impact ({currency})</span>
                <input
                  type="number"
                  placeholder="Actual realized money gain or loss"
                  value={outcomeForm.measured_impact}
                  onChange={(e) => setOutcomeForm({ ...outcomeForm, measured_impact: e.target.value })}
                />
              </label>

              <div className="modal-actions" style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 14 }}>
                <button type="button" className="mini-btn" onClick={() => setOutcomeModal(null)}>Cancel</button>
                <button type="submit" className="upload-button">Save Outcome & Close Loop</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default DecisionsPanel;
