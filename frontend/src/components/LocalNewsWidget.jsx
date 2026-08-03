// Phase 15d — Local news mini-widget. Reads /api/news/local for the
// currently-resolved market and shows up to 3 headlines. Refetches when
// the user changes their market via CityChip. Silently falls back to the
// stub stories the backend ships when the live provider is offline.
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Newspaper, ChevronRight } from "lucide-react";
import { Card } from "@/shell/primitives";
import { useGeoStore } from "@/store/useGeoStore";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

export default function LocalNewsWidget({ limit = 3, className = "" }) {
  const market = useGeoStore((s) => s.market);
  const city   = useGeoStore((s) => s.city);
  const [items, setItems]     = useState([]);
  const [source, setSource]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [hasError, setHasError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setHasError(false);
    axios.get(`${API}/news/local`, { params: { limit }, timeout: 4500 })
      .then((r) => {
        if (cancelled) return;
        setItems(r.data?.items || []);
        setSource(r.data?.source || null);
      })
      .catch(() => { if (!cancelled) { setItems([]); setSource(null); setHasError(true); } })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [market, limit]);

  return (
    <Card
      data-testid="home-local-news"
      className={`p-5 ${className}`}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Newspaper size={18} className="text-accent-electric" />
          <span className="font-display font-bold tracking-display-tight">
            {city ? `Around ${city}` : "Local headlines"}
          </span>
        </div>
        {source && source !== "live" && !hasError && (
          <span
            data-testid="home-local-news-source"
            className="text-[9px] font-mono uppercase tracking-widest
                              text-text-secondary"
          >
            {source.startsWith("mock") ? "demo feed" : source}
          </span>
        )}
        {hasError && (
          <span
            data-testid="home-local-news-source"
            className="text-[9px] font-mono uppercase tracking-widest
                              text-text-secondary"
          >
            quiet today
          </span>
        )}
      </div>
      <ul className="mt-3 space-y-2" data-testid="home-local-news-list">
        {loading && items.length === 0 && (
          <li className="text-sm text-text-secondary">Loading headlines…</li>
        )}
        {!loading && items.length === 0 && !hasError && (
          <li className="text-sm text-text-secondary">
            No headlines yet — check back soon.
          </li>
        )}
        {!loading && items.length === 0 && hasError && (
          <li className="text-sm text-text-secondary">
            Headlines will return shortly.
          </li>
        )}
        {items.slice(0, limit).map((it, i) => (
          <li
            key={`${i}-${it.title}`}
            data-testid={`home-local-news-item-${i}`}
            className="text-sm text-text-secondary leading-snug
                              flex items-start gap-2"
          >
            <ChevronRight size={12}
                                  className="mt-1 text-accent-electric shrink-0" />
            <span>
              <span className="text-white">{it.title}</span>
              {it.source && (
                <span className="ml-2 text-[10px] font-mono uppercase
                                          tracking-widest text-text-secondary">
                  {it.source}
                </span>
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
