// Phase E — AD.7.1 Split-the-bill: public invite landing.
// Route: /split/:invite_token
//
// Anonymous users see merchant/total/description + THIS share's amount +
// sibling status list (display_name only, no PII) and a login CTA.
// Auth'd users see the same, plus a "Pay my share" button that claims
// (if not yet claimed by them) then pays via /api/scan-to-pay/splits/shares/{id}/pay.
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, AlertTriangle, CheckCircle2, ArrowLeft, Users, CreditCard,
  Sparkles, Clock, LogIn, Wallet,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";


export default function SplitInvite() {
  const { invite_token } = useParams();
  const nav = useNavigate();
  const { user } = useAuth();
  const variant = useDesignVariant();
  const light = variant === "radiolife";

  const [state, setState] = useState({
    loading: true, view: null, error: null,
    payBusy: false, receipt: null,
  });
  const s = state;
  const set = (patch) => setState((cur) => ({ ...cur, ...patch }));

  const loadView = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/scan-to-pay/splits/by-token/${invite_token}`,
        { withCredentials: true });
      set({ view: r.data, loading: false, error: null });
    } catch (err) {
      set({ error: err?.response?.data?.detail?.code || err.message,
                loading: false });
    }
  }, [invite_token]);

  useEffect(() => { loadView(); }, [loadView]);

  const payMyShare = async () => {
    if (!user) return;
    set({ payBusy: true });
    try {
      // 1) claim (idempotent for same user)
      await axios.post(
        `${API}/scan-to-pay/splits/by-token/${invite_token}/claim`,
        {}, { withCredentials: true });
      // 2) pay
      const share_id = s.view?.share?.share_id;
      const pay = await axios.post(
        `${API}/scan-to-pay/splits/shares/${share_id}/pay`,
        { payment_method_id: "pm_card_visa" },
        { withCredentials: true });
      set({ receipt: pay.data, payBusy: false });
      // refresh view state
      loadView();
    } catch (err) {
      set({ error: err?.response?.data?.detail?.code || err.message,
                payBusy: false });
    }
  };

  const bg = light ? "bg-slate-50 text-slate-900"
                                        : "bg-slate-950 text-white";
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  if (s.loading) {
    return (
      <div className={`${bg} min-h-screen p-8`}
                data-testid="split-invite-loading">
        <div className={`inline-flex items-center gap-2 ${muted}`}>
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading your share…
        </div>
      </div>
    );
  }

  if (s.error && !s.receipt) {
    return (
      <div className={`${bg} min-h-screen p-8`}
                data-testid="split-invite-error">
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40
                                    text-red-400 text-sm inline-flex items-center gap-2">
          <AlertTriangle size={16} /> {prettyErr(s.error)}
        </div>
        <button onClick={() => nav("/")}
                        className="mt-4 text-xs text-fuchsia-500 hover:underline">
          Return home →
        </button>
      </div>
    );
  }

  const merchant  = s.view?.merchant || {};
  const split      = s.view?.split || {};
  const share      = s.view?.share || {};
  const others    = s.view?.other_shares || [];
  const alreadyPaid = share.status === "paid";
  const cancelled = ["cancelled", "expired"].includes(split.status);

  return (
    <div className={`${bg} min-h-screen`}
              data-testid="split-invite-page"
              data-variant={variant}>
      <div className="max-w-md mx-auto px-4 py-6">
        <button onClick={() => nav("/")}
                        className={`inline-flex items-center gap-1 text-xs ${muted}
                                              hover:opacity-80 mb-4`}
                        data-testid="split-invite-back">
          <ArrowLeft size={12} /> Home
        </button>

        {/* Bill card */}
        <div className={`${card} rounded-2xl p-5`}
                    data-testid="split-invite-card">
          <div className="flex items-center gap-3">
            {merchant.logo_url ? (
              <img src={`${process.env.REACT_APP_BACKEND_URL}${merchant.logo_url}`}
                          alt="" className="w-12 h-12 rounded-lg object-cover
                                                            bg-slate-800/40" />
            ) : (
              <div className="w-12 h-12 rounded-lg grid place-items-center
                                          bg-gradient-to-br from-fuchsia-500 to-amber-500">
                <Sparkles size={18} className="text-white" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
                You&apos;ve been invited to split
              </div>
              <div className="text-lg font-black truncate"
                          data-testid="split-invite-merchant">
                {merchant.business_name || merchant.merchant_id || "the bill"}
              </div>
              {split.description && (
                <div className={`text-[11px] ${muted} mt-0.5 truncate`}>
                  {split.description}
                </div>
              )}
            </div>
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3">
            <div>
              <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
                Bill total
              </div>
              <div className="text-lg font-black tabular-nums"
                          data-testid="split-invite-total">
                {formatMoney(split.total_amount_cents, split.currency)}
              </div>
            </div>
            <div>
              <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
                Your share
              </div>
              <div className="text-2xl font-black tabular-nums text-fuchsia-500"
                          data-testid="split-invite-my-share">
                {formatMoney(share.share_amount_cents, split.currency)}
              </div>
              {share.display_name && (
                <div className={`text-[10px] ${muted} mt-0.5`}>
                  for {share.display_name}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Siblings */}
        {others.length > 0 && (
          <div className={`${card} rounded-2xl p-4 mt-3`}
                      data-testid="split-invite-siblings">
            <div className={`text-[10px] uppercase tracking-widest font-mono mb-2 ${muted}
                                          inline-flex items-center gap-1`}>
              <Users size={11} /> Other payers
            </div>
            <div className="space-y-1.5">
              {others.map((o) => (
                <div key={o.share_id}
                            data-testid={`split-invite-sibling-${o.share_id}`}
                            className="flex items-center justify-between text-xs">
                  <span className="truncate">{o.display_name || "Guest"}</span>
                  <span className={`inline-flex items-center gap-1 font-mono ${
                                              statusPillClass(o.status, light)}`}>
                    <StatusDot status={o.status} />
                    {formatMoney(o.share_amount_cents, split.currency)} · {statusLabel(o.status)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Receipt */}
        {s.receipt && (
          <div className={`${card} rounded-2xl p-5 mt-3 text-center`}
                      data-testid="split-invite-receipt">
            <div className="w-14 h-14 mx-auto rounded-full grid place-items-center
                                        bg-emerald-500/15 border-2 border-emerald-500 mb-3">
              <CheckCircle2 size={28} className="text-emerald-500" />
            </div>
            <div className="text-[10px] uppercase tracking-widest font-mono
                                        text-emerald-500">Your share paid</div>
            <div className="text-3xl font-black mt-1 tabular-nums">
              {formatMoney(share.share_amount_cents, split.currency)}
            </div>
            {s.receipt.completed && (
              <div className={`mt-2 text-[11px] ${muted}`}>
                All shares paid — the merchant is settled 🎉
              </div>
            )}
            <div className={`text-[10px] font-mono mt-2 ${muted}`}>
              Transaction {s.receipt.transaction_id}
            </div>
          </div>
        )}

        {/* Call to action */}
        {!s.receipt && !cancelled && !alreadyPaid && (
          <div className={`${card} rounded-2xl p-5 mt-3`}>
            {!user ? (
              <div className="text-center">
                <div className={`text-sm ${muted} mb-3`}>
                  Sign in to pay your share securely.
                </div>
                <Link to={`/auth?redirect=/split/${invite_token}`}
                            data-testid="split-invite-signin"
                            className="w-full inline-flex items-center justify-center gap-2
                                                  py-3 rounded-full text-sm font-black
                                                  bg-fuchsia-500 text-white hover:bg-fuchsia-400">
                  <LogIn size={14} /> Sign in to pay
                </Link>
              </div>
            ) : (
              <>
                <button onClick={payMyShare}
                                disabled={s.payBusy}
                                data-testid="split-invite-pay-button"
                                className="w-full py-3 rounded-full text-sm font-black
                                                        inline-flex items-center justify-center gap-2
                                                        bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                        disabled:opacity-40 disabled:cursor-not-allowed">
                  {s.payBusy
                    ? <Loader2 size={16} className="animate-spin" />
                    : <CreditCard size={16} />}
                  Pay my share ({formatMoney(share.share_amount_cents, split.currency)})
                </button>
                <div className={`text-[10px] font-mono text-center mt-2 ${muted}`}>
                  Test-mode Stripe — card 4242 4242 4242 4242
                </div>
              </>
            )}
          </div>
        )}

        {cancelled && (
          <div className="mt-3 rounded-xl px-4 py-3 bg-amber-500/10 border
                                        border-amber-500/40 text-amber-500 text-xs
                                        inline-flex items-center gap-2"
                      data-testid="split-invite-cancelled">
            <AlertTriangle size={12} /> This split is {split.status}.
          </div>
        )}
        {alreadyPaid && !s.receipt && (
          <div className="mt-3 rounded-xl px-4 py-3 bg-emerald-500/10 border
                                        border-emerald-500/40 text-emerald-500 text-xs
                                        inline-flex items-center gap-2"
                      data-testid="split-invite-already-paid">
            <CheckCircle2 size={12} /> You already paid this share.
          </div>
        )}

        <Link to="/my/splits"
                    data-testid="split-invite-my-splits-link"
                    className={`block text-center text-[11px] mt-4 hover:underline
                                            text-fuchsia-500 inline-flex items-center gap-1
                                            justify-center w-full`}>
          <Wallet size={11} /> Manage my splits →
        </Link>
      </div>
    </div>
  );
}


function StatusDot({ status }) {
  const cls = {
    invited: "bg-slate-400",
    claimed: "bg-fuchsia-500",
    paid:      "bg-emerald-500",
    expired:  "bg-amber-500",
    cancelled: "bg-red-500",
  }[status] || "bg-slate-400";
  return <span className={`inline-block w-2 h-2 rounded-full ${cls}`} />;
}
function statusPillClass(status, light) {
  if (status === "paid") return "text-emerald-500";
  if (status === "claimed") return "text-fuchsia-500";
  if (status === "cancelled") return "text-red-500";
  if (status === "expired") return "text-amber-500";
  return light ? "text-slate-500" : "text-slate-400";
}
function statusLabel(status) {
  return { invited: "waiting", claimed: "claimed",
                    paid: "paid", expired: "expired",
                    cancelled: "cancelled" }[status] || status;
}
function symbolFor(cur) {
  const c = (cur || "").toLowerCase();
  if (c === "usd") return "$";
  if (c === "aed") return "AED";
  if (c === "eur") return "€";
  if (c === "gbp") return "£";
  return c.toUpperCase();
}
function formatMoney(cents, cur) {
  return `${symbolFor(cur)} ${((cents || 0) / 100).toFixed(2)}`;
}
function prettyErr(code) {
  const map = {
    share_not_found:        "This split invitation was not found.",
    split_not_found:        "This split was not found.",
    split_expired:          "This split has expired.",
    split_cancelled:      "This split was cancelled.",
    share_paid:                "This share has already been paid.",
    share_taken:              "Someone else already claimed this share.",
    auth_required:          "Please sign in first.",
  };
  return map[code] || String(code);
}
