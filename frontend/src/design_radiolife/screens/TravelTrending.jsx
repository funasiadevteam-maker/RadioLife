// Live "Trending routes" row — real cheapest prices (Travelpayouts Data API,
// proxied + cached by the backend). Auto-detects the listener's nearest origin,
// lets them switch departure hub, watch a route for price drops, and save a
// flight to My Trips.
import { useEffect, useState } from "react";
import axios from "axios";
import { TrendingUp, ArrowUpRight, MapPin, Bell, BellRing, Bookmark,
         BookmarkCheck, X, TrendingDown } from "lucide-react";
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
const rkey = (o, d) => `${o}|${d}`;

export default function TravelTrending() {
  const [origin, setOrigin] = useState(null);
  const [originCity, setOriginCity] = useState("Dubai");
  const [confident, setConfident] = useState(true);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [watchItems, setWatchItems] = useState([]);
  const [watched, setWatched] = useState(() => new Set());
  const [saved, setSaved] = useState(() => new Set());

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

  const loadWatches = () => {
    axios.get(`${API}/travel/watches`).then((r) => {
      const its = r.data?.items || [];
      setWatchItems(its);
      setWatched(new Set(its.map((w) => rkey(w.origin, w.destination))));
    }).catch(() => {});
  };
  const loadSaved = () => {
    axios.get(`${API}/travel/saved`).then((r) => {
      const fl = r.data?.flights || [];
      setSaved(new Set(fl.filter((f) => f.origin && f.destination).map((f) => rkey(f.origin, f.destination))));
    }).catch(() => {});
  };
  useEffect(() => { loadWatches(); loadSaved(); }, []);

  const toggleWatch = async (it) => {
    const k = rkey(it.origin, it.destination);
    if (watched.has(k)) {
      const w = watchItems.find((x) => rkey(x.origin, x.destination) === k);
      setWatched((s) => { const n = new Set(s); n.delete(k); return n; });
      if (w) await axios.delete(`${API}/travel/watches/${w.watch_id}`).catch(() => {});
      loadWatches();
    } else {
      setWatched((s) => new Set(s).add(k));
      await axios.post(`${API}/travel/watches`, {
        origin: it.origin, destination: it.destination, price: it.price, deep_link: it.deep_link,
      }).catch(() => {});
      loadWatches();
    }
  };

  const toggleSave = async (it) => {
    const k = rkey(it.origin, it.destination);
    if (saved.has(k)) return;
    setSaved((s) => new Set(s).add(k));
    await axios.post(`${API}/travel/saved`, {
      trip_type: "flight", title: `${originCity} → ${it.city}`,
      subtitle: `${it.transfers === 0 ? "Direct" : it.transfers + " stop"} · ${it.airline || ""}`.trim(),
      deep_link: it.deep_link, price_label: `$${it.price}`,
      origin: it.origin, destination: it.destination,
    }).catch(() => {});
  };

  const removeWatch = async (w) => {
    setWatchItems((xs) => xs.filter((x) => x.watch_id !== w.watch_id));
    setWatched((s) => { const n = new Set(s); n.delete(rkey(w.origin, w.destination)); return n; });
    await axios.delete(`${API}/travel/watches/${w.watch_id}`).catch(() => {});
  };

  const hubList = (!origin || HUBS.some((h) => h.iata === origin))
    ? HUBS : [{ iata: origin, city: originCity, emoji: "📍" }, ...HUBS];

  return (
    <section data-testid="travel-trending">
      {watchItems.length > 0 && (
        <div className="mb-3" data-testid="travel-watching">
          <div className="flex items-center gap-2 mb-1.5">
            <Bell size={14} className="fz-brand" />
            <h3 className="text-sm font-black fz-text">Price watch</h3>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-2 no-scrollbar">
            {watchItems.map((w) => (
              <div key={w.watch_id} data-testid={`watch-${w.destination}`}
                className="fz-card rounded-xl px-3 py-2 shrink-0 flex items-center gap-2" style={{ minWidth: 160 }}>
                <span className="text-lg">{w.emoji}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-xs font-black fz-text truncate">{w.origin_city} → {w.city}</div>
                  <div className="flex items-center gap-1">
                    <span className="text-sm font-black fz-brand">${w.current_price}</span>
                    {w.dropped && (
                      <span className="inline-flex items-center gap-0.5 text-[10px] font-black text-white px-1.5 rounded-full"
                        style={{ background: "var(--success,#16a34a)" }}>
                        <TrendingDown size={10} /> -{w.drop_pct}%
                      </span>
                    )}
                  </div>
                </div>
                <button onClick={() => removeWatch(w)} data-testid={`watch-remove-${w.destination}`}
                  className="fz-muted hover:text-red-500"><X size={14} /></button>
              </div>
            ))}
          </div>
        </div>
      )}

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
          <button key={h.iata} type="button" onClick={() => { setOrigin(h.iata); setOriginCity(h.city); setConfident(true); }}
            data-testid={`travel-origin-${h.iata}`}
            className={`shrink-0 whitespace-nowrap rounded-full px-3 py-1.5 text-xs font-bold transition-colors active:scale-95 ${origin === h.iata ? "fz-chip-active" : "fz-chip"}`}>
            {h.emoji} {h.city}
          </button>
        ))}
      </div>

      <div className="flex gap-3 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="fz-card rounded-2xl shrink-0" style={{ width: 160, height: 120 }} />
          ))
        ) : items.length === 0 ? (
          <div data-testid="travel-trending-empty" className="text-xs fz-muted py-4">
            No live prices for this origin right now.
          </div>
        ) : (
          items.map((it) => {
            const k = rkey(it.origin, it.destination);
            const isW = watched.has(k), isS = saved.has(k);
            return (
              <div key={it.destination} data-testid={`trending-${it.destination}`}
                className="fz-card rounded-2xl p-3 shrink-0 relative" style={{ width: 160 }}>
                <div className="absolute top-2 right-2 flex gap-1">
                  <button onClick={() => toggleWatch(it)} data-testid={`watch-btn-${it.destination}`}
                    title={isW ? "Stop watching" : "Watch for price drops"}
                    className={`w-7 h-7 rounded-full flex items-center justify-center ${isW ? "fz-grad text-white" : "bg-black/5 fz-muted"}`}>
                    {isW ? <BellRing size={13} /> : <Bell size={13} />}
                  </button>
                  <button onClick={() => toggleSave(it)} data-testid={`save-btn-${it.destination}`}
                    title={isS ? "Saved to My Trips" : "Save to My Trips"}
                    className={`w-7 h-7 rounded-full flex items-center justify-center ${isS ? "fz-grad text-white" : "bg-black/5 fz-muted"}`}>
                    {isS ? <BookmarkCheck size={13} /> : <Bookmark size={13} />}
                  </button>
                </div>
                <a href={it.deep_link} target="_blank" rel="noopener noreferrer" className="block hover:opacity-90">
                  <div className="text-2xl">{it.emoji}</div>
                  <div className="font-black fz-text mt-1 flex items-center gap-1 pr-16">
                    {it.city} <ArrowUpRight size={13} className="fz-muted shrink-0" />
                  </div>
                  <div className="text-xs fz-muted">{it.country}</div>
                  <div className="text-sm font-black fz-brand mt-1">from ${it.price}</div>
                  <div className="text-[10px] fz-muted">
                    {it.transfers === 0 ? "Direct" : `${it.transfers} stop`} · {it.airline}
                  </div>
                </a>
              </div>
            );
          })
        )}
      </div>
    </section>
  );
}
