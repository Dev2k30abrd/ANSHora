import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ReferenceLine,
} from "recharts";

import { useTheme } from "../hooks/useTheme";

const THEME_STYLES = {
  light: {
    grid: "#e5e7eb",
    axis: "#6b7280",
    tooltipBg: "#ffffff",
    tooltipBorder: "#e5e7eb",
    tooltipText: "#111827",
  },
  dark: {
    grid: "#374151",
    axis: "#9ca3af",
    tooltipBg: "#1f2937",
    tooltipBorder: "#374151",
    tooltipText: "#f9fafb",
  },
};

// Semantic palette
const SEMANTIC_COLORS = {
  revenue: "#2563eb",   // Blue
  profit: "#059669",    // Green
  cost: "#ea580c",      // Orange
  risk: "#dc2626",      // Red
  forecast: "#7c3aed",  // Purple
  customer: "#0891b2",  // Cyan
  discount: "#d97706",  // Amber
};

const DIVERSE_PALETTE = [
  "#2563eb", // Blue
  "#059669", // Green
  "#ea580c", // Orange
  "#7c3aed", // Purple
  "#0891b2", // Cyan
  "#d97706", // Amber
  "#dc2626", // Red
  "#ec4899", // Pink
  "#0d9488", // Teal
  "#4f46e5", // Indigo
];

function getSeriesColor(seriesName, index) {
  const norm = String(seriesName || "").toLowerCase();
  if (norm.includes("customer") || norm.includes("user") || norm.includes("client") || norm.includes("account")) {
    return SEMANTIC_COLORS.customer;
  }
  if (norm.includes("discount") || norm.includes("rebate") || norm.includes("concession") || norm.includes("allowance")) {
    return SEMANTIC_COLORS.discount;
  }
  if (norm.includes("revenue") || norm.includes("sales") || norm.includes("turnover") || norm.includes("gmv")) {
    return SEMANTIC_COLORS.revenue;
  }
  if (norm.includes("profit") || norm.includes("margin") || norm.includes("gain") || norm.includes("ebitda") || norm.includes("income")) {
    return SEMANTIC_COLORS.profit;
  }
  if (norm.includes("cost") || norm.includes("expense") || norm.includes("cogs") || norm.includes("spend") || norm.includes("opex")) {
    return SEMANTIC_COLORS.cost;
  }
  if (norm.includes("risk") || norm.includes("loss") || norm.includes("leak") || norm.includes("churn") || norm.includes("return") || norm.includes("drop")) {
    return SEMANTIC_COLORS.risk;
  }
  if (norm.includes("forecast") || norm.includes("project") || norm.includes("simulat") || norm.includes("trend")) {
    return SEMANTIC_COLORS.forecast;
  }
  return DIVERSE_PALETTE[index % DIVERSE_PALETTE.length];
}

function formatValue(val) {
  if (val == null || typeof val !== "number" || isNaN(val)) return val;
  const absVal = Math.abs(val);
  const sign = val < 0 ? "-" : "";
  if (absVal >= 1e7) return `${sign}${(absVal / 1e7).toFixed(2)} Cr`;
  if (absVal >= 1e5) return `${sign}${(absVal / 1e5).toFixed(2)} L`;
  if (absVal >= 1e3) return `${sign}${(absVal / 1e3).toFixed(1)}K`;
  return Number.isInteger(val) ? val.toLocaleString() : `${sign}${absVal.toFixed(2)}`;
}

// accepts the dashboard shape {labels, series:[{name,data}]} and the tool shape {x, y}
function normalizeChart(chart) {
  if (!chart || typeof chart !== "object") return null;
  if (chart.labels && chart.series) return chart;
  if (Array.isArray(chart.x) && Array.isArray(chart.y)) {
    return {
      type: chart.type === "line" ? "line" : "bar",
      title: chart.title,
      labels: chart.x.map((v) => String(v)),
      series: [{ name: chart.y_label || chart.title || "value", data: chart.y }],
    };
  }
  return null;
}

function CustomTooltip({ active, payload, label, styles }) {
  if (!active || !payload || !payload.length) return null;
  return (
    <div style={{
      background: styles.tooltipBg,
      border: `1px solid ${styles.tooltipBorder}`,
      borderRadius: 8,
      padding: "8px 12px",
      boxShadow: "0 4px 6px -1px rgba(0,0,0,0.1)",
      color: styles.tooltipText,
      fontSize: 12,
    }}>
      <div style={{ fontWeight: 600, marginBottom: 4, color: styles.tooltipText }}>{label}</div>
      {payload.map((item) => (
        <div key={item.name} style={{ display: "flex", alignItems: "center", gap: 8, margin: "2px 0" }}>
          <span style={{ width: 8, height: 8, borderRadius: "50%", background: item.color || item.fill }} />
          <span style={{ opacity: 0.85 }}>{item.name}:</span>
          <strong style={{ marginLeft: "auto", color: (typeof item.value === "number" && item.value < 0) ? SEMANTIC_COLORS.risk : "inherit" }}>
            {formatValue(item.value)}
          </strong>
        </div>
      ))}
    </div>
  );
}

function ChartRenderer({ chart: rawChart }) {
  const theme = useTheme();
  const styles = THEME_STYLES[theme] || THEME_STYLES.light;
  const chart = normalizeChart(rawChart);

  if (!chart) return null;

  const data = chart.labels.map((label, index) => {
    const row = { label };
    chart.series.forEach((series) => {
      row[series.name] = series.data[index];
    });
    return row;
  });

  const showLegend = chart.series.length > 1;

  // Check if any series contains negative values for baseline alignment
  const hasNegativeValues = chart.series.some((s) => s.data?.some((v) => typeof v === "number" && v < 0));

  return (
    <div className="chart-card">
      {chart.title && <div className="chart-title">{chart.title}</div>}

      <ResponsiveContainer width="100%" height={260}>
        {chart.type === "line" ? (
          <LineChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={styles.grid} vertical={false} />
            <XAxis dataKey="label" tick={{ fontSize: 11, fill: styles.axis }} stroke={styles.axis} />
            <YAxis tick={{ fontSize: 11, fill: styles.axis }} stroke={styles.axis} tickFormatter={formatValue} />
            {hasNegativeValues && <ReferenceLine y={0} stroke={styles.axis} strokeWidth={1} />}
            <Tooltip content={<CustomTooltip styles={styles} />} />
            {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: styles.axis, paddingTop: 6 }} />}
            {chart.series.map((series, i) => {
              const color = getSeriesColor(series.name, i);
              const isForecast = String(series.name).toLowerCase().includes("forecast");
              return (
                <Line
                  key={series.name}
                  type="monotone"
                  dataKey={series.name}
                  stroke={color}
                  strokeWidth={2.5}
                  strokeDasharray={isForecast ? "5 4" : undefined}
                  dot={{ r: 3, fill: color }}
                  activeDot={{ r: 5 }}
                  connectNulls={false}
                />
              );
            })}
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 12, right: 16, left: 0, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke={styles.grid} vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: styles.axis }}
              stroke={styles.axis}
              interval={0}
              angle={data.length > 6 ? -30 : 0}
              textAnchor={data.length > 6 ? "end" : "middle"}
              height={data.length > 6 ? 50 : 30}
            />
            <YAxis tick={{ fontSize: 11, fill: styles.axis }} stroke={styles.axis} tickFormatter={formatValue} />
            {hasNegativeValues && <ReferenceLine y={0} stroke={styles.axis} strokeWidth={1} />}
            <Tooltip content={<CustomTooltip styles={styles} />} />
            {showLegend && <Legend wrapperStyle={{ fontSize: 12, color: styles.axis, paddingTop: 6 }} />}
            {chart.series.map((series, i) => {
              const baseColor = getSeriesColor(series.name, i);
              return (
                <Bar
                  key={series.name}
                  dataKey={series.name}
                  fill={baseColor}
                  radius={[4, 4, 0, 0]}
                >
                  {data.map((entry, entryIdx) => {
                    const val = entry[series.name];
                    const isNeg = typeof val === "number" && val < 0;
                    return (
                      <Cell
                        key={`cell-${series.name}-${entryIdx}`}
                        fill={isNeg ? SEMANTIC_COLORS.risk : baseColor}
                      />
                    );
                  })}
                </Bar>
              );
            })}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export default ChartRenderer;
