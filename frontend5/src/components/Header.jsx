function Header({ onToggleSidebar, sidebarOpen }) {
  return (
    <header className="header">
      <div className="header-content">
        <button
          className="menu-toggle"
          onClick={onToggleSidebar}
          aria-label="Toggle sidebar"
          aria-expanded={sidebarOpen}
        >
          <span />
          <span />
          <span />
        </button>

        <div className="wordmark">
          <span className="wordmark-mark" aria-hidden="true" />
          <h1>DataMind</h1>
        </div>
      </div>
    </header>
  );
}

export default Header;
