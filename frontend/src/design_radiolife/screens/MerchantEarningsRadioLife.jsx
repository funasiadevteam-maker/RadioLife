// RadioLife Merchant Earnings — memberships sold, gross, platform fee, net,
// 30-day trends chart, and Stripe Connect payouts (withdraw + instant).
import React, { useEffect, useState, useCallback } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { ChevronLeft, TrendingUp, Crown, Banknote, Zap, CheckCircle2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { API } from "@/AuthContext";

const money = (c) => `$${((c || 0) / 100).toFixed(2)}`;

function TrendsChart({ daily }) {
  const days = daily || [];
  const max = Math.max(1, ...days.map((d) => d.net_cents || 0));
  const total = days.reduce((a, d) => a + (d.net_cents || 0), 0);
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="earnings-trends">
      <div className="flex items-center justify-between mb-3">
        <div className="text-xs font-black uppercase tracking-wider text-slate-400">Last 30 days</div>
        <div className="text-xs font-bold text-slate-500">{money(total)} net</div>
      </div>
      {total === 0 ? (
        <div className="text-center text-xs text-slate-400 py-6" data-testid="earnings-trends-empty">No sales in the last 30 days yet.</div>
      ) : (
        <div className="flex items-end gap-[3px] h-28">
          {days.map((d) => (
            <div key={d.date} className="flex-1 flex flex-col justify-end group relative" title={`${d.date}: ${money(d.net_cents)}`}>
              <div
                className={`w-full rounded-t ${d.net_cents > 0 ? "bg-emerald-500 group-hover:bg-emerald-600" : "bg-slate-200"}`}
                style={{ height: `${Math.max(d.net_cents > 0 ? 6 : 2, (d.net_cents / max) * 100)}%` }}
                data-testid={`earnings-bar-${d.date}`}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function PayoutsCard({ status, available, onConnect, onWithdraw, onInstant, busy }) {
  if (!status) return null;
  const connected = status.connected;
  const hasAccount = status.has_account;
  return (
    <div className="bg-white border border-slate-200 rounded-2xl p-4" data-testid="earnings-payouts">
      <div className="flex items-center gap-2 mb-1">
        <Banknote size={16} className="text-emerald-600" />
        <div className="text-sm font-black text-slate-900">Payouts</div>
        {connected && <span className="flex items-center gap-1 text-emerald-700 text-[10px] font-black bg-emerald-50 px-2 py-0.5 rounded-full"><CheckCircle2 size={11} />Connected</span>}
      </div>

      {connected ? (
        <>
          <p className="text-xs text-slate-500">Available to withdraw</p>
          <div className="text-2xl font-black text-slate-900" data-testid="payouts-available">{money(available)}</div>
          <div className="flex gap-2 mt-3">
            <button onClick={onWithdraw} disabled={busy || available <= 0} data-testid="payouts-withdraw"
              className="flex-1 flex items-center justify-center gap-1.5 bg-emerald-600 text-white font-black rounded-full py-2.5 text-sm disabled:opacity-40">
              <Banknote size={15} />{busy ? "Working…" : "Withdraw"}
            </button>
            <button onClick={onInstant} disabled={busy} data-testid="payouts-instant"
              className="flex items-center justify-center gap-1.5 bg-slate-900 text-white font-black rounded-full px-4 py-2.5 text-sm disabled:opacity-40">
              <Zap size={15} />Cash out now
            </button>
          </div>
          <p className="text-[11px] text-slate-400 mt-2">Withdraw moves your net to your Stripe balance (paid to your bank on schedule). &quot;Cash out now&quot; sends it to your bank instantly for a small fee.</p>
        </>
      ) : (
        <>
          <p className="text-xs text-slate-500 mt-1">
            {hasAccount ? "Finish your payout setup to start receiving money." : "Connect a bank via Stripe to receive your earnings."}
          </p>
          {(status.requirements_due || []).length > 0 && (
            <div className="flex items-start gap-1.5 mt-2 text-[11px] text-amber-700 bg-amber-50 rounded-lg p-2" data-testid="payouts-requirements">
              <AlertCircle size={13} className="mt-0.5 shrink-0" />
              <span>More info needed: {status.requirements_due.slice(0, 4).join(", ")}</span>
            </div>
          )}
          <button onClick={onConnect} disabled={busy} data-testid="payouts-connect"
            className="mt-3 w-full flex items-center justify-center gap-1.5 bg-orange-600 text-white font-black rounded-full py-2.5 text-sm disabled:opacity-50">
            <Banknote size={15} />{busy ? "Opening…" : hasAccount ? "Finish payout setup" : "Connect payouts"}
          </button>
        </>
      )}
    </div>
  );
}

export default function MerchantEarningsRadioLife() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const loadEarnings = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/merchant/marketplace/earnings`);
      setData(r.data);
    } catch { /* ignore */ }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/merchant/marketplace/connect/status`);
      setStatus(r.data);
    } catch { setStatus({ has_account: false, connected: false }); }
  }, []);

  useEffect(() => {
    (async () => {
      await Promise.all([loadEarnings(), loadStatus()]);
      setLoading(false);
    })();
  }, [loadEarnings, loadStatus]);

  // Returning from the Stripe onboarding flow → re-check status.
  useEffect(() => {
    if (params.get("connect")) {
      loadStatus();
      const next = new URLSearchParams(params);
      next.delete("connect");
      setParams(next, { replace: true });
    }
  }, [params, loadStatus, setParams]);

  const connectPayouts = async () => {
    setBusy(true);
    try {
      await axios.post(`${API}/merchant/marketplace/connect/account`);
      const r = await axios.post(`${API}/merchant/marketplace/connect/onboarding-link`, { origin_url: window.location.origin, platform: "web" });
      if (r.data.url) { window.location.href = r.data.url; return; }
    } catch { toast.error("Couldn't start payout setup"); }
    finally { setBusy(false); }
  };

  const withdraw = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/payout/withdraw`);
      toast.success(`Transferred ${money(r.data.amount_cents)} to your Stripe balance`);
      await loadEarnings();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.message || "Withdrawal failed");
    } finally { setBusy(false); }
  };

  const instant = async () => {
    setBusy(true);
    try {
      const r = await axios.post(`${API}/merchant/marketplace/payout/instant`);
      toast.success(`Instant payout of ${money(r.data.amount_cents)} on its way`);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.message || "Instant payout unavailable");
    } finally { setBusy(false); }
  };

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

          {/* Payouts (Stripe Connect) */}
          <PayoutsCard status={status} available={data.available_cents} busy={busy}
            onConnect={connectPayouts} onWithdraw={withdraw} onInstant={instant} />

          {/* 30-day trends */}
          <TrendsChart daily={data.daily} />

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
            The platform fee is set by your category and any negotiated rate. Payouts settle to your connected account via Stripe.
          </p>
        </div>
      )}
    </div>
  );
}
