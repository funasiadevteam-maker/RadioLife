// Phase F — Monetization M4: Boosted Flagship Slots · Admin page.
// Legacy dark only (admin surfaces stay legacy per useEffectivePageVariant).
// Create auction slots → review bids → approve/reject.  Advertiser
// gets the auction transparency stats via a separate endpoint.
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, Plus, CheckCircle2, XCircle, ArrowRight, TrendingUp,
  DollarSign, Flame, Calendar, MapPin, Radio, AlertTriangle, X,
} from "lucide-react";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const SLOTS = ["primary", "secondary", "tertiary"];


export default function AdminFlagshipBoosts() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("");
  const [region, setRegion] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [detail, setDetail] = useState(null); // {slot, bids}
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      if (region) p.set("region_code", region);
      const { data } = await axios.get(
        `${API}/admin/flagship-boosts/slots?${p}`, { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [status, region]);

  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-950 text-white"
              data-testid="admin-flagship-boosts-page">
      <div className="max-w-6xl mx-auto px-6 py-8">
        <AdminPageHeader
          title="Flagship Boosts"
          subtitle="Time-boxed boost slots on flagship stations, sold via direct-bid auction.  Advertisers bid, admin approves, Stripe charges, activation goes live."
          Icon={Flame}
          tint="text-orange-500"
          pinLabel="Flagship Boosts"
          breadcrumbs={[{ label: "Ad Monetization" },
                                          { label: "Flagship Boosts" }]}
          actions={
            <button onClick={() => setShowCreate(true)}
                            data-testid="admin-boosts-create-slot"
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
                                                    bg-orange-500 text-slate-950 text-xs font-black
                                                    hover:bg-orange-400">
              <Plus size={12} /> New auction slot
            </button>
          } />

        {/* Filters */}
        <div className="flex flex-wrap items-center gap-2 mb-6">
          <span className="text-[10px] font-mono uppercase tracking-widest
                                        text-slate-500">Status</span>
          {["", "open", "closed", "settled"].map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)}
                            data-testid={`admin-boosts-filter-status-${s || "all"}`}
                            className={`text-[10px] font-mono uppercase tracking-widest
                                                        px-3 py-1.5 rounded-full border transition ${
                                                            status === s
                                                                ? "border-orange-500 bg-orange-500/10 text-orange-500"
                                                                : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
              {s || "All"}
            </button>
          ))}
          <input type="text" placeholder="region_code (e.g. ae, us)"
                        value={region}
                        onChange={(e) => setRegion(e.target.value)}
                        data-testid="admin-boosts-region-filter"
                        className="ml-2 px-3 py-1.5 rounded-full bg-slate-900
                                              border border-slate-800 text-xs text-white
                                              placeholder:text-slate-600 focus:outline-none
                                              focus:border-orange-500" />
        </div>

        {err && (
          <div className="rounded-xl px-4 py-3 bg-red-500/10 border
                                        border-red-500/40 text-red-400 text-sm mb-4
                                        inline-flex items-center gap-2"
                      data-testid="admin-boosts-error">
            <AlertTriangle size={14} /> {err}
          </div>
        )}

        {items === null ? (
          <div className="text-slate-400 inline-flex items-center gap-2"
                      data-testid="admin-boosts-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl bg-slate-900/60 border border-slate-800
                                        p-8 text-center text-slate-400 text-sm"
                      data-testid="admin-boosts-empty">
            No slots yet. Create the first one.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((s) => (
              <SlotRow key={s.slot_id} slot={s}
                                onClick={() => openDetail(s.slot_id, setDetail)} />
            ))}
          </div>
        )}
      </div>

      {showCreate && (
        <CreateSlotModal onClose={() => setShowCreate(false)}
                                          onCreated={() => { setShowCreate(false); load(); }} />
      )}
      {detail && (
        <SlotDetailDrawer detail={detail} onClose={() => setDetail(null)}
                                            onChanged={() => { openDetail(detail.slot.slot_id, setDetail); load(); }} />
      )}
    </div>
  );
}


async function openDetail(slot_id, setDetail) {
  try {
    const { data } = await axios.get(
      `${API}/admin/flagship-boosts/slots/${slot_id}`, { withCredentials: true });
    setDetail(data);
  } catch (e) {
    setDetail(null);
  }
}


function SlotRow({ slot, onClick }) {
  const statusColor = {
    open:      "text-orange-500",
    closed:  "text-slate-400",
    settled: "text-emerald-500",
  }[slot.status] || "text-slate-500";
  return (
    <button onClick={onClick}
                    data-testid={`admin-boosts-slot-${slot.slot_id}`}
                    className="w-full text-left rounded-xl bg-slate-900/60
                                            border border-slate-800 hover:border-orange-500/50
                                            transition p-4">
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono uppercase tracking-widest
                                            text-orange-500">
              <MapPin size={10} className="inline mr-0.5" />
              {slot.region_code}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest
                                            text-slate-400">
              · {slot.station_slot}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest
                                          ml-auto ${statusColor}`}>
              {slot.status}
            </span>
          </div>
          <div className="text-sm font-black">
            Floor ${(slot.floor_price_cents / 100).toFixed(2)}
                    <span className="text-slate-500 mx-2">·</span>
                    Top ${(slot.top_bid_cents / 100).toFixed(2)}
                    <span className="text-slate-500 mx-2">·</span>
                    {slot.bid_count} bid{slot.bid_count === 1 ? "" : "s"}
          </div>
          <div className="text-[11px] font-mono text-slate-500 mt-1">
            {fmt(slot.start_at)} → {fmt(slot.end_at)}
          </div>
          {slot.notes && (
            <div className="text-[11px] text-slate-400 mt-1 italic truncate">
              {slot.notes}
            </div>
          )}
        </div>
        <ArrowRight size={16} className="text-slate-500 mt-1" />
      </div>
    </button>
  );
}


function CreateSlotModal({ onClose, onCreated }) {
  const nowIso = () => new Date(Date.now() + 60_000).toISOString().slice(0, 16);
  const endIso = () => new Date(Date.now() + 24 * 3600_000).toISOString().slice(0, 16);
  const [f, setF] = useState({
    region_code: "ae", station_slot: "primary",
    start_at: nowIso(), end_at: endIso(),
    floor_price_cents: 5000, currency: "usd", notes: "",
  });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      await axios.post(`${API}/admin/flagship-boosts/slots`, {
        ...f,
        start_at: new Date(f.start_at).toISOString(),
        end_at:    new Date(f.end_at).toISOString(),
        floor_price_cents: Number(f.floor_price_cents),
      }, { withCredentials: true });
      onCreated();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start sm:items-center justify-center p-4"
              data-testid="admin-boosts-create-modal">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl
                                    w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4
                                        border-b border-slate-800">
          <h3 className="text-sm font-black uppercase tracking-widest">
            New auction slot
          </h3>
          <button onClick={onClose}
                          className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3 text-sm">
          <Field label="Region code">
            <input type="text" value={f.region_code}
                          onChange={(e) => setF({ ...f, region_code: e.target.value })}
                          data-testid="admin-boosts-create-region"
                          placeholder="ae · us · us-tx-dallas"
                          className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                border border-slate-800 text-white" />
          </Field>
          <Field label="Station slot">
            <select value={f.station_slot}
                            onChange={(e) => setF({ ...f, station_slot: e.target.value })}
                            data-testid="admin-boosts-create-station-slot"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-white">
              {SLOTS.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Start at (UTC)">
              <input type="datetime-local" value={f.start_at}
                            onChange={(e) => setF({ ...f, start_at: e.target.value })}
                            data-testid="admin-boosts-create-start"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-white" />
            </Field>
            <Field label="End at (UTC)">
              <input type="datetime-local" value={f.end_at}
                            onChange={(e) => setF({ ...f, end_at: e.target.value })}
                            data-testid="admin-boosts-create-end"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-white" />
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <Field label="Floor price (cents)">
              <input type="number" min="1" value={f.floor_price_cents}
                            onChange={(e) => setF({ ...f, floor_price_cents: e.target.value })}
                            data-testid="admin-boosts-create-floor"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-white" />
            </Field>
            <Field label="Currency">
              <input type="text" value={f.currency}
                            onChange={(e) => setF({ ...f, currency: e.target.value })}
                            data-testid="admin-boosts-create-currency"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-white" />
            </Field>
          </div>
          <Field label="Notes (optional)">
            <textarea value={f.notes} rows={2}
                            onChange={(e) => setF({ ...f, notes: e.target.value })}
                            data-testid="admin-boosts-create-notes"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-white" />
          </Field>
          {err && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                        text-red-400 text-xs px-3 py-2"
                        data-testid="admin-boosts-create-error">
              {err}
            </div>
          )}
        </div>
        <div className="p-5 border-t border-slate-800 flex gap-2">
          <button onClick={onClose}
                          className="flex-1 py-2 rounded-full text-xs font-black
                                                border border-slate-700 text-slate-300
                                                hover:bg-slate-800/50">Cancel</button>
          <button onClick={submit} disabled={busy}
                          data-testid="admin-boosts-create-submit"
                          className="flex-1 py-2 rounded-full text-xs font-black
                                                bg-orange-500 text-slate-950 hover:bg-orange-400
                                                disabled:opacity-40 inline-flex items-center
                                                justify-center gap-2">
            {busy && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            Create slot
          </button>
        </div>
      </div>
    </div>
  );
}


function SlotDetailDrawer({ detail, onClose, onChanged }) {
  const { slot, bids } = detail || {};
  const [decisionNote, setDecisionNote] = useState("");
  const [force, setForce] = useState(false);
  const [busyId, setBusyId] = useState(null);
  const [err, setErr] = useState(null);

  const highestBid = useMemo(
    () => (bids || []).find((b) => ["pending", "winning"].includes(b.status)) || null,
    [bids]);

  const approve = async (bid_id) => {
    setBusyId(bid_id); setErr(null);
    try {
      await axios.post(
        `${API}/admin/flagship-boosts/bids/${bid_id}/approve${force ? "?force=true" : ""}`,
        { decision_note: decisionNote || null },
        { withCredentials: true });
      setDecisionNote("");
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusyId(null);
    }
  };
  const reject = async (bid_id) => {
    setBusyId(bid_id); setErr(null);
    try {
      await axios.post(
        `${API}/admin/flagship-boosts/bids/${bid_id}/reject`,
        { decision_note: decisionNote || null },
        { withCredentials: true });
      setDecisionNote("");
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusyId(null);
    }
  };
  const closeSlot = async () => {
    setBusyId("close");
    try {
      await axios.post(
        `${API}/admin/flagship-boosts/slots/${slot.slot_id}/close`,
        {}, { withCredentials: true });
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start justify-end p-4 overflow-auto"
              data-testid="admin-boosts-detail-drawer">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl
                                    w-full max-w-2xl shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4
                                        border-b border-slate-800">
          <div className="min-w-0">
            <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-orange-500">
              {slot.region_code} · {slot.station_slot} · {slot.status}
            </div>
            <div className="text-sm font-black truncate mt-0.5">
              Floor ${(slot.floor_price_cents / 100).toFixed(2)} ·
              {bids.length} bid{bids.length === 1 ? "" : "s"}
            </div>
            <div className="text-[11px] text-slate-500 font-mono mt-0.5">
              {fmt(slot.start_at)} → {fmt(slot.end_at)}
            </div>
          </div>
          <button onClick={onClose}
                          className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5">
          {slot.status === "open" && (
            <button onClick={closeSlot} disabled={busyId === "close"}
                            data-testid="admin-boosts-close-slot"
                            className="mb-4 text-[11px] font-mono uppercase tracking-widest
                                                    px-3 py-1.5 rounded-full border border-slate-700
                                                    text-slate-300 hover:bg-slate-800/50
                                                    inline-flex items-center gap-2">
              {busyId === "close" && <Loader2 className="w-3 h-3 animate-spin" />}
              Close auction (no new bids)
            </button>
          )}

          <label className="block text-[10px] font-mono uppercase tracking-widest
                                              text-slate-500 mb-1">Decision note (optional)</label>
          <input type="text" value={decisionNote}
                        onChange={(e) => setDecisionNote(e.target.value)}
                        data-testid="admin-boosts-decision-note"
                        placeholder="Attached to next approve/reject action"
                        className="w-full mb-2 px-3 py-2 rounded-lg bg-slate-950
                                              border border-slate-800 text-sm text-white" />
          <label className="flex items-center gap-2 text-xs text-slate-400 mb-3">
            <input type="checkbox" checked={force}
                          onChange={(e) => setForce(e.target.checked)}
                          data-testid="admin-boosts-force-toggle" />
            Force approval (override higher pending bid)
          </label>
          {err && (
            <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                        text-red-400 text-xs px-3 py-2 mb-3"
                        data-testid="admin-boosts-detail-error">
              {err}
            </div>
          )}

          <div className="space-y-2">
            {(bids || []).map((b, i) => (
              <BidRow key={b.bid_id} bid={b} rank={i + 1}
                              isHighest={b.bid_id === highestBid?.bid_id}
                              busy={busyId === b.bid_id}
                              onApprove={() => approve(b.bid_id)}
                              onReject={() => reject(b.bid_id)} />
            ))}
            {(bids || []).length === 0 && (
              <div className="text-slate-500 text-sm text-center py-8"
                          data-testid="admin-boosts-no-bids">
                No bids yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}


function BidRow({ bid, rank, isHighest, busy, onApprove, onReject }) {
  const statusColor = {
    pending:    "text-slate-300",
    winning:    "text-orange-500",
    approved:  "text-emerald-500",
    rejected:  "text-red-500",
    outbid:      "text-slate-500",
    cancelled: "text-slate-500",
    expired:    "text-amber-500",
  }[bid.status] || "text-slate-400";
  const canDecide = ["pending", "winning"].includes(bid.status);
  return (
    <div className="rounded-xl bg-slate-950/60 border border-slate-800 p-3"
              data-testid={`admin-boosts-bid-${bid.bid_id}`}>
      <div className="flex items-center gap-2">
        <span className={`text-[10px] font-mono uppercase tracking-widest
                                          ${isHighest ? "text-orange-500" : "text-slate-500"}`}>
          #{rank}
        </span>
        <span className="text-sm font-black tabular-nums">
          ${(bid.bid_amount_cents / 100).toFixed(2)}
        </span>
        <span className={`text-[10px] font-mono uppercase tracking-widest ml-auto ${statusColor}`}>
          {bid.status}
        </span>
      </div>
      <div className="text-[11px] text-slate-400 mt-1 truncate">
        {bid.creative?.display_headline}
      </div>
      <div className="text-[10px] font-mono text-slate-500 mt-0.5 truncate">
        {bid.advertiser_business_id} · promotes {bid.creative?.station_id_to_promote}
      </div>
      {canDecide && (
        <div className="flex gap-2 mt-2">
          <button onClick={onApprove} disabled={busy}
                          data-testid={`admin-boosts-approve-${bid.bid_id}`}
                          className="flex-1 py-1.5 rounded-full text-[11px] font-black
                                                bg-emerald-500 text-slate-950 hover:bg-emerald-400
                                                disabled:opacity-40 inline-flex items-center
                                                justify-center gap-1">
            {busy ? <Loader2 className="w-3 h-3 animate-spin" /> :
                            <CheckCircle2 className="w-3 h-3" />}
            Approve
          </button>
          <button onClick={onReject} disabled={busy}
                          data-testid={`admin-boosts-reject-${bid.bid_id}`}
                          className="flex-1 py-1.5 rounded-full text-[11px] font-black
                                                border border-slate-700 text-slate-300
                                                hover:bg-slate-800/50 inline-flex items-center
                                                justify-center gap-1">
            <XCircle className="w-3 h-3" /> Reject
          </button>
        </div>
      )}
    </div>
  );
}


function Field({ label, children }) {
  return (
    <div>
      <label className="block text-[10px] font-mono uppercase tracking-widest
                                          text-slate-500 mb-1">{label}</label>
      {children}
    </div>
  );
}
function fmt(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(undefined,
    { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }); }
  catch { return iso; }
}
