// Phase R.1 — Redeem Coupon.  Fetches the coupon detail from
// /api/commerce/coupons/{id}, renders a QR of the coupon.code for cashier scan.
import React, { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import QRCode from "react-qr-code";
import { ArrowLeft, Sparkles, Ticket, Clock, MapPin } from "lucide-react";
import { API } from "@/AuthContext";
import { RLCard, RLButton, RLBadge } from "../DesignSystem";

export default function RedeemCouponRadioLife() {
  // See RestaurantDetail — overlay runs outside <Routes>, parse from pathname.
  const { pathname } = useLocation();
  const coupon_id = pathname.startsWith("/coupon/")
    ? decodeURIComponent(pathname.slice("/coupon/".length).split("/")[0])
    : "";
  const navigate = useNavigate();
  const [coupon, setCoupon] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/commerce/coupons/${coupon_id}`,
                                              { withCredentials: true });
        setCoupon(r.data || null);
      } catch (_) { setCoupon(null); }
      finally { setLoading(false); }
    })();
  }, [coupon_id]);

  const expiresAt = coupon?.expires_at ? new Date(coupon.expires_at) : null;
  const daysLeft = expiresAt ? Math.max(0,
    Math.round((expiresAt.getTime() - Date.now()) / 86_400_000)) : null;

  return (
    <div className="min-h-screen relative overflow-hidden"
              data-testid="rl-redeem-page">
      <div className="absolute inset-0 pointer-events-none"
                style={{ background: "linear-gradient(180deg, #A020F0 0%, #EC4899 50%, #FAF7FE 100%)" }} />
      <div className="relative px-5 pt-4 pb-24">
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => navigate(-1)}
            data-testid="rl-redeem-back"
            className="w-10 h-10 rounded-full bg-white/25 backdrop-blur
                                text-white flex items-center justify-center
                                hover:bg-white/40 transition-colors">
            <ArrowLeft size={18} />
          </button>
          <div className="text-white/85 text-[11px] font-semibold uppercase tracking-widest">
            Redeem coupon
          </div>
          <div className="w-10 h-10" />
        </div>

        {loading ? (
          <RLCard className="mt-8 p-8 text-center">
            <div className="text-slate-500 text-sm">Loading your coupon…</div>
          </RLCard>
        ) : !coupon ? (
          <RLCard className="mt-8 p-8 text-center">
            <Ticket size={28} className="text-purple-300 mx-auto mb-3" />
            <div className="font-semibold text-slate-900">Coupon not found</div>
            <div className="text-sm text-slate-500 mt-1">
              This coupon may have expired or already been used.
            </div>
            <RLButton className="mt-4" onClick={() => navigate("/wallet")}>
              Back to Wallet
            </RLButton>
          </RLCard>
        ) : (
          <>
            {/* Offer summary */}
            <div className="text-center mt-6">
              <div className="text-white font-black text-2xl tracking-tight leading-tight">
                {coupon.offer_title || "Saved coupon"}
              </div>
              {coupon.business_name && (
                <div className="text-white/85 text-sm mt-2 max-w-xs mx-auto">
                  {coupon.business_name}
                </div>
              )}
              {daysLeft !== null && (
                <div className="mt-3 inline-flex items-center gap-1.5 px-3 py-1
                                            rounded-full bg-white/25 backdrop-blur text-white
                                            text-[11px] font-semibold">
                  <Clock size={11} />
                  {daysLeft === 0 ? "Expires today" : `${daysLeft} days left`}
                </div>
              )}
            </div>

            {/* QR card */}
            <RLCard className="mt-7 p-6 text-center" data-testid="rl-qr-card">
              <div className="bg-white p-4 rounded-2xl w-fit mx-auto">
                <QRCode value={coupon.redemption_code || coupon.coupon_id}
                              size={180}
                              level="M" />
              </div>
              <div className="mt-4 text-[11px] uppercase tracking-widest
                                        text-slate-500 font-semibold">
                Show this to the cashier
              </div>
              <div className="mt-1 font-mono font-bold text-slate-900 text-lg tracking-wider"
                        data-testid="rl-coupon-code">
                {coupon.redemption_code || coupon.coupon_id}
              </div>
            </RLCard>

            {/* Instructions */}
            <RLCard className="mt-4 p-5" data-testid="rl-redeem-instructions">
              <div className="flex items-center gap-2 text-purple-700 font-bold text-sm mb-3">
                <Sparkles size={15} />
                Redemption instructions
              </div>
              <ul className="space-y-2 text-sm text-slate-700">
                <li className="flex gap-2">
                  <span className="text-purple-500 font-bold">1.</span>
                  Show this QR to the cashier at checkout.
                </li>
                <li className="flex gap-2">
                  <span className="text-purple-500 font-bold">2.</span>
                  They&apos;ll scan or enter the code shown below the QR.
                </li>
                <li className="flex gap-2">
                  <span className="text-purple-500 font-bold">3.</span>
                  Discount applies to your bill instantly.
                </li>
                <li className="flex gap-2">
                  <span className="text-purple-500 font-bold">4.</span>
                  You earn +20 bonus points after successful redemption.
                </li>
              </ul>
            </RLCard>

            {/* Redeem CTA */}
            <div className="mt-5">
              <RLButton
                size="lg"
                className="w-full"
                data-testid="rl-redeem-now-btn"
                onClick={() => alert("Ready — hand this to the cashier for redemption.")}>
                <Ticket size={16} />
                Redeem now
              </RLButton>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
