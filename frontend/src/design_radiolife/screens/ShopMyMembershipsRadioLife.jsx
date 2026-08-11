// Membership Wallet — one "My Memberships" screen across every venue, with
// quick-claim buttons per benefit and renewal dates.
import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Crown, Check, Calendar, Store, Sparkles } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => (c == null ? "" : `$${(c / 100).toFixed(2)}`);
const fmtDate = (iso) => {
  if (!iso) return null;
  try { return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); }
  catch { return null; }
};

export default function ShopMyMembershipsRadioLife() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [pick, setPick] = useState({});      // benefit_id -> chosen option
  const [busy, setBusy] = useState(null);     // benefit_id being claimed
  const [flash, setFlash] = useState(null);

  const load = useCallback(async () => {
    try { const r = await axios.get(`${API}/shop/memberships/mine`); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const claim = async (m, b) => {
    if (b.options?.length && !pick[b.benefit_id]) { setFlash({ id: b.benefit_id, msg: "Pick an option first" }); return; }
    setBusy(b.benefit_id); setFlash(null);
    try {
      await axios.post(`${API}/shop/memberships/${m.membership_id}/claim`,
        { benefit_id: b.benefit_id, option: pick[b.benefit_id] || null });
      await load();
      setFlash({ id: b.benefit_id, msg: "Claimed! 🎉" });
    } catch (e) {
      setFlash({ id: b.benefit_id, msg: e?.response?.data?.detail?.code === "limit_reached" ? "Limit reached this period" : "Could not claim" });
    } finally { setBusy(null); }
  };

  return (
    <div className="px-4 pt-4 lg:pt-8 pb-24" data-testid="rl-my-memberships-page">
      <header className="mb-4 lg:mb-6">
        <div className="text-orange-600 text-[11px] font-black tracking-widest">RADIOLIFE MEMBERSHIPS</div>
        <h1 className="text-3xl lg:text-4xl font-black tracking-tight text-slate-900 mt-1">My Memberships</h1>
        <p className="text-slate-500 text-sm mt-1">Claim your perks across every venue in one place.</p>
      </header>

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
                  <Link to={`/shop/${m.business_id}`} className="text-xs font-bold text-orange-600 hover:underline">
                    {m.sponsor_name}
                  </Link>
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
                  return (
                    <div key={b.benefit_id} className="rounded-xl border border-slate-100 bg-slate-50/60 p-3"
                      data-testid={`benefit-${b.benefit_id}`}>
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-slate-800 truncate">{b.label}</div>
                          <div className="text-[11px] font-bold text-slate-500">
                            {b.remaining} of {b.qty} left this {b.period}
                          </div>
                        </div>
                        <button
                          onClick={() => claim(m, b)}
                          disabled={out || busy === b.benefit_id}
                          data-testid={`claim-${b.benefit_id}`}
                          className={"shrink-0 inline-flex items-center gap-1.5 rounded-full px-4 py-2 text-sm font-black transition-colors " +
                            (out ? "bg-slate-200 text-slate-400" : "bg-orange-600 text-white hover:bg-orange-700")}>
                          {out ? <>Used</> : busy === b.benefit_id ? <>…</> : <><Sparkles size={14} /> Claim</>}
                        </button>
                      </div>
                      {b.options?.length > 0 && !out && (
                        <div className="flex flex-wrap gap-1.5 mt-2">
                          {b.options.map((o) => (
                            <button key={o} onClick={() => setPick((p) => ({ ...p, [b.benefit_id]: o }))}
                              data-testid={`opt-${b.benefit_id}-${o}`}
                              className={"px-2.5 py-1 rounded-full text-[11px] font-bold border " +
                                (pick[b.benefit_id] === o ? "bg-orange-600 text-white border-orange-600" : "bg-white text-slate-600 border-slate-200")}>
                              {pick[b.benefit_id] === o && <Check size={10} className="inline mr-1" />}{o}
                            </button>
                          ))}
                        </div>
                      )}
                      {flash?.id === b.benefit_id && <div className="text-[11px] font-bold text-orange-600 mt-1.5">{flash.msg}</div>}
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
