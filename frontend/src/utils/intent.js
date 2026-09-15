// Preserve-intent helper. A public-landing CTA stores the destination the
// visitor wanted (e.g. "/radio/create"), then after sign-in / sign-up /
// onboarding we send them straight there instead of the generic home.
//
// `consumeIntent()` is a page-load singleton: it reads + clears sessionStorage
// on first call and returns the SAME value for the rest of the page load, so
// the multiple post-auth navigate() sites in Login don't race each other.
const KEY = "rl_intent";
let _cached;

export function setIntent(path) {
  try { if (path) sessionStorage.setItem(KEY, path); } catch (_e) { /* ignore */ }
}

export function consumeIntent() {
  if (_cached !== undefined) return _cached;
  try {
    _cached = sessionStorage.getItem(KEY) || null;
    sessionStorage.removeItem(KEY);
  } catch (_e) {
    _cached = null;
  }
  return _cached;
}
