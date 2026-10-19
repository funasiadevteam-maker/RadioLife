// FUUSIC Shop — My Trips (booked travel orders).
// Rendered via screenFor() inside ShopInShell. Reads GET /api/travel/orders.
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Plane, BedDouble, Luggage, Compass, Ship, Ticket, Users, ChevronLeft } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${Math.round((c || 0) / 100)}`;
const TYPE_ICON = { flight: Plane, hotel: BedDouble, package: Luggage, experience: Compass, cruise: Ship };

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

export default function ShopTravelTripsRadioLife() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    axios.get(`${API}/travel/orders`)
      .then((r) => setItems(r.data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="px-4 pt-6 pb-8 space-y-4 fz-text" data-testid="rl-travel-trips">
      <Link to="/shop/travel" className="inline-flex items-center gap-1 fz-muted text-sm font-bold" data-testid="trips-back">
        <ChevronLeft size={16} /> Travel
      </Link>
      <header>
        <div className="fz-brand text-[11px] font-black tracking-widest">FUUSIC TRAVEL</div>
        <h1 className="text-3xl font-black tracking-tight fz-text leading-tight mt-1">My Trips</h1>
      </header>

      {loading ? (
        <div className="text-center fz-muted py-10">Loading your trips…</div>
      ) : items.length === 0 ? (
        <div className="text-center py-12" data-testid="trips-empty">
          <div className="text-5xl mb-3">🧳</div>
          <div className="fz-text font-black">No trips yet</div>
          <div className="fz-muted text-sm mt-1">Book a deal and it'll show up here with your confirmation.</div>
          <Link to="/shop/travel" className="fz-grad inline-block mt-4 rounded-full px-5 py-2.5 font-black" data-testid="trips-browse">
            Browse deals
          </Link>
        </div>
      ) : (
        <div className="space-y-3" data-testid="trips-list">
          {items.map((o) => <TripCard key={o.order_id} o={o} />)}
        </div>
      )}
    </div>
  );
}
