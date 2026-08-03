// Phase K — M3 Marketplace · Admin featured-slot moderation queue.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, Sparkles, ArrowLeft, Check, X,
} from "lucide-react";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "pending_admin", "active", "completed",
                                  "cancelled", "draft"];


export default function AdminMarketplaceSlots() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("pending_admin");
  const [sel, setSel] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/admin/marketplace-featured-slots?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6"
              data-testid="admin-marketplace-slots-page">
      <div className="max-w-6xl mx-auto">
        <AdminPageHeader
          title="Marketplace Featured Slots"
          subtitle="Approve or reject over-threshold featured-slot purchases before they surface in the listener marketplace."
          Icon={Sparkles}
          tint="text-fuchsia-500"
          pinLabel="Marketplace Slots"
          breadcrumbs={[{ label: "Ad Monetization" },
                                          { label: "Marketplace Slots" }]} />

        <div className="flex flex-wrap gap-1.5 mb-4">
          {STATUSES.map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)}
                            data-testid={`admin-mfs-filter-${s || "all"}`}
                            className={`text-[10px] font-mono uppercase tracking-widest
                                                        px-3 py-1.5 rounded-full border transition ${
                                                            status === s
                                                                ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-400"
                                                                : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
              {s || "All"}
            </button>
          ))}
        </div>

        {err && <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                                          text-red-400 text-xs px-3 py-2 mb-3"
                                            data-testid="admin-mfs-error">{err}</div>}

        {items === null ? (
          <div className="text-slate-400 inline-flex items-center gap-2"
                      data-testid="admin-mfs-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl bg-slate-900/60 border border-slate-800
                                        p-6 text-center text-sm text-slate-500"
                      data-testid="admin-mfs-empty">
            No featured-slot purchases in this state.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((s) => (
              <Row key={s.slot_id} s={s} onOpen={() => setSel(s)} />
            ))}
          </div>
        )}
      </div>
      {sel && <Drawer s={sel} onClose={() => setSel(null)}
                                          onChanged={() => { setSel(null); load(); }} />}
    </div>
  );
}


function Row({ s, onOpen }) {
  const statusColor = {
    pending_admin: "text-fuchsia-400",
    active:            "text-emerald-500",
    completed:      "text-slate-400",
    cancelled:      "text-red-400",
    draft:              "text-slate-500",
  }[s.status] || "text-slate-400";
  const progress = s.days_purchased > 0
    ? Math.round((s.days_delivered / s.days_purchased) * 100) : 0;
  return (
    <button onClick={onOpen}
                    data-testid={`admin-mfs-row-${s.slot_id}`}
                    className="w-full text-left rounded-xl bg-slate-900/60
                                              border border-slate-800 p-4 hover:border-slate-700">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`admin-mfs-status-${s.slot_id}`}>
              {s.status}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {s.region_code?.toUpperCase()} · pos #{s.slot_position}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {s.listing_ref?.source_type}
            </span>
          </div>
          <div className="text-sm font-black truncate">
            slot binds: {s.listing_ref?.source_id}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            adv: {s.advertiser_business_id}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
            Budget
          </div>
          <div className="text-lg font-black">
            ${(s.total_budget_cents / 100).toFixed(2)}
          </div>
          <div className="text-[10px] font-mono text-slate-500">
            {s.days_delivered}/{s.days_purchased} days
          </div>
        </div>
      </div>
      <div className="mt-2 h-1 rounded-full bg-slate-800 overflow-hidden">
        <div className="h-full bg-fuchsia-500" style={{ width: `${progress}%` }} />
      </div>
    </button>
  );
}


function Drawer({ s, onClose, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);

  const decide = async (verb) => {
    if (verb === "reject" && !note.trim()) {
      setErr("admin_notes_required_for_reject"); return;
    }
    setBusy(verb); setErr(null);
    try {
      await axios.post(
        `${API}/admin/marketplace-featured-slots/${s.slot_id}/${verb}`,
        { admin_notes: note.trim() || null },
        { withCredentials: true });
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(null); }
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start sm:items-center justify-center p-4 overflow-auto"
              data-testid="admin-mfs-detail-drawer">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl
                                    w-full max-w-lg text-white shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <Sparkles size={14} className="text-fuchsia-500" />
            {s.status === "pending_admin" ? "Review featured slot" : "Featured slot"}
          </h3>
          <button onClick={onClose}
                          data-testid="admin-mfs-detail-close"
                          className="text-slate-400"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3 text-sm">
          <MetaRow label="Advertiser" value={s.advertiser_business_id} />
          <MetaRow label="Region · Position"
                              value={`${s.region_code?.toUpperCase()} · #${s.slot_position}`} />
          <MetaRow label="Binds to"
                              value={`${s.listing_ref?.source_type} / ${s.listing_ref?.source_id}`}
                              testId="admin-mfs-detail-listing-ref" />
          <MetaRow label="Cost/day"
                              value={`$${(s.cost_per_day_cents / 100).toFixed(2)}`} />
          <MetaRow label="Days"
                              value={`${s.days_delivered} / ${s.days_purchased}`} />
          <MetaRow label="Total charge"
                              value={`$${(s.total_budget_cents / 100).toFixed(2)}`}
                              testId="admin-mfs-detail-total" />
          <MetaRow label="Remaining"
                              value={`$${(s.remaining_budget_cents / 100).toFixed(2)}`} />
          <MetaRow label="Window"
                              value={`${s.start_at?.slice(0, 10) || "-"} → ${s.end_at?.slice(0, 10) || "-"}`} />
          {s.status === "pending_admin" && (
            <>
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest
                                                text-slate-500 block mb-1">
                  Admin note (required to reject)
                </label>
                <textarea value={note} onChange={(e) => setNote(e.target.value)}
                                        data-testid="admin-mfs-decision-note"
                                        rows={2} maxLength={280}
                                        className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                                  border border-slate-800 text-white text-xs" />
              </div>
              {err && <div className="text-xs text-red-400"
                                            data-testid="admin-mfs-decision-error">{err}</div>}
              <div className="flex gap-2">
                <button onClick={() => decide("approve")} disabled={!!busy}
                                data-testid="admin-mfs-approve"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                        bg-emerald-500 text-slate-950 hover:bg-emerald-400
                                                        disabled:opacity-40 inline-flex items-center
                                                        justify-center gap-1.5">
                  {busy === "approve" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                                          <Check size={12} />} Approve
                </button>
                <button onClick={() => decide("reject")} disabled={!!busy}
                                data-testid="admin-mfs-reject"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                        border border-red-500/40 text-red-400
                                                        hover:bg-red-500/10 disabled:opacity-40
                                                        inline-flex items-center justify-center gap-1.5">
                  {busy === "reject" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                                          <X size={12} />} Reject + refund
                </button>
              </div>
            </>
          )}
          {s.admin_notes && (
            <div className="text-[11px] text-slate-500"
                        data-testid="admin-mfs-detail-notes">
              Admin notes: {s.admin_notes}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function MetaRow({ label, value, testId }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </span>
      <span className="text-xs font-mono text-white truncate max-w-[65%]"
                  data-testid={testId}>{value}</span>
    </div>
  );
}
