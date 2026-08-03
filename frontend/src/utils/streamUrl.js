/**
 * P0 fix — Mixed-content proxy rewrite helper.
 *
 * The frontend is served over HTTPS.  Any `<audio src="http://...">` is
 * silently blocked by every modern browser as mixed content.  Some
 * upstream radio streams don't support TLS natively, so we route them
 * through `/api/stream-proxy?src=...` (a FastAPI streaming proxy with
 * SSRF-hardened host allowlist and Range pass-through).
 *
 * Rewrite rule:
 *   - `http://...`      → `${API_BASE}/api/stream-proxy?src=<encoded>`
 *   - `https://...`     → returned unchanged
 *   - `//foo`, relative → returned unchanged
 *   - falsy             → returned as-is
 *
 * Used by every player entry point that sets `stream_url` on the
 * global player store, and defensively by ImportedStreamBridge just
 * before assigning to `<audio>.src` (single choke point).
 */
const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

/**
 * @param {string|null|undefined} url — original upstream stream URL.
 * @returns {string|null|undefined} — a browser-safe URL (HTTPS or proxy).
 */
export function toPlayableStreamUrl(url) {
  if (!url || typeof url !== "string") return url;
  const trimmed = url.trim();
  if (!trimmed) return url;
  // Case-insensitive match on the scheme.  Any http:// upstream is
  // rewritten; https:// (and everything else) passes through.
  if (/^http:\/\//i.test(trimmed)) {
    const encoded = encodeURIComponent(trimmed);
    return `${BACKEND_URL}/api/stream-proxy?src=${encoded}`;
  }
  return trimmed;
}

/**
 * Convenience — mutate a station-shaped object in place-safe way: return
 * a shallow copy with `stream_url` rewritten.  Everything else on the
 * object is preserved.  Passes null/undefined through unchanged.
 */
export function withPlayableStreamUrl(station) {
  if (!station || typeof station !== "object") return station;
  const original = station.stream_url;
  const playable = toPlayableStreamUrl(original);
  if (playable === original) return station;
  return { ...station, stream_url: playable };
}
