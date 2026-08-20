// Phase 15a — design-system primitives. All consume the new tokens.
import React from "react";

// ─── Card ──────────────────────────────────────────────────────────────
export const Card = React.forwardRef(function Card(
  { as: Tag = "div", className = "", hoverable = false, children,
    "data-testid": tid, ...rest }, ref) {
  return (
    <Tag
      ref={ref}
      data-testid={tid}
      className={[
        "bg-bg-elevated text-text-primary rounded-token-card",
        "border border-white/[0.06] shadow-card font-sans",
        hoverable
          ? "transition-all duration-150 ease-out150 hover:-translate-y-0.5 hover:shadow-card-hover cursor-pointer"
          : "",
        className,
      ].join(" ")}
      {...rest}
    >{children}</Tag>
  );
});

// ─── Button ────────────────────────────────────────────────────────────
const VARIANTS = {
  primary: "bg-accent-electric text-black hover:brightness-110",
  magenta: "bg-accent-magenta text-white hover:brightness-110",
  gold:    "bg-accent-gold text-black hover:brightness-110",
  outline: "bg-transparent text-accent-electric border border-accent-electric hover:bg-accent-electric/10",
  ghost:   "bg-transparent text-white/65 hover:text-white hover:bg-white/5",
  danger:  "bg-accent-live text-white hover:brightness-110",
};

export function Button({ variant = "primary", size = "md", className = "",
                                  children, "data-testid": tid, ...rest }) {
  const v = VARIANTS[variant] || VARIANTS.primary;
  const sz = size === "lg" ? "h-12 px-6 text-base"
                : size === "sm" ? "h-8 px-3 text-xs"
                : "h-11 px-5 text-sm";
  return (
    <button
      data-testid={tid}
      className={[
        "inline-flex items-center justify-center gap-2 rounded-full",
        "font-sans font-semibold tracking-tight",
        "transition-all duration-150 ease-out150",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-accent-electric/60",
        v, sz, className,
      ].join(" ")}
      {...rest}
    >{children}</button>
  );
}

// ─── Chip ──────────────────────────────────────────────────────────────
export function Chip({ active = false, tone = "neutral", className = "",
                                children, "data-testid": tid, ...rest }) {
  const tones = {
    neutral:   active
        ? "bg-white/10 text-white border-white/15"
        : "bg-transparent text-white/65 border-white/10 hover:text-white",
    live:      "bg-accent-live/15 text-accent-live border-accent-live/30",
    electric:  "bg-accent-electric/15 text-accent-electric border-accent-electric/30",
    gold:      "bg-accent-gold/15 text-accent-gold border-accent-gold/30",
  };
  return (
    <button
      type="button"
      data-testid={tid}
      className={[
        "inline-flex items-center gap-1.5 rounded-full",
        "px-3 h-7 text-xs font-medium border",
        "transition-colors duration-150 ease-out150",
        tones[tone] || tones.neutral, className,
      ].join(" ")}
      {...rest}
    >{children}</button>
  );
}

// ─── LiveDot ───────────────────────────────────────────────────────────
export function LiveDot({ className = "" }) {
  return (
    <span
      data-testid="live-dot"
      className={["inline-block w-2 h-2 rounded-full bg-accent-live",
                        "animate-live-dot align-middle", className].join(" ")}
    />
  );
}

// ─── StationTile ───────────────────────────────────────────────────────
// Phase Π+3.1 (2026-07-24) — artwork is now rendered as an ACTUAL
// `<img>` element (with a CSS-background fallback for the null case),
// so headless test runners can measure `naturalWidth > 0` and confirm
// the browser painted the asset.  Prior version used a CSS
// `background: url(…)` which paints correctly but produces no
// `HTMLImageElement` for the DOM inspector to find.
export function StationTile({ name, dj, artwork, live = false,
                                          onPlay, className = "" }) {
  return (
    <Card hoverable className={["group p-3 flex flex-col gap-3 w-full",
                                          className].join(" ")}
            data-testid={`station-tile-${name}`}>
      <div className="relative aspect-square rounded-token-md overflow-hidden"
        style={{ background: "linear-gradient(135deg, var(--accent-electric) 0%, var(--accent-magenta) 100%)" }}>
        {artwork ? (
          <img
            src={artwork}
            alt={name}
            loading="lazy"
            onError={(e) => {
              // Hide the broken image so the gradient fallback shows through.
              const img = e.currentTarget;
              img.style.display = "none";
              const bg = img.parentElement?.querySelector(
                "[data-testid=station-tile-fallback]");
              if (bg) bg.style.display = "block";
            }}
            className="absolute inset-0 w-full h-full object-cover"
            data-testid={`station-tile-img-${name}`} />
        ) : null}
        <div
          data-testid="station-tile-fallback"
          className="absolute inset-0"
          style={{
            display: artwork ? "none" : "block",
            background: "linear-gradient(135deg, var(--accent-electric) 0%, "
                                    + "var(--accent-magenta) 100%)",
          }}
        />
        <button
          type="button"
          onClick={onPlay}
          aria-label={`Play ${name}`}
          className="absolute inset-0 flex items-center justify-center
                            opacity-0 group-hover:opacity-100 transition-opacity
                            duration-150 ease-out150 bg-black/40"
          data-testid={`station-play-${name}`}
        >
          <span className="w-12 h-12 rounded-full bg-accent-electric
                                    text-black grid place-items-center text-xl">▶</span>
        </button>
        {live && (
          <span className="absolute top-2 left-2 inline-flex items-center
                                    gap-1.5 px-2 py-0.5 rounded-full bg-black/70
                                    text-[10px] font-semibold text-accent-live">
            <LiveDot /> LIVE
          </span>
        )}
      </div>
      <div className="px-1">
        <div className="font-display font-bold tracking-display-tight text-sm
                              truncate">{name}</div>
        {dj && <div className="text-xs text-text-secondary truncate">{dj}</div>}
      </div>
    </Card>
  );
}

// ─── GameTile ──────────────────────────────────────────────────────────
export function GameTile({ name, prize, status = "live",
                                      onJoin, className = "" }) {
  return (
    <Card hoverable className={["p-4 flex flex-col gap-3", className].join(" ")}
            data-testid={`game-tile-${name}`}>
      <div className="flex items-center gap-2">
        {status === "live" && <LiveDot />}
        <span className="text-[10px] font-mono uppercase tracking-widest
                                text-text-secondary">{status}</span>
      </div>
      <div className="font-display font-bold tracking-display-tight text-lg">
        {name}
      </div>
      <div className="text-accent-gold font-mono text-xs">
        Prize · {prize}
      </div>
      <Button variant="magenta" size="sm" onClick={onJoin}
                  data-testid={`game-join-${name}`}>
        Join now
      </Button>
    </Card>
  );
}

// ─── WalletItemCard ────────────────────────────────────────────────────
export function WalletItemCard({ title, expires, badge, className = "" }) {
  return (
    <Card className={["p-4 flex items-center gap-4", className].join(" ")}
            data-testid={`wallet-item-${title}`}>
      <div className="w-12 h-12 rounded-token-md bg-accent-gold/20 grid
                            place-items-center text-accent-gold">★</div>
      <div className="flex-1">
        <div className="font-sans font-semibold text-sm">{title}</div>
        <div className="text-xs text-text-secondary">{expires}</div>
      </div>
      {badge && (
        <span className="text-[10px] font-mono uppercase text-accent-gold">
          {badge}
        </span>
      )}
    </Card>
  );
}

// ─── MiniPlayer — wired to usePlayerStore (Phase 15d.3) ────────────────
// Reads the current track + playing flag from the global player store and
// dispatches `bigfm:player:toggle` (handled by GlobalAudio) on click.  This
// works from EVERY route because GlobalAudio is mounted at AppShell root.
import { usePlayerStore } from "@/store/usePlayerStore";
import { BottomBarChannelStrip } from "@/components/Phase18Home";
import { fetchAutoplaySuggestion } from "@/store/useFavoritesStore";
// P0 mixed-content fix — rewrite http:// stream URLs through the proxy
// so the persistent-player cold-start flagship autoplay never trips
// the browser's mixed-content block.
import { toPlayableStreamUrl } from "@/utils/streamUrl";
// Phase B Bug B2 follow-up — surface the resolved city in the persistent
// player so the authed-home tester can verify header (CityChip) ↔ footer
// (this label) parity without leaving the dashboard.  Both read from the
// same useGeoStore, so they are guaranteed to agree by construction.
import { useGeoStore } from "@/store/useGeoStore";
// Phase 42-D3 — favorites flyout pinned to the bottom bar.
import { useStationFavoritesStore } from "@/store/useStationFavoritesStore";
import { FavoritesFlyout, FavoritesFlyoutToggle }
                                  from "@/components/FavoriteControls";
// Phase F-1 — unified points pill + drawer.
import PointsHeaderWidget from "@/components/PointsHeaderWidget";
// Phase 42-E1.1 — persistent banner ad in the bottom bar (free users only).
import PersistentBannerSlot from "@/components/PersistentBannerSlot";
// Phase 42-E2.2 — Universal share button (now-playing context).
import ShareButton from "@/components/ShareButton";
// Phase P0-BAR — favorites + region-flagship rail inside the bottom bar.
import BottomBarStationRail from "@/components/BottomBarStationRail";
// Phase AD.11 — bottom_bar banner zone.
import BannerZoneSlot from "@/components/BannerZoneSlot";
// Phase D — AI RJ Persona chip in the MiniPlayer.
import axios from "axios";
import { API } from "@/AuthContext";

// Fetches the highest-priority ACTIVE persona for the currently-playing
// station and returns null when no assignment exists.  Cached per
// stationId across mounts within the same session.
const _personaCache = new Map();       // stationId → persona | null
function useRjPersonaForStation(stationId) {
  const [persona, setPersona] = React.useState(
    stationId ? _personaCache.get(stationId) ?? null : null);
  React.useEffect(() => {
    if (!stationId) { setPersona(null); return; }
    if (_personaCache.has(stationId)) {
      setPersona(_personaCache.get(stationId));
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await axios.get(
          `${API}/rj/stations/${encodeURIComponent(stationId)}/personas`);
        const first = (r.data?.items || [])[0] || null;
        _personaCache.set(stationId, first);
        if (!cancelled) setPersona(first);
      } catch (_e) {
        _personaCache.set(stationId, null);
        if (!cancelled) setPersona(null);
      }
    })();
    return () => { cancelled = true; };
  }, [stationId]);
  return persona;
}

export function MiniPlayer({ className = "" }) {
  const currentSeg   = usePlayerStore((s) => s.currentSeg);
  const channelName  = usePlayerStore((s) => s.activeChannelName);
  const channelThumb = usePlayerStore((s) => s.activeChannelThumb);
  const activeSlug   = usePlayerStore((s) => s.activeChannel);
  const sessionId    = usePlayerStore((s) => s.sessionId);
  const playing      = usePlayerStore((s) => s.playing);
  // Phase 42-A2 — imported live-radio station context.
  const importedStation = usePlayerStore((s) => s.importedStation);
  // Phase B — podcast episode currently playing (nullable).
  const podcastEpisode  = usePlayerStore((s) => s.podcastEpisode);
  // P0 addendum — cold-start flagship autoplay reads this setter so
  // tapping the play button with no active station kicks off the
  // top region-matched flagship instead of being a silent no-op.
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  // Phase B — geo city for the footer-city label (read from the SAME
  // store that the header CityChip uses → guaranteed parity).
  const footerCity   = useGeoStore((s) => s.city);
  // Phase 42-D3 — favorites flyout state.  Bootstrap once silently;
  // if the user is anonymous the call 401s and we'll just sit empty.
  const favBootstrap = useStationFavoritesStore((s) => s.bootstrap);
  const favLoaded    = useStationFavoritesStore((s) => s.loaded);
  const [favOpen, setFavOpen] = React.useState(false);
  React.useEffect(() => {
    if (!favLoaded) favBootstrap();
  }, [favLoaded, favBootstrap]);

  // Phase 42-B-redux — derive the active source for the badge + the
  // primary text rows.
  // Phase H'.5a — when an AI-RJ inter-song segment is mid-playback,
  // override the source badge to "AI RJ" so listeners know who's
  // speaking.  Segment is content (not an ad), so it cannot be skipped.
  const currentRjSegment = usePlayerStore((s) => s.currentRjSegment);

  // Phase D — resolve the station's assigned host persona (if any).
  // Only meaningful for LIVE/COMMUNITY/AI-station playback; podcasts +
  // AI RJ inter-song don't show the chip.
  const _stationIdForPersona = importedStation?.id
                                                          || importedStation?.slug
                                                          || activeSlug
                                                          || null;
  const rjPersona = useRjPersonaForStation(
    (currentRjSegment || podcastEpisode) ? null : _stationIdForPersona);

  let activeSource = null;        // "AI" | "LIVE" | "COMMUNITY" | "AI_RJ" | "PODCAST" | null
  let displayTrack = `RadioLife${channelName ? " · " + channelName : ""}`;
  let displayArtist = currentSeg?.track_artist
                                              || channelName || "Tap a station to start";
  if (currentRjSegment) {
    activeSource = "AI_RJ";
    displayTrack = "AI RJ";
    displayArtist = (currentRjSegment.persona_name
                                              || currentRjSegment.voice_id
                                              || channelName
                                              || "RadioLife");
  } else if (podcastEpisode) {
    // Phase B — podcast episode is playing.  Show episode title +
    // podcast name.
    activeSource = "PODCAST";
    displayTrack = podcastEpisode.title || "Podcast episode";
    displayArtist = podcastEpisode.podcast_title || "Podcast";
  } else if (importedStation) {
    activeSource = "LIVE";
    displayTrack = importedStation.name || "Live Radio";
    displayArtist = [importedStation.country, importedStation.language]
                                              .filter(Boolean).join(" · ") || "Live broadcast";
  } else if (sessionId || activeSlug || currentSeg) {
    activeSource = "AI";
    displayTrack = currentSeg?.track_title || displayTrack;
  }

  const sourceBadgeClass = {
    AI:            "bg-cyan-400/20 text-cyan-300 border-cyan-400/30",
    AI_RJ:    "bg-amber-400/20 text-amber-300 border-amber-400/30",
    LIVE:        "bg-emerald-400/20 text-emerald-300 border-emerald-400/30",
    COMMUNITY: "bg-fuchsia-400/20 text-fuchsia-300 border-fuchsia-400/30",
    PODCAST:  "bg-violet-400/20 text-violet-300 border-violet-400/30",
  }[activeSource] || "";

  // Phase 18 — time-aware autoplay when user taps play with no channel active.
  //
  // P0 · 3rd attempt (2026-07-27) — FORCE NAVIGATION.  Prior in-place
  // `setImportedStation` attempts worked in Playwright but broke in real
  // browsers (the click handler / hot-reload / audio-autoplay-policy
  // interplay was too fragile).  The browse-card flow *already* works
  // reliably by navigating to `/radio/station/{id}`, so the bottom-bar
  // Play now uses the same route.  LiveRadioStation reads `?autoplay=1`
  // on mount and immediately calls togglePlay() so audio starts within
  // 3 s of the button tap.
  const onToggle = async () => {
    // Case 1 · a station, AI session, or podcast episode is already
    // selected — toggle play/pause.
    if (importedStation || sessionId || activeSlug || podcastEpisode) {
      window.dispatchEvent(new CustomEvent("bigfm:player:toggle"));
      return;
    }

    // Case 2 · Cold start — navigate to the top region-matched flagship.
    try {
      const backend = process.env.REACT_APP_BACKEND_URL || "";
      const r = await fetch(
        `${backend}/api/stations/flagship?limit=1`,
        { credentials: "include" });
      if (r.ok) {
        const d = await r.json();
        const top = (d.items || [])[0];
        if (top?.id) {
          window.location.href =
            `/radio/station/${encodeURIComponent(top.id)}?autoplay=1`;
          return;
        }
      }
    } catch (_e) { /* fall through */ }

    // Case 3 · Ultimate fallback — send user to Browse.
    window.location.href = "/radio/browse";
  };

  // Phase 18 — chip click switches channel (works on /radio + any route).
  const onSwitchChannel = (slug) => {
    window.location.href = `/radio?ch=${encodeURIComponent(slug)}&autoplay=1`;
  };

  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
  const thumb = podcastEpisode?.cover_image_url
                                    || importedStation?.favicon
                                    || channelThumb;
  const artworkBg = thumb
    ? (thumb.startsWith("http")
          ? `url(${thumb}) center/cover`
          : `url(${BACKEND_URL}${thumb}) center/cover`)
    : "linear-gradient(135deg,var(--accent-electric) 0%,var(--accent-magenta) 100%)";

  // 2026-07-31 — clicking the artwork toggles play/pause of the
  // currently-loaded station (parity with the play/pause button).
  // No navigation.  Cold-start (no station yet) is a deliberate
  // no-op — the play button still handles that flow.
  const hasContent = !!(importedStation || sessionId
                                                || activeSlug || podcastEpisode);
  const onArtworkClick = () => {
    if (!hasContent) return;
    window.dispatchEvent(new CustomEvent("bigfm:player:toggle"));
  };

  return (
    <>
    <div
      data-testid="mini-player"
      data-playing={playing ? "true" : "false"}
      data-has-session={currentSeg ? "true" : "false"}
      data-source={activeSource || "none"}
      className={[
        "flex items-center gap-3 px-4 py-2.5",
        "rounded-token-card border border-white/[0.08]",
        "bg-bg-glass backdrop-blur-glass shadow-glass",
        className,
      ].join(" ")}
    >
      <button
        type="button"
        onClick={onArtworkClick}
        aria-label={hasContent
          ? (playing ? "Pause" : "Play")
          : "Player artwork"}
        disabled={!hasContent}
        className="w-10 h-10 rounded-token-md flex-shrink-0 border-0 p-0
                              cursor-pointer disabled:cursor-default
                              focus:outline-none focus:ring-2 focus:ring-fuchsia-400/60"
        data-testid="mini-player-artwork"
        style={{ background: artworkBg }} />
      <div className="min-w-0 flex-1 max-w-[180px]">
        <div className="flex items-center gap-1.5 min-w-0">
          {activeSource && (
            <span
              data-testid="miniplayer-source-badge"
              data-source={activeSource}
              className={[
                "inline-block px-1.5 py-0.5 rounded text-[9px]",
                "font-mono uppercase tracking-widest border flex-shrink-0",
                sourceBadgeClass,
              ].join(" ")}
            >
              {activeSource === "AI_RJ" ? "AI RJ" : activeSource}
            </span>
          )}
          {/* Phase FUN.1 — FLAGSHIP pill for the FunAsia flagship stations. */}
          {importedStation?.is_flagship && (
            <span
              data-testid="miniplayer-flagship-badge"
              data-flagship-slug={importedStation.flagship_slug || ""}
              className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded
                                          text-[9px] font-black uppercase tracking-widest
                                          bg-gradient-to-r from-purple-500 to-pink-500 text-white
                                          flex-shrink-0">
              ★ FLAG
            </span>
          )}
          <div className="font-display text-sm font-semibold truncate"
                          data-testid="bottom-player-station-name"
                          data-legacy-testid="mini-player-track">{displayTrack}</div>
        </div>
        <div className="font-mono text-[10px] text-text-secondary truncate"
                data-testid="mini-player-artist">
          {displayArtist}
        </div>
        {/* Phase D — Hosted-by chip.  Only surfaces when a station has
              at least one active assigned persona.  Click opens a small
              tooltip via native browser `title` for MVP; a richer popover
              can come later. */}
        {rjPersona && (
          <div
            className="mt-0.5 inline-flex items-center gap-1 px-1.5 py-0.5
                                        rounded-full bg-violet-500/15 border border-violet-500/40
                                        text-violet-200 text-[10px] font-mono
                                        max-w-full w-fit"
            title={rjPersona.tagline || rjPersona.description
                              || `Hosted by ${rjPersona.name}`}
            data-testid="mini-player-persona-chip"
            data-persona-id={rjPersona.id}>
            <span aria-hidden>🎙️</span>
            <span className="truncate">
              Hosted by {rjPersona.name}
            </span>
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={onToggle}
        data-testid="bottom-player-play-button"
        data-legacy-testid="mini-player-toggle"
        className="w-9 h-9 rounded-full bg-accent-electric text-black
                          grid place-items-center transition-transform
                          duration-150 ease-out150 hover:scale-105 flex-shrink-0"
        aria-label={playing ? "Pause" : "Play"}
        aria-pressed={playing}
      >
        {playing ? "❚❚" : "▶"}
      </button>
      {/* Phase 42-E2.2 — share now-playing.  Builds a station deep
            link so the recipient lands on the same station with
            autoplay=1.  Falls back to plain text when no station/
            track is loaded yet. */}
      {(currentSeg || importedStation || activeSlug) && (() => {
          const trackTitle = currentSeg?.track_title;
          const stationName = importedStation?.name || channelName;
          const slug = activeSlug
            || (importedStation ? `live:${importedStation.id}` : null);
          const deepLink = slug && typeof window !== "undefined"
            ? `${window.location.origin}/radio/station/${encodeURIComponent(slug)}?autoplay=1`
            : (typeof window !== "undefined" ? window.location.origin : "");
          const text = trackTitle
            ? `Now playing: ${trackTitle}${stationName ? " on " + stationName : ""}. Listen on RadioLife →`
            : (stationName
                ? `I'm tuned to ${stationName} on RadioLife. Listen with me →`
                : "I'm listening on RadioLife — tune in →");
          return (
            <ShareButton
              compact
              featureType="miniplayer"
              contentId={slug || "current"}
              title={trackTitle || stationName || "RadioLife"}
              text={text}
              url={deepLink}
              iconSize={13} />
          );
      })()}
      {/* Phase B Bug B2 follow-up — footer city label.  Reads the same
            useGeoStore value as the header CityChip so the two surfaces
            are guaranteed to agree.  Hidden on the tightest mobile widths
            so the player buttons stay legible. */}
      {footerCity ? (
        <span
          data-testid="footer-city-label"
          data-footer-city={footerCity}
          className="hidden sm:inline-flex items-center gap-1.5 ml-1
                            px-2 h-6 rounded-full bg-white/[0.04]
                            border border-white/[0.06]
                            text-[10px] font-mono uppercase tracking-widest
                            text-text-secondary"
          title={`Resolved city — matches the header pill (${footerCity})`}
        >
          <span className="w-1 h-1 rounded-full bg-accent-electric" />
          Now in {footerCity}
        </span>
      ) : null}
      {/* Phase 18 — quick channel switch strip (hidden < 640px). */}
      <BottomBarChannelStrip currentSlug={activeSlug} onSwitch={onSwitchChannel} />
      {/* Phase P0-BAR — favorites + region-flagship rail (hidden < 640px
              on the mini-player row; the mobile shell shows its own copy
              above the bar). */}
      <div className="hidden sm:flex items-center min-w-0 max-w-[320px]"
                data-testid="bottom-bar-rail-slot-desktop">
        <BottomBarStationRail />
      </div>
      {/* Phase F-1 — unified points pill + drawer. */}
      <PointsHeaderWidget />
      {/* Phase 42-E1.1 — persistent banner ad (free users only).
              Phase LEGACY.1: hide inside the mini-player on mobile (<640px);
              the mobile shell renders a dedicated dismissible strip above
              the mini-player so the ad doesn't overflow the bottom nav. */}
      <div className="hidden sm:flex items-center gap-2">
        <PersistentBannerSlot placement="miniplayer" />
        {/* Phase AD.11 — bottom_bar zone (728×90).  Constrained to a
                small footprint inside the mini-player rail. */}
        <div className="hidden lg:block" style={{ maxWidth: 200 }}>
          <BannerZoneSlot zone="bottom_bar" />
        </div>
      </div>
      {/* Phase 42-D3 — favorites toggle + flyout pinned to the bottom bar. */}
      <FavoritesFlyoutToggle open={favOpen}
                                                onToggle={() => setFavOpen((v) => !v)} />
    </div>
    <FavoritesFlyout open={favOpen}
                                  onClose={() => setFavOpen(false)} />
    </>
  );
}
