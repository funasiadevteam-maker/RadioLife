// Phase AD.7 — Scan-to-Pay checkout at /scan-to-pay/:token.
//
// The customer sees the merchant name + amount, moves a points slider
// (0 → min(user_balance, max_allowed_by_cap)), optionally adds a tip,
// and confirms.  For simplicity in this POC we use `pm_card_visa`
// (Stripe test payment_method) — a full Stripe Elements integration
// happens in a follow-up.  All API responses drive the UI directly.
import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import {
  Loader2, AlertTriangle, CheckCircle2, ArrowLeft, Coins, CreditCard,
  Sparkles, Clock,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import SplitModal from "./SplitModal";


export default function ScanCheckout() {
  const { token } = useParams();
  const nav = useNavigate();
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user } = useAuth();
  const [splitOpen, setSplitOpen] = useState(false);
  const [state, setState] = useState({
    loading: true, resolved: null, error: null,
    pointsToUse: 0, tipCents: 0,
    quote: null, quoteBusy: false, quoteError: null,
    payBusy: false, receipt: null,
  });

  const s = state;
  const set = (patch) => setState((cur) => ({ ...cur, ...patch }));

  // Resolve QR on mount.
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/scan-to-pay/qr/${token}`,
          { withCredentials: true });
        set({ resolved: r.data, loading: false, error: null });
        // Prime the quote.
        computeQuote(0, 0);
      } catch (err) {
        set({ error: err?.response?.data?.detail?.code || err.message,
                  loading: false });
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const computeQuote = useCallback(async (pts, tip) => {
    set({ quoteBusy: true, quoteError: null });
    try {
      const r = await axios.post(`${API}/scan-to-pay/quote`,
        { qr_token: token, points_to_use: Number(pts) || 0,
          tip_cents: Number(tip) || 0 },
        { withCredentials: true });
      set({ quote: r.data, quoteBusy: false });
    } catch (err) {
      set({ quoteError: err?.response?.data?.detail?.code || err.message,
                quoteBusy: false });
    }
  }, [token]);

  // Recompute quote when points/tip change (debounced).
  useEffect(() => {
    if (!s.resolved) return undefined;
    const t = setTimeout(() => computeQuote(s.pointsToUse, s.tipCents), 220);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.pointsToUse, s.tipCents, s.resolved, computeQuote]);

  const pay = async () => {
    if (!s.quote) return;
    set({ payBusy: true });
    try {
      const auth = await axios.post(`${API}/scan-to-pay/authorize`,
        { qr_token: token,
          points_to_use: s.pointsToUse,
          tip_cents: s.tipCents,
          // POC-only: hard-coded Stripe test card.  A real integration
          // uses Stripe Elements to collect a payment_method here.
          payment_method_id: "pm_card_visa" },
        { withCredentials: true });
      const cap = await axios.post(`${API}/scan-to-pay/capture`,
        { transaction_id: auth.data.transaction_id },
        { withCredentials: true });
      set({ receipt: { ...auth.data, ...cap.data,
                                      merchant: s.resolved.merchant },
                payBusy: false });
    } catch (err) {
      set({ error: err?.response?.data?.detail?.code || err.message,
                payBusy: false });
    }
  };

  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";
  const card = light ? "bg-white border border-slate-200"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  if (!user) {
    return (
      <div className={`${bg} min-h-screen p-8 text-sm`}
                data-testid="scan-checkout-anon">
        Sign in to complete a scan-to-pay purchase.
      </div>
    );
  }

  if (s.loading) {
    return (
      <div className={`${bg} min-h-screen p-8`}
                data-testid="scan-checkout-loading">
        <div className={`inline-flex items-center gap-2 ${muted}`}>
          <Loader2 className="w-4 h-4 animate-spin" /> Loading merchant…
        </div>
      </div>
    );
  }

  if (s.error && !s.receipt) {
    return (
      <div className={`${bg} min-h-screen p-8`}
                data-testid="scan-checkout-error">
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2">
          <AlertTriangle size={16} /> {String(s.error)}
        </div>
        <button onClick={() => nav("/scan")}
                        className="mt-4 text-xs text-accent-electric hover:underline">
          Scan a different code →
        </button>
      </div>
    );
  }

  if (s.receipt) {
    const r = s.receipt;
    return (
      <div className={`${bg} min-h-screen`} data-testid="scan-checkout-success">
        <div className="max-w-md mx-auto px-4 py-8">
          <div className="text-center">
            <div className="w-16 h-16 mx-auto rounded-full grid place-items-center
                                        bg-emerald-500/15 border-2 border-emerald-500 mb-4">
              <CheckCircle2 size={32} className="text-emerald-500" />
            </div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-emerald-500">
              Payment complete
            </div>
            <h1 className="text-3xl font-black mt-2">
              ${((r.card_cents + (r.points_redeemed || 0)) / 100).toFixed(2)}
            </h1>
            <p className={`text-sm mt-1 ${muted}`}>
              paid at {r.merchant?.name || "the merchant"}
            </p>
          </div>
          <div className={`${card} rounded-2xl p-5 mt-6 space-y-2 text-sm`}>
            <Row label="Card charged" value={`$${(r.card_cents/100).toFixed(2)}`} />
            <Row label="Points redeemed"
                      value={`${r.points_redeemed} pts ($${(r.points_redeemed/100).toFixed(2)})`}
                      neg />
            <Row label="Points earned"
                      value={`+${r.points_earned} pts`}
                      good />
            <div className={`pt-3 border-t ${light ? "border-slate-200" : "border-slate-800"}
                                              text-[10px] font-mono ${muted}`}>
              Transaction: {r.transaction_id}
            </div>
          </div>
          <div className="flex gap-2 mt-6">
            <button onClick={() => nav("/wallet")}
                            data-testid="scan-checkout-view-wallet"
                            className="flex-1 py-2.5 rounded-full text-xs font-black
                                                    bg-amber-500 text-slate-950 hover:bg-amber-400">
              View wallet
            </button>
            <button onClick={() => nav("/scan")}
                            className="flex-1 py-2.5 rounded-full text-xs font-black
                                                    border border-slate-500/40 hover:bg-slate-500/10">
              Pay again
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Main checkout
  const merchant   = s.resolved?.merchant || {};
  const amount    = s.resolved?.amount_cents || 0;
  const balance    = s.resolved?.user_points_balance || 0;
  const maxByCap = s.quote?.max_points_allowed
                                    ?? (s.resolved?.settings?.max_points_redemption_pct || 50)
                                        * amount / 100;
  const sliderMax = Math.min(balance, Math.floor(maxByCap));

  return (
    <div className={`${bg} min-h-screen`} data-testid="scan-checkout-page">
      <div className="max-w-md mx-auto px-4 py-6">
        <button onClick={() => nav("/scan")}
                        className={`inline-flex items-center gap-1 text-xs ${muted}
                                              hover:opacity-80 mb-4`}
                        data-testid="scan-checkout-back">
          <ArrowLeft size={12} /> Cancel
        </button>

        <div className={`${card} rounded-2xl p-5`}>
          <div className="flex items-center gap-3">
            {merchant.logo_url ? (
              <img src={`${process.env.REACT_APP_BACKEND_URL}${merchant.logo_url}`}
                          alt="" className="w-12 h-12 rounded-lg object-cover bg-slate-800/40" />
            ) : (
              <div className="w-12 h-12 rounded-lg grid place-items-center
                                          bg-gradient-to-br from-fuchsia-500 to-amber-500">
                <Sparkles size={18} className="text-white" />
              </div>
            )}
            <div className="min-w-0 flex-1">
              <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
                Paying
              </div>
              <div className="text-lg font-black truncate"
                          data-testid="scan-checkout-merchant-name">
                {merchant.name}
              </div>
              <div className={`text-[10px] font-mono ${muted} mt-0.5
                                            inline-flex items-center gap-1`}>
                <Clock size={10} /> QR expires in 60s
              </div>
            </div>
            <div className="text-right">
              <div className={`text-[10px] uppercase tracking-widest font-mono ${muted}`}>
                Total
              </div>
              <div className="text-3xl font-black"
                          data-testid="scan-checkout-total">
                ${((amount + (Number(s.tipCents) || 0)) / 100).toFixed(2)}
              </div>
            </div>
          </div>
        </div>

        {/* Points slider */}
        <div className={`${card} rounded-2xl p-5 mt-4`}>
          <div className="flex items-center gap-2 mb-3">
            <Coins size={16} className="text-amber-500" />
            <span className="text-sm font-black">Use points</span>
            <span className={`ml-auto text-[10px] font-mono ${muted}`}>
              Balance: <span data-testid="scan-checkout-points-balance">{balance}</span> pts
            </span>
          </div>
          <input type="range" min="0" max={sliderMax}
                        value={s.pointsToUse}
                        onChange={(e) => set({ pointsToUse: Number(e.target.value) })}
                        step="1"
                        data-testid="scan-checkout-points-slider"
                        className="w-full accent-amber-500" />
          <div className="flex justify-between items-baseline mt-2">
            <span className="text-lg font-black text-amber-500">
              {s.pointsToUse} pts
            </span>
            <span className={`text-xs ${muted}`}
                        data-testid="scan-checkout-points-value">
              = ${(s.pointsToUse / 100).toFixed(2)}
            </span>
          </div>
          {sliderMax < balance && (
            <div className={`text-[10px] mt-1 font-mono ${muted}`}>
              Points capped at {s.resolved?.settings?.max_points_redemption_pct}% of the bill.
            </div>
          )}
        </div>

        {/* Tip */}
        <div className={`${card} rounded-2xl p-5 mt-4`}>
          <div className="text-[10px] uppercase tracking-widest font-mono mb-2">
            Add tip (optional)
          </div>
          <div className="flex gap-2">
            {[0, 100, 200, 500].map((t) => (
              <button key={t}
                              onClick={() => set({ tipCents: t })}
                              data-testid={`scan-checkout-tip-${t}`}
                              className={`flex-1 py-2 rounded-full text-xs font-black
                                                          border-2 transition ${
                                                              s.tipCents === t
                                                                  ? "border-amber-500 bg-amber-500/10 text-amber-500"
                                                                  : (light ? "border-slate-200 text-slate-600"
                                                                                : "border-slate-800 text-slate-400")}`}>
                {t === 0 ? "None" : `+$${(t/100).toFixed(2)}`}
              </button>
            ))}
          </div>
          <input type="number" min="0" step="1"
                        placeholder="Custom cents"
                        value={s.tipCents}
                        onChange={(e) => set({ tipCents: Number(e.target.value) || 0 })}
                        data-testid="scan-checkout-tip-input"
                        className={`w-full mt-2 px-3 py-2 rounded-lg text-sm
                                                    ${light ? "bg-white border border-slate-200"
                                                                    : "bg-slate-900 border border-slate-700"}`} />
        </div>

        {/* Breakdown + pay */}
        <div className={`${card} rounded-2xl p-5 mt-4 space-y-2 text-sm`}>
          <Row label="Card" value={`$${((s.quote?.card_cents || 0)/100).toFixed(2)}`}
                    testId="scan-checkout-card-cents" />
          <Row label="Points"
                    value={`${s.quote?.points_to_use || 0} pts ($${((s.quote?.points_value_cents || 0)/100).toFixed(2)})`}
                    neg />
          <Row label="You'll earn"
                    value={`+${s.quote?.points_earned || 0} pts`}
                    good />
          <button onClick={pay}
                          disabled={s.payBusy || s.quoteBusy || !s.quote
                                              || (s.quote.card_cents === 0 && s.quote.points_value_cents === 0)}
                          data-testid="scan-checkout-pay-button"
                          className="w-full mt-3 py-3 rounded-full text-sm font-black
                                                inline-flex items-center justify-center gap-2
                                                bg-emerald-500 text-slate-950 hover:bg-emerald-400
                                                disabled:opacity-40 disabled:cursor-not-allowed">
            {s.payBusy ? <Loader2 size={16} className="animate-spin" /> : <CreditCard size={16} />}
            Pay ${((amount + (Number(s.tipCents) || 0))/100).toFixed(2)}
          </button>
          <button onClick={() => setSplitOpen(true)}
                          data-testid="scan-checkout-split-button"
                          disabled={!user || !s.quote}
                          className={`w-full mt-2 py-2.5 rounded-full text-xs font-black
                                                    inline-flex items-center justify-center gap-2
                                                    border ${light ? "border-fuchsia-400 text-fuchsia-600 hover:bg-fuchsia-50"
                                                                                : "border-fuchsia-500/60 text-fuchsia-400 hover:bg-fuchsia-500/10"}
                                                    disabled:opacity-40 disabled:cursor-not-allowed`}>
            Split with a friend
          </button>
          <div className={`text-[10px] font-mono text-center ${muted}`}>
            Test-mode Stripe — card 4242 4242 4242 4242
          </div>
        </div>
      </div>

      <SplitModal
        open={splitOpen}
        onClose={() => setSplitOpen(false)}
        merchant={merchant}
        qrToken={token}
        totalAmountCents={amount + (Number(s.tipCents) || 0)}
        currency={"usd"}
        light={light}
      />
    </div>
  );
}


function Row({ label, value, neg, good, testId }) {
  return (
    <div className="flex justify-between items-center"
              data-testid={testId}>
      <span className="text-xs">{label}</span>
      <span className={`font-mono text-sm font-black ${
                                    neg ? "text-fuchsia-400" :
                                    good ? "text-emerald-400" : ""}`}>
        {value}
      </span>
    </div>
  );
}
