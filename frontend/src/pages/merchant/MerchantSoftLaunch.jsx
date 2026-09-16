// Soft-launch — Merchant "6 months free" claim + Preview As Customer.
// Shown to businesses during Business Setup Mode. Claiming waives the monthly
// subscription fee for the offer window (per-sale commission still applies)
// and unlocks the protected preview so the merchant can test-drive the app.
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { Store, Check, ArrowRight, Eye, Sparkles } from "lucide-react";
import { useLaunchStore } from "@/hooks/useLaunchStatus";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const cfg = { withCredentials: true };

export default function MerchantSoftLaunch() {
  const navigate = useNavigate();
  const [offer, setOffer] = useState(null);
  const [busy, setBusy] = useState(false);
  const refresh = useLaunchStore((s) => s.refresh);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/merchant/soft-launch/offer`, cfg); setOffer(r.data); }
    catch (_e) { setOffer({ error: true }); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const claim = useCallback(async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/merchant/soft-launch/claim`, {}, cfg);
      await load();
      await refresh(); // now a business → gets preview bypass
    } catch (_e) { /* ignore */ } finally { setBusy(false); }
  }, [load, refresh]);

  const months = offer?.offer_months || 6;
  const claimed = !!offer?.claimed;
  const claim0 = offer?.claim || {};

  return (
    <div data-testid="merchant-soft-launch" className="nlv2 min-h-screen text-white px-4 sm:px-8 py-10">
      <div className="max-w-2xl mx-auto">
        <div className="inline-flex items-center gap-2 text-[11px] font-mono uppercase tracking-widest px-3 py-1 rounded-full nlv2-chip" style={{ color: "#c4b5fd" }}>
          <Sparkles size={13} /> Soft launch
        </div>
        <h1 className="mt-4 text-3xl sm:text-4xl font-black leading-tight">
          <span className="nlv2-grad">{months} months free</span> on RadioLife
        </h1>
        <p className="mt-3 text-base" style={{ color: "#a8b0cc" }}>
          Get your storefront ready before we open to listeners. No monthly subscription fee for {months} months —
          you only pay a small commission when you actually sell.
        </p>

        <div className="mt-8 nlv2-glass rounded-2xl p-6" data-testid="merchant-offer-card">
          <div className="flex items-start gap-3">
            <span className="w-11 h-11 rounded-2xl grid place-items-center shrink-0" style={{ background: "linear-gradient(135deg,#f59e0b,#f5c563)" }}>
              <Store size={20} className="text-black" />
            </span>
            <div className="flex-1">
              <div className="font-black text-lg">Business Soft-Launch Offer</div>
              <div className="mt-1 text-sm" style={{ color: "#97a3c2" }}>{offer?.commission_note}</div>
            </div>
          </div>

          {claimed ? (
            <div className="mt-6" data-testid="merchant-offer-claimed">
              <div className="rounded-xl bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 px-4 py-3 flex items-center gap-2 text-sm font-semibold">
                <Check size={18} /> Claimed — free until {claim0.free_until ? new Date(claim0.free_until).toLocaleDateString() : "soon"}
              </div>
              <button type="button" data-testid="merchant-preview-as-customer"
                onClick={() => navigate("/preview")}
                className="mt-4 w-full h-12 rounded-full font-bold text-sm inline-flex items-center justify-center gap-2 text-white"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                <Eye size={16} /> Preview as customer <ArrowRight size={16} />
              </button>
              <button type="button" data-testid="merchant-goto-dashboard"
                onClick={() => navigate("/merchant/dashboard")}
                className="mt-3 w-full h-11 rounded-full font-semibold text-sm bg-white/10 hover:bg-white/20">
                Go to merchant dashboard
              </button>
            </div>
          ) : (
            <div className="mt-6">
              <button type="button" disabled={busy} onClick={claim} data-testid="merchant-claim-btn"
                className="w-full h-12 rounded-full font-bold text-sm inline-flex items-center justify-center gap-2 text-black disabled:opacity-60"
                style={{ background: "linear-gradient(135deg,#f59e0b,#f5c563)" }}>
                {busy ? "Claiming…" : `Claim ${months} months free`} <ArrowRight size={16} />
              </button>
              {!offer?.has_storefront && (
                <p className="mt-3 text-xs text-center" style={{ color: "#8b96b8" }}>
                  After claiming, finish setting up your storefront to start listing products.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
