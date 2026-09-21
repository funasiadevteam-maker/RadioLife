/** Phase 42-A2 — Unified Radio browse + filter grid.
 *
 *  `/radio/browse?q=&source=&category=&language=&country=&page=`
 *  Mixed-source results.  AI cards first, then community, then imported.
 */
import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import {
  Search, ArrowLeft, ChevronDown, X, Radio as RadioIcon, Music2,
  Sparkles, Users, Globe2,
} from "lucide-react";
import { API } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
// Phase 42-D3 — heart toggle for bigfm + imported.
import { FavoriteHeart } from "@/components/FavoriteControls";
// P0 mixed-content fix — rewrite http:// stream URLs through the proxy.
import { toPlayableStreamUrl } from "@/utils/streamUrl";
// Phase AD.11 — browse_row banner zone.
import BannerZoneSlot from "@/components/BannerZoneSlot";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
function resolveImg(u) {
  if (!u) return null;
  return u.startsWith("http") ? u : `${BACKEND_URL}${u}`;
}

const SOURCE_BADGE = {
  bigfm_ai:  { label: "AI",                  cls: "bg-cyan-400/20 text-cyan-300 border-cyan-400/30" },
  community: { label: "COMMUNITY", cls: "bg-fuchsia-400/20 text-fuchsia-300 border-fuchsia-400/30" },
  imported:  { label: "LIVE",            cls: "bg-emerald-400/20 text-emerald-300 border-emerald-400/30" },
};

const LANG_OPTIONS = ["", "english", "hindi", "spanish", "arabic", "german",
                                      "french", "russian", "italian", "polish", "portuguese"];

const LANG_GROUPS = [
  { key: "", label: "All" },
  { key: "english", label: "English" },
  { key: "hindi", label: "Hindi" },
  { key: "indian", label: "Indian Languages" },
  { key: "news", label: "News" },
];

const COUNTRY_OPTIONS = ["", "US", "GB", "IN", "DE", "FR", "AE", "RU", "IT",
                                              "ES", "MX", "TR", "BR", "PL", "JP", "AR"];

const SOURCE_OPTIONS = [
  { key: "all",        label: "All sources" },
  { key: "bigfm_ai",  label: "AI only",        icon: Sparkles },
  { key: "community", label: "Community",  icon: Users },
  { key: "imported",  label: "Live radio",  icon: Globe2 },
];

function GridCard({ s, onActivate }) {
  const src = s.source || "imported";
  const badge = SOURCE_BADGE[src] || SOURCE_BADGE.imported;
  const favType = src === "bigfm_ai" ? "bigfm"
                              : src === "imported" ? "imported" : null;
  // Phase FUN.1.1 — flagship + priority visual treatment on the active
  // browse card component.  Flagship gets an amber ring around the
  // whole card; priority (non-flagship Dubai) gets a cyan ⚡ PRIO pill.
  const isFlagship = !!s.is_flagship;
  const isPriority = !isFlagship && !!s.is_priority;
  const artUrl = resolveImg(s.logo_url || s.favicon);
  return (
    <div
      role="button"
      tabIndex={0}
      data-testid={`radio-browse-card-${s.id}`}
      data-source={src}
      data-flagship={isFlagship ? "1" : ""}
      data-priority={isPriority ? "1" : ""}
      onClick={() => onActivate(s)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onActivate(s); } }}
      className={`group text-left rounded-xl bg-white/[0.04] cursor-pointer
                          hover:bg-white/[0.08] border p-3
                          transition-colors duration-150
                          ${isFlagship
                              ? "border-amber-400/40 hover:border-amber-400/60 ring-1 ring-amber-400/20"
                              : "border-white/[0.06] hover:border-white/20"}`}
    >
      <div className="relative aspect-square rounded-lg overflow-hidden
                              bg-bg-elevated mb-3 flex items-center justify-center">
        {artUrl ? (
          <img src={artUrl} alt="" loading="lazy"
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                    className="w-full h-full object-cover" />
        ) : null}
        <RadioIcon size={32} className="text-white/30 absolute" />
        {/* Source pill — hidden when a flagship / priority pill takes the top-left slot. */}
        {!isFlagship && !isPriority && (
          <span className={[
                "absolute top-1.5 left-1.5 text-[10px] uppercase",
                "tracking-widest font-mono px-1.5 py-0.5 rounded border",
                badge.cls,
              ].join(" ")}>
            {badge.label}
          </span>
        )}
        {isFlagship && (
          <span className="absolute top-1.5 left-1.5 inline-flex items-center gap-0.5
                                      px-1.5 py-0.5 rounded-full text-[9px]
                                      font-black uppercase tracking-widest
                                      bg-gradient-to-r from-amber-400 to-pink-500
                                      text-slate-950 shadow-md"
                data-testid={`radio-browse-card-${s.id}-badge-flagship`}>
            ★ FLAG
          </span>
        )}
        {isPriority && (
          <span className="absolute top-1.5 left-1.5 inline-flex items-center gap-0.5
                                      px-1.5 py-0.5 rounded-full text-[9px]
                                      font-black uppercase tracking-widest
                                      bg-gradient-to-r from-cyan-500 to-blue-500
                                      text-white shadow-md"
                data-testid={`radio-browse-card-${s.id}-badge-priority`}>
            ⚡ PRIO
          </span>
        )}
        {favType && (
          <div className="absolute top-1.5 right-1.5 z-10">
            <FavoriteHeart
              stationId={s.id}
              stationType={favType}
              station={{
                name: s.name, favicon: s.favicon, thumbnail_url: s.favicon,
                country: s.country, language: s.language,
              }}
              size={12} />
          </div>
        )}
      </div>
      <div className="text-sm font-semibold text-white truncate"
                  title={s.name}>{s.name}</div>
      <div className="text-xs text-white/50 truncate mt-0.5">
        {src === "bigfm_ai" ? "FUUSIC AI" :
          src === "community" ? "Community" :
          [s.country, s.language].filter(Boolean).join(" · ") || "Live"}
      </div>
      {s.music_genre && (
        <div className="inline-flex items-center mt-1.5 px-2 py-0.5 rounded-full bg-accent-electric/15 text-accent-electric text-[10px] font-bold"
          data-testid="station-genre">
          {s.music_genre}
        </div>
      )}
    </div>
  );
}


function FilterSelect({ label, value, options, onChange, testid }) {
  return (
    <label className="relative inline-flex items-center text-xs text-white/60">
      <span className="mr-1.5">{label}:</span>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          data-testid={testid}
          className="appearance-none pl-3 pr-8 h-9 rounded-lg
                              bg-white/[0.05] border border-white/[0.10]
                              text-sm text-white outline-none cursor-pointer
                              hover:bg-white/[0.08] focus:border-cyan-400/50">
          {options.map((o) => (
            <option key={o.value ?? o} value={o.value ?? o}
                              className="bg-slate-900 text-white">
              {o.label ?? (o ? o[0].toUpperCase() + o.slice(1) : "All")}
            </option>
          ))}
        </select>
        <ChevronDown size={12}
                                className="absolute right-2 top-1/2
                                                  -translate-y-1/2 text-white/40
                                                  pointer-events-none" />
      </div>
    </label>
  );
}


export default function RadioBrowse() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);

  const filters = useMemo(() => ({
    q:                  searchParams.get("q") || "",
    category:  searchParams.get("category") || "",
    language:  searchParams.get("language") || "",
    country:    searchParams.get("country") || "",
    genre:      searchParams.get("genre") || "",
    lang_group: searchParams.get("lang_group") || "",
    source:      searchParams.get("source") || "all",
    show_all:  searchParams.get("show_all") === "1",
  }), [searchParams]);

  const [genreOptions, setGenreOptions] = useState([]);

  const [items, setItems] = useState([]);
  const [counts, setCounts] = useState({});
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 24 });
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [searchInput, setSearchInput] = useState(filters.q);

  const fetchPage = useCallback(async (page = 1, append = false) => {
    if (append) setLoadingMore(true); else setLoading(true);
    try {
      const params = { page, limit: 24, source: filters.source };
      if (filters.q) params.q = filters.q;
      if (filters.category) params.category = filters.category;
      if (filters.language) params.language = filters.language;
      if (filters.country) params.country = filters.country;
      if (filters.genre) params.genre = filters.genre;
      if (filters.lang_group) params.lang_group = filters.lang_group;
      if (filters.show_all) params.show_all = true;
      const r = await axios.get(`${API}/radio/browse`, { params, withCredentials: true });
      setMeta({ total: r.data.total, page: r.data.page, limit: r.data.limit });
      setCounts(r.data.counts_by_source || {});
      setItems((prev) => append ? [...prev, ...(r.data.items || [])]
                                                                : (r.data.items || []));
    } catch (_e) {
      if (!append) setItems([]);
    } finally { setLoadingMore(false); setLoading(false); }
  }, [filters]);

  useEffect(() => { fetchPage(1, false); setSearchInput(filters.q); },
                    [fetchPage, filters.q]);

  useEffect(() => {
    axios.get(`${API}/radio/genres`)
      .then((r) => setGenreOptions(r.data.genres || []))
      .catch(() => {});
  }, []);

  // Language memory — remember the last-used chip and reopen Browse on it.
  useEffect(() => {
    if (filters.lang_group) {
      try { localStorage.setItem("rl_fav_lang_group", filters.lang_group); } catch (_e) { /* */ }
    }
  }, [filters.lang_group]);

  const appliedFav = useRef(false);
  useEffect(() => {
    if (appliedFav.current) return;
    appliedFav.current = true;
    // Only apply the remembered chip on a clean visit (no deep-link params).
    const hasAny = searchParams.get("lang_group") || searchParams.get("category")
      || searchParams.get("q") || searchParams.get("genre") || searchParams.get("country");
    if (hasAny) return;
    let fav = "";
    try { fav = localStorage.getItem("rl_fav_lang_group") || ""; } catch (_e) { /* */ }
    if (fav) {
      const next = new URLSearchParams(searchParams);
      next.set("lang_group", fav);
      setSearchParams(next, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const updateFilter = (key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value && value !== "all") next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  const onSearchSubmit = (e) => {
    e.preventDefault();
    updateFilter("q", searchInput.trim());
  };

  const clearAll = () => setSearchParams(new URLSearchParams());

  const onActivate = async (s) => {
    if (s.source === "bigfm_ai") {
      navigate(`/radio?ch=${encodeURIComponent(s.id)}&autoplay=1`);
      return;
    }
    if (s.source === "community") {
      navigate(`/r/${s.share_id || s.channel_id || s.id}`);
      return;
    }
    try {
      const r = await axios.post(`${API}/radio/play/${s.id}`, {},
                                                                  { withCredentials: true });
      if (r.data?.stream_url) {
        setImportedStation({
          id: s.id, name: r.data.name,
          stream_url: toPlayableStreamUrl(r.data.stream_url),
          favicon: r.data.favicon || s.favicon,
          country: r.data.country, language: r.data.language,
          source: "imported",
        });
      }
      navigate(`/radio/station/${s.id}`);
    } catch (_e) { navigate(`/radio/station/${s.id}`); }
  };

  const activeFilters =
    (filters.q ? 1 : 0) + (filters.category ? 1 : 0)
    + (filters.language ? 1 : 0) + (filters.country ? 1 : 0)
    + (filters.genre ? 1 : 0) + (filters.lang_group ? 1 : 0)
    + (filters.source !== "all" ? 1 : 0);
  const hasMore = items.length < meta.total;

  return (
    <div data-testid="radio-browse-page"
              className="text-white max-w-[1200px] mx-auto px-5 pt-6 pb-24">
      <Link to="/radio" data-testid="radio-browse-back"
                  className="inline-flex items-center gap-1 text-xs text-white/50
                                  hover:text-white mb-4">
        <ArrowLeft size={12} /> Back to Radio
      </Link>

      <div className="flex items-end justify-between flex-wrap gap-3 mb-6">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Browse stations
          </h1>
          <p className="text-sm text-white/60 mt-1">
            {meta.total > 0
              ? `${meta.total.toLocaleString()} station${meta.total === 1 ? "" : "s"} matched ·
                  AI ${counts.bigfm_ai || 0} · Community ${counts.community || 0} ·
                  Live ${counts.imported || 0}`
              : "Use the filters below to find stations across all sources."}
          </p>
        </div>
      </div>

      {/* Language group chips — flip between English · Hindi · Indian · News */}
      <div data-testid="radio-browse-lang-groups"
                className="flex flex-wrap items-center gap-2 mb-4">
        {LANG_GROUPS.map((lg) => {
          const active = filters.lang_group === lg.key;
          return (
            <button
              key={lg.key || "all"}
              type="button"
              onClick={() => updateFilter("lang_group", lg.key)}
              data-testid={`radio-browse-lang-group-${lg.key || "all"}`}
              className={`px-4 h-9 rounded-full text-sm font-semibold border transition-colors
                              ${active
                                ? "bg-cyan-400 text-slate-950 border-cyan-400"
                                : "bg-white/[0.04] text-white/70 border-white/[0.10] hover:bg-white/[0.08] hover:text-white"}`}>
              {lg.label}
            </button>
          );
        })}
        {/* Content-language escape — English-only by default; show every language. */}
        <button
          type="button"
          onClick={() => updateFilter("show_all", filters.show_all ? "" : "1")}
          data-testid="radio-browse-show-all-languages"
          title="Show stations in every language"
          className={`ml-auto px-4 h-9 rounded-full text-sm font-semibold border transition-colors
                          ${filters.show_all
                            ? "bg-violet-500 text-white border-violet-500"
                            : "bg-white/[0.04] text-white/70 border-white/[0.10] hover:bg-white/[0.08] hover:text-white"}`}>
          {filters.show_all ? "✓ All languages" : "Show all languages"}
        </button>
      </div>
      {!filters.show_all && !filters.language && !filters.lang_group && (
        <p data-testid="radio-browse-lang-note" className="text-xs text-white/45 -mt-2 mb-4">
          Showing stations in your languages. Tap “Show all languages” to see every station.
        </p>
      )}

      {/* Filter bar */}
      <div data-testid="radio-browse-filters"
                className="flex flex-wrap items-center gap-2 mb-5
                                  p-3 rounded-xl bg-white/[0.03]
                                  border border-white/[0.06]">
        <form onSubmit={onSearchSubmit}
                    className="relative flex-grow min-w-[200px]">
          <Search size={14} className="absolute left-3 top-1/2
                                                                          -translate-y-1/2 text-white/40" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search station name, tag, or country…"
            data-testid="radio-browse-search-input"
            className="w-full pl-9 pr-3 h-10 rounded-lg bg-white/[0.05]
                                  border border-white/[0.06] text-sm text-white
                                  placeholder:text-white/30 outline-none
                                  focus:border-cyan-400/50" />
        </form>
        <FilterSelect label="Source" value={filters.source}
                                    options={SOURCE_OPTIONS.map((o) => ({ value: o.key, label: o.label }))}
                                    onChange={(v) => updateFilter("source", v)}
                                    testid="radio-browse-filter-source" />
        <FilterSelect label="Language" value={filters.language}
                                    options={LANG_OPTIONS.map((l) => ({ value: l, label: l ? l[0].toUpperCase() + l.slice(1) : "All" }))}
                                    onChange={(v) => updateFilter("language", v)}
                                    testid="radio-browse-filter-language" />
        <FilterSelect label="Country" value={filters.country}
                                    options={COUNTRY_OPTIONS.map((c) => ({ value: c, label: c || "All" }))}
                                    onChange={(v) => updateFilter("country", v)}
                                    testid="radio-browse-filter-country" />
        {genreOptions.length > 0 && (
          <FilterSelect label="Genre" value={filters.genre}
                                    options={[{ value: "", label: "All" }, ...genreOptions.map((g) => ({ value: g, label: g }))]}
                                    onChange={(v) => updateFilter("genre", v)}
                                    testid="radio-browse-filter-genre" />
        )}
        {activeFilters > 0 && (
          <button
            type="button" onClick={clearAll}
            data-testid="radio-browse-clear-filters"
            className="inline-flex items-center gap-1 text-xs text-white/60
                                hover:text-white px-2 h-9">
            <X size={12} /> Clear ({activeFilters})
          </button>
        )}
      </div>

      {/* Phase AD.11 — browse_row banner slot (below filters, above grid). */}
      <BannerZoneSlot zone="browse_row" />
      {/* Grid */}
      {loading ? (
        <div data-testid="radio-browse-loading"
                  className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4
                                      lg:grid-cols-5 gap-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-[230px] rounded-xl
                                                                  bg-white/[0.04] animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div data-testid="radio-browse-empty"
                  className="py-20 text-center text-white/40">
          <Music2 size={36} className="mx-auto mb-3 text-white/20" />
          <div className="text-sm">No stations match these filters.</div>
          <button onClick={clearAll}
                          className="mt-3 text-xs text-cyan-300 hover:text-cyan-200">
            Clear filters
          </button>
        </div>
      ) : (
        <>
          <div data-testid="radio-browse-grid"
                      className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4
                                          lg:grid-cols-5 gap-3">
            {items.map((s) => (
              <GridCard key={s.id} s={s} onActivate={onActivate} />
            ))}
          </div>
          {hasMore && (
            <div className="flex justify-center mt-8">
              <button
                type="button"
                onClick={() => fetchPage(meta.page + 1, true)}
                disabled={loadingMore}
                data-testid="radio-browse-load-more"
                className="px-5 h-10 rounded-full bg-white/[0.06]
                                    hover:bg-white/[0.12] border border-white/[0.10]
                                    text-sm text-white/80 hover:text-white
                                    disabled:opacity-40 transition-colors">
                {loadingMore ? "Loading…"
                                          : `Load more (${(meta.total - items.length).toLocaleString()} remaining)`}
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
