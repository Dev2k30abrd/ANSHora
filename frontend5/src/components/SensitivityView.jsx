import ChartRenderer from "./ChartRenderer";

const fmt = (n, cur = "") => {
  const a = Math.abs(n);
  const s = a >= 1e7 && cur === "₹" ? `${(a / 1e7).toFixed(2)} Cr` : a >= 1e5 && cur === "₹" ? `${(a / 1e5).toFixed(2)} L`
    : a >= 1e6 ? `${(a / 1e6).toFixed(2)}M` : a >= 1e3 ? `${(a / 1e3).toFixed(1)}K` : a.toFixed(0);
  return `${n < 0 ? "-" : ""}${cur}${s}`;
};

function SensitivityView({ data }) {
  if (!data?.profit_grid) return null;
  const cur = data.currency || "";
  const flat = data.profit_grid.flat();
  const lo = Math.min(...flat);
  const hi = Math.max(...flat);
  const color = (v) => {
    if (hi === lo) return "transparent";
    const base = data.base_profit;
    if (v >= base) {
      const t = hi === base ? 0 : (v - base) / (hi - base);
      return `rgba(95, 143, 117, ${0.12 + t * 0.5})`;
    }
    const t = base === lo ? 0 : (base - v) / (base - lo);
    return `rgba(201, 100, 66, ${0.12 + t * 0.5})`;
  };

  return (
    <div className="sens-view">
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">Baseline profit</div>
          <div className="kpi-value">{data.base_profit_formatted}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Best tested</div>
          <div className="kpi-value">{data.best_case.profit_formatted}</div>
          <div className="kpi-sub">
            price {data.best_case.price_pct > 0 ? "+" : ""}{data.best_case.price_pct}% · volume {data.best_case.volume_pct > 0 ? "+" : ""}{data.best_case.volume_pct}%
          </div>
        </div>
        <div className="kpi-card at-stake">
          <div className="kpi-label">Worst tested</div>
          <div className="kpi-value">{data.worst_case.profit_formatted}</div>
        </div>
        {data.break_even_price_change_pct != null && (
          <div className="kpi-card">
            <div className="kpi-label">Break-even price move</div>
            <div className="kpi-value">{data.break_even_price_change_pct.toFixed(1)}%</div>
          </div>
        )}
      </div>

      <div className="table-scroll">
        <table className="data-table heat">
          <thead>
            <tr>
              <th>Price ↓ / Volume →</th>
              {data.volume_changes_pct.map((v) => (
                <th key={v}>{v > 0 ? "+" : ""}{v}%</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.profit_grid.map((row, i) => (
              <tr key={i}>
                <th>{data.price_changes_pct[i] > 0 ? "+" : ""}{data.price_changes_pct[i]}%</th>
                {row.map((v, j) => (
                  <td key={j} style={{ background: color(v) }}>{fmt(v, cur)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="fine-print">Simulation, not observed data. {data.assumptions}</p>
      {data.charts?.map((c, i) => <ChartRenderer key={i} chart={c} />)}
    </div>
  );
}

export default SensitivityView;
