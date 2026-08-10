// RadioLife Merchant — sell prepaid packages / bundles (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Trash2, Pencil, Package as Pkg } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function MerchantPackagesRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", price: "", credits: "", allowPoints: true, allowCard: true });

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/merchant/marketplace/packages`); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: "", description: "", price: "", credits: "", allowPoints: true, allowCard: true }); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price || !form.credits) return;
    setSaving(true);
    const body = { name: form.name.trim(), description: form.description.trim() || null,
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), credits: parseInt(form.credits, 10) || 1,
      allow_points: form.allowPoints, allow_card: form.allowCard, active: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/packages/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/packages/items`, body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (p) => { setEditingId(p.package_id); setForm({ name: p.name || "", description: p.description || "", price: ((p.price_cents || 0) / 100).toString(), credits: String(p.credits || ""), allowPoints: p.allow_points, allowCard: p.allow_card }); };
  const del = async (pid) => { try { await axios.delete(`${API}/merchant/marketplace/packages/items/${pid}`); load(); } catch { /* ignore */ } };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  const Input = (props) => <input {...props} className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />;

  return (
    <div className="pb-24" data-testid="rl-merchant-packages-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="mpkg-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Packages</h1>
      </div>

      <div className="px-4 space-y-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2" data-testid="mpkg-form">
          <div className="font-black text-slate-900">{editingId ? "Edit package" : "New package"}</div>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Name e.g. 5 Haircuts" data-testid="mpkg-name" />
          <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" data-testid="mpkg-desc" />
          <div className="grid grid-cols-2 gap-2">
            <Input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price" data-testid="mpkg-price" />
            <Input value={form.credits} onChange={(e) => setForm({ ...form, credits: e.target.value })} placeholder="Credits (redemptions)" data-testid="mpkg-credits" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-slate-700">Allow pay by card</span>
            <input type="checkbox" checked={form.allowCard} onChange={(e) => setForm({ ...form, allowCard: e.target.checked })} data-testid="mpkg-allow-card" className="w-5 h-5 accent-orange-600" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-slate-700">Allow pay by BigPoints</span>
            <input type="checkbox" checked={form.allowPoints} onChange={(e) => setForm({ ...form, allowPoints: e.target.checked })} data-testid="mpkg-allow-points" className="w-5 h-5 accent-orange-600" />
          </div>
          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="mpkg-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving} data-testid="mpkg-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Create"}</button>
          </div>
        </div>

        {!items.length && <p className="text-slate-500 text-sm" data-testid="mpkg-empty">No packages yet.</p>}
        {items.map((p) => (
          <div key={p.package_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`mpkg-item-${p.package_id}`}>
            <div className="w-10 h-10 rounded-lg bg-orange-50 flex items-center justify-center"><Pkg size={18} className="text-orange-600" /></div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">{p.name} · {money(p.price_cents)}</div>
              <div className="text-xs font-black text-slate-500">{p.credits} credits · {p.sold_count || 0} sold{!p.active ? " · inactive" : ""}</div>
            </div>
            <button onClick={() => edit(p)} data-testid={`mpkg-edit-${p.package_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
            <button onClick={() => del(p.package_id)} data-testid={`mpkg-del-${p.package_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
