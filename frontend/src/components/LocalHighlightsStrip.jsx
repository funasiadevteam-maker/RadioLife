/** Phase 42-E2.1 — Local highlights horizontal strip.
 *  Pulls /api/home/local-highlights for the user's resolved market.
 *  Renders 3-5 mini cards (news / offer / predict-win).  Light surface
 *  — degrades silently when the endpoint returns no items.
 */
import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { ChevronRight, MapPin } from "lucide-react";
import { API } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";

const KIND_TINT = {
  news:                "border-cyan-400/30 bg-cyan-400/10 text-cyan-300",
  offer:              "border-amber-400/30 bg-amber-400/10 text-amber-300",
  predict_win: "border-magenta-400/30 bg-magenta-400/10 text-pink-300",
};

export default function LocalHighlightsStrip() {
  const market = useGeoStore((s) => s.market);
  const cityLabel = useGeoStore((s) => s.displayName)(market);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    axios.get(`${API}/home/local-highlights`,
                      { params: { market: market || "global", limit: 5 },
                          withCredentials: true })
      .then((r) => { if (!cancel) setItems(r.data?.items || []); })
      .catch(() => { if (!cancel) setItems([]); })
      .finally(() => { if (!cancel) setLoading(false); });
    return () => { cancel = true; };
  }, [market]);

  if (loading) {
    return (
      <section data-testid="home-local-highlights"
                          data-state="loading"
                          className="mt-2">
        <h2 className="font-display font-bold text-xl tracking-display-tight mb-4
                                      flex items-center gap-2">
          <MapPin size={16} className="text-accent-electric" />
          Around {cityLabel || "you"}
        </h2>
        <div className="flex gap-3 overflow-x-auto pb-1">
          {[0, 1, 2].map((i) => (
            <div key={i}
                  className="min-w-[280px] h-[110px] rounded-2xl
                                          bg-white/[0.04] animate-pulse" />
          ))}
        </div>
      </section>
    );
  }
  if (!items.length) return null;

  return (
    <section data-testid="home-local-highlights"
                  data-state="ready"
                  data-count={items.length}
                  className="mt-2">
      <h2 className="font-display font-bold text-xl tracking-display-tight mb-4
                                  flex items-center gap-2">
        <MapPin size={16} className="text-accent-electric" />
        Around {cityLabel || "you"}
      </h2>
      <div className="flex gap-3 overflow-x-auto pb-1 -mx-2 px-2 snap-x">
        {items.map((it) => (
          <Link
            key={`${it.kind}-${it.id}`}
            to={it.route}
            data-testid={`home-local-${it.kind}-${it.id}`}
            data-kind={it.kind}
            className="min-w-[280px] max-w-[320px] snap-start
                                    rounded-2xl border border-white/[0.06]
                                    bg-white/[0.02] hover:bg-white/[0.05]
                                    transition-colors duration-150
                                    p-4 flex flex-col justify-between gap-3"
          >
            <div className="flex items-start justify-between gap-2">
              <span className={`inline-block text-[9px] font-mono
                                              uppercase tracking-widest
                                              rounded-full border px-2 py-0.5
                                              ${KIND_TINT[it.kind] || "border-white/10 text-white/60"}`}>
                {it.badge}
              </span>
              <ChevronRight size={14} className="text-white/30" />
            </div>
            <div>
              <div className="text-white font-display font-bold text-sm
                                          leading-snug line-clamp-2 mb-1">
                {it.title}
              </div>
              {it.subtitle && (
                <div className="text-white/55 text-xs leading-snug
                                              line-clamp-1">
                  {it.subtitle}
                </div>
              )}
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
