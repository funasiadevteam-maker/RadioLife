// /billing/success?session_id=XXX — confirmation page after a Stripe checkout.
// Polls /api/billing/status until paid or expired, then redirects back to /.

import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { Crown, Loader2, Sparkles, AlertTriangle, ArrowRight } from "lucide-react";
import { Toaster, toast } from "sonner";
import { API, useAuth } from "@/AuthContext";
import "@/pricing.css";

const POLL_INTERVAL_MS = 2000;
const POLL_MAX_ATTEMPTS = 30; // 60s ceiling

export default function BillingSuccess() {
  const [params] = useSearchParams();
  const session_id = params.get("session_id");
  const { refresh } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState({ phase: "polling", data: null });
  const [redirectIn, setRedirectIn] = useState(null);
  const attemptsRef = useRef(0);

  useEffect(() => {
    if (!session_id) {
      setState({ phase: "error", data: { error: "Missing session_id" } });
      return;
    }
    let cancelled = false;
    const poll = async () => {
      attemptsRef.current += 1;
      try {
        const r = await axios.get(`${API}/billing/status/${session_id}`);
        if (cancelled) return;
        if (r.data.payment_status === "paid" && r.data.status === "complete") {
          setState({ phase: "paid", data: r.data });
          refresh(); // refresh user profile so VIP badge appears
          return;
        }
        if (r.data.status === "expired") {
          setState({ phase: "expired", data: r.data });
          return;
        }
        if (attemptsRef.current >= POLL_MAX_ATTEMPTS) {
          setState({ phase: "timeout", data: r.data });
          return;
        }
        setTimeout(poll, POLL_INTERVAL_MS);
      } catch (e) {
        if (cancelled) return;
        setState({
          phase: "error",
          data: { error: e?.response?.data?.detail || "Could not verify checkout" },
        });
      }
    };
    poll();
    return () => { cancelled = true; };
  }, [session_id, refresh]);

  // Once paid → countdown + redirect home
  useEffect(() => {
    if (state.phase !== "paid") return;
    setRedirectIn(6);
    const id = setInterval(() => {
      setRedirectIn((n) => {
        if (n === null) return null;
        if (n <= 1) { clearInterval(id); navigate("/", { replace: true }); return 0; }
        return n - 1;
      });
    }, 1000);
    return () => clearInterval(id);
  }, [state.phase, navigate]);

  return (
    <div className="success-shell" data-testid="billing-success-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      {state.phase === "polling" && (
        <div className="success-card success-polling" data-testid="success-polling">
          <Loader2 className="spin" size={42} />
          <h1>Verifying your purchase…</h1>
          <p className="dim">Talking to Stripe. This usually takes under 10 seconds.</p>
          <div className="poll-trail mono">SESSION · {session_id?.slice(0, 16)}…</div>
        </div>
      )}

      {state.phase === "paid" && (
        <div className="success-card success-paid" data-testid="success-paid">
          <div className="confetti">
            <Sparkles size={26} />
            <Crown size={36} />
            <Sparkles size={26} />
          </div>
          <div className="success-eyebrow mono">WELCOME TO</div>
          <h1>FUUSIC <span className="hero-accent">Premium</span></h1>
          <p className="success-sub">
            6 skips an hour, two VIP channels, and a gold badge — all yours.
          </p>
          <div className="success-receipt" data-testid="success-receipt">
            <div className="receipt-row">
              <span className="mono">PLAN</span>
              <span>{state.data?.plan_id || "premium_annual"}</span>
            </div>
            <div className="receipt-row">
              <span className="mono">PAID</span>
              <span>{state.data?.amount_total} {state.data?.currency}</span>
            </div>
            <div className="receipt-row">
              <span className="mono">STATUS</span>
              <span className="status-paid">PAID</span>
            </div>
          </div>
          <button
            type="button"
            className="plan-cta plan-cta-premium"
            onClick={() => navigate("/", { replace: true })}
            data-testid="success-back-to-radio"
          >
            <ArrowRight size={16} />
            BACK TO RADIO {redirectIn ? `· ${redirectIn}s` : ""}
          </button>
        </div>
      )}

      {state.phase === "expired" && (
        <div className="success-card success-expired" data-testid="success-expired">
          <AlertTriangle size={36} />
          <h1>Checkout expired</h1>
          <p>Your Stripe session timed out before payment was completed.</p>
          <Link className="plan-cta plan-cta-premium" to="/pricing">
            TRY AGAIN
          </Link>
        </div>
      )}

      {state.phase === "timeout" && (
        <div className="success-card success-expired" data-testid="success-timeout">
          <Loader2 size={36} />
          <h1>Still processing…</h1>
          <p>
            Your payment is taking longer than expected. Your premium will activate
            automatically as soon as Stripe confirms.
          </p>
          <Link className="plan-cta plan-cta-premium" to="/">
            BACK TO RADIO
          </Link>
        </div>
      )}

      {state.phase === "error" && (
        <div className="success-card success-expired" data-testid="success-error">
          <AlertTriangle size={36} />
          <h1>Couldn't verify your purchase</h1>
          <p>{state.data?.error || "Something went wrong."}</p>
          <Link className="plan-cta plan-cta-premium" to="/pricing">
            BACK TO PRICING
          </Link>
        </div>
      )}
    </div>
  );
}
