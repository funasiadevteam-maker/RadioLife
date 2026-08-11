// RadioLife Shop — food (pickup) checkout: choose gift card + BigPoints,
// see the live total, then pay by card (Stripe) or points/gift-card cover.
import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Coins, Gift, CreditCard, Check, ShoppingBag } from "lucide-react";
import { API } from "@/AuthContext";
import { useShopCart } from "../useShopCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function CheckoutMenuRadioLife() {
  const navigate = useNavigate();
  const cart = useShopCart();
  const [useGift, setUseGift] = useState(true);
  const [redeemPoints, setRedeemPoints] = useState(0);
  const [quote, setQuote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const items = useMemo(
    () => cart.items.map((i) => ({ item_id: i.item_id, qty: i.qty })), [cart.items]);

  const refresh = useCallback(async (rp) => {
    if (!cart.businessId || !items.length) return;
    try {
      const r = await axios.post(`${API}/shop/orders/quote`, {
        business_id: cart.businessId, items, use_gift_card: useGift, redeem_points: rp,
      });
      setQuote(r.data);
      if (r.data.redeemed_points !== rp) setRedeemPoints(r.data.redeemed_points);
    } catch (e) { setError(e?.response?.data?.detail?.code || "Could not price order"); }
  }, [cart.businessId, items, useGift]);

  useEffect(() => { refresh(redeemPoints); /* eslint-disable-next-line */ }, [useGift]);
  useEffect(() => { refresh(0); /* eslint-disable-next-line */ }, []);

  if (!cart.businessId || !cart.items.length) {
    return (
      <div className="px-4 pt-16 text-center" data-testid="rl-checkout-menu-empty">
        <ShoppingBag size={40} className="mx-auto text-slate-300" />
        <p className="text-slate-500 mt-3">Your cart is empty.</p>
        <button onClick={() => navigate("/shop")} className="mt-4 bg-orange-600 text-white font-black rounded-full px-6 py-2.5">Browse shops</button>
      </div>
    );
  }

  const pay = async () => {
    setBusy(true); setError(null);
    try {
      const r = await axios.post(`${API}/shop/orders/checkout`, {
        business_id: cart.businessId, items,
        use_gift_card: useGift, redeem_points: redeemPoints,
        origin_url: window.location.origin,
      });
      cart.clear();
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      navigate("/shop/orders");
    } catch (e) {
      setError(e?.response?.data?.detail?.code || "Checkout failed");
      setBusy(false);
    }
  };

  const total = quote ? quote.total_cents : cart.subtotal();
  const maxPts = quote ? quote.max_redeemable_points : 0;
  const paysByCard = total > 0;

  return (
    <div className="pb-40" data-testid="rl-checkout-menu-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="checkout-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Checkout</h1>
      </div>

      <div className="px-4 mt-4 space-y-4">
        {/* Order summary */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4">
          <div className="font-black text-slate-900 mb-2">{cart.businessName}</div>
          {cart.items.map((i) => (
            <div key={i.item_id} className="flex justify-between text-sm text-slate-600 py-0.5">
              <span>{i.qty}× {i.name}</span><span className="font-bold text-slate-900">{money(i.price_cents * i.qty)}</span>
            </div>
          ))}
          <div className="border-t border-slate-100 mt-2 pt-2 flex justify-between text-sm">
            <span className="text-slate-500">Subtotal</span>
            <span className="font-black text-slate-900">{money(quote ? quote.subtotal_cents : cart.subtotal())}</span>
          </div>
        </div>

        {/* Gift card */}
        {quote && quote.gift_available_cents > 0 && (
          <button onClick={() => setUseGift((v) => !v)} data-testid="checkout-giftcard-toggle"
            className="w-full flex items-center gap-3 bg-white border border-slate-200 rounded-2xl p-4 text-left">
            <span className={`w-5 h-5 rounded-md flex items-center justify-center ${useGift ? "bg-green-600" : "bg-slate-200"}`}>
              {useGift && <Check size={14} className="text-white" />}
            </span>
            <Gift size={18} className="text-green-600" />
            <div className="flex-1">
              <div className="font-bold text-slate-900 text-sm">Apply gift card</div>
              <div className="text-xs text-slate-500">{money(quote.gift_available_cents)} available · applies {money(quote.gift_applied_cents)}</div>
            </div>
          </button>
        )}

        {/* Points redemption */}
        {quote && quote.points_balance > 0 && (
          <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="checkout-points">
            <div className="flex items-center gap-2 mb-1">
              <Coins size={18} className="text-orange-600" />
              <div className="font-bold text-slate-900 text-sm">Use BigPoints</div>
              <div className="ml-auto text-xs text-slate-500">Balance: {quote.points_balance}</div>
            </div>
            <input type="range" min={0} max={maxPts} step={100} value={redeemPoints} data-testid="checkout-points-slider"
              onChange={(e) => { const v = Number(e.target.value); setRedeemPoints(v); refresh(v); }}
              className="w-full accent-orange-600" disabled={maxPts <= 0} />
            <div className="flex justify-between text-xs mt-1">
              <span className="text-slate-500">{redeemPoints} pts</span>
              <span className="font-bold text-orange-600">−{money(quote.points_discount_cents)}</span>
            </div>
          </div>
        )}

        {/* Total */}
        <div className="bg-slate-900 rounded-2xl p-4 flex items-center justify-between">
          <span className="text-white/70 font-bold">Total to pay</span>
          <span className="text-white text-2xl font-black" data-testid="checkout-total">{money(total)}</span>
        </div>

        {quote && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Coins size={13} className="text-amber-500" />You'll earn {quote.points_to_award} BigPoints on this order.
          </div>
        )}
        {error && <div className="text-rose-600 text-sm font-semibold" data-testid="checkout-error">{error}</div>}

        <button onClick={pay} disabled={busy} data-testid="checkout-pay"
          className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-4 disabled:opacity-60">
          {busy ? "Processing…" : paysByCard
            ? <><CreditCard size={18} />Pay {money(total)} by card</>
            : <><Check size={18} />Place order · {money(0)}</>}
        </button>
      </div>
    </div>
  );
}
