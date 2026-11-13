import { useEffect, useState } from "react";

import { getProactiveInsights } from "../../services/api";

const TYPE_META = {
  trend: { label: "Trend", color: "#7c7566" },
  anomaly: { label: "Anomaly", color: "#a6432f" },
  concentration: { label: "Observation", color: "#8f7f5f" },
  mix: { label: "Mix", color: "#8f7f5f" },
  opportunity: { label: "Opportunity", color: "#5f8f75" },
  risk: { label: "Risk", color: "#c96442" },
};

function InsightsPanel({ datasetId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    getProactiveInsights(datasetId)
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setError(err.response?.data?.detail || "Failed to scan for insights."))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (loading) return <div className="panel-loading">Scanning for trends, anomalies, risks…</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  if (data.total_findings === 0) {
    return <div className="panel-empty">No notable trends, anomalies, or risks detected in this dataset.</div>;
  }

  return (
    <div className="insights-panel">
      {data.findings.map((finding, i) => {
        const meta = TYPE_META[finding.type] || { label: finding.type, color: "#7c7566" };

        return (
          <div key={i} className="insight-card" style={{ "--type-color": meta.color }}>
            <div className="insight-card-header">
              <span className="insight-type-badge">{meta.label}</span>
              {finding.severity === "high" && <span className="insight-severity-badge">High</span>}
            </div>
            <div className="insight-title">{finding.title}</div>
            <details className="insight-detail">
              <summary>Show numbers</summary>
              <pre>{JSON.stringify(finding.detail, null, 2)}</pre>
            </details>
          </div>
        );
      })}
    </div>
  );
}

export default InsightsPanel;
