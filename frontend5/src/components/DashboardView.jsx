import ChartRenderer from "./ChartRenderer";

/** Pure renderer for the auto-dashboard result (used by the panel and the artifact side panel). */
function DashboardView({ data }) {
  if (!data) return null;
  return (
    <div className="dashboard-panel">
      <div className="kpi-grid">
        {(data.kpis || []).map((kpi) => (
          <div key={kpi.metric} className="kpi-card">
            <div className="kpi-label">{kpi.metric}</div>
            <div className="kpi-value">{Number(kpi.sum).toLocaleString()}</div>
            <div className="kpi-sub">
              avg {Number(kpi.mean).toLocaleString()} · {kpi.count} records
            </div>
          </div>
        ))}
      </div>
      <div className="chart-grid">
        {(data.charts || []).map((chart, i) => (
          <ChartRenderer key={i} chart={chart} />
        ))}
      </div>
    </div>
  );
}

export default DashboardView;
