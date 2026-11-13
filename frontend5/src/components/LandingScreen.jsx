import { useState } from "react";
import { errorText, getGoogleAuthUrl, login, loginGuest, register, setGuestToken, setToken } from "../services/api";

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

function GoogleIcon() {
  return (
    <svg className="google-icon" viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
      <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z" />
      <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.27 21.43 7.33 24 12 24z" />
      <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.17 0 10.03 0 12s.45 3.83 1.25 5.42l4.03-3.15z" />
      <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.27 2.57 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z" />
    </svg>
  );
}

function MailIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <polyline points="22,6 12,13 2,6" />
    </svg>
  );
}

function LandingScreen({ onAuthed, onGuest, theme, onToggleTheme }) {
  const [viewMode, setViewMode] = useState("overview"); // "overview" | "email"
  const [authMode, setAuthMode] = useState("login"); // "login" | "register"
  const [form, setForm] = useState({ name: "", email: "", password: "", workspace_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [guestBusy, setGuestBusy] = useState(false);
  const [showForgotNotice, setShowForgotNotice] = useState(false);

  const setField = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleGoogleSignIn = async () => {
    setGoogleBusy(true);
    setError("");
    try {
      // Requests Google Sign-In with incremental Gmail send permission
      const data = await getGoogleAuthUrl(window.location.origin, true);
      if (data?.url) {
        window.location.href = data.url;
      } else {
        throw new Error("Server did not return an authorization URL.");
      }
    } catch (err) {
      setError(errorText(err, "Google Sign-In is unavailable. Check server configuration."));
      setGoogleBusy(false);
    }
  };

  const handleGuestEntry = async () => {
    setGuestBusy(true);
    setError("");
    try {
      const res = await loginGuest();
      // Store ephemeral guest token strictly in memory
      setGuestToken(res.token);
      onGuest({ ...res.user, is_guest: true });
    } catch (err) {
      setError(errorText(err, "Could not initialize guest session."));
      setGuestBusy(false);
    }
  };

  const submitEmailAuth = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res =
        authMode === "login"
          ? await login({ email: form.email.trim(), password: form.password })
          : await register({
              email: form.email.trim(),
              password: form.password,
              name: form.name.trim(),
              workspace_name: form.workspace_name.trim() || undefined,
            });
      setToken(res.token);
      onAuthed(res.user);
    } catch (err) {
      setError(errorText(err, authMode === "login" ? "Invalid email or password." : "Could not create account."));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="welcome-screen">
      {/* Top Bar with understated brand wordmark & theme toggle */}
      <header className="welcome-nav">
        <div className="welcome-wordmark">
          <span className="wordmark-text">ANSHora</span>
        </div>
        <div className="welcome-nav-actions">
          <button
            type="button"
            className="welcome-theme-toggle"
            onClick={onToggleTheme}
            aria-label="Toggle theme"
            title="Toggle theme"
          >
            <ThemeIcon dark={theme === "dark"} />
          </button>
        </div>
      </header>

      {/* Main Editorial Hero & Large Auth Panel */}
      <main className="welcome-main">
        <div className="welcome-container">
          {/* Large Editorial Headline & Supporting Quote */}
          <section className="welcome-hero-content">
            <h1 className="welcome-headline">
              Question the numbers.<br />
              <span className="headline-highlight">Discover what matters.</span>
            </h1>
            <p className="welcome-quote">
              &ldquo;Your business data deserves better questions — and decisions backed by evidence.&rdquo;
            </p>
          </section>

          {/* Large, Prominent Authentication Panel */}
          <div className="welcome-panel-wrap">
            <div className="welcome-auth-panel">
              {viewMode === "overview" ? (
                <div className="welcome-entry-stack">
                  {error && <div className="welcome-error-banner" role="alert">{error}</div>}

                  {/* 1. Continue with Google */}
                  <div className="entry-action-group">
                    <button
                      type="button"
                      className="btn-welcome-primary google-entry"
                      onClick={handleGoogleSignIn}
                      disabled={googleBusy || busy || guestBusy}
                    >
                      <GoogleIcon />
                      <span>{googleBusy ? "Connecting to Google…" : "Continue with Google"}</span>
                    </button>
                    <p className="entry-scope-notice">
                      Includes optional Gmail authorization for executive report delivery. You can also sign in with email or explore as a guest.
                    </p>
                  </div>

                  {/* 2. Continue with Email */}
                  <button
                    type="button"
                    className="btn-welcome-secondary email-entry"
                    onClick={() => { setViewMode("email"); setError(""); }}
                    disabled={googleBusy || busy || guestBusy}
                  >
                    <MailIcon />
                    <span>Continue with Email</span>
                  </button>

                  {/* Subtle Divider */}
                  <div className="welcome-divider" aria-hidden="true">
                    <span>or</span>
                  </div>

                  {/* 3. Explore as Guest */}
                  <button
                    type="button"
                    className="btn-welcome-guest"
                    onClick={handleGuestEntry}
                    disabled={guestBusy || busy || googleBusy}
                  >
                    <div className="guest-label-block">
                      <span className="guest-main-title">
                        {guestBusy ? "Launching Guest Session…" : "Explore as Guest"}
                      </span>
                      <span className="guest-sub-title">Instant access · Ephemeral sandbox · No account required</span>
                    </div>
                    <span className="guest-forward-arrow" aria-hidden="true">→</span>
                  </button>
                </div>
              ) : (
                /* Email Sign-In / Register Mode */
                <div className="welcome-email-flow">
                  <div className="flow-nav-header">
                    <button
                      type="button"
                      className="btn-flow-back"
                      onClick={() => { setViewMode("overview"); setError(""); }}
                    >
                      ← Back
                    </button>
                    <div className="flow-tab-pills" role="tablist">
                      <button
                        type="button"
                        role="tab"
                        aria-selected={authMode === "login"}
                        className={`tab-pill ${authMode === "login" ? "active" : ""}`}
                        onClick={() => { setAuthMode("login"); setError(""); }}
                      >
                        Sign In
                      </button>
                      <button
                        type="button"
                        role="tab"
                        aria-selected={authMode === "register"}
                        className={`tab-pill ${authMode === "register" ? "active" : ""}`}
                        onClick={() => { setAuthMode("register"); setError(""); }}
                      >
                        Create Account
                      </button>
                    </div>
                  </div>

                  {error && <div className="welcome-error-banner" role="alert">{error}</div>}

                  <form className="welcome-form" onSubmit={submitEmailAuth}>
                    {authMode === "register" && (
                      <div className="welcome-field">
                        <label htmlFor="reg-name">Your Name</label>
                        <input
                          id="reg-name"
                          type="text"
                          required
                          value={form.name}
                          onChange={setField("name")}
                          placeholder="e.g. Alex Rivera"
                          autoComplete="name"
                        />
                      </div>
                    )}

                    <div className="welcome-field">
                      <label htmlFor="login-email">Email Address</label>
                      <input
                        id="login-email"
                        type="email"
                        required
                        value={form.email}
                        onChange={setField("email")}
                        placeholder="you@company.com"
                        autoComplete="email"
                      />
                    </div>

                    <div className="welcome-field">
                      <div className="field-label-row">
                        <label htmlFor="login-password">Password</label>
                        {authMode === "login" && (
                          <button
                            type="button"
                            className="btn-forgot-hint"
                            onClick={() => setShowForgotNotice((v) => !v)}
                          >
                            Forgot?
                          </button>
                        )}
                      </div>
                      <input
                        id="login-password"
                        type="password"
                        required
                        minLength={authMode === "register" ? 8 : undefined}
                        value={form.password}
                        onChange={setField("password")}
                        placeholder={authMode === "register" ? "Min. 8 characters" : "Enter password"}
                        autoComplete={authMode === "login" ? "current-password" : "new-password"}
                      />
                    </div>

                    {showForgotNotice && authMode === "login" && (
                      <div className="forgot-notice-box">
                        For local development workspaces, log in with registered credentials or use &ldquo;Explore as Guest&rdquo;.
                      </div>
                    )}

                    {authMode === "register" && (
                      <div className="welcome-field">
                        <label htmlFor="reg-ws">Workspace Name (Optional)</label>
                        <input
                          id="reg-ws"
                          type="text"
                          value={form.workspace_name}
                          onChange={setField("workspace_name")}
                          placeholder="e.g. Acme Analytics"
                        />
                      </div>
                    )}

                    <button
                      type="submit"
                      className="btn-welcome-submit"
                      disabled={busy}
                    >
                      {busy ? "Processing…" : authMode === "login" ? "Sign In" : "Create Account"}
                    </button>
                  </form>
                </div>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Understated Minimal Footer */}
      <footer className="welcome-footer">
        <p>&copy; 2026 ANSHora Decision Intelligence. Verifiable analytics with proof.</p>
      </footer>
    </div>
  );
}

export default LandingScreen;
