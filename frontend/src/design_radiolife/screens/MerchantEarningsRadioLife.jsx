// RadioLife Merchant Earnings — memberships sold, gross, platform fee, net (web).
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, TrendingUp, Crown } from "lucide-react";
import { API } from "@/AuthContext";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

export default function MerchantEarningsRadioLife() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/merchant/marketplace/earnings`);
        setData(r.data);
      } catch { /* ignore */ } finally { setLoading(false); }
    })();
  }, []);

  return (
    <div className="pb-24" data-testid="rl-merchant-earnings-page">
      <div className="flex items-center gap-3 px-4 pt-4 pb-2">
        <button onClick={() => navigate("/shop/merchant")} data-testid="earnings-back" className="w-9 h-9 rounded-full bg-slate-100 flex items-center justify-center"><ChevronLeft size={20} /></button>
        <h1 className="text-xl font-black text-slate-900 flex items-center gap-1.5"><TrendingUp size={18} className="text-emerald-600" />Earnings</h1>
      </div>

      {loading ? (
        <div className="px-4 py-10 text-center text-slate-400 text-sm">Loading…</div>
      ) : !data ? (
        <div className="px-4 py-10 text-center text-slate-400 text-sm">Couldn&apos;t load earnings.</div>
      ) : (
        <div className="px-4 space-y-4">
          {/* Net payout headline */}
          <div className="bg-gradient-to-br from-emerald-600 to-teal-500 text-white rounded-2xl p-5" data-testid="earnings-net-card">
            <div className="text-xs font-black opacity-80 uppercase tracking-wider">Net payout · all time</div>
            <div className="text-4xl font-black mt-1" data-testid="earnings-net-total">{money(data.net_cents)}</div>
            <div className="text-xs font-bold opacity-90 mt-1">
              {money(data.gross_cents)} collected · {money(data.fee_cents)} platform fee
            </div>
          </div>

          {/* Stat grid */}
          <div className="grid grid-cols-3 gap-3">
            <div className="bg-white border border-slate-200 rounded-2xl p-3 text-center" data-testid="earnings-sold">
              <div className="text-2xl font-black text-slate-900">{data.memberships_sold}</div>
              <div className="text-[11px] font-bold text-slate-500">Memberships sold</div>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-3 text-center" data-testid="earnings-month-net">
              <div className="text-2xl font-black text-slate-900">{money(data.month?.net_cents)}</div>
              <div className="text-[11px] font-bold text-slate-500">Net this month</div>
            </div>
            <div className="bg-white border border-slate-200 rounded-2xl p-3 text-center" data-testid="earnings-month-fee">
              <div className="text-2xl font-black text-slate-900">{money(data.month?.fee_cents)}</div>
              <div className="text-[11px] font-bold text-slate-500">Fee this month</div>
            </div>
          </div>

          {/* Transactions */}
          <div>
            <div className="text-xs font-black uppercase tracking-wider text-slate-400 mb-2">Recent membership sales</div>
            {(data.transactions || []).length === 0 ? (
              <div className="bg-white border border-slate-200 rounded-2xl p-5 text-center" data-testid="earnings-empty">
                <Crown size={22} className="text-amber-500 mx-auto" />
                <p className="text-sm text-slate-600 font-semibold mt-1">No membership sales yet.</p>
                <p className="text-xs text-slate-400">Sales appear here once shoppers subscribe to your memberships.</p>
              </div>
            ) : (
              <div className="space-y-2" data-testid="earnings-tx-list">
                {(data.transactions || []).map((t) => (
                  <div key={t.earning_id} className="bg-white border border-slate-200 rounded-xl p-3 flex items-center justify-between" data-testid={`earnings-tx-${t.earning_id}`}>
                    <div className="min-w-0">
                      <div className="font-bold text-slate-900 text-sm truncate">{t.plan_name || "Membership"}</div>
                      <div className="text-[11px] text-slate-500">{money(t.gross_cents)} · {Math.round(t.fee_pct)}% fee ({money(t.fee_cents)})</div>
                    </div>
                    <div className="text-emerald-700 font-black text-sm whitespace-nowrap">+{money(t.net_cents)}</div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <p className="text-[11px] text-slate-400 text-center px-4">
            The platform fee is set by your category and any negotiated rate. Payouts are settled to your account separately.
          </p>
        </div>
      )}
    </div>
  );
}
