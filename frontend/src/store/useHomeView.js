// Home view preference — V1 (classic New Look V2), V2 (Social Feed · Light),
// V3 (Social Feed · Dark). Backed by /api/social/home-view (stored per user).
// Non-destructive QA override: ?homeView=v1|v2|v3 (or social_feed/classic_v2
// with optional &appearance=light|dark). Overrides never bypass auth/launch.
import { create } from "zustand";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const VALID = new Set(["v1", "v2", "v3"]);

function queryOverride() {
  try {
    const p = new URLSearchParams(window.location.search);
    let hv = (p.get("homeView") || "").trim();
    const ap = (p.get("appearance") || "").trim();
    if (hv === "social_feed") hv = ap === "dark" ? "v3" : "v2";
    if (hv === "classic_v2") hv = "v1";
    if (VALID.has(hv)) return hv;
    if (!hv && ap) return ap === "dark" ? "v3" : "v2";
  } catch (_e) { /* ignore */ }
  return null;
}

export const useHomeView = create((set, get) => ({
  homeView: queryOverride() || "v2",
  loaded: false,
  override: queryOverride(),

  bootstrap: async () => {
    if (get().loaded) return;
    if (get().override) { set({ loaded: true }); return; }
    try {
      const r = await axios.get(`${API}/social/home-view`, { withCredentials: true });
      set({ homeView: VALID.has(r.data?.home_view) ? r.data.home_view : "v2", loaded: true });
    } catch (_e) { set({ loaded: true }); }
  },

  setView: async (hv) => {
    if (!VALID.has(hv)) return;
    set({ homeView: hv });
    try { await axios.put(`${API}/social/home-view`, { home_view: hv }, { withCredentials: true }); }
    catch (_e) { /* optimistic */ }
  },

  isSocialFeed: () => get().homeView === "v2" || get().homeView === "v3",
  appearance: () => (get().homeView === "v3" ? "dark" : "light"),
}));
