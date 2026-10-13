// Listen World Hub — the aggregator behind the "Listen" tab. Rebuilt for the
// unified FUUSIC Light/Dark theme (brand purple→pink): search, quick-access
// surfaces, My Radio one-tap, Explore by Country (flags), Browse by Genre and
// themed station rails. Copy stays generic (real catalog varies — no counts).
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Play, Pause, Radio as RadioIcon, Sparkles, ChevronRight,
  Podcast, Search, Headphones, Heart, Users, Globe,
} from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useShellSummary } from "@/shell/useShellData";
import PinnedAiRow from "@/components/PinnedAiRow";
import axios from "axios";
import { API } from "@/AuthContext";

const COUNTRY_NAMES = {
  US: "USA", IN: "India", AE: "UAE", GB: "UK", CA: "Canada", AU: "Australia",
  FR: "France", DE: "Germany", IT: "Italy", ES: "Spain", BR: "Brazil",
  MX: "Mexico", PK: "Pakistan", SA: "Saudi Arabia", NG: "Nigeria", ZA: "South Africa",
  JP: "Japan", KR: "Korea", CN: "China", RU: "Russia", NL: "Netherlands",
  SE: "Sweden", TR: "Turkey", EG: "Egypt", ID: "Indonesia", PH: "Philippines",
};
const flagOf = (cc) => {
  if (!cc || cc.length !== 2) return "🌐";
  try {
    return String.fromCodePoint(...[...cc.toUpperCase()].map((c) => 127397 + c.charCodeAt(0)));
  } catch (_e) { return "🌐"; }
};

function StationCard({ s }) {
  const art = s.art || s.favicon || s.logo || s.image;
  return (
    <Link to={`/radio/station/${encodeURIComponent(s.id)}?autoplay=1`}
      data-testid={`listen-station-${s.slug || s.id}`}
      className="fz-card group rounded-token-md overflow-hidden transition-transform hover:-translate-y-1 block">
      <div className="aspect-square overflow-hidden relative" style={{ background: "var(--surface-2)" }}>
        {art
          ? <img src={art} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
          : <div className="w-full h-full grid place-items-center"><RadioIcon size={24} className="fz-muted" /></div>}
        {s.live && <span className="absolute top-1.5 left-1.5 text-[9px] font-black px-1.5 py-0.5 rounded-full text-white" style={{ background: "var(--live)" }}>LIVE</span>}
        <span className="absolute inset-0 grid place-items-center opacity-0 group-hover:opacity-100 bg-black/40 transition-opacity">
          <Play size={22} className="text-white translate-x-0.5" />
        </span>
      </div>
      <div className="p-2">
        <div className="text-[13px] font-semibold truncate fz-text">{s.name}</div>
        {(s.country || s.language) && (
          <div className="text-[11px] truncate fz-muted">{[s.language, s.country].filter(Boolean).join(" · ")}</div>
        )}
      </div>
    </Link>
  );
}

export default function ListenHub() {
  const navigate = useNavigate();
  const summary = useShellSummary();
  const [q, setQ] = useState("");
  const [discover, setDiscover] = useState(null);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/radio/discover`, { withCredentials: true })
      .then((r) => { if (!cancel) setDiscover(r.data || null); }).catch(() => {});
    return () => { cancel = true; };
  }, []);

  const currentSeg = usePlayerStore((s) => s.currentSeg);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const activeChannelName = usePlayerStore((s) => s.activeChannelName);
  const playing = usePlayerStore((s) => s.playing || s.importedPlaying || s.podcastPlaying);

  const nowTitle = importedStation?.name || podcastEpisode?.title || currentSeg?.track_title || activeChannelName;
  const hasSession = !!nowTitle;

  const startMyRadio = () => navigate("/radio?ch=my&autoplay=1");
  const resume = () => { try { window.dispatchEvent(new CustomEvent("bigfm:player:toggle")); } catch (_e) { /* noop */ } };
  const runSearch = (e) => { e.preventDefault(); navigate(`/radio/browse${q.trim() ? `?q=${encodeURIComponent(q.trim())}` : ""}`); };

  const railsById = (discover?.rails || []).reduce((acc, r) => { acc[r.id] = r; return acc; }, {});
  const countries = (railsById.countries?.facet_chips || []).slice(0, 12);
  const genres = (railsById.genres?.facet_chips || []).slice(0, 10);
  const trending = (railsById.trending?.stations || railsById.local?.stations || []).slice(0, 8);
  const recommended = (railsById.for_you?.stations || railsById.ai_curated?.stations || []).slice(0, 8);
  const flagships = (summary?.flagships || []).slice(0, 8);

  const QUICK = [
    { key: "live", label: "Live Radio", icon: RadioIcon, to: "/radio/browse" },
    { key: "ai", label: "AI Radio", icon: Sparkles, to: "/radio?ch=my&autoplay=1" },
    { key: "podcasts", label: "Podcasts", icon: Podcast, to: "/podcasts" },
    { key: "favorites", label: "Favorites", icon: Heart, to: "/me/saved" },
    { key: "together", label: "Together", icon: Users, to: "/social" },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-7 fz-text" data-testid="listen-hub">
      <div>
        <div className="text-[11px] font-mono uppercase tracking-widest fz-brand">Listen</div>
        <h1 className="text-2xl sm:text-3xl font-display font-black tracking-tight mt-0.5">Radio from around the world</h1>
      </div>

      {/* Search */}
      <form onSubmit={runSearch} className="fz-field flex items-center gap-2 rounded-full px-4 py-3" data-testid="listen-search-form">
        <Search size={18} className="fz-muted" />
        <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="listen-search-input"
          placeholder="Search radio stations, genres, countries…"
          className="flex-1 outline-none text-sm bg-transparent border-0 p-0 fz-text" style={{ background: "transparent" }} />
      </form>

      {/* Quick access */}
      <section className="grid grid-cols-5 gap-2 sm:gap-3" data-testid="listen-quick-access">
        {QUICK.map((qa) => (
          <Link key={qa.key} to={qa.to} data-testid={`listen-quick-${qa.key}`}
            className="fz-card flex flex-col items-center gap-2 rounded-token-md p-3 transition-transform hover:-translate-y-1">
            <span className="w-11 h-11 rounded-full grid place-items-center fz-brand-soft"><qa.icon size={20} style={{ color: "var(--brand-solid)" }} /></span>
            <span className="text-[11px] sm:text-xs font-bold text-center fz-sub">{qa.label}</span>
          </Link>
        ))}
      </section>

      {/* My Radio — one tap */}
      <section data-testid="listen-hub-myradio">
        {hasSession ? (
          <div className="fz-card flex items-center gap-4 rounded-token-card p-4 sm:p-5" data-testid="listen-hub-resume-card">
            <div className="w-16 h-16 rounded-token-md overflow-hidden shrink-0 grid place-items-center" style={{ background: "var(--surface-2)" }}>
              <Headphones size={26} style={{ color: "var(--brand-solid)" }} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-mono uppercase tracking-widest fz-brand">{playing ? "Now playing" : "Paused"}</div>
              <div className="text-lg font-bold truncate">{nowTitle}</div>
              <div className="text-sm fz-muted truncate">My Radio · AI-personalized</div>
            </div>
            <button type="button" onClick={resume} data-testid="listen-hub-resume-btn"
              className="fz-grad w-14 h-14 rounded-full grid place-items-center shrink-0 hover:scale-105 transition-transform">
              {playing ? <Pause size={24} /> : <Play size={24} className="translate-x-0.5" />}
            </button>
          </div>
        ) : (
          <div className="fz-grad rounded-token-card p-6 sm:p-8 relative overflow-hidden" data-testid="listen-hub-start-card">
            <div className="relative z-10">
              <div className="text-[11px] font-mono uppercase tracking-widest opacity-80">Your radio, one tap away</div>
              <h2 className="text-2xl sm:text-3xl font-display font-black mt-1">Start My Radio</h2>
              <p className="text-sm opacity-90 mt-1 max-w-md">
                AI-personalized radio built around what you love. Like a track to hear more of it — skip what you don&apos;t.
              </p>
              <button type="button" onClick={startMyRadio} data-testid="listen-hub-myradio-btn"
                className="mt-4 inline-flex items-center gap-2 h-12 px-6 rounded-full bg-white text-black font-bold hover:scale-[1.03] transition-transform">
                <Play size={20} className="translate-x-0.5" /> Start My Radio
              </button>
            </div>
            <Sparkles size={140} className="absolute -right-6 -bottom-6 opacity-15" />
          </div>
        )}
      </section>

      <PinnedAiRow testId="listen-pinned-ai-row" />

      {/* Explore by Country */}
      {countries.length > 0 && (
        <section data-testid="listen-countries">
          <div className="flex items-center gap-2 mb-3">
            <Globe size={17} style={{ color: "var(--brand-solid)" }} />
            <h2 className="text-lg font-bold">Explore by Country</h2>
          </div>
          <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1">
            {countries.map((c) => (
              <button type="button" key={c.slug} onClick={() => navigate(`/radio/browse?country=${encodeURIComponent(c.slug)}`)}
                data-testid={`listen-country-${c.slug}`}
                className="fz-card shrink-0 w-24 rounded-token-md p-3 flex flex-col items-center gap-1.5 transition-transform hover:-translate-y-1">
                <span className="text-3xl leading-none">{flagOf(c.slug)}</span>
                <span className="text-[12px] font-bold text-center truncate w-full fz-text">{COUNTRY_NAMES[c.slug] || c.label}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Browse by Genre */}
      {genres.length > 0 && (
        <section data-testid="listen-genres">
          <h2 className="text-lg font-bold mb-3">Browse by Genre</h2>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            {genres.map((g, i) => (
              <button type="button" key={g.slug} onClick={() => navigate(`/radio/browse?category=${encodeURIComponent(g.slug)}`)}
                data-testid={`listen-genre-${g.slug}`}
                className="relative h-20 rounded-token-md overflow-hidden text-left p-3 flex items-end transition-transform hover:-translate-y-1"
                style={{ background: `linear-gradient(135deg, var(--brand-grad-start), var(--brand-grad-end))`, filter: i % 2 ? "hue-rotate(18deg)" : "none" }}>
              <span className="text-white font-black text-sm capitalize drop-shadow">{g.label}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* Live stations */}
      {flagships.length > 0 && (
        <section data-testid="listen-hub-flagships">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold">Live stations</h2>
            <Link to="/radio/browse" data-testid="listen-hub-flagships-seeall"
              className="text-sm font-semibold fz-brand hover:underline flex items-center gap-1">
              Browse all <ChevronRight size={15} />
            </Link>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {flagships.map((s) => <StationCard key={s.slug || s.id} s={s} />)}
          </div>
        </section>
      )}

      {/* Trending now */}
      {trending.length > 0 && (
        <section data-testid="listen-trending">
          <h2 className="text-lg font-bold mb-3">Trending Now</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {trending.map((s) => <StationCard key={`tr-${s.slug || s.id}`} s={s} />)}
          </div>
        </section>
      )}

      {/* Recommended for You */}
      {recommended.length > 0 && (
        <section data-testid="listen-recommended">
          <h2 className="text-lg font-bold mb-3">Recommended for You</h2>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {recommended.map((s) => <StationCard key={`rc-${s.slug || s.id}`} s={s} />)}
          </div>
        </section>
      )}
    </div>
  );
}
