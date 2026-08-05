// Phase SC.4 — Public consumer pay page.  No auth required.
// Phase SC.5 — Real Stripe destination-charge flow (replaces placeholder).
//
// Renders merchant metadata (logo, name, category badge, primary
// location, description) + link details + a Payment Element flow.
// Commission preview is HIDDEN from the customer per SC.4 constraint 3.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { AlertTriangle, Ban, CheckCircle2, Clock, Loader2, MapPin,
                  ShieldCheck, Sparkles, X, Tag, CreditCard, Coins,
                  UtensilsCrossed, ChevronDown, ChevronUp, Trash2 } from "lucide-react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useStripe, useElements }
  from "@stripe/react-stripe-js";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const INACTIVE_MSG = {
  not_found:            { title: "Link not found",
                                    text:  "This payment link doesn't exist or has been removed." },
  deactivated:      { title: "No longer active",
                                    text:  "The merchant has deactivated this payment link." },
  expired:            { title: "This link has expired",
                                    text:  "The merchant set an end date that's now past." },
  max_uses_reached: { title: "Fully redeemed",
                                    text:  "This link has reached its usage cap." },
};

// Cache Stripe instances per publishable key (avoid re-creating on re-render)
const _stripePromises = {};
function getStripe(pk) {
  if (!pk) return null;
  if (!_stripePromises[pk]) {
    _stripePromises[pk] = loadStripe(pk);
  }
  return _stripePromises[pk];
}


export default function PayPage() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { token } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [customAmount, setCustomAmount] = useState("");
  const [emailInput, setEmailInput] = useState("");
  const [showPayModal, setShowPayModal] = useState(false);
  const [intent, setIntent] = useState(null);         // full /intent response
  const [creatingIntent, setCreatingIntent] = useState(false);

  // Phase MER.3 — checkout modifiers state
  const [modifiersOpen, setModifiersOpen] = useState(false);
  const [modifiers, setModifiers] = useState([]);
  const [modifierInput, setModifierInput] = useState({type: "coupon", code: ""});
  const [pointsAmount, setPointsAmount] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [zeroCharging, setZeroCharging] = useState(false);
  const [wallet, setWallet] = useState(null);        // logged-in user's balances

  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/pay/link/${token}`);
        setData(data);
      } catch (e) {
        if (e?.response?.status === 404) setErr("not_found");
        else {
          setErr("load_error");
          toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
        }
      } finally { setLoading(false); }
    })();
  }, [token]);

  const link = data?.link;
  const merchant = data?.merchant;
  const backendBase = (process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
  const logoUrl = merchant?.logo_url
    ? (merchant.logo_url.startsWith("http")
          ? merchant.logo_url : backendBase + merchant.logo_url)
    : null;

  const isCustomAmount = link && link.amount_cents == null;
  const finalAmountCents = isCustomAmount
    ? (customAmount ? Math.round(parseFloat(customAmount) * 100) : null)
    : link?.amount_cents;

  const amountValid = useMemo(() => {
    if (!isCustomAmount) return true;
    if (!finalAmountCents || finalAmountCents <= 0) return false;
    if (link?.min_amount_cents && finalAmountCents < link.min_amount_cents) return false;
    if (link?.max_amount_cents && finalAmountCents > link.max_amount_cents) return false;
    return true;
  }, [isCustomAmount, finalAmountCents, link]);

  const emailRequiredButMissing = !user && !emailInput.trim().match(/.+@.+\..+/);
  const canPay = amountValid && !emailRequiredButMissing;

  // Phase MER.3 — pre-load user's wallet to show applicable modifiers
  useEffect(() => {
    if (!user) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/wallet/me`,
                                                                            { withCredentials: true });
        setWallet(data);
      } catch (e) { /* silent — user may just not have anything */ }
    })();
  }, [user]);

  // Recompute preview whenever amount + modifier list changes
  useEffect(() => {
    if (modifiers.length === 0) { setPreview(null); return; }
    if (!amountValid || !finalAmountCents) return;
    (async () => {
      setPreviewing(true);
      try {
        const { data } = await axios.post(
          `${API}/pay/${token}/modifiers/preview`,
          { amount_cents: finalAmountCents, modifiers },
          { withCredentials: true });
        setPreview(data);
      } catch (e) {
        const det = e?.response?.data?.detail;
        toast.error(`Preview failed: ${det?.detail || det?.code || e.message}`);
      } finally { setPreviewing(false); }
    })();
  }, [modifiers, finalAmountCents, token, amountValid]);

  const addModifier = () => {
    const t = modifierInput.type;
    if (t === "points") {
      const cents = Math.round(parseFloat(pointsAmount || "0") * 100);
      if (!cents || cents <= 0) { toast.error("Enter a valid AED amount"); return; }
      // Replace any existing points modifier
      const others = modifiers.filter(m => m.type !== "points");
      setModifiers([...others, { type: "points", amount_cents: cents }]);
      setPointsAmount("");
    } else {
      const code = modifierInput.code.trim().toUpperCase();
      if (!code) { toast.error("Enter a code"); return; }
      // Prevent duplicate codes
      if (modifiers.some(m => (m.code_or_id || "").toUpperCase() === code)) {
        toast.error("Already applied"); return;
      }
      setModifiers([...modifiers, { type: t, code_or_id: code }]);
      setModifierInput({type: t, code: ""});
    }
  };

  const removeModifier = (idx) => {
    setModifiers(modifiers.filter((_, i) => i !== idx));
  };

  const onPay = async () => {
    if (!canPay) {
      if (emailRequiredButMissing) toast.error("Enter your email for the receipt");
      else if (!amountValid)                toast.error("Please enter a valid amount");
      return;
    }
    // Phase MER.3 — zero-charge path
    if (preview?.zero_charge) {
      setZeroCharging(true);
      try {
        const { data } = await axios.post(
          `${API}/pay/${token}/zero-charge`,
          { amount_cents: finalAmountCents,
            modifiers,
            customer_email: user?.email || emailInput.trim() || null },
          { withCredentials: true });
        toast.success("Order confirmed · no card needed");
        navigate(`/pay/${token}/receipt?tx=${data.transaction_id}`);
      } catch (e) {
        const det = e?.response?.data?.detail;
        toast.error(`Zero-charge failed: ${det?.detail || det?.code || e.message}`);
      } finally { setZeroCharging(false); }
      return;
    }

    setCreatingIntent(true);
    try {
      const { data: intentData } = await axios.post(
        `${API}/pay/${token}/intent`,
        { amount_cents: finalAmountCents,
          customer_email: user?.email || emailInput.trim() || null,
          modifiers: modifiers.length ? modifiers : undefined },
        { withCredentials: true });
      setIntent(intentData);
      setShowPayModal(true);
    } catch (e) {
      const det = e?.response?.data?.detail;
      const msg = det?.detail || det?.code || det || e.message;
      toast.error(`Payment setup failed: ${msg}`);
    } finally { setCreatingIntent(false); }
  };

  if (loading) {
    return <div className={light ? "min-h-screen bg-white flex items-center justify-center"
                                                    : "min-h-screen bg-slate-950 flex items-center justify-center"}
                          data-testid="pay-page-loading">
      <Loader2 className="animate-spin" size={30}
                        color={light ? "#a855f7" : "#00d4ff"}/>
    </div>;
  }

  if (err === "not_found")  return <InactiveState light={light} kind="not_found"/>;
  if (err)                                  return <InactiveState light={light} kind="not_found"
                                                                                        customTitle="Something went wrong"
                                                                                        customText="Try refreshing. If the problem persists, contact the merchant."/>;
  if (data && !data.active) return <InactiveState light={light} kind={data.inactive_reason || "deactivated"}/>;

  return (
    <div className={light
                            ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
                            : "min-h-screen bg-slate-950 text-slate-100"}
              data-testid="pay-page"
              data-variant={variant}
              data-token={token}>
      <div className="max-w-lg mx-auto px-5 py-10">
        {/* Merchant card */}
        <div className={`rounded-3xl p-6 mb-4 ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`} data-testid="pay-merchant-card">
          <div className="flex items-start gap-4">
            {logoUrl ? (
              <img src={logoUrl} alt={merchant?.name || ""}
                        className="w-16 h-16 rounded-2xl object-cover shadow-sm"
                        data-testid="pay-merchant-logo"/>
            ) : (
              <div className={`w-16 h-16 rounded-2xl flex items-center justify-center ${
                light ? "bg-purple-100 text-purple-600"
                        : "bg-slate-800 text-slate-500"
              }`}>
                <Sparkles size={22}/>
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className={`text-[10px] font-bold uppercase tracking-widest ${
                light ? "text-purple-600" : "text-cyan-400"
              }`} data-testid="pay-merchant-category">
                {(merchant?.category || "").replace(/_/g, " ") || "Merchant"}
              </div>
              <h2 className={`mt-1 text-2xl font-black tracking-tight ${
                light ? "text-slate-900" : "text-white"
              }`} data-testid="pay-merchant-name">
                {merchant?.name || "—"}
              </h2>
              {merchant?.primary_location && (
                <div className={`mt-1 flex items-center gap-1 text-xs ${
                  light ? "text-slate-500" : "text-slate-500"
                }`} data-testid="pay-merchant-location">
                  <MapPin size={12}/>
                  <span className="truncate">
                    {merchant.primary_location.address}
                    {merchant.primary_location.city && `, ${merchant.primary_location.city}`}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Link + amount + Pay Now */}
        <div className={`rounded-3xl p-6 mb-4 ${
          light ? "bg-white shadow-sm border border-slate-100"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          {link?.table_number && (
            <div className={`inline-block text-[10px] font-bold uppercase tracking-widest px-2 py-1 rounded-full mb-3 ${
              light ? "bg-purple-100 text-purple-700"
                      : "bg-cyan-500/15 text-cyan-300"
            }`} data-testid="pay-table-chip">
              Table {link.table_number}
            </div>
          )}

          <h1 className={`text-2xl font-black tracking-tight ${
            light ? "text-slate-900" : "text-white"
          }`} data-testid="pay-link-title">{link?.title || "Payment"}</h1>
          {link?.description && (
            <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}
                data-testid="pay-link-description">{link.description}</p>
          )}

          <div className="mt-6">
            {isCustomAmount ? (
              <div>
                <div className={`text-[11px] font-bold uppercase tracking-widest mb-2 ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>Enter amount</div>
                <div className="flex items-center gap-2">
                  <input type="number" min={0} step="0.01"
                              value={customAmount}
                              onChange={(e) => setCustomAmount(e.target.value)}
                              placeholder="0.00"
                              data-testid="pay-custom-amount-input"
                              className={`flex-1 h-14 rounded-2xl px-4 text-2xl font-black tabular-nums outline-none ${
                                light
                                  ? "bg-slate-50 border border-slate-200 text-slate-900 focus:border-purple-500"
                                  : "bg-slate-950 border border-slate-800 text-slate-100 focus:border-cyan-500"
                              }`}/>
                  <span className={`text-lg font-bold ${
                    light ? "text-slate-600" : "text-slate-400"
                  }`}>{link?.currency || "AED"}</span>
                </div>
                {(link?.min_amount_cents || link?.max_amount_cents) && (
                  <div className={`mt-1 text-[10px] ${
                    light ? "text-slate-500" : "text-slate-500"
                  }`}>
                    {link.min_amount_cents ? `Min ${(link.min_amount_cents/100).toFixed(2)}` : ""}
                    {link.min_amount_cents && link.max_amount_cents ? " · " : ""}
                    {link.max_amount_cents ? `Max ${(link.max_amount_cents/100).toFixed(2)}` : ""}
                    {" "}{link.currency}
                  </div>
                )}
              </div>
            ) : (
              <div>
                <div className={`text-[11px] font-bold uppercase tracking-widest mb-1 ${
                  light ? "text-slate-500" : "text-slate-500"
                }`}>Amount</div>
                <div className={`text-4xl font-black tabular-nums ${
                  light ? "text-slate-900" : "text-white"
                }`} data-testid="pay-amount-display">
                  {(link.amount_cents / 100).toFixed(2)}
                  <span className={`ml-2 text-xl font-bold ${
                    light ? "text-slate-500" : "text-slate-500"
                  }`}>{link.currency}</span>
                </div>
              </div>
            )}
          </div>

          {/* Guest email input — required so we can send the receipt. */}
          {!user && (
            <div className="mt-5">
              <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 ${
                light ? "text-slate-500" : "text-slate-500"
              }`}>Email for receipt</div>
              <input type="email" value={emailInput}
                          onChange={(e) => setEmailInput(e.target.value)}
                          placeholder="you@example.com"
                          data-testid="pay-guest-email-input"
                          className={`w-full h-11 rounded-xl px-3 text-sm outline-none ${
                            light
                              ? "bg-slate-50 border border-slate-200 text-slate-900 focus:border-purple-500"
                              : "bg-slate-950 border border-slate-800 text-slate-100 focus:border-cyan-500"
                          }`}/>
            </div>
          )}

          {/* Phase MER.3 — apply discount / points collapsible section */}
          <div className={`mt-5 rounded-2xl border ${
            light ? "border-slate-200 bg-slate-50/50"
                    : "border-slate-800 bg-slate-950"
          }`} data-testid="pay-modifiers-section">
            <button type="button"
                          onClick={() => setModifiersOpen(!modifiersOpen)}
                          data-testid="pay-modifiers-toggle"
                          className={`w-full flex items-center gap-2 px-4 py-3 text-sm font-black ${
                            light ? "text-slate-800" : "text-slate-100"}`}>
              <Tag size={14}/> Apply discount, gift card or points
              <span className="ml-auto">
                {modifiersOpen ? <ChevronUp size={16}/> : <ChevronDown size={16}/>}
              </span>
            </button>
            {modifiersOpen && (
              <div className={`px-4 pb-4 border-t ${
                light ? "border-slate-200" : "border-slate-800"}`}>
                <div className="mt-3 grid grid-cols-3 gap-1">
                  {["coupon","gift_card","points"].map(t => (
                    <button key={t} type="button"
                                  onClick={() => setModifierInput({type: t, code: ""})}
                                  data-testid={`pay-modifier-type-${t}`}
                                  data-active={modifierInput.type === t}
                                  className={`h-9 rounded-full text-[10px] font-black uppercase tracking-widest ${
                                    modifierInput.type === t
                                      ? (light ? "bg-slate-900 text-white"
                                                    : "bg-white text-slate-950")
                                      : (light ? "bg-white text-slate-700 border border-slate-200"
                                                    : "bg-slate-900 text-slate-300 border border-slate-800")}`}>
                      {t === "gift_card" ? "Gift Card" :
                        t === "points" ? "Points" : "Coupon"}
                    </button>
                  ))}
                </div>
                <div className="mt-3 flex gap-2">
                  {modifierInput.type === "points" ? (
                    <input type="number" step="0.01" min={0.01}
                                value={pointsAmount}
                                onChange={(e) => setPointsAmount(e.target.value)}
                                onKeyDown={(e) => e.key === "Enter" && addModifier()}
                                placeholder={wallet ? `Max ${((wallet.points_balance||0)/100).toFixed(2)} AED (${wallet.points_balance||0} pts)` : "0.00 AED"}
                                data-testid="pay-modifier-input"
                                className={`flex-1 h-10 rounded-xl px-3 text-sm outline-none ${
                                  light ? "bg-white border border-slate-200 focus:border-purple-500"
                                          : "bg-slate-950 border border-slate-800 focus:border-cyan-500 text-white"}`}/>
                  ) : (
                    <input type="text"
                                value={modifierInput.code}
                                onChange={(e) => setModifierInput({...modifierInput, code: e.target.value.toUpperCase()})}
                                onKeyDown={(e) => e.key === "Enter" && addModifier()}
                                placeholder={modifierInput.type === "gift_card" ? "BIGFM-GC-XXXXXX" : "BIGFM-XXXXXX"}
                                data-testid="pay-modifier-input"
                                className={`flex-1 h-10 rounded-xl px-3 text-sm font-mono outline-none uppercase ${
                                  light ? "bg-white border border-slate-200 focus:border-purple-500"
                                          : "bg-slate-950 border border-slate-800 focus:border-cyan-500 text-white"}`}/>
                  )}
                  <button type="button" onClick={addModifier}
                                data-testid="pay-modifier-add"
                                className={`h-10 rounded-full px-4 text-xs font-bold ${
                                  light ? "bg-slate-900 text-white"
                                          : "bg-white text-slate-950"}`}>
                    Apply
                  </button>
                </div>

                {modifiers.length > 0 && (
                  <div className="mt-3 space-y-1.5" data-testid="pay-modifiers-list">
                    {modifiers.map((m, i) => {
                      const p = (preview?.discounts || [])[i] || {};
                      return (
                        <div key={i} className={`flex items-center gap-2 p-2 rounded-xl text-xs ${
                          p.ok === false
                            ? (light ? "bg-rose-50" : "bg-rose-500/10")
                            : (light ? "bg-emerald-50" : "bg-emerald-500/10")}`}
                              data-testid={`pay-modifier-row-${i}`}>
                          {m.type === "coupon" && <Tag size={12}/>}
                          {m.type === "gift_card" && <CreditCard size={12}/>}
                          {m.type === "points" && <Coins size={12}/>}
                          <span className="font-mono">{m.code_or_id || `${m.amount_cents/100} AED`}</span>
                          <span className="ml-auto font-bold">
                            {p.ok === false
                              ? `✗ ${p.reason}`
                              : `-${((p.amount_reduced_cents || 0)/100).toFixed(2)}`}
                          </span>
                          <button type="button" onClick={() => removeModifier(i)}
                                        data-testid={`pay-modifier-remove-${i}`}
                                        className={light ? "text-slate-400 hover:text-rose-600"
                                                              : "text-slate-500 hover:text-rose-400"}>
                            <Trash2 size={12}/>
                          </button>
                        </div>
                      );
                    })}
                  </div>
                )}

                {previewing && (
                  <div className={`mt-2 text-[10px] flex items-center gap-1 ${
                    light ? "text-slate-500" : "text-slate-500"}`}>
                    <Loader2 className="animate-spin" size={10}/> Calculating…
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Phase MER.3 — order summary if any modifiers applied */}
          {preview && preview.total_discount_cents > 0 && (
            <div className={`mt-4 rounded-2xl p-4 space-y-1.5 ${
              light ? "bg-purple-50 border border-purple-100"
                      : "bg-cyan-500/10 border border-cyan-500/20"}`}
                  data-testid="pay-order-summary">
              <SummaryRow light={light} k="Subtotal" v={preview.subtotal_cents}/>
              {(preview.discounts || []).filter(d => d.ok && d.amount_reduced_cents > 0).map((d, i) => (
                <SummaryRow key={i} light={light}
                                          k={`− ${d.type === "gift_card" ? "Gift Card" :
                                                      d.type === "points" ? "Points" :
                                                      d.type === "prepaid_meal" ? "Meal Pack" : "Coupon"}`}
                                          v={-d.amount_reduced_cents} negative/>
              ))}
              <div className={`h-px my-1 ${
                light ? "bg-slate-300" : "bg-slate-700"}`}></div>
              <SummaryRow light={light} k="Total charge" v={preview.stripe_charge_cents}
                                        bold data-testid="pay-summary-total"/>
            </div>
          )}

          <button type="button" onClick={onPay}
                        disabled={!canPay || creatingIntent || zeroCharging || previewing}
                        data-testid="pay-now-btn"
                        className={`mt-6 w-full h-14 rounded-full font-black text-base tracking-tight transition-all ${
                          canPay && !creatingIntent && !zeroCharging
                            ? "text-white shadow-lg shadow-purple-500/25 hover:brightness-110 active:scale-[0.99]"
                            : "text-slate-400 bg-slate-200/50 cursor-not-allowed"
                        }`}
                        style={canPay && !creatingIntent && !zeroCharging
                          ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" }
                          : undefined}>
            {creatingIntent
              ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={16}/> Preparing secure payment…</span>
              : zeroCharging
              ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={16}/> Confirming order…</span>
              : preview?.zero_charge
              ? "Confirm Order (no card needed)"
              : preview && preview.total_discount_cents > 0
              ? `Pay ${((preview.stripe_charge_cents||0)/100).toFixed(2)} ${link?.currency||"AED"}`
              : "Pay Now"}
          </button>

          <div className={`mt-3 flex items-center justify-center gap-1 text-[10px] font-semibold ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>
            <ShieldCheck size={12}/> Secured by RadioLife &amp; Stripe
          </div>
        </div>

        <div className={`text-center text-[10px] font-bold uppercase tracking-widest ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>
          Powered by RadioLife
        </div>
      </div>

      {showPayModal && intent && (
        <PaymentModal light={light}
                                    token={token}
                                    intent={intent}
                                    navigate={navigate}
                                    onClose={() => setShowPayModal(false)}/>
      )}
    </div>
  );
}


// ─── Payment Modal — hosts the Stripe Payment Element ────────────
function PaymentModal({ light, token, intent, navigate, onClose }) {
  const stripePromise = getStripe(intent.publishable_key);
  const options = { clientSecret: intent.client_secret,
                                appearance: {
                                  theme: light ? "flat" : "night",
                                  variables: {
                                    colorPrimary: light ? "#a855f7" : "#00d4ff",
                                    colorBackground: light ? "#ffffff" : "#0d0d18",
                                    colorText: light ? "#0f172a" : "#e2e8f0",
                                    borderRadius: "12px",
                                  },
                                } };

  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 p-0 sm:p-4"
              onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
                data-testid="pay-payment-modal"
                className={`w-full sm:max-w-md sm:rounded-3xl rounded-t-3xl max-h-[95vh] overflow-y-auto ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"
                }`}>
        <div className={`sticky top-0 flex items-center justify-between p-5 ${
          light ? "bg-white border-b border-slate-100"
                  : "bg-slate-900 border-b border-slate-800"
        }`}>
          <div>
            <div className={`text-[10px] font-bold uppercase tracking-widest ${
              light ? "text-purple-600" : "text-cyan-400"
            }`}>Secure checkout</div>
            <div className={`text-lg font-black ${
              light ? "text-slate-900" : "text-white"
            }`} data-testid="pay-modal-amount">
              {(intent.amount_cents/100).toFixed(2)} {intent.currency}
              <span className={`ml-2 text-xs font-semibold ${
                light ? "text-slate-500" : "text-slate-400"
              }`}>→ {intent.merchant?.name}</span>
            </div>
          </div>
          <button type="button" onClick={onClose}
                        data-testid="pay-modal-close"
                        className={light ? "text-slate-500" : "text-slate-500"}>
            <X size={22}/>
          </button>
        </div>

        <div className="p-5">
          {stripePromise ? (
            <Elements stripe={stripePromise} options={options}>
              <PaymentInner light={light} token={token} intent={intent}
                                          navigate={navigate} onClose={onClose}/>
            </Elements>
          ) : (
            <div className={`p-5 rounded-2xl text-sm ${
              light ? "bg-rose-50 border border-rose-200 text-rose-800"
                      : "bg-rose-500/10 border border-rose-500/30 text-rose-300"
            }`}>
              Stripe publishable key not configured.  Please contact support.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


// Phase MER.3 — order summary row helper
function SummaryRow({ light, k, v, bold, negative }) {
  const amt = Math.abs(v || 0);
  return (
    <div className={`flex items-center justify-between text-xs ${
      bold ? "font-black" : "font-semibold"
    } ${light ? "text-slate-900" : "text-white"}`}>
      <span className={light ? "text-slate-700" : "text-slate-300"}>{k}</span>
      <span className={negative
        ? (light ? "text-emerald-700" : "text-emerald-300")
        : ""}>
        {negative ? "−" : ""}{(amt / 100).toFixed(2)}
      </span>
    </div>
  );
}


function PaymentInner({ light, token, intent, navigate, onClose }) {
  const stripe = useStripe();
  const elements = useElements();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [polling, setPolling] = useState(false);
  const pollTimeout = useRef(null);

  useEffect(() => () => { if (pollTimeout.current) clearTimeout(pollTimeout.current); }, []);

  const pollUntilTerminal = useCallback(async () => {
    setPolling(true);
    const started = Date.now();
    const doOne = async () => {
      try {
        const { data } = await axios.post(
          `${API}/pay/${token}/confirm-poll`,
          { intent_id: intent.intent_id });
        if (data.local_status === "succeeded") {
          navigate(`/pay/${token}/receipt?intent_id=${intent.intent_id}`);
          return;
        }
        if (data.local_status === "failed"
                  || data.local_status === "canceled") {
          setErr(data.handler_result?.failure_reason || "Payment failed.");
          setPolling(false);
          return;
        }
      } catch (e) {
        // 404 or transient — keep trying up to 45s
      }
      if (Date.now() - started > 45000) {
        setErr("Payment is taking longer than expected.  Please check your wallet in a moment.");
        setPolling(false);
        return;
      }
      pollTimeout.current = setTimeout(doOne, 2000);
    };
    doOne();
  }, [token, intent, navigate]);

  const submit = async () => {
    if (!stripe || !elements) return;
    setBusy(true);
    setErr(null);
    try {
      const { error } = await stripe.confirmPayment({
        elements,
        redirect: "if_required",
        confirmParams: {
          return_url: `${window.location.origin}/pay/${token}/receipt?intent_id=${intent.intent_id}`,
        },
      });
      if (error) {
        setErr(error.message || "Card was declined.");
        setBusy(false);
        return;
      }
      // No redirect happened → poll the backend for terminal state
      await pollUntilTerminal();
    } catch (e) {
      setErr(e.message || "Unexpected error");
      setBusy(false);
    }
  };

  return (
    <div>
      <div data-testid="pay-payment-element-wrap">
        <PaymentElement options={{ layout: "tabs" }} />
      </div>

      {err && (
        <div className={`mt-3 rounded-xl px-3 py-2 text-sm ${
          light ? "bg-rose-50 border border-rose-200 text-rose-800"
                  : "bg-rose-500/10 border border-rose-500/30 text-rose-300"
        }`} data-testid="pay-error-msg">
          {err}
        </div>
      )}

      <button type="button" onClick={submit}
                    disabled={!stripe || busy || polling}
                    data-testid="pay-confirm-btn"
                    className={`mt-4 w-full h-13 py-3 rounded-full font-black text-base tracking-tight ${
                      (busy || polling || !stripe)
                        ? "text-slate-400 bg-slate-200/50 cursor-not-allowed"
                        : "text-white shadow-lg shadow-purple-500/25"
                    }`}
                    style={(busy || polling || !stripe) ? undefined
                      : { background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
        {busy ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={16}/> Processing…</span>
                    : polling ? <span className="inline-flex items-center gap-2"><Loader2 className="animate-spin" size={16}/> Confirming…</span>
                    : `Confirm & Pay ${(intent.amount_cents/100).toFixed(2)} ${intent.currency}`}
      </button>

      <div className={`mt-3 flex items-center justify-center gap-1 text-[10px] font-semibold ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>
        <ShieldCheck size={12}/> Secured by Stripe · Test mode
      </div>
    </div>
  );
}


function InactiveState({ light, kind, customTitle, customText }) {
  const msg = customTitle
    ? { title: customTitle, text: customText || "" }
    : (INACTIVE_MSG[kind] || INACTIVE_MSG.deactivated);
  const Icon = kind === "not_found" ? AlertTriangle
                            : kind === "expired" ? Clock
                            : kind === "max_uses_reached" ? CheckCircle2
                            : Ban;
  return (
    <div className={light
                          ? "min-h-screen bg-white flex items-center justify-center p-6"
                          : "min-h-screen bg-slate-950 flex items-center justify-center p-6"}
              data-testid="pay-page-inactive"
              data-reason={kind}>
      <div className={`max-w-md w-full rounded-3xl p-8 text-center ${
        light ? "bg-white shadow-sm border border-slate-100"
                : "bg-slate-900 border border-slate-800"
      }`}>
        <div className={`inline-flex h-14 w-14 rounded-full items-center justify-center mb-4 ${
          light ? "bg-amber-100 text-amber-700"
                  : "bg-amber-500/20 text-amber-300"
        }`}>
          <Icon size={26}/>
        </div>
        <h1 className={`text-2xl font-black ${light ? "text-slate-900" : "text-white"}`}
              data-testid="pay-inactive-title">{msg.title}</h1>
        <p className={`mt-2 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}
              data-testid="pay-inactive-text">{msg.text}</p>
        <div className={`mt-6 text-[10px] font-bold uppercase tracking-widest ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>
          Powered by RadioLife
        </div>
      </div>
    </div>
  );
}
