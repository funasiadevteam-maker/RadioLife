// RadioLife Merchant — membership plans as a true entitlement engine (web).
// Each entitlement targets items/categories, waives the base (+ chosen
// included options), and enforces quantity, reset frequency, rollover,
// day/time windows, stackability and an upgrade cap.
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Trash2, Pencil, Crown, Plus, X, Check } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const FREQS = [["daily", "Daily"], ["weekly", "Weekly"], ["monthly", "Monthly"], ["billing_cycle", "Billing cycle"], ["total", "One-time"]];
const blankEnt = () => ({
  label: "", target_type: "any", category: "", target_ids: [], included_option_ids: [],
  quantity: 1, reset_frequency: "monthly", rollover: false, rollover_cap: 0,
  days: [], start_hour: "", end_hour: "", stackable: false, max_upcharge: "",
});

export default function MerchantMembershipsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [canOffer, setCanOffer] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", price: "", interval: "month" });
  const [ents, setEnts] = useState([blankEnt()]);
  const [catalog, setCatalog] = useState([]); // {id, name, category, options:[{id,label}]}

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/merchant/marketplace/memberships`); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    (async () => {
      try {
        const [sub, pl] = await Promise.all([
          axios.get(`${API}/merchant/marketplace/subscription`),
          axios.get(`${API}/merchant/marketplace/subscription/plans`),
        ]);
        const planId = sub.data?.subscription?.plan_id;
        const plan = (pl.data?.items || []).find((x) => x.plan_id === planId);
        setCanOffer(!!(sub.data?.active && plan?.can_offer_memberships));
      } catch { /* default allow */ }
    })();
  }, []);

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/merchant/marketplace/menu`).catch(() => ({ data: { items: [] } })),
      axios.get(`${API}/merchant/marketplace/products`).catch(() => ({ data: { items: [] } })),
    ]).then(([m, p]) => {
      const menu = (m.data.items || []).map((it) => ({ id: it.item_id, name: it.name, category: it.section, options: (it.option_groups || []).flatMap((g) => g.options) }));
      const prods = (p.data.items || []).map((x) => ({ id: x.product_id, name: x.name, category: x.category, options: (x.option_groups || []).flatMap((g) => g.options) }));
      setCatalog([...menu, ...prods]);
    });
  }, []);

  const categories = useMemo(() => [...new Set(catalog.map((c) => c.category).filter(Boolean))], [catalog]);
  const optionChoices = useMemo(() => {
    const seen = {};
    catalog.forEach((c) => c.options.forEach((o) => { if (!seen[o.option_id]) seen[o.option_id] = { id: o.option_id, label: o.label }; }));
    return Object.values(seen);
  }, [catalog]);

  const reset = () => { setForm({ name: "", description: "", price: "", interval: "month" }); setEnts([blankEnt()]); setEditingId(null); };
  const updEnt = (i, patch) => setEnts((a) => a.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));
  const toggleIn = (i, key, val) => setEnts((a) => a.map((e, idx) => {
    if (idx !== i) return e;
    const set = new Set(e[key]); set.has(val) ? set.delete(val) : set.add(val);
    return { ...e, [key]: [...set] };
  }));

  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const entitlements = ents.filter((e) => e.label.trim()).map((e) => {
      const dt = (e.days.length || e.start_hour !== "" || e.end_hour !== "")
        ? { days: e.days, start_hour: e.start_hour === "" ? null : Number(e.start_hour), end_hour: e.end_hour === "" ? null : Number(e.end_hour) } : null;
      return {
        label: e.label.trim(), target_type: e.target_type,
        category: e.target_type === "category" ? (e.category || null) : null,
        target_ids: ["item", "product"].includes(e.target_type) ? e.target_ids : [],
        included_option_ids: e.included_option_ids,
        quantity: parseInt(e.quantity, 10) || 1, reset_frequency: e.reset_frequency,
        rollover: !!e.rollover, rollover_cap: e.rollover ? (parseInt(e.rollover_cap, 10) || 0) : 0,
        day_time: dt, stackable: !!e.stackable,
        max_upcharge_cents: e.max_upcharge === "" ? null : Math.round((parseFloat(e.max_upcharge) || 0) * 100),
        active: true,
      };
    });
    const body = { name: form.name.trim(), description: form.description.trim() || null,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), interval: form.interval, entitlements, active: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/memberships/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/memberships/items`, body);
      reset(); load();
    } catch (e) { if (e?.response?.status === 403) setCanOffer(false); }
    finally { setSaving(false); }
  };

  const edit = (p) => {
    setEditingId(p.plan_id);
    setForm({ name: p.name || "", description: p.description || "", price: ((p.price_cents || 0) / 100).toString(), interval: p.interval || "month" });
    setEnts((p.entitlements || []).map((e) => ({
      label: e.label || "", target_type: e.target_type || "any", category: e.category || "",
      target_ids: e.target_ids || [], included_option_ids: e.included_option_ids || [],
      quantity: e.quantity || 1, reset_frequency: e.reset_frequency || "monthly",
      rollover: !!e.rollover, rollover_cap: e.rollover_cap || 0,
      days: e.day_time?.days || [], start_hour: e.day_time?.start_hour ?? "", end_hour: e.day_time?.end_hour ?? "",
      stackable: !!e.stackable, max_upcharge: e.max_upcharge_cents == null ? "" : (e.max_upcharge_cents / 100).toString(),
    })) || [blankEnt()]);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const del = async (pid) => { try { await axios.delete(`${API}/merchant/marketplace/memberships/items/${pid}`); load(); } catch { /* ignore */ } };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  const inp = "w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm";
  const effectiveCanOffer = canOffer || items.length > 0;

  return (
    <div className="pb-24" data-testid="rl-merchant-memberships-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="mmem-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Memberships</h1>
      </div>

      <div className="px-4 space-y-4">
        {!effectiveCanOffer && (
          <div className="bg-amber-50 border border-amber-300 rounded-2xl p-4" data-testid="mmem-upgrade-gate">
            <div className="font-black text-slate-900 flex items-center gap-1.5"><Crown size={16} className="text-amber-600" />Memberships are a Pro feature</div>
            <p className="text-sm text-slate-600 mt-1">Upgrade to the Pro shop plan to create &amp; sell memberships with the entitlement engine.</p>
            <button onClick={() => navigate("/shop/merchant/subscribe")} data-testid="mmem-upgrade-btn" className="mt-2 bg-orange-600 text-white font-black rounded-full px-4 py-2 text-sm">Upgrade to Pro</button>
          </div>
        )}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2" data-testid="mmem-form">
          <div className="font-black text-slate-900">{editingId ? "Edit membership" : "New membership"}</div>
          <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name e.g. Pizza Club" data-testid="mmem-name" className={inp} />
          <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" data-testid="mmem-desc" className={inp} />
          <div className="grid grid-cols-2 gap-2">
            <input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price / period ($)" data-testid="mmem-price" className={inp} />
            <select value={form.interval} onChange={(e) => setForm({ ...form, interval: e.target.value })} data-testid="mmem-interval" className={inp}>
              <option value="month">Monthly</option><option value="week">Weekly</option>
            </select>
          </div>

          <div className="pt-1 text-xs font-black text-slate-500 uppercase">Entitlements</div>
          {ents.map((e, i) => (
            <div key={i} className="border border-slate-200 rounded-xl p-3 space-y-2.5" data-testid={`mmem-ent-${i}`}>
              <div className="flex gap-2">
                <input value={e.label} onChange={(ev) => updEnt(i, { label: ev.target.value })} placeholder="Perk name e.g. Free Pizza (Medium)" data-testid={`mmem-ent-label-${i}`} className={"flex-1 " + inp} />
                {ents.length > 1 && <button onClick={() => setEnts((a) => a.filter((_, idx) => idx !== i))} data-testid={`mmem-ent-remove-${i}`} className="w-9 h-9 rounded-lg bg-slate-50 flex items-center justify-center"><X size={15} className="text-rose-600" /></button>}
              </div>

              {/* Target */}
              <div className="flex gap-2 items-center">
                <span className="text-xs font-black text-slate-500 w-16">Applies to</span>
                <select value={e.target_type} onChange={(ev) => updEnt(i, { target_type: ev.target.value })} data-testid={`mmem-ent-target-${i}`} className={inp}>
                  <option value="any">Anything</option><option value="category">A category</option><option value="item">Specific items</option>
                </select>
              </div>
              {e.target_type === "category" && (
                <select value={e.category} onChange={(ev) => updEnt(i, { category: ev.target.value })} data-testid={`mmem-ent-category-${i}`} className={inp}>
                  <option value="">Choose category…</option>
                  {categories.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
              )}
              {e.target_type === "item" && (
                <div className="flex flex-wrap gap-1.5" data-testid={`mmem-ent-items-${i}`}>
                  {catalog.map((c) => (
                    <button key={c.id} onClick={() => toggleIn(i, "target_ids", c.id)}
                      className={"px-2.5 py-1 rounded-full text-[11px] font-bold border " + (e.target_ids.includes(c.id) ? "bg-orange-600 text-white border-orange-600" : "bg-white text-slate-600 border-slate-200")}>
                      {e.target_ids.includes(c.id) && <Check size={10} className="inline mr-1" />}{c.name}
                    </button>
                  ))}
                </div>
              )}

              {/* Included (free) options */}
              {optionChoices.length > 0 && (
                <div>
                  <div className="text-xs font-black text-slate-500 mb-1">Included free (base upgrades waived)</div>
                  <div className="flex flex-wrap gap-1.5" data-testid={`mmem-ent-included-${i}`}>
                    {optionChoices.map((o) => (
                      <button key={o.id} onClick={() => toggleIn(i, "included_option_ids", o.id)}
                        className={"px-2.5 py-1 rounded-full text-[11px] font-bold border " + (e.included_option_ids.includes(o.id) ? "bg-green-600 text-white border-green-600" : "bg-white text-slate-600 border-slate-200")}>
                        {e.included_option_ids.includes(o.id) && <Check size={10} className="inline mr-1" />}{o.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Quantity + reset */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="text-[11px] font-bold text-slate-400">Quantity</div>
                  <input type="number" min={1} value={e.quantity} onChange={(ev) => updEnt(i, { quantity: ev.target.value })} data-testid={`mmem-ent-qty-${i}`} className={inp} />
                </div>
                <div>
                  <div className="text-[11px] font-bold text-slate-400">Resets</div>
                  <select value={e.reset_frequency} onChange={(ev) => updEnt(i, { reset_frequency: ev.target.value })} data-testid={`mmem-ent-reset-${i}`} className={inp}>
                    {FREQS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
              </div>

              {/* Upgrade cap */}
              <div>
                <div className="text-[11px] font-bold text-slate-400">Max upgrade covered ($, optional)</div>
                <input value={e.max_upcharge} onChange={(ev) => updEnt(i, { max_upcharge: ev.target.value })} placeholder="e.g. 10.00" data-testid={`mmem-ent-cap-${i}`} className={inp} />
              </div>

              {/* Day/time window */}
              <div>
                <div className="text-[11px] font-bold text-slate-400 mb-1">Days (optional)</div>
                <div className="flex flex-wrap gap-1.5" data-testid={`mmem-ent-days-${i}`}>
                  {DAYS.map((d, di) => (
                    <button key={d} onClick={() => toggleIn(i, "days", di)}
                      className={"px-2.5 py-1 rounded-full text-[11px] font-bold border " + (e.days.includes(di) ? "bg-orange-600 text-white border-orange-600" : "bg-white text-slate-600 border-slate-200")}>{d}</button>
                  ))}
                </div>
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <input type="number" min={0} max={23} value={e.start_hour} onChange={(ev) => updEnt(i, { start_hour: ev.target.value })} placeholder="Start hour (0-23)" data-testid={`mmem-ent-start-${i}`} className={inp} />
                  <input type="number" min={0} max={24} value={e.end_hour} onChange={(ev) => updEnt(i, { end_hour: ev.target.value })} placeholder="End hour (0-24)" data-testid={`mmem-ent-end-${i}`} className={inp} />
                </div>
              </div>

              <div className="flex flex-wrap gap-3 pt-1">
                <label className="flex items-center gap-1.5 text-xs font-bold text-slate-600" data-testid={`mmem-ent-stackable-${i}`}>
                  <input type="checkbox" checked={e.stackable} onChange={(ev) => updEnt(i, { stackable: ev.target.checked })} className="accent-orange-600" />Stack with coupons
                </label>
                <label className="flex items-center gap-1.5 text-xs font-bold text-slate-600" data-testid={`mmem-ent-rollover-${i}`}>
                  <input type="checkbox" checked={e.rollover} onChange={(ev) => updEnt(i, { rollover: ev.target.checked })} className="accent-orange-600" />Roll over unused
                </label>
                {e.rollover && <input type="number" min={0} value={e.rollover_cap} onChange={(ev) => updEnt(i, { rollover_cap: ev.target.value })} placeholder="Rollover cap" data-testid={`mmem-ent-rollcap-${i}`} className="w-28 bg-slate-50 border border-slate-200 rounded-lg px-2 py-1 text-sm" />}
              </div>
            </div>
          ))}
          <button onClick={() => setEnts((a) => [...a, blankEnt()])} data-testid="mmem-add-ent" className="flex items-center gap-1 text-orange-600 font-black text-sm"><Plus size={15} />Add entitlement</button>

          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="mmem-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving || (!effectiveCanOffer && !editingId)} data-testid="mmem-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Create"}</button>
          </div>
        </div>

        {!items.length && <p className="text-slate-500 text-sm" data-testid="mmem-empty">No memberships yet.</p>}
        {items.map((p) => (
          <div key={p.plan_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`mmem-item-${p.plan_id}`}>
            <div className="w-10 h-10 rounded-lg bg-orange-50 flex items-center justify-center"><Crown size={18} className="text-orange-600" /></div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">{p.name} · {money(p.price_cents)}/{p.interval}</div>
              <div className="text-xs font-black text-slate-500">{(p.entitlements || []).length} entitlements · {p.member_count || 0} members{!p.active ? " · inactive" : ""}</div>
            </div>
            <button onClick={() => edit(p)} data-testid={`mmem-edit-${p.plan_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
            <button onClick={() => del(p.plan_id)} data-testid={`mmem-del-${p.plan_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
