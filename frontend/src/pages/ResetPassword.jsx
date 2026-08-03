// Phase AUTH.PWR (2026-07-31) — password-reset confirmation page.
//
// Route: /reset-password?token=<token>
// Backend: POST /api/auth/reset-password { token, new_password }
import { useState, useMemo, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Loader2, Lock, ArrowLeft, AlertTriangle,
                  CheckCircle2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


function _passwordViolations(pw) {
  const issues = [];
  if ((pw || "").length < 8) issues.push("at least 8 characters");
  if (!/[a-zA-Z]/.test(pw || "")) issues.push("a letter");
  if (!/\d/.test(pw || "")) issues.push("a digit");
  return issues;
}


export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const [pw1, setPw1] = useState("");
  const [pw2, setPw2] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const nav = useNavigate();

  const issues = useMemo(() => _passwordViolations(pw1), [pw1]);
  const mismatch = pw1 && pw2 && pw1 !== pw2;
  const canSubmit = !!token && !issues.length && !mismatch && pw1 === pw2;

  // If the URL doesn't carry a token at all, show the error immediately.
  useEffect(() => {
    if (!token) setError("Missing token. Request a new reset link.");
  }, [token]);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      await axios.post(`${API}/auth/reset-password`,
                                          { token, new_password: pw1 });
      setDone(true);
      setTimeout(() => nav("/login", {
        state: { flash: "Password updated. Sign in with your new password." }
      }), 1500);
    } catch (err) {
      setError(err?.response?.data?.detail
                            || err?.response?.data?.message
                            || "Invalid or expired token.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="reset-password-page"
              className="min-h-screen bg-slate-950 text-white
                                      flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <button type="button" onClick={() => nav("/login")}
                        data-testid="reset-back-to-login"
                        className="inline-flex items-center gap-2 text-sm
                                              text-slate-400 hover:text-white mb-6">
          <ArrowLeft size={14} /> Back to sign in
        </button>
        <div className="rounded-2xl border border-white/10 bg-slate-900/60
                                      p-8 shadow-2xl">
          <h1 className="text-2xl font-black tracking-tight mb-1">
            Choose a new password
          </h1>
          <p className="text-sm text-slate-400 mb-6">
            8+ characters, at least one letter and one digit.
          </p>
          {done ? (
            <div data-testid="reset-success-message"
                      className="flex items-start gap-3 p-4 rounded-lg
                                              bg-emerald-500/10 border
                                              border-emerald-500/30 text-emerald-100">
              <CheckCircle2 size={18} className="mt-0.5 flex-shrink-0" />
              <div className="text-sm leading-relaxed">
                Password updated. Redirecting to sign in…
              </div>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="text-xs uppercase tracking-widest
                                                    text-slate-500 font-mono">
                  New password
                </label>
                <div className="mt-1.5 relative">
                  <Lock size={16}
                              className="absolute left-3 top-1/2 -translate-y-1/2
                                                        text-slate-500 pointer-events-none" />
                  <input type="password" required autoFocus
                                  value={pw1} onChange={(e) => setPw1(e.target.value)}
                                  data-testid="reset-new-password-input"
                                  className="w-full pl-9 pr-4 py-3 rounded-lg
                                                          bg-slate-800/60 border border-white/10
                                                          focus:border-fuchsia-400
                                                          focus:outline-none text-sm" />
                </div>
                {pw1 && issues.length > 0 && (
                  <ul data-testid="reset-password-issues"
                              className="mt-2 text-xs text-amber-400 space-y-0.5">
                    {issues.map((i) => (
                      <li key={i}>• Password must contain {i}.</li>
                    ))}
                  </ul>
                )}
              </div>
              <div>
                <label className="text-xs uppercase tracking-widest
                                                    text-slate-500 font-mono">
                  Confirm password
                </label>
                <div className="mt-1.5 relative">
                  <Lock size={16}
                              className="absolute left-3 top-1/2 -translate-y-1/2
                                                        text-slate-500 pointer-events-none" />
                  <input type="password" required
                                  value={pw2} onChange={(e) => setPw2(e.target.value)}
                                  data-testid="reset-confirm-password-input"
                                  className="w-full pl-9 pr-4 py-3 rounded-lg
                                                          bg-slate-800/60 border border-white/10
                                                          focus:border-fuchsia-400
                                                          focus:outline-none text-sm" />
                </div>
                {mismatch && (
                  <div data-testid="reset-mismatch-message"
                            className="mt-2 text-xs text-rose-400">
                    Passwords don&apos;t match.
                  </div>
                )}
              </div>
              {error && (
                <div data-testid="reset-error-message"
                          className="flex items-start gap-2 p-3 rounded-lg
                                                  bg-rose-500/10 border border-rose-500/30
                                                  text-rose-100 text-xs">
                  <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
                  <span>{error}</span>
                </div>
              )}
              <button type="submit" disabled={busy || !canSubmit}
                              data-testid="reset-submit-btn"
                              className="w-full inline-flex items-center justify-center
                                                      gap-2 py-3 rounded-full bg-fuchsia-500
                                                      text-white font-bold text-sm
                                                      hover:bg-fuchsia-400 disabled:opacity-50
                                                      transition-colors">
                {busy && <Loader2 size={14} className="animate-spin" />}
                Set new password
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
