const TYPE_LABEL = {
  loss: "Loss",
  leak: "Leakage",
  opportunity: "Opportunity",
  exposure: "Exposure",
  trend: "Trend",
  anomaly: "Anomaly",
};

function ProfitImpact({ data, onLogDecision }) {
  if (!data) return null;
  if (data.mode === "none") {
    return (
      <div className="panel-empty">
        {(data.notes || []).map((n, i) => (
          <p key={i}>{n}</p>
        ))}
      </div>
    );
  }
  const h = data.headline?.formatted || {};
  const max = Math.max(...(data.findings || []).map((f) => f.impact_amount), 1);

  return (
    <div className="profit-view">
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Revenue</div>
          <div className="kpi-value">{h.revenue ?? "—"}</div>
        </div>
        {h.profit && (
          <div className="kpi-card">
            <div className="kpi-label">Profit</div>
            <div className="kpi-value">{h.profit}</div>
            {h.margin && <div className="kpi-sub">{h.margin} margin</div>}
          </div>
        )}
        <div className="kpi-card at-stake">
          <div className="kpi-label">Money at stake</div>
          <div className="kpi-value">{data.total_at_stake_formatted}</div>
          <div className="kpi-sub">upper bound</div>
        </div>
      </div>

      {data.findings?.length === 0 && <div className="panel-empty">No material money-impacting findings detected.</div>}

      <ol className="findings">
        {(data.findings || []).map((f) => (
          <li key={f.id} className={`finding ${f.type}`}>
            <div className="finding-top">
              <span className="finding-rank">{f.rank}</span>
              <div className="finding-title">
                {f.title}
                <span className={`finding-type ${f.type}`}>{TYPE_LABEL[f.type] || f.type}</span>
              </div>
              <div className="finding-impact">{f.impact_formatted}</div>
            </div>
            <div className="finding-bar">
              <span style={{ width: `${Math.max(4, (f.impact_amount / max) * 100)}%` }} />
            </div>
            <p className="finding-detail">{f.detail}</p>
            <div className="finding-foot">
              <span title={f.how}>How: {f.how}</span>
              <span className={`finding-conf ${f.confidence}`}>{f.confidence} confidence</span>
              {onLogDecision && f.counts_toward_total && (
                <button type="button" className="mini-btn" onClick={() => onLogDecision(f)}>
                  Log decision
                </button>
              )}
            </div>
          </li>
        ))}
      </ol>

      {data.total_note && <p className="fine-print">{data.total_note}</p>}
      {(data.notes || []).map((n, i) => (
        <p key={i} className="fine-print">• {n}</p>
      ))}
    </div>
  );
}

export default ProfitImpact;
