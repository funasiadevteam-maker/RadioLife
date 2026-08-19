// Switchable web browse layouts. Persists to localStorage + honors ?layout=.
import { create } from "zustand";

const KEY = "bigfm_browse_layout";
export const BROWSE_LAYOUTS = [
  { key: "classic", label: "Classic", desc: "Original RadioLife look" },
  { key: "cinematic", label: "Cinematic", desc: "Netflix-style rails" },
  { key: "studio", label: "Studio", desc: "Spotify-style library" },
  { key: "tube", label: "Tube", desc: "YouTube-style grid" },
];
const VALID = BROWSE_LAYOUTS.map((l) => l.key);

function initial() {
  try {
    const p = new URLSearchParams(window.location.search).get("layout");
    if (p && VALID.includes(p)) { localStorage.setItem(KEY, p); return p; }
    const s = localStorage.getItem(KEY);
    if (s && VALID.includes(s)) return s;
  } catch (_e) { /* ignore */ }
  return "classic";
}

export const useBrowseLayoutStore = create((set) => ({
  layout: initial(),
  setLayout: (l) => {
    if (!VALID.includes(l)) return;
    try { localStorage.setItem(KEY, l); } catch (_e) { /* ignore */ }
    set({ layout: l });
  },
}));

export function useBrowseLayout() {
  return useBrowseLayoutStore((s) => s.layout);
}
