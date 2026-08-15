// Merchant "Promote my shop" (Phase F) — buy a tiered promotion (Stripe hosted
// Checkout) that boosts the shop higher in Shop search + the Promoted-near-you
// rail. Goes live only after admin approval.
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Rocket, CheckCircle2, Clock, XCircle, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

const STATUS_UI = {
  pending_payment: { label: "Awaiting payment", cls: "bg-slate-100 text-slate-600", Icon: Clock },
  pending_review: { label: "In review", cls: "bg-amber-100 text-amber-700", Icon: Clock },
  active: { label: "Live", cls: "bg-green-100 text-green-700", Icon: CheckCircle2 },
  rejected: { label: "Rejected", cls: "bg-red-100 text-red-700", Icon: XCircle },
  expired: { label: "Expired", cls: "bg-slate-100 text-slate-500", Icon: Clock },
};

export default function MerchantPromoteRadioLife() {
  const navigate = useNavigate();
  const [tiers, setTiers] = useState([]);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);

  const load = useCallback(async () => {
    try {
      const [t, m] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/promotion/tiers`),
        axios.get(`${API}/merchant/marketplace/promotion`),
      ]);
      setTiers(t.data.tiers || []);
      setData(m.data);
      // Reconcile any promotion that came back from Stripe still marked unpaid.
      const pend = (m.data.items || []).find((p) => p.status === "pending_payment");
      if (pend) {
        const st = await axios.get(`${API}/merchant/marketplace/promotion/${pend.promotion_id}/status`);
        if (st.data.status !== "pending_payment") {
          const m2 = await axios.get(`${API}/merchant/marketplace/promotion`);
          setData(m2.data);
        }
      }
    } catch {
      setData({ no_profile: true });
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const buy = async (tier) => {
    setBusy(tier);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/promotion/checkout`,
        { tier, origin_url: window.location.origin });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "stripe_unconfigured"
        ? "Payments not configured" : "Could not start checkout");
    } finally { setBusy(null); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (data?.no_profile) return (
    <div className="px-4 pt-16 text-center" data-testid="promote-no-profile">
      <Rocket size={44} className="mx-auto text-orange-500" />
      <p className="mt-3 font-semibold text-slate-700">You don&apos;t have a business yet.</p>
      <button onClick={() => navigate("/sell")} className="mt-4 bg-orange-600 text-white font-black rounded-full px-6 py-3">Sell on RadioLife</button>
    </div>
  );

  const active = data?.active;
  const history = (data?.items || []).filter((p) => !active || p.promotion_id !== active.promotion_id);

  return (
    <div className="pb-24" data-testid="rl-merchant-promote-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="promote-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Promote my Shop</h1>
      </div>

      <div className="px-4 space-y-4">
        <p className="text-sm text-slate-500">Boost <b>{data?.public_name}</b> to the top of Shop search and the &quot;Promoted near you&quot; rail. Promotions go live once our team approves them.</p>

        {active && (
          <div className="bg-green-50 border border-green-200 rounded-2xl p-4" data-testid="promote-active">
            <div className="flex items-center gap-2 font-black text-green-700"><CheckCircle2 size={18} />You&apos;re promoted — {active.name}</div>
            <div className="text-xs text-green-700/80 mt-1">Live until {new Date(active.expires_at).toLocaleDateString()}.</div>
          </div>
        )}

        <div className="space-y-3">
          {tiers.map((t) => {
            const isActiveTier = active && active.tier === t.tier;
            return (
              <div key={t.tier} className={`bg-white border rounded-2xl p-4 ${t.tier === "boost_14" ? "border-orange-400" : "border-slate-200"}`} data-testid={`promote-tier-${t.tier}`}>
                <div className="flex items-center justify-between">
                  <div className="font-black text-slate-900 flex items-center gap-1.5">
                    <TrendingUp size={16} className="text-orange-600" />{t.name}
                    {t.tier === "boost_14" && <span className="text-[10px] font-black text-white bg-orange-600 px-2 py-0.5 rounded-full">POPULAR</span>}
                  </div>
                  <div className="text-lg font-black text-slate-900">{money(t.price_cents)}</div>
                </div>
                <div className="text-xs text-slate-500 mt-1">{t.blurb}</div>
                <button onClick={() => buy(t.tier)} disabled={!!busy || isActiveTier}
                  data-testid={`promote-buy-${t.tier}`}
                  className={`mt-3 w-full font-black rounded-full py-2.5 text-sm transition-colors ${isActiveTier ? "bg-slate-100 text-slate-400" : "bg-orange-600 text-white hover:bg-orange-700"}`}>
                  {isActiveTier ? "Current promotion" : busy === t.tier ? "Starting…" : `Promote for ${t.days} days`}
                </button>
              </div>
            );
          })}
        </div>

        {history.length > 0 && (
          <div>
            <h3 className="text-sm font-black text-slate-900 mt-2 mb-2">History</h3>
            <div className="space-y-2">
              {history.map((p) => {
                const ui = STATUS_UI[p.status] || STATUS_UI.expired;
                return (
                  <div key={p.promotion_id} className="flex items-center justify-between bg-white border border-slate-200 rounded-xl p-3" data-testid={`promote-history-${p.promotion_id}`}>
                    <div>
                      <div className="font-bold text-slate-800 text-sm">{p.name} · {money(p.price_cents)}</div>
                      {p.admin_note && <div className="text-xs text-red-500 mt-0.5">{p.admin_note}</div>}
                    </div>
                    <span className={`text-[11px] font-black px-2.5 py-1 rounded-full flex items-center gap-1 ${ui.cls}`}><ui.Icon size={12} />{ui.label}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
