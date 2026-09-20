// Phase 36e Turn 1 — Mock Stripe Checkout (DEVELOPMENT ONLY).
//
// THIS IS NOT REAL STRIPE CHECKOUT.
// Lives behind STRIPE_MODE=mock. The page makes it loud-and-clear that
// no payment is being processed — two "MOCK" banners + dev-only copy.
import React, {useEffect, useState} from "react";
import axios from "axios";
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function MockStripeCheckout() {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get("session_id");
  const priceId    = params.get("price");
  const trial         = parseInt(params.get("trial") || "7", 10);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const [err, setErr] = useState("");

  const simulate = async (success) => {
    setBusy(true); setErr("");
    try {
      const r = await axios.post(
        `${API}/mock/stripe/checkout/${sessionId}/complete`,
        {success}, {withCredentials: true});
      setDone(success ? "success" : "canceled");
      if (success && r.data?.subscription_id) {
        setTimeout(() => {
          window.location.href = "/listener/subscriptions?welcome=1";
        }, 1500);
      }
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "failed");
    } finally { setBusy(false); }
  };

  if (!sessionId) return (
    <div style={{padding: 40, color: "#fff"}}>
      No <code>session_id</code> in URL.
    </div>
  );

  return (
    <div data-testid="mock-checkout-page"
              style={{maxWidth: 520, margin: "60px auto", padding: 24,
                          background: "#0a0a14", color: "#fff",
                          border: "1px solid rgba(245,158,11,0.4)",
                          borderRadius: 14}}>
      <div data-testid="mock-banner-top"
                style={{background: "rgba(245,158,11,0.15)",
                            color: "#fbbf24", padding: "8px 12px", borderRadius: 6,
                            fontSize: 12, fontWeight: 800, textAlign: "center",
                            marginBottom: 18, letterSpacing: 0.6,
                            textTransform: "uppercase"}}>
        ⚠️ MOCK Stripe checkout — development only, no payment processed
      </div>
      <h1 style={{fontSize: 22, margin: "0 0 14px", fontWeight: 800}}>
        Confirm your subscription
      </h1>
      <div style={{fontSize: 13, color: "#cbd5e1", marginBottom: 14,
                              lineHeight: 1.5}}>
        FUUSIC does not currently process real card payments. This page
        simulates the Stripe checkout flow so the rest of the subscription
        lifecycle (webhook → status → paywall unlock) can be exercised.
      </div>
      <div style={{background: "#13131a", padding: 14, borderRadius: 8,
                              marginBottom: 18, fontSize: 12,
                              fontFamily: "monospace", color: "#94a3b8"}}>
        session_id: {sessionId}<br/>
        price_id:      {priceId || "—"}<br/>
        trial_days: {trial}
      </div>
      {err && <div data-testid="mock-checkout-err"
                              style={{color: "#fca5a5", marginBottom: 8,
                                          fontSize: 12}}>{err}</div>}
      {done === "success" && (
        <div data-testid="mock-checkout-success"
                  style={{color: "#22c55e", marginBottom: 12, fontSize: 13,
                              fontWeight: 700}}>
          ✓ Mock payment simulated. Routing to subscriptions…
        </div>
      )}
      {done === "canceled" && (
        <div data-testid="mock-checkout-canceled"
                  style={{color: "#fbbf24", marginBottom: 12, fontSize: 13}}>
          Simulated payment failure — your subscription remains incomplete.
        </div>
      )}
      <div style={{display: "flex", gap: 10}}>
        <button data-testid="mock-pay-success"
                        onClick={() => simulate(true)} disabled={busy || done === "success"}
                        style={btn(busy || done === "success", "#22c55e")}>
          Simulate successful payment
        </button>
        <button data-testid="mock-pay-fail"
                        onClick={() => simulate(false)} disabled={busy || done === "canceled"}
                        style={btn(busy || done === "canceled", "#ef4444")}>
          Simulate failure
        </button>
      </div>
      <div data-testid="mock-banner-bottom"
                style={{marginTop: 22, fontSize: 11, color: "#fbbf24",
                            textAlign: "center", letterSpacing: 0.4}}>
        🛑 MOCK MODE — flip backend `STRIPE_MODE=live` + provide
        `STRIPE_SECRET_KEY` to enable real Stripe checkout.
      </div>
    </div>
  );
}

const btn = (busy, color) => ({padding: "10px 18px", borderRadius: 8,
  background: color, color: "#0a0a0c", border: "none",
  fontWeight: 800, fontSize: 13, opacity: busy ? 0.5 : 1,
  cursor: busy ? "not-allowed" : "pointer"});
