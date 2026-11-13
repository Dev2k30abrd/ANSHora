import { useState } from "react";

import { errorText, getGoogleAuthUrl, login, loginGuest, register, setToken } from "../services/api";

function AuthScreen({ status, onAuthed }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ name: "", email: "", password: "", workspace_name: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [guestBusy, setGuestBusy] = useState(false);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const res =
        mode === "login"
          ? await login({ email: form.email, password: form.password })
          : await register({
              email: form.email,
              password: form.password,
              name: form.name,
              workspace_name: form.workspace_name || undefined,
            });
      setToken(res.token);
      onAuthed(res.user);
    } catch (err) {
      setError(errorText(err, "Could not sign in. Is the backend running?"));
    } finally {
      setBusy(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setGoogleBusy(true);
    setError("");
    try {
      const data = await getGoogleAuthUrl(window.location.origin);
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

  const handleGuestSignIn = async () => {
    setGuestBusy(true);
    setError("");
    try {
      const res = await loginGuest();
      // Guest mode is strictly ephemeral: NEVER save token to localStorage
      onAuthed({ ...res.user, is_guest: true });
    } catch (err) {
      setError(errorText(err, "Could not initialize guest session."));
    } finally {
      setGuestBusy(false);
    }
  };

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <div className="wordmark auth-brand">
          <span className="wordmark-mark" aria-hidden="true" />
          <h1>Anshora</h1>
        </div>
        <p className="auth-tagline">The analyst that shows its proof — and what it costs you.</p>

        {/* Google Sign-In Button */}
        <div className="auth-oauth-section">
          <button
            type="button"
            className="auth-google-btn"
            onClick={handleGoogleSignIn}
            disabled={googleBusy || busy || guestBusy}
          >
            <svg className="google-icon" viewBox="0 0 24 24" width="20" height="20">
              <path
                fill="#4285F4"
                d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.665-5.17 3.665-9.17z"
              />
              <path
                fill="#34A853"
                d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.27 21.43 7.33 24 12 24z"
              />
              <path
                fill="#FBBC05"
                d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.17 0 10.03 0 12s.45 3.83 1.25 5.42l4.03-3.15z"
              />
              <path
                fill="#EA4335"
                d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.27 2.57 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"
              />
            </svg>
            <span>{googleBusy ? "Opening Google Sign-In…" : "Continue with Google"}</span>
          </button>

          <div className="auth-separator">
            <span>or continue with email</span>
          </div>
        </div>

        <form onSubmit={submit} className="auth-form">
          {mode === "register" && (
            <>
              <label>
                Your name
                <input value={form.name} onChange={set("name")} required autoComplete="name" />
              </label>
              <label>
                Company / workspace <small>(optional)</small>
                <input value={form.workspace_name} onChange={set("workspace_name")} />
              </label>
            </>
          )}
          <label>
            Email
            <input type="email" value={form.email} onChange={set("email")} required autoComplete="email" />
          </label>
          <label>
            Password
            <input
              type="password"
              value={form.password}
              onChange={set("password")}
              required
              minLength={8}
              autoComplete={mode === "login" ? "current-password" : "new-password"}
            />
          </label>
          {error && <div className="message-error">{error}</div>}
          <button className="auth-submit" disabled={busy || googleBusy || guestBusy}>
            {busy ? <span className="spinner" /> : mode === "login" ? "Sign in" : "Create workspace"}
          </button>
        </form>

        <div className="auth-footer-actions">
          {status?.registration_open !== false && (
            <button
              type="button"
              className="auth-switch"
              onClick={() => setMode(mode === "login" ? "register" : "login")}
            >
              {mode === "login" ? "New here? Create a workspace" : "Have an account? Sign in"}
            </button>
          )}

          <button
            type="button"
            className="auth-guest-btn"
            onClick={handleGuestSignIn}
            disabled={guestBusy || busy || googleBusy}
          >
            {guestBusy ? "Starting guest session…" : "Try Guest Mode (explore without saving)"}
          </button>
        </div>

        {status?.llm?.mode === "demo" && (
          <p className="auth-demo">Demo mode: no LLM key configured on the server — answers use the offline analyst.</p>
        )}
      </div>
    </div>
  );
}

export default AuthScreen;
