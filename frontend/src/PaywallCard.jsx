// Phase 36e Turn 1 — Paywall card shown when episode access returns 402.
import React, {useState} from "react";
import axios from "axios";
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export function PaywallCard({channelId, plan}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  if (!plan) return null;
  const dollars = (plan.price_cents / 100).toFixed(2);

  const startTrial = async () => {
    setBusy(true); setErr("");
    try {
      // Phase 36e Turn 2 — funnel: fire cta-click BEFORE the subscribe call.
      // Best-effort; never block the subscribe attempt.
      axios.post(`${API}/podcasts/channels/${channelId}/funnel/cta-clicked`,
                          {}, {withCredentials: true}).catch(() => {});
      const r = await axios.post(
        `${API}/podcasts/channels/${channelId}/subscribe`, {},
        {withCredentials: true});
      if (r.data?.checkout_url) {
        window.location.href = r.data.checkout_url;
      }
    } catch (e) {
      setErr(e?.response?.data?.detail || e?.message || "Failed");
      setBusy(false);
    }
  };

  return (
    <div data-testid="paywall-card"
              style={{background: "linear-gradient(135deg,#1e1b3a,#0f0d1f)",
                          border: "1px solid rgba(245,158,11,0.4)",
                          borderRadius: 14, padding: 22, maxWidth: 520,
                          color: "#fff"}}>
      <div style={{fontSize: 11, color: "#fbbf24", letterSpacing: 0.6,
                              textTransform: "uppercase", marginBottom: 8}}>
        Subscribers only
      </div>
      <h3 style={{fontSize: 22, margin: 0, fontWeight: 800}}>
        {plan.plan_name}
      </h3>
      <div style={{margin: "10px 0 18px", fontSize: 14, color: "#cbd5e1"}}>
        Get this episode + every bonus drop on this channel.
      </div>
      <div style={{display: "flex", alignItems: "baseline", gap: 8,
                              marginBottom: 14}}>
        <span style={{fontSize: 32, fontWeight: 900}}>{`$${dollars}`}</span>
        <span style={{fontSize: 13, color: "#94a3b8"}}>/month USD</span>
      </div>
      <ul style={{listStyle: "none", padding: 0, margin: "0 0 18px",
                            fontSize: 13, color: "#e2e8f0", lineHeight: 1.7}}>
        {plan.features?.ad_free &&
            <li>✓ Ad-free listening on this channel</li>}
        {plan.features?.early_access_hours > 0 &&
            <li>✓ {plan.features.early_access_hours}-hour early access</li>}
        {plan.features?.bonus_episodes &&
            <li>✓ Bonus episodes only subscribers can hear</li>}
      </ul>
      {err && <div data-testid="paywall-err"
                              style={{color: "#fca5a5", fontSize: 12,
                                          marginBottom: 8}}>{err}</div>}
      <button data-testid="paywall-start-trial" onClick={startTrial}
                      disabled={busy}
                      style={{padding: "10px 18px", borderRadius: 8,
                                  background: "#f59e0b", color: "#0a0a0c",
                                  border: "none", fontWeight: 800, fontSize: 14,
                                  cursor: busy ? "not-allowed" : "pointer"}}>
        {busy ? "Opening checkout…" : `Start ${plan.trial_days}-day free trial`}
      </button>
    </div>
  );
}
