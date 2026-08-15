import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

/* ── "Saved for later" (mobile) — per-business shelf of items moved out of the
   cart to buy later. Mirrors the web useSavedForLater. Persisted MANUALLY to
   AsyncStorage (no zustand/middleware — it ships import.meta, which crashes the
   Expo web bundle). */

export type SavedEntry = { key: string; kind: string; [k: string]: any };

type SavedState = {
  byBiz: Record<string, SavedEntry[]>;
  save: (bizId: string, entry: SavedEntry) => void;
  remove: (bizId: string, key: string) => void;
  listFor: (bizId: string) => SavedEntry[];
};

export const useSavedForLater = create<SavedState>((set, get) => ({
  byBiz: {},
  save: (bizId, entry) => set((st) => {
    const list = st.byBiz[bizId] || [];
    if (list.some((e) => e.key === entry.key)) return {} as any;
    return { byBiz: { ...st.byBiz, [bizId]: [...list, entry] } };
  }),
  remove: (bizId, key) => set((st) => {
    const list = (st.byBiz[bizId] || []).filter((e) => e.key !== key);
    const byBiz = { ...st.byBiz };
    if (list.length) byBiz[bizId] = list; else delete byBiz[bizId];
    return { byBiz };
  }),
  listFor: (bizId) => get().byBiz[bizId] || [],
}));

const SAVED_KEY = 'radiolife-saved-for-later';

AsyncStorage.getItem(SAVED_KEY)
  .then((raw) => { if (raw) { try { useSavedForLater.setState({ byBiz: JSON.parse(raw) || {} }); } catch { /* bad data */ } } })
  .catch(() => { /* first run */ });

useSavedForLater.subscribe((s) => {
  AsyncStorage.setItem(SAVED_KEY, JSON.stringify(s.byBiz)).catch(() => { /* ignore */ });
});
