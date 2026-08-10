// RadioLife Merchant Subscription — Starter $29 / Pro $99 (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Check, CheckCircle2 } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(0)}`;

export default function MerchantSubscribeRadioLife() {
  const navigate = useNavigate();
  const [plans, setPlans] = useState([]);
  const [current, setCurrent] = useState(null);
  const [active, setActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = useCallback(async () => {
    try {
      const [p, m] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/subscription/plans`),
        axios.get(`${API}/merchant/marketplace/subscription`),
      ]);
      setPlans(p.data.items || []); setCurrent(m.data.subscription); setActive(!!m.data.active);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const subscribe = async (planId) => {
    setBusyId(planId);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/subscription/checkout`, { plan_id: planId, origin_url: window.location.origin });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
    } catch { setBusyId(null); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  return (
    <div className="pb-24" data-testid="rl-merchant-subscribe-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="subscribe-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Merchant Plans</h1>
      </div>

      <div className="px-4 space-y-4">
        {active && (
          <div className="flex items-center gap-2 bg-green-50 border border-green-300 rounded-xl p-3" data-testid="subscribe-active">
            <CheckCircle2 size={20} className="text-green-600" />
            <span className="text-sm font-bold text-slate-800">Your {current?.plan_id || ""} plan is active — you're live on the Shop.</span>
          </div>
        )}
        <p className="text-sm text-slate-500">List your business, reward customers with BigPoints, and accept pickup orders. Cancel anytime.</p>

        {plans.map((p) => {
          const isCurrent = active && current?.plan_id === p.plan_id;
          return (
            <div key={p.plan_id} className={`bg-white rounded-2xl p-5 ${p.plan_id === "pro" ? "border-2 border-orange-600" : "border border-slate-200"}`} data-testid={`plan-${p.plan_id}`}>
              <div className="flex items-center gap-2">
                <div className="text-xl font-black text-slate-900">{p.name}</div>
                {p.plan_id === "pro" && <span className="bg-orange-600 text-white text-[9px] font-black tracking-wider px-2 py-0.5 rounded-full">POPULAR</span>}
              </div>
              <div className="text-3xl font-black text-slate-900 mt-1">{money(p.price_cents)}<span className="text-base font-bold text-slate-400">/{p.interval}</span></div>
              <div className="mt-3 space-y-1.5">
                {(p.features || []).map((f, i) => (
                  <div key={i} className="flex items-center gap-2 text-sm text-slate-600 font-semibold"><Check size={15} className="text-green-600" />{f}</div>
                ))}
              </div>
              <button onClick={() => subscribe(p.plan_id)} disabled={!!busyId || isCurrent} data-testid={`subscribe-${p.plan_id}`}
                className="mt-4 w-full bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-50">
                {busyId === p.plan_id ? "Redirecting…" : isCurrent ? "Current Plan" : `Subscribe · ${money(p.price_cents)}/mo`}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
