import { useEffect, useState } from "react";
import {
  createWorkspace,
  deleteWorkspace,
  errorText,
  listWorkspaces,
  setToken,
  switchWorkspace,
  updateWorkspaceById,
} from "../../services/api";

function WorkspacesPanel({ user, onWorkspaceChanged }) {
  const [workspaces, setWorkspaces] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [editingId, setEditingId] = useState(null);
  const [editName, setEditName] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      const list = await listWorkspaces();
      setWorkspaces(list);
    } catch (err) {
      setError(errorText(err, "Failed to load workspaces."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initial load of workspaces on panel open
    load();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      await createWorkspace({ name: newName.trim() });
      setNewName("");
      setCreating(false);
      load();
    } catch (err) {
      setError(errorText(err, "Could not create workspace."));
    }
  };

  const handleSwitch = async (id) => {
    if (id === user.workspace?.id) return;
    try {
      const res = await switchWorkspace(id);
      setToken(res.token);
      onWorkspaceChanged(res.user);
      load();
    } catch (err) {
      setError(errorText(err, "Could not switch workspace."));
    }
  };

  const handleRename = async (id) => {
    if (!editName.trim()) return;
    try {
      await updateWorkspaceById(id, { name: editName.trim() });
      setEditingId(null);
      load();
    } catch (err) {
      setError(errorText(err, "Could not rename workspace."));
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm("Are you sure you want to delete this workspace and all associated datasets and chats?")) return;
    try {
      const res = await deleteWorkspace(id);
      if (res.active_workspace_id) {
        const switchRes = await switchWorkspace(res.active_workspace_id);
        setToken(switchRes.token);
        onWorkspaceChanged(switchRes.user);
      }
      load();
    } catch (err) {
      setError(errorText(err, "Could not delete workspace."));
    }
  };

  return (
    <div className="workspaces-panel">
      <div className="panel-header-desc">
        <p>Workspaces provide isolated environments for your datasets, projects, conversations, and reports.</p>
      </div>

      {error && <div className="message-error">{error}</div>}

      <div className="workspaces-list">
        {loading ? (
          <div className="loading-state">Loading workspaces…</div>
        ) : (
          workspaces.map((w) => {
            const isActive = w.id === user.workspace?.id;
            return (
              <div key={w.id} className={`workspace-card ${isActive ? "active" : ""}`}>
                <div className="ws-card-left">
                  <div className="ws-card-header">
                    {editingId === w.id ? (
                      <div className="ws-rename-box">
                        <input
                          type="text"
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          autoFocus
                        />
                        <button type="button" className="btn-sm primary" onClick={() => handleRename(w.id)}>
                          Save
                        </button>
                        <button type="button" className="btn-sm" onClick={() => setEditingId(null)}>
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <>
                        <h4 className="ws-card-title">{w.name}</h4>
                        {isActive && <span className="badge-active">Active Workspace</span>}
                      </>
                    )}
                  </div>
                  <div className="ws-card-meta">
                    <span>Currency: {w.currency || "₹"}</span>
                    <span>Industry: {w.industry_pack || "General"}</span>
                  </div>
                </div>

                <div className="ws-card-actions">
                  {!isActive && (
                    <button type="button" className="btn-sm primary" onClick={() => handleSwitch(w.id)}>
                      Switch to Workspace
                    </button>
                  )}
                  {editingId !== w.id && (
                    <button
                      type="button"
                      className="btn-sm"
                      onClick={() => {
                        setEditingId(w.id);
                        setEditName(w.name);
                      }}
                    >
                      Rename
                    </button>
                  )}
                  {workspaces.length > 1 && !isActive && (
                    <button type="button" className="btn-sm danger" onClick={() => handleDelete(w.id)}>
                      Delete
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className="workspace-create-section">
        {creating ? (
          <form onSubmit={handleCreate} className="ws-create-form">
            <h4>Create New Workspace</h4>
            <input
              type="text"
              placeholder="Workspace name (e.g. Acme Corp, Q4 Expansion)"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
              autoFocus
            />
            <div className="form-buttons">
              <button type="submit" className="btn-sm primary">
                Create Workspace
              </button>
              <button type="button" className="btn-sm" onClick={() => setCreating(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <button type="button" className="btn-create-ws" onClick={() => setCreating(true)}>
            + Create another workspace
          </button>
        )}
      </div>
    </div>
  );
}

export default WorkspacesPanel;
