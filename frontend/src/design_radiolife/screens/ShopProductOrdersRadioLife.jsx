// RadioLife Shop — my product orders + fulfillment tracker (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Check, Coins, Package, Truck } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const STEPS = ["paid", "packed", "shipped", "delivered"];
const LABELS = { pending_payment: "Awaiting Payment", paid: "Paid", packed: "Packed", shipped: "Shipped", delivered: "Delivered", canceled: "Canceled" };

export default function ShopProductOrdersRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/shop/product-orders`);
      const list = r.data.items || [];
      await Promise.all(list.filter((o) => o.payment_status !== "paid" && o.session_id)
        .map((o) => axios.get(`${API}/shop/product-orders/${o.order_id}/status`).catch(() => null)));
      const r2 = await axios.get(`${API}/shop/product-orders`);
      setItems(r2.data.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;

  return (
    <div className="pb-24" data-testid="rl-shop-product-orders-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="porders-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900">My Product Orders</h1>
      </div>

      <div className="px-4 space-y-3">
        {!items.length && (
          <div className="text-center text-slate-500 mt-16" data-testid="porders-empty">
            <Package size={44} className="mx-auto text-slate-300" /><p className="mt-3 font-semibold">No product orders yet.</p>
          </div>
        )}
        {items.map((o) => {
          const stepIdx = STEPS.indexOf(o.status);
          return (
            <div key={o.order_id} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`porder-${o.order_id}`}>
              <div className="flex items-center justify-between gap-2">
                <div className="font-black text-slate-900 truncate">{o.business_name}</div>
                <span className="text-xs font-black px-3 py-1.5 rounded-full bg-slate-100 text-slate-700" data-testid={`porder-status-${o.order_id}`}>{LABELS[o.status] || o.status}</span>
              </div>
              <div className="text-sm text-slate-500 font-semibold mt-1">
                {(o.items || []).reduce((n, i) => n + i.qty, 0)} items · {money(o.total_cents)}
                {o.fulfillment === "delivery" ? " · Delivery" : " · Pickup"}
                {o.gift_card_applied_cents > 0 ? ` · gift card −${money(o.gift_card_applied_cents)}` : ""}
              </div>
              {o.fulfillment === "delivery" && o.address && (
                <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-1"><Truck size={13} />{o.address}</div>
              )}
              {o.status !== "canceled" && stepIdx >= 0 && (
                <div className="flex items-center mt-3">
                  {STEPS.map((st, idx) => (
                    <React.Fragment key={st}>
                      <div className={`w-6 h-6 rounded-full flex items-center justify-center border ${idx <= stepIdx ? "bg-green-600 border-green-600" : "bg-slate-100 border-slate-200"}`}>
                        {idx <= stepIdx && <Check size={12} className="text-white" />}
                      </div>
                      {idx < STEPS.length - 1 && <div className={`flex-1 h-0.5 ${idx < stepIdx ? "bg-green-600" : "bg-slate-200"}`} />}
                    </React.Fragment>
                  ))}
                </div>
              )}
              <div className="flex items-center justify-end mt-3">
                <div className="flex items-center gap-1 bg-amber-100 px-3 py-1.5 rounded-full text-xs font-black text-amber-950">
                  <Coins size={13} />{o.points_awarded_done ? `+${o.points_to_award} earned` : `${o.points_to_award} on delivery`}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
