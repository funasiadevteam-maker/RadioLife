// Single-merchant Shop cart (web) — Marketplace Phase B + entitlement engine.
// Each line can carry option selections + an applied membership entitlement,
// so the same item with different options/entitlement is a distinct line.
import { create } from "zustand";

const lineKey = (itemId, optionIds, entId) =>
  `${itemId}::${[...(optionIds || [])].sort().join(",")}::${entId || ""}`;

export const useShopCart = create((set, get) => ({
  businessId: null,
  businessName: null,
  fulfillment: "pickup",   // "pickup" | "delivery" (UI/display only)
  pickupTime: "now",       // "now" | "+15" | "+30" | "+45"
  setFulfillment: (f) => set({ fulfillment: f }),
  setPickupTime: (t) => set({ pickupTime: t }),
  // {line_id, item_id, name, price_cents(unit, incl options), qty,
  //  selected_option_ids, option_summary, apply_entitlement_id, entitlement_label}
  items: [],
  addLine: (bizId, bizName, line) => set((st) => {
    let { items, businessId, businessName } = st;
    if (businessId !== bizId) { items = []; businessId = bizId; businessName = bizName; }
    const lid = lineKey(line.item_id, line.selected_option_ids, line.apply_entitlement_id);
    const ex = items.find((i) => i.line_id === lid);
    items = ex
      ? items.map((i) => (i.line_id === lid ? { ...i, qty: i.qty + (line.qty || 1) } : i))
      : [...items, { qty: 1, selected_option_ids: [], ...line, line_id: lid }];
    return { items, businessId, businessName };
  }),
  add: (bizId, bizName, item) => get().addLine(bizId, bizName, {
    item_id: item.item_id, name: item.name, price_cents: item.price_cents,
    selected_option_ids: [], option_summary: null, apply_entitlement_id: null,
  }),
  inc: (lid) => set((st) => ({ items: st.items.map((i) => (i.line_id === lid ? { ...i, qty: i.qty + 1 } : i)) })),
  dec: (lid) => set((st) => {
    const items = st.items.map((i) => (i.line_id === lid ? { ...i, qty: i.qty - 1 } : i)).filter((i) => i.qty > 0);
    return items.length ? { items } : { items: [], businessId: null, businessName: null };
  }),
  clear: () => set({ items: [], businessId: null, businessName: null }),
  replaceWith: (bizId, bizName, items) => set({
    businessId: bizId, businessName: bizName,
    items: (items || []).map((i) => ({
      line_id: lineKey(i.item_id, [], null), item_id: i.item_id, name: i.name,
      price_cents: i.price_cents, qty: i.qty || 1, selected_option_ids: [],
      option_summary: null, apply_entitlement_id: null,
    })),
  }),
  count: () => get().items.reduce((n, i) => n + i.qty, 0),
  subtotal: () => get().items.reduce((n, i) => n + i.price_cents * i.qty, 0),
}));
