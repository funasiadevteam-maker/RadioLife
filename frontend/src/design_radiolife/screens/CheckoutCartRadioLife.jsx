// RadioLife Shop — multi-venue products checkout: per-venue gift card +
// BigPoints, live totals, one payment for the whole cart.
import React, { useEffect, useMemo, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Coins, Gift, CreditCard, Check, Store, ShoppingBag } from "lucide-react";
import { API } from "@/AuthContext";
import { useProductCart } from "../useProductCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const BRAND = { visa: "Visa", mastercard: "Mastercard", amex: "Amex", discover: "Discover" };

export default function CheckoutCartRadioLife() {
  const navigate = useNavigate();
  const { groups, clear } = useProductCart();
  const entries = useMemo(() => Object.entries(groups), [groups]);
  const [useGift, setUseGift] = useState({});
  const [redeem, setRedeem] = useState({});
  const [quote, setQuote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [cards, setCards] = useState([]);
  const [payWith, setPayWith] = useState("new");

  useEffect(() => {
    axios.get(`${API}/shop/wallet/cards`).then((r) => {
      setCards(r.data.cards || []);
      const def = (r.data.cards || []).find((c) => c.is_default);
      if (def) setPayWith(def.id);
    }).catch(() => {});
  }, []);

  const buildGroups = useCallback((giftMap, redeemMap) => entries.map(([bizId, g]) => ({
    business_id: bizId, fulfillment: g.fulfillment,
    address: g.fulfillment === "delivery" ? (g.address || "").trim() : null,
    items: g.items.map((i) => ({ product_id: i.product_id, variant_label: i.variant_label, qty: i.qty })),
    use_gift_card: giftMap[bizId] !== false,
    redeem_points: redeemMap[bizId] || 0,
  })), [entries]);

  const refresh = useCallback(async (giftMap, redeemMap) => {
    if (!entries.length) return;
    try {
      const r = await axios.post(`${API}/shop/cart/quote`, { groups: buildGroups(giftMap, redeemMap) });
      setQuote(r.data);
      const fixed = {};
      r.data.groups.forEach((g) => { if ((redeemMap[g.business_id] || 0) !== g.redeemed_points) fixed[g.business_id] = g.redeemed_points; });
      if (Object.keys(fixed).length) setRedeem((s) => ({ ...s, ...fixed }));
    } catch (e) { setError(e?.response?.data?.detail?.code || "Could not price cart"); }
  }, [entries, buildGroups]);

  useEffect(() => { refresh(useGift, redeem); /* eslint-disable-next-line */ }, []);

  if (!entries.length) {
    return (
      <div className="px-4 pt-16 text-center" data-testid="rl-checkout-cart-empty">
        <ShoppingBag size={40} className="mx-auto text-slate-300" />
        <p className="text-slate-500 mt-3">Your cart is empty.</p>
        <button onClick={() => navigate("/shop")} className="mt-4 bg-orange-600 text-white font-black rounded-full px-6 py-2.5">Browse shops</button>
      </div>
    );
  }

  const toggleGift = (bizId) => {
    const next = { ...useGift, [bizId]: useGift[bizId] === false ? true : false };
    setUseGift(next); refresh(next, redeem);
  };
  const setPts = (bizId, v) => {
    const next = { ...redeem, [bizId]: v };
    setRedeem(next); refresh(useGift, next);
  };

  const pay = async () => {
    setBusy(true); setError(null);
    try {
      const r = await axios.post(`${API}/shop/cart/checkout`, {
        groups: buildGroups(useGift, redeem), origin_url: window.location.origin,
        payment_method_id: payWith !== "new" ? payWith : undefined,
      });
      clear();
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      navigate("/shop/product-orders");
    } catch (e) { setError(e?.response?.data?.detail?.code || "Checkout failed"); setBusy(false); }
  };

  const gq = (bizId) => quote?.groups.find((x) => x.business_id === bizId);
  const grand = quote ? quote.grand_total_cents : 0;
  const paysByCard = grand > 0;
  const savedCard = cards.find((c) => c.id === payWith);

  return (
    <div className="pb-40" data-testid="rl-checkout-cart-page">
      <div className="px-4 pt-4 flex items-center gap-2">
        <button onClick={() => navigate(-1)} data-testid="cart-checkout-back"
          className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={22} /></button>
        <h1 className="text-2xl font-black text-slate-900">Checkout</h1>
      </div>

      <div className="px-4 mt-4 space-y-4">
        {entries.map(([bizId, g]) => {
          const q = gq(bizId);
          const giftOn = useGift[bizId] !== false;
          return (
            <div key={bizId} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`checkout-group-${bizId}`}>
              <div className="font-black text-slate-900 flex items-center gap-1.5 mb-2"><Store size={16} className="text-orange-600" />{g.business_name}</div>
              {g.items.map((i) => (
                <div key={`${i.product_id}-${i.variant_label || ""}`} className="flex justify-between text-sm text-slate-600 py-0.5">
                  <span>{i.qty}× {i.name}{i.variant_label ? ` (${i.variant_label})` : ""}</span>
                  <span className="font-bold text-slate-900">{money(i.price_cents * i.qty)}</span>
                </div>
              ))}
              <div className="text-xs text-slate-500 mt-1 capitalize">{g.fulfillment}{q && q.delivery_fee_cents > 0 ? ` · delivery ${money(q.delivery_fee_cents)}` : ""}</div>

              {q && q.gift_available_cents > 0 && (
                <button onClick={() => toggleGift(bizId)} data-testid={`checkout-giftcard-toggle-${bizId}`}
                  className="w-full flex items-center gap-3 mt-3 bg-slate-50 border border-slate-200 rounded-xl p-3 text-left">
                  <span className={`w-5 h-5 rounded-md flex items-center justify-center ${giftOn ? "bg-green-600" : "bg-slate-200"}`}>{giftOn && <Check size={14} className="text-white" />}</span>
                  <Gift size={16} className="text-green-600" />
                  <div className="flex-1 text-sm"><span className="font-bold text-slate-900">Gift card</span> <span className="text-slate-500">· {money(q.gift_available_cents)} available, applies {money(q.gift_applied_cents)}</span></div>
                </button>
              )}
              {q && quote.points_balance > 0 && q.max_redeemable_points > 0 && (
                <div className="mt-3" data-testid={`checkout-points-${bizId}`}>
                  <div className="flex items-center gap-2 text-sm mb-1"><Coins size={16} className="text-orange-600" /><span className="font-bold text-slate-900">Use BigPoints</span><span className="ml-auto text-orange-600 font-bold">−{money(q.points_discount_cents)}</span></div>
                  <input type="range" min={0} max={q.max_redeemable_points} step={100} value={redeem[bizId] || 0} data-testid={`checkout-points-slider-${bizId}`}
                    onChange={(e) => setPts(bizId, Number(e.target.value))} className="w-full accent-orange-600" />
                </div>
              )}
              <div className="border-t border-slate-100 mt-2 pt-2 flex justify-between text-sm">
                <span className="text-slate-500">Venue total</span>
                <span className="font-black text-slate-900" data-testid={`checkout-group-total-${bizId}`}>{q ? money(q.total_cents) : "…"}</span>
              </div>
            </div>
          );
        })}

        <div className="bg-slate-900 rounded-2xl p-4 flex items-center justify-between">
          <span className="text-white/70 font-bold">Total to pay</span>
          <span className="text-white text-2xl font-black" data-testid="checkout-grand-total">{money(grand)}</span>
        </div>

        {/* Payment method */}
        {paysByCard && (
          <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="checkout-payment-method">
            <div className="flex items-center gap-2 mb-2">
              <CreditCard size={18} className="text-slate-700" />
              <div className="font-bold text-slate-900 text-sm">Payment method</div>
              <button onClick={() => navigate("/shop/wallet/cards")} data-testid="checkout-manage-cards"
                className="ml-auto text-xs font-bold text-orange-600">Manage</button>
            </div>
            <div className="space-y-2">
              {cards.map((c) => (
                <button key={c.id} onClick={() => setPayWith(c.id)} data-testid={`checkout-card-${c.id}`}
                  className={`w-full flex items-center gap-3 rounded-xl p-3 text-left border ${payWith === c.id ? "border-orange-500 bg-orange-50" : "border-slate-200 bg-slate-50"}`}>
                  <span className={`w-4 h-4 rounded-full border-2 ${payWith === c.id ? "border-orange-500 bg-orange-500" : "border-slate-300"}`} />
                  <CreditCard size={16} className="text-slate-700" />
                  <span className="text-sm font-bold text-slate-900">{BRAND[c.brand] || c.brand} •••• {c.last4}</span>
                  {c.is_default && <span className="ml-auto text-[10px] font-black text-green-700">DEFAULT</span>}
                </button>
              ))}
              <button onClick={() => setPayWith("new")} data-testid="checkout-card-new"
                className={`w-full flex items-center gap-3 rounded-xl p-3 text-left border ${payWith === "new" ? "border-orange-500 bg-orange-50" : "border-slate-200 bg-slate-50"}`}>
                <span className={`w-4 h-4 rounded-full border-2 ${payWith === "new" ? "border-orange-500 bg-orange-500" : "border-slate-300"}`} />
                <CreditCard size={16} className="text-slate-700" />
                <span className="text-sm font-bold text-slate-900">Pay with a new card</span>
              </button>
            </div>
          </div>
        )}

        {error && <div className="text-rose-600 text-sm font-semibold" data-testid="checkout-error">{error}</div>}

        <button onClick={pay} disabled={busy} data-testid="cart-checkout-pay"
          className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-4 disabled:opacity-60">
          {busy ? "Processing…" : paysByCard
            ? <><CreditCard size={18} />{savedCard ? `Pay ${money(grand)} · •••• ${savedCard.last4}` : `Pay ${money(grand)} by card`}</>
            : <><Check size={18} />Place order</>}
        </button>
      </div>
    </div>
  );
}
