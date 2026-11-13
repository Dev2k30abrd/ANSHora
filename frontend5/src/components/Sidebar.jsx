import { useEffect, useRef, useState } from "react";

const TOOLS = [
  { key: "profit", label: "Profit impact", icon: "₹" },
  { key: "dashboard", label: "Dashboard", icon: "◧" },
  { key: "health", label: "Data health", icon: "♡" },
  { key: "insights", label: "Insights", icon: "✦" },
  { key: "report", label: "Executive report", icon: "▤" },
];
const MORE_TOOLS = [
  { key: "decisions", label: "Decision log", icon: "✓" },
  { key: "monitors", label: "Monitors", icon: "◔" },
  { key: "context", label: "Business context", icon: "≡" },
  { key: "alerts", label: "Alert rules", icon: "!" },
];

/** Closes a popover when clicking outside / pressing Escape. */
function useDismiss(open, onClose) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const down = (e) => ref.current && !ref.current.contains(e.target) && onClose();
    const key = (e) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [open, onClose]);
  return ref;
}

function Sidebar({
  open, user, datasets, dataset, chats, chatId, hasDataset,
  onNewChat, onSelectDataset, onDeleteDataset, onAddData, onToggleDuplicates,
  onOpenTool, onSelectChat, onRenameChat, onDeleteChat, onExportChat, onSettings, onSignOut,
  onOpenWorkspaces, onOpenAuth,
}) {
  const [pickerOpen, setPickerOpen] = useState(false);
  const [moreOpen, setMoreOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [chatSearch, setChatSearch] = useState("");
  const pickerRef = useDismiss(pickerOpen, () => setPickerOpen(false));
  const menuRef = useDismiss(menuOpen, () => setMenuOpen(false));

  const dupes = dataset?.summary?.duplicate_rows || 0;
  const excluded = dataset?.summary?.duplicates_excluded || 0;
  const isGuest = Boolean(user && (user.is_guest === true || user.role === "guest" || (typeof user.email === "string" && user.email.startsWith("guest_"))));
  const isAuthenticated = Boolean(user && !isGuest && user.id);

  const filteredChats = chatSearch.trim()
    ? chats.filter((c) => (c.title || "").toLowerCase().includes(chatSearch.toLowerCase()))
    : chats;

  return (
    <aside className={`sb ${open ? "open" : ""}`} aria-label="Sidebar">
      <div className="sb-top">
        <div className="sb-brand">
          <span className="brand-mark" aria-hidden="true" />
          <span className="brand-name">Anshora</span>
        </div>

        <button className="sb-new" onClick={onNewChat}>
          <span className="sb-new-icon" aria-hidden="true">+</span>
          New chat
        </button>

        <div className="sb-dataset" ref={pickerRef}>
          <button className="sb-dataset-btn" onClick={() => setPickerOpen((v) => !v)} aria-expanded={pickerOpen}>
            <span className="file-badge">{(dataset?.filename?.split(".").pop() || "—").toUpperCase().slice(0, 4)}</span>
            <span className="sb-dataset-text">
              <b>{dataset ? dataset.filename : "No dataset"}</b>
              <small>{dataset ? `${dataset.summary?.rows ?? "—"} rows · ${dataset.summary?.columns ?? "—"} columns` : "Add data to begin"}</small>
            </span>
            <span className={`chev ${pickerOpen ? "up" : ""}`} aria-hidden="true">⌄</span>
          </button>

          {pickerOpen && (
            <div className="popover sb-picker" role="menu">
              {datasets.map((d) => (
                <div key={d.id} className={`pop-row ${dataset?.id === d.id ? "on" : ""}`}>
                  <button className="pop-main" onClick={() => { onSelectDataset(d); setPickerOpen(false); }} title={d.filename}>
                    {d.filename}
                  </button>
                  <button className="pop-x" onClick={() => onDeleteDataset(d.id)} aria-label={`Delete ${d.filename}`} title="Delete dataset">×</button>
                </div>
              ))}
              <button className="pop-add" onClick={() => { onAddData(); setPickerOpen(false); }}>+ Add data (file, URL, database)</button>
            </div>
          )}
        </div>

        {dataset && dupes > 0 && (
          <button className="sb-note" onClick={onToggleDuplicates} title="Click to switch">
            {excluded > 0
              ? `${excluded} duplicate row${excluded > 1 ? "s" : ""} excluded from analysis · include`
              : `${dupes} duplicate row${dupes > 1 ? "s" : ""} included · exclude`}
          </button>
        )}
      </div>

      <div className="sb-scroll">
        {hasDataset && (
          <nav className="sb-group" aria-label="Analysis tools">
            <p className="sb-label">Tools</p>
            {TOOLS.map((t) => (
              <button key={t.key} className="sb-item" onClick={() => onOpenTool(t.key)}>
                <span className="sb-item-icon" aria-hidden="true">{t.icon}</span>{t.label}
              </button>
            ))}
            {moreOpen && MORE_TOOLS.map((t) => (
              <button key={t.key} className="sb-item" onClick={() => onOpenTool(t.key)}>
                <span className="sb-item-icon" aria-hidden="true">{t.icon}</span>{t.label}
              </button>
            ))}
            <button className="sb-item muted" onClick={() => setMoreOpen((v) => !v)}>
              <span className="sb-item-icon" aria-hidden="true">{moreOpen ? "–" : "+"}</span>{moreOpen ? "Fewer tools" : "More tools"}
            </button>
          </nav>
        )}

        <div className="sb-group">
          <div className="sb-recents-header">
            <p className="sb-label">Recents</p>
            {isGuest && <span className="sb-guest-tag">Temporary</span>}
          </div>

          {!isGuest && chats.length > 3 && (
            <div className="sb-search-wrap">
              <input
                type="text"
                placeholder="Search chats…"
                value={chatSearch}
                onChange={(e) => setChatSearch(e.target.value)}
                className="sb-chat-search"
              />
              {chatSearch && (
                <button type="button" className="sb-search-clear" onClick={() => setChatSearch("")}>
                  ×
                </button>
              )}
            </div>
          )}

          {isGuest && (
            <div className="sb-guest-banner">
              <span>Guest conversations do not save to history.</span>
              <button type="button" className="btn-guest-signup" onClick={onOpenAuth || onSignOut}>
                Sign in to persist chats
              </button>
            </div>
          )}

          {filteredChats.length === 0 && (
            <p className="sb-empty">
              {chatSearch ? "No matching chats" : isGuest ? "New temporary session" : "Your chats will appear here"}
            </p>
          )}

          {filteredChats.map((c) => (
            <div key={c.id} className={`sb-chat ${chatId === c.id ? "on" : ""}`}>
              <button className="sb-chat-main" onClick={() => onSelectChat(c.id)} onDoubleClick={() => onRenameChat(c)} title={`${c.title}\n(double-click to rename)`}>
                {c.title}
              </button>
              <button className="sb-chat-x" onClick={(e) => onDeleteChat(c.id, e)} aria-label="Delete chat" title="Delete chat">×</button>
            </div>
          ))}
        </div>
      </div>

      <div className="sb-foot" ref={menuRef}>
        {isGuest ? (
          <div className="sb-guest-foot">
            <span className="avatar avatar-guest">G</span>
            <div className="sb-user-text">
              <b>Guest Session</b>
              <small>Ephemeral sandbox</small>
            </div>
          </div>
        ) : isAuthenticated ? (
          <button className="sb-user" onClick={() => setMenuOpen((v) => !v)} aria-expanded={menuOpen}>
            {user?.profile_image_url ? (
              <img src={user.profile_image_url} alt={user.name} className="avatar avatar-img" />
            ) : (
              <span className="avatar">{(user?.name || user?.email || "?").slice(0, 1).toUpperCase()}</span>
            )}
            <span className="sb-user-text">
              <b>{user?.name || user?.email?.split("@")[0]}</b>
              <small>{user?.workspace?.name || "Workspace"}</small>
            </span>
            <span className="chev" aria-hidden="true">⋯</span>
          </button>
        ) : null}
        {isAuthenticated && menuOpen && (
          <div className="popover sb-menu" role="menu">
            <button className="pop-item" onClick={() => { setMenuOpen(false); onOpenWorkspaces?.(); }}>
              Workspaces
            </button>
            <button className="pop-item" onClick={() => { setMenuOpen(false); onSettings(); }}>Settings</button>
            {chatId && <button className="pop-item" onClick={() => { setMenuOpen(false); onExportChat(); }}>Export this chat</button>}
            <button className="pop-item" onClick={() => { setMenuOpen(false); onSignOut(); }}>Sign out</button>
          </div>
        )}
      </div>
    </aside>
  );
}

export default Sidebar;
