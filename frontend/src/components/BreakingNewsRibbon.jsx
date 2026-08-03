// Phase R — Breaking News Ribbon (dismissable per session).
// Renders a compact strip when the current region has a breaking headline
// in the last 30 minutes.  Session-scoped dismiss via sessionStorage.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Zap, X, ChevronRight } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const FRESH_WINDOW_MIN = 30;
const SS_KEY = "bigfm.breaking.dismissed";

export default function BreakingNewsRibbon({ region_code, className = "" }) {
  const [head, setHead] = useState(null);
  const [dismissed, setDismissed] = useState(() => {
    try {
      const raw = sessionStorage.getItem(SS_KEY);
      return raw ? JSON.parse(raw) : [];
    } catch { return []; }
  });

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const q = new URLSearchParams({ limit: "1" });
        if (region_code) q.set("region_code", region_code);
        const { data } = await axios.get(
          `${API}/news/headlines/breaking?${q}`);
        if (!alive) return;
        const top = (data?.items || [])[0];
        if (!top) return;
        // Only surface if within the fresh window (30 minutes).
        const publishedMs = new Date(top.published_at).getTime();
        const ageMin = (Date.now() - publishedMs) / 60000;
        if (ageMin > FRESH_WINDOW_MIN) return;
        setHead(top);
      } catch { /* silent */ }
    })();
    return () => { alive = false; };
  }, [region_code]);

  const onDismiss = () => {
    if (!head) return;
    const next = [...new Set([...dismissed, head.id])];
    setDismissed(next);
    try { sessionStorage.setItem(SS_KEY, JSON.stringify(next)); } catch { /* noop */ }
  };

  if (!head || dismissed.includes(head.id)) return null;

  return (
    <div className={`w-full rounded-2xl border border-red-500/40 bg-red-500/10
                                    p-3 flex items-center gap-3 ${className}`}
              data-testid="breaking-news-ribbon"
              data-headline-id={head.id}>
      <div className="inline-flex items-center gap-1.5 shrink-0">
        <Zap className="w-4 h-4 text-red-400 animate-pulse" />
        <span className="text-[10px] font-mono uppercase tracking-widest text-red-400 font-bold">
          Breaking
        </span>
      </div>
      <Link to="/news"
                className="min-w-0 flex-1 text-sm font-bold hover:underline truncate"
                data-testid="breaking-news-ribbon-link">
        {head.headline_text}
      </Link>
      <Link to="/news" className="hidden sm:inline-flex items-center gap-1 text-xs text-red-400 hover:underline shrink-0"
                data-testid="breaking-news-ribbon-cta">
        More <ChevronRight className="w-3 h-3" />
      </Link>
      <button type="button" onClick={onDismiss}
                    data-testid="breaking-news-ribbon-dismiss"
                    className="text-slate-400 hover:text-white shrink-0"
                    aria-label="Dismiss breaking news">
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}
