// Always-visible store cart panel (web, desktop). Pinned on the right of the
// store page; reads the menu cart (useShopCart) or the product cart
// (useProductCart) depending on the store type, with qty steppers, per-item
// notes, one-tap "clear all" (with undo) and a related-items upsell.
import React from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ShoppingBag, Plus, Minus, Trash2, ArrowRight, Sparkles } from "lucide-react";
import { useShopCart } from "../useShopCart";
import { useProductCart } from "../useProductCart";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

export default function StoreCartPanel({ mode, bizId, suggestions = [], onAdd }) {
  const navigate = useNavigate();
  const menu = useShopCart();
  const product = useProductCart();

  let lines = [];
  let subtotal = 0;
  let inc, dec, remove, clearAll, checkoutPath;

  if (mode === "product") {
    const g = product.groups[bizId];
    lines = (g?.items || []).map((i) => ({
      id: i.key, name: i.name, sub: i.variant_label, note: i.note, qty: i.qty, price: i.price_cents, image_url: i.image_url,
    }));
    subtotal = lines.reduce((s, i) => s + i.price * i.qty, 0);
    inc = (id) => product.inc(bizId, id);
    dec = (id) => product.dec(bizId, id);
    remove = (id) => product.removeItem(bizId, id);
    clearAll = () => {
      const snapshot = JSON.parse(JSON.stringify(product.groups[bizId] || null));
      product.removeGroup(bizId);
      toast("Cart cleared", { action: { label: "Undo", onClick: () => product.restoreGroup(bizId, snapshot) } });
    };
    checkoutPath = "/shop/checkout/cart";
  } else {
    const sameBiz = menu.businessId === bizId;
    lines = (sameBiz ? menu.items : []).map((i) => ({
      id: i.line_id, name: i.name, sub: i.option_summary || i.entitlement_label, note: i.note, qty: i.qty, price: i.price_cents, image_url: null,
    }));
    subtotal = sameBiz ? menu.subtotal() : 0;
    inc = (id) => menu.inc(id);
    dec = (id) => menu.dec(id);
    remove = (id) => { const l = menu.items.find((x) => x.line_id === id); if (l) for (let k = 0; k < l.qty; k++) menu.dec(id); };
    clearAll = () => {
      const snap = { bizId: menu.businessId, name: menu.businessName, items: JSON.parse(JSON.stringify(menu.items)) };
      menu.clear();
      toast("Cart cleared", { action: { label: "Undo", onClick: () => menu.restore(snap.bizId, snap.name, snap.items) } });
    };
    checkoutPath = "/shop/checkout/menu";
  }

  const count = lines.reduce((n, i) => n + i.qty, 0);
  const isFood = mode !== "product";
  const upsell = count > 0 ? (suggestions || []).slice(0, 3) : [];

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

      {count === 0 ? (
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
                      <button onClick={() => remove(i.id)} data-testid={`store-cart-remove-${i.id}`} className="text-slate-300 hover:text-rose-600"><Trash2 size={15} /></button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

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
            <button onClick={() => navigate(checkoutPath)} data-testid="store-cart-checkout"
              className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3">
              Checkout <ArrowRight size={16} />
            </button>
          </div>
        </>
      )}
    </div>
  );
}
