// Per-user feature personalization (mobile) — which FUUSIC features show on
// Home + how they're ordered. Shared backend with web (/api/social/features),
// so a change on either surface syncs across devices.
import { create } from 'zustand';
import api from '../api/client';

export type FeatureCard = {
  key: string;
  label: string;
  desc: string;
  icon: string;
  to: string;
  mandatory?: boolean;
};

type State = {
  enabled: string[] | null;   // null until loaded → treat everything as on
  catalog: FeatureCard[];
  mandatory: string[];
  defaults: string[];         // city-aware default set from the backend
  homeCity: string | null;
  loaded: boolean;
  loading: boolean;
  bootstrap: () => Promise<void>;
  reload: () => Promise<void>;
  save: (list: string[]) => Promise<void>;
};

async function fetchPrefs(set: (p: Partial<State>) => void) {
  try {
    const { data } = await api.get('/social/features');
    set({
      enabled: data?.enabled || [],
      catalog: data?.catalog || [],
      mandatory: data?.mandatory || [],
      defaults: data?.default || [],
      homeCity: data?.home_city || null,
      loaded: true,
    });
  } catch {
    set({ enabled: [], loaded: true });
  }
}

export const useFeaturePrefs = create<State>((set, get) => ({
  enabled: null,
  catalog: [],
  mandatory: [],
  defaults: [],
  homeCity: null,
  loaded: false,
  loading: false,

  bootstrap: async () => {
    if (get().loading || get().loaded) return;
    set({ loading: true });
    await fetchPrefs(set);
    set({ loading: false });
  },

  reload: async () => {
    set({ loading: true });
    await fetchPrefs(set);
    set({ loading: false });
  },

  save: async (list) => {
    set({ enabled: list });
    try { await api.put('/social/features', { features: list }); } catch {}
  },
}));
