// Open shop-counter screen to redeem a game-won coupon.
// No login required (demo-friendly): staff enters/scans the code, sees the
// prize + business, and marks it redeemed.
import React, { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Loader2, ScanLine, CheckCircle2, XCircle, Ticket, RefreshCcw, Gift, History, Receipt } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const FMT_USD = (c) => `$${((c || 0) / 100).toFixed(2)}`;
const DEFAULT_MERCHANT = "biz_fun_pizza_kitchen";

export default function ShopRedeem() {
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");
  const [info, setInfo] = useState(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [redeeming, setRedeeming] = useState(false);

  const [merchantId, setMerchantId] = useState(DEFAULT_MERCHANT);
  const [history, setHistory] = useState(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  const reset = () => { setCode(""); setPin(""); setInfo(null); setDone(false); };

  const loadHistory = async () => {
    if (!merchantId.trim()) { toast.error("Enter a merchant id"); return; }
    setHistoryLoading(true);
    try {
      const { data } = await axios.get(`${API}/games/redemptions/today`, {
        params: { merchant_id: merchantId.trim(), pin: pin.trim() || undefined },
      });
      setHistory(data);
    } catch (e) {
      const c = e?.response?.data?.detail?.code || e?.response?.data?.code;
      toast.error(c === "bad_pin" ? "Wrong staff PIN" : "Could not load history");
    } finally { setHistoryLoading(false); }
  };

  const lookup = async (e) => {
    e?.preventDefault?.();
    if (!code.trim()) return;
    setLoading(true); setInfo(null); setDone(false);
    try {
      const { data } = await axios.get(
        `${API}/games/coupon/lookup?code=${encodeURIComponent(code.trim())}`);
      if (!data.found) { setInfo({ notFound: true }); toast.error("Code not found"); }
      else { setInfo(data); if (data.status === "redeemed") setDone(true); }
    } catch { toast.error("Lookup failed"); }
    finally { setLoading(false); }
  };

  const redeem = async () => {
    setRedeeming(true);
    try {
      const { data } = await axios.post(`${API}/games/coupon/redeem`,
        { code: code.trim(), pin: pin.trim() || undefined });
      setDone(true);
      setInfo((p) => ({ ...(p || {}), status: "redeemed" }));
      toast.success(data.idempotent ? "Already redeemed earlier" : "Redeemed ✓");
    } catch (e) {
      const c = e?.response?.data?.detail?.code || e?.response?.data?.code;
      toast.error(c === "expired" ? "Coupon expired"
        : c === "already_redeemed" ? "Already redeemed"
        : c === "bad_pin" ? "Wrong staff PIN"
        : c === "code_not_found" ? "Code not found" : "Redemption failed");
    } finally { setRedeeming(false); }
  };

  const valid = info && !info.notFound;
  const isGift = valid && (info.prize_title || "").toLowerCase().includes("gift");

  return (
    <div data-testid="shop-redeem-page"
              className="min-h-screen bg-slate-950 text-slate-100 px-4 py-8
                                max-w-lg mx-auto space-y-5">
      <Toaster richColors theme="dark" position="bottom-right" />
      <header className="space-y-1">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 flex items-center gap-2">
          <ScanLine size={11} /> Counter redemption
        </div>
        <h1 className="font-black text-3xl tracking-tight">
          Redeem a <span className="text-amber-400">winning code</span>
        </h1>
        <p className="text-sm text-slate-400">
          Enter the code the customer won in a game to mark it used.
        </p>
      </header>

      <div className="rounded-3xl bg-slate-900 border border-slate-800 p-6 space-y-4">
        <form onSubmit={lookup}>
          <label className="block space-y-1">
            <span className="text-xs text-slate-400 flex items-center gap-1.5">
              <Ticket size={11} /> Coupon code
            </span>
            <div className="flex gap-2">
              <input type="text" value={code} required placeholder="BIGFM-XXXXXX"
                            onChange={(e) => setCode(e.target.value.toUpperCase())}
                            data-testid="shop-redeem-code"
                            className="flex-1 rounded-xl bg-white/[0.04] border border-white/10
                                          px-3.5 py-2.5 text-sm font-mono tracking-wider uppercase
                                          focus:outline-none focus:border-amber-400/60" />
              <button type="submit" disabled={loading || !code.trim()}
                            data-testid="shop-redeem-lookup"
                            className="px-4 rounded-xl bg-slate-800 text-slate-100 text-sm font-bold
                                          hover:bg-slate-700 disabled:opacity-50">
                {loading ? <Loader2 size={14} className="animate-spin" /> : "Check"}
              </button>
            </div>
          </label>
        </form>

        {info?.notFound && (
          <div className="rounded-xl border border-rose-400/30 bg-rose-400/10 p-3 text-sm
                                  flex items-center gap-2 text-rose-200"
                  data-testid="shop-redeem-notfound">
            <XCircle size={16} /> Code not found — check and try again.
          </div>
        )}

        {valid && (
          <div className={`rounded-xl border p-4 space-y-3 ${
            done ? "border-slate-700 bg-slate-800/40"
                    : "border-emerald-400/30 bg-emerald-400/[0.06]"}`}
                  data-testid="shop-redeem-detail">
            <div className="flex items-start gap-3">
              <span className="w-11 h-11 rounded-2xl grid place-items-center flex-shrink-0"
                          style={{ background: isGift ? "#facc1522" : "#10b98122",
                                          color: isGift ? "#facc15" : "#10b981" }}>
                {isGift ? <Gift size={20} /> : <Ticket size={20} />}
              </span>
              <div className="min-w-0 flex-1">
                <div className="text-base font-black text-white"
                          data-testid="shop-redeem-prize">{info.prize_title}</div>
                <div className="text-xs text-slate-400 mt-0.5">
                  {info.business_name || "Fun Pizza Kitchen"}
                </div>
                <div className={`mt-1 inline-block text-[10px] font-black uppercase tracking-widest
                                          px-2 py-0.5 rounded-full ${
                  done ? "bg-slate-700 text-slate-300"
                          : "bg-emerald-500/15 text-emerald-300"}`}
                          data-testid="shop-redeem-status">
                  {done ? "Redeemed" : "Valid · ready to redeem"}
                </div>
              </div>
            </div>

            {!done ? (
              <>
                {info.pin_required && (
                  <label className="block space-y-1" data-testid="shop-redeem-pin-wrap">
                    <span className="text-xs text-slate-400">Staff PIN</span>
                    <input type="password" inputMode="numeric" value={pin}
                                  onChange={(e) => setPin(e.target.value)}
                                  placeholder="••••" maxLength={8}
                                  data-testid="shop-redeem-pin"
                                  className="w-full rounded-xl bg-white/[0.04] border border-white/10
                                                px-3.5 py-2.5 text-sm tracking-[0.3em] text-center
                                                focus:outline-none focus:border-amber-400/60" />
                  </label>
                )}
                <button type="button" onClick={redeem} disabled={redeeming}
                              data-testid="shop-redeem-confirm"
                              className="w-full h-11 rounded-full text-sm font-black text-slate-950
                                            bg-amber-400 hover:bg-amber-300 disabled:opacity-60">
                  {redeeming
                    ? <><Loader2 size={14} className="animate-spin inline mr-1" /> Redeeming…</>
                    : "Mark as redeemed"}
                </button>
              </>
            ) : (
              <div className="flex items-center gap-2 text-amber-300 text-sm font-bold"
                        data-testid="shop-redeem-success">
                <CheckCircle2 size={18} /> Done — enjoy the pizza!
              </div>
            )}
          </div>
        )}

        {(info || done) && (
          <button type="button" onClick={reset} data-testid="shop-redeem-reset"
                        className="w-full h-10 rounded-full text-xs font-bold bg-slate-800
                                      text-slate-200 hover:bg-slate-700 inline-flex items-center
                                      justify-center gap-1">
            <RefreshCcw size={13} /> Next code
          </button>
        )}
      </div>

      {/* ── Today's redemptions (end-of-day totals) ── */}
      <div className="rounded-3xl bg-slate-900 border border-slate-800 p-6 space-y-4"
                data-testid="shop-redeem-history-card">
        <div className="flex items-center justify-between gap-2">
          <div className="text-[10px] font-mono uppercase tracking-widest text-slate-400 flex items-center gap-2">
            <History size={12} /> Today's redemptions
          </div>
          <button type="button" onClick={loadHistory} disabled={historyLoading}
                        data-testid="shop-redeem-history-load"
                        className="px-3 h-8 rounded-full bg-slate-800 text-slate-100 text-xs font-bold
                                      hover:bg-slate-700 disabled:opacity-50 inline-flex items-center gap-1">
            {historyLoading
              ? <Loader2 size={12} className="animate-spin" />
              : <><RefreshCcw size={12} /> Refresh</>}
          </button>
        </div>

        <label className="block space-y-1">
          <span className="text-xs text-slate-400">Merchant</span>
          <input type="text" value={merchantId}
                        onChange={(e) => setMerchantId(e.target.value)}
                        data-testid="shop-redeem-history-merchant"
                        placeholder="biz_fun_pizza_kitchen"
                        className="w-full rounded-xl bg-white/[0.04] border border-white/10
                                      px-3.5 py-2.5 text-xs font-mono
                                      focus:outline-none focus:border-amber-400/60" />
          <span className="text-[10px] text-slate-500">
            Uses the staff PIN above · defaults to Fun Pizza Kitchen.
          </span>
        </label>

        <label className="block space-y-1">
          <span className="text-xs text-slate-400">Staff PIN</span>
          <input type="password" inputMode="numeric" value={pin} maxLength={8}
                        onChange={(e) => setPin(e.target.value)}
                        data-testid="shop-redeem-history-pin"
                        placeholder="••••"
                        className="w-full rounded-xl bg-white/[0.04] border border-white/10
                                      px-3.5 py-2.5 text-sm tracking-[0.3em] text-center
                                      focus:outline-none focus:border-amber-400/60" />
        </label>

        {history && (
          <div className="space-y-4" data-testid="shop-redeem-history">
            {/* Totals */}
            <div className="grid grid-cols-3 gap-2">
              <div className="rounded-xl bg-slate-800/60 p-3 text-center" data-testid="history-total-coupons">
                <div className="text-2xl font-black text-emerald-300">{history.totals.coupons_count}</div>
                <div className="text-[10px] text-slate-400 uppercase tracking-widest">Coupons</div>
              </div>
              <div className="rounded-xl bg-slate-800/60 p-3 text-center" data-testid="history-total-giftcards">
                <div className="text-2xl font-black text-amber-300">{history.totals.gift_cards_count}</div>
                <div className="text-[10px] text-slate-400 uppercase tracking-widest">GC spends</div>
              </div>
              <div className="rounded-xl bg-slate-800/60 p-3 text-center" data-testid="history-total-spend">
                <div className="text-2xl font-black text-white">{FMT_USD(history.totals.gift_card_spend_cents)}</div>
                <div className="text-[10px] text-slate-400 uppercase tracking-widest">GC total</div>
              </div>
            </div>

            {/* Coupon list */}
            {history.coupons.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                  <Ticket size={12} /> Coupons redeemed
                </div>
                {history.coupons.map((c) => (
                  <div key={c.code} data-testid={`history-coupon-${c.code}`}
                            className="flex items-center gap-3 rounded-xl bg-slate-800/40 p-3">
                    <span className="w-8 h-8 rounded-lg grid place-items-center bg-emerald-400/10 text-emerald-300 flex-shrink-0">
                      <Ticket size={15} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-bold text-white truncate">{c.prize_title}</div>
                      <div className="text-[11px] text-slate-400">
                        {c.first_name} · <span className="font-mono">{c.code}</span>
                      </div>
                    </div>
                    <div className="text-xs text-slate-500 whitespace-nowrap">
                      {c.redeemed_at ? new Date(c.redeemed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Gift card spends */}
            {history.gift_cards.length > 0 && (
              <div className="space-y-2">
                <div className="text-xs font-bold text-slate-300 flex items-center gap-1.5">
                  <Gift size={12} /> Gift cards spent
                </div>
                {history.gift_cards.map((g, i) => (
                  <div key={`${g.code}-${i}`} data-testid={`history-gc-${g.code}`}
                            className="flex items-center gap-3 rounded-xl bg-slate-800/40 p-3">
                    <span className="w-8 h-8 rounded-lg grid place-items-center bg-amber-400/10 text-amber-300 flex-shrink-0">
                      <Gift size={15} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-bold text-white">{g.first_name}</div>
                      <div className="text-[11px] text-slate-400 font-mono">{g.code}</div>
                    </div>
                    <div className="text-sm font-black text-amber-300 whitespace-nowrap">
                      {FMT_USD(g.amount_cents)}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {history.coupons.length === 0 && history.gift_cards.length === 0 && (
              <div className="rounded-xl border border-slate-800 p-6 text-center text-sm text-slate-400"
                        data-testid="shop-redeem-history-empty">
                <Receipt size={22} className="mx-auto mb-2 text-slate-500" />
                Nothing redeemed yet today.
              </div>
            )}
          </div>
        )}
      </div>

      <Link to="/play" className="block text-center text-xs text-slate-500 hover:text-slate-300">
        ← Back to games
      </Link>
    </div>
  );
}
