/** Phase 41 S4.5.A — Anonymous device fingerprint helper.
 *
 * Produces a stable per-browser identifier used to dedupe coupon
 * redemptions for anonymous (logged-out) listeners. NEVER shared
 * with third parties — only used by the RadioLife backend's
 * `(announcement_id, device_fingerprint)` unique compound index to
 * make `POST /api/announcements/{id}/redeem` idempotent.
 *
 * Strategy:
 *   1. Look up an existing id in localStorage under `bigfm_device_id`.
 *   2. If missing, hash `userAgent + screen + timezoneOffset` via
 *      SubtleCrypto SHA-256 → 32 hex chars. Persist to localStorage.
 *   3. Always return the URL-safe stable id (8-128 char regex on the
 *      backend so 32 hex chars passes cleanly).
 *
 * Falls back to a `Math.random()` based id when `crypto.subtle` is
 * unavailable (very old browsers).
 */

const STORAGE_KEY = "bigfm_device_id";
let _memo = null;

async function _sha256Hex(text) {
  const enc = new TextEncoder().encode(text);
  const buf = await window.crypto.subtle.digest("SHA-256", enc);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 32);
}

function _fallbackId() {
  return `fb${Math.random().toString(36).slice(2, 12)}${Date.now()
    .toString(36)
    .slice(-8)}`;
}

export async function getDeviceFingerprint() {
  if (_memo) return _memo;
  try {
    const cached = window.localStorage.getItem(STORAGE_KEY);
    if (cached && /^[A-Za-z0-9_-]{8,128}$/.test(cached)) {
      _memo = cached;
      return cached;
    }
  } catch {
    // localStorage may be unavailable (Safari private mode)
  }

  let id;
  try {
    const seed = [
      navigator.userAgent || "",
      `${window.screen?.width || 0}x${window.screen?.height || 0}`,
      `${window.screen?.colorDepth || 0}`,
      `${new Date().getTimezoneOffset()}`,
      navigator.language || "",
    ].join("|");
    id = await _sha256Hex(seed);
  } catch {
    id = _fallbackId();
  }

  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // ignore
  }
  _memo = id;
  return id;
}

/** Returns the current fingerprint synchronously if it has already
 * been computed in this session (or read from localStorage during a
 * previous mount). May return null on the very first call before
 * `getDeviceFingerprint()` resolves once.
 */
export function getDeviceFingerprintSync() {
  if (_memo) return _memo;
  try {
    const v = window.localStorage.getItem(STORAGE_KEY);
    if (v && /^[A-Za-z0-9_-]{8,128}$/.test(v)) {
      _memo = v;
      return v;
    }
  } catch {
    // ignore
  }
  return null;
}
