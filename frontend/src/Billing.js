// Phase 6 — /billing page: Current Plan + Plans + Manage + Family seats
import { useState, useEffect, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, ChevronLeft, Check, AlertTriangle, CreditCard, Users, Pause,
  Play, X, Mail, ExternalLink, Crown, Zap, Calendar, Sparkles, ArrowRight,
  Ticket, Gift,
} from "lucide-react";
import "./Wallet.css"; // reuse styling primitives

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const TIER_BADGE = {
  free: { color: "#888892", icon: "🆓" },
  premium: { color: "#fdb756", icon: "👑" },
  business: { color: "#a78bfa", icon: "🏢" },
};

export default function Billing() {
  const navigate = useNavigate();
  const [me, setMe] = useState(null);
  const [status, setStatus] = useState(null);
  const [plans, setPlans] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [s, p, u] = await Promise.all([
        axios.get(`${API}/billing/status`),
        axios.get(`${API}/billing/plans`),
        axios.get(`${API}/auth/me`),
      ]);
      setStatus(s.data); setPlans(p.data); setMe(u.data);
    } catch (e) {
      if (e?.response?.status === 401) navigate("/login");
      else toast.error("Failed to load billing");
    } finally { setLoading(false); }
  }, [navigate]);

  useEffect(() => { reload(); }, [reload]);

  const changePlan = async (slug) => {
    if (!window.confirm(`Switch to ${slug}? Upgrades charge a prorated amount immediately.`)) return;
    setBusy(slug);
    try {
      const r = await axios.post(`${API}/billing/change_plan`,
        { target_plan_slug: slug }, { headers: { "Idempotency-Key": `change-${Date.now()}` } });
      if (r.data.action === "upgrade") {
        toast.success(`Upgraded! Charged ${r.data.currency} ${r.data.net_charge?.toFixed(2)} (proration credit: ${r.data.proration_credit?.toFixed(2)})`);
      } else if (r.data.action === "downgrade_queued") {
        toast.success(`Downgrade scheduled for ${new Date(r.data.effective_at).toLocaleDateString()}`);
      } else {
        toast.success("Plan updated");
      }
      reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Switch failed");
    } finally { setBusy(null); }
  };

  const doAction = async (label, url) => {
    setBusy(label);
    try {
      const r = await axios.post(`${API}${url}`);
      toast.success(r.data.url ? "Redirecting to Stripe..." : `${label} done`);
      if (r.data.url) window.location.href = r.data.url;
      else reload();
    } catch (e) {
      toast.error(e?.response?.data?.detail || `${label} failed`);
    } finally { setBusy(null); }
  };

  if (loading) return <div className="wallet-wrap"><Loader2 className="spin" size={28} /></div>;

  const isPastDue = status?.billing_status === "past_due";
  const cancelScheduled = status?.cancel_at_period_end;
  const isPaused = status?.paused;
  const isFamilyRoot = status?.family?.is_family_root;

  return (
    <div className="wallet-wrap" data-testid="billing">
      <header className="wallet-header">
        <div>
          <Link to="/" style={{ color: "#888", fontSize: 12, textDecoration: "none" }} data-testid="back-to-radio">
            <ChevronLeft size={11} /> back to radio
          </Link>
          <h1>Billing &amp; Plans</h1>
          <p className="sub">Manage your subscription, family seats, and payment methods.</p>
        </div>
      </header>

      {isPastDue && (
        <div className="bc-balance-card" style={{ background: "linear-gradient(135deg, #2a0a14, #1a0a14)", border: "1px solid #fb7185", marginBottom: 24 }}
          data-testid="past-due-banner">
          <AlertTriangle size={32} color="#fb7185" />
          <div style={{ flex: 1 }}>
            <div style={{ color: "#fb7185", fontWeight: 700, fontSize: 14 }}>
              Payment failed — Premium ends {new Date(status.grace_period_ends_at).toLocaleDateString()}
            </div>
            <div style={{ color: "#aaa", fontSize: 12, marginTop: 4 }}>
              Update your card before {new Date(status.grace_period_ends_at).toLocaleDateString()} to keep your perks.
            </div>
          </div>
          <button className="reward-btn" onClick={() => doAction("portal", "/billing/portal")}
            style={{ width: "auto", padding: "10px 18px", background: "#fb7185" }}
            data-testid="past-due-update-card-btn">
            <CreditCard size={14} /> Update payment method
          </button>
        </div>
      )}

      {/* CURRENT PLAN */}
      <section className="bc-balance-card" data-testid="current-plan-card">
        <div style={{ fontSize: 56 }}>{TIER_BADGE[status.premium_tier || "free"]?.icon || "🆓"}</div>
        <div style={{ flex: 1 }}>
          <div className="bc-meta-label">CURRENT PLAN</div>
          <div className="bc-amount" style={{ fontSize: 36 }} data-testid="current-plan-name">
            {status.current_plan_display || "Free"}
          </div>
          <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap", alignItems: "center" }}>
            <span className="bc-tier-badge" style={{ color: TIER_BADGE[status.premium_tier || "free"]?.color }}>
              {(status.premium_tier || "free").toUpperCase()}
            </span>
            <span style={{ fontSize: 12, color: "#aaa" }}>
              Status: <b style={{ color: status.billing_status === "active" ? "#4ade80" : "#fdb756" }}>{status.billing_status}</b>
            </span>
            {status.next_invoice_at && (
              <span style={{ fontSize: 12, color: "#aaa" }}>
                <Calendar size={11} /> Renews {new Date(status.next_invoice_at).toLocaleDateString()}
              </span>
            )}
            {cancelScheduled && (
              <span style={{ fontSize: 12, color: "#fdb756" }}>
                Cancels at period end
              </span>
            )}
            {status.premium_source === "family_seat" && (
              <span style={{ fontSize: 11, color: "#a78bfa" }}>
                <Users size={11} /> Family seat
              </span>
            )}
          </div>
          {status.pending_plan_change && (
            <div style={{ marginTop: 10, color: "#fdb756", fontSize: 12 }}>
              ⏳ Downgrade to <b>{status.pending_plan_change.target_plan_slug}</b> scheduled for{" "}
              {new Date(status.pending_plan_change.scheduled_at).toLocaleDateString()}
            </div>
          )}
        </div>
      </section>

      {/* PLAN CARDS */}
      <h3 style={{ fontSize: 14, color: "#888", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 12 }}>
        Plans
      </h3>
      <section className="reward-grid" data-testid="plans-grid">
        {plans.plans.map((p) => {
          const isCurrent = p.slug === status.current_plan_slug;
          return (
            <div key={p.slug} className="reward-card"
              style={{ border: isCurrent ? "1px solid #fdb756" : undefined,
                          position: "relative" }}
              data-testid={`plan-${p.slug}`}>
              {p.savings_vs_monthly_pct && (
                <div style={{ position: "absolute", top: 10, right: 10,
                                background: "#4ade80", color: "#0a1a0a",
                                fontSize: 10, fontWeight: 700, padding: "3px 8px",
                                borderRadius: 999 }} data-testid={`plan-${p.slug}-savings`}>
                  SAVE {p.savings_vs_monthly_pct}%
                </div>
              )}
              <div style={{ fontSize: 22, marginBottom: 6 }}>
                {TIER_BADGE[p.tier]?.icon}
              </div>
              <div className="reward-name">{p.display_name}</div>
              <div className="reward-cost" style={{ marginTop: 8, marginBottom: 10 }}>
                {p.amount_display}
              </div>
              <div className="reward-desc">{p.description}</div>
              <ul style={{ color: "#aaa", fontSize: 11, padding: "0 0 0 16px", margin: "8px 0", lineHeight: 1.7 }}>
                {p.features.ad_free && <li>Ad-free listening</li>}
                <li>{p.features.max_skips_per_hour > 0 ? `${p.features.max_skips_per_hour} skips / hour` : "1 skip / hour"}</li>
                {p.features.premium_channels > 0 && <li>{p.features.premium_channels} VIP channels</li>}
                {p.family_seats > 1 && <li><b>{p.family_seats} family seats</b></li>}
                {p.features.bigcoin_2x_weekends && <li>2× BigPoints weekends</li>}
              </ul>
              <button className="reward-btn"
                onClick={() => isCurrent ? null : changePlan(p.slug)}
                disabled={isCurrent || !p.purchasable || busy === p.slug}
                data-testid={`switch-${p.slug}`}>
                {busy === p.slug ? <Loader2 className="spin" size={14} />
                  : isCurrent ? <><Check size={14} /> Current plan</>
                  : !p.purchasable ? "Free"
                  : (status.current_plan_slug !== "free" && p.tier_rank > (plans.plans.find(x => x.slug === status.current_plan_slug)?.tier_rank ?? 0))
                    ? <>Upgrade <ArrowRight size={12} /></>
                  : <>Switch</>}
              </button>
            </div>
          );
        })}
      </section>

      {/* MANAGE */}
      <h3 style={{ fontSize: 14, color: "#888", letterSpacing: "0.05em", textTransform: "uppercase", margin: "24px 0 12px" }}>
        Manage
      </h3>
      <section style={{ display: "flex", gap: 10, flexWrap: "wrap" }} data-testid="manage-actions">
        <button className="reward-btn" style={{ width: "auto", padding: "10px 18px" }}
          onClick={() => doAction("portal", "/billing/portal")}
          disabled={busy === "portal"} data-testid="open-portal-btn">
          <ExternalLink size={14} /> Stripe Customer Portal
        </button>
        {status.current_plan_slug !== "free" && !cancelScheduled && !isPaused && (
          <button className="reward-btn" style={{ width: "auto", padding: "10px 18px", background: "#2a2a36" }}
            onClick={() => doAction("cancel", "/billing/cancel")}
            disabled={busy === "cancel"} data-testid="cancel-btn">
            <X size={14} /> Cancel at period end
          </button>
        )}
        {cancelScheduled && (
          <button className="reward-btn" style={{ width: "auto", padding: "10px 18px", background: "#4ade80", color: "#0a1a0a" }}
            onClick={() => doAction("resume", "/billing/resume")}
            disabled={busy === "resume"} data-testid="resume-btn">
            <Check size={14} /> Undo cancellation
          </button>
        )}
        {status.current_plan_slug !== "free" && !isPaused && (
          <button className="reward-btn" style={{ width: "auto", padding: "10px 18px", background: "#2a2a36" }}
            onClick={() => doAction("pause", "/billing/pause")}
            disabled={busy === "pause"} data-testid="pause-btn">
            <Pause size={14} /> Pause subscription
          </button>
        )}
        {isPaused && (
          <button className="reward-btn" style={{ width: "auto", padding: "10px 18px" }}
            onClick={() => doAction("unpause", "/billing/unpause")}
            disabled={busy === "unpause"} data-testid="unpause-btn">
            <Play size={14} /> Resume now
          </button>
        )}
      </section>

      {/* Phase 42-D2 — Voucher redemption */}
      <VoucherRedeemSection onRedeemed={reload} />

      {/* FAMILY */}
      {isFamilyRoot && (
        <section style={{ marginTop: 32 }} data-testid="family-section">
          <h3 style={{ fontSize: 14, color: "#888", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 12 }}>
            <Users size={11} style={{ verticalAlign: "-1px" }} /> Family seats
            ({status.family.seats_used}/{status.family.seats_total} used)
          </h3>
          <FamilySection family={status.family} onChange={reload} />
        </section>
      )}
    </div>
  );
}

function FamilySection({ family, onChange }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const invite = async () => {
    if (!email) return toast.error("Email required");
    setBusy(true);
    try {
      const r = await axios.post(`${API}/billing/family/invite`, { email });
      toast.success(`Invite sent to ${email}. Share token: ${r.data.token.slice(0, 24)}...`);
      setEmail(""); onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Invite failed");
    } finally { setBusy(false); }
  };
  const remove = async (uid) => {
    if (!window.confirm(`Remove this member? They'll lose Premium immediately.`)) return;
    try {
      await axios.post(`${API}/billing/family/remove`, { user_id: uid });
      toast.success("Member removed"); onChange();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Remove failed");
    }
  };
  return (
    <div className="bc-balance-card" style={{ display: "block" }}>
      {family.seats_remaining > 0 && (
        <div style={{ marginBottom: 18, display: "flex", gap: 8 }}>
          <input
            type="email" placeholder="family-member@email.com"
            value={email} onChange={(e) => setEmail(e.target.value)}
            style={{ flex: 1, background: "#0f0f15", border: "1px solid #25252f",
                      borderRadius: 8, padding: 10, color: "#fff" }}
            data-testid="family-invite-email" />
          <button className="reward-btn" style={{ width: "auto", padding: "10px 18px" }}
            onClick={invite} disabled={busy || !email} data-testid="family-invite-btn">
            <Mail size={14} /> Invite
          </button>
        </div>
      )}
      <div className="bc-meta-label">MEMBERS</div>
      {family.members.length === 0 && family.pending_invites.length === 0 && (
        <p style={{ color: "#888", fontSize: 12, marginTop: 8 }}>No seats used yet.</p>
      )}
      {family.members.map((m) => (
        <div key={m.user_id} className="txn-row" data-testid={`family-member-${m.user_id}`}>
          <div>
            <div className="txn-src">{m.name || m.email}</div>
            <div className="txn-sub">{m.email}</div>
          </div>
          <button className="reward-btn" style={{ width: "auto", padding: "6px 14px", background: "#2a2a36" }}
            onClick={() => remove(m.user_id)} data-testid={`family-remove-${m.user_id}`}>
            Remove
          </button>
        </div>
      ))}
      {family.pending_invites.length > 0 && (
        <>
          <div className="bc-meta-label" style={{ marginTop: 18 }}>PENDING INVITES</div>
          {family.pending_invites.map((p) => (
            <div key={p.token} className="txn-row" style={{ opacity: 0.7 }}>
              <div>
                <div className="txn-src">{p.email}</div>
                <div className="txn-sub">Expires {new Date(p.expires_at).toLocaleDateString()}</div>
              </div>
              <div style={{ fontSize: 10, color: "#888", fontFamily: "monospace" }}>
                {p.token.slice(0, 24)}…
              </div>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// Phase 42-D2 — Voucher redemption inline card on /billing.
// Hits POST /api/subscriptions/redeem-voucher.  The endpoint stamps
// the same subscription_status/premium_until fields a paid checkout
// would, so a follow-up reload() refreshes the entire /billing page.
function VoucherRedeemSection({ onRedeemed }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [last, setLast] = useState(null);

  const submit = async () => {
    if (!code.trim()) { toast.error("Enter a voucher code"); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/subscriptions/redeem-voucher`,
                                                          { code: code.trim().toUpperCase() });
      setLast(r.data);
      toast.success(`Redeemed — ${r.data.plan} until ${new Date(r.data.expires_at).toLocaleDateString()}`);
      setCode("");
      onRedeemed?.();
    } catch (e) {
      const codeStr = e?.response?.data?.detail?.code;
      const map = {
        voucher_not_found:                "Code not recognised.",
        voucher_revoked:                  "This code has been revoked.",
        voucher_expired:                  "This code has expired.",
        voucher_exhausted:              "This code is fully redeemed.",
        voucher_already_redeemed: "You've already redeemed this code.",
      };
      toast.error(map[codeStr] || "Couldn't redeem code. Please try again.");
    } finally { setBusy(false); }
  };

  return (
    <section data-testid="voucher-redeem-section"
                    style={{ marginTop: 32 }}>
      <h3 style={{ fontSize: 14, color: "#888", letterSpacing: "0.05em",
                              textTransform: "uppercase", marginBottom: 12 }}>
        <Ticket size={11} style={{ verticalAlign: "-1px" }} /> Have a code?
      </h3>
      <div className="bc-balance-card" style={{ display: "block" }}>
        <div style={{ color: "#aaa", fontSize: 12, marginBottom: 12 }}>
          Enter a RadioLife voucher code to unlock Premium or extend an
          active trial. Codes are case-insensitive.
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input type="text"
                      value={code}
                      onChange={(e) => setCode(e.target.value.toUpperCase())}
                      onKeyDown={(e) => e.key === "Enter" && submit()}
                      placeholder="BIGFM-XXXXXXXX"
                      data-testid="voucher-redeem-input"
                      style={{ flex: 1, minWidth: 220, background: "#0f0f15",
                                  border: "1px solid #25252f", borderRadius: 8,
                                  padding: 10, color: "#fff",
                                  fontFamily: "monospace",
                                  textTransform: "uppercase" }} />
          <button className="reward-btn"
                          style={{ width: "auto", padding: "10px 18px" }}
                          onClick={submit} disabled={busy || !code.trim()}
                          data-testid="voucher-redeem-submit">
            {busy ? <Loader2 className="spin" size={14} /> : <Gift size={14} />}
            Redeem
          </button>
        </div>
        {last && (
          <div data-testid="voucher-redeem-result"
                    style={{ marginTop: 12, padding: 10,
                                background: "rgba(74,222,128,0.08)",
                                border: "1px solid rgba(74,222,128,0.3)",
                                borderRadius: 6, color: "#4ade80",
                                fontSize: 12, fontFamily: "monospace" }}>
            ✓ {last.plan} active until {new Date(last.expires_at).toLocaleString()}
          </div>
        )}
      </div>
    </section>
  );
}
