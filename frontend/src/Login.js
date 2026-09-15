// Login screen — Google OAuth (Emergent) + email/password tabs.
//
// REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH

import { useEffect, useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import { Loader2, Mail, KeyRound, User as UserIcon, ChevronRight, Radio as RadioIcon, Sun, Moon } from "lucide-react";
import { Toaster, toast } from "sonner";
import { useAuth } from "./AuthContext";
import SignInWithGoogleButton from "./SignInWithGoogleButton";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useTheme } from "@/theme/useTheme";

export default function Login() {
  const { user, login, register, demoLogin, loading } = useAuth();
  // When the RadioLife overlay is active, the /login route is served by
  // OnboardingRadioLife.jsx (which mounts its own SignInWithGoogleButton).
  // Skip mounting our copy here to avoid duplicate `sign-in-with-google-button`
  // testids in the DOM.  `useDesignVariant()` returns the variant STRING.
  const design = useDesignVariant();
  const isRadioLife = design === "radiolife";
  const navigate = useNavigate();
  const location = useLocation();
  const { theme, setTheme } = useTheme();
  const [mode, setMode] = useState("login"); // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [themeChoice, setThemeChoice] = useState(theme || "dark");
  const pickTheme = (t) => { setThemeChoice(t); setTheme(t); };

  useEffect(() => {
    if (loading) return;
    if (user) {
      navigate(user.onboarding_complete ? "/" : "/onboarding", { replace: true });
    }
    if (location.state?.authError) {
      toast.error(location.state.authError);
    }
    if (location.state?.adminBlocked) {
      toast.error("Admin access required");
    }
    if (location.state?.flash) {
      toast.success(location.state.flash);
    }
  }, [user, loading, navigate, location.state]);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      if (mode === "login") {
        const u = await login(email.trim(), password);
        toast.success(`Welcome back, ${u.name}`);
        navigate(u.onboarding_complete ? "/" : "/onboarding", { replace: true });
      } else {
        const u = await register(email.trim(), password, name.trim() || email.split("@")[0]);
        toast.success(`Account created. Let's set you up, ${u.name}!`);
        navigate("/onboarding", { replace: true });
      }
      setTheme(themeChoice);
    } catch (e2) {
      // Friendly parsing for FastAPI/pydantic 422s + plain string detail
      const detail = e2?.response?.data?.detail;
      let message;
      if (Array.isArray(detail)) {
        const parts = detail.map((d) => {
          const field = (d.loc || []).filter((l) => l !== "body").join(".");
          let msg = d.msg || "invalid";
          if (msg.includes("value is not a valid email")) msg = "Enter a valid email address";
          if (msg.includes("at least 8 characters")) msg = "Password must be at least 8 characters";
          return field ? `${field}: ${msg}` : msg;
        });
        message = parts.join(" · ");
      } else if (typeof detail === "string") {
        message = detail;
      } else if (e2?.response?.status === 409) {
        message = "Email already registered — try signing in instead.";
      } else if (e2?.response?.status === 401) {
        message = "Invalid email or password.";
      } else {
        message = `Could not ${mode}. Please try again.`;
      }
      toast.error(message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-shell" data-testid="login-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      <div className="auth-bg" aria-hidden>
        <div className="bg-ring r1" />
        <div className="bg-ring r2" />
        <div className="bg-ring r3" />
      </div>

      <div className="auth-card" data-testid="login-card">
        <div className="auth-brand">
          <span className="brand-dot" />
          <span className="brand-name">RadioLife</span>
        </div>

        <h1 className="auth-h1" data-testid="login-title">
          {mode === "login" ? "Sign in to start" : "Create your account"}
        </h1>
        <p className="auth-sub">
          {mode === "login"
            ? "Aapka personalized Hinglish radio chalu karne ke liye ek tap door."
            : "Tell us your taste once, then non-stop music."}
        </p>

        {!isRadioLife && (
          <>
            <SignInWithGoogleButton
              fullWidth
              size="medium"
              redirectPath="/dashboard"
            />
            {/* Legacy testid for backward-compat with older automation */}
            <span
              data-testid="google-signin-btn"
              aria-hidden
              style={{ display: "none" }}
            />
          </>
        )}

        <button
          type="button"
          className="apple-btn"
          onClick={() => {
            window.location.href = `${process.env.REACT_APP_BACKEND_URL || ""}/api/auth/apple/login`;
          }}
          data-testid="apple-signin-btn"
          style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            gap: 10, width: "100%", padding: "11px 14px", marginTop: 8,
            background: "#000", color: "#fff",
            border: "1px solid #000", borderRadius: 8,
            fontWeight: 600, fontSize: 14, cursor: "pointer",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="#fff"
                aria-hidden="true">
            <path d="M16.365 1.43c0 1.14-.467 2.255-1.23 3.063-.815.86-2.156 1.523-3.323 1.432-.156-1.103.404-2.246 1.158-3.066.847-.92 2.27-1.624 3.395-1.43zM21 17.115c-.6 1.4-.879 2.026-1.65 3.263-1.08 1.728-2.603 3.887-4.49 3.9-1.679.013-2.11-1.094-4.39-1.083-2.28.01-2.755 1.105-4.434 1.093-1.886-.014-3.33-1.968-4.41-3.696C-1.36 16.755-1.69 11.13.46 7.83 1.95 5.52 4.32 4.04 6.54 4.04c2.252 0 3.668 1.226 5.53 1.226 1.805 0 2.905-1.228 5.51-1.228 2.052 0 4.227 1.116 5.77 3.04-5.07 2.776-4.246 10.013-2.35 10.037z" />
          </svg>
          <span>Sign in with Apple</span>
        </button>

        <div className="auth-or"><span>or with email</span></div>

        <div data-testid="theme-choice" style={{ margin: "2px 0 14px" }}>
          <div style={{ fontSize: 11, letterSpacing: 1, textTransform: "uppercase",
                        color: "#6b6b78", marginBottom: 8 }}>Appearance</div>
          <div style={{ display: "flex", gap: 8 }}>
            {[
              { k: "dark", label: "Dark", Icon: Moon },
              { k: "light", label: "Light", Icon: Sun },
            ].map(({ k, label, Icon }) => {
              const active = themeChoice === k;
              return (
                <button key={k} type="button"
                  data-testid={`theme-choice-${k}`}
                  onClick={() => pickTheme(k)}
                  style={{
                    flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
                    gap: 8, padding: "10px 12px", borderRadius: 8, cursor: "pointer",
                    fontWeight: 600, fontSize: 13,
                    background: active ? "linear-gradient(135deg,#A020F0,#EC4899)" : "transparent",
                    color: active ? "#fff" : "#9aa0a6",
                    border: active ? "1px solid transparent" : "1px solid #2a2a36",
                    transition: "all 150ms ease",
                  }}>
                  <Icon size={15} /> {label}
                </button>
              );
            })}
          </div>
        </div>

        <form onSubmit={submit} className="auth-form" data-testid="auth-form">
          {mode === "register" && (
            <label className="auth-field">
              <UserIcon size={16} />
              <input
                type="text"
                placeholder="Display name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required={mode === "register"}
                data-testid="auth-name-input"
              />
            </label>
          )}
          <label className="auth-field">
            <Mail size={16} />
            <input
              type="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              data-testid="auth-email-input"
            />
          </label>
          <label className="auth-field">
            <KeyRound size={16} />
            <input
              type="password"
              placeholder={mode === "register" ? "8+ chars, letters & digits" : "Password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={mode === "register" ? 8 : 1}
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              data-testid="auth-password-input"
            />
          </label>

          <button
            type="submit"
            className="auth-submit"
            disabled={busy}
            data-testid="auth-submit-btn"
          >
            {busy ? <Loader2 className="spin" size={18} /> : <RadioIcon size={16} />}
            <span>{mode === "login" ? "Sign in" : "Create account"}</span>
            {!busy && <ChevronRight size={16} />}
          </button>
          {mode === "login" && (
            <div style={{ marginTop: 10, textAlign: "center" }}>
              <Link
                to="/forgot-password"
                data-testid="forgot-password-link"
                style={{ color: "#9aa0a6", fontSize: 12,
                                    textDecoration: "none",
                                    letterSpacing: 0.2 }}
                onMouseEnter={(e) => { e.currentTarget.style.color = "#fff"; }}
                onMouseLeave={(e) => { e.currentTarget.style.color = "#9aa0a6"; }}>
                Forgot password?
              </Link>
            </div>
          )}
        </form>

        <div className="auth-demo-divider"
                style={{ display: "flex", alignItems: "center", gap: 10,
                            margin: "18px 0 10px", color: "#6b6b78",
                            fontSize: 11, letterSpacing: 1, textTransform: "uppercase" }}>
          <span style={{ flex: 1, height: 1, background: "#2a2a36" }} />
          just exploring?
          <span style={{ flex: 1, height: 1, background: "#2a2a36" }} />
        </div>

        <button
          type="button"
          className="demo-btn"
          disabled={busy}
          onClick={async () => {
            if (busy) return;
            setBusy(true);
            try {
              const u = await demoLogin();
              toast.success("Welcome to the RadioLife demo — sign up to save your progress.");
              navigate(u.onboarding_complete ? "/" : "/onboarding", { replace: true });
            } catch (e2) {
              const status = e2?.response?.status;
              if (status === 429) {
                toast.error("Demo login rate limit reached — try again in a minute.");
              } else {
                toast.error("Could not start the demo. Please try again.");
              }
            } finally {
              setBusy(false);
            }
          }}
          data-testid="demo-login-btn"
          style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            gap: 8, width: "100%", padding: "10px 14px",
            background: "transparent", color: "#7BD3F7",
            border: "1px solid #7BD3F7", borderRadius: 8,
            fontWeight: 600, fontSize: 13, cursor: "pointer",
          }}
        >
          {busy ? <Loader2 className="spin" size={14} /> : <RadioIcon size={14} />}
          <span>Try the demo</span>
        </button>
        <p style={{ marginTop: 6, fontSize: 11, color: "#6b6b78",
                          textAlign: "center" }}>
          Logged in as a demo viewer — sign up to save your progress.
        </p>

        <div className="auth-switch">
          {mode === "login" ? (
            <>
              <span>New to RadioLife?</span>{" "}
              <button type="button" className="linkish" onClick={() => setMode("register")}
                      data-testid="switch-to-register">Create an account</button>
            </>
          ) : (
            <>
              <span>Already with us?</span>{" "}
              <button type="button" className="linkish" onClick={() => setMode("login")}
                      data-testid="switch-to-login">Sign in</button>
            </>
          )}
        </div>

        <p className="auth-footer mono">
          RADIOLIFE · PHASE 1 · <Link to="/" className="back-link">BACK TO RADIO</Link>
        </p>
      </div>
    </div>
  );
}
