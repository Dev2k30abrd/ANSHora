import { useEffect, useRef, useState } from "react";

function BellIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
  );
}

function ThemeIcon({ dark }) {
  return dark ? (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  ) : (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

function Header({
  title,
  onToggleSidebar,
  sidebarOpen,
  theme,
  onToggleTheme,
  unread,
  onBell,
  user,
  gmailStatus,
  onOpenWorkspaces,
  onOpenSettings,
  onSignOut,
  onOpenAuth,
}) {
  const [accountMenuOpen, setAccountMenuOpen] = useState(false);
  const accountMenuRef = useRef(null);

  useEffect(() => {
    if (!accountMenuOpen) return undefined;
    const down = (e) => {
      if (accountMenuRef.current && !accountMenuRef.current.contains(e.target)) {
        setAccountMenuOpen(false);
      }
    };
    const key = (e) => e.key === "Escape" && setAccountMenuOpen(false);
    document.addEventListener("mousedown", down);
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("mousedown", down);
      document.removeEventListener("keydown", key);
    };
  }, [accountMenuOpen]);

  const isGuest = Boolean(user && (user.is_guest === true || user.role === "guest" || (typeof user.email === "string" && user.email.startsWith("guest_"))));
  const isAuthenticated = Boolean(user && !isGuest && user.id);

  return (
    <header className="topbar">
      <div className="tb-left">
        <button className="tb-btn" onClick={onToggleSidebar} aria-label="Toggle sidebar" aria-expanded={sidebarOpen}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
            <rect x="3" y="4" width="18" height="16" rx="3" />
            <path d="M9 4v16" />
          </svg>
        </button>

        {user?.workspace?.name && (
          <button
            type="button"
            className="tb-workspace-pill"
            onClick={onOpenWorkspaces}
            title="Switch or manage workspaces"
          >
            <span className="ws-dot" />
            <span className="ws-name">{user.workspace.name}</span>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        )}
      </div>

      <div className="tb-title" title={title}>{title}</div>

      <div className="tb-right">
        {gmailStatus?.connected && (
          <div className="tb-gmail-badge" title={`Gmail connected: ${gmailStatus.account_email || gmailStatus.sender_email || "Active"}`}>
            <span className="gmail-dot" />
            <span className="gmail-label">Gmail Active</span>
          </div>
        )}

        {isAuthenticated ? (
          <div className="tb-account-wrap" ref={accountMenuRef}>
            <button
              type="button"
              className="tb-user-profile-btn"
              onClick={() => setAccountMenuOpen((v) => !v)}
              aria-expanded={accountMenuOpen}
              aria-label="Account menu"
              title={`Signed in as ${user.email}`}
            >
              {user.profile_image_url ? (
                <img src={user.profile_image_url} alt={user.name} className="user-avatar-img" />
              ) : (
                <span className="user-avatar-initials">{(user.name || user.email || "?").charAt(0).toUpperCase()}</span>
              )}
              <span className="user-name-text">{user.name || user.email?.split("@")[0]}</span>
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M6 9l6 6 6-6" />
              </svg>
            </button>

            {accountMenuOpen && (
              <div className="popover tb-account-popover" role="menu">
                <div className="account-pop-header">
                  <strong>{user.name}</strong>
                  <span className="account-pop-email">{user.email}</span>
                </div>
                <div className="pop-divider" />
                <button
                  type="button"
                  className="pop-item"
                  onClick={() => { setAccountMenuOpen(false); onOpenWorkspaces?.(); }}
                >
                  Workspaces
                </button>
                <button
                  type="button"
                  className="pop-item"
                  onClick={() => { setAccountMenuOpen(false); onOpenSettings?.(); }}
                >
                  Workspace Settings
                </button>
                <div className="pop-divider" />
                <button
                  type="button"
                  className="pop-item danger"
                  onClick={() => { setAccountMenuOpen(false); onSignOut?.(); }}
                >
                  Sign Out
                </button>
              </div>
            )}
          </div>
        ) : isGuest ? (
          <div className="tb-guest-notice">
            <span className="guest-badge">Guest Session</span>
            <button type="button" className="guest-signin-btn" onClick={onOpenAuth || onSignOut}>
              Sign In
            </button>
          </div>
        ) : null}

        <button className="tb-btn" onClick={onBell} aria-label="Alerts" title="Alerts">
          <BellIcon />
          {unread > 0 && <span className="bell-badge">{unread > 9 ? "9+" : unread}</span>}
        </button>
        <button className="tb-btn" onClick={onToggleTheme} aria-label="Toggle theme" title="Toggle theme">
          <ThemeIcon dark={theme === "dark"} />
        </button>
      </div>
    </header>
  );
}

export default Header;
