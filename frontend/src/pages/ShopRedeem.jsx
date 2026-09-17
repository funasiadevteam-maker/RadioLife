// Open shop-counter screen to redeem a game-won coupon.
// No login required (demo-friendly): staff enters/scans the code, sees the
// prize + business, and marks it redeemed.
import React, { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Loader2, ScanLine, CheckCircle2, XCircle, Ticket, RefreshCcw, Gift } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function ShopRedeem() {
  const [code, setCode] = useState("");
  const [pin, setPin] = useState("");
  const [info, setInfo] = useState(null);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [redeeming, setRedeeming] = useState(false);

  const reset = () => { setCode(""); setPin(""); setInfo(null); setDone(false); };

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

      <Link to="/play" className="block text-center text-xs text-slate-500 hover:text-slate-300">
        ← Back to games
      </Link>
    </div>
  );
}
