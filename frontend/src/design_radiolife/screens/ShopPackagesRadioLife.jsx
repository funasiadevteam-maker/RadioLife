// RadioLife Shop — buy & redeem prepaid packages (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Package as Pkg, Coins, CreditCard, Ticket } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;

export default function ShopPackagesRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/packages/")[1];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/shop/businesses/${id}/packages`); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const buy = async (pkg, method) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/shop/packages/purchase`, { package_id: pkg.package_id, method, origin_url: window.location.origin });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      load(); setBusy(false);
    } catch (e) { alert(e?.response?.data?.detail?.code || "Purchase failed"); setBusy(false); }
  };
  const redeem = async (purchaseId) => {
    try { await axios.post(`${API}/shop/packages/${purchaseId}/redeem`); load(); }
    catch (e) { alert(e?.response?.data?.detail?.code || "Redeem failed"); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Unavailable.</div>;
  const ppd = data.points_per_dollar || 100;

  return (
    <div className="pb-24" data-testid="rl-shop-packages-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="pkg-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900 truncate">{data.public_name} Packages</h1>
      </div>

      <div className="px-4 space-y-4">
        {data.mine?.length > 0 && (
          <div className="rounded-2xl border-2 border-orange-300 bg-orange-50 p-4" data-testid="pkg-mine">
            <div className="font-black text-slate-900 mb-2">Your packages</div>
            {data.mine.map((m) => (
              <div key={m.purchase_id} className="bg-white rounded-xl p-3 mb-2" data-testid={`pkg-mine-${m.purchase_id}`}>
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900 text-sm flex items-center gap-1.5"><Ticket size={15} className="text-orange-600" />{m.name}</span>
                  <span className="text-xs font-black text-slate-500">{m.credits_remaining}/{m.credits_total} left</span>
                </div>
                <button onClick={() => redeem(m.purchase_id)} disabled={m.credits_remaining <= 0} data-testid={`pkg-redeem-${m.purchase_id}`}
                  className="mt-2 w-full bg-orange-600 text-white font-black rounded-full py-2 text-sm disabled:opacity-40">
                  {m.credits_remaining <= 0 ? "Used up" : "Redeem one"}
                </button>
              </div>
            ))}
          </div>
        )}

        {!data.items?.length && !data.mine?.length && <p className="text-center text-slate-500 mt-10" data-testid="pkg-empty">No packages offered here yet.</p>}

        {data.items.map((p) => {
          const pointsCost = Math.round((p.price_cents / 100) * ppd);
          const canPoints = p.allow_points && data.points_balance >= pointsCost;
          return (
            <div key={p.package_id} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`pkg-product-${p.package_id}`}>
              <div className="flex items-center justify-between">
                <div className="font-black text-slate-900 flex items-center gap-1.5"><Pkg size={16} className="text-orange-600" />{p.name}</div>
                <div className="font-black text-orange-600">{money(p.price_cents)}</div>
              </div>
              <div className="text-sm text-slate-500 mt-0.5">{p.credits} credits{p.description ? ` · ${p.description}` : ""}</div>
              <div className="flex gap-2 mt-3">
                {p.allow_card && <button onClick={() => buy(p, "card")} disabled={busy} data-testid={`pkg-buy-card-${p.package_id}`}
                  className="flex-1 flex items-center justify-center gap-2 bg-orange-600 text-white font-black rounded-full py-2.5 text-sm disabled:opacity-50"><CreditCard size={15} />Buy</button>}
                {p.allow_points && <button onClick={() => buy(p, "points")} disabled={busy || !canPoints} data-testid={`pkg-buy-points-${p.package_id}`}
                  className="flex-1 flex items-center justify-center gap-2 bg-slate-100 text-slate-700 font-black rounded-full py-2.5 text-sm disabled:opacity-40"><Coins size={15} />{pointsCost} pts</button>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
