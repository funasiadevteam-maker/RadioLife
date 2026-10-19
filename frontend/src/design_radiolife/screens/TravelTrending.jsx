// Live "Trending routes" row — real cheapest prices (Travelpayouts Data API,
// proxied + cached by the backend). Each card deep-links to an attributed search.
import { useEffect, useState } from "react";
import axios from "axios";
import { TrendingUp, ArrowUpRight } from "lucide-react";
import { API } from "@/AuthContext";

export default function TravelTrending({ origin = "DXB" }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let on = true;
    axios.get(`${API}/travel/trending?origin=${origin}&limit=8`)
      .then((r) => { if (on) setItems(r.data?.items || []); })
      .catch(() => {})
      .finally(() => { if (on) setLoading(false); });
    return () => { on = false; };
  }, [origin]);

  if (!loading && items.length === 0) return null;

  return (
    <section data-testid="travel-trending">
      <div className="flex items-center gap-2 mb-2">
        <TrendingUp size={16} className="fz-brand" />
        <h2 className="text-base font-black fz-text">Trending routes from Dubai</h2>
        <span className="text-[10px] font-black text-white px-2 py-0.5 rounded-full ml-1"
          style={{ background: "var(--live)" }}>LIVE</span>
      </div>
      <div className="flex gap-3 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
        {loading
          ? Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="fz-card rounded-2xl shrink-0" style={{ width: 160, height: 104 }} />
            ))
          : items.map((it) => (
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
            ))}
      </div>
    </section>
  );
}
