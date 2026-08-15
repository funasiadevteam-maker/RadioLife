// Always-visible store cart panel (web, desktop). Reads the menu cart
// (useShopCart) or product cart (useProductCart), with qty steppers, per-item
// notes, save-for-later, a "make it a meal" combo nudge, clear-all (with undo)
// and a related-items upsell.
import React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShoppingBag, Plus, Minus, Trash2, ArrowRight, Sparkles, Bookmark, Utensils } from "lucide-react";
import { useShopCart } from "../useShopCart";
import { useProductCart } from "../useProductCart";
import { useSavedForLater } from "../useSavedForLater";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

export default function StoreCartPanel({ mode, bizId, bizName, suggestions = [], onAdd, combo }) {
  const navigate = useNavigate();
  const menu = useShopCart();
  const product = useProductCart();
  const saved = useSavedForLater();
  const isFood = mode !== "product";

  let lines = [];
  let subtotal = 0;
  let inc, dec, remove, clearAll, saveForLater, checkoutPath;

  if (mode === "product") {
    const g = product.groups[bizId];
    lines = (g?.items || []).map((i) => ({
      id: i.key, name: i.name, sub: i.variant_label, note: i.note, qty: i.qty, price: i.price_cents, image_url: i.image_url, raw: i,
    }));
    subtotal = lines.reduce((s, i) => s + i.price * i.qty, 0);
    inc = (id) => product.inc(bizId, id);
    dec = (id) => product.dec(bizId, id);
    remove = (id) => product.removeItem(bizId, id);
    saveForLater = (line) => {
      const i = line.raw;
      saved.save(bizId, {
        key: `p:${i.key}`, kind: "product", note: i.note || null,
        product: { product_id: i.product_id, name: i.name, image_url: i.image_url, price_cents: i.price_cents },
        variant: i.variant_label ? { label: i.variant_label, price_cents: i.price_cents } : null,
      });
      product.removeItem(bizId, i.key);
    };
    clearAll = () => {
      const snap = JSON.parse(JSON.stringify(product.groups[bizId] || null));
      product.removeGroup(bizId);
      toast("Cart cleared", { action: { label: "Undo", onClick: () => product.restoreGroup(bizId, snap) } });
    };
    checkoutPath = "/shop/checkout/cart";
  } else {
    const sameBiz = menu.businessId === bizId;
    lines = (sameBiz ? menu.items : []).map((i) => ({
      id: i.line_id, name: i.name, sub: i.option_summary || i.entitlement_label, note: i.note, qty: i.qty, price: i.price_cents, image_url: null, raw: i,
    }));
    subtotal = sameBiz ? menu.subtotal() : 0;
    inc = (id) => menu.inc(id);
    dec = (id) => menu.dec(id);
    remove = (id) => { const l = menu.items.find((x) => x.line_id === id); if (l) for (let k = 0; k < l.qty; k++) menu.dec(id); };
    saveForLater = (line) => {
      const i = line.raw;
      saved.save(bizId, {
        key: `m:${i.line_id}`, kind: "menu", item_id: i.item_id, name: i.name, price_cents: i.price_cents,
        selected_option_ids: i.selected_option_ids || [], option_summary: i.option_summary || null, note: i.note || null,
      });
      remove(i.line_id);
    };
    clearAll = () => {
      const snap = { bizId: menu.businessId, name: menu.businessName, items: JSON.parse(JSON.stringify(menu.items)) };
      menu.clear();
      toast("Cart cleared", { action: { label: "Undo", onClick: () => menu.restore(snap.bizId, snap.name, snap.items) } });
    };
    checkoutPath = "/shop/checkout/menu";
  }

  const savedList = saved.listFor(bizId);
  const moveToCart = (e) => {
    if (e.kind === "product") product.add(bizId, bizName, e.product, e.variant, 1, e.note);
    else menu.addLine(bizId, bizName, { item_id: e.item_id, name: e.name, price_cents: e.price_cents, selected_option_ids: e.selected_option_ids, option_summary: e.option_summary, note: e.note });
    saved.remove(bizId, e.key);
  };

  const count = lines.reduce((n, i) => n + i.qty, 0);
  const upsell = count > 0 ? (suggestions || []).slice(0, 3) : [];
  const showCombo = isFood && count > 0 && combo && combo.applies;

  return (
    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden flex flex-col" data-testid="store-cart-panel" style={{ maxHeight: "calc(100vh - 2rem)" }}>
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-100">
        <ShoppingBag size={18} className="text-orange-600" />
        <span className="font-black text-slate-900">{isFood ? "Your order" : "Cart"}</span>
        {count > 0 && <span className="text-xs font-black bg-orange-600 text-white rounded-full px-2 py-0.5" data-testid="store-cart-count">{count}</span>}
        {count > 0 && (
          <button onClick={clearAll} data-testid="store-cart-clear" className="ml-auto text-xs font-black text-slate-400 hover:text-rose-600 flex items-center gap-1">
            <Trash2 size={13} />Clear
          </button>
        )}
      </div>

      {count === 0 && savedList.length === 0 ? (
        <div className="flex-1 flex flex-col items-center justify-center text-center px-6 py-12" data-testid="store-cart-empty">
          <ShoppingBag size={36} className="text-slate-300" />
          <p className="mt-3 text-sm text-slate-500 font-semibold">Your cart is empty.<br />Tap <span className="text-orange-600 font-black">+</span> to add items.</p>
        </div>
      ) : (
        <>
          <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
            {lines.map((i) => (
              <div key={i.id} className="flex gap-3" data-testid={`store-cart-item-${i.id}`}>
                {i.image_url && <div className="w-14 h-14 rounded-lg bg-slate-100 overflow-hidden shrink-0"><img src={i.image_url} alt={i.name} className="w-full h-full object-cover" /></div>}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-bold text-slate-900 line-clamp-2">{i.name}</div>
                  {i.sub && <div className="text-xs text-slate-400 line-clamp-1">{i.sub}</div>}
                  {i.note && <div className="text-[11px] text-orange-600 font-semibold line-clamp-1 mt-0.5" data-testid={`store-cart-note-${i.id}`}>“{i.note}”</div>}
                  <div className="flex items-center justify-between mt-1.5">
                    <div className="flex items-center gap-2 bg-orange-50 rounded-full px-1 py-0.5">
                      <button onClick={() => dec(i.id)} data-testid={`store-cart-dec-${i.id}`} className="w-6 h-6 rounded-full bg-white flex items-center justify-center"><Minus size={12} className="text-orange-600" /></button>
                      <span className="font-black text-sm w-4 text-center text-slate-900">{i.qty}</span>
                      <button onClick={() => inc(i.id)} data-testid={`store-cart-inc-${i.id}`} className="w-6 h-6 rounded-full bg-white flex items-center justify-center"><Plus size={12} className="text-orange-600" /></button>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-black text-slate-900">{money(i.price * i.qty)}</span>
                      <button onClick={() => saveForLater(i)} data-testid={`store-cart-save-${i.id}`} title="Save for later" className="text-slate-300 hover:text-orange-600"><Bookmark size={15} /></button>
                      <button onClick={() => remove(i.id)} data-testid={`store-cart-remove-${i.id}`} title="Remove" className="text-slate-300 hover:text-rose-600"><Trash2 size={15} /></button>
                    </div>
                  </div>
                </div>
              </div>
            ))}

            {/* Saved for later */}
            {savedList.length > 0 && (
              <div className="pt-2 border-t border-dashed border-slate-200" data-testid="store-saved-list">
                <div className="flex items-center gap-1.5 text-xs font-black text-slate-500 mb-2"><Bookmark size={13} className="text-orange-500" />Saved for later</div>
                <div className="space-y-2">
                  {savedList.map((e) => (
                    <div key={e.key} className="flex items-center gap-2" data-testid={`store-saved-${e.key}`}>
                      <div className="flex-1 min-w-0">
                        <div className="text-xs font-bold text-slate-700 line-clamp-1">{e.name}{e.variant?.label ? ` · ${e.variant.label}` : ""}</div>
                        <div className="text-[11px] font-black text-slate-400">{money((e.variant?.price_cents ?? e.price_cents) || 0)}</div>
                      </div>
                      <button onClick={() => moveToCart(e)} data-testid={`store-saved-add-${e.key}`} className="text-[11px] font-black text-orange-600 hover:text-orange-700 flex items-center gap-0.5"><Plus size={13} />Move to cart</button>
                      <button onClick={() => saved.remove(bizId, e.key)} data-testid={`store-saved-remove-${e.key}`} className="text-slate-300 hover:text-rose-600"><Trash2 size={13} /></button>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Combo nudge */}
          {showCombo && (
            <div className="border-t border-slate-100 px-4 py-2.5 flex items-center gap-2 bg-green-50" data-testid="store-combo-nudge">
              <Utensils size={15} className="text-green-600" />
              <span className="text-xs font-black text-green-800">Meal combo applied — save ~{money(combo.saveCents)} at checkout 🎉</span>
            </div>
          )}

          {/* Related upsell */}
          {upsell.length > 0 && (
            <div className="border-t border-slate-100 px-3 py-3" data-testid="store-cart-upsell">
              <div className="flex items-center gap-1.5 text-xs font-black text-slate-500 mb-2"><Sparkles size={13} className="text-amber-500" />Add a little extra</div>
              <div className="space-y-2">
                {upsell.map((u) => (
                  <div key={u.id} className="flex items-center gap-2" data-testid={`store-upsell-${u.id}`}>
                    <div className="w-9 h-9 rounded-lg bg-slate-100 overflow-hidden shrink-0">
                      {u.image_url && <img src={u.image_url} alt={u.name} className="w-full h-full object-cover" />}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-bold text-slate-900 line-clamp-1">{u.name}</div>
                      <div className="text-[11px] font-black text-slate-500">{money(u.price_cents)}</div>
                    </div>
                    <button onClick={() => onAdd && onAdd(u)} data-testid={`store-upsell-add-${u.id}`}
                      className="w-7 h-7 rounded-full bg-orange-600 text-white flex items-center justify-center shrink-0 hover:bg-orange-700"><Plus size={15} /></button>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="border-t border-slate-100 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-slate-500 font-semibold text-sm">Subtotal</span>
              <span className="text-lg font-black text-slate-900" data-testid="store-cart-subtotal">{money(subtotal)}</span>
            </div>
            <button onClick={() => navigate(checkoutPath)} disabled={count === 0} data-testid="store-cart-checkout"
              className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-40">
              Checkout <ArrowRight size={16} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
