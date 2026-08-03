// Phase AD.1 — Budget tab: current balance + Stripe Checkout top-up + payments history.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import axios from "axios";
import { Wallet, ArrowUpRight, Loader2, CheckCircle2, XCircle } from "lucide-react";

import { useAdvertiser } from "./AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const fmt = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;
const AMOUNTS = [1000, 5000, 10000, 25000, 50000];

export default function AdvertiserBudget() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active } = useAdvertiser();
  const [params] = useSearchParams();
  const [amount, setAmount] = useState(10000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [payments, setPayments] = useState([]);
  const [refresher, setRefresher] = useState(0);
  const successBanner = params.get("topup") === "success";
  const cancelBanner = params.get("topup") === "cancel";

  useEffect(() => {
    if (!active) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/ad1/advertiser/${active.advertiser_id}/payments`);
        setPayments(data.items || []);
      } catch (_) {}
    })();
  }, [active, refresher]);

  async function topup(chosenAmount) {
    setError(null);
    setBusy(true);
    try {
      const { data } = await axios.post(`${API}/ad1/advertiser/${active.advertiser_id}/top-up`, {
        amount_cents: chosenAmount,
      });
      // Redirect to Stripe Checkout in a new tab.
      if (data.checkout_url) {
        window.location.href = data.checkout_url;
      }
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "object" ? (detail.code || JSON.stringify(detail)) : (detail || err.message));
    } finally { setBusy(false); }
  }

  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"} rounded-2xl p-6`;

  return (
    <div className="space-y-6" data-testid="advertiser-budget-page">
      <div>
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Budget</div>
        <h1 className="text-3xl font-bold mt-1">Ad spend</h1>
      </div>

      {successBanner && (
        <div className="rounded-2xl border border-emerald-500/40 bg-emerald-500/10 text-emerald-500 px-5 py-4 text-sm inline-flex items-center gap-2"
                      data-testid="advertiser-budget-topup-success">
          <CheckCircle2 className="w-4 h-4" /> Payment successful.  Your budget will be credited shortly.
        </div>
      )}
      {cancelBanner && (
        <div className="rounded-2xl border border-slate-500/40 bg-slate-500/10 text-slate-400 px-5 py-4 text-sm inline-flex items-center gap-2"
                      data-testid="advertiser-budget-topup-cancel">
          <XCircle className="w-4 h-4" /> Top-up cancelled.
        </div>
      )}

      <div className={cardCls}>
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Current balance</div>
        <div className="mt-2 text-4xl font-bold" data-testid="advertiser-budget-balance">
          {fmt(active?.budget_available_cents)}
        </div>
        <p className={`mt-1 text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
          USD · updates within seconds of a successful Stripe Checkout.
        </p>
      </div>

      <div className={cardCls}>
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Top up</div>
        <div className="mt-2 font-bold text-lg">Add funds via Stripe Checkout</div>
        <div className="flex gap-2 flex-wrap mt-4">
          {AMOUNTS.map((a) => (
            <button key={a} onClick={() => setAmount(a)}
                            data-testid={`advertiser-budget-preset-${a}`}
                            className={`px-4 py-2 rounded-full text-sm font-semibold ${
                                amount === a ? "bg-amber-500 text-slate-950" :
                                                            (light ? "border border-slate-300 text-slate-700 hover:bg-slate-100" :
                                                                            "border border-slate-700 text-slate-300 hover:bg-slate-800")
                            }`}>
              {fmt(a)}
            </button>
          ))}
        </div>
        <div className="flex gap-2 items-center mt-4">
          <input type="number" value={amount} onChange={(e) => setAmount(parseInt(e.target.value || 0, 10))}
                        className={`w-32 px-3 py-2 rounded-lg border ${
                            light ? "border-slate-300 bg-white" : "border-slate-700 bg-slate-900"
                        } text-sm`}
                        placeholder="cents"
                        data-testid="advertiser-budget-amount" />
          <button onClick={() => topup(amount)} disabled={busy || amount < 500}
                          data-testid="advertiser-budget-topup-btn"
                          className="inline-flex items-center gap-2 px-5 py-2 rounded-full bg-amber-500 text-slate-950 text-sm font-semibold hover:bg-amber-400 disabled:opacity-50 transition">
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <ArrowUpRight className="w-4 h-4" />}
            Top up {fmt(amount)}
          </button>
        </div>
        <p className={`text-xs mt-2 ${light ? "text-slate-500" : "text-slate-500"}`}>
          Minimum $5.00 · you'll be redirected to Stripe Checkout.
        </p>
        {error && (
          <div className="mt-3 rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-400"
                        data-testid="advertiser-budget-error">
            {error}
          </div>
        )}
      </div>

      <div className={cardCls}>
        <div className="flex items-center justify-between">
          <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Recent top-ups</div>
        </div>
        <div className="mt-4 space-y-2" data-testid="advertiser-budget-payments-list">
          {payments.length === 0 && (
            <div className={`text-sm ${light ? "text-slate-500" : "text-slate-500"}`}
                        data-testid="advertiser-budget-payments-empty">
              No top-ups yet.
            </div>
          )}
          {payments.map((p) => (
            <div key={p.payment_id}
                        className={`flex items-center justify-between py-2 ${
                            light ? "border-b border-slate-100" : "border-b border-slate-800"
                        }`}
                        data-testid={`advertiser-budget-payment-${p.payment_id}`}>
              <div>
                <div className="text-sm font-semibold">{fmt(p.amount_cents)}</div>
                <div className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
                  {p.created_at?.slice(0, 19).replace("T", " ")}
                </div>
              </div>
              <div className={`text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full ${
                                            p.status === "paid" ? "bg-emerald-500/15 text-emerald-500"
                                                                              : p.status === "pending" ? "bg-amber-500/15 text-amber-500"
                                                                              : "bg-red-500/15 text-red-400"
                                        }`}>
                {p.status}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
