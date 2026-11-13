import { useEffect, useState } from "react";

import {
  listAlertRules,
  createAlertRule,
  deleteAlertRule,
  evaluateAlerts,
  getAlertHistory,
} from "../../services/api";

function AlertsPanel({ datasetId }) {
  const [rules, setRules] = useState([]);
  const [history, setHistory] = useState([]);
  const [triggered, setTriggered] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");

  const [form, setForm] = useState({ column: "", operator: ">", threshold: "", aggregation: "mean" });

  const refresh = () =>
    Promise.all([listAlertRules(datasetId), getAlertHistory(datasetId)]).then(([r, h]) => {
      setRules(r);
      setHistory(h);
    });

  useEffect(() => {
    refresh().finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [datasetId]);

  if (loading) return <div className="panel-loading">Loading alerts…</div>;

  return (
    <div className="alerts-panel">
      <section>
        <div className="sidebar-label">Active rules</div>

        {rules.length === 0 && (
          <p className="context-hint">
            No threshold rules yet. Anomaly monitoring (statistical outlier detection) always runs automatically
            when you check now.
          </p>
        )}

        <div className="context-list">
          {rules.map((rule) => (
            <div key={rule.id} className="context-row">
              <span>{rule.label}</span>
              <button onClick={() => deleteAlertRule(datasetId, rule.id).then(refresh)}>Remove</button>
            </div>
          ))}
        </div>

        <form
          className="context-form alert-form"
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.column || form.threshold === "") return;
            setError("");
            createAlertRule(datasetId, { ...form, threshold: parseFloat(form.threshold) })
              .then(() => {
                setForm({ column: "", operator: ">", threshold: "", aggregation: "mean" });
                refresh();
              })
              .catch((err) => setError(err.response?.data?.detail || "Could not create rule."));
          }}
        >
          <select value={form.aggregation} onChange={(e) => setForm({ ...form, aggregation: e.target.value })}>
            <option value="mean">mean</option>
            <option value="sum">sum</option>
            <option value="min">min</option>
            <option value="max">max</option>
            <option value="count">count</option>
          </select>
          <input placeholder="column" value={form.column} onChange={(e) => setForm({ ...form, column: e.target.value })} />
          <select value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })}>
            <option value=">">&gt;</option>
            <option value="<">&lt;</option>
            <option value=">=">&ge;</option>
            <option value="<=">&le;</option>
            <option value="==">=</option>
            <option value="!=">≠</option>
          </select>
          <input placeholder="threshold" type="number" value={form.threshold}
            onChange={(e) => setForm({ ...form, threshold: e.target.value })} />
          <button type="submit">Add rule</button>
        </form>
        {error && <p className="upload-message error">{error}</p>}
      </section>

      <section>
        <button
          className="upload-button"
          disabled={checking}
          onClick={() => {
            setChecking(true);
            evaluateAlerts(datasetId)
              .then((result) => {
                setTriggered(result.triggered);
                refresh();
              })
              .finally(() => setChecking(false));
          }}
        >
          {checking ? "Checking…" : "Check now"}
        </button>

        {triggered && (
          <div className="context-list" style={{ marginTop: 10 }}>
            {triggered.length === 0 && <p className="context-hint">No alerts triggered right now.</p>}
            {triggered.map((t, i) => (
              <div key={i} className="context-row alert-triggered">
                <span>{t.label}{t.current_value !== undefined ? ` — currently ${t.current_value}` : ""}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      {history.length > 0 && (
        <section>
          <div className="sidebar-label">Recent history</div>
          <div className="context-list">
            {history.slice(0, 10).map((h, i) => (
              <div key={i} className="context-row">
                <span>{h.label} · {new Date(h.triggered_at).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

export default AlertsPanel;
