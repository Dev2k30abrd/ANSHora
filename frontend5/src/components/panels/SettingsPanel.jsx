import { useCallback, useEffect, useState } from "react";

import {
  authorizeGmail, createProject, deleteProject, disconnectGmail, errorText, getGmailStatus, getPacks, listProjects, setDatasetPack, updateProject, updateWorkspace,
} from "../../services/api";

function SettingsPanel({ user, dataset, onUserChange, onDatasetPackChange, onProjectsChange }) {
  const [packs, setPacks] = useState([]);
  const [projects, setProjects] = useState([]);
  const [ws, setWs] = useState({ name: user.workspace.name || "", currency: user.workspace.currency || "₹" });
  const [proj, setProj] = useState({ name: "", instructions: "", industry_pack: "general" });
  const [editing, setEditing] = useState(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [gmailStatus, setGmailStatus] = useState(null);

  const load = useCallback(
    () => {
      listProjects().then((p) => { setProjects(p); onProjectsChange?.(p); }).catch((e) => setError(errorText(e)));
      getGmailStatus().then(setGmailStatus).catch(() => {});
    },
    [onProjectsChange]
  );
  useEffect(() => { getPacks().then(setPacks); load(); }, [load]);

  const saveWs = async () => {
    try { onUserChange(await updateWorkspace(ws)); setMsg("Workspace saved."); } catch (e) { setError(errorText(e)); }
  };
  const savePack = async (id) => {
    try { await setDatasetPack(dataset.id, id); onDatasetPackChange(id); setMsg("Industry pack applied to this dataset."); } catch (e) { setError(errorText(e)); }
  };
  const saveProject = async (e) => {
    e.preventDefault();
    try {
      editing ? await updateProject(editing, proj) : await createProject(proj);
      setProj({ name: "", instructions: "", industry_pack: "general" });
      setEditing(null);
      load();
    } catch (err) { setError(errorText(err)); }
  };

  const handleConnectGmail = async () => {
    try {
      const res = await authorizeGmail(window.location.href);
      if (res.authorization_url) window.location.href = res.authorization_url;
    } catch (err) {
      setError(errorText(err));
    }
  };

  const handleDisconnectGmail = async () => {
    try {
      await disconnectGmail();
      setMsg("Gmail integration disconnected.");
      getGmailStatus().then(setGmailStatus);
    } catch (err) {
      setError(errorText(err));
    }
  };

  return (
    <div className="settings-panel">
      {error && <div className="panel-error">{error}</div>}
      {msg && <div className="panel-note">{msg}</div>}

      <h3 className="section-title">Workspace</h3>
      <div className="inline-form">
        <label>Name<input value={ws.name} onChange={(e) => setWs({ ...ws, name: e.target.value })} /></label>
        <label>Currency symbol<input value={ws.currency} maxLength={4} onChange={(e) => setWs({ ...ws, currency: e.target.value })} /></label>
        <button className="upload-button" onClick={saveWs}>Save</button>
      </div>

      <h3 className="section-title">Gmail Delivery Integration</h3>
      <div className="gmail-integration-card" style={{ background: "var(--card-bg, #1e1e24)", border: "1px solid var(--border, #333)", borderRadius: 10, padding: 16, marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
          <div>
            <strong>Sender Identity: </strong>
            <span>Anshora &lt;{gmailStatus?.sender_email || "anshora.ai.agent@gmail.com"}&gt;</span>
          </div>
          <span className={`pill ${gmailStatus?.connected ? "on" : ""}`} style={{ fontSize: 11 }}>
            {gmailStatus?.connected ? "Connected" : "Disconnected"}
          </span>
        </div>
        <p style={{ fontSize: 13, color: "var(--text-sub, #888)", margin: "0 0 12px 0" }}>
          Deliver verified executive reports and data exports to managers and clients via the Google Cloud Gmail API (Project: anshora-email-delivery).
        </p>
        <div style={{ fontSize: 12, color: "var(--text-sub, #888)", marginBottom: 12 }}>
          Registered OAuth Redirect URI: <code style={{ padding: "2px 6px", background: "rgba(0,0,0,0.2)", borderRadius: 4 }}>{gmailStatus?.redirect_uri || "http://localhost:8000/api/gmail/oauth/callback"}</code>
        </div>
        <div style={{ display: "flex", gap: 10 }}>
          {gmailStatus?.connected ? (
            <button type="button" className="mini-btn danger" onClick={handleDisconnectGmail}>Disconnect Gmail</button>
          ) : (
            <button type="button" className="upload-button" onClick={handleConnectGmail} disabled={!gmailStatus?.configured}>
              {gmailStatus?.configured ? "Connect with Google OAuth" : "Set GOOGLE_CLIENT_ID to Connect"}
            </button>
          )}
        </div>
      </div>

      {dataset && (
        <>
          <h3 className="section-title">Industry pack for “{dataset.filename}”</h3>
          <div className="pack-grid">
            {packs.map((p) => (
              <button key={p.id} type="button" className={`pack ${dataset.pack_id === p.id ? "on" : ""}`} onClick={() => savePack(p.id)}>
                <span className="pack-icon">{p.icon}</span>
                <b>{p.name}</b>
                <small>{p.description}</small>
              </button>
            ))}
          </div>
        </>
      )}

      <h3 className="section-title">Projects</h3>
      <p className="context-hint">A project carries standing instructions (fiscal calendar, definitions, tone) that the analyst follows on every question. New uploads inherit the project’s pack.</p>
      <form className="stack-form" onSubmit={saveProject}>
        <input placeholder="Project name" value={proj.name} onChange={(e) => setProj({ ...proj, name: e.target.value })} required />
        <textarea rows={3} placeholder="Instructions, e.g. Fiscal year starts in April. 'Active customer' = purchased in last 90 days. Always state numbers in ₹ Crore." value={proj.instructions} onChange={(e) => setProj({ ...proj, instructions: e.target.value })} />
        <select value={proj.industry_pack || "general"} onChange={(e) => setProj({ ...proj, industry_pack: e.target.value })}>
          {packs.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
        <button className="upload-button">{editing ? "Update project" : "Create project"}</button>
      </form>
      <div className="decision-list">
        {projects.map((p) => (
          <div key={p.id} className="decision">
            <div className="decision-top"><b>{p.name}</b><span className="pill on">{p.industry_pack}</span></div>
            {p.instructions && <p>{p.instructions}</p>}
            <div className="decision-actions">
              <button type="button" className="mini-btn" onClick={() => { setEditing(p.id); setProj({ name: p.name, instructions: p.instructions || "", industry_pack: p.industry_pack || "general" }); }}>Edit</button>
              <button type="button" className="mini-btn danger" onClick={async () => { await deleteProject(p.id); load(); }}>Delete</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default SettingsPanel;
