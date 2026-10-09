// New Look V2 — full-width premium player bar. Reuses the SAME audio engine
// as MiniPlayer (usePlayerStore + the `bigfm:player:toggle` event handled by
// GlobalAudio), just a larger, richer presentation: big artwork, transport,
// a live progress bar, city, BigPoints and favorites.
import React from "react";
import { Play, Pause, Users, Moon } from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useGeoStore } from "@/store/useGeoStore";
import { useStationFavoritesStore } from "@/store/useStationFavoritesStore";
import { useSleepTimer } from "@/store/useSleepTimer";
import { toast } from "sonner";
import { FavoritesFlyout, FavoritesFlyoutToggle } from "@/components/FavoriteControls";
import PointsHeaderWidget from "@/components/PointsHeaderWidget";

// Sleep timer control — "stop after N min" so a station winds down on its own.
function SleepTimerButton() {
  const endsAt = useSleepTimer((s) => s.endsAt);
  const start = useSleepTimer((s) => s.start);
  const cancel = useSleepTimer((s) => s.cancel);
  const [open, setOpen] = React.useState(false);
  const [now, setNow] = React.useState(Date.now());

  React.useEffect(() => {
    if (!endsAt) return;
    const i = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(i);
  }, [endsAt]);

  const active = !!endsAt;
  const remainMin = active ? Math.max(0, Math.ceil((endsAt - now) / 60000)) : 0;

  return (
    <div className="relative flex-shrink-0">
      <button type="button" onClick={() => setOpen((v) => !v)}
        data-testid="sleep-timer-toggle" aria-label="Sleep timer"
        title={active ? `Sleep timer — ${remainMin} min left` : "Sleep timer"}
        className="relative grid place-items-center w-9 h-9 rounded-full transition-transform hover:scale-105"
        style={{ background: active ? "rgba(34,211,238,0.22)" : "rgba(255,255,255,0.05)",
                        color: active ? "#67e8f9" : "#9aa6c8",
                        border: "1px solid rgba(255,255,255,0.10)" }}>
        <Moon size={16} />
        {active && (
          <span data-testid="sleep-timer-remaining"
            className="absolute -top-1 -right-1 min-w-[16px] h-4 px-1 rounded-full text-[9px] font-black grid place-items-center text-slate-950"
            style={{ background: "#67e8f9" }}>{remainMin}</span>
        )}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div data-testid="sleep-timer-menu"
            className="absolute bottom-full right-0 mb-2 z-50 w-44 rounded-2xl border border-white/10 bg-slate-900 shadow-2xl p-1.5">
            <div className="px-2.5 py-1.5 text-[10px] font-mono uppercase tracking-widest text-white/40">
              {active ? `Stops in ${remainMin} min` : "Sleep timer"}
            </div>
            {[15, 30, 45, 60].map((m) => (
              <button key={m} type="button" data-testid={`sleep-timer-${m}`}
                onClick={() => { start(m); setOpen(false); toast(`Sleep timer set — ${m} min 🌙`); }}
                className="w-full text-left px-2.5 h-9 rounded-xl text-sm font-bold text-white/85 hover:bg-white/[0.06] transition-colors">
                {m} minutes
              </button>
            ))}
            {active && (
              <button type="button" data-testid="sleep-timer-off"
                onClick={() => { cancel(); setOpen(false); toast("Sleep timer off"); }}
                className="w-full text-left px-2.5 h-9 rounded-xl text-sm font-bold text-rose-300 hover:bg-white/[0.06] transition-colors">
                Turn off
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}

export default function PlayerBarV2() {
  const currentSeg    = usePlayerStore((s) => s.currentSeg);
  const channelName   = usePlayerStore((s) => s.activeChannelName);
  const channelThumb  = usePlayerStore((s) => s.activeChannelThumb);
  const activeSlug    = usePlayerStore((s) => s.activeChannel);
  const sessionId     = usePlayerStore((s) => s.sessionId);
  const playing       = usePlayerStore((s) => s.playing);
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode  = usePlayerStore((s) => s.podcastEpisode);
  const currentRjSegment = usePlayerStore((s) => s.currentRjSegment);
  const currentTime   = usePlayerStore((s) => s.currentTime);
  const duration      = usePlayerStore((s) => s.duration);
  const footerCity    = useGeoStore((s) => s.city);

  const favBootstrap = useStationFavoritesStore((s) => s.bootstrap);
  const favLoaded    = useStationFavoritesStore((s) => s.loaded);
  const [favOpen, setFavOpen] = React.useState(false);
  React.useEffect(() => { if (!favLoaded) favBootstrap(); }, [favLoaded, favBootstrap]);

  let activeSource = null;
  let displayTrack = `FUUSIC${channelName ? " · " + channelName : ""}`;
  let displayArtist = currentSeg?.track_artist || channelName || "Tap a station to start";
  if (currentRjSegment) {
    activeSource = "AI_RJ";
    displayTrack = "AI RJ";
    displayArtist = currentRjSegment.persona_name || currentRjSegment.voice_id || channelName || "FUUSIC";
  } else if (podcastEpisode) {
    activeSource = "PODCAST";
    displayTrack = podcastEpisode.title || "Podcast episode";
    displayArtist = podcastEpisode.podcast_title || "Podcast";
  } else if (importedStation) {
    activeSource = "LIVE";
    displayTrack = importedStation.name || "Live Radio";
    displayArtist = [importedStation.country, importedStation.language].filter(Boolean).join(" · ") || "Live broadcast";
  } else if (sessionId || activeSlug || currentSeg) {
    activeSource = "AI";
    displayTrack = currentSeg?.track_title || displayTrack;
  }

  const hasContent = !!(importedStation || sessionId || activeSlug || podcastEpisode);

  const onToggle = async () => {
    if (hasContent) {
      window.dispatchEvent(new CustomEvent("bigfm:player:toggle"));
      return;
    }
    try {
      const backend = process.env.REACT_APP_BACKEND_URL || "";
      const r = await fetch(`${backend}/api/stations/flagship?limit=1`, { credentials: "include" });
      if (r.ok) {
        const d = await r.json();
        const top = (d.items || [])[0];
        if (top?.id) {
          window.location.href = `/radio/station/${encodeURIComponent(top.id)}?autoplay=1`;
          return;
        }
      }
    } catch (_e) { /* fall through */ }
    window.location.href = "/radio/browse";
  };

  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

  const startListenTogether = async () => {
    if (!hasContent) { window.location.href = "/social?action=listen"; return; }
    let content_type = "live"; let content = {};
    if (podcastEpisode) {
      content_type = "podcast";
      content = { id: podcastEpisode.episode_id, name: podcastEpisode.title, favicon: podcastEpisode.cover_image_url, podcast_id: podcastEpisode.podcast_id };
    } else if (importedStation) {
      content = { ...importedStation };
    } else {
      content = { id: activeSlug || sessionId, name: channelName || displayTrack, favicon: channelThumb };
    }
    try {
      const r = await fetch(`${BACKEND_URL}/api/social/rooms`, {
        method: "POST", credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ visibility: "public", content_type, content,
          playback: content_type === "podcast" ? { position_sec: currentTime || 0, is_playing: true } : undefined }),
      });
      const d = await r.json();
      window.location.href = d.room_id ? `/social/room/${d.room_id}` : "/social?action=listen";
    } catch (_) { window.location.href = "/social?action=listen"; }
  };

  const thumb = podcastEpisode?.cover_image_url || importedStation?.favicon || channelThumb;
  const artworkBg = thumb
    ? (thumb.startsWith("http") ? `url(${thumb}) center/cover` : `url(${BACKEND_URL}${thumb}) center/cover`)
    : "linear-gradient(135deg,#a855f7 0%,#ec4899 100%)";

  const earning = playing && ["AI", "LIVE", "COMMUNITY"].includes(activeSource);
  const subtitle = earning
    ? `${footerCity ? footerCity + " · " : ""}earning +1/min`
    : displayArtist;

  const pct = duration > 0 ? Math.min(100, (currentTime / duration) * 100) : 0;
  const isLive = activeSource === "LIVE" || (activeSource === "AI" && !duration);

  return (
    <>
    <div
      data-testid="nlv2-player-bar"
      data-playing={playing ? "true" : "false"}
      data-source={activeSource || "none"}
      className="nlv2-glass-strong rounded-2xl border border-white/10 shadow-2xl px-3 sm:px-4 py-2.5 flex items-center gap-3 sm:gap-4">
      {/* Big artwork — click toggles play/pause */}
      <button
        type="button"
        onClick={() => hasContent && window.dispatchEvent(new CustomEvent("bigfm:player:toggle"))}
        disabled={!hasContent}
        data-testid="nlv2-player-artwork"
        aria-label={hasContent ? (playing ? "Pause" : "Play") : "Player artwork"}
        className="w-12 h-12 sm:w-14 sm:h-14 rounded-xl flex-shrink-0 border-0 p-0 cursor-pointer disabled:cursor-default relative overflow-hidden focus:outline-none focus:ring-2 focus:ring-[#c084fc]/60"
        style={{ background: artworkBg }}>
        {playing && (
          <span className="absolute inset-0 grid place-items-center bg-black/25">
            <span className="flex items-end gap-0.5 h-4">
              <span className="w-0.5 bg-white nlv2-eq nlv2-eq1" />
              <span className="w-0.5 bg-white nlv2-eq nlv2-eq2" />
              <span className="w-0.5 bg-white nlv2-eq nlv2-eq3" />
            </span>
          </span>
        )}
      </button>

      {/* Title · subtitle · progress */}
      <div className="min-w-0 flex-1 sm:flex-none sm:w-[220px] xl:w-[280px]">
        <div className="flex items-center gap-2">
          {activeSource && (
            <span className="hidden sm:inline text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded"
              style={{ background: "rgba(192,132,252,0.18)", color: "#d8b4fe" }}>
              {activeSource === "AI_RJ" ? "AI RJ" : activeSource}
            </span>
          )}
          <div className="font-bold text-sm truncate text-white" data-testid="nlv2-player-title">{displayTrack}</div>
        </div>
        <div className="text-[11px] truncate mt-0.5" style={{ color: "#9aa6c8" }} data-testid="nlv2-player-subtitle">{subtitle}</div>
        {hasContent && (
          duration > 0 ? (
            <div className="mt-1.5 h-1 rounded-full overflow-hidden hidden sm:block" style={{ background: "rgba(255,255,255,0.10)" }}>
              <div className="h-full rounded-full" data-testid="nlv2-player-progress"
                style={{ width: `${pct}%`, background: "linear-gradient(90deg,#a855f7,#ec4899)" }} />
            </div>
          ) : isLive ? (
            <div className="mt-1 text-[10px] font-mono uppercase tracking-widest hidden sm:flex items-center gap-1" style={{ color: "#f472b6" }}>
              <span className="w-1.5 h-1.5 rounded-full bg-[#f472b6] animate-pulse" /> Live
            </div>
          ) : null
        )}
      </div>

      {/* Transport */}
      <button
        type="button"
        onClick={onToggle}
        data-testid="nlv2-player-play"
        aria-label={playing ? "Pause" : "Play"}
        aria-pressed={playing}
        className="w-11 h-11 sm:w-12 sm:h-12 rounded-full grid place-items-center flex-shrink-0 text-black transition-transform duration-150 hover:scale-105"
        style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)", color: "#fff" }}>
        {playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" />}
      </button>

      <div className="flex-1 hidden sm:block" />

      {/* Right cluster */}
      {footerCity ? (
        <span
          data-testid="nlv2-player-city"
          className="hidden lg:inline-flex items-center gap-1.5 px-2.5 h-7 rounded-full text-[10px] font-mono uppercase tracking-widest"
          style={{ background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.10)", color: "#9aa6c8" }}>
          <span className="w-1 h-1 rounded-full bg-[#c084fc]" />{footerCity}
        </span>
      ) : null}

      {hasContent && (
        <button type="button" onClick={startListenTogether} data-testid="player-invite-listen"
                title="Invite to Listen Together"
                className="hidden sm:grid place-items-center w-9 h-9 rounded-full flex-shrink-0 transition-transform hover:scale-105"
                style={{ background: "rgba(168,85,247,0.18)", color: "#d8b4fe" }}>
          <Users size={16} />
        </button>
      )}
      <PointsHeaderWidget />
      <SleepTimerButton />
      <FavoritesFlyoutToggle open={favOpen} onToggle={() => setFavOpen((v) => !v)} />
    </div>
    <FavoritesFlyout open={favOpen} onClose={() => setFavOpen(false)} />
    </>
  );
}
