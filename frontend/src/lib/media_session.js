/** Phase 42-E2.3 — MediaSession API glue.
 *
 *  Sets the OS-level metadata so iOS Control Center / Android
 *  notification / desktop lock-screen / Bluetooth headphones can show
 *  what's playing and toggle play/pause.
 *
 *  Per the spec:
 *    • `previoustrack` is INTENTIONALLY disabled (radio is
 *      non-interactive — no rewind).
 *    • `nexttrack` is supported but gracefully self-disables on a 429
 *      from the server-side skip-quota check.  Re-enabled at the next
 *      song boundary.
 *
 *  The module is no-op safe in browsers without MediaSession (older
 *  Safari desktop, IE).
 */

const supported = () =>
  typeof navigator !== "undefined" && "mediaSession" in navigator;

/** Phase 42-E2.3 — update both metadata + playbackState in one go. */
export function updateMediaSession({ title, artist, album, artwork, handlers }) {
  if (!supported()) return;
  try {
    if (title || artist || album || artwork) {
      // eslint-disable-next-line no-undef
      navigator.mediaSession.metadata = new MediaMetadata({
        title:    title  || "FUUSIC",
        artist:  artist || "",
        album:    album  || "FUUSIC",
        artwork: Array.isArray(artwork) ? artwork : [],
      });
    }
    if (handlers && typeof handlers === "object") {
      for (const [action, fn] of Object.entries(handlers)) {
        try {
          navigator.mediaSession.setActionHandler(
            action, fn ? fn : null);
        } catch (_e) {
          // Some browsers throw on unsupported actions — ignore.
        }
      }
    }
  } catch (_e) { /* metadata update failed — non-fatal */ }
}

/** Phase 42-E2.3 — flip the play/pause indicator (string union). */
export function setPlaybackState(state) {
  if (!supported()) return;
  try {
    navigator.mediaSession.playbackState =
      state === "playing" ? "playing"
        : state === "paused" ? "paused" : "none";
  } catch (_e) { /* */ }
}

/** Phase 42-E2.3 — disable a single handler (used on 429 from skip). */
export function disableHandler(action) {
  if (!supported()) return;
  try { navigator.mediaSession.setActionHandler(action, null); } catch (_e) { /* */ }
}

/** Phase 42-E2.3 — build a multi-resolution artwork array from one src.
 *  We hint the same URL at 96/256/512 so the OS picks the best match.
 *  The CDN ignores the size hint, but lock-screen rendering still
 *  honours `sizes`.
 */
export function artworkFromUrl(url, { absolute = true } = {}) {
  if (!url) return [];
  let abs = url;
  if (absolute && url.startsWith("/")) {
    const base = (typeof process !== "undefined" && process.env
                                && process.env.REACT_APP_BACKEND_URL) || "";
    abs = `${base}${url}`;
  }
  return [
    { src: abs, sizes:  "96x96",  type: "image/png" },
    { src: abs, sizes: "256x256", type: "image/png" },
    { src: abs, sizes: "512x512", type: "image/png" },
  ];
}
