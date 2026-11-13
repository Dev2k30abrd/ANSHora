import ChartRenderer from "./ChartRenderer";

function toRows(result) {
  if (!result) return { columns: [], rows: [] };
  if (result.columns && result.rows) return { columns: result.columns, rows: result.rows };
  const r = result.result;
  if (r && r.columns && r.rows) return { columns: r.columns, rows: r.rows };
  if (Array.isArray(r) && r.length && typeof r[0] === "object") return { columns: Object.keys(r[0]), rows: r };
  if (r && typeof r === "object" && !Array.isArray(r))
    return { columns: ["key", "value"], rows: Object.entries(r).map(([key, value]) => ({ key, value: typeof value === "object" ? JSON.stringify(value) : value })) };
  if (r !== undefined && r !== null) return { columns: ["result"], rows: [{ result: r }] };
  return { columns: [], rows: [] };
}

const csvCell = (v) => {
  const s = v === null || v === undefined ? "" : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

function TableView({ result }) {
  const { columns, rows } = toRows(result);

  const download = () => {
    const csv = [columns.map(csvCell).join(","), ...rows.map((r) => columns.map((c) => csvCell(r[c])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "result.csv";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1500);
  };

  return (
    <div className="table-view">
      {result?.sql && <pre className="step-code">{result.sql}</pre>}
      {result?.code && <pre className="step-code">{result.code}</pre>}
      {result?.stdout && <pre className="step-code muted">{result.stdout}</pre>}
      {rows.length > 0 && (
        <>
          <div className="table-tools">
            <span>{rows.length} row{rows.length === 1 ? "" : "s"}{result?.truncated ? " (truncated)" : ""}</span>
            <button type="button" className="mini-btn" onClick={download}>Download CSV</button>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
              </thead>
              <tbody>
                {rows.slice(0, 300).map((r, i) => (
                  <tr key={i}>{columns.map((c) => <td key={c}>{r[c] === null || r[c] === undefined ? "—" : String(r[c])}</td>)}</tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {result?.charts?.map((c, i) => <ChartRenderer key={i} chart={c} />)}
    </div>
  );
}

export default TableView;
