// RadioLife Merchant Dashboard — orders, BigPoints, happy hour (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, ArrowRight, Lock, Zap, CheckCircle2, Utensils, CreditCard } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const NEXT = { accepted: "preparing", preparing: "ready", ready: "picked_up" };
const NEXT_LABEL = { accepted: "Start Preparing", preparing: "Mark Ready", ready: "Mark Picked Up" };

export default function MerchantDashRadioLife() {
  const navigate = useNavigate();
  const [dash, setDash] = useState(null);
  const [orders, setOrders] = useState([]);
  const [hh, setHh] = useState({ enabled: false, start_hour: 17, end_hour: 19, multiplier: 2 });
  const [loading, setLoading] = useState(true);
  const [noProfile, setNoProfile] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, o, h] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/dashboard`),
        axios.get(`${API}/merchant/marketplace/orders`),
        axios.get(`${API}/merchant/marketplace/happy-hour`),
      ]);
      setDash(d.data); setOrders(o.data.items || []);
      if (h.data.happy_hour) setHh(h.data.happy_hour);
    } catch (e) {
      if (e?.response?.status === 404) setNoProfile(true);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const advance = async (order) => {
    const next = NEXT[order.status];
    if (!next) return;
    try { await axios.patch(`${API}/merchant/marketplace/orders/${order.order_id}/status`, { status: next }); load(); }
    catch { /* ignore */ }
  };
  const saveHh = async (patch) => {
    const nextHh = { ...hh, ...patch }; setHh(nextHh);
    try { await axios.patch(`${API}/merchant/marketplace/happy-hour`, nextHh); load(); } catch { /* ignore */ }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  if (noProfile) return (
    <div className="px-4 pt-16 text-center" data-testid="merchant-no-profile">
      <Utensils size={44} className="mx-auto text-orange-500" />
      <p className="mt-3 font-semibold text-slate-700">You don't have a business yet.</p>
      <button onClick={() => navigate("/sell")} data-testid="merchant-sell-cta"
        className="mt-4 bg-orange-600 text-white font-black rounded-full px-6 py-3">Sell on RadioLife</button>
    </div>
  );

  const inactive = !dash.subscription_active;

  return (
    <div className="pb-24" data-testid="rl-merchant-dash-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop")} data-testid="merchant-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Merchant Dashboard</h1>
      </div>

      <div className="px-4 space-y-4">
        {inactive && (
          <button onClick={() => navigate("/shop/merchant/subscribe")} data-testid="merchant-sub-banner"
            className="w-full flex items-center gap-2 bg-orange-600 text-white font-black rounded-xl p-4">
            <Lock size={18} /> Subscribe to list & sell on RadioLife <ArrowRight size={16} className="ml-auto" />
          </button>
        )}
        <h2 className="text-xl font-black text-slate-900">{dash.public_name}</h2>

        <div className="grid grid-cols-2 gap-3">
          {[["Open Orders", dash.open_orders, "open-orders"], ["Revenue", money(dash.revenue_cents)],
            ["Points Spent", dash.bigpoints_spent], ["Menu Items", dash.menu_item_count]].map(([lbl, val, tid], i) => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="text-2xl font-black text-slate-900" data-testid={tid ? `stat-${tid}` : undefined}>{val}</div>
              <div className="text-xs font-bold text-slate-400 mt-0.5">{lbl}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-3 gap-3">
          <button onClick={() => navigate("/shop/merchant/menu")} data-testid="merchant-open-menu"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Utensils size={15} />Menu</button>
          <button onClick={() => navigate("/shop/merchant/services")} data-testid="merchant-open-services"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><CreditCard size={15} />Services</button>
          <button onClick={() => navigate("/shop/merchant/subscribe")} data-testid="merchant-open-sub"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><CreditCard size={15} />{dash.subscription_active ? "Plan" : "Subscribe"}</button>
        </div>

        {/* Happy Hour */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="merchant-happy-hour">
          <div className="flex items-center gap-3">
            <div className="flex-1">
              <div className="font-black text-slate-900 flex items-center gap-1"><Zap size={15} className="text-orange-600" />Happy Hour Boost</div>
              <div className="text-xs text-slate-500 mt-0.5">Give {hh.multiplier}X BigPoints during set hours{dash.happy_hour_active_now ? " · LIVE NOW" : ""}.</div>
            </div>
            <label className="relative inline-flex items-center cursor-pointer">
              <input type="checkbox" className="sr-only peer" checked={!!hh.enabled}
                onChange={(e) => saveHh({ enabled: e.target.checked })} data-testid="hh-toggle" />
              <div className="w-11 h-6 bg-slate-200 peer-checked:bg-orange-600 rounded-full peer-checked:after:translate-x-5 after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
            </label>
          </div>
          {hh.enabled && (
            <div className="grid grid-cols-3 gap-2 mt-3">
              {[["Start (0-23)", "start_hour", "hh-start"], ["End (0-23)", "end_hour", "hh-end"], ["Multiplier", "multiplier", "hh-mult"]].map(([lbl, key, tid]) => (
                <div key={key}>
                  <div className="text-[9px] font-extrabold tracking-wide text-slate-400 mb-1">{lbl.toUpperCase()}</div>
                  <input type="number" defaultValue={hh[key]} data-testid={tid}
                    onBlur={(e) => saveHh({ [key]: key === "multiplier" ? Math.min(5, Math.max(1, parseFloat(e.target.value) || 2)) : Math.min(23, Math.max(0, parseInt(e.target.value, 10) || 0)) })}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-2 py-2 text-center font-black text-slate-900" />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Orders */}
        <h3 className="text-base font-black text-slate-900">Incoming Orders</h3>
        {!orders.length && <p className="text-slate-500 text-sm" data-testid="merchant-orders-empty">No paid orders yet.</p>}
        {orders.map((o) => (
          <div key={o.order_id} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`merchant-order-${o.order_id}`}>
            <div className="flex items-center justify-between">
              <div className="text-lg font-black tracking-widest text-slate-900">#{o.pickup_code}</div>
              <div className="text-xs font-black uppercase text-orange-600">{o.status}</div>
            </div>
            {(o.items || []).map((it, i) => <div key={i} className="text-sm text-slate-600 font-semibold">{it.qty}× {it.name}</div>)}
            <div className="text-sm font-bold text-slate-900 mt-1">{money(o.total_cents)} · rewards {o.points_to_award} BigPoints</div>
            {NEXT[o.status] && (
              <button onClick={() => advance(o)} data-testid={`merchant-advance-${o.order_id}`}
                className="mt-3 w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-lg py-2.5">{NEXT_LABEL[o.status]}<ArrowRight size={15} /></button>
            )}
            {o.status === "picked_up" && (
              <div className="flex items-center gap-1.5 mt-3 text-green-600 text-xs font-bold"><CheckCircle2 size={16} />Completed · {o.points_to_award} BigPoints awarded</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
