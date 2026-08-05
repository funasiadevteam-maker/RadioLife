// Phase SC.5 — Public payment receipt page.  No auth required.
//
// Reached in two ways:
//   1.  Automatic-payment-methods with `redirect: "if_required"` returns
//         no-redirect + the frontend `pollUntilTerminal` navigates here
//         once `payment_transactions_v2.status === "succeeded"`.
//   2.  Stripe redirects back to `return_url` after off-session flows
//         (Apple Pay / Google Pay / 3DS) — the intent may still be in
//         `processing` for a few seconds, so we poll `/receipt` (which
//         returns 404 until succeeded) with a max window of ~30s.
//
// Renders: merchant card, "Payment received" checkmark, amount, txn
// reference, date, optional table number, optional points banner,
// "Back to RadioLife" + "Explore more offers" CTAs.
import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { CheckCircle2, Clock, AlertTriangle, Loader2, MapPin,
                  Sparkles, ChevronRight } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const POLL_INTERVAL_MS = 2000;
const POLL_MAX_MS      = 30000;


export default function PayReceipt() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { token } = useParams();
  const [params] = useSearchParams();
  const intentId = params.get("intent_id")
                              || params.get("payment_intent")  // Stripe's default
                              || null;
  const navigate = useNavigate();

  const [state, setState] = useState("loading");   // loading | processing | succeeded | failed | not_found
  const [receipt, setReceipt] = useState(null);
  const [err, setErr] = useState(null);
  const timerRef = useRef(null);
  const startedAtRef = useRef(Date.now());

  useEffect(() => () => { if (timerRef.current) clearTimeout(timerRef.current); }, []);

  useEffect(() => {
    if (!intentId) { setState("not_found"); return; }
    let cancelled = false;

    async function fetchOnce() {
      try {
        const { data } = await axios.get(
          `${API}/pay/${token}/receipt`,
          { params: { intent_id: intentId } });
        if (cancelled) return;
        setReceipt(data);
        setState("succeeded");
      } catch (e) {
        if (cancelled) return;
        const status = e?.response?.status;
        const detail = e?.response?.data?.detail;
        // 404 with `not_succeeded_yet` → keep polling
        if (status === 404 && detail?.code === "not_succeeded_yet") {
          // Also nudge the /confirm-poll endpoint to speed up the sync
          try {
            await axios.post(`${API}/pay/${token}/confirm-poll`,
                                          { intent_id: intentId });
          } catch (_) { /* ignore */ }
          if (Date.now() - startedAtRef.current > POLL_MAX_MS) {
            setState("timeout");
            return;
          }
          setState("processing");
          timerRef.current = setTimeout(fetchOnce, POLL_INTERVAL_MS);
          return;
        }
        if (status === 404) { setState("not_found"); return; }
        setErr(detail?.detail || detail || e.message);
        setState("failed");
      }
    }
    fetchOnce();
    return () => { cancelled = true; };
  }, [token, intentId]);

  // ─── Render states ───────────────────────────────────────────
  if (state === "loading" || state === "processing") {
    return (
      <ShellFrame light={light} testid="receipt-processing">
        <div className={`w-full max-w-md rounded-3xl p-8 text-center ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          <div className={`inline-flex h-14 w-14 rounded-full items-center justify-center mb-4 ${
            light ? "bg-purple-100 text-purple-700"
                    : "bg-cyan-500/15 text-cyan-300"
          }`}>
            <Loader2 className="animate-spin" size={26}/>
          </div>
          <h1 className={`text-2xl font-black ${light ? "text-slate-900" : "text-white"}`}
                data-testid="receipt-processing-title">
            Confirming your payment…
          </h1>
          <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            Almost there — this usually takes just a few seconds.
          </p>
        </div>
      </ShellFrame>
    );
  }

  if (state === "timeout") {
    return (
      <ShellFrame light={light} testid="receipt-timeout">
        <div className={`w-full max-w-md rounded-3xl p-8 text-center ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          <div className={`inline-flex h-14 w-14 rounded-full items-center justify-center mb-4 ${
            light ? "bg-amber-100 text-amber-700"
                    : "bg-amber-500/15 text-amber-300"
          }`}>
            <Clock size={26}/>
          </div>
          <h1 className={`text-2xl font-black ${light ? "text-slate-900" : "text-white"}`}>
            Something took longer than expected
          </h1>
          <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            We&apos;re still confirming your payment.  You&apos;ll receive an email
            receipt once it clears.  Feel free to refresh in a moment.
          </p>
          <button type="button" onClick={() => window.location.reload()}
                        data-testid="receipt-refresh-btn"
                        className={`mt-6 h-11 px-6 rounded-full text-sm font-bold ${
                          light ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                                  : "bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25"
                        }`}>
            Refresh
          </button>
        </div>
      </ShellFrame>
    );
  }

  if (state === "not_found" || state === "failed") {
    return (
      <ShellFrame light={light} testid="receipt-error">
        <div className={`w-full max-w-md rounded-3xl p-8 text-center ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          <div className={`inline-flex h-14 w-14 rounded-full items-center justify-center mb-4 ${
            light ? "bg-rose-100 text-rose-700"
                    : "bg-rose-500/15 text-rose-300"
          }`}>
            <AlertTriangle size={26}/>
          </div>
          <h1 className={`text-2xl font-black ${light ? "text-slate-900" : "text-white"}`}
                data-testid="receipt-error-title">
            {state === "not_found" ? "Receipt not found" : "Something went wrong"}
          </h1>
          <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            {err || (state === "not_found"
              ? "We couldn\u2019t find this transaction.  Please check the link or contact the merchant."
              : "An error occurred while loading your receipt.")}
          </p>
          <button type="button" onClick={() => navigate(`/pay/${token}`)}
                        data-testid="receipt-back-to-pay"
                        className={`mt-6 h-11 px-6 rounded-full text-sm font-bold ${
                          light ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                                  : "bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25"
                        }`}>
            Back to payment page
          </button>
        </div>
      </ShellFrame>
    );
  }

  // ─── SUCCESS ─────────────────────────────────────────────────
  const merchant = receipt?.merchant || {};
  const link            = receipt?.link || {};
  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const logoUrl = merchant?.logo_url
    ? (merchant.logo_url.startsWith("http")
          ? merchant.logo_url : backendBase + merchant.logo_url)
    : null;
  const amountStr = ((receipt.amount_cents || 0) / 100).toFixed(2);
  const dateStr = receipt.succeeded_at
    ? new Date(receipt.succeeded_at).toLocaleString(undefined,
                { year: "numeric", month: "short", day: "numeric",
                  hour: "2-digit", minute: "2-digit" })
    : "";

  return (
    <ShellFrame light={light} testid="receipt-success">
      <div className="w-full max-w-lg">
        {/* Success hero */}
        <div className={`rounded-3xl p-8 mb-4 text-center ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          <div className={`inline-flex h-16 w-16 rounded-full items-center justify-center mb-4 ${
            light ? "bg-emerald-100 text-emerald-700"
                    : "bg-emerald-500/15 text-emerald-300"
          }`}>
            <CheckCircle2 size={30} strokeWidth={2.5}/>
          </div>
          <h1 className={`text-3xl font-black tracking-tight ${
            light ? "text-slate-900" : "text-white"
          }`} data-testid="receipt-success-title">
            Payment received
          </h1>
          <div className={`mt-3 text-4xl font-black tabular-nums ${
            light ? "text-slate-900" : "text-white"
          }`} data-testid="receipt-amount">
            {amountStr}
            <span className={`ml-2 text-xl font-bold ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>{receipt.currency}</span>
          </div>
          {receipt.points_earned > 0 && (
            <div className={`inline-flex items-center gap-1.5 mt-4 px-4 py-2 rounded-full text-sm font-bold ${
              light ? "bg-purple-100 text-purple-700"
                      : "bg-purple-500/15 text-purple-300"
            }`} data-testid="receipt-points-banner">
              <Sparkles size={14}/>
              +{receipt.points_earned} RadioLife points added
            </div>
          )}
        </div>

        {/* Merchant + details card */}
        <div className={`rounded-3xl p-6 mb-4 ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`} data-testid="receipt-merchant-card">
          <div className="flex items-start gap-4">
            {logoUrl ? (
              <img src={logoUrl} alt={merchant.name || ""}
                        className="w-14 h-14 rounded-2xl object-cover shadow-sm"
                        data-testid="receipt-merchant-logo"/>
            ) : (
              <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${
                light ? "bg-purple-100 text-purple-600"
                        : "bg-slate-800 text-slate-500"
              }`}>
                <Sparkles size={20}/>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className={`text-[10px] font-bold uppercase tracking-widest ${
                light ? "text-purple-600" : "text-cyan-400"
              }`}>
                {(merchant.category || "").replace(/_/g, " ") || "Merchant"}
              </div>
              <div className={`mt-1 text-lg font-black tracking-tight ${
                light ? "text-slate-900" : "text-white"
              }`} data-testid="receipt-merchant-name">
                {merchant.name || "—"}
              </div>
              {merchant.primary_location && (
                <div className={`mt-1 flex items-center gap-1 text-xs ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>
                  <MapPin size={12}/>
                  <span className="truncate">
                    {merchant.primary_location.address}
                    {merchant.primary_location.city && `, ${merchant.primary_location.city}`}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Line items table */}
          <div className={`mt-5 pt-5 border-t space-y-3 ${
            light ? "border-slate-100" : "border-slate-800"
          }`}>
            <ReceiptRow light={light} label="Item" value={link.title || "Payment"}
                                  testid="receipt-row-item"/>
            {receipt.table_number && (
              <ReceiptRow light={light} label="Table"
                                    value={`Table ${receipt.table_number}`}
                                    testid="receipt-row-table"/>
            )}
            {receipt.payment_method_type && (
              <ReceiptRow light={light} label="Payment method"
                                    value={receipt.payment_method_type.replace(/_/g, " ")}
                                    testid="receipt-row-method"/>
            )}
            <ReceiptRow light={light} label="Reference"
                                  value={<code className={`text-[11px] ${
                                    light ? "text-slate-700" : "text-slate-300"
                                  }`}>{receipt.transaction_id}</code>}
                                  testid="receipt-row-reference"/>
            {dateStr && (
              <ReceiptRow light={light} label="Date" value={dateStr}
                                    testid="receipt-row-date"/>
            )}
          </div>
        </div>

        {/* Phase MER.4 — Follow-this-business CTA (only when merchant_id available) */}
        {receipt.merchant_id && (
          <FollowMerchantCTA light={light}
                                                merchantId={receipt.merchant_id}
                                                merchantName={receipt.merchant?.name}/>
        )}

        {/* CTAs */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Link to="/"
                    data-testid="receipt-back-home"
                    className={`h-12 rounded-full font-bold text-sm inline-flex items-center justify-center gap-1 ${
                      light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                              : "bg-slate-800 text-slate-200 hover:bg-slate-700"
                    }`}>
            Back to RadioLife
          </Link>
          <Link to="/discover"
                    data-testid="receipt-explore-offers"
                    className="h-12 rounded-full font-bold text-sm text-white
                                        inline-flex items-center justify-center gap-1
                                        shadow-lg shadow-purple-500/25 hover:brightness-110"
                    style={{background: "linear-gradient(135deg,#a855f7,#ec4899)"}}>
            Explore more offers <ChevronRight size={16}/>
          </Link>
        </div>

        <div className={`text-center mt-6 text-[10px] font-bold uppercase tracking-widest ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>
          Powered by RadioLife
        </div>
      </div>
    </ShellFrame>
  );
}


// ─── Helpers ─────────────────────────────────────────────────────
function ShellFrame({ light, testid, children }) {
  return (
    <div className={light
                          ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50 flex items-center justify-center p-5"
                          : "min-h-screen bg-slate-950 flex items-center justify-center p-5"}
              data-testid={testid}>
      {children}
    </div>
  );
}


function ReceiptRow({ light, label, value, testid }) {
  return (
    <div className="flex items-start justify-between gap-4"
              data-testid={testid}>
      <span className={`text-xs uppercase tracking-wider font-semibold ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>{label}</span>
      <span className={`text-sm font-semibold text-right ${
        light ? "text-slate-800" : "text-slate-200"
      }`}>{value}</span>
    </div>
  );
}


// Phase MER.4 — one-tap follow after successful payment.
function FollowMerchantCTA({ light, merchantId, merchantName }) {
  const [state, setState] = React.useState("idle");  // idle | busy | done
  const follow = async () => {
    setState("busy");
    try {
      await axios.post(`${API}/business/${merchantId}/follow`, null,
                                        { withCredentials: true });
      setState("done");
    } catch (e) {
      if (e?.response?.status === 401) {
        // Anon guest — send them to login with return-to
        window.location.href = `/login?next=/business/${merchantId}`;
      } else {
        setState("idle");
      }
    }
  };
  if (state === "done") {
    return (
      <div className={`mb-4 rounded-2xl p-4 flex items-center gap-3 ${
        light ? "bg-rose-50 border border-rose-100"
                : "bg-rose-500/10 border border-rose-500/20"}`}
                data-testid="receipt-follow-done">
        <CheckCircle2 size={18} color={light ? "#e11d48" : "#fb7185"}/>
        <div className={`text-sm font-black ${
          light ? "text-rose-800" : "text-rose-200"}`}>
          You're now following {merchantName || "this business"} 
        </div>
      </div>);
  }
  return (
    <button type="button" onClick={follow} disabled={state === "busy"}
                  data-testid="receipt-follow-cta"
                  className={`mb-4 w-full rounded-2xl p-4 text-left flex items-center gap-3 ${
                    light ? "bg-white border border-slate-100 shadow-sm hover:border-rose-300"
                            : "bg-slate-900 border border-slate-800 hover:border-rose-500/30"}`}>
      <div className={`w-10 h-10 rounded-full flex items-center justify-center ${
        light ? "bg-rose-100 text-rose-600" : "bg-rose-500/20 text-rose-400"}`}>
        <Sparkles size={16}/>
      </div>
      <div className="flex-1 min-w-0">
        <div className={`text-sm font-black ${
          light ? "text-slate-900" : "text-white"}`}>
          Follow {merchantName || "this business"}
        </div>
        <div className={`text-[10px] ${
          light ? "text-slate-500" : "text-slate-500"}`}>
          Get notified about future offers &amp; events
        </div>
      </div>
      <ChevronRight size={16} color={light ? "#64748b" : "#94a3b8"}/>
    </button>
  );
}
