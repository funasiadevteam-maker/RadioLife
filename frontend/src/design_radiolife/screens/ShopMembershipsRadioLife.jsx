// RadioLife Shop — venue memberships: subscribe + claim benefits (web).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, Crown, Check, Coffee, Sparkles } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${(c / 100).toFixed(2)}`;
const periodLabel = (p) => (p === "day" ? "/ day" : p === "week" ? "/ week" : "/ month");

export default function ShopMembershipsRadioLife() {
  const navigate = useNavigate();
  const id = window.location.pathname.split("/shop/memberships/")[1];
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState({});

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/shop/businesses/${id}/memberships`); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const subscribe = async (planId) => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/shop/memberships/subscribe`, { plan_id: planId, origin_url: window.location.origin });
      if (r.data.checkout_url) { window.location.href = r.data.checkout_url; return; }
      load();
    } catch (e) { alert(e?.response?.data?.detail?.code || "Subscription failed"); setBusy(false); }
  };

  const claim = async (benefit) => {
    const option = benefit.options?.length ? pick[benefit.benefit_id] : null;
    if (benefit.options?.length && !option) { alert("Choose an option first"); return; }
    try {
      await axios.post(`${API}/shop/memberships/${data.mine.membership_id}/claim`, { benefit_id: benefit.benefit_id, option });
      load();
    } catch (e) { alert(e?.response?.data?.detail?.code || "Claim failed"); }
  };

  if (loading) return <div className="px-4 pt-10 text-center text-slate-500">Loading…</div>;
  if (!data) return <div className="px-4 pt-10 text-center text-slate-500">Unavailable.</div>;

  return (
    <div className="pb-24" data-testid="rl-shop-memberships-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate(-1)} data-testid="mem-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900 truncate">{data.public_name} Memberships</h1>
      </div>

      <div className="px-4 space-y-4">
        {data.mine && (
          <div className="rounded-2xl border-2 border-amber-400 bg-amber-50 p-4" data-testid="mem-mine">
            <div className="flex items-center gap-2 font-black text-amber-950"><Crown size={18} className="text-amber-500" />You're a {data.mine.plan_name} member</div>
            <div className="mt-3 space-y-2">
              {(data.mine.benefits || []).map((b) => (
                <div key={b.benefit_id} className="bg-white rounded-xl p-3" data-testid={`mem-benefit-${b.benefit_id}`}>
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-900 text-sm flex items-center gap-1.5"><Coffee size={14} className="text-orange-600" />{b.label}</span>
                    <span className="text-xs font-black text-slate-500">{b.remaining}/{b.qty} left {periodLabel(b.period)}</span>
                  </div>
                  {b.options?.length > 0 && (
                    <div className="flex gap-1.5 flex-wrap mt-2">
                      {b.options.map((o) => (
                        <button key={o} onClick={() => setPick((m) => ({ ...m, [b.benefit_id]: o }))}
                          data-testid={`mem-option-${b.benefit_id}-${o}`}
                          className={`px-3 h-8 rounded-full text-xs font-black ${pick[b.benefit_id] === o ? "bg-orange-600 text-white" : "bg-slate-100 text-slate-700"}`}>{o}</button>
                      ))}
                    </div>
                  )}
                  <button onClick={() => claim(b)} disabled={b.remaining <= 0} data-testid={`mem-claim-${b.benefit_id}`}
                    className="mt-2 w-full bg-orange-600 text-white font-black rounded-full py-2 text-sm disabled:opacity-40">
                    {b.remaining <= 0 ? "Claimed for this period" : "Claim now"}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {!data.items?.length && !data.mine && <p className="text-center text-slate-500 mt-10" data-testid="mem-empty">No memberships offered here yet.</p>}

        {data.items.map((p) => {
          const isMine = data.mine && data.mine.plan_id === p.plan_id;
          return (
            <div key={p.plan_id} className="bg-white border border-slate-200 rounded-2xl p-4" data-testid={`mem-plan-${p.plan_id}`}>
              <div className="flex items-center justify-between">
                <div className="font-black text-slate-900 flex items-center gap-1.5"><Sparkles size={16} className="text-orange-600" />{p.name}</div>
                <div className="font-black text-orange-600">{money(p.price_cents)}<span className="text-xs text-slate-400">{periodLabel(p.interval)}</span></div>
              </div>
              {p.description && <div className="text-sm text-slate-500 mt-1">{p.description}</div>}
              <div className="mt-2 space-y-1">
                {(p.entitlements || []).map((e) => (
                  <div key={e.benefit_id} className="flex items-center gap-2 text-sm text-slate-600">
                    <Check size={14} className="text-green-600" />{e.qty}× {e.label}{e.options?.length ? ` (choose: ${e.options.join("/")})` : ""} {periodLabel(e.period)}
                  </div>
                ))}
              </div>
              <button onClick={() => subscribe(p.plan_id)} disabled={busy || isMine} data-testid={`mem-subscribe-${p.plan_id}`}
                className="mt-3 w-full bg-orange-600 text-white font-black rounded-full py-3 disabled:opacity-50">
                {isMine ? "Active member" : `Join · ${money(p.price_cents)}${periodLabel(p.interval)}`}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
}
