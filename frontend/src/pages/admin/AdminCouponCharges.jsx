// Phase N — M7 CPA · Admin view.
// Legacy dark.  Coupon action charges audit + manual refund.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Loader2, ArrowLeft, Coins, X, Undo2 } from "lucide-react";
import { Link } from "react-router-dom";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const REFUND_FILTERS = [
  { v: "", label: "All" },
  { v: "false", label: "Not refunded" },
  { v: "true", label: "Refunded" },
];


export default function AdminCouponCharges() {
  const [items, setItems] = useState(null);
  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (filter) p.set("refunded", filter);
      p.set("limit", "100");
      const { data } = await axios.get(
        `${API}/admin/coupon-action-charges?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [filter]);
  useEffect(() => { load(); }, [load]);

  const refund = async (id) => {
    const reason = window.prompt("Refund reason (audit trail):",
                                  "admin cleanup");
    if (!reason) return;
    setBusy(id);
    try {
      await axios.post(
        `${API}/admin/coupon-action-charges/${id}/refund`,
        { reason }, { withCredentials: true });
      await load();
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(null);
  };

  return (
    <div data-testid="admin-coupon-charges-page"
         className="min-h-screen bg-slate-950 text-white p-6">
      <AdminPageHeader
        title="Coupon Action Charges (CPA)"
        subtitle="Audit coupon-action charges and issue manual refunds."
        Icon={Coins}
        tint="text-orange-500"
        pinLabel="Coupon Charges"
        breadcrumbs={[{ label: "Ad Monetization" },
                                        { label: "Coupon Charges" }]} />

      <div className="flex gap-1.5 mt-3 mb-4">
        {REFUND_FILTERS.map((r) => (
          <button key={r.v || "all"} onClick={() => setFilter(r.v)}
                  data-testid={`admin-cac-filter-${r.v || "all"}`}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold border ${
                    filter === r.v
                      ? "bg-white text-slate-900 border-white"
                      : "border-white/10 text-slate-300"}`}>
            {r.label}
          </button>
        ))}
      </div>

      {items === null && (
        <div className="text-slate-400"
             data-testid="admin-cac-loading">
          <Loader2 size={16} className="animate-spin inline" /> Loading…
        </div>
      )}
      {items?.length === 0 && (
        <div className="text-slate-400 text-sm"
             data-testid="admin-cac-empty">
          No charges match this filter.
        </div>
      )}
      {err && (
        <div data-testid="admin-cac-error"
             className="text-red-400 text-xs">{err}</div>
      )}

      <div className="grid gap-2">
        {(items || []).map((c) => (
          <div key={c.id} data-testid={`admin-cac-row-${c.id}`}
               className="rounded-2xl p-4 bg-white/5 border border-white/10">
            <div className="grid grid-cols-6 gap-3 items-center text-sm">
              <div className="col-span-2">
                <div className="font-bold text-white text-xs font-mono">
                  {c.id}
                </div>
                <div className="text-[10px] text-slate-500 mt-1">
                  coupon {c.coupon_id}
                </div>
              </div>
              <div className="text-slate-300 text-[11px]">
                {c.redemption_type}
                <div className="text-[10px] text-slate-500 mt-0.5">
                  {new Date(c.charged_at).toLocaleString()}
                </div>
              </div>
              <div className="text-slate-300 text-[11px]">
                advertiser<br />
                <span className="font-mono text-[10px] text-slate-400">
                  {c.advertiser_business_id}
                </span>
              </div>
              <div className="text-right font-black font-mono"
                   data-testid={`admin-cac-amount-${c.id}`}>
                {c.cost_charged_cents}¢
                {c.refunded && (
                  <div className="text-[10px] text-emerald-400">
                    refunded
                  </div>
                )}
                {c.refund_reason && !c.refunded && (
                  <div className="text-[10px] text-amber-400">
                    {c.refund_reason}
                  </div>
                )}
              </div>
              <div className="text-right">
                {!c.refunded && c.cost_charged_cents > 0 && (
                  <button onClick={() => refund(c.id)}
                          disabled={busy === c.id}
                          data-testid={`admin-cac-refund-${c.id}`}
                          className="inline-flex items-center gap-1 text-xs
                                     font-bold bg-red-500 hover:bg-red-400
                                     text-white px-3 py-1.5 rounded-full
                                     disabled:opacity-40">
                    <Undo2 size={12} /> {busy === c.id ? "…" : "Refund"}
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
