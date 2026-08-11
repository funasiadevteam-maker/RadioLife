/** Phase 42-A — Live Radio Browse / Filter page.
 *
 *  Paginated grid surface backing `/live-radio/browse?category=&language=
 *  &country=&q=`.  Reads filters from query string so deep links + chip
 *  taps from /live-radio just work.  Sorts: backend default
 *  (AI-first → votes/clicks desc).
 */
import React, { useEffect, useState, useCallback, useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import {
  Search, ArrowLeft, ChevronDown, X, Radio as RadioIcon, Music2,
} from "lucide-react";
import { API } from "@/AuthContext";

const COUNTRIES = ["", "US", "GB", "IN", "DE", "FR", "AE", "RU", "IT",
                    "ES", "MX", "TR", "BR", "PL"];

const LANGUAGES = ["", "english", "hindi", "spanish", "arabic", "german",
                    "french", "russian", "italian", "polish", "portuguese"];

function StationGridCard({ s, onPlay }) {
  const isAI = s.source === "bigfm_ai";
  return (
    <button
      type="button"
      data-testid={`live-radio-browse-card-${s.id}`}
      data-source={s.source}
      onClick={onPlay}
      className="group text-left rounded-xl bg-white/[0.04]
                 hover:bg-white/[0.08] border border-white/[0.06]
                 hover:border-white/20 p-3 transition-colors duration-150"
    >
      <div className="relative aspect-square rounded-lg overflow-hidden
                      bg-gradient-to-br from-slate-700 to-slate-900
                      mb-3 flex items-center justify-center">
        {s.favicon ? (
          <img src={s.favicon} alt="" loading="lazy"
               onError={(e) => { e.currentTarget.style.display = "none"; }}
               className="w-full h-full object-cover" />
        ) : null}
        <RadioIcon size={32} className="text-white/30 absolute" />
        {isAI && (
          <span className="absolute top-1.5 left-1.5 text-[10px] uppercase
                           tracking-widest font-mono px-1.5 py-0.5
                           rounded bg-cyan-400/20 text-cyan-300
                           border border-cyan-400/30">
            AI
          </span>
        )}
      </div>
      <div className="text-sm font-semibold text-white truncate"
           title={s.name}>{s.name}</div>
      <div className="text-xs text-white/50 truncate mt-0.5">
        {isAI
          ? "RadioLife AI-Curated"
          : [s.country, s.language].filter(Boolean).join(" · ") || "Live"}
      </div>
      {s.music_genre && (
        <div className="inline-flex items-center mt-1 px-2 py-0.5 rounded-full bg-accent-electric/15 text-accent-electric text-[10px] font-bold"
          data-testid="station-genre">
          {s.music_genre}
        </div>
      )}
      {s.tags_json && s.tags_json.length > 0 && (
        <div className="text-[10px] text-white/30 mt-1 truncate">
          {s.tags_json.slice(0, 3).join(" · ")}
        </div>
      )}
    </button>
  );
}

export default function LiveRadioBrowse() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  const filters = useMemo(() => ({
    category: searchParams.get("category") || "",
    language: searchParams.get("language") || "",
    country:  searchParams.get("country")  || "",
    q:        searchParams.get("q")        || "",
  }), [searchParams]);

  const [categories, setCategories] = useState([]);
  const [items, setItems] = useState([]);
  const [meta, setMeta] = useState({ total: 0, page: 1, limit: 24 });
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [searchInput, setSearchInput] = useState(filters.q);

  // Load category list once
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/live-radio/categories`);
        setCategories(r.data.items || []);
      } catch (_e) { /* swallow */ }
    })();
  }, []);

  // Fetch stations whenever filters change
  const fetchStations = useCallback(async (page = 1, append = false) => {
    if (append) setSearching(true); else setLoading(true);
    try {
      const params = { page, limit: 24 };
      if (filters.category) params.category = filters.category;
      if (filters.language) params.language = filters.language;
      if (filters.country)  params.country  = filters.country;
      if (filters.q)        params.q        = filters.q;
      const r = await axios.get(`${API}/live-radio/stations`, { params });
      setMeta({
        total: r.data.total, page: r.data.page,
        limit: r.data.limit, ai_count: r.data.ai_count,
        imported_count: r.data.imported_count,
      });
      setItems((prev) => append ? [...prev, ...(r.data.items || [])]
                                : (r.data.items || []));
    } catch (_e) {
      if (!append) setItems([]);
    } finally {
      setSearching(false); setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchStations(1, false);
    setSearchInput(filters.q);
  }, [fetchStations, filters.q]);

  const updateFilter = useCallback((key, value) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value); else next.delete(key);
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const onSearchSubmit = (e) => {
    e.preventDefault();
    updateFilter("q", searchInput.trim());
  };

  const clearAll = () => setSearchParams(new URLSearchParams());

  const onPlayCard = (s) => {
    if (s.source === "bigfm_ai") {
      navigate(`/radio?channel=${encodeURIComponent(s.id)}`);
      return;
    }
    navigate(`/live-radio/station/${s.id}`);
  };

  const activeFilterCount =
    (filters.category ? 1 : 0) + (filters.language ? 1 : 0) +
    (filters.country ? 1 : 0) + (filters.q ? 1 : 0);

  const hasMore = items.length < meta.total;

  return (
    <div data-testid="live-radio-browse-page"
         className="text-white max-w-[1200px] mx-auto px-5 pt-6 pb-24">
      <Link to="/live-radio" data-testid="live-radio-browse-back"
            className="inline-flex items-center gap-1 text-xs text-white/50
                       hover:text-white mb-4">
        <ArrowLeft size={12} /> Back to Live Radio
      </Link>

      <div className="flex items-end justify-between flex-wrap gap-3 mb-6">
        <div>
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Browse stations
          </h1>
          <p className="text-sm text-white/60 mt-1">
            {meta.total > 0
              ? `${meta.total.toLocaleString()} station${meta.total === 1 ? "" : "s"} match your filters.`
              : "Use the filters below to find stations."}
          </p>
        </div>
      </div>

      {/* Filter bar */}
      <div data-testid="live-radio-browse-filters"
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
            placeholder="Search station name…"
            data-testid="live-radio-browse-search-input"
            className="w-full pl-9 pr-3 h-10 rounded-lg bg-white/[0.05]
                       border border-white/[0.06] text-sm text-white
                       placeholder:text-white/30 outline-none
                       focus:border-cyan-400/50" />
        </form>
        <FilterSelect
          label="Category"
          value={filters.category}
          options={[{ value: "", label: "All" },
                    ...categories.map((c) => ({
                      value: c.slug,
                      label: `${c.label} (${c.total})` }))]}
          onChange={(v) => updateFilter("category", v)}
          testid="live-radio-browse-filter-category" />
        <FilterSelect
          label="Language"
          value={filters.language}
          options={LANGUAGES.map((l) => ({
            value: l, label: l ? l[0].toUpperCase() + l.slice(1) : "All" }))}
          onChange={(v) => updateFilter("language", v)}
          testid="live-radio-browse-filter-language" />
        <FilterSelect
          label="Country"
          value={filters.country}
          options={COUNTRIES.map((c) => ({
            value: c, label: c || "All" }))}
          onChange={(v) => updateFilter("country", v)}
          testid="live-radio-browse-filter-country" />
        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={clearAll}
            data-testid="live-radio-browse-clear-filters"
            className="inline-flex items-center gap-1 text-xs text-white/60
                       hover:text-white px-2 h-9">
            <X size={12} /> Clear ({activeFilterCount})
          </button>
        )}
      </div>

      {/* Grid */}
      {loading ? (
        <div data-testid="live-radio-browse-loading"
             className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4
                        lg:grid-cols-5 gap-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-[230px] rounded-xl
                                     bg-white/[0.04] animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div data-testid="live-radio-browse-empty"
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
          <div data-testid="live-radio-browse-grid"
               className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4
                          lg:grid-cols-5 gap-3">
            {items.map((s) => (
              <StationGridCard key={s.id} s={s}
                                              onPlay={() => onPlayCard(s)} />
            ))}
          </div>
          {hasMore && (
            <div className="flex justify-center mt-8">
              <button
                type="button"
                onClick={() => fetchStations(meta.page + 1, true)}
                disabled={searching}
                data-testid="live-radio-browse-load-more"
                className="px-5 h-10 rounded-full bg-white/[0.06]
                           hover:bg-white/[0.12] border border-white/[0.10]
                           text-sm text-white/80 hover:text-white
                           disabled:opacity-40 transition-colors">
                {searching ? "Loading…"
                                : `Load more (${meta.total - items.length} remaining)`}
              </button>
            </div>
          )}
        </>
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
            <option key={o.value} value={o.value}
                          className="bg-slate-900 text-white">
              {o.label}
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
