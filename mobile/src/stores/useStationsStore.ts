/**
 * useStationsStore — persisted favorites + recently played radio stations.
 * Backed by AsyncStorage so the lists survive app restarts.
 */
import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

export interface SavedStation {
  id: string;
  name: string;
  favicon?: string | null;
  logo_url?: string | null;
  country?: string | null;
  language?: string | null;
  source?: string;
  is_flagship?: boolean;
  stream_url?: string | null;
}

const FAV_KEY = 'bigfm_fav_stations';
const REC_KEY = 'bigfm_recent_stations';

interface StationsState {
  favorites: SavedStation[];
  recents: SavedStation[];
  loaded: boolean;
  load: () => Promise<void>;
  isFavorite: (id: string) => boolean;
  toggleFavorite: (st: SavedStation) => void;
  addRecent: (st: SavedStation) => void;
}

export const useStationsStore = create<StationsState>((set, get) => ({
  favorites: [],
  recents: [],
  loaded: false,

  load: async () => {
    try {
      const [f, r] = await Promise.all([
        AsyncStorage.getItem(FAV_KEY),
        AsyncStorage.getItem(REC_KEY),
      ]);
      set({
        favorites: f ? JSON.parse(f) : [],
        recents: r ? JSON.parse(r) : [],
        loaded: true,
      });
    } catch {
      set({ loaded: true });
    }
  },

  isFavorite: (id) => get().favorites.some((s) => s.id === id),

  toggleFavorite: (st) => {
    const fav = get().favorites;
    const exists = fav.some((s) => s.id === st.id);
    const next = exists ? fav.filter((s) => s.id !== st.id) : [st, ...fav].slice(0, 100);
    set({ favorites: next });
    AsyncStorage.setItem(FAV_KEY, JSON.stringify(next)).catch(() => {});
  },

  addRecent: (st) => {
    const rec = get().recents.filter((s) => s.id !== st.id);
    const next = [st, ...rec].slice(0, 30);
    set({ recents: next });
    AsyncStorage.setItem(REC_KEY, JSON.stringify(next)).catch(() => {});
  },
}));
