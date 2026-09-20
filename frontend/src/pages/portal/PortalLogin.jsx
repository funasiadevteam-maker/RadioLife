// Phase PORTAL.0 — Unified portal login (design-independent route).
// Route: /portal/login  — for business owners, staff, cashiers, FUUSIC
// admins and approved advertisers. ONE shared login system; the ACTIVE
// design variant only controls appearance. New Look V2 gets the premium
// dark-cinematic screen; other variants get a compatible themed card.
// After auth we resolve access context and hand off to /portal (PortalRoleRouter).
import { useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Loader2, ShieldCheck, Store, Sparkles } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { usePortalAccess } from "@/hooks/usePortalAccess";
import SignInWithGoogleButton from "@/SignInWithGoogleButton";
import "@/design_v2/newlookv2.css";

export default function PortalLogin() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const navigate = useNavigate();
  const { login } = useAuth();
  const fetchAccess = usePortalAccess((s) => s.fetch);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password) return;
    setBusy(true);
    try {
      await login(email.trim(), password);
      await fetchAccess();
      navigate("/portal", { replace: true });
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(
        d === "invalid_credentials" || err?.response?.status === 401
          ? "Invalid email or password."
          : "Couldn't sign in. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  // Shared form body — same fields/testids across every variant.
  const form = (
    <form onSubmit={submit} className="space-y-3" data-testid="portal-login-form">
      <SignInWithGoogleButton size="large" redirectPath="/portal"
                                                      data-testid="portal-login-google" />
      <div className="flex items-center gap-3 my-1">
        <span className="flex-1 h-px" style={{ background: light ? "#e2e8f0" : "rgba(255,255,255,0.1)" }} />
        <span className="text-[11px] font-mono uppercase tracking-widest"
                    style={{ color: light ? "#94a3b8" : "#6b7392" }}>or with email</span>
        <span className="flex-1 h-px" style={{ background: light ? "#e2e8f0" : "rgba(255,255,255,0.1)" }} />
      </div>
      <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@business.com" autoComplete="email" required
                    data-testid="portal-login-email"
                    className={`w-full rounded-xl px-4 py-3 text-sm outline-none ${
                      light ? "bg-white border border-slate-200 text-slate-900"
                            : "bg-white/[0.04] border border-white/10 text-white placeholder:text-[#6b7392]"}`} />
      <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                    placeholder="Password" autoComplete="current-password" required
                    data-testid="portal-login-password"
                    className={`w-full rounded-xl px-4 py-3 text-sm outline-none ${
                      light ? "bg-white border border-slate-200 text-slate-900"
                            : "bg-white/[0.04] border border-white/10 text-white placeholder:text-[#6b7392]"}`} />
      <button type="submit" disabled={busy} data-testid="portal-login-submit"
                    className="w-full h-12 rounded-xl font-black text-sm text-white
                                  inline-flex items-center justify-center gap-2 disabled:opacity-60"
                    style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
        {busy ? <Loader2 size={16} className="animate-spin" /> : "Enter portal"}
      </button>
      <div className="text-center pt-1">
        <Link to="/forgot-password"
                    className="text-xs font-semibold"
                    style={{ color: light ? "#7c3aed" : "#8b96b8" }}>
          Forgot password?
        </Link>
      </div>
    </form>
  );

  const roleChips = (
    <div className="flex flex-wrap gap-2 justify-center pt-1">
      {["Owners", "Managers", "Cashiers", "Admins", "Advertisers"].map((r) => (
        <span key={r} data-testid={`portal-login-role-${r.toLowerCase()}`}
                    className="text-[10px] font-bold uppercase tracking-widest px-2.5 py-1 rounded-full"
                    style={{ background: light ? "#f1f5f9" : "rgba(255,255,255,0.05)",
                                    color: light ? "#64748b" : "#8b96b8" }}>{r}</span>
      ))}
    </div>
  );

  // ── New Look V2 — premium dark cinematic ──
  if (variant === "new_look_v2") {
    return (
      <div className="nlv2 min-h-screen flex items-center justify-center p-4"
                data-testid="portal-login" data-variant={variant}>
        <div className="w-full max-w-md nlv2-glass-strong rounded-3xl p-7 sm:p-9">
          <div className="flex flex-col items-center text-center mb-6">
            <span className="w-14 h-14 rounded-2xl grid place-items-center mb-3"
                        style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              <Store size={26} className="text-white" />
            </span>
            <div className="font-black text-2xl tracking-tight">
              <span className="nlv2-grad">FUUSIC</span> Portal
            </div>
            <div className="text-[11px] font-mono uppercase tracking-widest mt-1"
                        style={{ color: "#8b96b8" }}>
              Business · Staff · Admin
            </div>
            <div className="inline-flex items-center gap-1.5 mt-3 px-3 py-1 rounded-full"
                        style={{ background: "rgba(245,197,99,0.12)", border: "1px solid rgba(245,197,99,0.3)" }}>
              <Sparkles size={12} className="text-[#f5c563]" />
              <span className="text-[10px] font-bold text-[#f5c563] uppercase tracking-widest">
                Soft Launch · 6 Months Free
              </span>
            </div>
          </div>
          {form}
          <div className="mt-5">{roleChips}</div>
          <div className="text-center mt-5 text-[11px]" style={{ color: "#6b7392" }}>
            New here?{" "}
            <Link to="/merchant/apply" className="font-bold nlv2-grad"
                        data-testid="portal-login-apply-link">List your business →</Link>
          </div>
        </div>
      </div>
    );
  }

  // ── Other variants — compatible themed card (same functionality) ──
  return (
    <div className={`min-h-screen flex items-center justify-center p-4 ${
                        light ? "bg-purple-50" : "bg-slate-950"}`}
              data-testid="portal-login" data-variant={variant}>
      <div className={`w-full max-w-md rounded-3xl p-8 ${
                          light ? "bg-white border border-slate-100 shadow-sm"
                                : "bg-slate-900 border border-slate-800"}`}>
        <div className="flex flex-col items-center text-center mb-6">
          <ShieldCheck size={30} className={light ? "text-purple-600 mb-2" : "text-cyan-400 mb-2"} />
          <div className={`font-black text-2xl ${light ? "text-slate-900" : "text-white"}`}>
            FUUSIC Portal
          </div>
          <div className={`text-xs mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
            Business · Staff · Admin
          </div>
        </div>
        {form}
        <div className="mt-5">{roleChips}</div>
        <div className={`text-center mt-5 text-[11px] ${light ? "text-slate-500" : "text-slate-500"}`}>
          New here?{" "}
          <Link to="/merchant/apply"
                      className={light ? "text-purple-600 font-bold" : "text-cyan-400 font-bold"}
                      data-testid="portal-login-apply-link">List your business →</Link>
        </div>
      </div>
    </div>
  );
}
