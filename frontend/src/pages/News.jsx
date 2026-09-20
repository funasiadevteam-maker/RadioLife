// Phase R — Listener /news page (dual-design).
// Displays breaking-headline carousel + region/category chips + category-grouped
// headline cards + "News channels near you" sidebar.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Radio, Zap, MapPin, Loader2, Filter, ArrowRight,
                 Clock, ExternalLink } from "lucide-react";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const CATEGORY_LABELS = {
  breaking:        "Breaking",
  local:           "Local",
  politics:        "Politics",
  business:        "Business",
  sports:          "Sports",
  weather:         "Weather",
  traffic:         "Traffic",
  features:        "Features",
  world:           "World",
  tech:            "Tech",
  entertainment:   "Entertainment",
};

export default function News() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";

  const [region,   setRegion]   = useState("");        // "" = global
  const [category, setCategory] = useState("");
  const [headlines,setHeadlines]= useState([]);
  const [channels, setChannels] = useState([]);
  const [breaking, setBreaking] = useState([]);
  const [busy,     setBusy]     = useState(true);
  const [err,      setErr]      = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      setBusy(true);
      setErr(null);
      try {
        const q = new URLSearchParams({ limit: "50" });
        if (region)   q.set("region_code", region);
        if (category) q.set("category",    category);
        const [h, c, b] = await Promise.all([
          axios.get(`${API}/news/headlines?${q}`),
          axios.get(`${API}/news/channels${region ? `?region_code=${region}` : ""}`),
          axios.get(`${API}/news/headlines/breaking${region ? `?region_code=${region}` : ""}`),
        ]);
        if (!alive) return;
        setHeadlines(h.data?.items || []);
        setChannels(c.data?.items || []);
        setBreaking(b.data?.items || []);
      } catch (e) {
        if (alive) setErr(e?.response?.data?.detail?.code || e.message);
      } finally {
        if (alive) setBusy(false);
      }
    })();
    return () => { alive = false; };
  }, [region, category]);

  const grouped = useMemo(() => {
    const buckets = {};
    for (const h of headlines) {
      const c = h.category || "features";
      (buckets[c] = buckets[c] || []).push(h);
    }
    return Object.entries(buckets).sort(
      (a, b) => (b[1].length - a[1].length));
  }, [headlines]);

  const catChips = useMemo(() => Object.keys(CATEGORY_LABELS), []);

  const bg = light ? "bg-slate-50 text-slate-900" : "bg-slate-950 text-white";
  const cardBg = light ? "bg-white border-slate-200 shadow-sm"
                                    : "bg-slate-900/60 border-slate-800";

  return (
    <div className={`min-h-screen ${bg}`} data-testid="news-page"
              data-variant={variant}>
      <div className="max-w-7xl xl:max-w-[1400px] mx-auto p-6 sm:p-8">
        {/* Header */}
        <div className="mb-6">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${
              light ? "text-red-600" : "text-red-400"}`}>
            FUUSIC News · Phase R
          </div>
          <h1 className="mt-1 text-3xl md:text-4xl xl:text-5xl font-black
                                      tracking-tight inline-flex items-center gap-3">
            <Radio className={`w-8 h-8 xl:w-10 xl:h-10 ${
                light ? "text-red-600" : "text-red-400"}`} />
            News Radio
          </h1>
          <div className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            Curator-picked headlines · Live channels · Bulletins refreshed on the hour.
          </div>
        </div>

        {/* Breaking strip */}
        {breaking.length > 0 && (
          <div className="mb-6 rounded-2xl border border-red-500/40 bg-red-500/10 p-4"
                    data-testid="news-breaking-strip">
            <div className="flex items-center gap-2 mb-2">
              <Zap className="w-4 h-4 text-red-400" />
              <div className="text-[10px] font-mono uppercase tracking-widest text-red-400 font-bold">
                Breaking
              </div>
            </div>
            <div className="flex overflow-x-auto gap-3 pb-2">
              {breaking.map((h) => (
                <div key={h.id}
                          data-testid={`news-breaking-card-${h.id}`}
                          className={`min-w-[320px] max-w-[320px] rounded-xl border p-3 ${
                            light ? "bg-white border-red-300" : "bg-slate-900 border-red-500/50"}`}>
                  <div className="text-sm font-bold line-clamp-2">{h.headline_text}</div>
                  {h.summary_text && (
                    <div className={`mt-1 text-xs ${light ? "text-slate-600" : "text-slate-400"} line-clamp-3`}>
                      {h.summary_text}
                    </div>
                  )}
                  {h.source_url && (
                    <a href={h.source_url} target="_blank" rel="noreferrer"
                        className="mt-2 inline-flex items-center gap-1 text-[11px] text-red-400 hover:underline">
                      <ExternalLink className="w-3 h-3" />
                      {h.source_name || "Source"}
                    </a>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Filter chips */}
        <div className="mb-6" data-testid="news-filter-row">
          <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2 inline-flex items-center gap-1.5">
            <Filter className="w-3 h-3" /> Filter by region + category
          </div>
          <div className="flex flex-wrap gap-2">
            <input type="text"
                        value={region}
                        onChange={(e) => setRegion(e.target.value.toUpperCase())}
                        placeholder="Region code — e.g. AE-DU"
                        data-testid="news-region-input"
                        className={`px-3 py-1.5 rounded-full text-xs font-mono w-40
                                      focus:outline-none focus-visible:ring-2 focus-visible:ring-red-500 ${
                          light ? "bg-slate-100 text-slate-900 border border-slate-200"
                                  : "bg-slate-900 text-slate-100 border border-slate-800"}`} />
            <button onClick={() => setCategory("")}
                          data-testid="news-cat-all"
                          className={`px-3 py-1.5 rounded-full text-xs font-bold transition ${
                              category === ""
                                ? (light ? "bg-slate-900 text-white" : "bg-white text-slate-900")
                                : (light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                                  : "bg-slate-800 text-slate-300 hover:bg-slate-700")}`}>
              All
            </button>
            {catChips.map((c) => (
              <button key={c} onClick={() => setCategory(c)}
                              data-testid={`news-cat-${c}`}
                              className={`px-3 py-1.5 rounded-full text-xs font-bold transition ${
                                  category === c
                                    ? (light ? "bg-red-600 text-white" : "bg-red-500 text-white")
                                    : (light ? "bg-slate-100 text-slate-700 hover:bg-slate-200"
                                                      : "bg-slate-800 text-slate-300 hover:bg-slate-700")}`}>
                {CATEGORY_LABELS[c]}
              </button>
            ))}
          </div>
        </div>

        {/* Content — 2-col at lg+ (main + sidebar) */}
        <div className="grid grid-cols-1 lg:grid-cols-[1fr_320px] xl:grid-cols-[1fr_360px] gap-6">
          {/* Headline groups */}
          <div className="min-w-0" data-testid="news-headline-groups">
            {busy ? (
              <div className="flex items-center gap-2 text-sm text-slate-400 py-8">
                <Loader2 className="w-4 h-4 animate-spin" /> Loading news…
              </div>
            ) : err ? (
              <div className="text-sm text-red-400" data-testid="news-error">
                Could not load news: {String(err)}
              </div>
            ) : grouped.length === 0 ? (
              <div className={`rounded-2xl border p-8 text-center ${cardBg}`}
                        data-testid="news-empty">
                <Radio className="w-8 h-8 mx-auto text-slate-500" />
                <div className="mt-2 font-bold">No headlines for that filter.</div>
                <div className={`text-xs mt-1 ${light ? "text-slate-600" : "text-slate-500"}`}>
                  Try a different region code or clear the category filter.
                </div>
              </div>
            ) : (
              grouped.map(([cat, list]) => (
                <section key={cat} className="mb-6" data-testid={`news-group-${cat}`}>
                  <div className={`text-[10px] font-mono uppercase tracking-widest mb-2 ${
                      light ? "text-red-600" : "text-red-400"}`}>
                    {CATEGORY_LABELS[cat] || cat}
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
                    {list.map((h) => (
                      <HeadlineCard key={h.id} h={h}
                                              light={light} cardBg={cardBg} />
                    ))}
                  </div>
                </section>
              ))
            )}
          </div>

          {/* Channels sidebar */}
          <aside data-testid="news-channels-sidebar">
            <div className={`rounded-2xl border p-4 ${cardBg}`}>
              <div className="flex items-center gap-2 mb-3">
                <MapPin className={`w-4 h-4 ${light ? "text-red-600" : "text-red-400"}`} />
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 font-bold">
                  News channels
                </div>
              </div>
              {channels.length === 0 ? (
                <div className={`text-xs ${light ? "text-slate-600" : "text-slate-500"}`}>
                  No channels yet for that region.  Admins can create one at{" "}
                  <span className="font-mono">/admin/news</span>.
                </div>
              ) : (
                <div className="space-y-2">
                  {channels.map((c) => (
                    <Link key={c.id} to={`/news/channels/${c.id}`}
                                data-testid={`news-channel-item-${c.id}`}
                                className={`block rounded-xl p-3 border transition ${
                                    light ? "bg-white border-slate-200 hover:border-red-300"
                                              : "bg-slate-950 border-slate-800 hover:border-red-500/50"}`}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-bold truncate">{c.name}</div>
                          {c.tagline && (
                            <div className={`text-[11px] mt-0.5 ${
                              light ? "text-slate-600" : "text-slate-400"} truncate`}>
                              {c.tagline}
                            </div>
                          )}
                          <div className="text-[10px] font-mono text-slate-500 mt-1">
                            {c.city || c.region_code || "Global"} · {c.language}
                          </div>
                        </div>
                        <ArrowRight className={`w-4 h-4 ${
                            light ? "text-slate-500" : "text-slate-400"} shrink-0`} />
                      </div>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function HeadlineCard({ h, light, cardBg }) {
  return (
    <div className={`rounded-2xl border p-4 ${cardBg}
                              hover:border-red-400/50 transition`}
             data-testid={`news-card-${h.id}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className={`text-[10px] font-mono uppercase tracking-widest ${
            light ? "text-red-600" : "text-red-400"}`}>
          {CATEGORY_LABELS[h.category] || h.category}
        </span>
        {h.is_breaking && (
          <span className="text-[10px] font-mono uppercase tracking-widest text-red-400 font-bold">
            · BREAKING
          </span>
        )}
        <span className="ml-auto text-[10px] font-mono text-slate-500 inline-flex items-center gap-1">
          <Clock className="w-3 h-3" />
          {new Date(h.published_at).toLocaleTimeString([], {
              hour: "2-digit", minute: "2-digit" })}
        </span>
      </div>
      <div className="text-sm font-bold line-clamp-3">{h.headline_text}</div>
      {h.summary_text && (
        <div className={`mt-1.5 text-xs ${light ? "text-slate-600" : "text-slate-400"} line-clamp-3`}>
          {h.summary_text}
        </div>
      )}
      {h.source_url && (
        <a href={h.source_url} target="_blank" rel="noreferrer"
              className="mt-2 inline-flex items-center gap-1 text-[11px] hover:underline text-red-400"
              data-testid={`news-card-source-${h.id}`}>
          <ExternalLink className="w-3 h-3" />
          {h.source_name || "Source"}
        </a>
      )}
      {h.curated_by_llm && (
        <div className={`mt-1 text-[10px] font-mono ${
            light ? "text-slate-500" : "text-slate-500"}`}>
          Summary generated by AI
        </div>
      )}
    </div>
  );
}
