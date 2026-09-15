// New Look V2 — full-width premium player bar. Reuses the SAME audio engine
// as MiniPlayer (usePlayerStore + the `bigfm:player:toggle` event handled by
// GlobalAudio), just a larger, richer presentation: big artwork, transport,
// a live progress bar, city, BigPoints and favorites.
import React from "react";
import { Play, Pause } from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { useGeoStore } from "@/store/useGeoStore";
import { useStationFavoritesStore } from "@/store/useStationFavoritesStore";
import { FavoritesFlyout, FavoritesFlyoutToggle } from "@/components/FavoriteControls";
import PointsHeaderWidget from "@/components/PointsHeaderWidget";

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
  let displayTrack = `RadioLife${channelName ? " · " + channelName : ""}`;
  let displayArtist = currentSeg?.track_artist || channelName || "Tap a station to start";
  if (currentRjSegment) {
    activeSource = "AI_RJ";
    displayTrack = "AI RJ";
    displayArtist = currentRjSegment.persona_name || currentRjSegment.voice_id || channelName || "RadioLife";
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

      <PointsHeaderWidget />
      <FavoritesFlyoutToggle open={favOpen} onToggle={() => setFavOpen((v) => !v)} />
    </div>
    <FavoritesFlyout open={favOpen} onClose={() => setFavOpen(false)} />
    </>
  );
}
