// Classic-B audio-first Home (Phase 3 start). Answers "what should I listen
// to / what was I listening to" FIRST: a big Continue-Listening / Start
// block, then a single personalized "For You" rail. Everything else lives
// behind the Listen / Play / Shop / Social tabs.
import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { Play, Pause, Radio as RadioIcon, Sparkles, ChevronRight } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useShellSummary } from "@/shell/useShellData";

function firstName(user) {
  return (user?.first_name || user?.name || "").split(" ")[0] || "there";
}

export default function HomeB() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const summary = useShellSummary();

  const currentSeg = usePlayerStore((s) => s.currentSeg);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const activeChannelName = usePlayerStore((s) => s.activeChannelName);
  const activeChannelThumb = usePlayerStore((s) => s.activeChannelThumb);
  const playing = usePlayerStore((s) => s.playing || s.importedPlaying || s.podcastPlaying);

  const nowTitle = importedStation?.name
    || podcastEpisode?.title
    || currentSeg?.title || currentSeg?.track_title
    || activeChannelName;
  const nowArt = importedStation?.favicon
    || podcastEpisode?.cover_image_url
    || currentSeg?.artwork_url || activeChannelThumb;
  const nowSub = importedStation ? "Live radio"
    : podcastEpisode ? (podcastEpisode.podcast_title || "Podcast")
    : (currentSeg?.artist || currentSeg?.channel_name || "AI radio");
  const hasSession = !!nowTitle;

  const togglePlay = () => {
    try { window.dispatchEvent(new CustomEvent("bigfm:player:toggle")); } catch (_e) { /* noop */ }
  };
  const startListening = () => navigate("/radio");

  const forYou = (summary?.flagships || []).slice(0, 6);

  return (
    <div className="max-w-5xl mx-auto space-y-8" data-testid="home-b">
      <div>
        <div className="text-[11px] font-mono uppercase tracking-widest text-text-secondary">
          {new Date().getHours() < 12 ? "Good morning" : new Date().getHours() < 18 ? "Good afternoon" : "Good evening"}
        </div>
        <h1 className="text-2xl sm:text-3xl font-display font-black tracking-tight mt-0.5">
          Hi {firstName(user)} — ready to listen?
        </h1>
      </div>

      {/* A · Continue Listening / Start */}
      <section data-testid="home-b-continue">
        {hasSession ? (
          <div className="flex items-center gap-4 rounded-token-card border border-white/[0.08] bg-bg-elevated p-4 sm:p-5"
               data-testid="home-b-resume-card">
            <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-token-md overflow-hidden shrink-0 bg-black/30">
              {nowArt
                ? <img src={nowArt} alt="" className="w-full h-full object-cover" />
                : <div className="w-full h-full grid place-items-center"><RadioIcon size={28} className="text-text-secondary" /></div>}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[11px] font-mono uppercase tracking-widest text-accent-electric">
                {playing ? "Now playing" : "Paused"}
              </div>
              <div className="text-lg sm:text-xl font-bold truncate">{nowTitle}</div>
              <div className="text-sm text-text-secondary truncate">{nowSub}</div>
            </div>
            <button type="button" onClick={togglePlay} data-testid="home-b-resume-btn"
              className="w-14 h-14 rounded-full bg-accent-electric text-black grid place-items-center shrink-0 hover:scale-105 transition-transform">
              {playing ? <Pause size={24} /> : <Play size={24} className="translate-x-0.5" />}
            </button>
          </div>
        ) : (
          <div className="rounded-token-card p-6 sm:p-8 text-white relative overflow-hidden"
               data-testid="home-b-start-card"
               style={{ background: "linear-gradient(135deg, #A020F0, #EC4899)" }}>
            <div className="relative z-10">
              <div className="text-[11px] font-mono uppercase tracking-widest opacity-80">Your radio, one tap away</div>
              <h2 className="text-2xl sm:text-3xl font-display font-black mt-1">Start My Radio</h2>
              <p className="text-sm opacity-90 mt-1 max-w-md">
                AI-personalized radio built around what you love. Skip what you don't, earn BigPoints as you listen.
              </p>
              <button type="button" onClick={startListening} data-testid="home-b-start-btn"
                className="mt-4 inline-flex items-center gap-2 h-12 px-6 rounded-full bg-white text-black font-bold hover:scale-[1.03] transition-transform">
                <Play size={20} className="translate-x-0.5" /> Start Listening
              </button>
            </div>
            <Sparkles size={140} className="absolute -right-6 -bottom-6 opacity-15" />
          </div>
        )}
      </section>

      {/* B · For You */}
      <section data-testid="home-b-foryou">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold">For You</h2>
          <Link to="/radio" data-testid="home-b-foryou-seeall"
            className="text-sm font-semibold text-accent-electric hover:underline flex items-center gap-1">
            See all listening <ChevronRight size={15} />
          </Link>
        </div>
        {forYou.length === 0 ? (
          <div className="rounded-token-card border border-white/[0.08] bg-bg-elevated p-6 text-center text-text-secondary text-sm"
               data-testid="home-b-foryou-empty">
            Start listening and your picks will appear here.
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3" data-testid="home-b-foryou-grid">
            {forYou.map((s) => (
              <Link key={s.slug || s.id} to={`/radio/station/${encodeURIComponent(s.id)}?autoplay=1`}
                data-testid={`home-b-foryou-${s.slug || s.id}`}
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
        )}
      </section>
    </div>
  );
}
