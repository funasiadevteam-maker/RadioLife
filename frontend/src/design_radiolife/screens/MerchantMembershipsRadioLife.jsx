// RadioLife Merchant — create membership plans with benefit rules (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Trash2, Pencil, Crown, Plus, X } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const blankEnt = () => ({ label: "", qty: 1, period: "day", options: "" });

export default function MerchantMembershipsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", price: "", interval: "month" });
  const [ents, setEnts] = useState([blankEnt()]);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/merchant/marketplace/memberships`); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: "", description: "", price: "", interval: "month" }); setEnts([blankEnt()]); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const entitlements = ents.filter((e) => e.label.trim()).map((e) => ({
      label: e.label.trim(), qty: parseInt(e.qty, 10) || 1, period: e.period,
      options: (e.options || "").split(",").map((o) => o.trim()).filter(Boolean),
    }));
    const body = { name: form.name.trim(), description: form.description.trim() || null,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), interval: form.interval,
      entitlements, active: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/memberships/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/memberships/items`, body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p) => {
    setEditingId(p.plan_id);
    setForm({ name: p.name || "", description: p.description || "", price: ((p.price_cents || 0) / 100).toString(), interval: p.interval || "month" });
    setEnts((p.entitlements || []).map((e) => ({ label: e.label, qty: e.qty, period: e.period, options: (e.options || []).join(", ") })) || [blankEnt()]);
  };
  const del = async (pid) => { try { await axios.delete(`${API}/merchant/marketplace/memberships/items/${pid}`); load(); } catch { /* ignore */ } };
  const updEnt = (i, patch) => setEnts((a) => a.map((e, idx) => (idx === i ? { ...e, ...patch } : e)));

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  const Input = (props) => <input {...props} className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />;

  return (
    <div className="pb-24" data-testid="rl-merchant-memberships-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="mmem-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Memberships</h1>
      </div>

      <div className="px-4 space-y-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2" data-testid="mmem-form">
          <div className="font-black text-slate-900">{editingId ? "Edit membership" : "New membership"}</div>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name e.g. Coffee Club" data-testid="mmem-name" />
          <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" data-testid="mmem-desc" />
          <div className="grid grid-cols-2 gap-2">
            <Input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price / period" data-testid="mmem-price" />
            <select value={form.interval} onChange={(e) => setForm({ ...form, interval: e.target.value })} data-testid="mmem-interval"
              className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm">
              <option value="month">Monthly</option><option value="week">Weekly</option>
            </select>
          </div>

          <div className="pt-1 text-xs font-black text-slate-500 uppercase">Benefit rules</div>
          {ents.map((e, i) => (
            <div key={i} className="border border-slate-200 rounded-xl p-2 space-y-2" data-testid={`mmem-ent-${i}`}>
              <div className="flex gap-2">
                <input value={e.label} onChange={(ev) => updEnt(i, { label: ev.target.value })} placeholder="e.g. Free coffee" data-testid={`mmem-ent-label-${i}`}
                  className="flex-1 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
                {ents.length > 1 && <button onClick={() => setEnts((a) => a.filter((_, idx) => idx !== i))} data-testid={`mmem-ent-remove-${i}`} className="w-9 h-9 rounded-lg bg-slate-50 flex items-center justify-center"><X size={15} className="text-rose-600" /></button>}
              </div>
              <div className="flex gap-2">
                <input type="number" value={e.qty} onChange={(ev) => updEnt(i, { qty: ev.target.value })} placeholder="Qty" data-testid={`mmem-ent-qty-${i}`}
                  className="w-20 bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
                <select value={e.period} onChange={(ev) => updEnt(i, { period: ev.target.value })} data-testid={`mmem-ent-period-${i}`}
                  className="bg-slate-50 border border-slate-200 rounded-lg px-2 py-2 text-sm">
                  <option value="day">per day</option><option value="week">per week</option><option value="month">per month</option>
                </select>
              </div>
              <input value={e.options} onChange={(ev) => updEnt(i, { options: ev.target.value })} placeholder="Choices (comma) — leave blank for fixed" data-testid={`mmem-ent-options-${i}`}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
            </div>
          ))}
          <button onClick={() => setEnts((a) => [...a, blankEnt()])} data-testid="mmem-add-ent" className="flex items-center gap-1 text-orange-600 font-black text-sm"><Plus size={15} />Add benefit</button>

          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="mmem-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving} data-testid="mmem-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Create"}</button>
          </div>
        </div>

        {!items.length && <p className="text-slate-500 text-sm" data-testid="mmem-empty">No memberships yet.</p>}
        {items.map((p) => (
          <div key={p.plan_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`mmem-item-${p.plan_id}`}>
            <div className="w-10 h-10 rounded-lg bg-orange-50 flex items-center justify-center"><Crown size={18} className="text-orange-600" /></div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">{p.name} · {money(p.price_cents)}/{p.interval}</div>
              <div className="text-xs font-black text-slate-500">{(p.entitlements || []).length} benefits · {p.member_count || 0} members{!p.active ? " · inactive" : ""}</div>
            </div>
            <button onClick={() => edit(p)} data-testid={`mmem-edit-${p.plan_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
            <button onClick={() => del(p.plan_id)} data-testid={`mmem-del-${p.plan_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
