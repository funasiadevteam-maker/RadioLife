/** Phase 40 — Home headlines strip.
 *  Renders 5 text-only news rows below the hero CTAs.  Clicking a row
 *  navigates to /news/:news_id.  Hides itself entirely on fetch error
 *  or empty so it never breaks Home.
 */
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Newspaper, ChevronRight } from "lucide-react";
import { API } from "@/AuthContext";

function relTime(pubDate) {
  if (!pubDate) return "";
  // pubDate is "YYYY-MM-DD HH:MM:SS" UTC from NewsData.io.
  const t = Date.parse(pubDate.replace(" ", "T") + "Z");
  if (isNaN(t)) return "";
  const mins = Math.max(1, Math.floor((Date.now() - t) / 60000));
  if (mins < 60)        return `${mins}m ago`;
  if (mins < 60 * 24)   return `${Math.floor(mins / 60)}h ago`;
  return `${Math.floor(mins / 1440)}d ago`;
}

export default function HomeNewsStrip({ limit = 5 }) {
  const [items, setItems]     = useState(null);  // null = loading
  const [error, setError]     = useState(false);
  const navigate              = useNavigate();

  useEffect(() => {
    let cancel = false;
    (async () => {
      try {
        const r = await axios.get(`${API}/news/headlines`,
          { params: { limit }, withCredentials: true });
        if (!cancel) setItems(r.data?.items || []);
      } catch (e) {
        if (!cancel) setError(true);
      }
    })();
    return () => { cancel = true; };
  }, [limit]);

  if (error) return null;
  if (items === null) {
    return (
      <div data-testid="home-news-loading"
           className="mt-6 space-y-2">
        {[0,1,2].map(i => (
          <div key={i} className="h-12 rounded-lg bg-white/[0.04] animate-pulse" />
        ))}
      </div>
    );
  }
  if (!items.length) return null;

  return (
    <section data-testid="home-news-strip"
             className="mt-7 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Newspaper size={18} className="text-accent-electric" />
          <span className="font-display font-bold tracking-display-tight
                            text-base">
            Latest News
          </span>
        </div>
        <Link to="/news" data-testid="home-news-viewall"
              className="text-xs font-mono text-text-secondary
                          hover:text-accent-electric transition-colors
                          flex items-center gap-1">
          View all <ChevronRight size={12} />
        </Link>
      </div>
      <ul className="space-y-1.5">
        {items.map((n) => (
          <li key={n.news_id}>
            <button
              data-testid={`home-news-row-${n.news_id}`}
              onClick={() => navigate(`/news/${encodeURIComponent(n.news_id)}`)}
              className="w-full text-left rounded-lg px-3 py-2.5
                          bg-white/[0.03] hover:bg-white/[0.07]
                          transition-colors border border-white/[0.04]
                          hover:border-accent-electric/40">
              <div className="text-sm font-medium text-text-primary
                              line-clamp-2 leading-snug">
                {n.title}
              </div>
              <div className="mt-1 text-[11px] font-mono text-text-secondary
                              flex items-center gap-2">
                <span>{n.source_name || n.source_id || "—"}</span>
                <span className="opacity-40">·</span>
                <span>{relTime(n.pubDate)}</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
