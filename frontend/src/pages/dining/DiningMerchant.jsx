// Dining Club — restaurant (merchant) dashboard: enroll + Stripe Connect,
// locations, daily veg/non-veg meal + capacity, analytics, webhooks.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  ChevronLeft, Store, Loader2, Plus, MapPin, BadgeCheck, AlertTriangle,
  BarChart3, Webhook, Trash2, DollarSign,
} from "lucide-react";
import { diningApi, DINE, money, errCode } from "./diningApi";
import { Shell, NeonBtn, GhostBtn } from "./DiningHome";

const Label = ({ children }) => (
  <span className="text-[11px] font-mono uppercase" style={{ color: DINE.muted, letterSpacing: "0.14em" }}>{children}</span>
);
const Card = ({ children, testid }) => (
  <div className="rounded-3xl p-6 mb-5" style={{ background: DINE.card, border: `1px solid ${DINE.border}` }} data-testid={testid}>{children}</div>
);
const Input = (p) => (
  <input {...p} className="w-full rounded-xl px-4 py-3 mb-3 outline-none"
    style={{ background: DINE.panel, border: `1px solid ${DINE.border}`, color: DINE.text }} />
);

export default function DiningMerchant() {
  const nav = useNavigate();
  const [me, setMe] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [hooks, setHooks] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", cuisine: "american", restaurant_class: "FAST_CASUAL" });
  const [loc, setLoc] = useState({ name: "", address: "" });
  const [hookUrl, setHookUrl] = useState("");

  const load = async () => {
    try {
      const m = await diningApi.merchantMe();
      setMe(m);
      if (m.enrolled) {
        setAnalytics(await diningApi.merchantAnalytics().catch(() => null));
        setHooks(await diningApi.merchantWebhooks().catch(() => null));
      }
    } catch (e) { toast.error(errCode(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const enroll = async () => {
    if (!form.name.trim()) return toast.error("Restaurant name required");
    setBusy(true);
    try {
      const r = await diningApi.merchantEnroll(form);
      toast.success("Enrolled! Finish Stripe payouts to get paid $8.99/meal.");
      if (r.connect_onboarding_url) window.open(r.connect_onboarding_url, "_blank");
      await load();
    } catch (e) { toast.error(errCode(e)); } finally { setBusy(false); }
  };

  const connect = async () => {
    try { const r = await diningApi.merchantConnectLink(); if (r.connect_onboarding_url) window.open(r.connect_onboarding_url, "_blank"); }
    catch (e) { toast.error(errCode(e)); }
  };

  const addLocation = async () => {
    if (!loc.name.trim() || !loc.address.trim()) return toast.error("Name & address required");
    setBusy(true);
    try {
      await diningApi.merchantAddLocation({ ...loc, veg_available: true, nonveg_available: true });
      setLoc({ name: "", address: "" }); toast.success("Location added"); await load();
    } catch (e) { toast.error(errCode(e)); } finally { setBusy(false); }
  };

  const saveCapacity = async (id, key, val) => {
    const location = me.locations.find((l) => l.location_id === id);
    const cap = { ...(location.capacity || {}), [key]: Math.max(0, parseInt(val || 0, 10)) };
    try { await diningApi.merchantSetCapacity(id, cap); toast.success("Capacity saved"); await load(); }
    catch (e) { toast.error(errCode(e)); }
  };

  const saveMeal = async (id, veg, title) => {
    try { await diningApi.merchantSetMeals(id, [{ veg_preference: veg, meal_period: "LUNCH", customer_title: title }]); toast.success("Meal set"); }
    catch (e) { toast.error(errCode(e)); }
  };

  const addHook = async () => {
    if (!hookUrl.startsWith("http")) return toast.error("Valid URL required");
    try { await diningApi.merchantAddWebhook({ url: hookUrl }); setHookUrl(""); toast.success("Webhook added"); setHooks(await diningApi.merchantWebhooks()); }
    catch (e) { toast.error(errCode(e)); }
  };
  const delHook = async (id) => { try { await diningApi.merchantDeleteWebhook(id); setHooks(await diningApi.merchantWebhooks()); } catch (e) { toast.error(errCode(e)); } };

  if (loading) return <Shell><div className="flex justify-center py-24"><Loader2 className="animate-spin" color={DINE.pink} /></div></Shell>;

  return (
    <Shell testid="dining-merchant-page">
      <button onClick={() => nav("/dining")} className="flex items-center gap-1 mb-6 text-sm" style={{ color: DINE.muted }} data-testid="merchant-back">
        <ChevronLeft size={16} /> Dining Club
      </button>
      <div className="flex items-center gap-2 mb-6"><Store color={DINE.pink} /><h1 className="text-3xl font-black" style={{ color: DINE.text }}>Restaurant Portal</h1></div>

      {!me?.enrolled ? (
        <Card testid="merchant-enroll-card">
          <Label>Join the Dining Club network</Label>
          <p className="text-sm mt-2 mb-5" style={{ color: DINE.muted }}>You set the meal &amp; capacity — we send the diner. You receive <b style={{ color: DINE.gold }}>$8.99</b> per redeemed meal (platform keeps $1).</p>
          <Input placeholder="Restaurant name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="merchant-name" />
          <Input placeholder="Cuisine (e.g. indian)" value={form.cuisine} onChange={(e) => setForm({ ...form, cuisine: e.target.value })} data-testid="merchant-cuisine" />
          <select value={form.restaurant_class} onChange={(e) => setForm({ ...form, restaurant_class: e.target.value })} data-testid="merchant-class"
            className="w-full rounded-xl px-4 py-3 mb-4 outline-none" style={{ background: DINE.panel, border: `1px solid ${DINE.border}`, color: DINE.text }}>
            <option value="FAST_CASUAL">Fast Casual</option>
            <option value="SIT_DOWN">Sit-Down</option>
            <option value="OTHER_APPROVED">Other</option>
          </select>
          <NeonBtn testid="merchant-enroll" onClick={enroll} disabled={busy} color={DINE.pink} full>
            {busy ? <Loader2 size={18} className="animate-spin" /> : <Store size={18} />} Enroll my restaurant
          </NeonBtn>
        </Card>
      ) : (
        <>
          <Card testid="merchant-connect">
            <div className="flex items-center justify-between">
              <div>
                <Label>Payouts · Stripe Connect</Label>
                <div className="flex items-center gap-2 mt-1">
                  {me.merchant?.stripe_account_id ? <BadgeCheck size={18} color={DINE.cyan} /> : <AlertTriangle size={18} color={DINE.gold} />}
                  <span className="font-bold" style={{ color: DINE.text }}>{me.merchant?.stripe_onboarding_status || "not_started"}</span>
                </div>
              </div>
              <GhostBtn testid="merchant-connect-btn" onClick={connect}><DollarSign size={16} /> {me.merchant?.stripe_account_id ? "Manage payouts" : "Set up payouts"}</GhostBtn>
            </div>
          </Card>

          {analytics && (
            <Card testid="merchant-analytics">
              <div className="flex items-center gap-2 mb-4"><BarChart3 size={16} color={DINE.cyan} /><Label>Performance</Label></div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <Metric v={analytics.appearances} l="In wheels" />
                <Metric v={analytics.wins} l="Selected" />
                <Metric v={analytics.redemptions} l="Redeemed" />
                <Metric v={money(analytics.earnings?.net_cents)} l="Earned (net)" color={DINE.gold} />
              </div>
            </Card>
          )}

          <Card testid="merchant-locations">
            <Label>Locations</Label>
            {(me.locations || []).map((l) => (
              <div key={l.location_id} className="rounded-2xl p-4 mt-3" style={{ background: DINE.panel, border: `1px solid ${DINE.border}` }} data-testid={`merchant-loc-${l.location_id}`}>
                <div className="flex items-center gap-2 font-bold" style={{ color: DINE.text }}><MapPin size={14} color={DINE.pink} />{l.name}</div>
                <p className="text-xs mb-3" style={{ color: DINE.muted }}>{l.address}</p>
                <div className="grid grid-cols-2 gap-2">
                  {["LUNCH:VEG", "LUNCH:NON_VEG", "DINNER:VEG", "DINNER:NON_VEG"].map((k) => (
                    <div key={k}>
                      <span className="text-[10px]" style={{ color: DINE.muted }}>{k.replace(":", " ")}</span>
                      <input type="number" min={0} defaultValue={(l.capacity || {})[k] ?? 0}
                        onBlur={(e) => saveCapacity(l.location_id, k, e.target.value)} data-testid={`cap-${l.location_id}-${k}`}
                        className="w-full rounded-lg px-3 py-2 mt-0.5 outline-none" style={{ background: DINE.bg, border: `1px solid ${DINE.border}`, color: DINE.text }} />
                    </div>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2 mt-3">
                  <input placeholder="Today's Veg meal" onBlur={(e) => e.target.value && saveMeal(l.location_id, "VEG", e.target.value)} data-testid={`meal-${l.location_id}-veg`}
                    className="rounded-lg px-3 py-2 outline-none text-sm" style={{ background: DINE.bg, border: `1px solid ${DINE.cyan}44`, color: DINE.text }} />
                  <input placeholder="Today's Non-Veg meal" onBlur={(e) => e.target.value && saveMeal(l.location_id, "NON_VEG", e.target.value)} data-testid={`meal-${l.location_id}-nonveg`}
                    className="rounded-lg px-3 py-2 outline-none text-sm" style={{ background: DINE.bg, border: `1px solid ${DINE.pink}44`, color: DINE.text }} />
                </div>
              </div>
            ))}
            <div className="mt-4">
              <Input placeholder="Location name" value={loc.name} onChange={(e) => setLoc({ ...loc, name: e.target.value })} data-testid="loc-name" />
              <Input placeholder="Address" value={loc.address} onChange={(e) => setLoc({ ...loc, address: e.target.value })} data-testid="loc-address" />
              <GhostBtn testid="loc-add" onClick={addLocation}><Plus size={16} /> Add location</GhostBtn>
            </div>
          </Card>

          <Card testid="merchant-webhooks">
            <div className="flex items-center gap-2 mb-3"><Webhook size={16} color={DINE.gold} /><Label>POS webhooks</Label></div>
            {(hooks?.webhooks || []).map((w) => (
              <div key={w.webhook_id} className="flex items-center justify-between rounded-xl px-3 py-2 mb-2" style={{ background: DINE.panel }}>
                <span className="text-xs truncate" style={{ color: DINE.text }}>{w.url}</span>
                <button onClick={() => delHook(w.webhook_id)} data-testid={`hook-del-${w.webhook_id}`}><Trash2 size={14} color={DINE.muted} /></button>
              </div>
            ))}
            <div className="flex gap-2 mt-2">
              <input placeholder="https://your-pos/webhook" value={hookUrl} onChange={(e) => setHookUrl(e.target.value)} data-testid="hook-url"
                className="flex-1 rounded-xl px-4 py-3 outline-none" style={{ background: DINE.panel, border: `1px solid ${DINE.border}`, color: DINE.text }} />
              <GhostBtn testid="hook-add" onClick={addHook}><Plus size={16} /> Add</GhostBtn>
            </div>
          </Card>
        </>
      )}
    </Shell>
  );
}

function Metric({ v, l, color }) {
  return (
    <div className="rounded-2xl p-3" style={{ background: DINE.panel }}>
      <div className="text-xl font-black" style={{ color: color || DINE.text }}>{v}</div>
      <span className="text-[10px] font-mono uppercase" style={{ color: DINE.muted }}>{l}</span>
    </div>
  );
}
