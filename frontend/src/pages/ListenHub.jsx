// Listen Hub (Phase 4) — the aggregator page behind the "Listen" tab.
// My Radio one-tap lives at the top; the classic Radio hub is kept as a
// secondary "option 2" link on top; below are the live flagship stations
// plus quick links to Browse / News Radio / Podcasts.
import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  Play, Pause, Radio as RadioIcon, Sparkles, ChevronRight,
  Newspaper, Podcast, Search, Headphones, Film,
} from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useShellSummary, fmtCount } from "@/shell/useShellData";
import PinnedAiRow from "@/components/PinnedAiRow";
import axios from "axios";
import { API } from "@/AuthContext";

export default function ListenHub() {
  const navigate = useNavigate();
  const summary = useShellSummary();
  const [clips, setClips] = useState([]);
  const [news, setNews] = useState([]);

  useEffect(() => {
    let cancel = false;
    axios.get(`${API}/shell/clips`, { params: { limit: 10 }, withCredentials: true })
      .then((r) => { if (!cancel) setClips(r.data?.items || []); }).catch(() => {});
    axios.get(`${API}/news/headlines`, { params: { limit: 6 }, withCredentials: true })
      .then((r) => { if (!cancel) setNews(r.data?.items || []); }).catch(() => {});
    return () => { cancel = true; };
  }, []);

  const currentSeg = usePlayerStore((s) => s.currentSeg);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const activeChannelName = usePlayerStore((s) => s.activeChannelName);
  const playing = usePlayerStore((s) => s.playing || s.importedPlaying || s.podcastPlaying);

  const nowTitle = importedStation?.name
    || podcastEpisode?.title
    || currentSeg?.track_title
    || activeChannelName;
  const hasSession = !!nowTitle;

  const startMyRadio = () => navigate("/radio?ch=my&autoplay=1");
  const resume = () => {
    try { window.dispatchEvent(new CustomEvent("bigfm:player:toggle")); } catch (_e) { /* noop */ }
  };

  const flagships = (summary?.flagships || []).slice(0, 8);
  const count = summary?.station_count ? `${fmtCount(summary.station_count)}+ stations` : "50,000+ stations";

  const quickLinks = [
    { key: "browse",   label: "Browse stations", sub: count,                     icon: Search,    to: "/radio/browse" },
    { key: "news",     label: "News Radio",      sub: "Headlines, read aloud",   icon: Newspaper, to: "/radio/news" },
    { key: "podcasts", label: "Podcasts",        sub: "Shows & episodes",        icon: Podcast,   to: "/podcasts" },
  ];

  return (
    <div className="max-w-5xl mx-auto space-y-7" data-testid="listen-hub">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[11px] font-mono uppercase tracking-widest text-text-secondary">Listen</div>
          <h1 className="text-2xl sm:text-3xl font-display font-black tracking-tight mt-0.5">
            Everything to listen to
          </h1>
        </div>
        {/* Old radio hub kept as "option 2" on top */}
        <Link to="/radio" data-testid="listen-hub-old-hub-link"
          className="shrink-0 inline-flex items-center gap-1.5 h-9 px-3.5 rounded-full text-[13px] font-bold border transition-colors hover:text-accent-electric"
          style={{ borderColor: "var(--line)" }}>
          <RadioIcon size={15} /> Radio hub <ChevronRight size={14} />
        </Link>
      </div>

      {/* My Radio — one tap */}
      <section data-testid="listen-hub-myradio">
        {hasSession ? (
          <div className="flex items-center gap-4 rounded-token-card border border-white/[0.08] bg-bg-elevated p-4 sm:p-5"
               data-testid="listen-hub-resume-card">
            <div className="w-16 h-16 rounded-token-md overflow-hidden shrink-0 bg-black/30 grid place-items-center">
              <Headphones size={26} className="text-accent-electric" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-mono uppercase tracking-widest text-accent-electric">
                {playing ? "Now playing" : "Paused"}
              </div>
              <div className="text-lg font-bold truncate">{nowTitle}</div>
              <div className="text-sm text-text-secondary truncate">My Radio · AI-personalized</div>
            </div>
            <button type="button" onClick={resume} data-testid="listen-hub-resume-btn"
              className="w-14 h-14 rounded-full bg-accent-electric text-black grid place-items-center shrink-0 hover:scale-105 transition-transform">
              {playing ? <Pause size={24} /> : <Play size={24} className="translate-x-0.5" />}
            </button>
          </div>
        ) : (
          <div className="rounded-token-card p-6 sm:p-8 text-white relative overflow-hidden"
               data-testid="listen-hub-start-card"
               style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
            <div className="relative z-10">
              <div className="text-[11px] font-mono uppercase tracking-widest opacity-80">Your radio, one tap away</div>
              <h2 className="text-2xl sm:text-3xl font-display font-black mt-1">Start My Radio</h2>
              <p className="text-sm opacity-90 mt-1 max-w-md">
                AI-personalized radio built around what you love. Like a track to hear more of it — skip what you don't.
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

      {/* Quick links — the other listening surfaces */}
      <section className="grid grid-cols-1 sm:grid-cols-3 gap-3" data-testid="listen-hub-quicklinks">
        {quickLinks.map((q) => (
          <Link key={q.key} to={q.to} data-testid={`listen-hub-quicklink-${q.key}`}
            className="group flex items-center gap-3 rounded-token-card border border-white/[0.08] bg-bg-elevated p-4 hover:border-accent-electric/40 transition-colors">
            <div className="w-11 h-11 rounded-token-md grid place-items-center bg-accent-electric/15 text-accent-electric shrink-0">
              <q.icon size={20} />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[14.5px] font-bold truncate">{q.label}</div>
              <div className="text-xs text-text-secondary truncate">{q.sub}</div>
            </div>
            <ChevronRight size={16} className="text-text-secondary group-hover:text-accent-electric transition-colors" />
          </Link>
        ))}
      </section>

      {/* Live flagship stations */}
      {flagships.length > 0 && (
        <section data-testid="listen-hub-flagships">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-lg font-bold">Live flagship stations</h2>
            <Link to="/radio/browse" data-testid="listen-hub-flagships-seeall"
              className="text-sm font-semibold text-accent-electric hover:underline flex items-center gap-1">
              Browse all <ChevronRight size={15} />
            </Link>
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {flagships.map((s) => (
              <Link key={s.slug || s.id} to={`/radio/station/${encodeURIComponent(s.id)}?autoplay=1`}
                data-testid={`listen-hub-flagship-${s.slug || s.id}`}
                className="group rounded-token-md overflow-hidden border border-white/[0.06] bg-bg-elevated hover:border-accent-electric/40 transition-colors">
                <div className="aspect-square bg-black/30 overflow-hidden relative">
                  {(s.art || s.favicon)
                    ? <img src={s.art || s.favicon} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                    : <div className="w-full h-full grid place-items-center"><RadioIcon size={24} className="text-text-secondary" /></div>}
                  {s.live && <span className="absolute top-1.5 left-1.5 text-[9px] font-black px-1.5 py-0.5 rounded-full bg-accent-live text-white">LIVE</span>}
                  <span className="absolute inset-0 grid place-items-center opacity-0 group-hover:opacity-100 bg-black/40 transition-opacity">
                    <Play size={22} className="text-white translate-x-0.5" />
                  </span>
                </div>
                <div className="p-2">
                  <div className="text-[13px] font-semibold truncate">{s.name}</div>
                </div>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* Clips — RJ moments (moved off Home) */}
      {clips.length > 0 && (
        <section data-testid="listen-hub-clips">
          <div className="flex items-center gap-2 mb-3">
            <Film size={17} className="text-accent-electric" />
            <h2 className="text-lg font-bold">Clips</h2>
            <span className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">RJ moments</span>
          </div>
          <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1" data-testid="listen-hub-clips-row">
            {clips.map((c) => (
              <button type="button" key={c.id}
                onClick={() => (c.business_id ? navigate("/shop") : navigate(`/radio?ch=${encodeURIComponent(c.slug || "")}`))}
                data-testid={`listen-hub-clip-${c.id}`}
                className="group relative shrink-0 w-[132px] h-[216px] rounded-token-md overflow-hidden border border-white/[0.06] bg-bg-elevated text-left">
                {c.image
                  ? <img src={c.image} alt="" className="absolute inset-0 w-full h-full object-cover group-hover:scale-105 transition-transform duration-300" />
                  : <div className="absolute inset-0 grid place-items-center"><RadioIcon size={24} className="text-text-secondary" /></div>}
                <div className="absolute inset-0 bg-gradient-to-t from-black/70 to-transparent" />
                {c.sponsored && (
                  <span className="absolute top-2 left-2 text-[8px] font-black px-1.5 py-0.5 rounded-full bg-accent-gold text-black tracking-widest">SPONSORED</span>
                )}
                <div className="absolute inset-x-0 bottom-0 p-2.5">
                  <div className="text-[13px] font-bold text-white line-clamp-2">{c.title}</div>
                  <div className="text-[11px] text-white/80 truncate">{c.channel}</div>
                </div>
              </button>
            ))}
          </div>
        </section>
      )}

      {/* News — headlines (moved off Home) */}
      {news.length > 0 && (
        <section data-testid="listen-hub-news">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Newspaper size={17} className="text-accent-electric" />
              <h2 className="text-lg font-bold">News</h2>
            </div>
            <Link to="/radio/news" data-testid="listen-hub-news-seeall"
              className="text-sm font-semibold text-accent-electric hover:underline flex items-center gap-1">
              News Radio <ChevronRight size={15} />
            </Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5" data-testid="listen-hub-news-grid">
            {news.slice(0, 6).map((n, idx) => (
              <Link key={n.id || idx} to="/news" data-testid={`listen-hub-news-${idx}`}
                className="flex items-center gap-3 rounded-token-md border border-white/[0.06] bg-bg-elevated p-3 hover:border-accent-electric/40 transition-colors">
                {n.image_url
                  ? <img src={n.image_url} alt="" className="w-14 h-14 rounded-token-sm object-cover shrink-0" />
                  : <div className="w-14 h-14 rounded-token-sm bg-black/30 grid place-items-center shrink-0"><Newspaper size={18} className="text-text-secondary" /></div>}
                <div className="text-[13.5px] font-semibold line-clamp-2">{n.headline_text || n.title || n.headline}</div>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
