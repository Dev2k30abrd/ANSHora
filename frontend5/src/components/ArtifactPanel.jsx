import { useState } from "react";

import ChartRenderer from "./ChartRenderer";
import DashboardView from "./DashboardView";
import ProfitImpact from "./ProfitImpact";
import SensitivityView from "./SensitivityView";
import TableView from "./TableView";
import { toolLabel } from "../utils/toolLabels";

function KeyValues({ result }) {
  const rows = Object.entries(result || {}).filter(
    ([k, v]) => !["evidence", "charts", "chart", "_guard_notes"].includes(k) && (typeof v === "number" || (typeof v === "string" && v.length < 140))
  );
  if (!rows.length) return null;
  return (
    <div className="kv-grid">
      {rows.slice(0, 12).map(([k, v]) => (
        <div key={k} className="kv">
          <span>{k.replace(/_/g, " ")}</span>
          <b>{typeof v === "number" ? Number(v).toLocaleString() : v}</b>
        </div>
      ))}
    </div>
  );
}

function Body({ run, onLogDecision }) {
  const res = run.result;
  if (!res) return <div className="panel-empty">Result too large to display. Ask a narrower question.</div>;
  switch (run.artifact_kind) {
    case "profit_impact":
      return <ProfitImpact data={res} onLogDecision={onLogDecision} />;
    case "sensitivity":
      return <SensitivityView data={res} />;
    case "dashboard":
      return <DashboardView data={res} />;
    case "table":
      return <TableView result={res} />;
    default: {
      const charts = [...(res.charts || []), ...(res.chart ? [res.chart] : [])];
      return (
        <>
          <KeyValues result={res} />
          {charts.map((c, i) => <ChartRenderer key={i} chart={c} />)}
        </>
      );
    }
  }
}

/** Claude-style side panel that opens the real output of a tool run. */
function ArtifactPanel({ runs, activeId, onSelect, onClose, onLogDecision }) {
  const [viewState, setViewState] = useState({ id: null, view: "result" });
  const list = (runs || []).filter((r) => r.ok);
  const run = list.find((r) => r.id === activeId) || list[list.length - 1];
  if (!run) return null;
  const view = viewState.id === run.id ? viewState.view : "result";
  const setView = (v) => setViewState({ id: run.id, view: v });

  const copy = () => navigator.clipboard?.writeText(JSON.stringify(run.result, null, 2)).catch(() => {});

  return (
    <aside className="artifact-panel">
      <div className="artifact-head">
        <div className="artifact-title">{toolLabel(run.name)}</div>
        <div className="artifact-actions">
          <button type="button" className={`seg ${view === "result" ? "on" : ""}`} onClick={() => setView("result")}>Result</button>
          <button type="button" className={`seg ${view === "proof" ? "on" : ""}`} onClick={() => setView("proof")}>Proof</button>
          <button type="button" className={`seg ${view === "raw" ? "on" : ""}`} onClick={() => setView("raw")}>Raw</button>
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close panel">×</button>
        </div>
      </div>

      {list.length > 1 && (
        <div className="artifact-tabs">
          {list.map((r) => (
            <button key={r.id} type="button" className={`tab ${r.id === run.id ? "on" : ""}`} onClick={() => onSelect(r.id)}>
              {toolLabel(r.name)}
            </button>
          ))}
        </div>
      )}

      <div className="artifact-body">
        {view === "result" && <Body run={run} onLogDecision={onLogDecision} />}
        {view === "proof" && (
          <div className="evidence-card">
            <div className="evidence-label">How this was computed</div>
            {run.evidence ? (
              <>
                <div className="evidence-row"><span>Dataset</span><span>{run.evidence.dataset_filename}</span></div>
                <div className="evidence-row"><span>Columns used</span><span>{run.evidence.columns_used?.join(", ") || "—"}</span></div>
                <div className="evidence-row"><span>Rows analyzed</span><span>{run.evidence.rows_analyzed} of {run.evidence.total_rows_in_dataset}</span></div>
                <div className="evidence-row"><span>Calculation</span><span>{run.evidence.calculation}</span></div>
                <div className="evidence-row"><span>Computed at</span><span>{run.evidence.generated_at}</span></div>
              </>
            ) : (
              <p>No evidence block for this step.</p>
            )}
          </div>
        )}
        {view === "raw" && (
          <>
            <button type="button" className="mini-btn" onClick={copy}>Copy JSON</button>
            <pre className="raw-json">{JSON.stringify(run.result, null, 2)}</pre>
          </>
        )}
      </div>
    </aside>
  );
}

export default ArtifactPanel;
