// Phase I — Business Redemption Portal: redeem screen.
// Counter operator pastes the customer's coupon code, clicks Validate
// (no PIN required for validation), then enters the 4-digit PIN to
// commit the redemption.  The customer earns +20 BigCoin (PointsService
// award) on success.
import React, { useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { Loader2, ScanLine, CheckCircle2, XCircle, Ticket,
          KeyRound, RefreshCcw } from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";
import { API } from "@/AuthContext";

export default function BusinessRedeem() {
  const [code, setCode] = useState("");
  const [pin, setPin]   = useState("");
  const [check, setCheck] = useState(null);          // validation result
  const [done, setDone]    = useState(null);          // redemption result
  const [validating, setValidating]   = useState(false);
  const [redeeming, setRedeeming]      = useState(false);

  const reset = () => { setCode(""); setPin(""); setCheck(null); setDone(null); };

  const validate = async (e) => {
    e?.preventDefault?.();
    if (!code.trim()) return;
    setValidating(true); setDone(null); setCheck(null);
    try {
      const r = await axios.post(`${API}/business/coupons/validate`,
                                                  { code: code.trim() });
      setCheck(r.data);
      if (!r.data.valid) {
        toast.error(`Invalid · ${r.data.reason}`);
      } else {
        toast.success("Coupon is valid.");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Validation failed.");
    } finally { setValidating(false); }
  };

  const redeem = async () => {
    if (!check?.valid) return;
    if (!/^\d{4}$/.test(pin)) {
      toast.error("Enter the 4-digit PIN.");
      return;
    }
    setRedeeming(true);
    try {
      const r = await axios.post(`${API}/business/coupons/redeem`,
                                                  { code: code.trim(), terminal_pin: pin });
      setDone(r.data);
      toast.success(r.data?.idempotent
        ? "Already redeemed earlier — same receipt."
        : "Redemption confirmed ✓");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(detail === "bad_pin" ? "Wrong PIN."
                              : detail === "code_not_found" ? "Code not found."
                              : detail || "Redemption failed.");
    } finally { setRedeeming(false); }
  };

  return (
    <div data-testid="business-redeem-page"
            className="min-h-screen bg-bg-base px-4 py-8 pb-24
                                      max-w-2xl mx-auto space-y-5">
      <Toaster richColors theme="dark" position="bottom-right" />
      <header className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary flex items-center gap-2">
            <ScanLine size={11} /> Counter redemption
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl
                                  tracking-display-tight">
            Redeem a <span className="text-accent-gold">coupon</span>
          </h1>
        </div>
        <Link to="/business" className="text-xs text-accent-electric hover:underline"
                data-testid="business-redeem-back">
          ← Back to dashboard
        </Link>
      </header>

      <Card className="p-6 space-y-4" data-testid="business-redeem-form">
        <form onSubmit={validate}>
          <label className="block space-y-1">
            <span className="text-xs text-text-secondary flex items-center gap-1.5">
              <Ticket size={11} /> Coupon code
            </span>
            <div className="flex gap-2">
              <input type="text" value={code} required
                            placeholder="BIGFM-XXXXXXXX"
                            onChange={(e) => setCode(e.target.value.toUpperCase())}
                            data-testid="business-redeem-code"
                            className="flex-1 rounded-token-md bg-white/[0.04] border border-white/10
                                          px-3.5 py-2.5 text-sm font-mono tracking-wider uppercase
                                          focus:outline-none focus:border-accent-gold/60" />
              <Button type="submit" variant="outline"
                              disabled={validating || !code.trim()}
                              data-testid="business-redeem-validate">
                {validating
                  ? <Loader2 size={14} className="animate-spin" />
                  : "Validate"}
              </Button>
            </div>
          </label>
        </form>

        {check && !check.valid && (
          <div className="rounded-token-md border border-rose-400/30 bg-rose-400/10
                                  p-3 text-sm flex items-start gap-2 text-rose-200"
                  data-testid="business-redeem-invalid">
            <XCircle size={16} className="mt-0.5 flex-shrink-0" />
            <div className="flex-1">
              <div className="font-semibold capitalize">
                {check.reason?.replace(/_/g, " ")}
              </div>
              {check.intended_business_id && (
                <div className="text-xs mt-1 opacity-80">
                  This code is for a different business.
                </div>
              )}
            </div>
          </div>
        )}

        {check?.valid && !done && (
          <div className="rounded-token-md border border-emerald-400/30
                                  bg-emerald-400/[0.06] p-4 space-y-3"
                  data-testid="business-redeem-valid">
            <div className="flex items-start gap-2">
              <CheckCircle2 size={18} className="text-emerald-400 mt-0.5" />
              <div className="flex-1">
                <div className="text-sm text-emerald-200 font-semibold">
                  Valid · {check.offer_title || "Customer coupon"}
                </div>
                <div className="text-xs text-text-secondary flex flex-wrap
                                          gap-x-3 gap-y-1 mt-1">
                  <span>Customer · <span className="font-mono">
                      {check.customer_user_id_masked || "—"}</span></span>
                  {check.savings_value && (
                    <span>Value · <strong className="text-emerald-300">
                        ${check.savings_value}</strong></span>
                  )}
                </div>
              </div>
            </div>

            <div className="bg-bg-base/60 rounded-token-md p-3 space-y-2">
              <label className="block space-y-1">
                <span className="text-xs text-text-secondary flex items-center gap-1.5">
                  <KeyRound size={11} /> Terminal PIN
                </span>
                <input type="password" inputMode="numeric" maxLength={4}
                              pattern="\d{4}" value={pin}
                              onChange={(e) => setPin(e.target.value.replace(/\D/g, ""))}
                              placeholder="••••"
                              data-testid="business-redeem-pin"
                              className="w-full rounded-token-md bg-white/[0.04]
                                              border border-white/10 px-3.5 py-2.5 text-2xl
                                              tracking-[0.6em] text-center font-mono
                                              focus:outline-none focus:border-accent-gold/60" />
              </label>
              <Button type="button" variant="gold" className="w-full"
                              onClick={redeem} disabled={redeeming || pin.length !== 4}
                              data-testid="business-redeem-confirm">
                {redeeming
                  ? <><Loader2 size={14} className="animate-spin" /> Redeeming…</>
                  : "Confirm redemption"}
              </Button>
            </div>
          </div>
        )}

        {done && (
          <div className="rounded-token-md border border-accent-gold/40
                                  bg-accent-gold/[0.08] p-4 space-y-3 text-center"
                  data-testid="business-redeem-success">
            <CheckCircle2 size={28} className="text-accent-gold mx-auto" />
            <div className="font-display font-bold text-xl">
              {done.idempotent ? "Already redeemed" : "Redemption confirmed"}
            </div>
            <div className="text-xs text-text-secondary font-mono">
              {done.redemption_id}
            </div>
            {done.reward_awarded?.awarded && (
              <Chip tone="gold" data-testid="business-redeem-reward-chip">
                Customer earned +{done.reward_awarded.delta || 20} BigCoin
              </Chip>
            )}
            <Button variant="outline" onClick={reset} className="mx-auto"
                            data-testid="business-redeem-reset">
              <RefreshCcw size={14} /> Next coupon
            </Button>
          </div>
        )}
      </Card>

      <p className="text-xs text-text-secondary text-center max-w-md mx-auto">
        Tip — your PIN is hashed on the server, never visible to BigFM
        staff. Rotate it from the dashboard anytime.
      </p>
    </div>
  );
}
