// Merchant "Promote my shop" (Phase F) — buy a tiered promotion (Stripe hosted
// Checkout) that boosts the shop in Shop search + the Promoted-near-you rail;
// see promo analytics (extra views/orders); auto-renew via a saved card; and
// run a per-impression Category Spotlight bid auction.
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Rocket, CheckCircle2, Clock, XCircle, TrendingUp, BarChart3, RefreshCw, Target, CreditCard } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;
const cents = (c) => `${c}¢`;

const STATUS_UI = {
  pending_payment: { label: "Awaiting payment", cls: "bg-slate-100 text-slate-600", Icon: Clock },
  pending_review: { label: "In review", cls: "bg-amber-100 text-amber-700", Icon: Clock },
  active: { label: "Live", cls: "bg-green-100 text-green-700", Icon: CheckCircle2 },
  rejected: { label: "Rejected", cls: "bg-red-100 text-red-700", Icon: XCircle },
  expired: { label: "Expired", cls: "bg-slate-100 text-slate-500", Icon: Clock },
};

function Stat({ label, value, extra }) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-3 flex-1">
      <div className="text-xl font-black text-slate-900">{value}</div>
      <div className="text-[11px] font-bold text-slate-400">{label}</div>
      {extra != null && <div className="text-[11px] font-black text-green-600 mt-0.5">+{extra} vs before</div>}
    </div>
  );
}

function TrendChart({ trend }) {
  const pts = (trend || []).filter(Boolean);
  if (!pts.length) return null;
  const max = Math.max(1, ...pts.map((d) => d.views));
  const anyCapped = pts.some((d) => d.capped);
  return (
    <div className="mt-3" data-testid="promote-trend">
      <div className="flex items-center justify-between mb-1">
        <div className="text-[11px] font-bold text-slate-400">Daily views · orders</div>
        {anyCapped && (
          <div className="flex items-center gap-1 text-[10px] font-black text-red-500" data-testid="promote-trend-cap-legend">
            <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />Daily cap hit
          </div>
        )}
      </div>
      <div className="flex items-end gap-1 h-16">
        {pts.map((d) => (
          <div key={d.date} className="flex-1 flex flex-col items-center justify-end"
            title={`${d.date}: ${d.views} views, ${d.orders} orders${d.capped ? " · daily cap hit" : ""}`}
            data-testid={d.capped ? `promote-trend-capped-${d.date}` : undefined}>
            {d.capped
              ? <div className="w-1.5 h-1.5 rounded-full bg-red-500 mb-0.5" />
              : (d.orders > 0 && <div className="text-[9px] font-black text-orange-600 leading-none mb-0.5">{d.orders}</div>)}
            <div className={`w-full rounded-t ${d.capped ? "bg-red-400" : "bg-orange-400"}`} style={{ height: `${Math.max(4, (d.views / max) * 52)}px` }} />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-[9px] text-slate-400 mt-1">
        <span>{pts[0].date.slice(5)}</span><span>{pts[pts.length - 1].date.slice(5)}</span>
      </div>
    </div>
  );
}

export default function MerchantPromoteRadioLife() {
  const navigate = useNavigate();
  const [tiers, setTiers] = useState([]);
  const [data, setData] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [cbid, setCbid] = useState(null);
  const [cats, setCats] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [bidCat, setBidCat] = useState("");
  const [bidCents, setBidCents] = useState("5");
  const [dailyCap, setDailyCap] = useState("0");
  const [topupDollars, setTopupDollars] = useState("10");
  const [autoTopupDollars, setAutoTopupDollars] = useState("10");

  const load = useCallback(async () => {
    try {
      const [t, m, a, cb, cc] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/promotion/tiers`),
        axios.get(`${API}/merchant/marketplace/promotion`),
        axios.get(`${API}/merchant/marketplace/promotion/analytics`).catch(() => ({ data: { has_data: false } })),
        axios.get(`${API}/merchant/marketplace/category-bid`).catch(() => ({ data: {} })),
        axios.get(`${API}/merchant/marketplace/category-bid/categories`).catch(() => ({ data: { items: [] } })),
      ]);
      setTiers(t.data.tiers || []);
      setData(m.data);
      setAnalytics(a.data);
      setCbid(cb.data);
      setCats(cc.data.items || []);
      if (cb.data?.bid?.category) setBidCat(cb.data.bid.category);
      else if ((cc.data.items || [])[0]) setBidCat(cc.data.items[0].key);
      if (cb.data?.bid?.bid_cents) setBidCents(String(cb.data.bid.bid_cents));
      if (cb.data?.bid?.daily_cap_cents != null) setDailyCap(String(cb.data.bid.daily_cap_cents));
      if (cb.data?.bid?.auto_topup_amount_cents) setAutoTopupDollars(String(cb.data.bid.auto_topup_amount_cents / 100));
      const pend = (m.data.items || []).find((p) => p.status === "pending_payment");
      if (pend) {
        const st = await axios.get(`${API}/merchant/marketplace/promotion/${pend.promotion_id}/status`);
        if (st.data.status !== "pending_payment") { const m2 = await axios.get(`${API}/merchant/marketplace/promotion`); setData(m2.data); }
      }
    } catch { setData({ no_profile: true }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const buy = async (tier) => {
    setBusy(tier);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/promotion/checkout`, { tier, origin_url: window.location.origin });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "stripe_unconfigured" ? "Payments not configured" : "Could not start checkout");
    } finally { setBusy(null); }
  };

  const toggleAutoRenew = async (enabled) => {
    const active = data?.active;
    if (!active) return;
    if (enabled && !data?.default_pm && !(data?.saved_cards || []).length) {
      // No card yet — send them to save one first.
      try {
        const r = await axios.post(`${API}/shop/wallet/cards/setup-session`, { origin_url: window.location.origin });
        if (r.data.checkout_url || r.data.url) { window.location.href = r.data.checkout_url || r.data.url; return; }
      } catch { toast.error("Could not open card setup"); }
      return;
    }
    try {
      await axios.post(`${API}/merchant/marketplace/promotion/${active.promotion_id}/auto-renew`,
        { enabled, payment_method_id: data?.default_pm });
      toast.success(enabled ? "Auto-renew on" : "Auto-renew off");
      load();
    } catch { toast.error("Could not update auto-renew"); }
  };

  const saveBid = async () => {
    setBusy("bid");
    try {
      const r = await axios.post(`${API}/merchant/marketplace/category-bid/set`,
        { category: bidCat, bid_cents: Math.max(1, parseInt(bidCents, 10) || 1),
          daily_cap_cents: Math.max(0, parseInt(dailyCap, 10) || 0) });
      setCbid((c) => ({ ...(c || {}), standing: r.data.standing }));
      toast.success(r.data.status === "active" ? "Bid live" : "Bid saved — add budget to go live");
      load();
    } catch { toast.error("Could not save bid"); }
    finally { setBusy(null); }
  };

  const topUp = async () => {
    setBusy("topup");
    try {
      const amt = Math.round(parseFloat(topupDollars) * 100);
      const r = await axios.post(`${API}/merchant/marketplace/category-bid/topup/checkout`,
        { amount_cents: amt, origin_url: window.location.origin });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "set_bid_first" ? "Set a bid first" : "Could not start top-up");
    } finally { setBusy(null); }
  };

  const toggleAutoTopup = async (enabled) => {
    if (enabled && !cbid?.default_pm && !(cbid?.saved_cards || []).length) {
      try {
        const r = await axios.post(`${API}/shop/wallet/cards/setup-session`, { origin_url: window.location.origin });
        if (r.data.checkout_url || r.data.url) { window.location.href = r.data.checkout_url || r.data.url; return; }
      } catch { toast.error("Could not open card setup"); }
      return;
    }
    try {
      const amt = Math.max(500, Math.round(parseFloat(autoTopupDollars) * 100) || 1000);
      await axios.post(`${API}/merchant/marketplace/category-bid/auto-topup`,
        { enabled, amount_cents: amt, payment_method_id: cbid?.default_pm });
      toast.success(enabled ? "Auto top-up on" : "Auto top-up off");
      load();
    } catch { toast.error("Could not update auto top-up"); }
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
  const bid = cbid?.bid;
  const standing = cbid?.standing;

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
            {/* Auto-renew */}
            <div className="flex items-center justify-between mt-3 pt-3 border-t border-green-200">
              <div>
                <div className="font-black text-slate-800 flex items-center gap-1.5 text-sm"><RefreshCw size={14} className="text-green-700" />Auto-renew</div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {data?.default_pm || (data?.saved_cards || []).length ? "Charges your saved card when it expires — a receipt is emailed each time." : "Add a card to keep it running automatically."}
                </div>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" className="sr-only peer" checked={!!data?.auto_renew}
                  onChange={(e) => toggleAutoRenew(e.target.checked)} data-testid="promote-autorenew-toggle" />
                <div className="w-11 h-6 bg-slate-200 peer-checked:bg-green-600 rounded-full peer-checked:after:translate-x-5 after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
              </label>
            </div>
          </div>
        )}

        {/* Analytics */}
        {analytics?.has_data && (
          <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="promote-analytics">
            <div className="font-black text-slate-900 flex items-center gap-1.5"><BarChart3 size={16} className="text-orange-600" />Promotion impact</div>
            <div className="text-[11px] text-slate-400 mb-3">Since your {analytics.tier} promotion started</div>
            <div className="flex gap-2">
              <Stat label="Views" value={analytics.views} extra={analytics.extra_views || null} />
              <Stat label="Impressions" value={analytics.impressions} extra={analytics.extra_impressions || null} />
            </div>
            <div className="flex gap-2 mt-2">
              <Stat label="Orders" value={analytics.orders} extra={analytics.extra_orders || null} />
              <Stat label="Revenue" value={money(analytics.revenue_cents)} extra={analytics.extra_revenue_cents ? money(analytics.extra_revenue_cents).replace("$", "$") : null} />
            </div>
            <TrendChart trend={analytics.trend} />
          </div>
        )}

        {/* Tiers */}
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
                <button onClick={() => buy(t.tier)} disabled={!!busy || isActiveTier} data-testid={`promote-buy-${t.tier}`}
                  className={`mt-3 w-full font-black rounded-full py-2.5 text-sm transition-colors ${isActiveTier ? "bg-slate-100 text-slate-400" : "bg-orange-600 text-white hover:bg-orange-700"}`}>
                  {isActiveTier ? "Current promotion" : busy === t.tier ? "Starting…" : `Promote for ${t.days} days`}
                </button>
              </div>
            );
          })}
        </div>

        {/* Category Spotlight bid auction */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="promote-category-spotlight">
          <div className="font-black text-slate-900 flex items-center gap-1.5"><Target size={16} className="text-orange-600" />Category Spotlight</div>
          <div className="text-xs text-slate-500 mt-0.5 mb-3">Bid per impression to top one category. Highest bid ranks first — you only pay from your prepaid budget as your shop is shown.</div>

          {standing && bid && (
            <div className={`rounded-xl p-3 mb-3 ${standing.outbid ? "bg-red-50 border border-red-200" : "bg-green-50 border border-green-200"}`} data-testid="promote-bid-standing">
              {standing.rank ? (
                <div className={`font-black text-sm ${standing.outbid ? "text-red-700" : "text-green-700"}`}>
                  You&apos;re #{standing.rank} of {standing.competitors} in {bid.category}
                </div>
              ) : <div className="font-black text-sm text-slate-600">Not ranking yet in {bid.category}</div>}
              <div className="text-[11px] text-slate-600 mt-0.5">
                Top bid {cents(standing.top_bid_cents)} · your bid {cents(bid.bid_cents)} · budget {money(bid.budget_cents)} left
              </div>
              {standing.outbid && (
                <div className="text-[11px] font-black text-red-600 mt-1" data-testid="promote-outbid-alert">
                  You&apos;ve been outbid — bid {cents(standing.suggested_bid_cents)}+ to take #1.
                </div>
              )}
            </div>
          )}

          {cbid?.budget && bid && (cbid.budget.low_budget || cbid.budget.depleted) && (
            <div className="rounded-xl p-3 mb-3 bg-amber-50 border border-amber-200" data-testid="promote-low-budget">
              <div className="font-black text-sm text-amber-700">
                {cbid.budget.depleted ? "Budget used up — you're no longer spotlighted" : "Low budget — top up to keep your spot"}
              </div>
              <div className="text-[11px] text-amber-700/80 mt-0.5">
                About {cbid.budget.impressions_left} impression{cbid.budget.impressions_left === 1 ? "" : "s"} left at your current bid.
              </div>
            </div>
          )}

          <div className="flex gap-2">
            <select value={bidCat} onChange={(e) => setBidCat(e.target.value)} data-testid="promote-bid-category"
              className="flex-1 rounded-xl bg-slate-50 border border-slate-200 px-3 py-2.5 text-sm font-bold">
              {cats.map((c) => <option key={c.key} value={c.key}>{c.name}</option>)}
            </select>
            <div className="flex items-center bg-slate-50 border border-slate-200 rounded-xl px-2">
              <input type="number" min="1" value={bidCents} onChange={(e) => setBidCents(e.target.value)} data-testid="promote-bid-cents"
                className="w-14 bg-transparent text-center font-black text-slate-900 py-2.5" />
              <span className="text-xs font-bold text-slate-400 pr-1">¢/imp</span>
            </div>
          </div>
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs font-bold text-slate-500 flex-1">Max spend per day (0 = no cap)</span>
            <div className="flex items-center bg-slate-50 border border-slate-200 rounded-xl px-3">
              <span className="text-sm font-bold text-slate-400">$</span>
              <input type="number" min="0" step="0.5"
                value={(parseInt(dailyCap, 10) || 0) / 100 || ""}
                onChange={(e) => setDailyCap(String(Math.round((parseFloat(e.target.value) || 0) * 100)))}
                placeholder="0" data-testid="promote-daily-cap"
                className="w-16 bg-transparent text-center font-black text-slate-900 py-2" />
            </div>
          </div>
          <button onClick={saveBid} disabled={busy === "bid"} data-testid="promote-bid-save"
            className="mt-2 w-full bg-slate-900 text-white font-black rounded-full py-2.5 text-sm">
            {busy === "bid" ? "Saving…" : bid ? "Update bid" : "Place bid"}
          </button>

          {bid && (
            <div className="mt-3 pt-3 border-t border-slate-100">
              <div className="text-xs font-bold text-slate-500 mb-1.5 flex items-center gap-1"><CreditCard size={13} />Add budget</div>
              <div className="flex gap-2">
                <div className="flex items-center bg-slate-50 border border-slate-200 rounded-xl px-3 flex-1">
                  <span className="text-sm font-bold text-slate-400">$</span>
                  <input type="number" min="5" value={topupDollars} onChange={(e) => setTopupDollars(e.target.value)} data-testid="promote-topup-amount"
                    className="w-full bg-transparent font-black text-slate-900 py-2.5 px-1" />
                </div>
                <button onClick={topUp} disabled={busy === "topup"} data-testid="promote-topup-btn"
                  className="bg-orange-600 text-white font-black rounded-full px-5 text-sm">
                  {busy === "topup" ? "…" : "Top up"}
                </button>
              </div>
              {/* Auto top-up */}
              <div className="flex items-center justify-between mt-3 pt-3 border-t border-slate-100" data-testid="promote-autotopup">
                <div className="flex-1 pr-2">
                  <div className="font-black text-slate-800 text-sm flex items-center gap-1.5"><RefreshCw size={13} className="text-orange-600" />Auto top-up</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">
                    {cbid?.default_pm || (cbid?.saved_cards || []).length
                      ? `Refills $${autoTopupDollars} from your saved card when budget runs low.`
                      : "Add a card to keep your spotlight funded automatically."}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="flex items-center bg-slate-50 border border-slate-200 rounded-xl px-2">
                    <span className="text-sm font-bold text-slate-400">$</span>
                    <input type="number" min="5" value={autoTopupDollars} onChange={(e) => setAutoTopupDollars(e.target.value)} data-testid="promote-autotopup-amount"
                      className="w-12 bg-transparent text-center font-black text-slate-900 py-2" />
                  </div>
                  <label className="relative inline-flex items-center cursor-pointer">
                    <input type="checkbox" className="sr-only peer" checked={!!bid?.auto_topup}
                      onChange={(e) => toggleAutoTopup(e.target.checked)} data-testid="promote-autotopup-toggle" />
                    <div className="w-11 h-6 bg-slate-200 peer-checked:bg-orange-600 rounded-full peer-checked:after:translate-x-5 after:content-[''] after:absolute after:top-0.5 after:left-0.5 after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
                  </label>
                </div>
              </div>
            </div>
          )}
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
                      <div className="font-bold text-slate-800 text-sm">{p.name} · {p.price_cents ? money(p.price_cents) : "COMP"}{p.renewed ? " · renewed" : ""}</div>
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
