/** Phase B — Podcast episode playback bridge.
 *
 *  Mounted once at AppShell root (peer of <GlobalAudio /> and
 *  <ImportedStreamBridge />).  Owns a single <audio> element that plays
 *  the current podcast episode from `usePlayerStore.podcastEpisode`.
 *
 *  Duties:
 *    1. On new episode → GET saved progress, seek to `position_seconds`
 *         (or `podcastResumePosition` if the caller supplied it) then play.
 *    2. Mirror `playing` / `currentTime` / `duration` back to the store so
 *         MiniPlayer displays the right transport state.
 *    3. POST `/api/podcasts/episodes/{id}/progress` every 15s while
 *         playing + on pause + on ended (backend handles idempotency +
 *         completion detection + `podcast_completed` trigger).
 *    4. Listen for `bigfm:player:toggle` (dispatched by MiniPlayer / kb
 *         shortcuts) — pause/resume the podcast element.
 *
 *  Ducking / crossfade do NOT apply to podcast playback (per Phase B spec).
 *  Episodes play cleanly straight through.
 */
import { useEffect, useRef } from "react";
import axios from "axios";
import { usePlayerStore } from "@/store/usePlayerStore";
import { API } from "@/AuthContext";

const PROGRESS_INTERVAL_MS = 15_000;
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

function _resolveAudioUrl(url) {
  if (!url) return "";
  if (url.startsWith("http://") || url.startsWith("https://")) return url;
  return `${BACKEND_URL}${url.startsWith("/") ? "" : "/"}${url}`;
}

export default function PodcastPlayerBridge() {
  const episode          = usePlayerStore((s) => s.podcastEpisode);
  const resumePos        = usePlayerStore((s) => s.podcastResumePosition);
  const podcastPlaying   = usePlayerStore((s) => s.podcastPlaying);
  const setPodcastPlaying = usePlayerStore((s) => s.setPodcastPlaying);
  const setCurrentTime   = usePlayerStore((s) => s.setCurrentTime);
  const setDuration      = usePlayerStore((s) => s.setDuration);
  const setPlaying       = usePlayerStore((s) => s.setPlaying);

  const audioRef = useRef(null);
  const activeIdRef = useRef(null);
  const lastPingRef = useRef(0);
  const inFlightRef = useRef(false);

  // ── Post progress helper — idempotent on the backend side. ──
  const postProgress = async (position) => {
    if (!episode || inFlightRef.current) return;
    if (!Number.isFinite(position) || position < 0) return;
    inFlightRef.current = true;
    try {
      const r = await axios.post(
        `${API}/podcasts/episodes/${episode.episode_id}/progress`,
        { position_seconds: Math.floor(position),
          duration_seconds: episode.duration_seconds || undefined },
        { withCredentials: true });
      // Phase G — surface AD.9 completion awards via a toast + custom
      // event.  The response payload carries `ad9_awards` on the same
      // request that flips completion; render exactly once.
      const awards = r?.data?.ad9_awards || [];
      if (awards.length > 0) {
        try {
          window.dispatchEvent(new CustomEvent("bigfm:ad9-awards", {
            detail: { awards, episode_id: episode.episode_id },
          }));
        } catch { /* no-op */ }
        try {
          const { toast } = await import("sonner");
          for (const a of awards) {
            const label = a.currency === "usd"
              ? `+$${(a.points_awarded / 100).toFixed(2)} voucher`
              : `+${a.points_awarded} points`;
            const msg = a.sponsor_message
              ? `${label} — ${a.sponsor_message}`
              : label;
            toast.success(`🎉 ${msg}`, {
              duration: 6000,
              id: `ad9-${a.award_id}`,
            });
          }
        } catch { /* sonner unavailable — event still fired */ }
      }
    } catch (_e) {
      // Silent — anon users get 401, that's expected; server also stays
      // silent on other faults.
    } finally {
      inFlightRef.current = false;
      lastPingRef.current = Date.now();
    }
  };

  // ── On episode change: load audio, restore position, play. ──
  useEffect(() => {
    const el = audioRef.current;
    if (!el || !episode) {
      activeIdRef.current = null;
      return;
    }
    // Guard against re-runs for the same episode.
    if (activeIdRef.current === episode.episode_id) return;
    activeIdRef.current = episode.episode_id;
    const src = _resolveAudioUrl(episode.audio_url);
    if (!src) return;
    el.src = src;
    // Restore server-known position ELSE the caller-supplied resume ELSE 0.
    (async () => {
      let seekTo = Number(resumePos) || 0;
      try {
        const r = await axios.get(
          `${API}/podcasts/episodes/${episode.episode_id}/progress`,
          { withCredentials: true });
        const saved = r?.data?.progress;
        if (saved && Number(saved.position_seconds) > 0 &&
                !saved.completed) {
          // Rewind 3 s so the resume doesn't clip mid-word.
          seekTo = Math.max(0, Number(saved.position_seconds) - 3);
        }
      } catch (_e) { /* anon or 404 — use 0. */ }
      try {
        el.currentTime = seekTo;
      } catch (_e) { /* not-ready yet — will apply on canplay. */ }
      try {
        await el.play();
        setPodcastPlaying(true);
      } catch (_e) {
        // Autoplay policy blocked — user has to hit play. Not fatal.
        setPodcastPlaying(false);
      }
    })();
     
  }, [episode?.episode_id]);

  // ── Play/pause sync when store flag flips. ──
  useEffect(() => {
    const el = audioRef.current;
    if (!el || !episode) return;
    if (podcastPlaying && el.paused) {
      el.play().catch(() => setPodcastPlaying(false));
    } else if (!podcastPlaying && !el.paused) {
      el.pause();
    }
  }, [podcastPlaying, episode, setPodcastPlaying]);

  // ── Global toggle event — pauses / resumes podcast. ──
  useEffect(() => {
    if (!episode) return;
    const handler = () => {
      const el = audioRef.current;
      if (!el) return;
      if (el.paused) {
        el.play().catch(() => {});
      } else {
        el.pause();
      }
    };
    window.addEventListener("bigfm:player:toggle", handler);
    return () => window.removeEventListener(
      "bigfm:player:toggle", handler);
  }, [episode]);

  // ── Audio element event listeners. ──
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onTimeUpdate = () => {
      setCurrentTime(el.currentTime || 0);
      // Every 15 s while playing, POST progress.
      const now = Date.now();
      if (!el.paused &&
          now - (lastPingRef.current || 0) >= PROGRESS_INTERVAL_MS) {
        postProgress(el.currentTime);
      }
    };
    const onDurationChange = () => {
      if (Number.isFinite(el.duration)) setDuration(el.duration);
    };
    const onPlay  = () => {
      setPodcastPlaying(true);
      setPlaying(true);
    };
    const onPause = () => {
      setPodcastPlaying(false);
      setPlaying(false);
      // Snapshot on pause.
      postProgress(el.currentTime || 0);
    };
    const onEnded = () => {
      setPodcastPlaying(false);
      setPlaying(false);
      // Force a final ping at duration → backend flips completed.
      if (Number.isFinite(el.duration)) postProgress(el.duration);
    };
    el.addEventListener("timeupdate", onTimeUpdate);
    el.addEventListener("durationchange", onDurationChange);
    el.addEventListener("play",  onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    return () => {
      el.removeEventListener("timeupdate", onTimeUpdate);
      el.removeEventListener("durationchange", onDurationChange);
      el.removeEventListener("play",  onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
    };
     
  }, [episode?.episode_id]);

  return (
    <audio
      ref={audioRef}
      data-testid="podcast-audio-element"
      preload="metadata"
      style={{ display: "none" }}
    />
  );
}
