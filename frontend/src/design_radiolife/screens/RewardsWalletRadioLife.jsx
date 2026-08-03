// Phase R.1 — Rewards Wallet.  Points card + active coupons list.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Ticket, Sparkles } from "lucide-react";
import { API } from "@/AuthContext";
import { RLCard, extractTier } from "../DesignSystem";
import PointsBalanceCard from "../components/PointsBalanceCard";
import CouponCard from "../components/CouponCard";

export default function RewardsWalletRadioLife() {
  const [balance, setBalance] = useState(0);
  const [tier, setTier] = useState({ name: "Listener", nextName: "Regular",
                                                progress: 0, threshold: 100, points: 0 });
  const [coupons, setCoupons] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const [ptsR, psR, cpR] = await Promise.allSettled([
          axios.get(`${API}/me/points`, { withCredentials: true }),
          axios.get(`${API}/passport/me`, { withCredentials: true }),
          axios.get(`${API}/commerce/coupons/me?status=saved&limit=50`,
                          { withCredentials: true }),
        ]);
        if (ptsR.status === "fulfilled") setBalance(ptsR.value.data?.balance || 0);
        if (psR.status === "fulfilled") setTier(extractTier(psR.value.data));
        if (cpR.status === "fulfilled") {
          setCoupons(cpR.value.data?.items || []);
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="px-4 pt-6 pb-6 space-y-5" data-testid="rl-rewards-page">
      <header>
        <h1 className="text-2xl font-black tracking-tight text-slate-900">
          Rewards Wallet
        </h1>
        <p className="text-slate-500 text-sm mt-1">
          Earn on every listen · spend at 100+ spots
        </p>
      </header>

      <PointsBalanceCard balance={balance} tier={tier} showViewWallet={false} />

      <section>
        <h2 className="text-lg font-black tracking-tight text-slate-900 mb-3">
          Active coupons
        </h2>
        {loading ? (
          <RLCard className="p-4 text-sm text-slate-500">Loading your wallet…</RLCard>
        ) : coupons.length === 0 ? (
          <RLCard className="p-8 text-center" data-testid="rl-coupons-empty">
            <Ticket size={28} className="text-purple-300 mx-auto mb-3" />
            <div className="font-semibold text-slate-900">No coupons yet</div>
            <div className="text-sm text-slate-500 mt-1">
              Save deals from Discover or Commute Mode to see them here.
            </div>
          </RLCard>
        ) : (
          <div className="space-y-3" data-testid="rl-coupons-list">
            {coupons.map((c) => (
              <CouponCard
                key={c.coupon_id}
                coupon={{
                  coupon_id: c.coupon_id,
                  code: c.redemption_code || c.coupon_id.slice(-6).toUpperCase(),
                  expires_at: c.expires_at,
                  title: c.offer_title,
                  business_name: c.business_name,
                }}
                offer={{ offer_id: c.offer_id,
                            title: c.offer_title,
                            discount_percent: c.offer_discount_percent }}
                business={{ name: c.business_name }} />
            ))}
          </div>
        )}
      </section>

      <RLCard className="p-4 flex items-center gap-3"
                    data-testid="rl-rewards-cta">
        <div className="w-10 h-10 rounded-xl bg-purple-100 text-purple-700
                                flex items-center justify-center flex-shrink-0">
          <Sparkles size={18} />
        </div>
        <div className="flex-1 text-sm text-slate-700">
          Save deals during your commute or from Discover — they land here
          instantly, ready to scan.
        </div>
      </RLCard>
    </div>
  );
}
