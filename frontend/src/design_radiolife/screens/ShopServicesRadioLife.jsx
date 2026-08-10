// RadioLife Shop — service booking (pick service, date, slot, reserve).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Calendar, Coins } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const iso = (d) => d.toISOString().slice(0, 10);
const dayLabel = (d) => d.toLocaleDateString("en-US", { weekday: "short", day: "numeric" });

export default function ShopServicesRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/services/")[1];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [dateIdx, setDateIdx] = useState(0);
  const [slots, setSlots] = useState([]);
  const [slotLoading, setSlotLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const dates = Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return d; });

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}/services`).then((r) => setData(r.data))
      .catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const loadSlots = useCallback(async (svc, di) => {
    if (!svc) return;
    setSlotLoading(true); setSlots([]);
    try {
      const r = await axios.get(`${API}/shop/businesses/${id}/services/${svc.service_id}/slots?date=${iso(dates[di])}`);
      setSlots(r.data.slots || []);
    } catch { setSlots([]); } finally { setSlotLoading(false); }
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const book = async (startTime) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/shop/service-bookings/checkout`, {
        business_id: id, service_id: selected.service_id, date: iso(dates[dateIdx]),
        start_time: startTime, origin_url: window.location.origin,
      });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      navigate("/shop/bookings");
    } catch { setBusy(false); loadSlots(selected, dateIdx); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Services unavailable.</div>;

  return (
    <div className="pb-24" data-testid="rl-shop-services-page">
      <div className="flex items-center justify-between gap-3 px-4 pt-4 pb-2">
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => navigate(-1)} data-testid="svc-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
          <h1 className="text-xl font-black text-slate-900 truncate">{data.public_name}</h1>
        </div>
        <button onClick={() => navigate("/shop/bookings")} data-testid="svc-bookings"><Calendar size={20} className="text-slate-700" /></button>
      </div>

      <div className="px-4">
        <h2 className="text-base font-black text-slate-900 mt-3 mb-2">Choose a service</h2>
        {(data.services || []).map((svc) => (
          <button key={svc.service_id} onClick={() => { setSelected(svc); setDateIdx(0); loadSlots(svc, 0); }}
            data-testid={`svc-${svc.service_id}`}
            className={`w-full text-left flex items-center gap-3 bg-white border rounded-xl p-3.5 mb-2 ${selected?.service_id === svc.service_id ? "border-orange-600" : "border-slate-200"}`}>
            {svc.image_url && <img src={svc.image_url} alt={svc.name} className="w-14 h-14 rounded-lg object-cover bg-slate-100" />}
            <div className="flex-1 min-w-0">
              <div className="text-sm font-bold text-slate-900">{svc.name}</div>
              {svc.description && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{svc.description}</div>}
              <div className="text-xs font-black text-orange-600 mt-1">{svc.duration_min} min · {money(svc.price_cents)}{svc.reservation_fee_cents > 0 ? ` · ${money(svc.reservation_fee_cents)} reservation` : ""}</div>
            </div>
          </button>
        ))}
        {(!data.services || !data.services.length) && <p className="text-slate-500 mt-3">No services published yet.</p>}

        {selected && (
          <>
            <h2 className="text-base font-black text-slate-900 mt-6 mb-2">Pick a day</h2>
            <div className="flex gap-2 overflow-x-auto pb-1">
              {dates.map((d, i) => (
                <button key={i} onClick={() => { setDateIdx(i); loadSlots(selected, i); }} data-testid={`svc-date-${i}`}
                  className={`shrink-0 px-4 h-11 rounded-full font-black text-sm ${dateIdx === i ? "bg-orange-600 text-white" : "bg-white border border-slate-200 text-slate-700"}`}>{dayLabel(d)}</button>
              ))}
            </div>

            <h2 className="text-base font-black text-slate-900 mt-6 mb-2">Available times</h2>
            {slotLoading ? <p className="text-slate-500">Loading…</p>
              : slots.length ? (
                <div className="flex flex-wrap gap-2">
                  {slots.map((t) => (
                    <button key={t} onClick={() => book(t)} disabled={busy} data-testid={`svc-slot-${t}`}
                      className="px-4 py-3 rounded-lg bg-orange-50 text-orange-600 font-black disabled:opacity-50">{t}</button>
                  ))}
                </div>
              ) : <p className="text-slate-500" data-testid="svc-no-slots">No open times that day.</p>}
            {selected.reservation_fee_cents > 0 && (
              <p className="text-xs text-slate-500 mt-4 leading-relaxed">You'll pay {money(selected.reservation_fee_cents)} now to reserve — credited toward your {money(selected.price_cents)} service.</p>
            )}
          </>
        )}
      </div>
    </div>
  );
}
