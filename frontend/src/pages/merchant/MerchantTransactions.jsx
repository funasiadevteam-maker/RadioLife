// Phase MER.1 — Merchant-wide Transactions listing.
// Paginated table with refund action on succeeded rows.
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, ChevronLeft, ChevronRight, Undo2, X, Loader2 } from "lucide-react";
import { useMerchant } from "@/pages/merchant/MerchantShell";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_TINT = (status, light) => {
  const m = {
    succeeded:                        light ? "bg-emerald-100 text-emerald-700"
                                                    : "bg-emerald-500/15 text-emerald-300",
    refunded:                          light ? "bg-slate-100 text-slate-700"
                                                    : "bg-slate-500/15 text-slate-300",
    failed:                              light ? "bg-rose-100 text-rose-700"
                                                    : "bg-rose-500/15 text-rose-300",
    canceled:                          light ? "bg-slate-100 text-slate-600"
                                                    : "bg-slate-500/15 text-slate-400",
    requires_confirmation: light ? "bg-amber-100 text-amber-700"
                                                    : "bg-amber-500/15 text-amber-300",
    abandoned:                        light ? "bg-slate-100 text-slate-500"
                                                    : "bg-slate-500/15 text-slate-500",
  };
  return m[status] || m.canceled;
};

const PAGE_SIZE = 25;


export default function MerchantTransactions() {
  const { merchant, light } = useMerchant();
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [refunding, setRefunding] = useState(null);

  const load = async () => {
    if (!merchant) return;
    setLoading(true);
    try {
      const params = { limit: PAGE_SIZE, offset };
      if (statusFilter) params.status = statusFilter;
      const { data } = await axios.get(
        `${API}/merchant/${merchant.merchant_id}/transactions`,
        { params, withCredentials: true });
      setRows(data.rows || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); },
    [merchant, statusFilter, offset]);

  const filters = [
    { k: "",                        label: "All" },
    { k: "succeeded",      label: "Succeeded" },
    { k: "refunded",        label: "Refunded" },
    { k: "failed",            label: "Failed" },
    { k: "requires_confirmation", label: "Pending" },
  ];

  return (
    <div className="p-6 lg:p-10 max-w-6xl mx-auto space-y-5"
              data-testid="merchant-transactions-page">
      <div className="flex items-center gap-3 flex-wrap">
        <h1 className={`text-3xl font-black tracking-tight ${
          light ? "text-slate-900" : "text-white"
        }`}>Transactions</h1>
        <button onClick={load}
                      className={`ml-auto text-xs font-bold flex items-center gap-1.5 ${
                        light ? "text-slate-500 hover:text-slate-700"
                                : "text-slate-500 hover:text-slate-300"
                      }`}>
          {loading ? <Loader2 className="animate-spin" size={12}/>
                          : <RefreshCw size={12}/>} Refresh
        </button>
      </div>

      {/* Filter chips */}
      <div className="flex items-center gap-2 flex-wrap">
        {filters.map((f) => {
          const active = statusFilter === f.k;
          return (
            <button key={f.k || "all"}
                          onClick={() => { setStatusFilter(f.k); setOffset(0); }}
                          data-testid={`merchant-tx-filter-${f.k || "all"}`}
                          className={`px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider ${
                            active
                              ? (light ? "bg-purple-600 text-white"
                                              : "bg-cyan-500 text-slate-950")
                              : (light ? "bg-white text-slate-600 border border-slate-200"
                                              : "bg-slate-900 text-slate-400 border border-slate-800")
                          }`}>
              {f.label}
            </button>
          );
        })}
        <div className={`ml-auto text-xs ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>{total} transaction{total === 1 ? "" : "s"}</div>
      </div>

      {/* Table */}
      <div className={`rounded-2xl overflow-hidden ${
        light ? "bg-white border border-slate-100 shadow-sm"
                : "bg-slate-900 border border-slate-800"
      }`}>
        {rows.length === 0 && !loading ? (
          <div className={`p-10 text-center text-sm ${
            light ? "text-slate-500" : "text-slate-500"
          }`} data-testid="merchant-tx-empty">
            No transactions match this filter.
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className={`text-[10px] uppercase tracking-wider ${
                light ? "bg-slate-50 text-slate-500"
                        : "bg-slate-950 text-slate-500"
              }`}>
                <th className="text-left px-4 py-3">Date</th>
                <th className="text-left px-4 py-3">Link</th>
                <th className="text-right px-4 py-3">Amount</th>
                <th className="text-center px-4 py-3">Status</th>
                <th className="text-left px-4 py-3">Method</th>
                <th className="text-left px-4 py-3">Customer</th>
                <th className="text-right px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((tx) => {
                const canRefund = tx.status === "succeeded"
                                              && (tx.amount_cents - tx.refunded_cents) > 0;
                return (
                  <tr key={tx.transaction_id}
                        data-testid={`merchant-tx-row-${tx.transaction_id}`}
                        className={light ? "border-t border-slate-100"
                                                      : "border-t border-slate-800"}>
                    <td className={`px-4 py-3 text-xs ${
                      light ? "text-slate-600" : "text-slate-400"
                    }`}>
                      {new Date(tx.succeeded_at || tx.created_at)
                          .toLocaleString(undefined,
                              { month: "short", day: "numeric", hour: "2-digit",
                                minute: "2-digit" })}
                    </td>
                    <td className="px-4 py-3">
                      <div className={`font-semibold truncate max-w-[180px] ${
                        light ? "text-slate-800" : "text-slate-200"
                      }`}>{tx.link_title}</div>
                      <div className={`text-[10px] font-mono ${
                        light ? "text-slate-500" : "text-slate-500"
                      }`}>{tx.transaction_id.slice(0, 20)}…</div>
                    </td>
                    <td className={`px-4 py-3 text-right tabular-nums font-bold ${
                      light ? "text-slate-900" : "text-white"
                    }`}>
                      ${(tx.amount_cents/100).toFixed(2)}
                      {tx.refunded_cents > 0 && (
                        <div className={`text-[10px] font-bold ${
                          light ? "text-amber-700" : "text-amber-300"
                        }`}>-${(tx.refunded_cents/100).toFixed(2)} refunded</div>
                      )}
                    </td>
                    <td className="px-4 py-3 text-center">
                      <span className={`inline-block px-2 py-0.5 rounded-full text-[10px] font-black uppercase tracking-wider ${STATUS_TINT(tx.status, light)}`}>
                        {tx.status.replace(/_/g, " ")}
                      </span>
                    </td>
                    <td className={`px-4 py-3 text-xs ${
                      light ? "text-slate-600" : "text-slate-400"
                    }`}>{(tx.payment_method_type || "—").replace(/_/g, " ")}</td>
                    <td className={`px-4 py-3 text-xs truncate max-w-[180px] ${
                      light ? "text-slate-600" : "text-slate-400"
                    }`}>{tx.customer_email || "guest"}</td>
                    <td className="px-4 py-3 text-right">
                      {canRefund && (
                        <button onClick={() => setRefunding(tx)}
                                      data-testid={`merchant-tx-refund-btn-${tx.transaction_id}`}
                                      className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full inline-flex items-center gap-1 ${
                                        light ? "bg-purple-100 text-purple-700 hover:bg-purple-200"
                                                        : "bg-cyan-500/15 text-cyan-300 hover:bg-cyan-500/25"
                                      }`}>
                          <Undo2 size={11}/> Refund
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Pagination */}
      {total > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <div className={`text-xs ${
            light ? "text-slate-500" : "text-slate-500"
          }`}>
            {offset + 1}–{Math.min(offset + PAGE_SIZE, total)} of {total}
          </div>
          <div className="flex gap-1">
            <PagerBtn light={light} disabled={offset <= 0}
                                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                                testid="merchant-tx-prev">
              <ChevronLeft size={14}/> Prev
            </PagerBtn>
            <PagerBtn light={light} disabled={offset + PAGE_SIZE >= total}
                                onClick={() => setOffset(offset + PAGE_SIZE)}
                                testid="merchant-tx-next">
              Next <ChevronRight size={14}/>
            </PagerBtn>
          </div>
        </div>
      )}

      {refunding && (
        <RefundModal light={light}
                                    merchantId={merchant.merchant_id}
                                    tx={refunding}
                                    onClose={() => setRefunding(null)}
                                    onSuccess={() => { setRefunding(null); load(); }}/>
      )}
    </div>
  );
}


function PagerBtn({ light, disabled, onClick, children, testid }) {
  return (
    <button disabled={disabled} onClick={onClick} data-testid={testid}
                  className={`h-8 px-3 rounded-full text-xs font-bold inline-flex items-center gap-1 ${
                    disabled
                      ? "opacity-40 cursor-not-allowed"
                      : (light ? "bg-white text-slate-700 border border-slate-200 hover:bg-slate-50"
                                      : "bg-slate-900 text-slate-300 border border-slate-800 hover:bg-slate-800")
                  }`}>
      {children}
    </button>
  );
}


function RefundModal({ light, merchantId, tx, onClose, onSuccess }) {
  const remaining = (tx.amount_cents - (tx.refunded_cents || 0)) / 100;
  const [amount, setAmount] = useState(remaining.toFixed(2));
  const [reason, setReason] = useState("requested_by_customer");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const body = { transaction_id: tx.transaction_id, reason };
      if (amount) body.amount_cents = Math.round(parseFloat(amount) * 100);
      const { data } = await axios.post(
        `${API}/merchant/${merchantId}/refunds`, body,
        { withCredentials: true });
      toast.success(`Refund ${data.refund_id.substring(0,12)}… · ${data.status}`);
      onSuccess();
    } catch (e) {
      const d = e?.response?.data?.detail;
      setErr(d?.detail || d?.code || d || e.message);
    } finally { setBusy(false); }
  };

  return (
    <div onClick={onClose}
              data-testid="merchant-tx-refund-backdrop"
              className="fixed inset-0 z-[60] bg-black/70 flex items-end sm:items-center justify-center p-0 sm:p-4">
      <div onClick={(e) => e.stopPropagation()}
                data-testid="merchant-tx-refund-modal"
                className={`w-full sm:max-w-md rounded-t-3xl sm:rounded-3xl p-6 ${
                  light ? "bg-white" : "bg-slate-900 border border-slate-800"
                }`}>
        <div className="flex items-center justify-between mb-4">
          <h3 className={`text-lg font-black ${
            light ? "text-slate-900" : "text-white"
          }`}>Issue refund</h3>
          <button onClick={onClose} className={
            light ? "text-slate-500" : "text-slate-500"}>
            <X size={20}/>
          </button>
        </div>

        <div className={`text-xs mb-4 ${
          light ? "text-slate-500" : "text-slate-500"
        }`}>
          <div>Refunding to <code className={
            light ? "font-mono text-slate-700" : "font-mono text-slate-300"
          }>{tx.transaction_id}</code></div>
          <div>Remaining: <b>${remaining.toFixed(2)} {tx.currency}</b></div>
        </div>

        <Label light={light}>Amount ({tx.currency})</Label>
        <input type="number" step="0.01" min="0.01" max={remaining.toFixed(2)}
                    value={amount} onChange={(e) => setAmount(e.target.value)}
                    data-testid="merchant-tx-refund-amount"
                    className={inputCls(light)}/>

        <Label light={light}>Reason</Label>
        <select value={reason} onChange={(e) => setReason(e.target.value)}
                        data-testid="merchant-tx-refund-reason"
                        className={inputCls(light)}>
          <option value="requested_by_customer">Requested by customer</option>
          <option value="duplicate">Duplicate</option>
          <option value="fraudulent">Fraudulent</option>
          <option value="expired_uncaptured_charge">Expired uncaptured</option>
        </select>

        <div className={`text-[10px] p-2 rounded-lg my-3 ${
          light ? "bg-amber-50 text-amber-700 border border-amber-100"
                  : "bg-amber-500/10 text-amber-300 border border-amber-500/20"
        }`}>
          BigFM commission on the refunded portion is retained by the
          platform.  Ask an admin if you need a full fee reversal.
        </div>

        {err && (
          <div className={`text-xs rounded-lg p-2 mb-3 ${
            light ? "bg-rose-50 text-rose-700 border border-rose-100"
                    : "bg-rose-500/10 text-rose-300 border border-rose-500/20"
          }`} data-testid="merchant-tx-refund-error">{err}</div>
        )}

        <button onClick={submit} disabled={busy}
                      data-testid="merchant-tx-refund-submit"
                      className="w-full h-12 rounded-full font-black text-sm text-white"
                      style={{ background: busy
                                            ? "#94a3b8"
                                            : "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {busy ? "Processing…" : `Refund $${amount} ${tx.currency}`}
        </button>
      </div>
    </div>
  );
}


function Label({ light, children }) {
  return <div className={`text-[10px] font-bold uppercase tracking-widest mb-1 mt-3 ${
    light ? "text-slate-500" : "text-slate-500"
  }`}>{children}</div>;
}
function inputCls(light) {
  return `w-full h-11 rounded-xl px-3 text-sm outline-none ${
    light ? "bg-slate-50 border border-slate-200 focus:border-purple-500"
            : "bg-slate-950 border border-slate-800 text-slate-200 focus:border-cyan-500"
  }`;
}
