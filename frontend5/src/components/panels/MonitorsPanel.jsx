import { useCallback, useEffect, useState } from "react";

import { createMonitor, deleteMonitor, errorText, listMonitors, runMonitor, toggleMonitor } from "../../services/api";

const KIND_HELP = {
  profit_scan: "Re-scans for money-impacting findings and alerts when the money at stake is above your minimum.",
  anomaly: "Alerts when automatic z-score anomalies appear in any numeric column.",
  threshold: "Alerts when an aggregate of a column crosses a limit you set.",
};

function MonitorsPanel({ datasetId, columns = [] }) {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [f, setF] = useState({ name: "", kind: "profit_scan", interval: 60, min_impact: "", column: columns[0] || "", operator: ">", threshold: "", aggregation: "mean", channel: "" });

  const load = useCallback(() => listMonitors(datasetId).then(setItems).catch((e) => setError(errorText(e))), [datasetId]);
  useEffect(() => { load(); }, [load]);

  const add = async (e) => {
    e.preventDefault();
    setError("");
    const config =
      f.kind === "profit_scan" ? { min_impact: Number(f.min_impact) || 0 }
      : f.kind === "threshold" ? { column: f.column, operator: f.operator, threshold: Number(f.threshold), aggregation: f.aggregation }
      : {};
    const channels = ["in_app", ...(f.channel.trim() ? [f.channel.trim()] : [])];
    try {
      await createMonitor({ dataset_id: datasetId, name: f.name, kind: f.kind, config, interval_minutes: Number(f.interval) || 60, channels });
      setF({ ...f, name: "" });
      load();
    } catch (err) {
      setError(errorText(err));
    }
  };

  const run = async (id) => {
    setNote("");
    try {
      const r = await runMonitor(id);
      setNote(r.result.triggered ? `Triggered: ${r.result.title}` : "Ran — nothing to report right now.");
      load();
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <div className="monitors-panel">
      <p className="context-hint">Monitors watch your data on a schedule and alert you with the money at stake. Deliver to the app, Slack, Teams, a webhook or email.</p>
      {error && <div className="panel-error">{error}</div>}
      {note && <div className="panel-note">{note}</div>}

      <form className="stack-form" onSubmit={add}>
        <input placeholder="Monitor name (e.g. Weekly margin watch)" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required />
        <div className="row">
          <select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>
            <option value="profit_scan">Profit scan</option>
            <option value="anomaly">Anomaly watch</option>
            <option value="threshold">Threshold</option>
          </select>
          <input type="number" min="1" value={f.interval} onChange={(e) => setF({ ...f, interval: e.target.value })} title="Check every N minutes" />
          <span className="row-note">minutes</span>
        </div>
        <small className="hint">{KIND_HELP[f.kind]}</small>
        {f.kind === "profit_scan" && <input type="number" placeholder="Minimum money at stake to alert (optional)" value={f.min_impact} onChange={(e) => setF({ ...f, min_impact: e.target.value })} />}
        {f.kind === "threshold" && (
          <div className="row">
            <select value={f.aggregation} onChange={(e) => setF({ ...f, aggregation: e.target.value })}>{["mean", "sum", "min", "max", "count"].map((a) => <option key={a}>{a}</option>)}</select>
            <select value={f.column} onChange={(e) => setF({ ...f, column: e.target.value })}>{columns.map((c) => <option key={c}>{c}</option>)}</select>
            <select value={f.operator} onChange={(e) => setF({ ...f, operator: e.target.value })}>{[">", "<", ">=", "<=", "==", "!="].map((o) => <option key={o}>{o}</option>)}</select>
            <input type="number" placeholder="value" value={f.threshold} onChange={(e) => setF({ ...f, threshold: e.target.value })} required />
          </div>
        )}
        <input placeholder="Extra channel (optional): slack:https://hooks…  |  teams:…  |  webhook:…  |  email:you@co.com" value={f.channel} onChange={(e) => setF({ ...f, channel: e.target.value })} />
        <button className="upload-button">Create monitor</button>
      </form>

      <div className="decision-list">
        {items.map((m) => (
          <div key={m.id} className="decision">
            <div className="decision-top">
              <b>{m.name}</b>
              <span className={`pill ${m.enabled ? "on" : ""}`}>{m.enabled ? "active" : "paused"}</span>
            </div>
            <div className="decision-meta">
              <span>{m.kind.replace("_", " ")}</span>
              <span>every {m.interval_minutes} min</span>
              <span>→ {m.channels.join(", ")}</span>
              <span>{m.last_run ? `last run ${new Date(m.last_run).toLocaleString()} (${m.last_status})` : "not run yet"}</span>
            </div>
            <div className="decision-actions">
              <button type="button" className="mini-btn" onClick={() => run(m.id)}>Run now</button>
              <button type="button" className="mini-btn" onClick={async () => { await toggleMonitor(m.id); load(); }}>{m.enabled ? "Pause" : "Resume"}</button>
              <button type="button" className="mini-btn danger" onClick={async () => { await deleteMonitor(m.id); load(); }}>Delete</button>
            </div>
          </div>
        ))}
        {items.length === 0 && <div className="panel-empty">No monitors yet.</div>}
      </div>
    </div>
  );
}

export default MonitorsPanel;
