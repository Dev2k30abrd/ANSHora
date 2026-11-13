import { useEffect, useState } from "react";

import { getDataHealth } from "../../services/api";

function scoreColor(score) {
  if (score >= 90) return "#5f8f75";
  if (score >= 75) return "#c9a13b";
  if (score >= 55) return "#c96442";
  return "#a6432f";
}

function HealthPanel({ datasetId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    getDataHealth(datasetId)
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setError(err.response?.data?.detail || "Failed to load data health."))
      .finally(() => !cancelled && setLoading(false));

    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (loading) return <div className="panel-loading">Scoring data quality…</div>;
  if (error) return <div className="panel-error">{error}</div>;
  if (!data) return null;

  const color = scoreColor(data.overall_score);

  return (
    <div className="health-panel">
      <div className="health-score-row">
        <div className="health-gauge" style={{ "--score-color": color }}>
          <span className="health-gauge-value">{data.overall_score}</span>
          <span className="health-gauge-label">/ 100</span>
        </div>
        <div>
          <div className="health-grade" style={{ color }}>{data.grade}</div>
          <div className="health-grade-sub">Overall data quality score</div>
        </div>
      </div>

      <div className="health-breakdown">
        {Object.entries(data.breakdown).map(([key, section]) => (
          <div key={key} className="health-breakdown-row">
            <span className="health-breakdown-name">{key.replace(/_/g, " ")}</span>
            <div className="health-breakdown-bar">
              <div
                className="health-breakdown-fill"
                style={{ width: `${section.score}%`, background: scoreColor(section.score) }}
              />
            </div>
            <span className="health-breakdown-score">{section.score}</span>
          </div>
        ))}
      </div>

      <div className="health-recommendations">
        <div className="sidebar-label">Recommendations</div>
        <ul>
          {data.recommendations.map((rec, i) => (
            <li key={i}>{rec}</li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default HealthPanel;
