// Phase 15d — geo store. Single source of truth for the user's resolved
// market. Bootstrap fires once on mount (App.js) and writes to localStorage
// so a hard refresh doesn't flash the wrong city. Components read with
// `const market = useGeoStore((s) => s.market);` to stay reactive.
import { create } from "zustand";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

const LS_KEY = "bigfm.geo.v1";

const SUPPORTED = ["dubai", "new_york", "london", "mumbai", "los_angeles", "dfw"];

const DISPLAY_NAMES = {
  dubai:        "Dubai",
  new_york:     "New York",
  london:       "London",
  mumbai:       "Mumbai",
  los_angeles:  "Los Angeles",
  dfw:           "Dallas",
};

function readCache() {
  try {
    const raw = localStorage.getItem(LS_KEY);
    if (!raw) return null;
    const obj = JSON.parse(raw);
    if (obj && typeof obj === "object" && obj.market) return obj;
  } catch (_e) { /* noop */ }
  return null;
}

function writeCache(geo) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(geo)); }
  catch (_e) { /* noop */ }
}

export const useGeoStore = create((set, get) => ({
  ready:         false,
  loading:       false,
  market:        readCache()?.market || "global",
  city:          readCache()?.city || "Global",
  country:       readCache()?.country || "",
  timezone:      readCache()?.timezone || "UTC",
  source:        readCache()?.source || "cache",
  supported:     SUPPORTED,
  displayName: (m) => DISPLAY_NAMES[m] || (m ? m.replace(/_/g, " ") : ""),

  bootstrap: async () => {
    if (get().loading) return;
    set({ loading: true });
    // Phase 15d.1 — send browser timezone as a fallback signal for
    // ipapi.co rate-limit / shared-egress IP misroutes. Server uses it
    // when the IP lookup falls back to mock.
    let tz = "";
    try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ""; }
    catch (_e) { /* noop */ }
    try {
      const r = await axios.get(`${API}/geo/me`,
                                            { params: tz ? { tz } : {}, timeout: 4500 });
      const g = r.data || {};
      const next = {
        market:    g.market   || "global",
        city:       g.city     || DISPLAY_NAMES[g.market || ""] || "Global",
        country:   g.country || "",
        timezone: g.timezone || tz || "UTC",
        source:    g.source   || "ip",
      };
      writeCache(next);
      set({ ...next, ready: true, loading: false });
    } catch (_e) {
      // Hold the cached value; just mark ready so consumers stop spinning.
      set({ ready: true, loading: false });
    }
  },

  setMarket: async (market, { persist = true } = {}) => {
    const m = (market || "").trim().toLowerCase().replace(/[\s-]/g, "_");
    if (!SUPPORTED.includes(m)) return false;
    const next = {
      market: m,
      city:    DISPLAY_NAMES[m],
      source: "override",
    };
    writeCache({ ...readCache(), ...next });
    set(next);
    if (persist) {
      try {
        await axios.patch(`${API}/users/me/market`, { market: m },
                                { withCredentials: true, timeout: 4500 });
      } catch (_e) {
        // anon visitors don't have a session — that's fine, override is
        // still applied client-side via the cache.
      }
    }
    return true;
  },

  clearOverride: async () => {
    try {
      await axios.patch(`${API}/users/me/market`, { market: null },
                              { withCredentials: true, timeout: 4500 });
    } catch (_e) { /* anon — noop */ }
    // Re-bootstrap from IP.
    await get().bootstrap();
  },
}));
