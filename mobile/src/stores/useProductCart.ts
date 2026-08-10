import { create } from 'zustand';

/* ── Multi-merchant Shop product cart (Marketplace Phase E) ──
   Items grouped by business; checkout splits into one order per venue. */

export type ProductCartItem = {
  key: string;
  product_id: string;
  variant_label: string | null;
  name: string;
  price_cents: number;
  qty: number;
};

export type ProductCartGroup = {
  business_name: string;
  fulfillment: string; // pickup | delivery
  address: string;
  delivery_cfg: { pickup?: boolean; delivery?: boolean; fee_cents?: number; free_over_cents?: number };
  items: ProductCartItem[];
};

type ProductCartState = {
  groups: Record<string, ProductCartGroup>;
  add: (bizId: string, bizName: string, product: any, variant: any, deliveryCfg?: any) => void;
  inc: (bizId: string, key: string) => void;
  dec: (bizId: string, key: string) => void;
  setFulfillment: (bizId: string, fulfillment: string) => void;
  setAddress: (bizId: string, address: string) => void;
  removeGroup: (bizId: string) => void;
  clear: () => void;
  count: () => number;
  venueCount: () => number;
};

const keyOf = (pid: string, v?: string | null) => (v ? `${pid}::${v}` : pid);

export const useProductCart = create<ProductCartState>((set, get) => ({
  groups: {},

  add: (bizId, bizName, product, variant, deliveryCfg) => set((st) => {
    const groups = { ...st.groups };
    const g = groups[bizId] || { business_name: bizName, fulfillment: 'pickup', address: '', delivery_cfg: deliveryCfg || { pickup: true }, items: [] };
    const key = keyOf(product.product_id, variant?.label);
    const price = variant && variant.price_cents > 0 ? variant.price_cents : product.price_cents;
    const items = [...g.items];
    const ex = items.find((i) => i.key === key);
    if (ex) ex.qty += 1;
    else items.push({ key, product_id: product.product_id, variant_label: variant?.label || null, name: product.name, price_cents: price, qty: 1 });
    groups[bizId] = { ...g, business_name: bizName, delivery_cfg: deliveryCfg || g.delivery_cfg, items };
    return { groups };
  }),

  inc: (bizId, key) => set((st) => {
    const g = st.groups[bizId]; if (!g) return {} as any;
    return { groups: { ...st.groups, [bizId]: { ...g, items: g.items.map((i) => i.key === key ? { ...i, qty: i.qty + 1 } : i) } } };
  }),

  dec: (bizId, key) => set((st) => {
    const g = st.groups[bizId]; if (!g) return {} as any;
    const items = g.items.map((i) => i.key === key ? { ...i, qty: i.qty - 1 } : i).filter((i) => i.qty > 0);
    const groups = { ...st.groups };
    if (items.length) groups[bizId] = { ...g, items }; else delete groups[bizId];
    return { groups };
  }),

  setFulfillment: (bizId, fulfillment) => set((st) => st.groups[bizId] ? ({ groups: { ...st.groups, [bizId]: { ...st.groups[bizId], fulfillment } } }) : {} as any),
  setAddress: (bizId, address) => set((st) => st.groups[bizId] ? ({ groups: { ...st.groups, [bizId]: { ...st.groups[bizId], address } } }) : {} as any),
  removeGroup: (bizId) => set((st) => { const groups = { ...st.groups }; delete groups[bizId]; return { groups }; }),
  clear: () => set({ groups: {} }),

  count: () => Object.values(get().groups).reduce((n, g) => n + g.items.reduce((m, i) => m + i.qty, 0), 0),
  venueCount: () => Object.keys(get().groups).length,
}));
