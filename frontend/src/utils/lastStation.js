// Last-played FUUSIC AI station — powers the "Continue where you left off"
// resume card on Radio Discover. Client-only (localStorage); ephemeral by design.
const KEY = "fuusic:lastAiStation";

export function setLastAiStation({ slug, name, thumb }) {
  if (!slug) return;
  try {
    localStorage.setItem(KEY, JSON.stringify({
      slug, name: name || null, thumb: thumb || null, ts: Date.now(),
    }));
  } catch (_e) { /* ignore quota / SSR */ }
}

export function getLastAiStation() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const v = JSON.parse(raw);
    return v && v.slug ? v : null;
  } catch (_e) { return null; }
}
