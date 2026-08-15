// "Saved for later" list (web) — per-business shelf of items a shopper moved
// out of the cart to buy later. Persisted so it survives navigation/reload.
import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useSavedForLater = create(persist((set, get) => ({
  byBiz: {}, // { [bizId]: [entry] }  entry = {key, kind, ...payload}

  save: (bizId, entry) => set((st) => {
    const list = st.byBiz[bizId] || [];
    if (list.some((e) => e.key === entry.key)) return {};
    return { byBiz: { ...st.byBiz, [bizId]: [...list, entry] } };
  }),
  remove: (bizId, key) => set((st) => {
    const list = (st.byBiz[bizId] || []).filter((e) => e.key !== key);
    const byBiz = { ...st.byBiz };
    if (list.length) byBiz[bizId] = list; else delete byBiz[bizId];
    return { byBiz };
  }),
  listFor: (bizId) => get().byBiz[bizId] || [],
}), { name: "rl-saved-for-later" }));
