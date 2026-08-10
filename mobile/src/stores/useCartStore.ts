import { create } from 'zustand';

/* ── Single-merchant Shop cart (Marketplace Phase B) ──
   MVP: one restaurant per order. Adding an item from a different business
   replaces the cart (UI warns before switching). */

export type CartItem = { item_id: string; name: string; price_cents: number; qty: number };

type CartState = {
  businessId: string | null;
  businessName: string | null;
  items: CartItem[];
  add: (bizId: string, bizName: string, item: { item_id: string; name: string; price_cents: number }) => void;
  inc: (itemId: string) => void;
  dec: (itemId: string) => void;
  remove: (itemId: string) => void;
  clear: () => void;
  count: () => number;
  subtotal: () => number;
  conflicts: (bizId: string) => boolean;
};

export const useCartStore = create<CartState>((set, get) => ({
  businessId: null,
  businessName: null,
  items: [],
  conflicts: (bizId) => !!get().businessId && get().businessId !== bizId && get().items.length > 0,
  add: (bizId, bizName, item) => set((st) => {
    let items = st.items;
    let businessId = st.businessId;
    let businessName = st.businessName;
    if (businessId !== bizId) {
      items = [];
      businessId = bizId;
      businessName = bizName;
    }
    const existing = items.find((i) => i.item_id === item.item_id);
    if (existing) {
      items = items.map((i) => i.item_id === item.item_id ? { ...i, qty: i.qty + 1 } : i);
    } else {
      items = [...items, { ...item, qty: 1 }];
    }
    return { items, businessId, businessName };
  }),
  inc: (itemId) => set((st) => ({
    items: st.items.map((i) => i.item_id === itemId ? { ...i, qty: i.qty + 1 } : i),
  })),
  dec: (itemId) => set((st) => {
    const items = st.items
      .map((i) => i.item_id === itemId ? { ...i, qty: i.qty - 1 } : i)
      .filter((i) => i.qty > 0);
    return items.length ? { items } : { items: [], businessId: null, businessName: null };
  }),
  remove: (itemId) => set((st) => {
    const items = st.items.filter((i) => i.item_id !== itemId);
    return items.length ? { items } : { items: [], businessId: null, businessName: null };
  }),
  clear: () => set({ items: [], businessId: null, businessName: null }),
  count: () => get().items.reduce((n, i) => n + i.qty, 0),
  subtotal: () => get().items.reduce((n, i) => n + i.price_cents * i.qty, 0),
}));
