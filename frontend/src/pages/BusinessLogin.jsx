// Phase I — Business Redemption Portal: login page.
// Re-uses the platform's existing /api/auth/login + cookie session.  A
// successful auth then bounces to /business if the user has a business
// profile; otherwise /business/register.
import React, { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Loader2, Store, Mail, KeyRound, ChevronRight } from "lucide-react";
import { Card, Button } from "@/shell/primitives";
import { API, useAuth } from "@/AuthContext";

export default function BusinessLogin() {
  const { login, user, loading } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [pwd, setPwd]     = useState("");
  const [busy, setBusy]   = useState(false);

  useEffect(() => {
    if (loading || !user) return;
    (async () => {
      try {
        await axios.get(`${API}/business/me`);
        navigate("/business", { replace: true });
      } catch (e) {
        if (e?.response?.status === 403) {
          navigate("/business/register", { replace: true });
        }
      }
    })();
  }, [user, loading, navigate]);

  const submit = async (e) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    try {
      await login(email.trim(), pwd);
      try {
        await axios.get(`${API}/business/me`);
        navigate("/business", { replace: true });
      } catch (err) {
        if (err?.response?.status === 403) {
          toast.message("Let's set up your business first.");
          navigate("/business/register", { replace: true });
        } else { throw err; }
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Sign-in failed.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="business-login-page"
            className="min-h-screen flex items-center justify-center bg-bg-base px-4 py-12">
      <Toaster richColors theme="dark" position="bottom-right" />
      <Card className="w-full max-w-md p-8 space-y-6">
        <header className="space-y-2 text-center">
          <div className="inline-flex items-center justify-center w-14 h-14 rounded-token-md
                                  bg-accent-gold/15 text-accent-gold mx-auto">
            <Store size={26} />
          </div>
          <h1 className="font-display font-bold text-3xl tracking-display-tight">
            Business <span className="text-accent-gold">Portal</span>
          </h1>
          <p className="text-text-secondary text-sm">
            Redeem customer coupons, see your foot traffic, run BigFM ads.
          </p>
        </header>

        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary flex items-center gap-2 mb-1">
              <Mail size={11} /> Email
            </span>
            <input type="email" value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          required
                          data-testid="business-login-email"
                          className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                          px-3.5 py-2.5 text-sm focus:outline-none focus:border-accent-gold/60" />
          </label>
          <label className="block">
            <span className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary flex items-center gap-2 mb-1">
              <KeyRound size={11} /> Password
            </span>
            <input type="password" value={pwd}
                          onChange={(e) => setPwd(e.target.value)}
                          required
                          data-testid="business-login-password"
                          className="w-full rounded-token-md bg-white/[0.04] border border-white/10
                                          px-3.5 py-2.5 text-sm focus:outline-none focus:border-accent-gold/60" />
          </label>
          <Button type="submit" variant="gold" className="w-full"
                          disabled={busy} data-testid="business-login-submit">
            {busy
              ? <><Loader2 size={14} className="animate-spin" /> Signing in…</>
              : <>Sign in <ChevronRight size={14} /></>}
          </Button>
        </form>

        <div className="text-center text-xs text-text-secondary">
          New here?{" "}
          <Link to="/business/register" data-testid="business-login-register-link"
                  className="text-accent-electric hover:underline font-semibold">
            Register your business →
          </Link>
        </div>
      </Card>
    </div>
  );
}
