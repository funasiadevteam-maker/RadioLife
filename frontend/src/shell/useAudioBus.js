// Phase 15b — central audio bus. Routes that own an audio element call
// `useAudioBus({...callbacks})` once. The hook attaches `bigfm:player:*`
// + `bigfm:list:*` listeners to window and proxies them to the callbacks.
// This lets the keyboard shortcuts in 15a drive the real player without
// either side knowing about the other.
import { useEffect } from "react";

const EVENT_TO_CALLBACK = {
  "bigfm:player:toggle":  "onToggle",
  "bigfm:player:volup":   "onVolUp",
  "bigfm:player:voldown": "onVolDown",
  "bigfm:list:next":      "onListNext",
  "bigfm:list:prev":      "onListPrev",
};

export function useAudioBus(handlers = {}) {
  useEffect(() => {
    const wired = [];
    for (const [ev, key] of Object.entries(EVENT_TO_CALLBACK)) {
      const cb = handlers[key];
      if (!cb) continue;
      const fn = (e) => {
        try { cb(e?.detail); } catch (_) { /* swallow */ }
      };
      window.addEventListener(ev, fn);
      wired.push([ev, fn]);
    }
    return () => {
      wired.forEach(([ev, fn]) => window.removeEventListener(ev, fn));
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    // Re-bind only if the handler identities change. Pages pass useCallback'd
    // functions so this stays cheap.
    handlers.onToggle, handlers.onVolUp, handlers.onVolDown,
    handlers.onListNext, handlers.onListPrev,
  ]);
}

// Helper for pages that own an <audio> ref: clamp volume by `step` and
// return the new value. Used by Radio + MiniPlayer.
export function bumpVolume(audioEl, step) {
  if (!audioEl) return null;
  const cur = typeof audioEl.volume === "number" ? audioEl.volume : 1;
  const next = Math.max(0, Math.min(1, cur + step));
  audioEl.volume = next;
  return next;
}
