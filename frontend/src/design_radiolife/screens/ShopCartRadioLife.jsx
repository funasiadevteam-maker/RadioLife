// RadioLife Shop — Amazon-style cart (web). Line items w/ thumbnails + qty
// steppers + remove, per-venue pickup/delivery, right-rail order summary.
// Splits into one order per venue at checkout.
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ChevronLeft, ShoppingBag, Minus, Plus, Trash2, Store, ArrowRight } from "lucide-react";
import { useProductCart } from "../useProductCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ShopCartRadioLife() {
  const navigate = useNavigate();
  const { groups, inc, dec, removeItem, setFulfillment, setAddress, removeGroup } = useProductCart();
  const entries = Object.entries(groups);
  const [err, setErr] = useState("");
  const totalItems = entries.reduce((n, [, g]) => n + g.items.reduce((m, i) => m + i.qty, 0), 0);
  const grand = entries.reduce((s, [, g]) => s + g.items.reduce((m, i) => m + i.price_cents * i.qty, 0), 0);

  const goCheckout = () => {
    const missing = entries.some(([, g]) => g.fulfillment === "delivery" && !(g.address || "").trim());
    if (missing) { setErr("Add a delivery address for each delivery order."); return; }
    navigate("/shop/checkout/cart");
  };

  if (!entries.length) return (
    <div className="pb-24" data-testid="rl-shop-cart-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="cart-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Your Cart</h1>
      </div>
      <div className="text-center text-slate-500 mt-16" data-testid="cart-empty">
        <ShoppingBag size={44} className="mx-auto text-slate-300" /><p className="mt-3 font-semibold">Your cart is empty.</p>
        <button onClick={() => navigate("/shop")} className="mt-5 bg-orange-600 text-white font-black rounded-full px-6 py-2.5">Browse shops</button>
      </div>
    </div>
  );

  return (
    <div className="pb-40" data-testid="rl-shop-cart-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="cart-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">Your Cart</h1>
        <span className="text-sm font-bold text-slate-400">{totalItems} item{totalItems > 1 ? "s" : ""}</span>
      </div>

      <div className="px-4 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Items */}
        <div className="lg:col-span-2 space-y-4">
          {entries.map(([bizId, g]) => {
            const sub = g.items.reduce((m, i) => m + i.price_cents * i.qty, 0);
            return (
              <div key={bizId} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`cart-group-${bizId}`}>
                <div className="flex items-center justify-between">
                  <div className="font-black text-slate-900 flex items-center gap-1.5"><Store size={16} className="text-orange-600" />{g.business_name}</div>
                  <button onClick={() => removeGroup(bizId)} data-testid={`cart-remove-group-${bizId}`} className="text-slate-300 hover:text-rose-600"><Trash2 size={16} /></button>
                </div>

                <div className="mt-3 space-y-3">
                  {g.items.map((i) => (
                    <div key={i.key} className="flex gap-3" data-testid={`cart-item-${bizId}-${i.key}`}>
                      <div className="w-16 h-16 rounded-lg bg-slate-100 overflow-hidden shrink-0">
                        {i.image_url && <img src={i.image_url} alt={i.name} className="w-full h-full object-cover" />}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-bold text-slate-900 line-clamp-2">{i.name}</div>
                        {i.variant_label && <div className="text-xs text-slate-400">{i.variant_label}</div>}
                        <div className="flex items-center justify-between mt-1.5">
                          <div className="flex items-center gap-2 bg-orange-50 rounded-full px-1 py-0.5">
                            <button onClick={() => dec(bizId, i.key)} data-testid={`cart-dec-${bizId}-${i.key}`} className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Minus size={13} className="text-orange-600" /></button>
                            <span className="font-black text-sm w-5 text-center text-slate-900">{i.qty}</span>
                            <button onClick={() => inc(bizId, i.key)} data-testid={`cart-inc-${bizId}-${i.key}`} className="w-7 h-7 rounded-full bg-white flex items-center justify-center"><Plus size={13} className="text-orange-600" /></button>
                          </div>
                          <div className="flex items-center gap-3">
                            <span className="font-black text-slate-900">{money(i.price_cents * i.qty)}</span>
                            <button onClick={() => removeItem(bizId, i.key)} data-testid={`cart-remove-${bizId}-${i.key}`} className="text-slate-300 hover:text-rose-600"><Trash2 size={15} /></button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="flex gap-2 mt-4">
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
        </div>

        {/* Order summary */}
        <div className="lg:sticky lg:top-4 self-start">
          <div className="bg-white border border-slate-200 rounded-2xl p-4">
            <div className="font-black text-slate-900 mb-3">Order summary</div>
            <div className="flex justify-between text-sm mb-1"><span className="text-slate-500">Items ({totalItems})</span><span className="font-bold text-slate-900">{money(grand)}</span></div>
            <div className="flex justify-between text-sm mb-3"><span className="text-slate-500">Gift card / points / coupon</span><span className="text-slate-400">Next step</span></div>
            <div className="border-t border-slate-100 pt-3 flex justify-between items-center">
              <span className="font-black text-slate-900">Subtotal</span>
              <span className="text-xl font-black text-slate-900" data-testid="cart-grand">{money(grand)}</span>
            </div>
            {err && <p className="text-rose-600 text-xs font-bold mt-2" data-testid="cart-error">{err}</p>}
            <button onClick={goCheckout} data-testid="cart-checkout"
              className="w-full mt-3 flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3">
              Proceed to checkout <ArrowRight size={16} />
            </button>
            <p className="text-center text-[11px] text-slate-400 mt-2">One order per venue · gift card &amp; points applied at checkout</p>
          </div>
        </div>
      </div>
    </div>
  );
}
