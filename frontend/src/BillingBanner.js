// Phase 6.1 — sticky site-wide billing banner.
// Renders above the radio bar based on the AuthContext's `billing` state.
//
//   past_due                  → amber/red, NOT dismissible, CTA "Update payment method" → Stripe Portal
//   canceled_for_nonpayment   → red,       NOT dismissible, CTA "Reactivate" → /billing
//   cancel_at_period_end      → muted info, DISMISSIBLE (sessionStorage keyed by user_id), CTA "Resume"
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { AlertTriangle, XCircle, Clock, ExternalLink, X } from "lucide-react";
import { useAuth, API } from "@/AuthContext";

const TONES = {
  past_due: {
    bg: "linear-gradient(90deg, rgba(251,113,133,0.18), rgba(251,113,133,0.10))",
    border: "#fb7185",
    text: "#fecdd3",
    Icon: AlertTriangle,
  },
  canceled: {
    bg: "linear-gradient(90deg, rgba(220,38,38,0.22), rgba(220,38,38,0.12))",
    border: "#dc2626",
    text: "#fecaca",
    Icon: XCircle,
  },
  pending_cancel: {
    bg: "linear-gradient(90deg, rgba(123,211,247,0.10), rgba(123,211,247,0.06))",
    border: "#475569",
    text: "#cbd5e1",
    Icon: Clock,
  },
};


function fmtDate(iso) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined,
      { month: "short", day: "numeric" });
  } catch { return iso; }
}


export default function BillingBanner() {
  const navigate = useNavigate();
  const { user, billing, refreshBilling } = useAuth();
  const [busy, setBusy] = useState(false);
  const [dismissedSoftCancel, setDismissedSoftCancel] = useState(false);

  // Dismissible-for-session state — keyed by user_id so a different login
  // doesn't inherit a previous user's dismiss.
  useEffect(() => {
    if (!user) return;
    const k = `bigfm:dismiss:soft-cancel:${user.user_id}`;
    setDismissedSoftCancel(sessionStorage.getItem(k) === "1");
  }, [user]);

  if (!user || !billing) return null;

  const isPastDue = billing.billing_status === "past_due";
  const isCanceled = billing.billing_status === "canceled_for_nonpayment";
  const isPendingCancel = billing.cancel_at_period_end === true &&
                            !isPastDue && !isCanceled;

  // Nothing to show
  if (!isPastDue && !isCanceled && !isPendingCancel) return null;
  if (isPendingCancel && dismissedSoftCancel) return null;

  const onUpdateCard = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/billing/portal`);
      if (r.data?.url) {
        // Open in same window so when user returns, focus listener refreshes
        // billing status automatically and the banner clears.
        window.location.href = r.data.url;
      }
    } catch (_e) {
      // Fall back to /billing page if portal session creation fails
      navigate("/billing");
    } finally { setBusy(false); }
  };

  const onReactivate = () => navigate("/billing");

  const onResume = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/billing/resume`);
      await refreshBilling();
    } catch (_e) {
      navigate("/billing");
    } finally { setBusy(false); }
  };

  const dismissSoft = () => {
    if (!user) return;
    sessionStorage.setItem(`bigfm:dismiss:soft-cancel:${user.user_id}`, "1");
    setDismissedSoftCancel(true);
  };

  let kind, copy, ctaLabel, ctaAction;
  if (isPastDue) {
    kind = "past_due";
    copy = `Payment failed — your Premium subscription will be canceled on ${fmtDate(billing.grace_period_ends_at)}.`;
    ctaLabel = "Update payment method";
    ctaAction = onUpdateCard;
  } else if (isCanceled) {
    kind = "canceled";
    copy = "Your Premium subscription was canceled due to non-payment.";
    ctaLabel = "Reactivate";
    ctaAction = onReactivate;
  } else {
    kind = "pending_cancel";
    copy = `Premium ends on ${fmtDate(billing.next_invoice_at)}. Resume anytime.`;
    ctaLabel = "Resume";
    ctaAction = onResume;
  }
  const tone = TONES[kind];
  const Icon = tone.Icon;

  return (
    <div
      data-testid={`billing-banner-${kind}`}
      style={{
        position: "sticky", top: 0, zIndex: 9999,
        background: tone.bg, borderBottom: `1px solid ${tone.border}`,
        backdropFilter: "blur(8px)",
        color: tone.text,
        padding: "10px 16px",
        display: "flex", alignItems: "center", gap: 12,
        fontSize: 13, fontFamily: "Inter, system-ui, sans-serif",
      }}
    >
      <Icon size={16} color={tone.border} aria-hidden="true" />
      <span style={{ flex: 1, lineHeight: 1.4 }} data-testid={`billing-banner-copy-${kind}`}>
        {copy}
      </span>
      <button
        onClick={ctaAction} disabled={busy}
        data-testid={`billing-banner-cta-${kind}`}
        style={{
          background: tone.border,
          color: kind === "pending_cancel" ? "#fff" : "#1a0a0e",
          border: "none", borderRadius: 6,
          padding: "6px 14px", fontWeight: 700, fontSize: 12,
          cursor: busy ? "wait" : "pointer", whiteSpace: "nowrap",
          display: "inline-flex", alignItems: "center", gap: 6,
        }}
      >
        {ctaLabel === "Update payment method" && <ExternalLink size={12} />}
        {ctaLabel}
      </button>
      {kind === "pending_cancel" && (
        <button
          onClick={dismissSoft}
          data-testid="billing-banner-dismiss"
          aria-label="Dismiss"
          style={{
            background: "transparent", border: "none",
            color: tone.text, cursor: "pointer", padding: 4,
            display: "inline-flex", alignItems: "center",
          }}>
          <X size={14} />
        </button>
      )}
    </div>
  );
}
