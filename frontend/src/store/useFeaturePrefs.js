// Per-user feature personalization — which FUUSIC features show on Home + nav.
// Shared across Home, the shell nav, the onboarding modal and the Settings
// page so a save anywhere updates everything reactively.
// Backed by /api/social/features (stored on the user doc).
import { create } from "zustand";
import axios from "axios";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export const useFeaturePrefs = create((set, get) => ({
  enabled: null,          // null until loaded → treat everything as on (no flash)
  catalog: [],
  mandatory: [],
  defaults: [],           // city-aware default set from the backend
  homeCity: null,
  needsOnboarding: false,
  loaded: false,
  loading: false,

  bootstrap: async () => {
    if (get().loading || get().loaded) return;
    set({ loading: true });
    try {
      const r = await axios.get(`${API}/social/features`, { withCredentials: true });
      set({
        enabled: r.data?.enabled || [],
        catalog: r.data?.catalog || [],
        mandatory: r.data?.mandatory || [],
        defaults: r.data?.default || [],
        homeCity: r.data?.home_city || null,
        needsOnboarding: !!r.data?.needs_onboarding,
        loaded: true,
      });
    } catch (_e) {
      set({ enabled: [], loaded: true });
    } finally {
      set({ loading: false });
    }
  },

  save: async (list) => {
    set({ enabled: list, needsOnboarding: false });
    try {
      await axios.put(`${API}/social/features`, { features: list },
        { withCredentials: true });
    } catch (_e) { /* optimistic — soft fail */ }
  },

  // true while unloaded (avoid hiding features before prefs arrive)
  isEnabled: (k) => {
    const e = get().enabled;
    return !e ? true : e.includes(k);
  },
}));
