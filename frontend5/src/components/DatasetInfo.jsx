function fileExtBadge(filename = "") {
  const ext = filename.split(".").pop()?.toUpperCase() || "FILE";
  return ext.length > 4 ? ext.slice(0, 4) : ext;
}

function DatasetInfo({ dataset }) {
  if (!dataset) return null;

  const summary = dataset.summary;

  return (
    <div className="dataset-panel">
      <div className="dataset-label">ACTIVE DATASET</div>

      <div className="dataset-name">
        <div className="file-icon">{fileExtBadge(dataset.filename)}</div>
        <span>{dataset.filename}</span>
      </div>

      <div className="dataset-stats">
        <div>
          <strong>{summary?.rows ?? "—"}</strong>
          <span>Rows</span>
        </div>

        <div>
          <strong>{summary?.columns ?? "—"}</strong>
          <span>Columns</span>
        </div>
      </div>

      {summary?.duplicate_rows > 0 && (
        <div className="dataset-warning">
          {summary.duplicate_rows} duplicate row
          {summary.duplicate_rows === 1 ? "" : "s"} detected
        </div>
      )}

      <div className="dataset-status">
        <span className="status-dot"></span>
        Ready to analyze
      </div>
    </div>
  );
}

export default DatasetInfo;
