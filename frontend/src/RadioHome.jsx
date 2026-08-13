// Phase RL.2 — RadioLife /radio look refresh + marketing splash.
// Renders at `/radio` (both design variants).  Replaces the old
// RadioDiscover-first landing with a marketing hero + flagship rail +
// gamified tiles + browse teaser.  The existing RadioDiscover is still
// reachable at `/radio/discover` for anyone with a bookmark.
import { useEffect, useMemo, useRef, useState, forwardRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Radio, Sparkles, Gift, MapPin, Play, ChevronRight, Loader2,
  Gamepad2, Ticket, Coins, Zap, Award, PartyPopper, HandCoins,
  ScrollText, Trophy, ArrowRight, Search, X,
} from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import { useGeoStore } from "@/store/useGeoStore";
import BannerZoneSlot from "@/components/BannerZoneSlot";
import SafeImage from "@/components/SafeImage";
import { toPlayableStreamUrl } from "@/utils/streamUrl";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

// ─── Public helper: scroll to flagship rail (used by primary CTA) ────
const scrollToRail = () => {
  const el = document.querySelector('[data-testid="radio-flagship-rail"]');
  if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
};


export default function RadioHome() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const navigate = useNavigate();
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  const market = useGeoStore((s) => s.market);

  const [flagships, setFlagships] = useState(null);
  const railRef = useRef(null);

  useEffect(() => {
    (async () => {
      try {
        const params = new URLSearchParams();
        params.set("limit", "12");
        if (market) params.set("matches_country_code", market);
        const { data } = await axios.get(`${API}/stations/flagship?${params}`);
        setFlagships(data.items || []);
      } catch (_) { setFlagships([]); }
    })();
  }, [market]);

  const primaryFlagship = useMemo(
    () => (flagships || []).find(
      (s) => s.playable_status !== "unreachable") || null,
    [flagships]);

  function startListening() {
    if (primaryFlagship) {
      setImportedStation({
        id:                    primaryFlagship.id,
        station_id:      primaryFlagship.id,
        name:                primaryFlagship.name,
        url_resolved: primaryFlagship.url_resolved,
        url:                  primaryFlagship.url_resolved || primaryFlagship.url,
        favicon:          primaryFlagship.logo_url || primaryFlagship.favicon,
        logo_url:        primaryFlagship.logo_url || primaryFlagship.favicon,
        homepage:      primaryFlagship.homepage,
        country:          primaryFlagship.country,
        tags_json:      primaryFlagship.tags_json,
        is_flagship:  true,
        flagship_slug: primaryFlagship.flagship_slug,
      });
      // Scroll down so users see the player start with the rail visible.
      scrollToRail();
    } else {
      scrollToRail();
    }
  }

  const shellBg = light
    ? "bg-gradient-to-b from-white via-fuchsia-50/40 to-white"
    : "bg-slate-950";
  const textPrimary = light ? "text-slate-900" : "text-white";

  return (
    <div className={`${shellBg} ${textPrimary} min-h-screen`}
              data-testid="radio-home-page">
      <MarketingHero
        light={light}
        onStartListening={startListening}
        onSeeRewards={() => navigate("/wallet")}
        primaryFlagship={primaryFlagship} />

      {/* Phase AD.11 — landing_hero banner slot. */}
      <div className="max-w-6xl mx-auto px-4 sm:px-6 pt-4">
        <BannerZoneSlot zone="landing_hero" />
      </div>

      <FlagshipRail
        ref={railRef}
        light={light}
        items={flagships}
        onPlay={(s) => {
          setImportedStation({
            id: s.id, station_id: s.id, name: s.name,
            url_resolved: s.url_resolved,
            url: s.url_resolved || s.url,
            favicon: s.logo_url || s.favicon,
            logo_url: s.logo_url || s.favicon,
            homepage: s.homepage, country: s.country,
            tags_json: s.tags_json, is_flagship: true,
            flagship_slug: s.flagship_slug,
          });
        }} />

      <GamesSection light={light} />

      <BrowseTeaser light={light} />

      <BottomStrip light={light} />
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Marketing Hero
// ═══════════════════════════════════════════════════════════════════
function MarketingHero({ light, onStartListening, onSeeRewards,
                                                      primaryFlagship }) {
  // RadioLife light: purple/pink gradient card with white text.
  // Legacy dark: deep slate with amber accents.
  const bg = light
    ? "bg-gradient-to-br from-fuchsia-500 via-purple-600 to-indigo-600"
    : "bg-gradient-to-br from-slate-900 via-amber-950/40 to-slate-900 border border-amber-500/20";
  const accent = light ? "text-amber-300" : "text-amber-400";
  const headlineCls = light ? "text-white" : "text-white";
  const subCls = light ? "text-white/85" : "text-slate-300";
  const bulletBg = light
    ? "bg-white/10 backdrop-blur-sm border border-white/15 text-white"
    : "bg-slate-800/60 border border-slate-700 text-slate-200";
  const primaryBtn = light
    ? "bg-white text-purple-700 hover:bg-white/95 shadow-2xl shadow-black/20"
    : "bg-amber-500 text-slate-900 hover:bg-amber-400 shadow-2xl shadow-amber-500/30";
  const secondaryBtn = light
    ? "bg-white/10 backdrop-blur-sm text-white border border-white/25 hover:bg-white/20"
    : "bg-slate-800 text-white border border-slate-700 hover:bg-slate-700";

  const bullets = [
    { Icon: Radio,        text: "50,000+ radio stations + AI-curated channels" },
    { Icon: Gamepad2,  text: "Play & Win — spin, scratch, trivia, predict" },
    { Icon: Ticket,      text: "Real rewards — nightlife, bars, movies, food" },
    { Icon: MapPin,      text: "Deals near you every day" },
  ];

  return (
    <section className={`${bg} relative overflow-hidden`}
                        data-testid="radio-hero">
      {/* Ambient decorative bokeh — desktop only */}
      <div aria-hidden className="absolute inset-0 pointer-events-none hidden md:block">
        <div className={`absolute -top-20 -right-20 w-80 h-80 rounded-full blur-3xl ${
                                        light ? "bg-fuchsia-300/40" : "bg-amber-500/10"}`}></div>
        <div className={`absolute -bottom-32 -left-20 w-96 h-96 rounded-full blur-3xl ${
                                        light ? "bg-indigo-400/30" : "bg-purple-500/10"}`}></div>
      </div>

      <div className="relative max-w-6xl mx-auto px-4 sm:px-6 py-14 sm:py-20 lg:py-24">
        <div className="grid lg:grid-cols-[1.35fr,1fr] gap-8 lg:gap-12 items-center">
          {/* Copy */}
          <div>
            <div className={`inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest ${accent}`}>
              <Sparkles className="w-3 h-3" /> Only on RadioLife
            </div>
            <h1 data-testid="radio-hero-headline"
                    className={`mt-3 text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight leading-[1.05] ${headlineCls}`}>
              The only radio that <span className={accent}>pays YOU</span> to listen.
            </h1>
            <p data-testid="radio-hero-subtitle"
                  className={`mt-4 text-base sm:text-lg lg:text-xl ${subCls} max-w-xl leading-relaxed`}>
              Earn points every minute. Win giveaways, concert tickets, club night
              access, restaurant deals — everything happening in your city.
            </p>

            {/* Feature bullets */}
            <ul className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-2 max-w-2xl"
                    data-testid="radio-hero-bullets">
              {bullets.map(({ Icon, text }, i) => (
                <li key={i}
                        className={`${bulletBg} flex items-center gap-2 px-3 py-2 rounded-xl text-sm`}
                        data-testid={`radio-hero-bullet-${i}`}>
                  <Icon className={`w-4 h-4 ${accent} flex-shrink-0`} />
                  <span className="leading-tight">{text}</span>
                </li>
              ))}
            </ul>

            {/* CTAs */}
            <div className="mt-7 flex flex-col sm:flex-row gap-3">
              <button onClick={onStartListening}
                              data-testid="radio-hero-cta-listen"
                              className={`inline-flex items-center justify-center gap-2 ${primaryBtn} px-6 py-3.5 rounded-full font-black text-base transition transform hover:-translate-y-0.5`}>
                <Play className="w-5 h-5 fill-current" />
                Start Listening
              </button>
              <button onClick={onSeeRewards}
                              data-testid="radio-hero-cta-rewards"
                              className={`inline-flex items-center justify-center gap-2 ${secondaryBtn} px-6 py-3.5 rounded-full font-black text-base transition`}>
                <Gift className="w-5 h-5" />
                See rewards
              </button>
            </div>
          </div>

          {/* Right side — animated equalizer + featured flagship glimpse */}
          <div className="hidden lg:block">
            <div className={`${light ? "bg-white/10 border border-white/20"
                                                              : "bg-slate-900/60 border border-slate-800"}
                                            backdrop-blur-sm rounded-3xl p-6`}>
              <div className={`text-[10px] uppercase tracking-widest font-mono ${accent} mb-3`}>
                Now trending
              </div>
              {primaryFlagship ? (
                <div className="flex items-center gap-4">
                  <SafeImage
                    src={primaryFlagship.logo_url || primaryFlagship.favicon}
                    alt={primaryFlagship.name}
                    fallbackKind="station"
                    fallbackText={primaryFlagship.name}
                    className="w-16 h-16 rounded-2xl object-cover bg-black/20 flex-shrink-0" />
                  <div className="min-w-0">
                    <div className={`text-xl font-black ${light ? "text-white" : "text-white"} truncate`}>
                      {primaryFlagship.name}
                    </div>
                    <div className={`text-xs ${light ? "text-white/70" : "text-slate-400"} truncate`}>
                      {primaryFlagship.frequency} · {primaryFlagship.city || primaryFlagship.country}
                    </div>
                    <div className="mt-2 flex items-center gap-1">
                      {[8, 14, 20, 12, 16, 10, 18].map((h, i) => (
                        <span key={i}
                                    style={{ height: `${h}px`,
                                                        animation: `radiolife-eq 1.1s ${i * 0.09}s infinite ease-in-out`}}
                                    className={`w-1 rounded-full ${light ? "bg-amber-300" : "bg-amber-400"}`}></span>
                      ))}
                    </div>
                  </div>
                </div>
              ) : (
                <Loader2 className="w-6 h-6 animate-spin text-amber-300" />
              )}
              <style>{`
                @keyframes radiolife-eq {
                  0%,100% { transform: scaleY(0.4); }
                  50%          { transform: scaleY(1); }
                }
              `}</style>
              <div className={`mt-4 text-[11px] ${light ? "text-white/70" : "text-slate-400"}`}>
                Tap “Start Listening” to tune in →
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Flagship rail — horizontal scroll of region-matched stations
// ═══════════════════════════════════════════════════════════════════
const FlagshipRail = forwardRef(function FlagshipRail(
  { light, items, onPlay }, ref) {
  const cardBase = light
    ? "bg-white border border-slate-200 hover:border-purple-400 hover:shadow-xl hover:shadow-purple-500/10"
    : "bg-slate-900 border border-slate-800 hover:border-amber-500/50 hover:shadow-xl hover:shadow-amber-500/10";
  const nameCls = light ? "text-slate-900" : "text-white";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <section ref={ref}
                          className="max-w-6xl mx-auto px-4 sm:px-6 pt-10 pb-8"
                          data-testid="radio-flagship-rail">
      <div className="flex items-end justify-between gap-3 mb-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight">
            Flagship stations
          </h2>
          <p className={`text-sm mt-0.5 ${muted}`}>Trending in your city · tap to tune in</p>
        </div>
        <Link to="/radio/browse"
                    className={`hidden sm:inline-flex items-center gap-1 text-xs font-bold ${
                                    light ? "text-purple-600 hover:text-purple-700"
                                                  : "text-amber-500 hover:text-amber-400"}`}
                    data-testid="radio-flagship-rail-all">
          See all <ChevronRight className="w-3.5 h-3.5" />
        </Link>
      </div>

      {items === null ? (
        <div className="py-8 text-center"><Loader2 className="w-5 h-5 animate-spin mx-auto text-amber-500" /></div>
      ) : items.length === 0 ? (
        <div className={`py-6 text-center text-sm ${muted}`}
                    data-testid="radio-flagship-rail-empty">
          No flagships available in your region yet.
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto snap-x snap-mandatory pb-3 -mx-4 px-4 scrollbar-hide"
                    data-testid="radio-flagship-rail-list">
          {items.map((s) => {
            const slug = s.flagship_slug || s.id;
            return (
              <button
                key={s.id}
                onClick={() => onPlay(s)}
                data-testid={`radio-flagship-card-${slug}`}
                className={`${cardBase} snap-start flex-shrink-0 w-[170px] sm:w-[190px] rounded-2xl p-4 text-left transition transform hover:-translate-y-0.5 group`}>
                <div className="relative w-full aspect-square rounded-xl overflow-hidden bg-slate-800/40">
                  <SafeImage src={s.logo_url || s.favicon} alt={s.name}
                                            fallbackKind="station"
                                            fallbackText={s.name}
                                            className="w-full h-full object-cover" />
                  <div className={`absolute inset-0 grid place-items-center bg-black/50 opacity-0 group-hover:opacity-100 transition`}>
                    <div className={`w-12 h-12 rounded-full grid place-items-center ${
                                                          light ? "bg-white text-purple-600" : "bg-amber-500 text-slate-900"}`}>
                      <Play className="w-5 h-5 fill-current" />
                    </div>
                  </div>
                </div>
                <div className={`mt-3 font-bold truncate ${nameCls}`}>{s.name}</div>
                <div className={`text-[11px] mt-0.5 truncate ${muted}`}>
                  {s.frequency || "Live"} · {s.city || s.country || ""}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </section>
  );
});


// ═══════════════════════════════════════════════════════════════════
// Games section — 4 large tiles
// ═══════════════════════════════════════════════════════════════════
function GamesSection({ light }) {
  const navigate = useNavigate();
  const tiles = [
    {
      id: "spin", Icon: Zap, name: "Spin & Win",
      preview: "Daily wheel · earn 10-500 pts",
      to: "/predict-win",
      gradient: light
        ? "from-amber-400 to-pink-500"
        : "from-amber-500/30 to-pink-500/20",
      testid: "radio-games-tile-spin",
      comingSoon: false,
    },
    {
      id: "scratch", Icon: ScrollText, name: "Scratch Card",
      preview: "Instant prizes · daily 1x free",
      gradient: light
        ? "from-slate-300 to-slate-400"
        : "from-slate-700 to-slate-800",
      testid: "radio-games-tile-scratch",
      comingSoon: true,
    },
    {
      id: "predict", Icon: HandCoins, name: "Predict & Win",
      preview: "Yes / No markets · real cash",
      to: "/predict-win",
      gradient: light
        ? "from-purple-500 to-indigo-500"
        : "from-purple-500/30 to-indigo-500/20",
      testid: "radio-games-tile-predict",
      comingSoon: false,
    },
    {
      id: "trivia", Icon: Trophy, name: "Trivia",
      preview: "Live rooms · daily quiz",
      to: "/trivia",
      gradient: light
        ? "from-emerald-500 to-teal-500"
        : "from-emerald-500/30 to-teal-500/20",
      testid: "radio-games-tile-trivia",
      comingSoon: false,
    },
  ];

  return (
    <section className="max-w-6xl mx-auto px-4 sm:px-6 py-8"
                        data-testid="radio-games-section">
      <div className="flex items-end justify-between gap-3 mb-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight inline-flex items-center gap-2">
            <Gamepad2 className={`w-6 h-6 ${light ? "text-purple-600" : "text-amber-400"}`} />
            Play & Win
          </h2>
          <p className={`text-sm mt-0.5 ${light ? "text-slate-500" : "text-slate-400"}`}>
            Real rewards every day · no purchase necessary
          </p>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {tiles.map((t) => (
          <button
            key={t.id}
            disabled={t.comingSoon}
            onClick={() => t.to && navigate(t.to)}
            data-testid={t.testid}
            className={`relative overflow-hidden rounded-2xl p-5 text-left transition group ${
                                        t.comingSoon
                                            ? "opacity-60 cursor-not-allowed"
                                            : "hover:-translate-y-1 transform"}`}>
            <div className={`absolute inset-0 bg-gradient-to-br ${t.gradient}`}></div>
            <div className={`absolute inset-0 ${light ? "bg-white/0" : "bg-slate-950/40"} group-hover:bg-white/5 transition`}></div>
            <div className="relative">
              <t.Icon className={`w-10 h-10 ${light ? "text-white drop-shadow-md" : "text-white"}`} />
              <div className={`mt-4 text-lg font-black text-white leading-tight`}>
                {t.name}
              </div>
              <div className={`mt-1 text-[11px] text-white/80`}>
                {t.preview}
              </div>
              <div className={`mt-4 inline-flex items-center gap-1 text-xs font-bold ${
                                                    t.comingSoon ? "text-white/60" : "text-white"}`}>
                {t.comingSoon ? "Coming soon" : (
                  <>Play now <ArrowRight className="w-3.5 h-3.5" /></>
                )}
              </div>
            </div>
          </button>
        ))}
      </div>
    </section>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Browse teaser — auto top-played stations + language/genre/country
// filters + search + hot/live badges + remembered filters.
// ═══════════════════════════════════════════════════════════════════
const DISCOVER_FILTERS_KEY = "radiolife.discover.filters";

const COUNTRY_NAMES = {
  US: "USA", GB: "UK", DE: "Germany", FR: "France", IN: "India", IT: "Italy",
  ES: "Spain", RU: "Russia", MX: "Mexico", TR: "Turkey", CH: "Switzerland",
  GR: "Greece", NL: "Netherlands", RO: "Romania", PL: "Poland", AE: "UAE",
  CA: "Canada", AU: "Australia", BR: "Brazil", PK: "Pakistan", SA: "Saudi Arabia",
  EG: "Egypt", JP: "Japan", CN: "China", KR: "Korea", PT: "Portugal",
  SE: "Sweden", NO: "Norway", DK: "Denmark", BE: "Belgium", AT: "Austria",
  IE: "Ireland", UA: "Ukraine", ID: "Indonesia", PH: "Philippines", TH: "Thailand",
  ZA: "South Africa", NG: "Nigeria", AR: "Argentina", CO: "Colombia",
};

function countryName(cc) { return COUNTRY_NAMES[cc] || cc; }

function flagEmoji(cc) {
  if (!cc || !/^[A-Za-z]{2}$/.test(cc)) return "";
  const base = 0x1F1E6;
  const up = cc.toUpperCase();
  return String.fromCodePoint(base + up.charCodeAt(0) - 65, base + up.charCodeAt(1) - 65);
}

function FilterChip({ light, active, onClick, children, testid }) {
  return (
    <button type="button" onClick={onClick} data-testid={testid}
      className={`shrink-0 px-3.5 py-1.5 rounded-full text-xs font-black whitespace-nowrap transition ${
        active
          ? (light ? "bg-purple-600 text-white shadow shadow-purple-500/30"
                   : "bg-amber-500 text-slate-900 shadow shadow-amber-500/30")
          : (light ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
                   : "bg-slate-800 text-slate-300 hover:bg-slate-700")}`}>
      {children}
    </button>
  );
}

function BrowseTeaser({ light }) {
  const navigate = useNavigate();
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  const saved = useMemo(() => {
    try { return JSON.parse(localStorage.getItem(DISCOVER_FILTERS_KEY) || "{}"); }
    catch (_) { return {}; }
  }, []);
  const [langs, setLangs] = useState([]);
  const [genres, setGenres] = useState([]);
  const [countries, setCountries] = useState([]);
  const [lang, setLang] = useState(saved.lang || "");
  const [genre, setGenre] = useState(saved.genre || "");
  const [country, setCountry] = useState(saved.country || "");
  const [qInput, setQInput] = useState("");
  const [q, setQ] = useState("");
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);

  const cardCls = light
    ? "bg-white border border-slate-200 hover:border-purple-400"
    : "bg-slate-900/60 border border-slate-800 hover:border-amber-500/50";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const nameCls = light ? "text-slate-900" : "text-white";

  // Filter facets (language + genre + country) — loaded once from discover.
  useEffect(() => {
    (async () => {
      try {
        const { data } = await axios.get(`${API}/radio/discover`);
        const rails = {};
        for (const r of (data?.rails || [])) rails[r.id] = r;
        setLangs((rails.languages?.facet_chips || []).slice(0, 12));
        setGenres((rails.genres?.facet_chips || []).slice(0, 12));
        setCountries((rails.countries?.facet_chips || []).slice(0, 20));
      } catch (_) { /* filters optional */ }
    })();
  }, []);

  // Debounce the search box.
  useEffect(() => {
    const t = setTimeout(() => setQ(qInput.trim()), 350);
    return () => clearTimeout(t);
  }, [qInput]);

  // Remember the listener's language/genre/country choice.
  useEffect(() => {
    try { localStorage.setItem(DISCOVER_FILTERS_KEY, JSON.stringify({ lang, genre, country })); }
    catch (_) { /* private mode */ }
  }, [lang, genre, country]);

  // Top-played stations, re-fetched whenever a filter or search changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const params = new URLSearchParams({ source: "imported", limit: "24" });
        if (lang) params.set("language", lang);
        if (genre) params.set("category", genre);
        if (country) params.set("country", country);
        if (q) params.set("q", q);
        const { data } = await axios.get(`${API}/radio/browse?${params}`);
        if (!cancelled) setItems(data.items || []);
      } catch (_) { if (!cancelled) setItems([]); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [lang, genre, country, q]);

  const play = async (s) => {
    if (s.source === "bigfm_ai") {
      navigate(`/radio?ch=${encodeURIComponent(s.id)}&autoplay=1`);
      return;
    }
    try {
      const r = await axios.post(`${API}/radio/play/${s.id}`, {}, { withCredentials: true });
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

  return (
    <section className="max-w-6xl mx-auto px-4 sm:px-6 py-8"
                        data-testid="radio-browse-teaser">

      <div className="flex items-end justify-between gap-3 mb-4">
        <div>
          <h2 className="text-2xl sm:text-3xl font-black tracking-tight">
            Discover more
          </h2>
          <p className={`text-sm mt-0.5 ${muted}`}>
            One app · 50,000+ radio stations · every language, every mood
          </p>
        </div>
        <Link to="/radio/browse" data-testid="radio-browse-teaser-cta-top"
          className={`hidden sm:inline-flex items-center gap-1.5 text-sm font-black whitespace-nowrap ${
            light ? "text-purple-600 hover:text-purple-500" : "text-amber-400 hover:text-amber-300"}`}>
          See all <ArrowRight className="w-4 h-4" />
        </Link>
      </div>

      {/* Search */}
      <div className="mb-3">
        <div className={`relative flex items-center rounded-full ${light ? "bg-slate-100" : "bg-slate-800/70"}`}>
          <Search className={`w-4 h-4 ml-3.5 shrink-0 ${muted}`} />
          <input
            data-testid="radio-browse-search"
            value={qInput}
            onChange={(e) => setQInput(e.target.value)}
            placeholder="Search stations by name…"
            className={`flex-1 bg-transparent px-2.5 py-2.5 text-sm outline-none ${
              light ? "text-slate-900 placeholder-slate-400" : "text-white placeholder-slate-500"}`} />
          {qInput && (
            <button type="button" onClick={() => setQInput("")}
              data-testid="radio-browse-search-clear" className="mr-2 p-1 rounded-full hover:bg-black/10">
              <X className={`w-4 h-4 ${muted}`} />
            </button>
          )}
        </div>
      </div>

      {/* Language filter */}
      {langs.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-1"
                    data-testid="radio-browse-lang-chips">
          <span className={`shrink-0 text-[11px] font-black uppercase tracking-wider ${muted}`}>Language</span>
          <FilterChip light={light} active={!lang} onClick={() => setLang("")} testid="radio-browse-lang-all">All</FilterChip>
          {langs.map((l) => (
            <FilterChip light={light} key={l.slug} active={lang === l.slug} onClick={() => setLang(l.slug)}
                        testid={`radio-browse-lang-${l.slug}`}>{l.label}</FilterChip>
          ))}
        </div>
      )}

      {/* Genre filter */}
      {genres.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-1"
                    data-testid="radio-browse-genre-chips">
          <span className={`shrink-0 text-[11px] font-black uppercase tracking-wider ${muted}`}>Genre</span>
          <FilterChip light={light} active={!genre} onClick={() => setGenre("")} testid="radio-browse-genre-all">All</FilterChip>
          {genres.map((g) => (
            <FilterChip light={light} key={g.slug} active={genre === g.slug} onClick={() => setGenre(g.slug)}
                        testid={`radio-browse-genre-${g.slug}`}>{g.label}</FilterChip>
          ))}
        </div>
      )}

      {/* Country filter */}
      {countries.length > 0 && (
        <div className="flex items-center gap-2 overflow-x-auto pb-2 mb-4"
                    data-testid="radio-browse-country-chips">
          <span className={`shrink-0 text-[11px] font-black uppercase tracking-wider ${muted}`}>Country</span>
          <FilterChip light={light} active={!country} onClick={() => setCountry("")} testid="radio-browse-country-all">All</FilterChip>
          {countries.map((c) => (
            <FilterChip light={light} key={c.slug} active={country === c.slug} onClick={() => setCountry(c.slug)}
                        testid={`radio-browse-country-${c.slug}`}>{`${flagEmoji(c.slug)} ${countryName(c.slug)}`}</FilterChip>
          ))}
        </div>
      )}

      {loading && items === null ? (
        <div className="py-10 text-center"><Loader2 className="w-5 h-5 animate-spin mx-auto text-amber-500" /></div>
      ) : (items || []).length === 0 ? (
        <div className={`py-10 text-center text-sm ${muted}`} data-testid="radio-browse-teaser-empty">
          No stations match these filters. Try clearing a filter.
        </div>
      ) : (
        <div className={`flex gap-3 overflow-x-auto pb-3 -mx-4 px-4 sm:mx-0 sm:px-0 snap-x transition-opacity ${loading ? "opacity-50" : "opacity-100"}`}
                    data-testid="radio-browse-teaser-scroll">
          {(items || []).map((s, idx) => (
            <button
              key={s.id}
              onClick={() => play(s)}
              data-testid={`radio-browse-teaser-card-${s.id}`}
              className={`${cardCls} shrink-0 w-36 sm:w-40 snap-start rounded-2xl p-3 text-left transition group`}>
              <div className="w-full aspect-square rounded-lg overflow-hidden bg-slate-800/40 relative">
                <SafeImage src={s.favicon} alt={s.name}
                                          fallbackKind="station"
                                          fallbackText={s.name}
                                          className="w-full h-full object-cover" />
                <span className="absolute top-1.5 left-1.5 flex items-center gap-1 bg-red-600/95 text-white text-[9px] font-black px-1.5 py-0.5 rounded-full shadow"
                      data-testid={`radio-browse-live-${s.id}`}>
                  <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" />LIVE
                </span>
                {idx < 3 && !q && (
                  <span className="absolute top-1.5 right-1.5 bg-amber-400 text-slate-900 text-[9px] font-black px-1.5 py-0.5 rounded-full shadow"
                        data-testid={`radio-browse-hot-${s.id}`}>
                    🔥 HOT
                  </span>
                )}
                <span className="absolute inset-0 flex items-center justify-center bg-black/25 opacity-0 group-hover:opacity-100 transition">
                  <Play className="w-8 h-8 text-white fill-white" />
                </span>
              </div>
              <div className={`mt-2 text-sm font-bold truncate ${nameCls}`}>{s.name}</div>
              <div className={`text-[10px] truncate capitalize ${muted}`}>
                {s.country || s.language || "Live"}
              </div>
            </button>
          ))}
        </div>
      )}

      <div className="mt-6 text-center">
        <Link to="/radio/browse"
                    data-testid="radio-browse-teaser-cta"
                    className={`inline-flex items-center gap-2 px-6 py-3 rounded-full text-sm font-black transition ${
                                        light ? "bg-purple-600 text-white hover:bg-purple-500 shadow-lg shadow-purple-500/30"
                                                      : "bg-amber-500 text-slate-900 hover:bg-amber-400 shadow-lg shadow-amber-500/30"}`}>
          Browse all 50,000+ stations
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </section>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Bottom strip — value-prop reminder + rewards teaser
// ═══════════════════════════════════════════════════════════════════
function BottomStrip({ light }) {
  const bg = light
    ? "bg-gradient-to-r from-purple-600 via-fuchsia-600 to-pink-600 text-white"
    : "bg-gradient-to-r from-amber-500/10 via-amber-500/10 to-amber-500/10 border-y border-amber-500/20 text-white";
  return (
    <section className={`${bg} mt-8`}
                        data-testid="radio-bottom-strip">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 py-8 grid grid-cols-2 lg:grid-cols-4 gap-6 text-center">
        {[
          { Icon: Coins,          label: "Listen → Earn",    body: "Points every minute you tune in" },
          { Icon: Ticket,        label: "Win prizes",          body: "Concert, club, and food giveaways" },
          { Icon: Sparkles,  label: "AI-curated",          body: "Bespoke channels that match your vibe" },
          { Icon: PartyPopper, label: "Your city",        body: "Nightlife, bars, and local deals" },
        ].map(({ Icon, label, body }, i) => (
          <div key={i} className="flex flex-col items-center gap-1"
                        data-testid={`radio-bottom-strip-item-${i}`}>
            <Icon className={`w-6 h-6 ${light ? "text-amber-200" : "text-amber-400"}`} />
            <div className="text-sm font-black">{label}</div>
            <div className={`text-xs ${light ? "text-white/85" : "text-slate-300"}`}>{body}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
