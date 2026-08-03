// Phase SC.6 — Merchant Payouts page.  Both design variants.
//
// Lists payouts owned by the current merchant with aggregate summary.
// Route: /merchant/payouts
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { ArrowLeft, RefreshCw, Wallet, Clock, XCircle,
                  CheckCircle2, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import { useAuth } from "@/AuthContext";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_META = {
  pending:            { label: "Pending",        Icon: Clock,        color: "amber" },
  in_transit:      { label: "In transit",  Icon: TrendingUp, color: "sky" },
  paid:                    { label: "Paid",              Icon: CheckCircle2, color: "emerald" },
  failed:                { label: "Failed",          Icon: XCircle,      color: "rose" },
  canceled:            { label: "Canceled",      Icon: XCircle,      color: "slate" },
};


export default function MerchantPayouts() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { user } = useAuth();
  const [merchantId, setMerchantId] = useState(null);
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");

  useEffect(() => {
    (async () => {
      if (!user) return;
      try {
        const { data } = await axios.get(`${API}/merchant/mine`,
                                                                        { withCredentials: true });
        const merchants = data.items || data.merchants || [];
        if (merchants.length) setMerchantId(merchants[0].merchant_id
                                                                              || merchants[0].business_id
                                                                              || merchants[0]._id);
      } catch (e) {
        // silent
      }
    })();
  }, [user]);

  const load = async () => {
    if (!merchantId) return;
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      const { data } = await axios.get(
        `${API}/merchant/${merchantId}/payouts`,
        { params, withCredentials: true });
      setRows(data.rows || []);
      setSummary(data.summary || null);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [merchantId, statusFilter]);

  if (!user) {
    return <ShellFrame light={light}><p>Please log in.</p></ShellFrame>;
  }

  if (!merchantId) {
    return (
      <ShellFrame light={light} testid="merchant-payouts-no-merchant">
        <p className={light ? "text-slate-600" : "text-slate-400"}>
          No merchant found.  <Link to="/merchant/apply" className={
            light ? "text-purple-600 underline" : "text-cyan-400 underline"}>Apply now</Link>.
        </p>
      </ShellFrame>
    );
  }

  return (
    <div className={light ? "min-h-screen bg-gradient-to-b from-purple-50 via-white to-pink-50"
                                          : "min-h-screen bg-slate-950 text-slate-100"}
              data-testid="merchant-payouts-page"
              data-variant={variant}>
      <div className="max-w-5xl mx-auto px-5 py-8">
        <div className="flex items-center gap-3 mb-6">
          <Link to="/merchant/dashboard"
                    data-testid="merchant-payouts-back"
                    className={light ? "text-purple-600 hover:text-purple-700"
                                              : "text-cyan-400 hover:text-cyan-300"}>
            <ArrowLeft size={20}/>
          </Link>
          <h1 className={`text-3xl font-black tracking-tight ${
            light ? "text-slate-900" : "text-white"
          }`}>Payouts</h1>
          <button onClick={load}
                        className={`ml-auto text-xs font-semibold flex items-center gap-1 ${
                          light ? "text-slate-500 hover:text-slate-700"
                                  : "text-slate-500 hover:text-slate-300"
                        }`}>
            <RefreshCw size={13}/> Refresh
          </button>
        </div>

        {/* Summary cards */}
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
          <SummaryCard light={light} label="Total Paid"
                                      value={summary?.total_paid_cents}
                                      Icon={Wallet}
                                      color="emerald"
                                      testid="merchant-payouts-summary-paid"/>
          <SummaryCard light={light} label="Pending"
                                      value={summary?.pending_cents}
                                      Icon={Clock}
                                      color="amber"
                                      testid="merchant-payouts-summary-pending"/>
          <SummaryCard light={light} label="Failed"
                                      value={summary?.failed_cents}
                                      Icon={XCircle}
                                      color="rose"
                                      testid="merchant-payouts-summary-failed"/>
        </div>

        {/* Filter */}
        <div className="flex items-center gap-2 mb-4">
          {["", "pending", "in_transit", "paid", "failed"].map((s) => (
            <button key={s || "all"}
                          onClick={() => setStatusFilter(s)}
                          data-testid={`merchant-payouts-filter-${s || "all"}`}
                          className={`px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                            statusFilter === s
                              ? (light ? "bg-purple-600 text-white"
                                              : "bg-cyan-500 text-slate-950")
                              : (light ? "bg-white text-slate-600 border border-slate-200"
                                              : "bg-slate-900 text-slate-400 border border-slate-800")
                          }`}>
              {s ? s.replace(/_/g, " ") : "All"}
            </button>
          ))}
          <div className={`ml-auto text-xs ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>
            {loading ? "Loading…" : `${total} payout${total === 1 ? "" : "s"}`}
          </div>
        </div>

        {/* Table */}
        <div className={`rounded-2xl overflow-hidden ${
          light ? "bg-white border border-slate-100 shadow-sm"
                  : "bg-slate-900 border border-slate-800"
        }`}>
          {rows.length === 0 ? (
            <div className={`p-8 text-center text-sm ${
              light ? "text-slate-500" : "text-slate-500"
            }`}>
              No payouts yet.  When Stripe schedules a payout to your
              connected account, it will appear here.
            </div>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className={`text-[10px] uppercase tracking-wider ${
                  light ? "bg-slate-50 text-slate-500"
                          : "bg-slate-950 text-slate-500"
                }`}>
                  <th className="text-left px-4 py-3">Date</th>
                  <th className="text-right px-4 py-3">Amount</th>
                  <th className="text-center px-4 py-3">Status</th>
                  <th className="text-left px-4 py-3">Method</th>
                  <th className="text-left px-4 py-3">Arrival</th>
                  <th className="text-left px-4 py-3">Payout ID</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => {
                  const meta = STATUS_META[p.status] || STATUS_META.pending;
                  const StatusIcon = meta.Icon;
                  return (
                    <tr key={p.stripe_payout_id}
                          data-testid={`merchant-payout-row-${p.stripe_payout_id}`}
                          className={light ? "border-t border-slate-100"
                                                        : "border-t border-slate-800"}>
                      <td className={`px-4 py-3 text-xs ${
                        light ? "text-slate-600" : "text-slate-400"
                      }`}>
                        {p.created_at ? new Date(p.created_at).toLocaleDateString(undefined,
                          { month: "short", day: "numeric", year: "numeric" }) : ""}
                      </td>
                      <td className={`px-4 py-3 text-right font-bold tabular-nums ${
                        light ? "text-slate-900" : "text-white"
                      }`}>
                        {(p.amount_cents / 100).toFixed(2)}
                        <span className={`ml-1 text-[10px] font-normal ${
                          light ? "text-slate-500" : "text-slate-500"
                        }`}>{p.currency}</span>
                      </td>
                      <td className="px-4 py-3 text-center">
                        <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider ${statusPillClass(meta.color, light)}`}>
                          <StatusIcon size={10}/> {meta.label}
                        </span>
                      </td>
                      <td className={`px-4 py-3 text-xs ${
                        light ? "text-slate-600" : "text-slate-400"
                      }`}>{p.method}</td>
                      <td className={`px-4 py-3 text-xs ${
                        light ? "text-slate-600" : "text-slate-400"
                      }`}>
                        {p.arrival_date ? new Date(p.arrival_date)
                                                                    .toLocaleDateString(undefined,
                              { month: "short", day: "numeric" }) : "—"}
                      </td>
                      <td className={`px-4 py-3 text-[10px] font-mono ${
                        light ? "text-slate-500" : "text-slate-500"
                      }`}>{p.stripe_payout_id}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}


function SummaryCard({ light, label, value, Icon, color, testid }) {
  const cents = value || 0;
  const dollars = (cents / 100).toFixed(2);
  const palette = {
    emerald: light ? "bg-emerald-50 text-emerald-700"
                                    : "bg-emerald-500/10 text-emerald-300",
    amber:      light ? "bg-amber-50 text-amber-700"
                                    : "bg-amber-500/10 text-amber-300",
    rose:        light ? "bg-rose-50 text-rose-700"
                                    : "bg-rose-500/10 text-rose-300",
  }[color];
  return (
    <div className={`rounded-2xl p-4 ${
      light ? "bg-white shadow-sm border border-slate-100"
              : "bg-slate-900 border border-slate-800"
    }`} data-testid={testid}>
      <div className="flex items-center gap-3">
        <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${palette}`}>
          <Icon size={16}/>
        </div>
        <div>
          <div className={`text-[10px] font-bold uppercase tracking-widest ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>{label}</div>
          <div className={`text-xl font-black tabular-nums ${
            light ? "text-slate-900" : "text-white"
          }`}>${dollars}</div>
        </div>
      </div>
    </div>
  );
}


function statusPillClass(color, light) {
  const map = {
    emerald: light ? "bg-emerald-100 text-emerald-700"
                                    : "bg-emerald-500/15 text-emerald-300",
    amber:      light ? "bg-amber-100 text-amber-700"
                                    : "bg-amber-500/15 text-amber-300",
    sky:          light ? "bg-sky-100 text-sky-700"
                                    : "bg-sky-500/15 text-sky-300",
    rose:        light ? "bg-rose-100 text-rose-700"
                                    : "bg-rose-500/15 text-rose-300",
    slate:      light ? "bg-slate-100 text-slate-700"
                                    : "bg-slate-500/15 text-slate-300",
  };
  return map[color] || map.slate;
}


function ShellFrame({ light, testid, children }) {
  return (
    <div className={light
                          ? "min-h-screen bg-white flex items-center justify-center p-6"
                          : "min-h-screen bg-slate-950 flex items-center justify-center p-6"}
              data-testid={testid}>
      {children}
    </div>
  );
}
