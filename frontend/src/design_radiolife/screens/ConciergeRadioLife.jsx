// AI Ordering Concierge (web) — chat to order with your memberships applied.
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Sparkles, Send, Crown, ShoppingBag } from "lucide-react";
import { API } from "@/AuthContext";
import { useShopCart } from "../useShopCart";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const EXAMPLES = [
  "Use my Pizza Club for a large Tandoori Chicken pizza tonight",
  "Order me a coffee with my membership",
  "Get a medium pizza with extra cheese",
];

export default function ConciergeRadioLife() {
  const navigate = useNavigate();
  const cart = useShopCart();
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [resp, setResp] = useState(null);

  const ask = async (q) => {
    const query = (q ?? text).trim();
    if (!query || loading) return;
    setText(query); setLoading(true); setResp(null);
    try {
      const r = await axios.post(`${API}/shop/concierge`, { text: query });
      setResp(r.data);
    } catch {
      setResp({ ok: false, message: "The concierge is unavailable right now — please try again." });
    } finally { setLoading(false); }
  };

  const addToOrder = () => {
    const p = resp.proposal;
    cart.addLine(p.business_id, p.business_name, {
      item_id: p.item_id, name: p.name, price_cents: p.unit_price_cents, qty: p.qty,
      selected_option_ids: p.selected_option_ids, option_summary: p.option_summary,
      apply_entitlement_id: p.apply_entitlement_id, entitlement_label: p.entitlement_label,
    });
    navigate("/shop/checkout/menu");
  };

  const p = resp?.proposal;
  return (
    <div className="px-4 pt-4 lg:pt-8 pb-24 max-w-2xl mx-auto" data-testid="rl-concierge-page">
      <div className="flex items-center gap-3 mb-4">
        <button onClick={() => navigate(-1)} data-testid="concierge-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <div>
          <div className="text-orange-600 text-[11px] font-black tracking-widest flex items-center gap-1"><Sparkles size={12} />AI CONCIERGE</div>
          <h1 className="text-2xl font-black tracking-tight text-slate-900">Order by chat</h1>
        </div>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-4">
        <div className="flex items-center gap-2 bg-slate-50 border border-slate-200 rounded-xl px-3 py-2">
          <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && ask()}
            data-testid="concierge-input" placeholder="e.g. use my Pizza Club for a large pizza tonight"
            className="flex-1 outline-none text-sm text-slate-800 bg-transparent" />
          <button onClick={() => ask()} disabled={loading} data-testid="concierge-send"
            className="w-9 h-9 rounded-full bg-orange-600 text-white flex items-center justify-center disabled:opacity-60">
            <Send size={16} />
          </button>
        </div>
        <div className="flex flex-wrap gap-2 mt-3">
          {EXAMPLES.map((ex) => (
            <button key={ex} onClick={() => ask(ex)} data-testid="concierge-example"
              className="text-[11px] font-bold text-slate-600 bg-slate-100 rounded-full px-3 py-1.5 hover:bg-orange-50 hover:text-orange-700">{ex}</button>
          ))}
        </div>
      </div>

      {loading && <div className="mt-4 text-center text-slate-500 text-sm" data-testid="concierge-loading">Thinking…</div>}

      {resp && !loading && (
        <div className="mt-4" data-testid="concierge-response">
          <div className="flex items-start gap-2 rounded-2xl bg-orange-50 border border-orange-100 p-3">
            <div className="w-8 h-8 rounded-full bg-orange-600 text-white flex items-center justify-center shrink-0"><Sparkles size={15} /></div>
            <p className="text-sm text-slate-800 font-semibold pt-1">{resp.message}</p>
          </div>

          {p && (
            <div className="mt-3 rounded-2xl border border-slate-200 bg-white p-4" data-testid="concierge-proposal">
              <div className="text-xs font-black text-slate-400 tracking-wide">{p.business_name}</div>
              <div className="text-lg font-black text-slate-900 mt-0.5">{p.qty}× {p.name}</div>
              {p.option_summary && <div className="text-sm text-slate-500">{p.option_summary}</div>}
              {p.entitlement_label && (
                <div className="inline-flex items-center gap-1 mt-1.5 text-xs font-black text-orange-700 bg-orange-100 rounded-full px-2 py-0.5">
                  <Crown size={11} />{p.entitlement_label}
                </div>
              )}
              <div className="flex items-end justify-between mt-3">
                <div>
                  {p.entitlement_discount_cents > 0 && <div className="text-xs text-slate-400 line-through">{money(p.subtotal_cents)}</div>}
                  <div className="text-2xl font-black text-slate-900" data-testid="concierge-total">{money(p.total_cents)}</div>
                </div>
                <button onClick={addToOrder} data-testid="concierge-add-order"
                  className="flex items-center gap-2 bg-orange-600 text-white font-black rounded-full px-5 py-3">
                  <ShoppingBag size={16} /> Add to order
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
