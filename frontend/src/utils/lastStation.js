// Last-played + recently-played FUUSIC AI stations.
// Powers the Discover "Continue where you left off" card (last) and the
// "Jump back in" row (recents). Client-only (localStorage); ephemeral.
const KEY = "fuusic:lastAiStation";
const RECENTS_KEY = "fuusic:recentAiStations";
const MAX_RECENTS = 10;

export function setLastAiStation({ slug, name, thumb }) {
  if (!slug) return;
  const entry = { slug, name: name || null, thumb: thumb || null, ts: Date.now() };
  try {
    localStorage.setItem(KEY, JSON.stringify(entry));
  } catch (_e) { /* ignore quota/SSR */ }
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    let list = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(list)) list = [];
    list = list.filter((x) => x && x.slug && x.slug !== slug);
    list.unshift(entry);
    localStorage.setItem(RECENTS_KEY, JSON.stringify(list.slice(0, MAX_RECENTS)));
  } catch (_e) { /* ignore */ }
}

export function getLastAiStation() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const v = JSON.parse(raw);
    return v && v.slug ? v : null;
  } catch (_e) { return null; }
}

export function getRecentAiStations() {
  try {
    const raw = localStorage.getItem(RECENTS_KEY);
    const l = raw ? JSON.parse(raw) : [];
    return Array.isArray(l) ? l.filter((x) => x && x.slug) : [];
  } catch (_e) { return []; }
}
