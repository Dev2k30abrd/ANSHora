import { useEffect, useState } from "react";

import { downloadExport, errorText, getProfitImpact, runSensitivity } from "../../services/api";
import EmailReportModal from "../EmailReportModal";
import ProfitImpact from "../ProfitImpact";
import SensitivityView from "../SensitivityView";

function ProfitPanel({ datasetId, onLogDecision }) {
  const [data, setData] = useState(null);
  const [sens, setSens] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [form, setForm] = useState({ elasticity: "", cost: "0" });

  useEffect(() => {
    let off = false;
    getProfitImpact(datasetId)
      .then((d) => !off && setData(d))
      .catch((e) => !off && setError(errorText(e)))
      .finally(() => !off && setLoading(false));
    return () => (off = true);
  }, [datasetId]);

  const simulate = async () => {
    setBusy("sens");
    setError("");
    try {
      setSens(await runSensitivity(datasetId, {
        cost_change_pct: Number(form.cost) || 0,
        elasticity: form.elasticity === "" ? null : Number(form.elasticity),
      }));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy("");
    }
  };

  const exportAs = async (fmt) => {
    setBusy(fmt);
    try {
      await downloadExport(datasetId, fmt);
    } catch (e) {
      setError(errorText(e, "Export failed."));
    } finally {
      setBusy("");
    }
  };

  if (loading) return <div className="panel-loading">Finding where the money is…</div>;
  return (
    <div className="profit-panel">
      {error && <div className="panel-error">{error}</div>}
      <div className="toolbar">
        <span className="toolbar-label">Dispatch or Export</span>
        <button
          type="button"
          className="mini-btn primary"
          onClick={() => setShowEmailModal(true)}
          style={{ background: "#2563eb", color: "#fff", fontWeight: 600 }}
        >
          ✉️ Email Report via Gmail
        </button>
        {["pdf", "xlsx", "html", "md"].map((f) => (
          <button key={f} type="button" className="mini-btn" disabled={!!busy} onClick={() => exportAs(f)}>
            {busy === f ? "…" : f.toUpperCase()}
          </button>
        ))}
      </div>
      <ProfitImpact data={data} onLogDecision={onLogDecision} />

      <h3 className="section-title">Price × volume what-if</h3>
      <div className="inline-form">
        <label>Price elasticity <small>(optional, e.g. -1.2)</small>
          <input value={form.elasticity} onChange={(e) => setForm({ ...form, elasticity: e.target.value })} placeholder="none" />
        </label>
        <label>Cost change %
          <input value={form.cost} onChange={(e) => setForm({ ...form, cost: e.target.value })} />
        </label>
        <button type="button" className="upload-button" onClick={simulate} disabled={busy === "sens"}>Run</button>
      </div>
      <SensitivityView data={sens} />

      {showEmailModal && (
        <EmailReportModal
          datasetId={datasetId}
          onClose={() => setShowEmailModal(false)}
        />
      )}
    </div>
  );
}

export default ProfitPanel;
