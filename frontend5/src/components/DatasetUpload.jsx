import { useRef, useState } from "react";

import { uploadDataset } from "../services/api";

const SUPPORTED_EXTENSIONS = [".csv", ".tsv", ".xlsx", ".xls", ".json", ".parquet"];

function DatasetUpload({ onUploadSuccess }) {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef(null);

  const chooseFile = (nextFile) => {
    if (!nextFile) return;
    const name = nextFile.name.toLowerCase();
    if (!SUPPORTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
      setMessage("Supported: CSV, TSV, Excel, JSON, Parquet.");
      return;
    }
    setFile(nextFile);
    setMessage("");
  };

  const handleUpload = async () => {
    if (!file) {
      setMessage("Choose a data file first.");
      return;
    }

    try {
      setLoading(true);
      setMessage("");

      const data = await uploadDataset(file);

      setMessage("success:Dataset uploaded.");
      onUploadSuccess(data);
    } catch (error) {
      console.error(error);
      setMessage(
        error.response?.data?.detail || "Failed to upload dataset."
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="compact-upload">
      <label
        className={`file-upload-label ${dragOver ? "drag-over" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragOver(false);
          chooseFile(e.dataTransfer.files?.[0]);
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".csv,.tsv,.xlsx,.xls,.json,.parquet"
          onChange={(event) => chooseFile(event.target.files?.[0])}
        />

        <svg
          className="upload-icon"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 3v12" />
          <path d="M7 8l5-5 5 5" />
          <path d="M4 17v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
        </svg>

        <span>{file ? file.name : "Choose or drop a data file"}</span>
      </label>

      {file && (
        <button onClick={handleUpload} disabled={loading} className="upload-button">
          {loading ? (
            <>
              <span className="spinner" /> Uploading
            </>
          ) : (
            "Upload dataset"
          )}
        </button>
      )}

      {message && (
        <p
          className={`upload-message ${
            message.startsWith("success:") ? "success" : "error"
          }`}
        >
          {message.replace("success:", "")}
        </p>
      )}
    </div>
  );
}

export default DatasetUpload;
