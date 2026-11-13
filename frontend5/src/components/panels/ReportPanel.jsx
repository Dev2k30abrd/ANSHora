import { useCallback, useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

import { downloadExport, generateExecutiveReport } from "../../services/api";
import ChartRenderer from "../ChartRenderer";
import EmailReportModal from "../EmailReportModal";

function ReportPanel({ datasetId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showEmailModal, setShowEmailModal] = useState(false);

  const fetchReport = useCallback(
    async (refresh = false) => {
      if (!datasetId) return;
      setLoading(true);
      setError("");
      setBusy(true);

      try {
        const result = await generateExecutiveReport(datasetId, refresh);
        setData(result);
        setError("");
      } catch (err) {
        const msg = err.response?.data?.detail || err.message || "Failed to generate report.";
        setError(msg);
      } finally {
        setLoading(false);
        setBusy(false);
      }
    },
    [datasetId]
  );

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial report load on mount
    setLoading(true);
    generateExecutiveReport(datasetId, false)
      .then((result) => {
        if (!cancelled) {
          setData(result);
          setError("");
        }
      })
      .catch((err) => {
        if (!cancelled) {
          const msg = err.response?.data?.detail || err.message || "Failed to generate report.";
          setError(msg);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          setBusy(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (loading) {
    return (
      <div className="panel-loading">
        <span className="spinner" style={{ marginRight: 8 }} />
        Writing your executive report…
      </div>
    );
  }

  if (error) {
    return (
      <div className="report-panel error-view">
        <div className="panel-error-card">
          <div className="error-icon">⚠️</div>
          <div className="error-content">
            <strong>Unable to Generate Executive Report</strong>
            <p>{error}</p>
          </div>
          <div className="error-actions">
            <button
              type="button"
              className="action-pill primary"
              onClick={() => fetchReport(true)}
              disabled={busy}
            >
              {busy ? "Generating…" : "🔄 Retry Generation"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!data) return null;

  const isDeterministic = data.source === "deterministic";

  return (
    <div className="report-panel">
      {isDeterministic && (
        <div className="deterministic-notice">
          <div className="notice-icon">📋</div>
          <div className="notice-body">
            <strong>Verified Deterministic Report</strong>
            <p>
              {data.ai_warning ||
                "Generated from verified calculations because AI narrative generation was temporarily unavailable."}
            </p>
          </div>
          <button
            type="button"
            className="action-pill btn-retry-ai"
            onClick={() => fetchReport(true)}
            disabled={busy}
            title="Try generating natural language narrative again"
          >
            {busy ? "Retrying…" : "🔄 Retry AI Narrative"}
          </button>
        </div>
      )}

      <div className="report-toolbar">
        <div className="toolbar-left">
          <span className={`toolbar-badge ${isDeterministic ? "badge-deterministic" : "badge-verified"}`}>
            {isDeterministic ? "Deterministic Verified Analysis" : "Verified Analysis"}
          </span>
        </div>
        <div className="toolbar-actions">
          <button
            type="button"
            className="action-pill"
            onClick={() => fetchReport(true)}
            disabled={busy}
            title="Refresh calculations and regenerate report"
          >
            🔄 Refresh
          </button>
          <button
            type="button"
            className="action-pill primary"
            onClick={() => setShowEmailModal(true)}
          >
            ✉️ Email via Gmail
          </button>
          <button
            type="button"
            className="action-pill"
            onClick={() => downloadExport(datasetId, "pdf")}
          >
            PDF Export
          </button>
          <button
            type="button"
            className="action-pill"
            onClick={() => downloadExport(datasetId, "xlsx")}
          >
            Excel Export
          </button>
        </div>
      </div>

      <div className="report-narrative markdown-body">
        <ReactMarkdown>{data.narrative}</ReactMarkdown>
      </div>

      {data.charts?.length > 0 && (
        <div className="chart-grid">
          {data.charts.map((chart, i) => (
            <ChartRenderer key={i} chart={chart} />
          ))}
        </div>
      )}

      {showEmailModal && (
        <EmailReportModal
          datasetId={datasetId}
          onClose={() => setShowEmailModal(false)}
        />
      )}
    </div>
  );
}

export default ReportPanel;
