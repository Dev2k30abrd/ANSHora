import { useState } from "react";

import { errorText, importSql, importUrl } from "../../services/api";

function ConnectorsPanel({ projectId, onImported }) {
  const [tab, setTab] = useState("url");
  const [url, setUrl] = useState("");
  const [sql, setSql] = useState({ connection_url: "", query: "SELECT * FROM orders LIMIT 100000", name: "sql-import" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const go = async () => {
    setBusy(true);
    setError("");
    try {
      const ds = tab === "url" ? await importUrl(url, projectId) : await importSql({ ...sql, project_id: projectId });
      onImported(ds);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="connectors-panel">
      <div className="artifact-tabs">
        <button className={`tab ${tab === "url" ? "on" : ""}`} onClick={() => setTab("url")}>URL / Google Sheet</button>
        <button className={`tab ${tab === "sql" ? "on" : ""}`} onClick={() => setTab("sql")}>SQL database</button>
      </div>
      {error && <div className="panel-error">{error}</div>}

      {tab === "url" ? (
        <div className="stack-form">
          <p className="context-hint">Paste a link to a CSV, JSON, Parquet or Excel file, or a Google Sheet shared with “anyone with the link”.</p>
          <input placeholder="https://…" value={url} onChange={(e) => setUrl(e.target.value)} />
        </div>
      ) : (
        <div className="stack-form">
          <p className="context-hint">
            Read-only import of a SELECT query result (Postgres, MySQL, SQLite…). The connection string is used once and
            <b> never stored</b>. Install the driver on the server first (e.g. <code>pip install psycopg2-binary</code>).
          </p>
          <input placeholder="postgresql+psycopg2://user:pass@host:5432/db" value={sql.connection_url} onChange={(e) => setSql({ ...sql, connection_url: e.target.value })} />
          <textarea rows={4} value={sql.query} onChange={(e) => setSql({ ...sql, query: e.target.value })} />
          <input placeholder="Dataset name" value={sql.name} onChange={(e) => setSql({ ...sql, name: e.target.value })} />
        </div>
      )}
      <button className="upload-button" onClick={go} disabled={busy || (tab === "url" ? !url : !sql.connection_url)}>
        {busy ? "Importing…" : "Import dataset"}
      </button>
    </div>
  );
}

export default ConnectorsPanel;
