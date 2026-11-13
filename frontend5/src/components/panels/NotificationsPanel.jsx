import { useEffect, useState } from "react";

import { errorText, getNotifications, markAllNotificationsRead } from "../../services/api";

function NotificationsPanel({ onRead }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getNotifications()
      .then(async (r) => { setItems(r.notifications); if (r.unread) { await markAllNotificationsRead(); onRead?.(); } })
      .catch((e) => setError(errorText(e)));
    // eslint-disable-next-line
  }, []);

  if (error) return <div className="panel-error">{error}</div>;
  if (!items) return <div className="panel-loading">Loading…</div>;
  if (!items.length) return <div className="panel-empty">No alerts yet. Create a monitor to be notified when money is at stake.</div>;

  return (
    <div className="decision-list">
      {items.map((n) => (
        <div key={n.id} className={`decision notif ${n.severity}`}>
          <div className="decision-top"><b>{n.title}</b><span className="pill">{n.severity}</span></div>
          <p style={{ whiteSpace: "pre-line" }}>{n.body}</p>
          <div className="decision-meta"><span>{new Date(n.created_at).toLocaleString()}</span></div>
        </div>
      ))}
    </div>
  );
}

export default NotificationsPanel;
