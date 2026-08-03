// Phase FUN.1 — Reusable Flagship strip.  Renders a horizontal scrollable
// row (mobile) / grid (desktop) of flagship stations.  Used on Home,
// Business Profile, RadioLife /listen, Landing, admin dashboard, etc.
//
// Every station card fires the SAME player pathway used by imported
// stations (`usePlayerStore.setImportedStation`) so pre-roll ads still
// run (Phase Π+4 FIX A).
import { useEffect, useState } from "react";
import axios from "axios";
import { Play, Loader2, AlertCircle, Radio, Flame } from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import FlagshipBadge from "@/components/FlagshipBadge";
import { useLiveFlagshipBoosts } from "@/hooks/useLiveFlagshipBoosts";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function FlagshipStrip({
  category = null,
  matchesLanguage = null,
  matchesCity = null,
  matchesCountryCode = null,
  limit = 12,
  title = "Flagship Stations",
  variant = "hero",   // hero | inline | grid
  light = false,
  testId = "flagship-strip",
}) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  // Phase F — Monetization M4: overlay "🔥 Boosted" chip on winning cards.
  const { byStationId: boostByStationId, recordImpression } =
    useLiveFlagshipBoosts(matchesCountryCode || null);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams();
        if (category) params.set("category", category);
        if (matchesLanguage) params.set("matches_language", matchesLanguage);
        if (matchesCity) params.set("matches_city", matchesCity);
        if (matchesCountryCode) params.set("matches_country_code", matchesCountryCode);
        params.set("limit", limit);
        const { data } = await axios.get(`${API}/stations/flagship?${params}`);
        setItems(data.items || []);
      } catch (_) {}
      finally { setLoading(false); }
    })();
  }, [category, matchesLanguage, matchesCity, matchesCountryCode, limit]);

  if (loading) {
    return (
      <div className="py-6 text-center" data-testid={`${testId}-loading`}>
        <Loader2 className="w-5 h-5 animate-spin mx-auto text-amber-500" />
      </div>
    );
  }
  if (items.length === 0) return null;

  const play = (station) => {
    if (station.playable_status === "unreachable") return;
    setImportedStation({
      // Shape matches what ImportedStreamBridge expects (parity with
      // the imported_radio_stations schema used elsewhere).
      id:                    station.id,
      station_id:      station.id,
      name:                station.name,
      url_resolved: station.url_resolved,
      url:                  station.url_resolved || station.url,
      favicon:          station.logo_url || station.favicon,
      logo_url:        station.logo_url || station.favicon,
      homepage:      station.homepage,
      country:          station.country,
      language:        station.language,
      tags_json:      station.tags_json,
      is_flagship:  true,
      flagship_slug: station.flagship_slug,
    });
  };

  const gridCls = variant === "hero"
    ? "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3"
    : "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3";

  return (
    <section data-testid={testId}
                    data-flagship-count={items.length}
                    data-flagship-category={category || ""}>
      <div className="flex items-end justify-between mb-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest text-amber-500">
            FunAsia Network · Flagship
          </div>
          <h2 className={`mt-0.5 text-xl sm:text-2xl font-bold ${
                                light ? "text-slate-900" : "text-white"}`}>
            🌟 {title}
          </h2>
        </div>
      </div>
      <div className={gridCls}>
        {items.map((s) => (
          <FlagshipCard key={s.id} station={s} onPlay={() => play(s)}
                                    light={light}
                                    boost={boostByStationId[s.id]}
                                    onImpression={recordImpression} />
        ))}
      </div>
    </section>
  );
}

function FlagshipCard({ station: s, onPlay, light, boost, onImpression }) {
  const unreachable = s.playable_status === "unreachable";
  const pending    = s.playable_status === "pending" && !s.url_resolved;
  const disabled   = unreachable || pending;
  // Phase F — record an impression the first time this card is
  // rendered (dedup at server side via 60-min bucket).
  useEffect(() => {
    if (boost && onImpression) onImpression(boost.activation_id);
  }, [boost, onImpression]);
  const badgeColorMap = {
    orange:    "bg-orange-500 text-slate-950",
    amber:      "bg-amber-500 text-slate-950",
    fuchsia:  "bg-fuchsia-500 text-white",
    emerald:  "bg-emerald-500 text-slate-950",
    sky:          "bg-sky-500 text-white",
  };
  const boostChip = boost ? (
    <div className="absolute top-2 right-2 z-10"
              title={boost.creative?.display_headline || ""}
              data-testid={`flagship-boost-chip-${s.flagship_slug || s.id}`}>
      <span className={`inline-flex items-center gap-1 text-[10px] font-black
                                          uppercase tracking-widest px-2 py-1 rounded-full shadow-lg
                                          ${badgeColorMap[boost.creative?.badge_color] ||
                                              badgeColorMap.orange}`}>
        <Flame size={10} /> Boosted
      </span>
    </div>
  ) : null;
  // Phase A Item 2: RadioLife (light) branch shows a purple/pink gradient
  // border ring wrapping the card. Legacy dark branch stays untouched.
  if (light) {
    return (
      <div
        onClick={() => !disabled && onPlay()}
        data-testid={`flagship-card-${s.flagship_slug || s.id}`}
        data-flagship-slug={s.flagship_slug || ""}
        data-playable-status={s.playable_status || "unknown"}
        className={`relative rounded-2xl p-[2px]
                                bg-gradient-to-br from-purple-500 to-pink-500
                                shadow-md shadow-purple-500/10
                                hover:shadow-lg hover:shadow-purple-500/20
                                transition
                                ${disabled ? "opacity-70" : "cursor-pointer"}`}>
        <div className="rounded-[14px] overflow-hidden bg-white group">
          <div className="aspect-square relative">
            {boostChip}
            <img src={s.logo_url || s.favicon}
                        alt={s.name}
                        className="w-full h-full object-cover"
                        onError={(e) => {
                          const initials = (s.name || "?").split(/\s+/).slice(0, 2)
                            .map((w) => w[0]).join("").toUpperCase();
                          const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256' viewBox='0 0 256 256'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' stop-color='#8b5cf6'/><stop offset='100%' stop-color='#ec4899'/></linearGradient></defs><rect width='256' height='256' fill='url(#g)'/><text x='50%' y='55%' font-family='system-ui,sans-serif' font-size='96' font-weight='900' text-anchor='middle' fill='#fff' dominant-baseline='middle'>${initials}</text></svg>`;
                          e.currentTarget.src = "data:image/svg+xml;base64," + btoa(svg);
                          e.currentTarget.onerror = null;
                        }} />
            {!disabled && (
              <div className="absolute inset-0 flex items-center justify-center
                                              bg-black/40 opacity-0 group-hover:opacity-100
                                              transition-opacity">
                <div className="w-12 h-12 rounded-full bg-amber-500 flex
                                                items-center justify-center">
                  <Play className="w-5 h-5 fill-slate-950 text-slate-950 ml-0.5" />
                </div>
              </div>
            )}
            <div className="absolute top-2 left-2">
              <FlagshipBadge compact />
            </div>
          </div>
          <div className="p-3">
            <div className="text-sm font-bold truncate text-slate-900"
                        data-testid={`flagship-card-name-${s.flagship_slug || s.id}`}>
              {s.name}
            </div>
            <div className="mt-0.5 flex items-center gap-1 text-[10px]">
              <span className="text-slate-500">
                {(s.language_codes || []).join(" · ").toUpperCase() ||
                              (s.language || "").toUpperCase()}
              </span>
              {s.frequency && (
                <>
                  <span className="text-slate-500">·</span>
                  <span className="text-slate-500">{s.frequency}</span>
                </>
              )}
            </div>
            {unreachable && (
              <div className="mt-1 inline-flex items-center gap-1 text-[10px]
                                              text-amber-600"
                            data-testid={`flagship-card-unavailable-${s.flagship_slug}`}>
                <AlertCircle className="w-3 h-3" /> Temporarily unavailable
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }
  const rootCls = `
    relative rounded-2xl overflow-hidden group
    bg-slate-900 border border-slate-800 hover:border-purple-500
    ${disabled ? "opacity-70" : "cursor-pointer"}
    transition
    before:content-[''] before:absolute before:inset-0 before:rounded-2xl
    before:pointer-events-none
    before:bg-gradient-to-br before:from-purple-500/10 before:via-transparent before:to-pink-500/10
  `;
  return (
    <div
      className={rootCls}
      onClick={() => !disabled && onPlay()}
      data-testid={`flagship-card-${s.flagship_slug || s.id}`}
      data-flagship-slug={s.flagship_slug || ""}
      data-playable-status={s.playable_status || "unknown"}>
      <div className="aspect-square relative">
        {boostChip}
        <img src={s.logo_url || s.favicon}
                    alt={s.name}
                    className="w-full h-full object-cover"
                    onError={(e) => {
                      // Phase FUN.1.1 — station-initials SVG fallback (data URI so
                      // it works even when logos can't be resolved).
                      const initials = (s.name || "?").split(/\s+/).slice(0, 2)
                        .map((w) => w[0]).join("").toUpperCase();
                      const svg = `<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256' viewBox='0 0 256 256'><defs><linearGradient id='g' x1='0%' y1='0%' x2='100%' y2='100%'><stop offset='0%' stop-color='#8b5cf6'/><stop offset='100%' stop-color='#ec4899'/></linearGradient></defs><rect width='256' height='256' fill='url(#g)'/><text x='50%' y='55%' font-family='system-ui,sans-serif' font-size='96' font-weight='900' text-anchor='middle' fill='#fff' dominant-baseline='middle'>${initials}</text></svg>`;
                      e.currentTarget.src = "data:image/svg+xml;base64," + btoa(svg);
                      e.currentTarget.onerror = null;
                    }} />
        {!disabled && (
          <div className="absolute inset-0 flex items-center justify-center
                                          bg-black/40 opacity-0 group-hover:opacity-100
                                          transition-opacity">
            <div className="w-12 h-12 rounded-full bg-amber-500 flex
                                            items-center justify-center">
              <Play className="w-5 h-5 fill-slate-950 text-slate-950 ml-0.5" />
            </div>
          </div>
        )}
        <div className="absolute top-2 left-2">
          <FlagshipBadge compact />
        </div>
      </div>
      <div className="p-3">
        <div className={`text-sm font-bold truncate ${light ? "text-slate-900" : "text-white"}`}
                    data-testid={`flagship-card-name-${s.flagship_slug || s.id}`}>
          {s.name}
        </div>
        <div className="mt-0.5 flex items-center gap-1 text-[10px]">
          <span className={light ? "text-slate-500" : "text-slate-500"}>
            {(s.language_codes || []).join(" · ").toUpperCase() ||
                          (s.language || "").toUpperCase()}
          </span>
          {s.frequency && (
            <>
              <span className="text-slate-600">·</span>
              <span className={light ? "text-slate-500" : "text-slate-500"}>{s.frequency}</span>
            </>
          )}
        </div>
        {unreachable && (
          <div className="mt-1 inline-flex items-center gap-1 text-[10px]
                                          text-amber-500"
                        data-testid={`flagship-card-unavailable-${s.flagship_slug}`}>
            <AlertCircle className="w-3 h-3" /> Temporarily unavailable
          </div>
        )}
      </div>
    </div>
  );
}
