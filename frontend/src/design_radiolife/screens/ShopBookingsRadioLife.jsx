// RadioLife Shop — my service bookings (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Coins, Calendar } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const LABELS = { pending_payment: "Awaiting Payment", confirmed: "Confirmed", completed: "Completed", canceled: "Canceled", no_show: "No Show" };

export default function ShopBookingsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/shop/service-bookings`);
      const list = r.data.items || [];
      await Promise.all(list.filter((b) => b.payment_status !== "paid" && b.session_id)
        .map((b) => axios.get(`${API}/shop/service-bookings/${b.booking_id}/status`).catch(() => null)));
      const r2 = await axios.get(`${API}/shop/service-bookings`);
      setItems(r2.data.items || []);
    } catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  return (
    <div className="pb-24" data-testid="rl-shop-bookings-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="bookings-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">My Bookings</h1>
      </div>
      <div className="px-4 space-y-3">
        {!items.length && (
          <div className="text-center text-slate-500 mt-16" data-testid="bookings-empty">
            <Calendar size={44} className="mx-auto text-slate-300" /><p className="mt-3 font-semibold">No bookings yet.</p>
          </div>
        )}
        {items.map((b) => (
          <div key={b.booking_id} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`booking-${b.booking_id}`}>
            <div className="flex items-center justify-between gap-2">
              <div className="font-black text-slate-900 truncate">{b.business_name}</div>
              <span className="text-xs font-black px-3 py-1.5 rounded-full bg-slate-100 text-slate-700" data-testid={`booking-status-${b.booking_id}`}>{LABELS[b.status] || b.status}</span>
            </div>
            <div className="text-sm font-bold text-slate-900 mt-1">{b.service_name}</div>
            <div className="text-sm text-slate-500 font-semibold">{b.date} · {b.start_time} · {b.duration_min} min</div>
            <div className="flex items-center justify-between mt-3">
              <div className="text-sm font-bold text-slate-900">{money(b.price_cents)}{b.reservation_fee_cents > 0 ? ` · ${money(b.reservation_fee_cents)} paid` : ""}</div>
              <div className="flex items-center gap-1 bg-amber-100 px-3 py-1.5 rounded-full text-xs font-black text-amber-950"><Coins size={13} />{b.points_awarded_done ? `+${b.points_to_award}` : `${b.points_to_award} on visit`}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
