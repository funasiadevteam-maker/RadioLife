// Phase 15d.3 — Global audio mount.  Renders the TWO crossfade <audio>
// elements ONCE at the AppShell root so that route navigation never
// unmounts the audio nodes.  Owns the cross-route control plane:
//
//   1.  Mirrors `currentTime`, `playing`, `duration` to `usePlayerStore`
//       so MiniPlayer / Radio.js can render the right transport UI from
//       anywhere in the app.
//   2.  Wires the Media Session API so browser-level media hubs (Chrome
//       URL-bar media button, macOS Touch Bar, Android lock screen,
//       Windows volume mixer) all see FUUSIC track metadata + transport
//       controls.
//   3.  Listens for the `bigfm:player:toggle` window event (dispatched
//       by the keyboard shortcuts AND the MiniPlayer ▶/❚❚ button) and
//       plays / pauses the currently-active audio element.  This works
//       from EVERY route because the listener lives on AppShell, not on
//       Radio.js.
//   4.  Drives the `ended` handler — when the current segment finishes,
//       it swaps to the prefetched next segment (the "B" element) and
//       triggers the next prefetch from `/api/radio/next`.  This is the
//       continuous-radio promise: songs play back-to-back even if the
//       user is sitting on /account or /wallet.
//
// NOTE: This component does NOT call `startRadio` — that remains a
// user-gesture-only action in Radio.js / Home.jsx so browsers honor
// autoplay policy.  Once a session is live the prefetched chain keeps
// playing forever.
import { useEffect, useRef } from "react";
import axios from "axios";
import { toast } from "sonner";
import { API } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { audioElements } from "@/store/audioElements";
// Phase 42-E2.3 — MediaSession helpers (skip-cap aware).
import { setPlaybackState, disableHandler } from "@/lib/media_session";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const PREFETCH_LEAD_SEC = 8;

export default function GlobalAudio() {
  const sessionId      = usePlayerStore((s) => s.sessionId);
  const currentSeg     = usePlayerStore((s) => s.currentSeg);
  const nextSeg        = usePlayerStore((s) => s.nextSeg);
  const activeIdx      = usePlayerStore((s) => s.activeIdx);
  const channelName    = usePlayerStore((s) => s.activeChannelName);
  const channelThumb   = usePlayerStore((s) => s.activeChannelThumb);

  const setNextSeg     = usePlayerStore((s) => s.setNextSeg);
  const setCurrentSeg  = usePlayerStore((s) => s.setCurrentSeg);
  const pushHistory    = usePlayerStore((s) => s.pushHistory);
  const setActiveIdx   = usePlayerStore((s) => s.setActiveIdx);
  const setPlaying     = usePlayerStore((s) => s.setPlaying);
  const setCurrentTime = usePlayerStore((s) => s.setCurrentTime);
  const setDuration    = usePlayerStore((s) => s.setDuration);
  const setSkipState   = usePlayerStore((s) => s.setSkipState);
  // Phase 42-E2.3 — skip quota mirror for MediaSession nexttrack toggle.
  const skipUsed       = usePlayerStore((s) => s.skipUsed);
  const skipLimit      = usePlayerStore((s) => s.skipLimit);

  // Phase H'.5a — AI-RJ inter-song glue.
  const rjCadence            = usePlayerStore((s) => s.rjCadence);
  const songsPlayedSinceRj  = usePlayerStore((s) => s.songsPlayedSinceRj);
  const currentRjSegment    = usePlayerStore((s) => s.currentRjSegment);
  const setRjCadence            = usePlayerStore((s) => s.setRjCadence);
  const bumpSongsSinceRj    = usePlayerStore((s) => s.bumpSongsPlayedSinceRj);
  const resetSongsSinceRj  = usePlayerStore((s) => s.resetSongsPlayedSinceRj);
  const setCurrentRjSegment = usePlayerStore((s) => s.setCurrentRjSegment);

  // Phase J.5 — mid-stream audio-ad glue.  Parallel counter to RJ.
  // We keep the state in a local ref because we don't need the rest of
  // the app to read it; ImportedStreamBridge etc. don't care.
  const midstreamCadenceRef       = useRef(null);   // null = unknown, fetched on session start
  const songsSinceMidstreamRef = useRef(0);
  const midstreamPlayingRef      = useRef(false);
  const midstreamStationIdRef  = useRef(null);

  // Refs so the event handlers always read the latest store snapshot.
  // (zustand selectors are NOT used inside imperative DOM listeners.)
  const stateRef = useRef({});
  stateRef.current = { sessionId, currentSeg, nextSeg, activeIdx,
                                              rjCadence, songsPlayedSinceRj,
                                              currentRjSegment };
  const prefetchTriggered = useRef(false);

  // ─── Phase J.5 — fetch midstream cadence once per session ───────────
  useEffect(() => {
    if (!sessionId) return;
    if (midstreamCadenceRef.current !== null) return;
    let cancelled = false;
    axios.get(`${API}/admin/midstream-ad/cadence`, { withCredentials: true,
                                                                                                              timeout: 4000 })
      .then((r) => {
        if (cancelled) return;
        const n = Number(r.data?.every_n_songs);
        if (Number.isFinite(n) && n >= 2 && n <= 8) {
          midstreamCadenceRef.current = n;
        } else {
          midstreamCadenceRef.current = 4;
        }
      })
      .catch(() => {
        // Anonymous / non-admin — default to 4.  The server will honour
        // its own runtime cadence on /request anyway.
        if (!cancelled) midstreamCadenceRef.current = 4;
      });
    return () => { cancelled = true; };
  }, [sessionId]);

  // ─── Phase J.5 — request ONE mid-stream ad ──────────────────────────
  // Returns the ad object on success, null otherwise.  Never throws.
  const fetchMidstreamAd = async () => {
    const stationId = midstreamStationIdRef.current
                                            || stateRef.current?.currentSeg?.station_id
                                            || null;
    if (!stationId) return null;
    if (midstreamPlayingRef.current) return null;
    try {
      const r = await axios.post(`${API}/live-radio/midstream-ad/request`,
        { station_id: stationId,
          session_id: stateRef.current.sessionId,
          songs_played_in_session: songsSinceMidstreamRef.current },
        { withCredentials: true, timeout: 8000 });
      if (r.data?.has_ad && r.data?.ad) {
        return { ...r.data.ad, impression_id: r.data.impression_id || null };
      }
    } catch (_e) { /* swallow — non-critical */ }
    return null;
  };

  // ─── Phase J.5 — play a mid-stream ad on the RJ <audio> element ─────
  // Reuses the RJ audio element so we get the same mediasession + skip
  // semantics for free.  Resolves when the ad ends or errors.
  const playMidstreamAd = (ad) => new Promise((resolve) => {
    const rjEl = audioElements.rj.current;
    const audioUrl = ad?.audio_url || ad?.creative_url || ad?.url;
    if (!rjEl || !audioUrl) { resolve(); return; }
    midstreamPlayingRef.current = true;
    // Phase COMPANION.1 — surface the ad's companion offer above the
    // player (synced) for the duration of the audio ad, when present.
    const comp = (ad?.attached_offer_id || ad?.companion_image_url
                                || ad?.companion_cta_url)
      ? {
          impression_id: ad.impression_id || null,
          source: ad.source || "local",
          advertiser_name: ad.advertiser_name || null,
          name: ad.name || null,
          cta_text: ad.companion_cta_text || null,
          cta_url: ad.companion_cta_url || null,
          image_url: ad.companion_image_url || null,
          offer_id: ad.attached_offer_id || null,
        }
      : null;
    if (comp) usePlayerStore.getState().setActiveCompanion(comp);
    rjEl.src = audioUrl.startsWith("http") ? audioUrl
                            : `${BACKEND_URL}${audioUrl}`;
    rjEl.volume = 1.0;
    const cleanup = () => {
      rjEl.removeEventListener("ended", onDone);
      rjEl.removeEventListener("error", onDone);
      midstreamPlayingRef.current = false;
      usePlayerStore.getState().setActiveCompanion(null);
      resolve();
    };
    const onDone = () => cleanup();
    rjEl.addEventListener("ended", onDone, { once: true });
    rjEl.addEventListener("error", onDone, { once: true });
    rjEl.play().catch(() => cleanup());
  });

  // ─── Phase H'.5a — fetch cadence once per session start ─────────────
  useEffect(() => {
    if (!sessionId) return;
    if (rjCadence !== null) return;
    let cancelled = false;
    axios.get(`${API}/ai-rj/segment/cadence`, { withCredentials: true,
                                                                                                  timeout: 6000 })
      .then((r) => {
        if (cancelled) return;
        const n = Number(r.data?.every_n_songs);
        if (Number.isFinite(n) && n >= 2 && n <= 6) setRjCadence(n);
      })
      .catch(() => { /* silent — cadence stays null = no RJ inserts */ });
    return () => { cancelled = true; };
  }, [sessionId, rjCadence, setRjCadence]);

  // ─── Phase H'.5a — generate an inter-song RJ segment ────────────────
  // Returns the segment object (with audio_url) on success, null on
  // failure / over-quota / no cadence.  Never throws — caller must
  // gracefully skip ahead to the next song.
  const fetchRjSegment = async (prevSeg, nextSegHint) => {
    try {
      const body = {
        previous_track: prevSeg ? {
          track_id: prevSeg.track_id,
          title:      prevSeg.track_title || "",
          artist:    prevSeg.track_artist || "",
          energy_level: prevSeg.energy_level || "medium",
          mood:        prevSeg.mood || null,
        } : null,
        next_track: {
          track_id: nextSegHint?.track_id,
          title:      nextSegHint?.track_title || "Up next",
          artist:    nextSegHint?.track_artist || "",
          energy_level: nextSegHint?.energy_level || "medium",
          mood:        nextSegHint?.mood || null,
        },
        channel_name: channelName,
      };
      const r = await axios.post(`${API}/ai-rj/segment/generate`, body,
                                                              { withCredentials: true, timeout: 30000 });
      if (r.data?.audio_url) {
        console.log("[ai-rj] segment ready",
                                  { cache_hit: r.data.cache_hit, voice: r.data.voice_id,
                                      dur: r.data.duration_seconds });
        return r.data;
      }
    } catch (e) {
      console.warn("[ai-rj] segment fetch failed — skipping", e?.message);
    }
    return null;
  };

  // ─── Phase H'.5a — play an RJ segment on the dedicated <audio> ──────
  // Returns a promise that resolves when the RJ audio finishes (or
  // fails to load).  The caller is responsible for triggering the
  // song-swap afterwards.
  const playRjSegment = (rjSeg) => new Promise((resolve) => {
    const rjEl = audioElements.rj.current;
    if (!rjEl || !rjSeg?.audio_url) { resolve(); return; }
    setCurrentRjSegment(rjSeg);
    rjEl.src = `${BACKEND_URL}${rjSeg.audio_url}`;
    rjEl.volume = 1.0;
    const cleanup = () => {
      rjEl.removeEventListener("ended", onDone);
      rjEl.removeEventListener("error", onDone);
      setCurrentRjSegment(null);
      resolve();
    };
    const onDone = () => cleanup();
    rjEl.addEventListener("ended", onDone, { once: true });
    rjEl.addEventListener("error", onDone, { once: true });
    rjEl.play().catch(() => cleanup());
  });

  // ─── Phase R — fetch + play a live news bulletin ────────────────────
  // Best-effort integration point (spec R.4):
  //
  //   The bulletin injection reuses the SAME crossfade slot + RJ audio
  //   element as Phase I sponsored reads.  Callers pass a Phase R
  //   `news_channels.id`; the endpoint returns the most recent bulletin
  //   with `status="live"`.  On success the RJ element streams the
  //   Tigris audio URL, mid-stream ad-ducking picks it up like any
  //   voice event, then normal music/talk resumes on `ended`.
  //
  //   Not called anywhere by default — a station's metadata needs a
  //   `news_channel_id` pointer (or the caller picks the channel via
  //   region_code) before the injection is opt-in.  When you wire this,
  //   call `await fetchAndPlayNewsBulletin(currentStation.news_channel_id)`
  //   inside the `onEnded` handler ABOVE the existing sponsored-read
  //   branch so news bulletins take precedence during a news-tagged
  //   station's playback loop.
  //
  //   Safe by design: any fetch/render error returns false silently and
  //   the crossfade proceeds without the bulletin.
  // eslint-disable-next-line no-unused-vars
  const fetchAndPlayNewsBulletin = async (channelId) => {
    if (!channelId) return false;
    let bulletin = null;
    try {
      const r = await axios.get(
        `${API}/news/bulletins/next`,
        { withCredentials: true, timeout: 6000,
          params: { channel_id: channelId } });
      bulletin = r.data?.bulletin || null;
    } catch (e) {
      console.warn("[phase-r-news] next-bulletin fetch failed", e?.message);
      return false;
    }
    if (!bulletin?.audio_url) return false;
    const rjEl = audioElements.rj.current;
    if (!rjEl) return false;
    console.log("[phase-r-news] injecting bulletin",
                              bulletin.id, bulletin.channel_id);
    setCurrentRjSegment({ ...bulletin, is_news_bulletin: true });
    rjEl.src = bulletin.audio_url;
    rjEl.volume = 1.0;
    await new Promise((resolve) => {
      const cleanup = () => {
        rjEl.removeEventListener("ended", onEnd);
        rjEl.removeEventListener("error", onEnd);
        setCurrentRjSegment(null);
        resolve();
      };
      const onEnd = () => cleanup();
      rjEl.addEventListener("ended", onEnd, { once: true });
      rjEl.addEventListener("error", onEnd, { once: true });
      rjEl.play().catch(cleanup);
    });
    return true;
  };

  // ─── Phase I (M1) — fetch + play a sponsored AI-RJ read ─────────────
  // Fired in the same slot as an RJ cadence break, BEFORE the regular
  // RJ segment.  Impression is recorded after the audio finishes so a
  // listener who abandons before it plays isn't counted.  Silent on any
  // network error — sponsored reads must never break playback.
  const fetchAndPlaySponsoredRead = async (stationId) => {
    if (!stationId) return false;
    let readMeta = null;
    try {
      const r = await axios.get(
        `${API}/rj/sponsored-reads/next-sponsored`,
        { withCredentials: true, timeout: 6000,
          params: { station_id: stationId } });
      readMeta = r.data?.sponsored_read || null;
    } catch (e) {
      console.warn("[m1-rjsr] next-sponsored fetch failed", e?.message);
      return false;
    }
    if (!readMeta?.audio_url) return false;
    const rjEl = audioElements.rj.current;
    if (!rjEl) return false;

    // Use the RJ <audio> element so mid-stream ad ducking + player UI
    // pick this up as an on-air voice event.  Signed Tigris URL is
    // absolute, so we skip the BACKEND_URL prefix.
    console.log("[m1-rjsr] injecting sponsored read",
                              readMeta.sponsored_read_id, readMeta.disclosure_chip);
    setCurrentRjSegment({ ...readMeta, is_sponsored: true });
    rjEl.src = readMeta.audio_url;
    rjEl.volume = 1.0;
    await new Promise((resolve) => {
      const cleanup = () => {
        rjEl.removeEventListener("ended", onEnd);
        rjEl.removeEventListener("error", onEnd);
        setCurrentRjSegment(null);
        resolve();
      };
      const onEnd = () => cleanup();
      rjEl.addEventListener("ended", onEnd, { once: true });
      rjEl.addEventListener("error", onEnd, { once: true });
      rjEl.play().catch(() => cleanup());
    });

    // Fire-and-forget impression.  Deduped per (read, user, hour) on
    // the backend so double-fires from unmount races are harmless.
    axios.post(
      `${API}/rj/sponsored-reads/${readMeta.sponsored_read_id}/played`,
      { station_id: stationId },
      { withCredentials: true, timeout: 4000 })
        .catch(() => { /* swallow */ });
    return true;
  };

  // ─── Prefetch the next segment from /api/radio/next ────────────────
  const fetchNext = async () => {
    const sid = stateRef.current.sessionId;
    if (!sid) return null;
    try {
      const r = await axios.get(`${API}/radio/next`,
        { params: { session_id: sid }, timeout: 120000 });
      if (r.data?.skip_state) {
        const ss = r.data.skip_state;
        setSkipState(ss.used, ss.limit, ss.reset_in_sec || 0);
      }
      return r.data.segment;
    } catch (_e) {
      return null;
    }
  };

  // ─── Cross-route toggle from MiniPlayer / keyboard shortcut ─────────
  //
  // Phase Π+4.1 (2026-07-25) — source-aware routing.  Both GlobalAudio
  // (AI-composed radio) AND ImportedStreamBridge (raw live streams)
  // listen for `bigfm:player:toggle`.  Prior to this fix, when the
  // MiniPlayer Pause fired while an imported station was playing, the
  // ImportedStreamBridge would correctly pause its audio + setPlaying(
  // false), then GlobalAudio's handler would race in — see its own
  // (idle, srcless) AI audio A element as `paused`, call .play() on
  // it, and setPlaying(true), silently OVERRIDING the bridge's pause.
  // Result: mini-player button state never updates on imported routes.
  //
  // Fix: if an imported station is active in the store, this handler
  // returns immediately and lets the bridge own the toggle.
  useEffect(() => {
    const onToggle = () => {
      // Source-aware: defer to ImportedStreamBridge for imported streams.
      if (usePlayerStore.getState().importedStation) return;
      const i = stateRef.current.activeIdx;
      const a = i === 0 ? audioElements.a.current : audioElements.b.current;
      if (!a) return;
      if (a.paused) {
        a.play().then(() => setPlaying(true)).catch(() => {});
      } else {
        a.pause(); setPlaying(false);
      }
    };
    window.addEventListener("bigfm:player:toggle", onToggle);
    return () => window.removeEventListener("bigfm:player:toggle", onToggle);
  }, [setPlaying]);

  // ─── Cross-route SKIP / NEXT ────────────────────────────────────────
  // Fired by the Now Playing next button, PlayerBarV2 skip, keyboard
  // shortcut, and the MediaSession `nexttrack` glyph (all dispatch
  // `bigfm:player:skip`). Previously NOTHING listened for this event, so
  // the Now Playing "next" button was a dead control and the station just
  // kept spinning without ever advancing. This handler performs the real
  // POST /api/radio/skip against the active crossfade element — the SAME
  // logic the classic Radio.js skip() uses, but owned by the global audio
  // engine so it works from every route and every design variant.
  useEffect(() => {
    let skipping = false;
    const onSkip = async () => {
      const store = usePlayerStore.getState();
      // Skip only applies to the AI-composed radio session — not raw
      // imported live streams or podcast episodes.
      if (store.importedStation || store.podcastEpisode) return;
      const sid = stateRef.current.sessionId;
      if (!sid || skipping) return;
      skipping = true;
      store.setAdvancing(true);
      const aIdx = stateRef.current.activeIdx;
      const activeEl = aIdx === 0 ? audioElements.a.current
                                  : audioElements.b.current;
      if (activeEl) { try { activeEl.pause(); } catch (_e) { /* */ } }
      try {
        const r = await axios.post(`${API}/radio/skip`, null,
          { params: { session_id: sid }, timeout: 120000 });
        if (r.data?.skip_state) {
          const ss = r.data.skip_state;
          setSkipState(ss.used, ss.limit, ss.reset_in_sec || 0);
        }
        const seg = r.data.segment;
        if (seg) {
          // Play on the prefetched "B" element when one is ready; else
          // reuse the active element.
          const preIdx = 1 - aIdx;
          const preEl = preIdx === 0 ? audioElements.a.current
                                     : audioElements.b.current;
          const hasPrefetch = !!stateRef.current.nextSeg && !!preEl;
          const targetEl = hasPrefetch ? preEl : activeEl;
          const targetIdx = hasPrefetch ? preIdx : aIdx;
          if (targetEl) {
            const url = `${BACKEND_URL}${seg.segment_url}`;
            if (targetEl.src !== url) { targetEl.src = url; targetEl.load(); }
            try { await targetEl.play(); setPlaying(true); setActiveIdx(targetIdx); }
            catch (_e) { /* autoplay policy — UI still advances */ }
          }
          setCurrentSeg(seg);
          pushHistory(seg);
          setNextSeg(null);
          prefetchTriggered.current = false;
          // Prefetch the subsequent segment in the background.
          setTimeout(async () => {
            const nseg = await fetchNext();
            if (nseg) {
              setNextSeg(nseg);
              const inactiveIdx = 1 - usePlayerStore.getState().activeIdx;
              const inactive = inactiveIdx === 0 ? audioElements.a.current
                                                 : audioElements.b.current;
              if (inactive) { inactive.src = `${BACKEND_URL}${nseg.segment_url}`; inactive.load(); }
            }
          }, 100);
        }
      } catch (e) {
        if (e?.response?.status === 429) {
          const d = e.response.data || {};
          if (d.skip_state) {
            const ss = d.skip_state;
            setSkipState(ss.used, ss.limit, ss.reset_in_sec || 0);
          }
          const secs = d.reset_in_sec || d.retry_after_sec || 0;
          const mins = secs > 0 ? Math.ceil(secs / 60) : 0;
          toast.error(mins > 0
            ? `Skip limit reached — more skips in ~${mins} min.`
            : "Skip limit reached — try again shortly.");
          // Resume the paused current track so the listener isn't left silent.
          if (activeEl) { try { await activeEl.play(); setPlaying(true); } catch (_e) { /* */ } }
        } else {
          toast.error(e?.response?.data?.detail?.message
            || e?.response?.data?.detail || "Couldn't skip — try again.");
          if (activeEl) { try { await activeEl.play(); setPlaying(true); } catch (_e) { /* */ } }
        }
      } finally {
        skipping = false;
        usePlayerStore.getState().setAdvancing(false);
      }
    };
    window.addEventListener("bigfm:player:skip", onSkip);
    return () => window.removeEventListener("bigfm:player:skip", onSkip);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ─── Attach per-element listeners.  Re-attaches when activeIdx flips
  //      so timeupdate/ended always come from the *active* element. ──
  //
  // Phase Π+4.1 — `sessionId` added to deps so this effect re-runs the
  // moment the audio elements are mounted (they're gated behind
  // `aiActive` in the render).  Without this the listeners wouldn't
  // attach on first session start after our conditional mount.
  useEffect(() => {
    const a = activeIdx === 0 ? audioElements.a.current
                              : audioElements.b.current;
    if (!a) return;

    const onTime = () => {
      setCurrentTime(a.currentTime);
      // Trigger prefetch when within PREFETCH_LEAD_SEC of segment end.
      if (!prefetchTriggered.current
          && a.duration > 0
          && (a.duration - a.currentTime) < PREFETCH_LEAD_SEC
          && !stateRef.current.nextSeg) {
        prefetchTriggered.current = true;
        fetchNext().then((seg) => {
          if (seg) {
            setNextSeg(seg);
            const inactiveIdx = 1 - stateRef.current.activeIdx;
            const inactive = inactiveIdx === 0 ? audioElements.a.current
                                                : audioElements.b.current;
            if (inactive) {
              inactive.src = `${BACKEND_URL}${seg.segment_url}`;
              inactive.load();
            }
          }
        });
      }
    };
    const onMeta = () => setDuration(a.duration || 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = async () => {
      const { activeIdx: aIdx, nextSeg: nSeg,
                      currentSeg: cSeg,
                      rjCadence: cadence,
                      songsPlayedSinceRj: sPlayed } = stateRef.current;
      const inactiveIdx = 1 - aIdx;
      const inactiveEl = inactiveIdx === 0 ? audioElements.a.current
                                            : audioElements.b.current;

      // Phase H'.5a — count this song as played and, if we've crossed
      // the cadence threshold, slip an AI-RJ segment in BEFORE swapping
      // to the prefetched next song.  Failures fall through to the
      // existing crossfade path silently.
      bumpSongsSinceRj();
      const shouldRj = cadence && (sPlayed + 1) >= cadence;
      if (shouldRj) {
        // Phase I — check for a sponsored read FIRST; if one is
        // available for this station, play it before the RJ break.
        const stationId = cSeg?.station_id
                                                || midstreamStationIdRef.current
                                                || null;
        let playedSponsored = false;
        if (stationId) {
          playedSponsored = await fetchAndPlaySponsoredRead(stationId);
        }
        const rjSeg = await fetchRjSegment(cSeg, nSeg);
        if (rjSeg || playedSponsored) {
          resetSongsSinceRj();
          if (rjSeg) await playRjSegment(rjSeg);
          // intentional fall-through to the normal swap below.
        }
      }

      // Phase J.5 — independent mid-stream ad counter.  Staggered with
      // the RJ counter so the same song boundary never fires both.
      // Cadence default = 4 (env / admin override via system_config).
      try {
        const msCadence = midstreamCadenceRef.current || 4;
        songsSinceMidstreamRef.current += 1;
        // remember the station_id from the current segment so anonymous
        // bridge audio (preroll skip) still resolves to a station.
        if (cSeg?.station_id) midstreamStationIdRef.current = cSeg.station_id;
        const shouldMidstream = !shouldRj
                                                      && (songsSinceMidstreamRef.current >= msCadence);
        if (shouldMidstream) {
          const ad = await fetchMidstreamAd();
          if (ad) {
            songsSinceMidstreamRef.current = 0;
            await playMidstreamAd(ad);
          } else {
            // Reset counter to halfway so we don't hammer the SSP on
            // every song after a no-fill.
            songsSinceMidstreamRef.current = Math.floor(msCadence / 2);
          }
        }
      } catch (_e) { /* swallow — non-critical */ }

      if (nSeg && inactiveEl) {
        // Crossfade-ready: B was prefetched, just swap.
        setActiveIdx(inactiveIdx);
        setCurrentSeg(nSeg);
        pushHistory(nSeg);
        setNextSeg(null);
        prefetchTriggered.current = false;
        try { await inactiveEl.play(); setPlaying(true); }
        catch (_e) { setPlaying(false); }
        // Prefetch THIRD segment in background.
        setTimeout(async () => {
          const seg = await fetchNext();
          if (seg) {
            setNextSeg(seg);
            const newInactive = aIdx === 0 ? audioElements.a.current
                                            : audioElements.b.current;
            if (newInactive) {
              newInactive.src = `${BACKEND_URL}${seg.segment_url}`;
              newInactive.load();
            }
          }
        }, 100);
      } else {
        // No prefetch ready — fetch + play on the SAME element.
        const seg = await fetchNext();
        if (seg) {
          setCurrentSeg(seg);
          pushHistory(seg);
          if (a) {
            a.src = `${BACKEND_URL}${seg.segment_url}`;
            a.load();
            try { await a.play(); setPlaying(true); }
            catch (_e) { /* */ }
          }
        }
      }
    };

    a.addEventListener("timeupdate", onTime);
    a.addEventListener("loadedmetadata", onMeta);
    a.addEventListener("durationchange", onMeta);
    a.addEventListener("play", onPlay);
    a.addEventListener("pause", onPause);
    a.addEventListener("ended", onEnded);
    return () => {
      a.removeEventListener("timeupdate", onTime);
      a.removeEventListener("loadedmetadata", onMeta);
      a.removeEventListener("durationchange", onMeta);
      a.removeEventListener("play", onPlay);
      a.removeEventListener("pause", onPause);
      a.removeEventListener("ended", onEnded);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIdx, sessionId]);

  // Reset prefetch flag every time the current segment changes (so the
  // next prefetch happens against the freshly-active track).
  useEffect(() => {
    prefetchTriggered.current = false;
  }, [currentSeg?.segment_id]);

  // ─── Media Session API (browser/OS-level media controls) ────────────
  // Sets metadata that surfaces on Chrome media hub, macOS Touch Bar /
  // lock screen, Android lock screen, Windows volume mixer.  Album text
  // intentionally uses the dynamic channel name ("FUUSIC · Bollywood Mehfil",
  // "FUUSIC · VIP Lounge", etc.) — never hardcoded.
  //
  // Phase 15d.3 race fix — we publish on TWO triggers:
  //   (a) currentSeg changes (new track within the same channel), and
  //   (b) channelName / channelThumb changes (channel switch — fires
  //       synchronously the moment the listener clicks a new station
  //       because Radio.js writes those to the store optimistically,
  //       BEFORE the /radio/switch_channel API resolves).
  // This eliminates the 5-15s lag between click and lock-screen update.
  useEffect(() => {
    if (typeof window === "undefined" || !("mediaSession" in navigator)) return;
    if (!currentSeg && !channelName) {
      navigator.mediaSession.metadata = null;
      return;
    }
    const albumLabel = channelName ? `FUUSIC · ${channelName}` : "FUUSIC";
    const artworkSrc = channelThumb
      ? (channelThumb.startsWith("http") ? channelThumb : `${BACKEND_URL}${channelThumb}`)
      : null;
    try {
      navigator.mediaSession.metadata = new window.MediaMetadata({
        title:  currentSeg?.track_title  || channelName || "On Air",
        artist: currentSeg?.track_artist || channelName || "FUUSIC",
        album:  albumLabel,
        artwork: artworkSrc
          ? [{ src: artworkSrc, sizes: "1024x1024", type: "image/webp" }]
          : [],
      });
    } catch (_e) { /* older browsers without MediaMetadata constructor */ }
  }, [currentSeg, channelName, channelThumb]);

  // Wire Media Session action handlers ONCE — re-attaching every render
  // resets handler state on some browsers.
  useEffect(() => {
    if (typeof window === "undefined" || !("mediaSession" in navigator)) return;
    const fire = (ev) => window.dispatchEvent(new CustomEvent(ev));
    try {
      navigator.mediaSession.setActionHandler("play",
        () => fire("bigfm:player:toggle"));
      navigator.mediaSession.setActionHandler("pause",
        () => fire("bigfm:player:toggle"));
      navigator.mediaSession.setActionHandler("nexttrack",
        () => fire("bigfm:player:skip"));
      navigator.mediaSession.setActionHandler("previoustrack", null);
    } catch (_e) { /* */ }
    return () => {
      try {
        navigator.mediaSession.setActionHandler("play", null);
        navigator.mediaSession.setActionHandler("pause", null);
        navigator.mediaSession.setActionHandler("nexttrack", null);
      } catch (_e) { /* */ }
    };
  }, []);

  // Phase 42-E2.3 — MediaSession playback state + skip-cap handling.
  //  • Mirror our `playing` flag to navigator.mediaSession.playbackState
  //    so the lock-screen pause/play glyph stays in sync.
  //  • When the skip quota is exhausted, NULL-out the `nexttrack`
  //    handler so the OS-level skip button disappears.  The handler is
  //    re-attached at the next song boundary (currentSeg change).
  const playing = usePlayerStore((s) => s.playing);
  useEffect(() => {
    setPlaybackState(playing ? "playing" : "paused");
  }, [playing]);

  useEffect(() => {
    if (typeof window === "undefined" || !("mediaSession" in navigator)) return;
    const exhausted = skipLimit > 0 && skipUsed >= skipLimit;
    try {
      if (exhausted) {
        disableHandler("nexttrack");
      } else {
        navigator.mediaSession.setActionHandler("nexttrack",
          () => window.dispatchEvent(new CustomEvent("bigfm:player:skip")));
      }
    } catch (_e) { /* */ }
  }, [skipUsed, skipLimit, currentSeg?.segment_id]);

  // ─── Render — invisible.  Two parallel <audio> tags for crossfade. ──
  // Phase Π+4.1 (2026-07-25) — gate the AI-composed audio placeholders
  // behind `sessionId || currentSeg || currentRjSegment` so a deep-load
  // to an imported-station page (where no AI session is ever started)
  // has exactly ONE `<audio>` in the DOM — the one owned by
  // ImportedStreamBridge.  Every effect above already guards with
  // `if (!a) return`, so the null-ref window is safe.  When an AI
  // session later starts, sessionId flips truthy → these audios mount
  // → the `[activeIdx, sessionId]` listener-attach effect below re-runs
  // and wires up the freshly-mounted elements.
  const aiActive = !!(sessionId || currentSeg || currentRjSegment);
  return (
    <div aria-hidden style={{ position: "fixed", width: 0, height: 0,
                                      overflow: "hidden", opacity: 0 }}
          data-testid="global-audio-mount">
      {aiActive && (<>
        <audio
          ref={(el) => { audioElements.a.current = el; }}
          preload="auto"
          data-testid="audio-0"
          data-active={activeIdx === 0 ? "true" : "false"}
        />
        <audio
          ref={(el) => { audioElements.b.current = el; }}
          preload="auto"
          data-testid="audio-1"
          data-active={activeIdx === 1 ? "true" : "false"}
        />
        {/* Phase H'.5a — dedicated AI-RJ inter-song segment element. */}
        <audio
          ref={(el) => { audioElements.rj.current = el; }}
          preload="auto"
          data-testid="audio-rj"
          data-active={currentRjSegment ? "true" : "false"}
        />
      </>)}
    </div>
  );
}
