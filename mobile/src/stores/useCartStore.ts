import { create } from 'zustand';
import AsyncStorage from '@react-native-async-storage/async-storage';

/* ── Single-merchant Shop cart (Marketplace Phase B + entitlement engine) ──
   One restaurant per order. Each line can carry option selections + an applied
   membership entitlement, so the same item with different options is its own line.
   Persisted to AsyncStorage so the cart survives app reload / background.
   NOTE: persistence is done MANUALLY (hydrate + subscribe) rather than via
   zustand/middleware — that middleware ships `import.meta`, which crashes the
   Expo web bundle (metro.config is protected and can't transpile it). */

export type CartItem = {
  line_id: string;
  item_id: string;
  name: string;
  price_cents: number; // unit price incl. selected options
  qty: number;
  selected_option_ids: string[];
  option_summary?: string | null;
  apply_entitlement_id?: string | null;
  entitlement_label?: string | null;
};

const lineKey = (itemId: string, optionIds: string[], entId?: string | null) =>
  `${itemId}::${[...(optionIds || [])].sort().join(',')}::${entId || ''}`;

type LineInput = {
  item_id: string; name: string; price_cents: number; qty?: number;
  selected_option_ids?: string[]; option_summary?: string | null;
  apply_entitlement_id?: string | null; entitlement_label?: string | null;
};

type CartState = {
  businessId: string | null;
  businessName: string | null;
  fulfillment: string;
  pickupTime: string;
  setFulfillment: (f: string) => void;
  setPickupTime: (t: string) => void;
  items: CartItem[];
  addLine: (bizId: string, bizName: string, line: LineInput) => void;
  add: (bizId: string, bizName: string, item: { item_id: string; name: string; price_cents: number }) => void;
  inc: (lineId: string) => void;
  dec: (lineId: string) => void;
  remove: (lineId: string) => void;
  clear: () => void;
  replaceWith: (bizId: string, bizName: string, items: { item_id: string; name: string; price_cents: number; qty?: number }[]) => void;
  count: () => number;
  subtotal: () => number;
  conflicts: (bizId: string) => boolean;
};

export const useCartStore = create<CartState>((set, get) => ({
  businessId: null,
  businessName: null,
  fulfillment: 'pickup',
  pickupTime: 'now',
  setFulfillment: (f) => set({ fulfillment: f }),
  setPickupTime: (t) => set({ pickupTime: t }),
  items: [],
  conflicts: (bizId) => !!get().businessId && get().businessId !== bizId && get().items.length > 0,
  addLine: (bizId, bizName, line) => set((st) => {
    let { items, businessId, businessName } = st;
    if (businessId !== bizId) { items = []; businessId = bizId; businessName = bizName; }
    const lid = lineKey(line.item_id, line.selected_option_ids || [], line.apply_entitlement_id);
    const ex = items.find((i) => i.line_id === lid);
    items = ex
      ? items.map((i) => (i.line_id === lid ? { ...i, qty: i.qty + (line.qty || 1) } : i))
      : [...items, {
          line_id: lid, item_id: line.item_id, name: line.name, price_cents: line.price_cents,
          qty: line.qty || 1, selected_option_ids: line.selected_option_ids || [],
          option_summary: line.option_summary || null,
          apply_entitlement_id: line.apply_entitlement_id || null,
          entitlement_label: line.entitlement_label || null,
        }];
    return { items, businessId, businessName };
  }),
  add: (bizId, bizName, item) => get().addLine(bizId, bizName, { ...item, selected_option_ids: [] }),
  inc: (lineId) => set((st) => ({ items: st.items.map((i) => (i.line_id === lineId ? { ...i, qty: i.qty + 1 } : i)) })),
  dec: (lineId) => set((st) => {
    const items = st.items.map((i) => (i.line_id === lineId ? { ...i, qty: i.qty - 1 } : i)).filter((i) => i.qty > 0);
    return items.length ? { items } : { items: [], businessId: null, businessName: null };
  }),
  remove: (lineId) => set((st) => {
    const items = st.items.filter((i) => i.line_id !== lineId);
    return items.length ? { items } : { items: [], businessId: null, businessName: null };
  }),
  clear: () => set({ items: [], businessId: null, businessName: null }),
  replaceWith: (bizId, bizName, items) => set({
    businessId: bizId, businessName: bizName,
    items: (items || []).map((i) => ({
      line_id: lineKey(i.item_id, [], null), item_id: i.item_id, name: i.name,
      price_cents: i.price_cents, qty: i.qty || 1, selected_option_ids: [],
      option_summary: null, apply_entitlement_id: null, entitlement_label: null,
    })),
  }),
  count: () => get().items.reduce((n, i) => n + i.qty, 0),
  subtotal: () => get().items.reduce((n, i) => n + i.price_cents * i.qty, 0),
}));

/* ── Manual AsyncStorage persistence (no zustand/middleware) ── */
const CART_STORAGE_KEY = 'radiolife-cart';

AsyncStorage.getItem(CART_STORAGE_KEY)
  .then((raw) => {
    if (!raw) return;
    const d = JSON.parse(raw);
    useCartStore.setState({
      items: Array.isArray(d.items) ? d.items : [],
      businessId: d.businessId ?? null,
      businessName: d.businessName ?? null,
      fulfillment: d.fulfillment === 'delivery' ? 'delivery' : 'pickup',
      pickupTime: d.pickupTime ?? 'now',
    });
  })
  .catch(() => { /* first run / bad data */ });

useCartStore.subscribe((s) => {
  AsyncStorage.setItem(CART_STORAGE_KEY, JSON.stringify({
    items: s.items, businessId: s.businessId, businessName: s.businessName,
    fulfillment: s.fulfillment, pickupTime: s.pickupTime,
  })).catch(() => { /* ignore */ });
});
