// Amazon-style slide-in mini-cart drawer (web). Opens on "add to cart";
// shows line items across venues with qty steppers → View cart / Checkout.
import React from "react";
import { useNavigate } from "react-router-dom";
import { X, Plus, Minus, Trash2, ShoppingBag, Store, ArrowRight } from "lucide-react";
import { useProductCart } from "../useProductCart";
import { useMiniCart } from "../useMiniCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ProductMiniCart() {
  const navigate = useNavigate();
  const open = useMiniCart((s) => s.open);
  const hide = useMiniCart((s) => s.hide);
  const { groups, inc, dec, removeItem } = useProductCart();
  const entries = Object.entries(groups);
  const count = entries.reduce((n, [, g]) => n + g.items.reduce((m, i) => m + i.qty, 0), 0);
  const grand = entries.reduce((s, [, g]) => s + g.items.reduce((m, i) => m + i.price_cents * i.qty, 0), 0);

  if (!open) return null;
  const go = (path) => { hide(); navigate(path); };

  return (
    <div className="fixed inset-0 z-[95]" data-testid="product-mini-cart">
      <div className="absolute inset-0 bg-black/40" onClick={hide} data-testid="mini-cart-backdrop" />
      <div className="absolute right-0 top-0 h-full w-full max-w-sm bg-white shadow-2xl flex flex-col animate-[slideIn_.2s_ease-out]"
           style={{ animationName: "none" }}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <div className="flex items-center gap-2 font-black text-slate-900">
            <ShoppingBag size={18} className="text-orange-600" />Cart · {count}
          </div>
          <button onClick={hide} data-testid="mini-cart-close" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><X size={18} /></button>
        </div>

        {count === 0 ? (
          <div className="flex-1 flex flex-col items-center justify-center text-center px-6">
            <ShoppingBag size={40} className="text-slate-300" />
            <p className="mt-3 text-slate-500 font-semibold">Your cart is empty.</p>
          </div>
        ) : (
          <>
            <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
              {entries.map(([bizId, g]) => (
                <div key={bizId}>
                  <div className="flex items-center gap-1.5 text-xs font-black text-slate-500 uppercase tracking-wide mb-2"><Store size={12} className="text-orange-600" />{g.business_name}</div>
                  <div className="space-y-3">
                    {g.items.map((i) => (
                      <div key={i.key} className="flex gap-3" data-testid={`mini-item-${i.key}`}>
                        <div className="w-16 h-16 rounded-lg bg-slate-100 overflow-hidden shrink-0">
                          {i.image_url && <img src={i.image_url} alt={i.name} className="w-full h-full object-cover" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm font-bold text-slate-900 line-clamp-2">{i.name}</div>
                          {i.variant_label && <div className="text-xs text-slate-400">{i.variant_label}</div>}
                          <div className="flex items-center justify-between mt-1.5">
                            <div className="flex items-center gap-2 bg-orange-50 rounded-full px-1 py-0.5">
                              <button onClick={() => dec(bizId, i.key)} data-testid={`mini-dec-${i.key}`} className="w-6 h-6 rounded-full bg-white flex items-center justify-center"><Minus size={12} className="text-orange-600" /></button>
                              <span className="font-black text-sm w-4 text-center text-slate-900">{i.qty}</span>
                              <button onClick={() => inc(bizId, i.key)} data-testid={`mini-inc-${i.key}`} className="w-6 h-6 rounded-full bg-white flex items-center justify-center"><Plus size={12} className="text-orange-600" /></button>
                            </div>
                            <div className="flex items-center gap-2">
                              <span className="text-sm font-black text-slate-900">{money(i.price_cents * i.qty)}</span>
                              <button onClick={() => removeItem(bizId, i.key)} data-testid={`mini-remove-${i.key}`} className="text-slate-300 hover:text-rose-600"><Trash2 size={15} /></button>
                            </div>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            <div className="border-t border-slate-100 p-4 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <span className="text-slate-500 font-semibold">Subtotal</span>
                <span className="text-lg font-black text-slate-900" data-testid="mini-subtotal">{money(grand)}</span>
              </div>
              <button onClick={() => go("/shop/checkout/cart")} data-testid="mini-checkout"
                className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3">
                Proceed to checkout <ArrowRight size={16} />
              </button>
              <button onClick={() => go("/shop/cart")} data-testid="mini-go-cart"
                className="w-full text-center text-sm font-bold text-slate-600 py-1.5">View full cart</button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
