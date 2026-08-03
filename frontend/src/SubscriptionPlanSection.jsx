// Phase 36e Turn 1 — Creator Subscription Plan section
// (mounted inside CreatorChannelSettings.jsx).
import React, {useEffect, useState} from "react";
import axios from "axios";
const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export function SubscriptionPlanSection({channelId, creatorId}) {
  const [acct,    setAcct]    = useState(null);
  const [acctLoaded, setAcctLoaded] = useState(false);
  const [plan,    setPlan]    = useState(null);
  const [err,      setErr]    = useState("");
  const [busy,    setBusy]    = useState(false);
  // form
  const [name,             setName]             = useState("Premium");
  const [priceDollars, setPriceDollars] = useState("4.99");
  const [trialDays,    setTrialDays]    = useState(7);

  const loadAcct = async () => {
    try {
      const r = await axios.get(
        `${API}/creators/${creatorId}/stripe-account`,
        {withCredentials: true});
      setAcct(r.data);
    } catch (e) {
      if (e?.response?.status !== 404) setErr(_msg(e));
      setAcct(null);
    } finally { setAcctLoaded(true); }
  };
  const loadPlan = async () => {
    try {
      const r = await axios.get(
        `${API}/podcasts/channels/${channelId}/subscription-plan`,
        {withCredentials: true});
      setPlan(r.data);
    } catch (e) { setPlan(null); }
  };
  useEffect(() => { loadAcct(); loadPlan(); }, []);  // eslint-disable-line

  const connectStripe = async () => {
    setBusy(true); setErr("");
    try {
      await axios.post(
        `${API}/creators/${creatorId}/stripe-account`, {},
        {withCredentials: true});
      const link = await axios.post(
        `${API}/creators/${creatorId}/stripe-account/onboarding-link`, {},
        {withCredentials: true});
      window.location.href = link.data.url;
    } catch (e) { setErr(_msg(e)); setBusy(false); }
  };

  const createPlan = async () => {
    setBusy(true); setErr("");
    try {
      const r = await axios.post(
        `${API}/podcasts/channels/${channelId}/subscription-plan`,
        {name, price_cents: Math.round(parseFloat(priceDollars) * 100),
          trial_days: trialDays},
        {withCredentials: true});
      setPlan(r.data);
    } catch (e) { setErr(_msg(e)); }
    finally { setBusy(false); }
  };

  const togglePause = async () => {
    setBusy(true); setErr("");
    try {
      const r = await axios.patch(
        `${API}/podcasts/channels/${channelId}/subscription-plan`,
        {active: !plan.active}, {withCredentials: true});
      setPlan(r.data);
    } catch (e) { setErr(_msg(e)); }
    finally { setBusy(false); }
  };

  return (
    <section data-testid="subscription-section" style={card()}>
      <h2 style={sectionH()}>Subscription plan</h2>
      {err && <div data-testid="subscription-err"
                              style={{color: "#fca5a5", marginBottom: 8,
                                          fontSize: 12}}>{err}</div>}

      {!acctLoaded && <div style={{color: "#94a3b8"}}>Loading…</div>}

      {acctLoaded && !acct && (
        <div>
          <p style={hint()}>Connect Stripe to start monetizing this channel.</p>
          <button data-testid="stripe-connect-cta" onClick={connectStripe}
                          disabled={busy} style={btnPrimary(busy)}>
            {busy ? "Opening Stripe…" : "Connect Stripe to monetize"}
          </button>
        </div>
      )}

      {acctLoaded && acct && !acct.charges_enabled && (
        <div>
          <p style={hint()}>Complete Stripe onboarding to enable charges.</p>
          <button data-testid="stripe-complete-cta" onClick={connectStripe}
                          disabled={busy} style={btnPrimary(busy)}>
            Complete Stripe onboarding
          </button>
        </div>
      )}

      {acctLoaded && acct && acct.charges_enabled && !plan && (
        <div data-testid="plan-form" style={{display: "grid", gap: 8}}>
          <p style={hint()}>Create your channel's subscription plan.</p>
          <label style={lbl()}>Name
            <input data-testid="plan-name-input" value={name}
                        onChange={e => setName(e.target.value)} style={inp()}/>
          </label>
          <label style={lbl()}>Price (USD/month, min $3)
            <input data-testid="plan-price-input" type="number" min={3}
                        step={0.5} value={priceDollars}
                        onChange={e => setPriceDollars(e.target.value)} style={inp()}/>
          </label>
          <label style={lbl()}>Trial days (default 7)
            <input data-testid="plan-trial-input" type="number" min={1} max={30}
                        value={trialDays}
                        onChange={e => setTrialDays(parseInt(e.target.value)||7)}
                        style={inp()}/>
          </label>
          <button data-testid="plan-create-btn" onClick={createPlan}
                          disabled={busy} style={btnPrimary(busy)}>
            {busy ? "Creating…" : "Create plan"}
          </button>
        </div>
      )}

      {plan && (
        <div data-testid="active-plan-summary">
          <div style={{fontSize: 14, color: "#e2e8f0"}}>
            <b>{plan.name}</b> · ${(plan.price_cents/100).toFixed(2)}/mo ·
            &nbsp;{plan.trial_days}-day trial · {plan.active ? "Active" : "Paused"}
          </div>
          <div style={{marginTop: 10, display: "flex", gap: 8}}>
            <button data-testid="plan-toggle-active" onClick={togglePause}
                            disabled={busy} style={btnSec()}>
              {plan.active ? "Pause plan" : "Resume plan"}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function _msg(e) {
  return e?.response?.data?.detail || e?.message || String(e);
}
const card = () => ({marginTop: 24, padding: 18,
  background: "#13131a", borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.06)"});
const sectionH = () => ({fontSize: 16, fontWeight: 700, margin: "0 0 12px"});
const hint = () => ({fontSize: 12, color: "#9aa3af",
  lineHeight: 1.5, marginBottom: 10});
const lbl = () => ({display: "flex", flexDirection: "column",
  fontSize: 11, color: "#94a3b8", gap: 4});
const inp = () => ({padding: "6px 8px", borderRadius: 5,
  background: "#0a0a14", color: "#fff",
  border: "1px solid rgba(255,255,255,0.1)", fontSize: 13});
const btnPrimary = (busy) => ({padding: "8px 16px", borderRadius: 6,
  background: busy ? "#3f3f46" : "#f59e0b",
  color: busy ? "#a1a1aa" : "#0a0a0c", border: "none",
  fontWeight: 700, fontSize: 13, cursor: busy ? "not-allowed" : "pointer",
  width: "fit-content"});
const btnSec = () => ({padding: "6px 12px", borderRadius: 6,
  background: "rgba(255,255,255,0.04)", color: "#e7e7ea",
  border: "1px solid rgba(255,255,255,0.1)", cursor: "pointer", fontSize: 12});
