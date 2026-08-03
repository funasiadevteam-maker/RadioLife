import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { Search, BookHeadphones, Play, Loader2 } from "lucide-react";
import { useAuth } from "@/AuthContext";
import SafeImage from "@/components/SafeImage";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const CATEGORIES = ["business","food_local","movies_culture","real_estate",
  "health_wellness","legal_finance","events_community","news_commentary",
  "comedy","true_crime","devotional","sports","tech","education","other"];

function _fmtSecs(s) {
  if (!s || !Number.isFinite(s)) return "";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export default function Podcasts() {
  const { user } = useAuth();
  const [channels, setChannels] = useState([]);
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [loading, setLoading] = useState(true);
  const [cont, setCont] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    const p = new URLSearchParams();
    if (q) p.set("q", q);
    if (cat) p.set("category", cat);
    try {
      const r = await axios.get(`${API}/podcasts/discover?${p.toString()}`);
      setChannels(r.data.channels || []);
    } catch (_) { setChannels([]); }
    setLoading(false);
  }, [q, cat]);
  useEffect(() => { load(); }, [load]);

  // Load continue-listening strip for auth users.
  useEffect(() => {
    if (!user) { setCont([]); return; }
    axios.get(`${API}/podcasts/me/continue-listening?limit=6`,
      { withCredentials: true })
      .then((r) => setCont(r.data?.items || []))
      .catch(() => setCont([]));
  }, [user]);

  return (
    <div className="min-h-screen bg-slate-950 text-white pb-24"
              data-testid="podcasts-tab">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8">
        <header>
          <div className="text-[10px] uppercase tracking-widest font-mono
                                          text-violet-400">Podcasts</div>
          <h1 className="text-3xl sm:text-4xl font-black tracking-tight">
            On-demand shows
          </h1>
          <p className="mt-1 text-sm text-white/60">
            {channels.length} podcasts from BigFM creators + imported feeds.
          </p>
        </header>

        {/* Continue-listening strip. */}
        {cont.length > 0 && (
          <section className="mt-8" data-testid="podcasts-continue-listening">
            <div className="text-xs uppercase tracking-widest font-mono
                                            text-white/40 mb-3">
              Continue listening
            </div>
            <ul className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1
                                            snap-x">
              {cont.map((row) => {
                if (!row.episode || !row.podcast) return null;
                const pct = row.duration_seconds
                  ? Math.min(100,
                        Math.round((row.position_seconds
                                                  / row.duration_seconds) * 100))
                  : 0;
                return (
                  <li key={row.episode_id}
                          className="snap-start flex-shrink-0 w-56
                                                  rounded-2xl bg-white/[0.03]
                                                  border border-white/[0.08] p-3
                                                  hover:bg-white/[0.06] transition"
                          data-testid={`continue-listening-${row.episode_id}`}>
                    <Link to={`/podcasts/${row.podcast.id}`}
                                className="block">
                      <div className="aspect-square rounded-xl overflow-hidden
                                                      bg-violet-900/30 flex items-center
                                                      justify-center">
                        <SafeImage
                          src={row.episode.cover_image_url
                            || row.podcast.cover_image_url}
                          alt={row.episode.title}
                          fallbackKind="podcast"
                          fallbackText={row.episode.title || row.podcast.title}
                          className="w-full h-full object-cover" />
                      </div>
                      <div className="text-xs font-semibold mt-2 line-clamp-2">
                        {row.episode.title}
                      </div>
                      <div className="text-[10px] text-white/50 mt-0.5 truncate">
                        {row.podcast.title}
                      </div>
                    </Link>
                    <div className="mt-2 h-1 bg-white/10 rounded-full
                                                    overflow-hidden">
                      <div className="h-full bg-violet-400"
                                  style={{ width: `${pct}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        {/* Search + category. */}
        <div className="mt-8 flex flex-col sm:flex-row gap-3">
          <div className="flex-1 relative">
            <Search size={14} className="absolute left-3 top-1/2
                                                        -translate-y-1/2 text-white/40" />
            <input
              type="search"
              placeholder="Search podcasts…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              data-testid="podcasts-search"
              className="w-full h-10 pl-9 pr-3 rounded-full bg-white/[0.04]
                                          border border-white/[0.08] text-sm
                                          focus:outline-none focus:border-violet-400
                                          text-white placeholder:text-white/40" />
          </div>
          <select
            value={cat} onChange={(e) => setCat(e.target.value)}
            data-testid="podcasts-cat"
            className="h-10 px-4 rounded-full bg-white/[0.04]
                                    border border-white/[0.08] text-sm text-white">
            <option value="">All categories</option>
            {CATEGORIES.map((c) =>
              <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
          </select>
        </div>

        {/* Category chips (quick filter). */}
        <div className="mt-4 flex flex-wrap gap-2"
                    data-testid="podcasts-cat-chips">
          {CATEGORIES.slice(0, 8).map((c) => {
            const on = cat === c;
            return (
              <button
                type="button"
                key={c}
                onClick={() => setCat(on ? "" : c)}
                data-testid={`podcasts-cat-chip-${c}`}
                className={[
                  "h-7 px-3 rounded-full text-[11px] font-semibold",
                  "transition",
                  on
                    ? "bg-violet-500 text-white"
                    : "bg-white/[0.04] border border-white/[0.08] "
                        + "text-white/70 hover:bg-white/[0.08]",
                ].join(" ")}>
                {c.replace(/_/g, " ")}
              </button>
            );
          })}
        </div>

        {/* Grid. */}
        <div className="mt-8">
          {loading ? (
            <div className="p-8 flex justify-center"
                        data-testid="podcasts-loading">
              <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
            </div>
          ) : channels.length === 0 ? (
            <div className="p-10 text-center rounded-2xl border
                                            border-white/10 bg-white/[0.03]
                                            text-white/60"
                        data-testid="podcasts-empty">
              No podcasts match your filters yet.
              {" "}<Link to="/creator" className="text-violet-400 underline">
                Be the first to apply
              </Link>.
            </div>
          ) : (
            <ul className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4
                                            lg:grid-cols-5 gap-4"
                        data-testid="podcasts-grid">
              {channels.map((ch) => (
                <li key={ch.id}
                        data-testid={`podcast-card-${ch.slug}`}>
                  <Link to={`/podcasts/${ch.id}`}
                              className="block group">
                    <div className="aspect-square rounded-2xl overflow-hidden
                                                    bg-gradient-to-br from-violet-700/50
                                                    to-pink-700/40 flex items-center
                                                    justify-center relative">
                      <SafeImage src={ch.cover_image_url} alt={ch.title}
                                            fallbackKind="podcast"
                                            fallbackText={ch.title}
                                            className="w-full h-full object-cover" />
                      <div className="absolute inset-0 opacity-0
                                                      group-hover:opacity-100 transition
                                                      bg-black/40 flex items-center
                                                      justify-center">
                        <div className="w-11 h-11 rounded-full bg-violet-500
                                                          flex items-center justify-center">
                          <Play size={16} className="text-white ml-0.5" />
                        </div>
                      </div>
                    </div>
                    <div className="mt-2 text-sm font-semibold truncate">
                      {ch.title}
                    </div>
                    <div className="text-[11px] text-white/50 mt-0.5">
                      {(ch.category || "").replace(/_/g, " ")} ·
                      {" "}{ch.follower_count || 0} subs
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
