// FUUSIC Shop — Travel vertical (browse / search / follow).
// Curated travel deals (flights · hotels · packages · experiences · cruises).
// Following "Travel deals" surfaces recommended deals in the social wall.
import React, { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Search, Plane, BedDouble, Luggage, Compass, Ship, Star, Coins, Bell, BellRing } from "lucide-react";
import { API } from "@/AuthContext";
import TravelLiveSearch from "./TravelLiveSearch";
import TravelTrending from "./TravelTrending";

const money = (c) => `$${Math.round((c || 0) / 100)}`;

const TYPE_META = {
  all: { label: "All", Icon: Compass },
  flight: { label: "Flights", Icon: Plane },
  hotel: { label: "Hotels", Icon: BedDouble },
  package: { label: "Packages", Icon: Luggage },
  experience: { label: "Experiences", Icon: Compass },
  cruise: { label: "Cruises", Icon: Ship },
};
const TYPES = ["all", "flight", "hotel", "package", "experience", "cruise"];

function Chip({ active, children, ...props }) {
  return (
    <button type="button"
      className={`shrink-0 whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-bold transition-colors active:scale-95 ${active ? "fz-chip-active" : "fz-chip"}`}
      {...props}>{children}</button>
  );
}

function DealCard({ d }) {
  const TM = TYPE_META[d.deal_type] || TYPE_META.all;
  return (
    <Link to={`/shop/travel/${d.deal_id}`} data-testid={`travel-deal-${d.deal_id}`}
      className="fz-card block rounded-2xl overflow-hidden transition-transform hover:-translate-y-1"
      style={{ boxShadow: "var(--card-shadow)" }}>
      <div className="relative aspect-[4/3]" style={{ background: "var(--surface-2)" }}>
        {d.image_url && <img src={d.image_url} alt={d.title} loading="lazy" className="w-full h-full object-cover" />}
        <span className="absolute top-2 left-2 flex items-center gap-1 text-[10px] font-black text-white px-2 py-0.5 rounded-full" style={{ background: "var(--brand-solid)" }}>
          <TM.Icon size={11} /> {TM.label}
        </span>
        {d.promoted && (
          <span className="absolute top-2 right-2 text-[10px] font-black text-white px-2 py-0.5 rounded-full" style={{ background: "var(--live)" }}>DEAL</span>
        )}
        <span className="absolute bottom-2 right-2 flex items-center gap-1 text-[11px] font-black px-2 py-1 rounded-full" style={{ background: "var(--bigpoints-gold)", color: "#3a2a00" }}>
          <Coins size={11} /> +{d.bigpoints}
        </span>
      </div>
      <div className="p-3">
        <div className="fz-text font-black truncate">{d.title}</div>
        <div className="fz-muted text-xs truncate mt-0.5">{d.destination}</div>
        <div className="flex items-center justify-between mt-1.5">
          <div className="flex items-baseline gap-1.5">
            <span className="fz-text font-black">{money(d.price_cents)}</span>
            {d.strike_cents ? <span className="text-[11px] fz-muted line-through">{money(d.strike_cents)}</span> : null}
            {d.duration ? <span className="text-[11px] fz-muted">· {d.duration}</span> : null}
          </div>
          {d.rating ? <span className="flex items-center gap-1 text-xs font-bold fz-sub">
            <Star size={11} style={{ color: "var(--bigpoints-gold)", fill: "var(--bigpoints-gold)" }} />{d.rating.toFixed(1)}</span> : null}
        </div>
      </div>
    </Link>
  );
}

export default function ShopTravelRadioLife() {
  const [items, setItems] = useState([]);
  const [type, setType] = useState("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("featured");
  const [loading, setLoading] = useState(true);
  const [following, setFollowing] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);

  useEffect(() => {
    axios.get(`${API}/travel/follow`).then((r) => setFollowing(!!r.data?.following)).catch(() => {});
  }, []);

  useEffect(() => {
    setLoading(true);
    const params = { sort };
    if (type !== "all") params.type = type;
    if (q.trim()) params.q = q.trim();
    axios.get(`${API}/travel/deals`, { params })
      .then((r) => setItems(r.data.items || []))
      .catch(() => setItems([]))
      .finally(() => setLoading(false));
  }, [type, q, sort]);

  const toggleFollow = async () => {
    setFollowBusy(true);
    const next = !following;
    setFollowing(next);
    try {
      if (next) await axios.post(`${API}/travel/follow`);
      else await axios.delete(`${API}/travel/follow`);
    } catch (_e) { setFollowing(!next); }
    finally { setFollowBusy(false); }
  };

  const promoted = useMemo(() => items.filter((d) => d.promoted).slice(0, 6), [items]);

  return (
    <div className="px-4 pt-6 pb-8 space-y-4 fz-text" data-testid="rl-travel-page">
      <header className="flex items-start justify-between gap-3">
        <div>
          <div className="fz-brand text-[11px] font-black tracking-widest">FUUSIC TRAVEL</div>
          <h1 className="text-3xl font-black tracking-tight fz-text leading-tight mt-1">
            Book your next trip. Earn BigPoints.
          </h1>
        </div>
        <Link to="/shop/travel/trips" data-testid="travel-my-trips"
          className="fz-card shrink-0 inline-flex items-center gap-1.5 rounded-full px-3.5 py-2 text-sm font-bold fz-text mt-1">
          <Luggage size={15} /> My Trips
        </Link>
      </header>

      <TravelLiveSearch />

      <TravelTrending />

      <button onClick={toggleFollow} disabled={followBusy} data-testid="travel-follow-btn"
        className={`w-full flex items-center gap-3 rounded-2xl p-4 transition-opacity hover:opacity-95 ${following ? "fz-brand-soft" : "fz-grad"}`}>
        {following ? <BellRing size={20} className="fz-brand" /> : <Bell size={20} />}
        <div className="flex-1 text-left">
          <div className={`font-black ${following ? "fz-text" : ""}`}>
            {following ? "Following Travel deals" : "Follow Travel deals"}
          </div>
          <div className={`text-xs ${following ? "fz-muted" : "opacity-90"}`}>
            {following ? "Recommended deals show up in your wall." : "Get recommended deals in your social wall."}
          </div>
        </div>
        <span className={`text-sm font-black rounded-full px-3 py-1.5 ${following ? "fz-card fz-text" : "bg-white/20"}`}>
          {following ? "Following" : "Follow"}
        </span>
      </button>

      <div className="fz-field flex items-center gap-2 rounded-full px-4 py-3">
        <Search size={18} className="fz-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="travel-search"
          placeholder="Search destinations, deals…" className="fz-field flex-1 outline-none text-sm border-0 bg-transparent p-0" style={{ background: "transparent" }} />
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 no-scrollbar" data-testid="travel-types">
        {TYPES.map((k) => {
          const TM = TYPE_META[k];
          return (
            <Chip key={k} active={type === k} onClick={() => setType(k)} data-testid={`travel-type-${k}`}>
              <span className="inline-flex items-center gap-1.5"><TM.Icon size={14} />{TM.label}</span>
            </Chip>
          );
        })}
      </div>

      <div className="flex items-center gap-2">
        {[["featured", "Featured"], ["price_low", "Price ↑"], ["price_high", "Price ↓"], ["rating", "Top Rated"]].map(([k, l]) => (
          <Chip key={k} active={sort === k} onClick={() => setSort(k)} data-testid={`travel-sort-${k}`}>{l}</Chip>
        ))}
      </div>

      {loading ? (
        <div className="text-center fz-muted py-10">Loading deals…</div>
      ) : items.length === 0 ? (
        <div className="text-center fz-muted py-10" data-testid="travel-empty">No deals found. Try another search.</div>
      ) : (
        <>
          {type === "all" && !q.trim() && promoted.length > 0 && (
            <section data-testid="travel-featured-row">
              <h2 className="text-lg font-black fz-text mb-2">🔥 Featured Deals</h2>
              <div className="flex gap-3 overflow-x-auto pb-1 -mx-1 px-1 no-scrollbar">
                {promoted.map((d) => (
                  <div key={`promo-${d.deal_id}`} className="shrink-0 w-56"><DealCard d={d} /></div>
                ))}
              </div>
            </section>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3" data-testid="travel-grid">
            {items.map((d) => <DealCard key={d.deal_id} d={d} />)}
          </div>
        </>
      )}
    </div>
  );
}
