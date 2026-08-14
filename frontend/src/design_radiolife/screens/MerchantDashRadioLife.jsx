// RadioLife Merchant Dashboard — orders, BigPoints, happy hour (web).
import React, { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, ArrowRight, Lock, Zap, CheckCircle2, Utensils, CreditCard, Package, Gift, Crown, CalendarDays, Tag, Bell, QrCode, Flame, Coins, TrendingUp, Clock } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const NEXT = { accepted: "preparing", preparing: "ready", ready: "picked_up" };
const NEXT_LABEL = { accepted: "Start Preparing", preparing: "Mark Ready", ready: "Mark Picked Up" };
const PICKUP_LABELS = { now: "Now (~15 min)", "+15": "In 15 min", "+30": "In 30 min", "+45": "In 45 min" };
const PNEXT = { paid: "packed", packed: "shipped", shipped: "delivered" };
const PNEXT_LABEL = { paid: "Mark Packed", packed: "Mark Shipped", shipped: "Mark Delivered" };

// Audible "new order" ping via Web Audio — no asset needed.
function playPing() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const beep = (freq, start, dur) => {
      const o = ctx.createOscillator(); const g = ctx.createGain();
      o.type = "sine"; o.frequency.value = freq;
      o.connect(g); g.connect(ctx.destination);
      g.gain.setValueAtTime(0.001, ctx.currentTime + start);
      g.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + start + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + start + dur);
      o.start(ctx.currentTime + start); o.stop(ctx.currentTime + start + dur);
    };
    beep(880, 0, 0.18); beep(1174, 0.16, 0.22);
    setTimeout(() => ctx.close(), 800);
  } catch { /* ignore */ }
}

export default function MerchantDashRadioLife() {
  const navigate = useNavigate();
  const [dash, setDash] = useState(null);
  const [orders, setOrders] = useState([]);
  const [productOrders, setProductOrders] = useState([]);
  const [newCount, setNewCount] = useState({ food: 0, products: 0, total: 0 });
  const [hh, setHh] = useState({ enabled: false, start_hour: 17, end_hour: 19, multiplier: 2 });
  const [pts, setPts] = useState({ mode: "default", default_points: 50, points_per_dollar: 2 });
  const [soundOn, setSoundOn] = useState(true);
  const [loading, setLoading] = useState(true);
  const [noProfile, setNoProfile] = useState(false);
  const prevNew = useRef(null);

  const load = useCallback(async () => {
    try {
      const [d, o, h, po, nc, bp] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/dashboard`),
        axios.get(`${API}/merchant/marketplace/orders`),
        axios.get(`${API}/merchant/marketplace/happy-hour`),
        axios.get(`${API}/merchant/marketplace/products/orders`),
        axios.get(`${API}/merchant/marketplace/orders/new-count`),
        axios.get(`${API}/merchant/marketplace/bigpoints/settings`).catch(() => ({ data: {} })),
      ]);
      setDash(d.data); setOrders(o.data.items || []);
      setProductOrders(po.data.items || []);
      const nextNew = nc.data || { total: 0 };
      // Audible ping when the new-order count goes up.
      if (prevNew.current !== null && nextNew.total > prevNew.current && soundOn) playPing();
      prevNew.current = nextNew.total;
      setNewCount(nextNew);
      if (h.data.happy_hour) setHh(h.data.happy_hour);
      if (bp.data.bigpoints) setPts({
        mode: bp.data.bigpoints.mode || "default",
        default_points: bp.data.bigpoints.default_points ?? 50,
        points_per_dollar: bp.data.bigpoints.points_per_dollar ?? 2,
      });
    } catch (e) {
      if (e?.response?.status === 404) setNoProfile(true);
    } finally { setLoading(false); }
  }, [soundOn]);
  useEffect(() => {
    load();
    const t = setInterval(load, 15000); // poll for new orders
    return () => clearInterval(t);
  }, [load]);

  const savePts = async (patch) => {
    const next = { ...pts, ...patch }; setPts(next);
    try { await axios.patch(`${API}/merchant/marketplace/bigpoints/settings`, next); } catch { /* ignore */ }
  };

  const advance = async (order) => {
    const next = NEXT[order.status];
    if (!next) return;
    try { await axios.patch(`${API}/merchant/marketplace/orders/${order.order_id}/status`, { status: next }); load(); }
    catch { /* ignore */ }
  };
  const advanceProduct = async (order) => {
    const next = PNEXT[order.status];
    if (!next) return;
    try { await axios.patch(`${API}/merchant/marketplace/products/orders/${order.order_id}/status`, { status: next }); load(); }
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

        {newCount.total > 0 && (
          <div className="flex items-center gap-2 bg-green-600 text-white font-black rounded-xl p-4 animate-pulse" data-testid="merchant-new-order-alert">
            <Bell size={18} />
            {newCount.total} new order{newCount.total > 1 ? "s" : ""} to action
            {newCount.food > 0 && newCount.products > 0 ? ` · ${newCount.food} food, ${newCount.products} product` : ""}
            <button onClick={() => setSoundOn((v) => !v)} data-testid="merchant-sound-toggle"
              className="ml-auto text-xs bg-white/20 rounded-full px-2 py-1">{soundOn ? "🔔 On" : "🔕 Off"}</button>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          {[["Open Orders", dash.open_orders, "open-orders"], ["Revenue", money(dash.revenue_cents)],
            ["Points Spent", dash.bigpoints_spent], ["Menu Items", dash.menu_item_count]].map(([lbl, val, tid], i) => (
            <div key={i} className="bg-white border border-slate-200 rounded-xl p-4">
              <div className="text-2xl font-black text-slate-900" data-testid={tid ? `stat-${tid}` : undefined}>{val}</div>
              <div className="text-xs font-bold text-slate-400 mt-0.5">{lbl}</div>
            </div>
          ))}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button onClick={() => navigate("/shop/merchant/menu")} data-testid="merchant-open-menu"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Utensils size={15} />Menu</button>
          <button onClick={() => navigate("/shop/merchant/services")} data-testid="merchant-open-services"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><CreditCard size={15} />Services</button>
          <button onClick={() => navigate("/shop/merchant/products")} data-testid="merchant-open-products"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Package size={15} />Products</button>
          <button onClick={() => navigate("/shop/merchant/giftcards")} data-testid="merchant-open-giftcards"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Gift size={15} />Gift Cards</button>
          <button onClick={() => navigate("/shop/merchant/memberships")} data-testid="merchant-open-memberships"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Crown size={15} />Memberships</button>
          <button onClick={() => navigate("/shop/merchant/packages")} data-testid="merchant-open-packages"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Package size={15} />Packages</button>
          <button onClick={() => navigate("/shop/merchant/events")} data-testid="merchant-open-events"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><CalendarDays size={15} />Events</button>
          <button onClick={() => navigate("/shop/merchant/coupons")} data-testid="merchant-open-coupons"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Tag size={15} />Coupons</button>
          <button onClick={() => navigate("/shop/merchant/specials")} data-testid="merchant-open-specials"
            className="flex items-center justify-center gap-1.5 bg-orange-50 text-orange-600 font-black rounded-xl py-3 text-sm"><Flame size={15} />Specials</button>
          <button onClick={() => navigate("/shop/merchant/scan")} data-testid="merchant-open-scan"
            className="flex items-center justify-center gap-1.5 bg-green-600 text-white font-black rounded-xl py-3 text-sm"><QrCode size={15} />Scan to Charge</button>
          <button onClick={() => navigate("/shop/merchant/earnings")} data-testid="merchant-open-earnings"
            className="flex items-center justify-center gap-1.5 bg-emerald-50 text-emerald-700 font-black rounded-xl py-3 text-sm"><TrendingUp size={15} />Earnings</button>
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

        {/* BigPoints earning — flat or points-per-dollar */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="merchant-points-settings">
          <div className="font-black text-slate-900 flex items-center gap-1"><Coins size={15} className="text-orange-600" />BigPoints Earning</div>
          <div className="text-xs text-slate-500 mt-0.5">Reward big spenders and rank higher by earning points per dollar.</div>
          <div className="flex gap-2 mt-3">
            <button onClick={() => savePts({ mode: "default" })} data-testid="points-mode-flat"
              className={`flex-1 rounded-xl py-2.5 text-sm font-black border ${pts.mode === "default" ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 text-slate-500"}`}>Flat per order</button>
            <button onClick={() => savePts({ mode: "per_order_value" })} data-testid="points-mode-perdollar"
              className={`flex-1 rounded-xl py-2.5 text-sm font-black border ${pts.mode === "per_order_value" ? "border-orange-500 bg-orange-50 text-orange-700" : "border-slate-200 text-slate-500"}`}>Per dollar</button>
          </div>
          {pts.mode === "per_order_value" ? (
            <label className="block text-xs font-bold text-slate-500 mt-3">Points per $1 spent
              <input type="number" defaultValue={pts.points_per_dollar} data-testid="points-ppd-input"
                onBlur={(e) => savePts({ points_per_dollar: Math.max(0, parseFloat(e.target.value) || 0) })}
                className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5 font-black text-slate-900" />
            </label>
          ) : (
            <label className="block text-xs font-bold text-slate-500 mt-3">Flat points per order
              <input type="number" defaultValue={pts.default_points} data-testid="points-flat-input"
                onBlur={(e) => savePts({ default_points: Math.max(0, parseInt(e.target.value, 10) || 0) })}
                className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2.5 font-black text-slate-900" />
            </label>
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
            <div className="flex items-center gap-1.5 mt-1 text-xs font-black text-green-700" data-testid={`merchant-order-pickup-${o.order_id}`}>
              <Clock size={12} />{o.fulfillment === "delivery" ? "Deliver" : "Pickup"} · {PICKUP_LABELS[o.pickup_time] || "Now (~15 min)"}
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

        {/* Product Orders */}
        <h3 className="text-base font-black text-slate-900 flex items-center gap-1.5"><Package size={16} className="text-orange-600" />Product Orders</h3>
        {!productOrders.length && <p className="text-slate-500 text-sm" data-testid="merchant-product-orders-empty">No product orders yet.</p>}
        {productOrders.map((o) => (
          <div key={o.order_id} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`merchant-product-order-${o.order_id}`}>
            <div className="flex items-center justify-between">
              <div className="text-sm font-black text-slate-900">{o.fulfillment === "delivery" ? "🚚 Delivery" : "🏬 Pickup"}</div>
              <div className="text-xs font-black uppercase text-orange-600">{o.status}</div>
            </div>
            {(o.items || []).map((it, i) => <div key={i} className="text-sm text-slate-600 font-semibold">{it.qty}× {it.name}{it.variant_label ? ` (${it.variant_label})` : ""}</div>)}
            {o.fulfillment === "delivery" && o.address && <div className="text-xs text-slate-400 mt-1">📍 {o.address}</div>}
            <div className="text-sm font-bold text-slate-900 mt-1">{money(o.total_cents)} · rewards {o.points_to_award} BigPoints</div>
            {PNEXT[o.status] && (
              <button onClick={() => advanceProduct(o)} data-testid={`merchant-product-advance-${o.order_id}`}
                className="mt-3 w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-lg py-2.5">{PNEXT_LABEL[o.status]}<ArrowRight size={15} /></button>
            )}
            {o.status === "delivered" && (
              <div className="flex items-center gap-1.5 mt-3 text-green-600 text-xs font-bold"><CheckCircle2 size={16} />Delivered · {o.points_to_award} BigPoints awarded</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
