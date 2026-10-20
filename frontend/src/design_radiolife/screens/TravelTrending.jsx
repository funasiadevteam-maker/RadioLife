// Live "Trending routes" row — real cheapest prices (Travelpayouts Data API,
// proxied + cached by the backend). Auto-detects the listener's nearest origin
// (set-your-city prompt when unsure) and lets them switch departure hub.
import { useEffect, useState } from "react";
import axios from "axios";
import { TrendingUp, ArrowUpRight, MapPin } from "lucide-react";
import { API } from "@/AuthContext";

const HUBS = [
  { iata: "DXB", city: "Dubai", emoji: "🇦🇪" },
  { iata: "AUH", city: "Abu Dhabi", emoji: "🇦🇪" },
  { iata: "DOH", city: "Doha", emoji: "🇶🇦" },
  { iata: "RUH", city: "Riyadh", emoji: "🇸🇦" },
  { iata: "JED", city: "Jeddah", emoji: "🇸🇦" },
  { iata: "KWI", city: "Kuwait City", emoji: "🇰🇼" },
  { iata: "CAI", city: "Cairo", emoji: "🇪🇬" },
  { iata: "IST", city: "Istanbul", emoji: "🇹🇷" },
  { iata: "LON", city: "London", emoji: "🇬🇧" },
  { iata: "DEL", city: "Delhi", emoji: "🇮🇳" },
  { iata: "BOM", city: "Mumbai", emoji: "🇮🇳" },
  { iata: "KHI", city: "Karachi", emoji: "🇵🇰" },
];

export default function TravelTrending() {
  const [origin, setOrigin] = useState(null);
  const [originCity, setOriginCity] = useState("Dubai");
  const [confident, setConfident] = useState(true);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    axios.get(`${API}/travel/nearest-airport`)
      .then((r) => {
        if (!on) return;
        const d = r.data || {};
        setOrigin((d.origin || "DXB").toUpperCase());
        setOriginCity(d.city || "Dubai");
        setConfident(!!d.confident);
      })
      .catch(() => { if (on) { setOrigin("DXB"); setOriginCity("Dubai"); setConfident(false); } });
    return () => { on = false; };
  }, []);

  useEffect(() => {
    if (!origin) return;
    let on = true;
    setLoading(true);
    axios.get(`${API}/travel/trending?origin=${origin}&limit=8`)
      .then((r) => {
        if (!on) return;
        setItems(r.data?.items || []);
        if (r.data?.origin_city && r.data.origin_city !== origin) setOriginCity(r.data.origin_city);
      })
      .catch(() => { if (on) setItems([]); })
      .finally(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, [origin]);

  const hubList = (!origin || HUBS.some((h) => h.iata === origin))
    ? HUBS : [{ iata: origin, city: originCity, emoji: "📍" }, ...HUBS];

  return (
    <section data-testid="travel-trending">
      <div className="flex items-center gap-2 mb-2">
        <TrendingUp size={16} className="fz-brand" />
        <h2 className="text-base font-black fz-text">Trending routes from {originCity}</h2>
        <span className="text-[10px] font-black text-white px-2 py-0.5 rounded-full ml-1"
          style={{ background: "var(--live)" }}>LIVE</span>
      </div>

      {!confident && (
        <div data-testid="travel-origin-prompt" className="flex items-center gap-1.5 text-xs fz-muted mb-2">
          <MapPin size={13} className="fz-brand" /> Not your city? Pick your departure city below.
        </div>
      )}

      <div className="flex gap-2 overflow-x-auto pb-2 no-scrollbar" data-testid="travel-origin-switcher">
        {hubList.map((h) => (
          <button key={h.iata} type="button"
            onClick={() => { setOrigin(h.iata); setOriginCity(h.city); setConfident(true); }}
            data-testid={`travel-origin-${h.iata}`}
            className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-bold transition-colors active:scale-95 ${origin === h.iata ? "fz-chip-active" : "fz-chip"}`}>
            {h.emoji} {h.city}
          </button>
        ))}
      </div>

      <div className="flex gap-3 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="fz-card rounded-2xl shrink-0" style={{ width: 160, height: 104 }} />
          ))
        ) : items.length === 0 ? (
          <div data-testid="travel-trending-empty" className="text-xs fz-muted py-4">
            No live prices for this origin right now.
          </div>
        ) : (
          items.map((it) => (
            <a key={it.destination} href={it.deep_link} target="_blank" rel="noopener noreferrer"
              data-testid={`trending-${it.destination}`}
              className="fz-card rounded-2xl p-3 shrink-0 hover:opacity-90 transition-opacity"
              style={{ width: 160 }}>
              <div className="text-2xl">{it.emoji}</div>
              <div className="font-black fz-text mt-1 flex items-center gap-1">
                {it.city} <ArrowUpRight size={13} className="fz-muted" />
              </div>
              <div className="text-xs fz-muted">{it.country}</div>
              <div className="text-sm font-black fz-brand mt-1">from ${it.price}</div>
              <div className="text-[10px] fz-muted">
                {it.transfers === 0 ? "Direct" : `${it.transfers} stop`} · {it.airline}
              </div>
            </a>
          ))
        )}
      </div>
    </section>
  );
}
