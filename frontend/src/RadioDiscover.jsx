/** Phase 42-A2 — Unified Radio Discover (home page).
 *
 *  `/radio` (when no `?ch=...` query) renders this.  Single-call data
 *  fetch via `/api/radio/discover` returns 7-8 rails with all the data
 *  pre-baked.  Different rail types: `stations` rails render a
 *  horizontal carousel of UnifiedCard, `facet_chips` rails render a chip
 *  row that deep-links into /radio/browse.
 *
 *  Source-aware navigation: AI tiles open `/radio?ch=<slug>&autoplay=1`
 *  (existing personalized engine).  Community → `/r/<share_id>`.
 *  Imported → start the imported-stream player via store action and
 *  navigate to detail.
 */
import React, { useEffect, useMemo, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Radio as RadioIcon, Sparkles, Users, MapPin, Flame, Music2,
  Languages, Globe2, Search, ChevronRight, Heart, Pin, Play,
} from "lucide-react";
import { API } from "@/AuthContext";
import { useGeoStore } from "@/store/useGeoStore";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useStationFavoritesStore } from "@/store/useStationFavoritesStore";
import { getLastAiStation } from "@/utils/lastStation";
// Phase 42-D3 — heart toggle.  Skips community sources (only bigfm/imported supported by the API).
import { FavoriteHeart } from "@/components/FavoriteControls";
// Phase FUN.1-v2 — flagship stations pinned above all discover rails.
import FlagshipStrip from "@/components/FlagshipStrip";
// P0 mixed-content fix — rewrite http:// stream URLs through the proxy.
import { toPlayableStreamUrl } from "@/utils/streamUrl";

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

const RAIL_ICON = {
  for_you: Heart, ai_curated: Sparkles, community: Users,
  local: MapPin, trending: Flame, languages: Languages,
  genres: Music2, countries: Globe2, pinned: Pin,
};

// FUUSIC AI-curated rails — highlighted + pinned above the flagship strip.
const AI_RAIL_IDS = ["for_you", "ai_curated"];

function UnifiedCard({ station, onActivate }) {
  const src = station.source || "imported";
  const badge = SOURCE_BADGE[src] || SOURCE_BADGE.imported;
  // Phase 42-D3 — only `bigfm` and `imported` are favoritable (API
  // contract).  Community gets no heart for now.
  const favType = src === "bigfm_ai" ? "bigfm"
                              : src === "imported" ? "imported" : null;
  const artUrl = resolveImg(station.favicon);
  return (
    <button
      type="button"
      data-testid={`radio-card-${station.id}`}
      data-source={src}
      onClick={() => onActivate(station)}
      className="group relative flex-shrink-0 w-[180px] text-left
                          rounded-xl bg-white/[0.04] hover:bg-white/[0.08]
                          border border-white/[0.06] hover:border-white/20
                          p-3 transition-colors duration-150"
    >
      <div className="relative aspect-square rounded-lg overflow-hidden
                              bg-bg-elevated mb-3 flex items-center justify-center">
        {artUrl ? (
          <img src={artUrl} alt="" loading="lazy"
                    onError={(e) => { e.currentTarget.style.display = "none"; }}
                    className="w-full h-full object-cover" />
        ) : null}
        <RadioIcon size={32} className="text-white/30 absolute" />
        <span className={[
            "absolute top-1.5 left-1.5 text-[10px] uppercase",
            "tracking-widest font-mono px-1.5 py-0.5 rounded border",
            badge.cls,
          ].join(" ")}
          data-testid={`radio-card-${station.id}-badge`}>
          {badge.label}
        </span>
        {favType && (
          <div className="absolute top-1.5 right-1.5 z-10">
            <FavoriteHeart
              stationId={station.id}
              stationType={favType}
              station={{
                name: station.name, favicon: station.favicon,
                thumbnail_url: station.favicon,
                country: station.country, language: station.language,
                tagline: station.tagline,
              }}
              size={12} />
          </div>
        )}
      </div>
      <div className="text-sm font-semibold text-white truncate"
                  title={station.name}>
        {station.name}
      </div>
      <div className="text-xs text-white/50 truncate mt-0.5">
        {src === "bigfm_ai"
          ? "FUUSIC AI-Curated"
          : src === "community"
            ? "Community Station"
            : [station.country, station.language].filter(Boolean).join(" · ") || "Live"}
      </div>
    </button>
  );
}


function StationRail({ rail, onActivate }) {
  const Icon = RAIL_ICON[rail.id] || RadioIcon;
  const items = rail.stations || [];
  return (
    <section data-testid={`radio-rail-${rail.id}`} className="mb-10">
      <div className="flex items-end justify-between mb-3">
        <div className="flex items-center gap-2">
          <Icon size={18} className="text-cyan-400" />
          <h2 className="text-lg font-semibold text-white">{rail.title}</h2>
        </div>
        {items.length > 0 && (
          <Link to={`/radio/browse?rail=${rail.id}`}
                      data-testid={`radio-rail-${rail.id}-cta`}
                      className="text-xs text-cyan-300 hover:text-cyan-200
                                          inline-flex items-center gap-1">
            See all <ChevronRight size={12} />
          </Link>
        )}
      </div>
      {items.length === 0 ? (
        <div className="text-sm text-white/40 py-6"
                  data-testid={`radio-rail-${rail.id}-empty`}>
          Nothing here yet — check back soon.
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-2 -mx-1 px-1"
                  style={{ scrollbarWidth: "thin" }}>
          {items.map((s) => (
            <UnifiedCard key={s.id} station={s} onActivate={onActivate} />
          ))}
        </div>
      )}
    </section>
  );
}


function ChipRail({ rail, paramKey }) {
  const chips = rail.facet_chips || [];
  const Icon = RAIL_ICON[rail.id] || Music2;
  if (!chips.length) return null;
  return (
    <section data-testid={`radio-rail-${rail.id}`} className="mb-10">
      <div className="flex items-center gap-2 mb-3">
        <Icon size={18} className="text-cyan-400" />
        <h2 className="text-lg font-semibold text-white">{rail.title}</h2>
      </div>
      <div className="flex flex-wrap gap-2">
        {chips.map((c) => (
          <Link
            key={c.slug}
            to={`/radio/browse?${paramKey}=${encodeURIComponent(c.slug)}`}
            data-testid={`radio-chip-${rail.id}-${c.slug}`}
            className="inline-flex items-center gap-2 px-3 h-9 rounded-full
                                bg-white/[0.05] hover:bg-white/[0.10]
                                border border-white/[0.08] text-sm
                                text-white/80 hover:text-white whitespace-nowrap
                                transition-colors">
            <span className="capitalize">{c.label}</span>
            <span className="text-[10px] text-white/40 font-mono">
              {c.count.toLocaleString()}
            </span>
          </Link>
        ))}
      </div>
    </section>
  );
}


export default function RadioDiscover() {
  const navigate = useNavigate();
  const country = useGeoStore((s) => s.country);
  const city = useGeoStore((s) => s.city);
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState("all");   // all | ai | live
  const favorites = useStationFavoritesStore((s) => s.favorites);
  const favLoaded = useStationFavoritesStore((s) => s.loaded);
  const bootstrapFavs = useStationFavoritesStore((s) => s.bootstrap);
  const resume = useMemo(() => getLastAiStation(), []);

  useEffect(() => { if (!favLoaded) bootstrapFavs(); }, [favLoaded, bootstrapFavs]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const r = await axios.get(`${API}/radio/discover`, {
          params: { country: country || undefined,
                              city: city || undefined },
          withCredentials: true,
        });
        if (!cancelled) setData(r.data);
      } catch (_e) {
        if (!cancelled) setData({ rails: [], rail_count: 0 });
      } finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [country, city]);

  const onActivate = useCallback(async (station) => {
    if (station.source === "bigfm_ai") {
      // Existing personalized AI flow.
      navigate(`/radio?ch=${encodeURIComponent(station.id)}&autoplay=1`);
      return;
    }
    if (station.source === "community") {
      // Community stations have their own deep-link surface.
      const slug = station.share_id || station.channel_id || station.id;
      navigate(`/r/${slug}`);
      return;
    }
    // Imported: pull playback config + start stream via global store.
    try {
      const r = await axios.post(`${API}/radio/play/${station.id}`, {},
                                                                  { withCredentials: true });
      if (r.data?.mode === "imported" && r.data.stream_url) {
        setImportedStation({
          id: station.id,
          name: r.data.name,
          stream_url: toPlayableStreamUrl(r.data.stream_url),
          favicon: r.data.favicon || station.favicon,
          country: r.data.country, language: r.data.language,
          source: "imported",
        });
      }
      // Always navigate to detail for context (player keeps streaming).
      navigate(`/radio/station/${station.id}`);
    } catch (_e) {
      navigate(`/radio/station/${station.id}`);
    }
  }, [navigate, setImportedStation]);

  const stationRails = useMemo(
    () => (data?.rails || []).filter((r) => "stations" in r),
    [data]);
  const aiRails = useMemo(
    () => stationRails.filter((r) => AI_RAIL_IDS.includes(r.id)),
    [stationRails]);
  const otherStationRails = useMemo(
    () => stationRails.filter((r) => !AI_RAIL_IDS.includes(r.id)),
    [stationRails]);
  const chipRails = useMemo(
    () => (data?.rails || []).filter((r) => "facet_chips" in r),
    [data]);
  // The highlighted box shows ONLY genuine AI stations (filter out any
  // imported stations the personalized "For You" rail may mix in).
  const aiRailsFiltered = useMemo(() => aiRails
    .map((r) => ({ ...r, stations: (r.stations || []).filter((s) => (s.source || "imported") === "bigfm_ai") }))
    .filter((r) => r.stations.length > 0), [aiRails]);
  // Pinned AI channels = the listener's favourited FUUSIC AI stations.
  const pinnedStations = useMemo(() => favorites
    .filter((f) => f.station_type === "bigfm")
    .map((f) => ({
      id: f.station_id,
      name: (f.station && f.station.name) || f.station_id,
      source: "bigfm_ai",
      favicon: (f.station && (f.station.favicon || f.station.thumbnail_url)) || null,
    })), [favorites]);

  if (loading) {
    return (
      <div data-testid="radio-discover-loading"
                className="text-white max-w-[1200px] mx-auto px-5 pt-6 pb-24">
        <div className="h-10 w-2/3 bg-white/[0.06] rounded mb-6 animate-pulse" />
        {[0, 1, 2].map((i) => (
          <div key={i} className="mb-10">
            <div className="h-5 w-1/4 bg-white/[0.06] rounded mb-3 animate-pulse" />
            <div className="flex gap-3 overflow-hidden">
              {[0,1,2,3,4].map((j) => (
                <div key={j} className="w-[180px] h-[230px] rounded-xl
                                                              bg-white/[0.04] animate-pulse flex-shrink-0" />
              ))}
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div data-testid="radio-discover-page"
              className="text-white max-w-[1200px] mx-auto px-5 pt-6 pb-24">
      {/* Hero search */}
      <div className="mb-8">
        <div className="flex items-center gap-3 mb-2">
          <RadioIcon size={26} className="text-cyan-400" />
          <h1 className="text-3xl sm:text-4xl font-bold tracking-tight">
            Radio
          </h1>
        </div>
        <p className="text-sm text-white/60 mb-5 max-w-[640px]">
          FUUSIC AI-curated stations · Community creators · 58,000+ live
          stations from around the world — one search, every source.
        </p>
        <Link
          to="/radio/browse"
          data-testid="radio-discover-search-cta"
          className="flex items-center gap-3 max-w-[560px] px-4 h-12
                              rounded-full bg-white/[0.05] hover:bg-white/[0.08]
                              border border-white/[0.10] hover:border-cyan-400/40
                              transition-colors group">
          <Search size={16} className="text-cyan-400" />
          <span className="text-sm text-white/50 group-hover:text-white/70 flex-grow">
            Search 58,000+ stations…
          </span>
          <span className="text-xs text-cyan-300/70 group-hover:text-cyan-200
                                          uppercase tracking-widest font-mono">
            Browse
          </span>
        </Link>
      </div>

      {/* Continue where you left off — one-tap resume of your last AI station. */}
      {resume && resume.slug && view !== "live" && (
        <button type="button" data-testid="radio-discover-resume"
          onClick={() => navigate(`/radio?ch=${encodeURIComponent(resume.slug)}&autoplay=1`)}
          className="group w-full mb-6 flex items-center gap-4 text-left
                              rounded-2xl p-3 sm:p-4 bg-gradient-to-r from-cyan-500/10 to-fuchsia-500/10
                              border border-cyan-400/20 hover:border-cyan-400/50 transition-colors">
          <span className="relative w-14 h-14 rounded-xl overflow-hidden shrink-0 grid place-items-center bg-white/[0.06]">
            {resume.thumb
              ? <img src={resolveImg(resume.thumb)} alt="" className="w-full h-full object-cover" />
              : <Sparkles size={22} className="text-cyan-300" />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-mono uppercase tracking-widest text-cyan-300">
              Continue where you left off
            </div>
            <div className="text-base font-bold text-white truncate">
              {resume.name || "Your last AI station"}
            </div>
          </div>
          <span className="shrink-0 inline-flex items-center gap-1.5 h-10 px-4 rounded-full
                                      font-black text-sm text-slate-950 group-hover:brightness-110"
                style={{ background: "linear-gradient(135deg,#22d3ee,#a855f7)" }}>
            <Play size={15} fill="currentColor" /> Resume
          </span>
        </button>
      )}

      {/* Source filter — All · AI Radio · Live */}
      <div className="flex items-center gap-1.5 mb-6 p-1 rounded-full bg-white/[0.04]
                            border border-white/[0.08] w-fit" data-testid="radio-discover-view-toggle">
        {[
          { id: "all", label: "All" },
          { id: "ai", label: "AI Radio" },
          { id: "live", label: "Live" },
        ].map((t) => (
          <button key={t.id} type="button" data-testid={`radio-discover-view-${t.id}`}
            onClick={() => setView(t.id)}
            className={`px-4 h-9 rounded-full text-sm font-bold transition-colors ${
              view === t.id ? "bg-white text-slate-950" : "text-white/60 hover:text-white"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* FUUSIC AI radio — highlighted and pinned ABOVE the flagship strip. */}
      {view !== "live" && (pinnedStations.length > 0 || aiRailsFiltered.length > 0) && (
        <section data-testid="radio-discover-ai-highlight"
          className="relative mb-8 rounded-3xl p-[1.5px]
                              bg-gradient-to-br from-cyan-400/70 via-fuchsia-500/50 to-purple-500/70
                              shadow-[0_0_44px_-12px_rgba(34,211,238,0.5)]">
          <div className="rounded-[22px] bg-[#0b0f1a]/95 backdrop-blur px-4 sm:px-6 pt-5 pb-1">
            <div className="flex items-center gap-2 mb-4">
              <span className="inline-flex items-center gap-1.5 px-2.5 h-7 rounded-full
                                          text-[11px] font-mono uppercase tracking-widest
                                          bg-cyan-400/15 text-cyan-300 border border-cyan-400/30">
                <Sparkles size={13} /> FUUSIC AI Radio
              </span>
              <span className="text-xs text-white/50 hidden sm:inline">
                Personalised, AI-curated stations made for you
              </span>
            </div>
            {pinnedStations.length > 0 && (
              <StationRail rail={{ id: "pinned", title: "Pinned", stations: pinnedStations }}
                onActivate={onActivate} />
            )}
            {aiRailsFiltered.map((r) => (
              <StationRail key={r.id} rail={r} onActivate={onActivate} />
            ))}
          </div>
        </section>
      )}

      {view === "ai" && pinnedStations.length === 0 && aiRailsFiltered.length === 0 && (
        <div className="text-sm text-white/40 py-10 text-center"
          data-testid="radio-discover-ai-empty">
          No AI stations available right now — check back soon.
        </div>
      )}

      {view !== "ai" && (
        <>
          {/* Flagship strip (live) — sits BELOW the AI highlight. */}
          <div className="mb-8">
            <FlagshipStrip
              title="Flagship Stations"
              testId="radio-discover-flagship-strip"
              limit={12} />
          </div>

          {/* Remaining station rails (community, local, trending, …) */}
          {otherStationRails.map((r) => (
            <StationRail key={r.id} rail={r} onActivate={onActivate} />
          ))}

          {/* Chip rails */}
          {chipRails.map((r) => (
            <ChipRail
              key={r.id} rail={r}
              paramKey={r.id === "languages" ? "language"
                                  : r.id === "genres" ? "category"
                                  : r.id === "countries" ? "country" : "category"}
            />
          ))}
        </>
      )}

      <div className="text-xs text-white/30 pt-8 border-t border-white/[0.06]"
                data-testid="radio-discover-attribution">
        Imported station data sourced from
        <a href="https://www.radio-browser.info/"
              target="_blank" rel="noopener noreferrer"
              className="text-cyan-400 hover:text-cyan-300 mx-1 underline">
          radio-browser.info
        </a>
        — a community-maintained directory of free radio streams.
      </div>
    </div>
  );
}
