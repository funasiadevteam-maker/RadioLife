// Phase AUTH.PWR (2026-07-31) — password-reset request page.
//
// Route: /forgot-password
// Backend: POST /api/auth/forgot-password  { email }
// Response: anti-enumeration — always returns the same success message
// whether the email exists or not.
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Loader2, Mail, ArrowLeft, CheckCircle2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function ForgotPassword() {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const nav = useNavigate();

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setMsg(""); setBusy(true);
    try {
      const r = await axios.post(
        `${API}/auth/forgot-password`,
        { email: email.trim().toLowerCase() });
      setMsg(r.data?.message
        || "If that email exists, we've sent a reset link.");
    } catch (err) {
      // Keep the same anti-enumeration message even on transport error
      // — we shouldn't leak which emails exist in the DB.
      setMsg("If that email exists, we've sent a reset link.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="forgot-password-page"
              className="min-h-screen bg-slate-950 text-white
                                      flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <button type="button" onClick={() => nav("/login")}
                        data-testid="forgot-back-to-login"
                        className="inline-flex items-center gap-2 text-sm
                                              text-slate-400 hover:text-white mb-6">
          <ArrowLeft size={14} /> Back to sign in
        </button>
        <div className="rounded-2xl border border-white/10 bg-slate-900/60
                                      p-8 shadow-2xl">
          <h1 className="text-2xl font-black tracking-tight mb-1">
            Forgot password?
          </h1>
          <p className="text-sm text-slate-400 mb-6">
            Enter the email you signed up with — we&apos;ll send you a link
            to set a new one.
          </p>
          {msg ? (
            <div data-testid="forgot-success-message"
                      className="flex items-start gap-3 p-4 rounded-lg
                                              bg-emerald-500/10 border
                                              border-emerald-500/30 text-emerald-100">
              <CheckCircle2 size={18} className="mt-0.5 flex-shrink-0" />
              <span className="text-sm leading-relaxed">{msg}</span>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-4">
              <div>
                <label className="text-xs uppercase tracking-widest
                                                    text-slate-500 font-mono">Email</label>
                <div className="mt-1.5 relative">
                  <Mail size={16}
                                className="absolute left-3 top-1/2 -translate-y-1/2
                                                        text-slate-500 pointer-events-none" />
                  <input type="email" required autoFocus
                                  value={email} onChange={(e) => setEmail(e.target.value)}
                                  placeholder="you@example.com"
                                  data-testid="forgot-email-input"
                                  className="w-full pl-9 pr-4 py-3 rounded-lg
                                                          bg-slate-800/60 border border-white/10
                                                          focus:border-fuchsia-400 focus:outline-none
                                                          text-sm placeholder:text-slate-600" />
                </div>
              </div>
              {error && (
                <div data-testid="forgot-error-message"
                          className="text-xs text-rose-400">{error}</div>
              )}
              <button type="submit" disabled={busy || !email}
                              data-testid="forgot-submit-btn"
                              className="w-full inline-flex items-center justify-center
                                                      gap-2 py-3 rounded-full bg-fuchsia-500
                                                      text-white font-bold text-sm
                                                      hover:bg-fuchsia-400 disabled:opacity-50
                                                      transition-colors">
                {busy && <Loader2 size={14} className="animate-spin" />}
                Send reset link
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
