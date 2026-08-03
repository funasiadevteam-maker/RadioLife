/** Phase 42-D3 — Station favorites store (BigFM AI channels + imported live radio).
 *
 *  Drives the Heart toggle on every station card AND the favorites
 *  strip exposed via MiniPlayer.  Backed by /api/me/favorite-stations
 *  (see backend/routes/station_favorites.py).  Distinct from the
 *  channel-slug-only `useFavoritesStore` that powers the home strip.
 */
import { create } from "zustand";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL;

export const useStationFavoritesStore = create((set, get) => ({
  favorites: [],       // [{favorite_id, station_id, station_type, station}]
  cap: 100,
  loaded: false,
  loading: false,

  bootstrap: async () => {
    if (get().loading) return;
    set({ loading: true });
    try {
      const r = await axios.get(`${API}/api/me/favorite-stations`,
                                                          { withCredentials: true });
      set({ favorites: r.data?.items || [],
                  cap: r.data?.cap || 100,
                  loaded: true, loading: false });
    } catch (_e) {
      set({ favorites: [], loaded: true, loading: false });
    }
  },

  isFavorited: (stationId) =>
    get().favorites.some((f) => f.station_id === stationId),

  add: async (stationId, stationType, optimisticStation = null) => {
    const existing = get().favorites.find(
      (f) => f.station_id === stationId);
    if (existing) return { ok: true, already: true };
    // Optimistic add.
    const optimistic = {
      favorite_id: `tmp_${stationId}`,
      station_id: stationId,
      station_type: stationType,
      station: optimisticStation || { id: stationId, name: stationId,
                                                                          type: stationType },
      added_at: new Date().toISOString(),
    };
    set({ favorites: [optimistic, ...get().favorites] });
    try {
      const r = await axios.post(
        `${API}/api/me/favorite-stations`,
        { station_id: stationId, station_type: stationType },
        { withCredentials: true });
      // Patch the temp id with the real one.
      set({
        favorites: get().favorites.map((f) =>
          f.station_id === stationId
            ? { ...f, favorite_id: r.data.favorite_id }
            : f),
      });
      return { ok: true };
    } catch (e) {
      // Rollback.
      set({
        favorites: get().favorites.filter(
          (f) => f.station_id !== stationId),
      });
      const code = e?.response?.data?.detail?.code;
      return { ok: false, code,
                      message: code === "favorites_cap"
                                  ? `Favorites limit reached (${get().cap}).`
                                  : "Couldn't favorite this station." };
    }
  },

  remove: async (stationId) => {
    const prev = get().favorites;
    set({ favorites: prev.filter((f) => f.station_id !== stationId) });
    try {
      await axios.delete(
        `${API}/api/me/favorite-stations/${stationId}`,
        { withCredentials: true });
      return { ok: true };
    } catch (_e) {
      // Rollback.
      set({ favorites: prev });
      return { ok: false };
    }
  },

  toggle: async (stationId, stationType, optimisticStation = null) => {
    return get().isFavorited(stationId)
      ? get().remove(stationId)
      : get().add(stationId, stationType, optimisticStation);
  },

  reset: () => set({ favorites: [], loaded: false }),
}));
