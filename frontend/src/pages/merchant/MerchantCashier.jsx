// Phase MER.2 — Cashier redemption page (touch-optimised for POS/iPad).
// Requires `can_redeem_coupons`.
import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { ScanLine, Check, X, AlertTriangle, Loader2, RefreshCw,
                  Sparkles, Undo2 } from "lucide-react";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function MerchantCashier() {
  const { merchant, light } = useMerchant();
  const [code, setCode] = useState("");
  const [scanning, setScanning] = useState(false);
  const [redeeming, setRedeeming] = useState(false);
  const [preview, setPreview] = useState(null);      // scan result if ok:true
  const [error, setError] = useState(null);              // scan result if ok:false OR http error
  const [today, setToday] = useState({ count: 0, list: [] });
  const [giftCardAmount, setGiftCardAmount] = useState("");
  const inputRef = useRef(null);

  const loadToday = async () => {
    try {
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/cashier/redemptions/today`,
        { withCredentials: true });
      setToday(data);
    } catch (e) {
      // silent
    }
  };
  useEffect(() => { if (merchant) loadToday(); }, [merchant]);

  useEffect(() => {
    // Keep the input focused so the barcode scanner or keyboard can type
    if (inputRef.current && !preview && !error) inputRef.current.focus();
  }, [preview, error]);

  const handleScan = async () => {
    const v = code.trim().toUpperCase();
    if (!v) return;
    setScanning(true); setError(null); setPreview(null);
    try {
      // Phase MER.3 — use scan-any which auto-routes by code prefix
      // (BIGFM-GC-* → gift card, BIGFM-PM-* → prepaid meal, else coupon).
      const { data } = await axios.post(
        `${API}/merchant/${merchant.merchant_id}/cashier/scan-any`,
        { code: v }, { withCredentials: true });
      if (data.ok) setPreview(data);
      else setError(data);
    } catch (e) {
      setError({ ok: false, reason: e?.response?.data?.detail?.detail
                                                                || e?.response?.data?.detail
                                                                || e.message });
    } finally { setScanning(false); }
  };

  const handleRedeem = async () => {
    if (!preview) return;
    setRedeeming(true);
    try {
      let data;
      if (preview.type === "gift_card") {
        // Redeem the full remaining balance by default (cashier-optimised default)
        const amt = giftCardAmount || preview.current_balance_cents;
        const resp = await axios.post(
          `${API}/merchant/${merchant.merchant_id}/cashier/redeem-gift-card`,
          { code: preview.code, amount_cents_to_use: Number(amt) },
          { withCredentials: true });
        data = resp.data;
        toast.success(`Redeemed ${(Number(amt)/100).toFixed(2)} ${preview.currency || "AED"} from gift card`);
      } else if (preview.type === "prepaid_meal") {
        const resp = await axios.post(
          `${API}/merchant/${merchant.merchant_id}/cashier/redeem-meal`,
          { code: preview.code, count: 1 }, { withCredentials: true });
        data = resp.data;
        toast.success(`Redeemed 1 meal · ${data.remaining_meals} remaining`);
      } else {
        const resp = await axios.post(
          `${API}/merchant/${merchant.merchant_id}/cashier/redeem`,
          { coupon_id: preview.coupon_id }, { withCredentials: true });
        data = resp.data;
        toast.success(`Redeemed · ${data.offer_title || preview.offer_title}`);
      }
      setCode(""); setPreview(null); setError(null); setGiftCardAmount("");
      await loadToday();
      setTimeout(() => inputRef.current?.focus(), 100);
    } catch (e) {
      const d = e?.response?.data?.detail;
      setError({ ok: false, reason: d?.code || d?.detail || e.message });
    } finally { setRedeeming(false); }
  };

  const reset = () => {
    setCode(""); setPreview(null); setError(null); setGiftCardAmount("");
    setTimeout(() => inputRef.current?.focus(), 100);
  };

  const REASON_LABELS = {
    not_found:            "Coupon code not found",
    not_this_merchant: "This coupon belongs to a different merchant",
    already_redeemed: "Already redeemed",
    expired:                "This coupon has expired",
    revoked:                "This coupon has been revoked",
  };
  const errLabel = error?.reason
    ? (REASON_LABELS[error.reason]
          || (error.reason.startsWith("invalid_status_")
                ? `Status: ${error.reason.replace("invalid_status_", "")}`
                : error.reason))
    : "Something went wrong";

  return (
    <div className={light ? "min-h-screen"
                                          : "min-h-screen"}
              data-testid="merchant-cashier-page">
      <div className="max-w-2xl mx-auto p-6 lg:p-10 space-y-6">
        <div className="rounded-3xl p-5 flex items-center gap-4 flex-wrap"
                  style={{ background: "linear-gradient(120deg,#0b0f1e,#1a1038 60%,#2a1148)" }}
                  data-testid="merchant-cashier-pos-header">
          <div className="w-12 h-12 rounded-2xl grid place-items-center text-white shrink-0"
                    style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            <ScanLine size={22}/>
          </div>
          <div className="min-w-0">
            <div className="text-[10px] font-black uppercase tracking-[0.2em] text-purple-300">FUUSIC · Cashier</div>
            <h1 className="text-2xl font-black text-white truncate">{merchant?.name}</h1>
          </div>
          <div className="ml-auto inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-bold bg-white/10 text-cyan-200"
                    data-testid="merchant-cashier-today-count">
            <Sparkles size={12}/> {today.count} redeemed today
          </div>
        </div>

        {/* Main scan card */}
        {!preview && !error && (
          <div className={`rounded-3xl p-6 sm:p-10 ${
            light ? "bg-white border border-slate-100 shadow-sm"
                    : "bg-slate-900 border border-slate-800"
          }`} data-testid="merchant-cashier-scan-card">
            <div className={`text-center mb-6`}>
              <div className={`inline-flex w-16 h-16 rounded-2xl items-center justify-center ${
                light ? "bg-purple-100 text-purple-700"
                        : "bg-cyan-500/15 text-cyan-300"
              }`}>
                <ScanLine size={32}/>
              </div>
              <h2 className={`mt-4 text-2xl font-black ${
                light ? "text-slate-900" : "text-white"
              }`}>Scan or enter code</h2>
              <p className={`mt-1 text-sm ${
                light ? "text-slate-500" : "text-slate-500"
              }`}>Enter the customer&apos;s coupon code below.</p>
            </div>

            <input ref={inputRef}
                        type="text" autoFocus
                        value={code}
                        onChange={(e) => setCode(e.target.value.toUpperCase())}
                        onKeyDown={(e) => e.key === "Enter" && handleScan()}
                        placeholder="BIGFM-XXXXXX"
                        autoCapitalize="characters"
                        autoComplete="off"
                        data-testid="merchant-cashier-code-input"
                        className={`w-full text-center text-2xl sm:text-3xl font-black tracking-widest font-mono uppercase rounded-2xl px-6 py-5 outline-none ${
                          light ? "bg-slate-50 border-2 border-slate-200 focus:border-purple-500 text-slate-900"
                                  : "bg-slate-950 border-2 border-slate-800 focus:border-cyan-500 text-white"
                        }`}/>

            <button onClick={handleScan} disabled={scanning || !code.trim()}
                          data-testid="merchant-cashier-scan-btn"
                          className={`w-full mt-4 h-14 rounded-full text-base font-black text-white flex items-center justify-center gap-2 ${
                            !code.trim() || scanning ? "bg-slate-400 cursor-not-allowed" : ""
                          }`}
                          style={!scanning && code.trim()
                                              ? { background: "linear-gradient(135deg,#a855f7,#ec4899)"}
                                              : undefined}>
              {scanning ? <Loader2 className="animate-spin" size={18}/>
                                    : "Scan"}
            </button>
          </div>
        )}

        {/* Preview card — coupon / gift card / prepaid meal */}
        {preview && (
          <div className={`rounded-3xl overflow-hidden ${
            light ? "bg-white shadow-md border border-slate-100"
                    : "bg-slate-900 border border-slate-800"
          }`} data-testid="merchant-cashier-preview-card"
                data-type={preview.type || "coupon"}>
            <div className={`p-6 ${
              light ? "bg-gradient-to-br from-purple-50 to-pink-50"
                      : "bg-slate-950 border-b border-slate-800"
            }`}>
              <div className="flex items-center gap-3">
                <div className={`w-12 h-12 rounded-2xl flex items-center justify-center ${
                  light ? "bg-purple-600 text-white"
                          : "bg-cyan-500 text-slate-950"
                }`}>
                  <Check size={22} strokeWidth={3}/>
                </div>
                <div className="flex-1 min-w-0">
                  <div className={`text-[10px] font-black uppercase tracking-widest ${
                    light ? "text-purple-600" : "text-cyan-400"
                  }`}>
                    {preview.type === "gift_card" ? "Valid gift card"
                      : preview.type === "prepaid_meal" ? "Valid meal pack"
                      : "Valid coupon"}
                  </div>
                  <div className={`text-lg font-black truncate ${
                    light ? "text-slate-900" : "text-white"
                  }`} data-testid="merchant-cashier-offer-title">
                    {preview.type === "gift_card"
                      ? `Balance: ${((preview.current_balance_cents || 0)/100).toFixed(2)} ${preview.currency || "AED"}`
                      : preview.type === "prepaid_meal"
                      ? `${preview.remaining_meals} of ${preview.total_meals} meals remaining`
                      : (preview.offer_title || "Coupon")}
                  </div>
                </div>
              </div>
            </div>
            <div className="p-6 space-y-3">
              {preview.type === "gift_card" && (
                <>
                  <PRow light={light} label="Code"
                                value={<code className="text-xs">{preview.code}</code>}/>
                  <PRow light={light} label="Initial balance"
                                value={`${((preview.initial_balance_cents||0)/100).toFixed(2)} ${preview.currency||"AED"}`}/>
                  <div>
                    <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 ${
                      light ? "text-slate-500" : "text-slate-500"}`}>Amount to use (AED)</div>
                    <input type="number" step="0.01" min={0.01}
                                data-testid="merchant-cashier-gc-amount"
                                value={giftCardAmount}
                                onChange={e => setGiftCardAmount(
                                  e.target.value ? String(Math.round(parseFloat(e.target.value)*100)) : "")}
                                placeholder={((preview.current_balance_cents||0)/100).toFixed(2)}
                                className={`w-full h-11 rounded-xl px-3 text-sm outline-none ${
                                  light ? "bg-slate-50 border border-slate-200 focus:border-purple-500"
                                          : "bg-slate-950 border border-slate-800 focus:border-cyan-500 text-white"}`}/>
                    <div className={`mt-1 text-[10px] ${
                      light ? "text-slate-500" : "text-slate-500"}`}>
                      Default: use full balance
                    </div>
                  </div>
                </>
              )}
              {preview.type === "prepaid_meal" && (
                <>
                  <PRow light={light} label="Code"
                                value={<code className="text-xs">{preview.code}</code>}/>
                  <PRow light={light} label="Meal pack"
                                value={preview.sku_name || "—"}/>
                  <PRow light={light} label="Per-meal value"
                                value={`${((preview.per_meal_value_cents||0)/100).toFixed(2)} AED`}/>
                  <PRow light={light} label="Expires"
                                value={preview.expires_at ? new Date(preview.expires_at).toLocaleDateString() : "—"}/>
                </>
              )}
              {(!preview.type || preview.type === "coupon") && (
                <>
                  <PRow light={light} label="Discount"
                                value={preview.offer_discount_percent
                                                ? `${preview.offer_discount_percent}% off`
                                                : (preview.offer_type || "—")}/>
                  <PRow light={light} label="Merchant"
                                value={preview.business_name || merchant?.name}/>
                  <PRow light={light} label="Customer"
                                value={preview.customer_masked || "—"}/>
                  <PRow light={light} label="Code"
                                value={<code className="text-xs">{preview.redemption_code
                                                                                            || preview.coupon_id}</code>}/>
                  <PRow light={light} label="Expires"
                                value={preview.expires_at
                                                  ? new Date(preview.expires_at).toLocaleDateString()
                                                  : "—"}/>
                </>
              )}
            </div>
            <div className={`px-6 pb-6 grid grid-cols-2 gap-3`}>
              <button onClick={reset}
                            data-testid="merchant-cashier-cancel-btn"
                            className={`h-14 rounded-full font-bold text-sm ${
                              light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                      : "bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700"
                            }`}>
                Cancel
              </button>
              <button onClick={handleRedeem} disabled={redeeming}
                            data-testid="merchant-cashier-confirm-btn"
                            className={`h-14 rounded-full font-black text-sm text-white flex items-center justify-center gap-2 ${
                              redeeming ? "bg-slate-400" : ""
                            }`}
                            style={!redeeming
                                              ? { background: "linear-gradient(135deg,#10b981,#22c55e)"}
                                              : undefined}>
                {redeeming ? <Loader2 className="animate-spin" size={16}/>
                                    : (<><Check size={16}/>
                                            {preview.type === "gift_card" ? "Redeem gift card"
                                              : preview.type === "prepaid_meal" ? "Burn 1 meal"
                                              : "Confirm redeem"}</>)}
              </button>
            </div>
          </div>
        )}

        {/* Error card */}
        {error && (
          <div className={`rounded-3xl p-6 sm:p-8 text-center ${
            light ? "bg-white border border-rose-200 shadow-sm"
                    : "bg-slate-900 border border-rose-500/30"
          }`} data-testid="merchant-cashier-error-card">
            <div className={`inline-flex w-14 h-14 rounded-2xl items-center justify-center ${
              light ? "bg-rose-100 text-rose-700"
                      : "bg-rose-500/15 text-rose-300"
            }`}>
              <AlertTriangle size={26}/>
            </div>
            <h3 className={`mt-4 text-xl font-black ${
              light ? "text-rose-900" : "text-rose-200"
            }`} data-testid="merchant-cashier-error-label">{errLabel}</h3>
            <p className={`mt-1 text-xs ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>Code: <code>{code}</code></p>
            <button onClick={reset}
                          data-testid="merchant-cashier-error-reset"
                          className={`mt-6 h-12 px-6 rounded-full font-bold text-sm ${
                            light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                    : "bg-slate-800 text-slate-200 hover:bg-slate-700 border border-slate-700"
                          }`}>
              Try another code
            </button>
          </div>
        )}

        {/* Today's redemptions */}
        {today.list.length > 0 && (
          <div className={`rounded-2xl p-5 ${
            light ? "bg-white border border-slate-100 shadow-sm"
                    : "bg-slate-900 border border-slate-800"
          }`} data-testid="merchant-cashier-today-list">
            <div className="flex items-center justify-between mb-3">
              <h3 className={`text-sm font-black uppercase tracking-widest ${
                light ? "text-slate-700" : "text-slate-200"
              }`}>Today&apos;s redemptions</h3>
              <button onClick={loadToday}
                            className={`text-[10px] font-bold uppercase tracking-widest ${
                              light ? "text-slate-500 hover:text-slate-700"
                                      : "text-slate-500 hover:text-slate-300"
                            }`}><RefreshCw size={10} className="inline"/> Refresh</button>
            </div>
            <div className="space-y-1.5">
              {today.list.map((r) => (
                <div key={r.redemption_id}
                          data-testid={`merchant-cashier-today-row-${r.redemption_id}`}
                          className={`flex items-center gap-3 rounded-lg p-2 ${
                            light ? "hover:bg-slate-50" : "hover:bg-slate-950"
                          }`}>
                  <Check size={12} className={
                    light ? "text-emerald-600" : "text-emerald-400"}/>
                  <div className="flex-1 min-w-0">
                    <div className={`text-xs font-bold truncate ${
                      light ? "text-slate-800" : "text-slate-200"
                    }`}>{r.offer_title || r.redemption_code}</div>
                    <div className={`text-[10px] font-mono ${
                      light ? "text-slate-500" : "text-slate-500"
                    }`}>{r.redemption_code}</div>
                  </div>
                  <div className={`text-[10px] ${
                    light ? "text-slate-500" : "text-slate-500"
                  }`}>
                    {new Date(r.redeemed_at).toLocaleTimeString(undefined,
                          { hour: "2-digit", minute: "2-digit" })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function PRow({ light, label, value }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className={`text-[10px] font-bold uppercase tracking-widest ${
        light ? "text-slate-500" : "text-slate-500"
      }`}>{label}</span>
      <span className={`text-sm font-semibold ${
        light ? "text-slate-800" : "text-slate-200"
      }`}>{value}</span>
    </div>
  );
}
