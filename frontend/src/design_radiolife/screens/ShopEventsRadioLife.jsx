// RadioLife Shop — buy tickets to venue events (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, CalendarDays, MapPin, Coins, CreditCard, Ticket, Minus, Plus } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => (c === 0 ? "Free" : `$${(c / 100).toFixed(2)}`);
const fmt = (s) => { try { return new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }); } catch { return s; } };

export default function ShopEventsRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/events/")[1];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [qty, setQty] = useState({});

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/shop/businesses/${id}/events`); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const q = (eid) => qty[eid] || 1;
  const setQ = (eid, v) => setQty((m) => ({ ...m, [eid]: Math.max(1, v) }));

  const buy = async (ev, method) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/shop/events/purchase`, { event_id: ev.event_id, qty: q(ev.event_id), method, origin_url: window.location.origin });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      load(); setBusy(false);
    } catch (e) { alert(e?.response?.data?.detail?.code || "Purchase failed"); setBusy(false); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Unavailable.</div>;
  const ppd = data.points_per_dollar || 100;

  return (
    <div className="pb-24" data-testid="rl-shop-events-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="evt-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900 truncate">{data.public_name} Events</h1>
      </div>

      <div className="px-4 space-y-4">
        {data.mine?.length > 0 && (
          <div className="rounded-2xl border-2 border-orange-300 bg-orange-50 p-4" data-testid="evt-mine">
            <div className="font-black text-slate-900 mb-2">Your tickets</div>
            {data.mine.map((t) => (
              <div key={t.ticket_id} className="bg-white rounded-xl p-3 mb-2 flex items-center justify-between" data-testid={`evt-ticket-${t.ticket_id}`}>
                <span className="font-bold text-slate-900 text-sm flex items-center gap-1.5"><Ticket size={15} className="text-orange-600" />{t.event_title} · {t.qty}×</span>
                <span className="text-xs font-black text-slate-500 font-mono">{t.code}</span>
              </div>
            ))}
          </div>
        )}

        {!data.items?.length && !data.mine?.length && <p className="text-center text-slate-500 mt-10" data-testid="evt-empty">No upcoming events here yet.</p>}

        {data.items.map((ev) => {
          const pointsCost = Math.round((ev.price_cents / 100) * ppd) * q(ev.event_id);
          const canPoints = ev.allow_points && (ev.price_cents === 0 || data.points_balance >= pointsCost);
          return (
            <div key={ev.event_id} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`evt-${ev.event_id}`}>
              <div className="flex items-center justify-between">
                <div className="font-black text-slate-900">{ev.title}</div>
                <div className="font-black text-orange-600">{money(ev.price_cents)}</div>
              </div>
              <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-1"><CalendarDays size={13} />{fmt(ev.starts_at)}</div>
              {ev.location && <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-0.5"><MapPin size={13} />{ev.location}</div>}
              {ev.description && <div className="text-sm text-slate-600 mt-1">{ev.description}</div>}
              <div className="text-xs font-black mt-2" data-testid={`evt-remaining-${ev.event_id}`}>
                {ev.sold_out ? <span className="text-rose-600">SOLD OUT</span> : <span className="text-green-600">{ev.remaining} tickets left</span>}
              </div>
              {!ev.sold_out && (
                <>
                  <div className="flex items-center gap-3 mt-3">
                    <button onClick={() => setQ(ev.event_id, q(ev.event_id) - 1)} data-testid={`evt-qty-minus-${ev.event_id}`} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center"><Minus size={14} /></button>
                    <span className="font-black w-6 text-center" data-testid={`evt-qty-${ev.event_id}`}>{q(ev.event_id)}</span>
                    <button onClick={() => setQ(ev.event_id, Math.min(ev.remaining, q(ev.event_id) + 1))} data-testid={`evt-qty-plus-${ev.event_id}`} className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center"><Plus size={14} /></button>
                  </div>
                  <div className="flex gap-2 mt-3">
                    {ev.allow_card && ev.price_cents > 0 && <button onClick={() => buy(ev, "card")} disabled={busy} data-testid={`evt-buy-card-${ev.event_id}`}
                      className="flex-1 flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-2.5 text-sm disabled:opacity-50"><CreditCard size={15} />Buy</button>}
                    {(ev.allow_points || ev.price_cents === 0) && <button onClick={() => buy(ev, "points")} disabled={busy || !canPoints} data-testid={`evt-buy-points-${ev.event_id}`}
                      className="flex-1 flex items-center justify-center gap-2 bg-slate-100 text-slate-700 font-black rounded-full py-2.5 text-sm disabled:opacity-40"><Coins size={15} />{ev.price_cents === 0 ? "Get free ticket" : `${pointsCost} pts`}</button>}
                  </div>
                </>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
