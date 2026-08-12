// Membership Wallet (web) — one "My Memberships" view across venues. Shows
// each entitlement's remaining usage, lets members order eligible items
// straight from here (order-from-wallet), and keeps quick-claim for in-store perks.
import React, { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Crown, Check, Calendar, Store, Sparkles, ShoppingBag, Clock, PiggyBank } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => (c == null ? "" : `$${(c / 100).toFixed(2)}`);
const fmtDate = (iso) => {
  if (!iso) return null;
  try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); }
  catch { return null; }
};

export default function ShopMyMembershipsRadioLife() {
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [savings, setSavings] = useState(null);
  const [pick, setPick] = useState({});
  const [busy, setBusy] = useState(null);
  const [flash, setFlash] = useState(null);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/shop/memberships/mine`); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
    axios.get(`${API}/shop/memberships/savings`).then((r) => setSavings(r.data)).catch(() => setSavings(null));
  }, []);
  useEffect(() => { load(); }, [load]);

  const entId = (b) => b.entitlement_id || b.benefit_id;
  const claim = async (m, b) => {
    if (b.options?.length && !pick[entId(b)]) { setFlash({ id: entId(b), msg: "Pick an option first" }); return; }
    setBusy(entId(b)); setFlash(null);
    try {
      await axios.post(`${API}/shop/memberships/${m.membership_id}/claim`,
        { entitlement_id: entId(b), option: pick[entId(b)] || null });
      await load();
      setFlash({ id: entId(b), msg: "Claimed! 🎉" });
    } catch (e) {
      setFlash({ id: entId(b), msg: e?.response?.data?.detail?.code === "limit_reached" ? "Limit reached this period" : "Could not claim" });
    } finally { setBusy(null); }
  };

  const orderItem = (m, b, it) => {
    const q = new URLSearchParams({ item: it.id, apply_entitlement: entId(b) }).toString();
    navigate(`/shop/menu/${m.business_id}?${q}`);
  };

  return (
    <div className="px-4 pt-4 lg:pt-8 pb-24" data-testid="rl-my-memberships-page">
      <header className="mb-4 lg:mb-6">
        <div className="text-orange-600 text-[11px] font-black tracking-widest">RADIOLIFE MEMBERSHIPS</div>
        <h1 className="text-3xl lg:text-4xl font-black tracking-tight text-slate-900 mt-1">My Memberships</h1>
        <p className="text-slate-500 text-sm mt-1">Order eligible items or claim your perks across every venue.</p>
      </header>

      {savings && savings.lifetime_savings_cents > 0 && (
        <div className="mb-5 rounded-2xl bg-gradient-to-br from-orange-600 to-amber-500 text-white p-4 flex items-center gap-4" data-testid="savings-tracker">
          <div className="w-12 h-12 rounded-2xl bg-white/20 flex items-center justify-center shrink-0"><PiggyBank size={26} /></div>
          <div className="flex-1">
            <div className="text-[11px] font-black tracking-widest opacity-90">MEMBERSHIP SAVINGS</div>
            <div className="text-2xl font-black leading-tight" data-testid="savings-month">{money(savings.month_savings_cents)} <span className="text-sm font-bold opacity-80">this month</span></div>
            <div className="text-xs font-bold opacity-90 mt-0.5">{money(savings.lifetime_savings_cents)} saved all-time · {savings.lifetime_count} perks used</div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="space-y-3">{[0, 1].map((i) => <div key={i} className="h-40 rounded-2xl bg-slate-100 animate-pulse" />)}</div>
      ) : !items.length ? (
        <div className="text-center py-16" data-testid="mymemberships-empty">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-orange-50 flex items-center justify-center mb-3">
            <Crown size={28} className="text-orange-600" />
          </div>
          <div className="font-black text-slate-800">No memberships yet</div>
          <p className="text-slate-500 text-sm mt-1 mb-4">Join a venue membership to unlock recurring perks.</p>
          <Link to="/shop" data-testid="mymemberships-browse"
            className="inline-flex items-center gap-2 bg-orange-600 text-white font-black rounded-full px-6 py-2.5">
            <Store size={16} /> Explore the Shop
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {items.map((m) => (
            <div key={m.membership_id} className="bg-white border border-slate-200 rounded-2xl p-4 shadow-sm"
              data-testid={`mymembership-${m.membership_id}`}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <Crown size={16} className="text-orange-600 shrink-0" />
                    <span className="font-black text-slate-900 truncate">{m.plan_name || "Membership"}</span>
                  </div>
                  <Link to={`/shop/${m.business_id}`} className="text-xs font-bold text-orange-600 hover:underline">{m.sponsor_name}</Link>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-sm font-black text-slate-900">{money(m.price_cents)}<span className="text-slate-400 font-bold">/{m.interval || "mo"}</span></div>
                  {fmtDate(m.current_period_end) && (
                    <div className="text-[11px] font-bold text-slate-500 flex items-center gap-1 justify-end mt-0.5">
                      <Calendar size={11} /> Renews {fmtDate(m.current_period_end)}
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-3 space-y-2">
                {(m.benefits || []).map((b) => {
                  const out = b.remaining <= 0;
                  const eid = entId(b);
                  const orderable = ["item", "product", "category"].includes(b.target_type) && (b.eligible_items || []).length > 0;
                  return (
                    <div key={eid} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3" data-testid={`benefit-${eid}`}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-slate-800 truncate">{b.label}</div>
                          <div className="text-[11px] font-bold text-slate-500 flex items-center gap-1">
                            {b.remaining} of {b.qty} left this {b.period}
                            {b.available_now === false && <span className="text-rose-500 flex items-center gap-0.5"><Clock size={10} />off-hours</span>}
                          </div>
                        </div>
                        {!orderable && (
                          <button onClick={() => claim(m, b)} disabled={out || busy === eid} data-testid={`claim-${eid}`}
                            className={"shrink-0 inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-black transition-colors " +
                              (out ? "bg-slate-200 text-slate-400" : "bg-orange-600 text-white hover:bg-orange-700")}>
                            {out ? <>Used</> : busy === eid ? <>…</> : <><Sparkles size={14} /> Claim</>}
                          </button>
                        )}
                      </div>

                      {orderable && !out && (
                        <div className="mt-2">
                          <div className="text-[11px] font-black text-slate-400 uppercase mb-1">Order with this membership</div>
                          <div className="flex gap-2 overflow-x-auto pb-1" data-testid={`benefit-order-row-${eid}`}>
                            {b.eligible_items.map((it) => (
                              <button key={it.id} onClick={() => orderItem(m, b, it)} data-testid={`benefit-order-${eid}-${it.id}`}
                                className="shrink-0 w-28 text-left bg-white border border-slate-200 rounded-xl overflow-hidden hover:border-orange-300">
                                {it.image_url && <img src={it.image_url} alt={it.name} className="w-full h-16 object-cover bg-slate-100" />}
                                <div className="p-2">
                                  <div className="text-[11px] font-bold text-slate-800 line-clamp-2 leading-tight">{it.name}</div>
                                  <div className="mt-1 inline-flex items-center gap-1 text-[10px] font-black text-orange-600"><ShoppingBag size={10} />Order</div>
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {b.options?.length > 0 && !orderable && !out && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {b.options.map((o) => (
                            <button key={o} onClick={() => setPick((p) => ({ ...p, [eid]: o }))} data-testid={`opt-${eid}-${o}`}
                              className={"px-2.5 py-1 rounded-full text-[11px] font-bold border " +
                                (pick[eid] === o ? "bg-orange-600 text-white border-orange-600" : "bg-white text-slate-600 border-slate-200")}>
                              {pick[eid] === o && <Check size={10} className="inline mr-1" />}{o}
                            </button>
                          ))}
                        </div>
                      )}
                      {flash?.id === eid && <div className="text-[11px] font-bold text-orange-600 mt-1.5">{flash.msg}</div>}
                    </div>
                  );
                })}
                {!(m.benefits || []).length && <div className="text-xs text-slate-400">No claimable perks on this plan.</div>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
