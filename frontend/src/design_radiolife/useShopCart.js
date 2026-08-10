// Single-merchant Shop cart (web) — Marketplace Phase B.
import { create } from "zustand";

export const useShopCart = create((set, get) => ({
  businessId: null,
  businessName: null,
  items: [], // {item_id, name, price_cents, qty}
  add: (bizId, bizName, item) => set((st) => {
    let { items, businessId, businessName } = st;
    if (businessId !== bizId) { items = []; businessId = bizId; businessName = bizName; }
    const ex = items.find((i) => i.item_id === item.item_id);
    items = ex
      ? items.map((i) => i.item_id === item.item_id ? { ...i, qty: i.qty + 1 } : i)
      : [...items, { ...item, qty: 1 }];
    return { items, businessId, businessName };
  }),
  inc: (id) => set((st) => ({ items: st.items.map((i) => i.item_id === id ? { ...i, qty: i.qty + 1 } : i) })),
  dec: (id) => set((st) => {
    const items = st.items.map((i) => i.item_id === id ? { ...i, qty: i.qty - 1 } : i).filter((i) => i.qty > 0);
    return items.length ? { items } : { items: [], businessId: null, businessName: null };
  }),
  clear: () => set({ items: [], businessId: null, businessName: null }),
  count: () => get().items.reduce((n, i) => n + i.qty, 0),
  subtotal: () => get().items.reduce((n, i) => n + i.price_cents * i.qty, 0),
}));
