/**
 * Phase 18 — Favorites store + Home rec cards + bottom-bar strip helpers.
 *
 * - `useFavoritesStore` (zustand) — favorites: [{channel_slug, channel}].
 * - `useAutoplaySuggestion` — fetches /api/me/autoplay/suggestion lazily.
 * - `useTopRecs` — top-channel & top-game cards for the home hero.
 */
import { create } from "zustand";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL + "/api";
if (axios.defaults) axios.defaults.withCredentials = true;
const FAVORITES_CAP = 8;

export const useFavoritesStore = create((set, get) => ({
  favorites: [],          // [{channel_slug, channel}]
  cap:        FAVORITES_CAP,
  loaded:    false,

  bootstrap: async () => {
    try {
      const { data } = await axios.get(`${API}/me/favorites`);
      set({ favorites: data.favorites || [], cap: data.cap || FAVORITES_CAP, loaded: true });
    } catch {
      set({ favorites: [], loaded: true });
    }
  },

  add: async (slug) => {
    const cur = get().favorites;
    if (cur.some((f) => f.channel_slug === slug)) return { ok: true, added: false };
    if (cur.length >= get().cap) {
      return { ok: false, code: "favorites_cap",
                  message: `You've got ${get().cap} favorites already — remove one to add another.` };
    }
    try {
      await axios.post(`${API}/me/favorites`, { channel_slug: slug });
      await get().bootstrap();
      return { ok: true, added: true };
    } catch (e) {
      const d = e?.response?.data?.detail;
      return { ok: false,
                  code: d?.code,
                  message: d?.message || "Couldn't add favorite." };
    }
  },

  remove: async (slug) => {
    try {
      await axios.delete(`${API}/me/favorites/${slug}`);
      set({ favorites: get().favorites.filter((f) => f.channel_slug !== slug) });
      return { ok: true };
    } catch {
      return { ok: false };
    }
  },

  isFavorite: (slug) => get().favorites.some((f) => f.channel_slug === slug),
}));


// One-shot helpers ─────────────────────────────────────────────────
export async function fetchAutoplaySuggestion() {
  try {
    const { data } = await axios.get(`${API}/me/autoplay/suggestion`);
    return data;
  } catch {
    return null;
  }
}


export async function fetchTopChannelRec() {
  try {
    const { data } = await axios.get(`${API}/me/recommendations/top-channel`);
    return data?.channel === null ? null : data;
  } catch {
    return null;
  }
}


export async function fetchTopGameRec() {
  try {
    const { data } = await axios.get(`${API}/me/recommendations/top-game`);
    return data?.game === null ? null : data;
  } catch {
    return null;
  }
}
