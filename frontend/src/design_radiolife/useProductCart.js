// Multi-merchant Shop product cart (web) — Marketplace Phase E.
// Items grouped by business; checkout splits into one order per venue.
import { create } from "zustand";
import { persist } from "zustand/middleware";

const keyOf = (pid, v) => (v ? `${pid}::${v}` : pid);

export const useProductCart = create(persist((set, get) => ({
  groups: {}, // { [businessId]: { business_name, fulfillment, address, items: [{key, product_id, variant_label, name, price_cents, qty}] } }

  add: (bizId, bizName, product, variant) => set((st) => {
    const groups = { ...st.groups };
    const g = groups[bizId] || { business_name: bizName, fulfillment: "pickup", address: "", items: [] };
    const key = keyOf(product.product_id, variant?.label);
    const price = variant && variant.price_cents > 0 ? variant.price_cents : product.price_cents;
    const items = [...g.items];
    const ex = items.find((i) => i.key === key);
    if (ex) ex.qty += 1;
    else items.push({ key, product_id: product.product_id, variant_label: variant?.label || null, name: product.name, price_cents: price, qty: 1 });
    groups[bizId] = { ...g, business_name: bizName, items };
    return { groups };
  }),
  inc: (bizId, key) => set((st) => {
    const g = st.groups[bizId]; if (!g) return {};
    return { groups: { ...st.groups, [bizId]: { ...g, items: g.items.map((i) => i.key === key ? { ...i, qty: i.qty + 1 } : i) } } };
  }),
  dec: (bizId, key) => set((st) => {
    const g = st.groups[bizId]; if (!g) return {};
    const items = g.items.map((i) => i.key === key ? { ...i, qty: i.qty - 1 } : i).filter((i) => i.qty > 0);
    const groups = { ...st.groups };
    if (items.length) groups[bizId] = { ...g, items }; else delete groups[bizId];
    return { groups };
  }),
  setFulfillment: (bizId, fulfillment) => set((st) => st.groups[bizId] ? ({ groups: { ...st.groups, [bizId]: { ...st.groups[bizId], fulfillment } } }) : {}),
  setAddress: (bizId, address) => set((st) => st.groups[bizId] ? ({ groups: { ...st.groups, [bizId]: { ...st.groups[bizId], address } } }) : {}),
  removeGroup: (bizId) => set((st) => { const groups = { ...st.groups }; delete groups[bizId]; return { groups }; }),
  clear: () => set({ groups: {} }),

  count: () => Object.values(get().groups).reduce((n, g) => n + g.items.reduce((m, i) => m + i.qty, 0), 0),
  venueCount: () => Object.keys(get().groups).length,
}), { name: "rl-product-cart" }));
