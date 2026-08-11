// RadioLife Shop — buy a venue gift card (points or card) — web.
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Gift, Coins, CreditCard, Check } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(0)}`;

export default function ShopGiftCardsRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/giftcards/")[1];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [product, setProduct] = useState(null);
  const [amount, setAmount] = useState(null);
  const [method, setMethod] = useState("card");
  const [giftOpen, setGiftOpen] = useState(false);
  const [giftEmail, setGiftEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    axios.get(`${API}/shop/businesses/${id}/giftcards`).then((r) => {
      setData(r.data);
      const first = (r.data.items || [])[0];
      if (first) { setProduct(first); setAmount((first.denominations_cents || [])[0] || null); }
    }).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const ppd = data?.points_per_dollar || 100;
  const pointsCost = amount ? Math.round((amount / 100) * ppd) : 0;
  const canPoints = product?.allow_points && (data?.points_balance || 0) >= pointsCost;

  const buy = async () => {
    if (!product || !amount) return;
    if (giftOpen && !giftEmail.trim().includes("@")) { alert("Enter a valid friend's email to gift."); return; }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/giftcards/purchase`, {
        product_id: product.product_id, amount_cents: amount, method,
        gift_to_email: giftOpen ? giftEmail.trim() : null,
        message: giftOpen ? (message.trim() || null) : null,
        origin_url: window.location.origin,
      });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      setDone(true);
    } catch (e) {
      alert(e?.response?.data?.detail?.code || "Purchase failed");
      setBusy(false);
    }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Unavailable.</div>;

  return (
    <div className="pb-24" data-testid="rl-shop-giftcards-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="gc-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900 truncate">{data.public_name} Gift Cards</h1>
      </div>

      {done ? (
        <div className="px-4 pt-10 text-center" data-testid="gc-success">
          <div className="w-16 h-16 rounded-full bg-green-100 mx-auto flex items-center justify-center"><Check size={30} className="text-green-600" /></div>
          <div className="text-xl font-black text-slate-900 mt-4">Gift card purchased!</div>
          <div className="text-sm text-slate-500 mt-1">{giftEmail ? `We sent it to ${giftEmail}.` : "It's ready in your wallet and auto-applies at checkout."}</div>
          <button onClick={() => navigate(`/shop/${id}`)} className="mt-6 bg-orange-600 text-white font-black rounded-full px-6 py-3">Back to venue</button>
        </div>
      ) : !data.items?.length ? (
        <p className="text-center text-slate-500 mt-10" data-testid="gc-empty">No gift cards available here yet.</p>
      ) : (
        <div className="px-4 space-y-4">
          {data.items.map((p) => (
            <button key={p.product_id} onClick={() => { setProduct(p); setAmount((p.denominations_cents || [])[0]); }}
              data-testid={`gc-product-${p.product_id}`}
              className={`w-full text-left rounded-2xl p-4 border-2 ${product?.product_id === p.product_id ? "border-orange-600 bg-orange-50" : "border-slate-200 bg-white"}`}>
              <div className="flex items-center gap-2 font-black text-slate-900"><Gift size={18} className="text-orange-600" />{data.public_name} Gift Card</div>
              <div className="flex gap-2 flex-wrap mt-3">
                {(p.denominations_cents || []).map((d) => (
                  <span key={d} onClick={(e) => { e.stopPropagation(); setProduct(p); setAmount(d); }}
                    data-testid={`gc-denom-${p.product_id}-${d}`}
                    className={`px-4 h-9 flex items-center rounded-full font-black text-sm cursor-pointer ${product?.product_id === p.product_id && amount === d ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"}`}>{money(d)}</span>
                ))}
              </div>
            </button>
          ))}

          {product && amount && (
            <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3">
              <div className="flex gap-2">
                <button onClick={() => setMethod("card")} data-testid="gc-method-card"
                  className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-black text-sm ${method === "card" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"} ${!product.allow_card ? "opacity-40 pointer-events-none" : ""}`}><CreditCard size={16} />Pay by card</button>
                <button onClick={() => setMethod("points")} data-testid="gc-method-points"
                  className={`flex-1 flex items-center justify-center gap-2 py-3 rounded-xl font-black text-sm ${method === "points" ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"} ${!product.allow_points ? "opacity-40 pointer-events-none" : ""}`}><Coins size={16} />{pointsCost} pts</button>
              </div>
              {method === "points" && !canPoints && <div className="text-xs font-bold text-rose-600">Not enough BigPoints (you have {data.points_balance}).</div>}

              <button type="button" onClick={() => setGiftOpen((v) => !v)} data-testid="gc-gift-toggle"
                className={`flex items-center gap-2 text-sm font-black ${giftOpen ? "text-orange-600" : "text-slate-500"}`}>
                <Gift size={15} />{giftOpen ? "Gifting to a friend" : "Gift this gift card"}
              </button>
              {giftOpen && (
                <div className="space-y-2" data-testid="gc-gift-fields">
                  <input value={giftEmail} onChange={(e) => setGiftEmail(e.target.value)} type="email" placeholder="Friend's email" data-testid="gc-gift-email"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
                  <input value={message} onChange={(e) => setMessage(e.target.value)} maxLength={280} placeholder="Optional message" data-testid="gc-message"
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm" />
                </div>
              )}
              <button onClick={buy} disabled={busy || (method === "points" && !canPoints)} data-testid="gc-buy"
                className="w-full flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-50">
                <Gift size={16} />{giftOpen ? `Gift ${money(amount)} card` : `Buy ${money(amount)} gift card`}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
