import { useEffect, useState } from "react";

import { getAutoDashboard, errorText } from "../../services/api";
import DashboardView from "../DashboardView";

function DashboardPanel({ datasetId }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    getAutoDashboard(datasetId)
      .then((result) => !cancelled && setData(result))
      .catch((err) => !cancelled && setError(errorText(err, "Failed to load dashboard.")))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [datasetId]);

  if (loading) return <div className="panel-loading">Generating dashboard…</div>;
  if (error) return <div className="panel-error">{error}</div>;
  return <DashboardView data={data} />;
}

export default DashboardPanel;
