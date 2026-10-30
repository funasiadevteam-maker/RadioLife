// FUUSIC Shop — My Trips. Booked BigPoints orders + saved flights/hotels/cars
// (My Trips Sync). Reads GET /api/travel/orders and GET /api/travel/saved.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Plane, BedDouble, Luggage, Compass, Ship, Car, Ticket, Users,
         ChevronLeft, X, ExternalLink } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${Math.round((c || 0) / 100)}`;
const TYPE_ICON = { flight: Plane, hotel: BedDouble, package: Luggage, experience: Compass, cruise: Ship, car: Car };

function fmtDate(iso) {
  try { return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }); }
  catch (_e) { return ""; }
}

function StatusBadge({ status }) {
  const s = (status || "confirmed").toLowerCase();
  const tone = s === "cancelled" ? "var(--live)" : "var(--success, #16a34a)";
  return (
    <span className="text-[10px] font-black text-white px-2 py-0.5 rounded-full capitalize" style={{ background: tone }}>
      {s}
    </span>
  );
}

function TripCard({ o }) {
  const Icon = TYPE_ICON[o.deal_type] || Plane;
  return (
    <div className="fz-card rounded-2xl overflow-hidden flex" data-testid={`trip-${o.order_id}`} style={{ boxShadow: "var(--card-shadow)" }}>
      <div className="w-28 shrink-0" style={{ background: "var(--surface-2)" }}>
        {o.image_url && <img src={o.image_url} alt={o.title} loading="lazy" className="w-full h-full object-cover" />}
      </div>
      <div className="flex-1 p-3 min-w-0">
        <div className="flex items-center gap-2">
          <Icon size={13} className="fz-brand shrink-0" />
          <span className="fz-text font-black truncate">{o.title}</span>
        </div>
        <div className="fz-muted text-xs truncate mt-0.5">{o.destination}</div>
        <div className="flex items-center gap-2 mt-2 flex-wrap">
          <StatusBadge status={o.status} />
          <span className="flex items-center gap-1 text-[11px] font-bold fz-sub">
            <Ticket size={11} /> {o.confirmation}
          </span>
          <span className="flex items-center gap-1 text-[11px] fz-muted">
            <Users size={11} /> {o.travelers}
          </span>
        </div>
        <div className="flex items-center justify-between mt-1.5">
          <span className="fz-text font-black">{money(o.total_cents)}</span>
          <span className="text-[11px] fz-muted">{fmtDate(o.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

function SavedCard({ s, onRemove }) {
  const Icon = TYPE_ICON[s.trip_type] || Plane;
  const body = (
    <div className="flex items-center gap-3 p-3">
      <div className="w-9 h-9 rounded-xl flex items-center justify-center fz-brand shrink-0" style={{ background: "var(--surface-2)" }}>
        <Icon size={16} />
      </div>
      <div className="min-w-0 flex-1">
        <div className="fz-text font-black truncate flex items-center gap-1">
          {s.title} {s.deep_link && <ExternalLink size={12} className="fz-muted shrink-0" />}
        </div>
        {s.subtitle && <div className="fz-muted text-xs truncate">{s.subtitle}</div>}
      </div>
      {s.price_label && <span className="fz-brand font-black text-sm shrink-0">{s.price_label}</span>}
    </div>
  );
  return (
    <div className="fz-card rounded-2xl overflow-hidden flex items-center" data-testid={`saved-${s.saved_id}`}>
      {s.deep_link
        ? <a href={s.deep_link} target="_blank" rel="noopener noreferrer" className="flex-1 min-w-0 hover:opacity-90">{body}</a>
        : <div className="flex-1 min-w-0">{body}</div>}
      <button onClick={() => onRemove(s)} data-testid={`saved-remove-${s.saved_id}`}
        className="px-3 fz-muted hover:text-red-500"><X size={16} /></button>
    </div>
  );
}

const SAVED_SECTIONS = [
  { key: "flights", label: "Saved flights", Icon: Plane },
  { key: "hotels", label: "Saved hotels", Icon: BedDouble },
  { key: "cars", label: "Saved cars", Icon: Car },
];

export default function ShopTravelTripsRadioLife() {
  const [orders, setOrders] = useState([]);
  const [saved, setSaved] = useState({ flights: [], hotels: [], cars: [] });
  const [loading, setLoading] = useState(true);

  const loadSaved = () => axios.get(`${API}/travel/saved`)
    .then((r) => setSaved({ flights: r.data?.flights || [], hotels: r.data?.hotels || [], cars: r.data?.cars || [] }))
    .catch(() => {});

  useEffect(() => {
    Promise.all([
      axios.get(`${API}/travel/orders`).then((r) => setOrders(r.data.items || [])).catch(() => {}),
      loadSaved(),
    ]).finally(() => setLoading(false));
  }, []);

  const removeSaved = async (s) => {
    setSaved((prev) => {
      const next = { ...prev };
      for (const k of ["flights", "hotels", "cars"]) next[k] = next[k].filter((x) => x.saved_id !== s.saved_id);
      return next;
    });
    await axios.delete(`${API}/travel/saved/${s.saved_id}`).catch(() => {});
  };

  const savedCount = saved.flights.length + saved.hotels.length + saved.cars.length;
  const empty = orders.length === 0 && savedCount === 0;

  return (
    <div className="px-4 pt-6 pb-8 space-y-5 fz-text" data-testid="rl-travel-trips">
      <Link to="/shop/travel" className="inline-flex items-center gap-1 fz-muted text-sm font-bold" data-testid="trips-back">
        <ChevronLeft size={16} /> Travel
      </Link>
      <header>
        <div className="fz-brand text-[11px] font-black tracking-widest">FUUSIC TRAVEL</div>
        <h1 className="text-3xl font-black tracking-tight fz-text leading-tight mt-1">My Trips</h1>
      </header>

      {loading ? (
        <div className="text-center fz-muted py-10">Loading your trips…</div>
      ) : empty ? (
        <div className="text-center py-12" data-testid="trips-empty">
          <div className="text-5xl mb-3">🧳</div>
          <div className="fz-text font-black">No trips yet</div>
          <div className="fz-muted text-sm mt-1">Book a deal or save a flight, hotel or car and it'll show up here.</div>
          <Link to="/shop/travel" className="fz-grad inline-block mt-4 rounded-full px-5 py-2.5 font-black" data-testid="trips-browse">
            Browse deals
          </Link>
        </div>
      ) : (
        <>
          {orders.length > 0 && (
            <section className="space-y-3" data-testid="trips-booked">
              <h2 className="text-sm font-black fz-text flex items-center gap-2"><Ticket size={15} className="fz-brand" /> Booked</h2>
              {orders.map((o) => <TripCard key={o.order_id} o={o} />)}
            </section>
          )}

          {SAVED_SECTIONS.map(({ key, label, Icon }) => (
            saved[key].length > 0 && (
              <section key={key} className="space-y-2" data-testid={`trips-saved-${key}`}>
                <h2 className="text-sm font-black fz-text flex items-center gap-2"><Icon size={15} className="fz-brand" /> {label}</h2>
                {saved[key].map((s) => <SavedCard key={s.saved_id} s={s} onRemove={removeSaved} />)}
              </section>
            )
          ))}
        </>
      )}
    </div>
  );
}
