// RadioLife Merchant — services catalogue + incoming bookings (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Pencil, Trash2 } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const BOOK_NEXT = { confirmed: [{ label: "Mark Completed", status: "completed" }, { label: "No Show", status: "no_show" }] };

export default function MerchantServicesRadioLife() {
  const navigate = useNavigate();
  const [services, setServices] = useState([]);
  const [bookings, setBookings] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState({ name: "", description: "", duration: "30", price: "", fee: "", points: "" });
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, b] = await Promise.all([
        axios.get(`${API}/merchant/marketplace/services`),
        axios.get(`${API}/merchant/marketplace/services/bookings`),
      ]);
      setServices(s.data.items || []); setBookings(b.data.items || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm({ name: "", description: "", duration: "30", price: "", fee: "", points: "" }); setEditingId(null); };
  const save = async () => {
    if (!form.name.trim() || !form.price) return;
    setSaving(true);
    const body = { name: form.name.trim(), description: form.description.trim() || null,
      duration_min: parseInt(form.duration, 10) || 30, price_cents: Math.round((parseFloat(form.price) || 0) * 100),
      reservation_fee_cents: Math.round((parseFloat(form.fee) || 0) * 100),
      bigpoints: form.points ? parseInt(form.points, 10) : null, active: true };
    try {
      if (editingId) await axios.patch(`${API}/merchant/marketplace/services/items/${editingId}`, body);
      else await axios.post(`${API}/merchant/marketplace/services/items`, body);
      reset(); load();
    } catch { /* ignore */ } finally { setSaving(false); }
  };
  const edit = (s) => { setEditingId(s.service_id); setForm({ name: s.name || "", description: s.description || "", duration: String(s.duration_min || 30), price: ((s.price_cents || 0) / 100).toString(), fee: ((s.reservation_fee_cents || 0) / 100).toString(), points: s.bigpoints != null ? String(s.bigpoints) : "" }); };
  const del = async (id) => { try { await axios.delete(`${API}/merchant/marketplace/services/items/${id}`); load(); } catch { /* ignore */ } };
  const setBooking = async (id, status) => { try { await axios.patch(`${API}/merchant/marketplace/services/bookings/${id}/status`, { status }); load(); } catch { /* ignore */ } };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  const Input = (props) => <input {...props} className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />;

  return (
    <div className="pb-24" data-testid="rl-merchant-services-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="msvc-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Services &amp; Bookings</h1>
      </div>

      <div className="px-4 space-y-4">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-2">
          <div className="font-black text-slate-900">{editingId ? "Edit service" : "Add a service"}</div>
          <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Service name (e.g. Men Haircut)" data-testid="svc-name" />
          <Input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Description (optional)" data-testid="svc-desc" />
          <div className="grid grid-cols-3 gap-2">
            <Input value={form.duration} onChange={(e) => setForm({ ...form, duration: e.target.value })} placeholder="Mins" data-testid="svc-duration" />
            <Input value={form.price} onChange={(e) => setForm({ ...form, price: e.target.value })} placeholder="Price" data-testid="svc-price" />
            <Input value={form.fee} onChange={(e) => setForm({ ...form, fee: e.target.value })} placeholder="Reserve fee" data-testid="svc-fee" />
          </div>
          <Input value={form.points} onChange={(e) => setForm({ ...form, points: e.target.value })} placeholder="BigPoints on completion (optional)" data-testid="svc-points" />
          <div className="flex gap-2 pt-1">
            {editingId && <button onClick={reset} data-testid="svc-cancel" className="flex-1 border border-slate-200 rounded-full py-2.5 font-bold text-slate-600">Cancel</button>}
            <button onClick={save} disabled={saving} data-testid="svc-save" className="flex-1 bg-orange-600 text-white font-black rounded-full py-2.5 disabled:opacity-60">{editingId ? "Update" : "Add Service"}</button>
          </div>
        </div>

        <h3 className="text-base font-black text-slate-900">Your services</h3>
        {!services.length && <p className="text-slate-500 text-sm">No services yet.</p>}
        {services.map((sv) => (
          <div key={sv.service_id} className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl p-3" data-testid={`msvc-item-${sv.service_id}`}>
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">{sv.name}</div>
              <div className="text-xs font-black text-orange-600">{sv.duration_min} min · {money(sv.price_cents)}{sv.reservation_fee_cents > 0 ? ` · ${money(sv.reservation_fee_cents)} reserve` : ""}</div>
            </div>
            <button onClick={() => edit(sv)} data-testid={`msvc-edit-${sv.service_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Pencil size={15} className="text-blue-600" /></button>
            <button onClick={() => del(sv.service_id)} data-testid={`msvc-del-${sv.service_id}`} className="w-9 h-9 rounded-full bg-slate-50 flex items-center justify-center"><Trash2 size={15} className="text-rose-600" /></button>
          </div>
        ))}

        <h3 className="text-base font-black text-slate-900">Incoming bookings</h3>
        {!bookings.length && <p className="text-slate-500 text-sm" data-testid="msvc-bookings-empty">No paid bookings yet.</p>}
        {bookings.map((b) => (
          <div key={b.booking_id} className="bg-white border border-slate-200 rounded-xl p-4" data-testid={`msvc-booking-${b.booking_id}`}>
            <div className="flex items-center justify-between">
              <div className="text-sm font-black text-slate-900">{b.service_name}</div>
              <div className="text-xs font-black uppercase text-orange-600">{b.status}</div>
            </div>
            <div className="text-sm text-slate-500 font-semibold mt-1">{b.date} · {b.start_time} · {b.duration_min} min · rewards {b.points_to_award}</div>
            {(BOOK_NEXT[b.status] || []).length > 0 && (
              <div className="flex gap-2 mt-3">
                {BOOK_NEXT[b.status].map((a) => (
                  <button key={a.status} onClick={() => setBooking(b.booking_id, a.status)} data-testid={`msvc-book-${a.status}-${b.booking_id}`}
                    className={`flex-1 rounded-lg py-2.5 font-black ${a.status === "completed" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-600"}`}>{a.label}</button>
                ))}
              </div>
            )}
            {b.status === "completed" && <div className="text-green-600 text-xs font-bold mt-2">✓ {b.points_to_award} BigPoints awarded</div>}
          </div>
        ))}
      </div>
    </div>
  );
}
