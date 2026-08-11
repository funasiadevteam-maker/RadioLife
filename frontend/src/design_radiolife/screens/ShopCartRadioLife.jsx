// RadioLife Shop — multi-merchant cart, splits into one order per venue at checkout (web).
import React from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ShoppingBag, Minus, Plus, Trash2, Store } from "lucide-react";
import { useProductCart } from "../useProductCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ShopCartRadioLife() {
  const navigate = useNavigate();
  const { groups, inc, dec, setFulfillment, setAddress, removeGroup } = useProductCart();
  const entries = Object.entries(groups);
  const grand = entries.reduce((s, [, g]) => s + g.items.reduce((m, i) => m + i.price_cents * i.qty, 0), 0);

  const goCheckout = () => {
    const missing = entries.some(([, g]) => g.fulfillment === "delivery" && !(g.address || "").trim());
    if (missing) { alert("Add a delivery address for each delivery order"); return; }
    navigate("/shop/checkout/cart");
  };

  return (
    <div className="pb-40" data-testid="rl-shop-cart-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="cart-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Your Cart</h1>
      </div>

      {!entries.length ? (
        <div className="text-center text-slate-500 mt-16" data-testid="cart-empty">
          <ShoppingBag size={44} className="mx-auto text-slate-300" /><p className="mt-3 font-semibold">Your cart is empty.</p>
          <button onClick={() => navigate("/shop")} className="mt-5 bg-orange-600 text-white font-black rounded-full px-6 py-2.5">Browse shops</button>
        </div>
      ) : (
        <div className="px-4 space-y-4">
          {entries.map(([bizId, g]) => {
            const sub = g.items.reduce((m, i) => m + i.price_cents * i.qty, 0);
            return (
              <div key={bizId} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`cart-group-${bizId}`}>
                <div className="flex items-center justify-between">
                  <div className="font-black text-slate-900 flex items-center gap-1.5"><Store size={16} className="text-orange-600" />{g.business_name}</div>
                  <button onClick={() => removeGroup(bizId)} data-testid={`cart-remove-group-${bizId}`} className="text-rose-600"><Trash2 size={16} /></button>
                </div>
                <div className="mt-2 space-y-1.5">
                  {g.items.map((i) => (
                    <div key={i.key} className="flex items-center justify-between text-sm" data-testid={`cart-item-${bizId}-${i.key}`}>
                      <span className="truncate text-slate-700 font-semibold">{i.name}{i.variant_label ? ` (${i.variant_label})` : ""}</span>
                      <span className="flex items-center gap-2">
                        <button onClick={() => dec(bizId, i.key)} className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center"><Minus size={12} /></button>
                        <span className="font-black w-4 text-center">{i.qty}</span>
                        <button onClick={() => inc(bizId, i.key)} className="w-6 h-6 rounded-full bg-slate-100 flex items-center justify-center"><Plus size={12} /></button>
                        <span className="font-black w-14 text-right">{money(i.price_cents * i.qty)}</span>
                      </span>
                    </div>
                  ))}
                </div>
                <div className="flex gap-2 mt-3">
                  <button onClick={() => setFulfillment(bizId, "pickup")} data-testid={`cart-pickup-${bizId}`} className={`flex-1 py-2 rounded-lg font-black text-sm ${g.fulfillment === "pickup" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"}`}>Pickup</button>
                  <button onClick={() => setFulfillment(bizId, "delivery")} data-testid={`cart-delivery-${bizId}`} className={`flex-1 py-2 rounded-lg font-black text-sm ${g.fulfillment === "delivery" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"}`}>Delivery</button>
                </div>
                {g.fulfillment === "delivery" && (
                  <input value={g.address || ""} onChange={(e) => setAddress(bizId, e.target.value)} placeholder="Delivery address" data-testid={`cart-address-${bizId}`}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm mt-2" />
                )}
                <div className="text-right text-sm font-black text-slate-500 mt-2">Subtotal {money(sub)}</div>
              </div>
            );
          })}

          <div className="fixed bottom-16 left-0 right-0 max-w-3xl mx-auto px-4 py-3 bg-white border-t border-slate-200">
            <button onClick={goCheckout} data-testid="cart-checkout"
              className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-60">
              <ShoppingBag size={16} />Review &amp; Checkout {entries.length > 1 ? `${entries.length} venues` : ""} · {money(grand)}
            </button>
            <p className="text-center text-xs text-slate-400 mt-1.5">Choose gift card &amp; points on the next step · one order per venue</p>
          </div>
        </div>
      )}
    </div>
  );
}
