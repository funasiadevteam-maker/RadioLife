// Custom order for a listener's pinned AI stations (drag-to-reorder).
// Client-only (localStorage) — pins themselves live in the favourites API;
// this just remembers the order the listener dragged them into.
const KEY = "fuusic:pinOrder";

export function getPinOrder() {
  try {
    const v = JSON.parse(localStorage.getItem(KEY));
    return Array.isArray(v) ? v : [];
  } catch (_e) { return []; }
}

export function setPinOrder(ids) {
  try { localStorage.setItem(KEY, JSON.stringify(ids || [])); } catch (_e) { /* ignore */ }
}

// Sort stations by the saved order; unknown (newly pinned) ids keep their
// incoming position at the end via a stable sort.
export function orderByPinOrder(stations) {
  const order = getPinOrder();
  const rank = (id) => {
    const i = order.indexOf(id);
    return i === -1 ? Number.MAX_SAFE_INTEGER : i;
  };
  return [...stations].sort((a, b) => rank(a.id) - rank(b.id));
}
