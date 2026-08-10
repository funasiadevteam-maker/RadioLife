// RadioLife Merchant — create ticketed events with limited capacity (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Trash2, Pencil, CalendarDays } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => (c === 0 ? "Free" : `$${(c / 100).toFixed(2)}`);

export default function MerchantEventsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", location: "", startsAt: "", price: "", capacity: "", allowPoints: true, allowCard: true });

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/merchant/marketplace/events`); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ title: "", description: "", location: "", startsAt: "", price: "", capacity: "", allowPoints: true, allowCard: true }); setEditingId(null); };
  const save = async () => {
    if (!form.title.trim() || !form.startsAt || !form.capacity) return;
    setSaving(true);
    const body = { title: form.title.trim(), description: form.description.trim() || null,
      location: form.location.trim() || null, starts_at: new Date(form.startsAt).toISOString(),
      price_cents: Math.round((parseFloat(form.price) || 0) * 100), capacity: parseInt(form.capacity, 10) || 1,
      allow_points: form.allowPoints, allow_card: form.allowCard, active: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/events/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/events/items`, body);
      reset(); load();
    } catch (e) { alert(e?.response?.data?.detail?.code || "Save failed"); } finally { setSaving(false); }
  };
  const edit = (ev) => {
    setEditingId(ev.event_id);
    let local = ""; try { const d = new Date(ev.starts_at); local = new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 16); } catch { local = ""; }
    setForm({ title: ev.title || "", description: ev.description || "", location: ev.location || "", startsAt: local, price: ((ev.price_cents || 0) / 100).toString(), capacity: String(ev.capacity || ""), allowPoints: ev.allow_points, allowCard: ev.allow_card });
  };
  const del = async (eid) => { try { await axios.delete(`${API}/merchant/marketplace/events/items/${eid}`); load(); } catch { /* ignore */ } };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  const Input = (props) => <input {...props} className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />;

  return (
    <div className="pb-24" data-testid="rl-merchant-events-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="mevt-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Events</h1>
      </div>

      <div className="px-4 space-y-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2" data-testid="mevt-form">
          <div className="font-black text-slate-900">{editingId ? "Edit event" : "New event"}</div>
          <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Title e.g. Live Jazz Night" data-testid="mevt-title" />
          <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" data-testid="mevt-desc" />
          <Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder="Location (optional)" data-testid="mevt-location" />
          <Input type="datetime-local" value={form.startsAt} onChange={(e) => setForm({ ...form, startsAt: e.target.value })} data-testid="mevt-startsat" />
          <div className="grid grid-cols-2 gap-2">
            <Input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price (0 = free)" data-testid="mevt-price" />
            <Input value={form.capacity} onChange={(e) => setForm({ ...form, capacity: e.target.value })} placeholder="Capacity" data-testid="mevt-capacity" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-slate-700">Allow pay by card</span>
            <input type="checkbox" checked={form.allowCard} onChange={(e) => setForm({ ...form, allowCard: e.target.checked })} data-testid="mevt-allow-card" className="w-5 h-5 accent-orange-600" />
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm font-bold text-slate-700">Allow pay by BigPoints</span>
            <input type="checkbox" checked={form.allowPoints} onChange={(e) => setForm({ ...form, allowPoints: e.target.checked })} data-testid="mevt-allow-points" className="w-5 h-5 accent-orange-600" />
          </div>
          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="mevt-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving} data-testid="mevt-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Create"}</button>
          </div>
        </div>

        {!items.length && <p className="text-slate-500 text-sm" data-testid="mevt-empty">No events yet.</p>}
        {items.map((ev) => (
          <div key={ev.event_id} className="flex items-center gap-3 bg-white border border-slate-200 rounded-xl p-3" data-testid={`mevt-item-${ev.event_id}`}>
            <div className="w-10 h-10 rounded-lg bg-orange-50 flex items-center justify-center"><CalendarDays size={18} className="text-orange-600" /></div>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900 truncate">{ev.title} · {money(ev.price_cents)}</div>
              <div className="text-xs font-black text-slate-500">{ev.tickets_sold}/{ev.capacity} sold{ev.sold_out ? " · SOLD OUT" : ""}{!ev.active ? " · inactive" : ""}</div>
            </div>
            <button onClick={() => edit(ev)} data-testid={`mevt-edit-${ev.event_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
            <button onClick={() => del(ev.event_id)} data-testid={`mevt-del-${ev.event_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
          </div>
        ))}
      </div>
    </div>
  );
}
