/** Phase 42-A2 — Imported-stream playback bridge.
 *  Phase 42-B-redux — Pre-roll gate added.
 *
 *  Mounted once at AppShell root next to <GlobalAudio />.  Owns a single
 *  <audio> element that plays raw imported live-radio streams when the
 *  global player store has `importedStation != null`.
 *
 *  Pre-roll flow (Phase 42-B-redux):
 *    1. New importedStation lands in the store (via setImportedStation).
 *    2. Bridge calls POST /api/live-radio/preroll/request.
 *    3. If `has_preroll=true` → render <PrerollOverlay/>, keep the live
 *       <audio> paused with `pendingLiveSrc` cached.
 *    4. On overlay complete/skip → swap to `pendingLiveSrc` and play.
 *    5. If `has_preroll=false` (premium / grace / cap / no ad) → play
 *       live stream immediately.
 *
 *  Source isolation: pre-roll requests are ONLY made for `imp_*` station
 *  ids.  AI (`source==='bigfm_ai'`) and community (`source==='community'`)
 *  do their own playback elsewhere and never hit this bridge.
 */
import { useEffect, useRef, useState, useCallback } from "react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { API } from "@/AuthContext";
import axios from "axios";
import PrerollOverlay from "@/components/PrerollOverlay";
// P0 mixed-content fix — defense-in-depth: rewrite http:// URLs at the
// single choke point right before `<audio>.src` assignment.  Every
// caller already rewrites at setImportedStation time; this catches any
// path that bypasses the util (e.g. a store rehydration from disk).
import { toPlayableStreamUrl } from "@/utils/streamUrl";

// Stable per-tab session id used as the dedup key for anonymous users.
function _getSessionId() {
  try {
    const KEY = "bigfm.preroll.session.v1";
    let v = sessionStorage.getItem(KEY);
    if (!v) {
      v = `sess_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
      sessionStorage.setItem(KEY, v);
    }
    return v;
  } catch (_e) { return `sess_${Date.now()}`; }
}

// Phase 42-B2.4 (2026-07-31) — resolve the playable stream URL from
// any of the three shapes callers use.  Historical inconsistency:
//   • LiveRadioStation / RadioBrowse / FavoriteControls: pass
//     `stream_url` (already rewritten with toPlayableStreamUrl).
//   • RadioHome.startListening / FlagshipRail.onPlay /
//     RadioHome.BrowseTeaser click / FlagshipStrip.play: pass
//     `url_resolved` + `url` in the raw imported_radio_stations
//     shape, NO `stream_url` field at all.
//
// Previously the bridge only read `.stream_url` and returned early
// (`!importedStation.stream_url` → teardown), so every play from
// the home flagship rail SILENTLY failed — audio.src stayed empty
// while the mini-player still showed the LIVE ribbon (store had
// an importedStation entry but no bytes ever flowed).  This is
// the "click flagship #1 plays fine ✓ / click flagship #2 does
// nothing" symptom users reported.
//
// The single choke point below reads all three shapes with
// `stream_url ?? url_resolved ?? url` and then defensively
// rewrites through `toPlayableStreamUrl` so any http:// upstream
// still routes through /api/stream-proxy.
function _resolveStreamUrl(station) {
  if (!station) return null;
  const raw = station.stream_url || station.url_resolved || station.url;
  return raw ? toPlayableStreamUrl(raw) : null;
}

export default function ImportedStreamBridge() {
  const importedStation = usePlayerStore((s) => s.importedStation);
  const importedPlaying = usePlayerStore((s) => s.importedPlaying);
  const setImportedPlaying = usePlayerStore((s) => s.setImportedPlaying);
  const setPlaying = usePlayerStore((s) => s.setPlaying);
  const audioRef = useRef(null);

  // Pre-roll state: null | "loading" | {chain: [{impression_id, ad}], idx: 0, chain_count}
  const [preroll, setPreroll] = useState(null);
  // Cache the live stream URL while pre-roll plays.
  const liveSrcRef = useRef(null);
  // Track which station we've already gated so we don't loop.
  const gatedStationIdRef = useRef(null);
  // Phase RELIABILITY.P2 — consecutive-failure counter per station.
  // Reset on station change or successful play.  When it hits 2 in
  // quick succession we open the StationOfflineModal via a global
  // CustomEvent and tear down the imported slot.
  const failureCountRef = useRef({ id: null, count: 0, lastAt: 0 });

  // Phase PREROLL.EXT — preroll is served across ALL station types
  // (imported, community, AI channels).  The backend resolver in
  // `preroll_ad_service.resolve_station` handles the id-shape zoo; if
  // the station lands via `setImportedStation` we always ask for a
  // preroll.  Non-imported ids that don't resolve get a benign 200 with
  // `has_preroll:false, reason:"station_not_found"` and we play through.
  const isImportedSource = !!importedStation;

  // ────────── Pre-roll request: fires when a new imp_* station lands.
  useEffect(() => {
    if (!importedStation) {
      gatedStationIdRef.current = null;
      setPreroll(null);
      liveSrcRef.current = null;
      failureCountRef.current = { id: null, count: 0, lastAt: 0 };
      return;
    }
    // New station → reset failure counter.
    if (failureCountRef.current.id !== importedStation.id) {
      failureCountRef.current = {
        id: importedStation.id, count: 0, lastAt: 0,
      };
    }
    if (!isImportedSource) {
      // Non-imported (defensive): just play directly.
      gatedStationIdRef.current = importedStation.id;
      return;
    }
    // Already gated this exact station instance — don't re-request.
    if (gatedStationIdRef.current === importedStation.id) return;
    gatedStationIdRef.current = importedStation.id;
    liveSrcRef.current = _resolveStreamUrl(importedStation);
    setPreroll("loading");
    axios.post(`${API}/live-radio/preroll/request`, {
      station_id: importedStation.id,
      session_id: _getSessionId(),
    }, { withCredentials: true }).then((r) => {
      if (r.data?.has_preroll) {
        // Phase 42-F.4 — backend returns either a single `ad`/`impression_id`
        // (chain_count=1, legacy shape) or arrays `ads`/`impression_ids`
        // (chain_count>1).  Normalise to a chain array of length >= 1.
        const ads = Array.isArray(r.data.ads) && r.data.ads.length
          ? r.data.ads : [r.data.ad];
        const ids = Array.isArray(r.data.impression_ids) && r.data.impression_ids.length
          ? r.data.impression_ids : [r.data.impression_id];
        const chain = ads.map((ad, i) => ({
          impression_id: ids[i] || ids[0], ad,
        }));
        setPreroll({ chain, idx: 0, chain_count: r.data.chain_count || chain.length });
      } else {
        setPreroll(null);
      }
    }).catch(() => {
      // Fail-open: if pre-roll service is down, skip straight to live.
      setPreroll(null);
    });
  }, [importedStation, isImportedSource]);

  const _startLive = useCallback(() => {
    const el = audioRef.current;
    if (!el || !liveSrcRef.current) return;
    if (el.src !== liveSrcRef.current) {
      el.src = liveSrcRef.current;
      el.load();
    }
    // Fire and forget — the `<audio>` element's onPlay/onPause events
    // are the source of truth for `importedPlaying`, not the .play()
    // Promise resolution.  Historical bug (2026-07-27): calling
    // `setImportedPlaying(false)` inside `.catch()` flipped the store
    // back to paused on rejected `play()` calls (e.g. autoplay-policy
    // AbortError raised when the resume happened milliseconds after a
    // pause) — freezing the button on the paused state.  Now we just
    // log the rejection; if the play truly failed, the audio remains
    // paused and the store already reflects that.
    const p = el.play();
    if (p && typeof p.catch === "function") {
      p.catch((err) => {
        // eslint-disable-next-line no-console
        console.warn("[ImportedStreamBridge] play() rejected:",
                                err && err.name, err && err.message);
      });
    }
  }, []);

  // ────────── Drive the live audio element.
  // When there is NO active pre-roll (and we have a station), play the
  // live stream.  When a pre-roll IS active, keep the live audio paused.
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    // No station at all → tear down.
    if (!importedStation || !_resolveStreamUrl(importedStation)) {
      el.pause();
      el.removeAttribute("src");
      el.load();
      return;
    }
    // Pre-roll is active or loading → wait.
    if (preroll) {
      if (!el.paused) el.pause();
      return;
    }
    // Pre-roll resolved → drive the audio element per store state.
    //
    // P0 · 2026-07-27 (2nd iteration) — three distinct branches now, so
    // the play↔pause↔resume↔pause↔resume cycle is fully symmetric:
    //   (a) importedPlaying + no src   → cold start via _startLive()
    //   (b) importedPlaying + paused   → simple el.play() resume
    //   (c) !importedPlaying + playing → el.pause()
    // Previously (b) fell through to _startLive() which fires el.load()
    // — that reload plus the racy `.catch(setImportedPlaying(false))`
    // path meant the resume click occasionally flipped the store back
    // to paused, freezing the button.
    const expectedSrc = liveSrcRef.current;
    if (importedPlaying) {
      if (!el.src || (expectedSrc && el.src !== expectedSrc)) {
        _startLive();                                     // cold start
      } else if (el.paused) {
        const p = el.play();                        // resume (no reload)
        if (p && typeof p.catch === "function") {
          p.catch((err) => {
            // eslint-disable-next-line no-console
            console.warn("[ImportedStreamBridge] resume() rejected:",
                                    err && err.name, err && err.message);
          });
        }
      }
    } else if (!el.paused) {
      el.pause();
    }
  }, [importedStation, importedPlaying, preroll, _startLive]);

  // Overlay → next ad in chain (if any) → live stream transition.
  const _onPrerollDone = useCallback(() => {
    setPreroll((cur) => {
      if (!cur || cur === "loading") return null;
      const nextIdx = cur.idx + 1;
      if (nextIdx >= cur.chain.length) {
        // End of chain — drop the overlay; the effect below kicks live audio.
        return null;
      }
      // Advance to next ad in the chain.
      return { ...cur, idx: nextIdx };
    });
    // _startLive runs in the effect above; mark playing=true so it kicks
    // ONLY when the chain has cleared.  React batches this state update
    // with the previous one; the live-play effect re-reads preroll on
    // re-render, so a non-null chain keeps the audio paused.
    setImportedPlaying(true);
  }, [setImportedPlaying]);

  // ────────── Global toggle handler (mini-player play/pause).
  useEffect(() => {
    const onToggle = () => {
      const el = audioRef.current;
      if (!el) return;
      const s = usePlayerStore.getState();
      if (!s.importedStation) return;
      // If a pre-roll is up, ignore the global toggle entirely.
      if (preroll) return;
      if (s.importedPlaying) {
        el.pause();
        setImportedPlaying(false);
      } else {
        el.play().then(() => setImportedPlaying(true)).catch(() => {});
      }
    };
    window.addEventListener("bigfm:player:toggle", onToggle);
    return () => window.removeEventListener("bigfm:player:toggle", onToggle);
  }, [preroll, setImportedPlaying]);

  // Phase RELIABILITY.P2 — <audio onError> handler.  Reports the
  // failure to /api/playback-errors (fire-and-forget), and on the
  // 2nd consecutive failure within 60s dispatches
  // `bigfm:station-offline` so StationOfflineModal opens.  A single
  // failure is silently retried by the browser's own <audio> element
  // recovery; only sustained failures escalate to the user.
  const _onAudioError = useCallback(() => {
    setImportedPlaying(false);
    const st = importedStation;
    if (!st || !st.id) return;
    // Extract MediaError code + upstream host for context.
    const el = audioRef.current;
    let errorCode = "unknown";
    if (el && el.error) {
      // MediaError codes: 1=aborted, 2=network, 3=decode, 4=src_not_supported
      errorCode = `media_error_${el.error.code || "unknown"}`;
    }
    let hostname = null;
    try {
      const rawSrc = (el && el.currentSrc) || liveSrcRef.current || "";
      // Extract raw upstream URL from /api/stream-proxy?src=... if present.
      const m = rawSrc.match(/[?&]src=([^&]+)/);
      const target = m ? decodeURIComponent(m[1]) : rawSrc;
      hostname = new URL(target).hostname;
    } catch (_) { /* ignore parse errors */ }

    axios.post(`${API}/playback-errors`, {
      station_id:  st.id,
      error_code:  errorCode,
      hostname,
      source:      st.source || "imported",
    }, { withCredentials: true }).catch(() => { /* fire-and-forget */ });

    const now = Date.now();
    const rec = failureCountRef.current;
    if (rec.id !== st.id) {
      failureCountRef.current = { id: st.id, count: 1, lastAt: now };
      return;
    }
    // Reset the counter if the previous failure was long enough ago
    // to be a fresh listening session.
    if (now - rec.lastAt > 60_000) {
      failureCountRef.current = { id: st.id, count: 1, lastAt: now };
      return;
    }
    const nextCount = rec.count + 1;
    failureCountRef.current = { id: st.id, count: nextCount, lastAt: now };
    if (nextCount >= 2) {
      // Double failure → escalate to modal.  Reset the counter so a
      // subsequent retry starts fresh once the user picks a new
      // station.
      failureCountRef.current = { id: null, count: 0, lastAt: 0 };
      try {
        window.dispatchEvent(new CustomEvent("bigfm:station-offline", {
          detail: { station_id: st.id, station_name: st.name || null },
        }));
      } catch (_) { /* older browsers */ }
    }
  }, [importedStation, setImportedPlaying]);

  return (
    <>
      {/* Phase Π+4.1 — only mount the imported audio element when an
                imported station is actually set, so pages without an active
                imported stream have zero bridge audios in the DOM. */}
      {importedStation && (
        <audio
          ref={audioRef}
          preload="none"
          data-testid="imported-stream-audio"
          onPlay={() => {
            setImportedPlaying(true);
            setPlaying(true);
            // Successful play → reset the failure counter so a later
            // outage counts from zero.
            failureCountRef.current = { id: null, count: 0, lastAt: 0 };
          }}
          onPause={() => { setImportedPlaying(false); setPlaying(false); }}
          onError={_onAudioError}
          style={{ display: "none" }} />
      )}
      {preroll && preroll !== "loading" && (
        <PrerollOverlay
          key={`${preroll.chain[preroll.idx].impression_id}-${preroll.idx}`}
          impressionId={preroll.chain[preroll.idx].impression_id}
          ad={preroll.chain[preroll.idx].ad}
          chainPosition={preroll.idx + 1}
          chainCount={preroll.chain.length}
          onComplete={_onPrerollDone}
          onSkip={_onPrerollDone}
        />
      )}
    </>
  );
}
