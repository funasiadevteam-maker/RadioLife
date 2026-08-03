/** Phase B — RadioLife (light) variant of the podcasts catalog.
 *
 *  Route match: /podcasts  when useDesignVariant() === "radiolife".
 *  Mounted by RadioLifeOverlay.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Search, BookHeadphones, Play, Loader2 } from "lucide-react";
import { API, useAuth } from "@/AuthContext";
import SafeImage from "@/components/SafeImage";

const CATEGORIES = ["business","food_local","movies_culture","real_estate",
  "health_wellness","legal_finance","events_community","news_commentary",
  "comedy","true_crime","devotional","sports","tech","education","other"];

export default function PodcastsRadioLife() {
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

  useEffect(() => {
    if (!user) { setCont([]); return; }
    axios.get(`${API}/podcasts/me/continue-listening?limit=6`,
      { withCredentials: true })
      .then((r) => setCont(r.data?.items || []))
      .catch(() => setCont([]));
  }, [user]);

  return (
    <div className="px-4 pt-6 pb-6 space-y-4"
              data-testid="rl-podcasts-page">
      <header>
        <h1 className="text-2xl font-black tracking-tight text-slate-900">
          Podcasts
        </h1>
        <p className="text-slate-500 text-sm mt-1"
              data-testid="rl-podcasts-count">
          {channels.length} on-demand shows.
        </p>
      </header>

      {cont.length > 0 && (
        <section data-testid="rl-podcasts-continue-listening">
          <div className="text-[11px] font-semibold uppercase tracking-widest
                                          text-slate-400 mb-2">
            Continue listening
          </div>
          <ul className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1 snap-x">
            {cont.map((row) => {
              if (!row.episode || !row.podcast) return null;
              const pct = row.duration_seconds
                ? Math.min(100,
                      Math.round((row.position_seconds
                                                / row.duration_seconds) * 100))
                : 0;
              return (
                <li key={row.episode_id}
                        className="snap-start flex-shrink-0 w-44 rounded-2xl
                                                bg-white border border-slate-200 p-3
                                                shadow-sm"
                        data-testid={`rl-continue-${row.episode_id}`}>
                  <Link to={`/podcasts/${row.podcast.id}`}
                              className="block">
                    <div className="aspect-square rounded-xl overflow-hidden
                                                    bg-slate-100 flex items-center
                                                    justify-center">
                      <SafeImage
                        src={row.episode.cover_image_url
                          || row.podcast.cover_image_url}
                        alt={row.episode.title}
                        fallbackKind="podcast"
                        fallbackText={row.episode.title || row.podcast.title}
                        className="w-full h-full object-cover" />
                    </div>
                    <div className="text-xs font-semibold mt-2 line-clamp-2
                                                    text-slate-900">
                      {row.episode.title}
                    </div>
                  </Link>
                  <div className="mt-2 h-1 bg-slate-200 rounded-full
                                                  overflow-hidden">
                    <div className="h-full bg-violet-500"
                                style={{ width: `${pct}%` }} />
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      <div className="flex gap-2">
        <div className="flex-1 relative">
          <Search size={14} className="absolute left-3 top-1/2
                                                      -translate-y-1/2 text-slate-400" />
          <input
            type="search"
            placeholder="Search…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            data-testid="rl-podcasts-search"
            className="w-full h-10 pl-9 pr-3 rounded-full bg-white
                                        border border-slate-200 text-sm
                                        focus:outline-none focus:border-violet-500
                                        text-slate-900 placeholder:text-slate-400" />
        </div>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-1 -mx-1 px-1"
                data-testid="rl-podcasts-cat-chips">
        {CATEGORIES.slice(0, 10).map((c) => {
          const on = cat === c;
          return (
            <button
              type="button"
              key={c}
              onClick={() => setCat(on ? "" : c)}
              data-testid={`rl-podcasts-cat-chip-${c}`}
              className={[
                "h-8 px-3 rounded-full text-[11px] font-semibold",
                "whitespace-nowrap transition",
                on
                  ? "bg-violet-500 text-white"
                  : "bg-white border border-slate-200 text-slate-700",
              ].join(" ")}>
              {c.replace(/_/g, " ")}
            </button>
          );
        })}
      </div>

      {loading ? (
        <div className="p-8 flex justify-center"
                    data-testid="rl-podcasts-loading">
          <Loader2 className="w-6 h-6 animate-spin text-violet-500" />
        </div>
      ) : channels.length === 0 ? (
        <div className="p-8 text-center rounded-2xl border border-slate-200
                                        bg-white text-slate-500"
                    data-testid="rl-podcasts-empty">
          No podcasts match your filters.
        </div>
      ) : (
        <ul className="grid grid-cols-2 sm:grid-cols-3 gap-3"
                    data-testid="rl-podcasts-grid">
          {channels.map((ch) => (
            <li key={ch.id}
                    data-testid={`rl-podcast-card-${ch.slug}`}>
              <Link to={`/podcasts/${ch.id}`} className="block group">
                <div className="aspect-square rounded-2xl overflow-hidden
                                                bg-gradient-to-br from-violet-100
                                                to-pink-100 border border-slate-200
                                                flex items-center justify-center
                                                relative">
                  <SafeImage src={ch.cover_image_url} alt={ch.title}
                                            fallbackKind="podcast"
                                            fallbackText={ch.title}
                                            className="w-full h-full object-cover" />
                  <div className="absolute inset-0 opacity-0
                                                  group-hover:opacity-100 transition
                                                  bg-black/30 flex items-center
                                                  justify-center">
                    <div className="w-10 h-10 rounded-full bg-white
                                                      flex items-center justify-center">
                      <Play size={14} className="text-violet-600 ml-0.5" />
                    </div>
                  </div>
                </div>
                <div className="mt-2 text-sm font-semibold text-slate-900
                                                truncate">
                  {ch.title}
                </div>
                <div className="text-[11px] text-slate-500 mt-0.5">
                  {(ch.category || "").replace(/_/g, " ")}
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
