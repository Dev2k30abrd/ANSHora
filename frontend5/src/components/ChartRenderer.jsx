import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from "recharts";

const ACCENT = "#c96442";

function ChartRenderer({ chart }) {
  if (!chart || !chart.labels || !chart.series) return null;

  const data = chart.labels.map((label, index) => {
    const row = { label };
    chart.series.forEach((series) => {
      row[series.name] = series.data[index];
    });
    return row;
  });

  return (
    <div className="chart-card">
      {chart.title && <div className="chart-title">{chart.title}</div>}

      <ResponsiveContainer width="100%" height={240}>
        {chart.type === "line" ? (
          <LineChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e3ded4" />
            <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#a6a08f" />
            <YAxis tick={{ fontSize: 11 }} stroke="#a6a08f" />
            <Tooltip
              contentStyle={{
                background: "#fff",
                border: "1px solid #e3ded4",
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            {chart.series.map((series) => (
              <Line
                key={series.name}
                type="monotone"
                dataKey={series.name}
                stroke={ACCENT}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={data} margin={{ top: 8, right: 12, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e3ded4" />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11 }}
              stroke="#a6a08f"
              interval={0}
              angle={data.length > 6 ? -30 : 0}
              textAnchor={data.length > 6 ? "end" : "middle"}
              height={data.length > 6 ? 50 : 30}
            />
            <YAxis tick={{ fontSize: 11 }} stroke="#a6a08f" />
            <Tooltip
              contentStyle={{
                background: "#fff",
                border: "1px solid #e3ded4",
                borderRadius: 8,
                fontSize: 12,
              }}
            />
            {chart.series.map((series) => (
              <Bar key={series.name} dataKey={series.name} fill={ACCENT} radius={[6, 6, 0, 0]} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export default ChartRenderer;
