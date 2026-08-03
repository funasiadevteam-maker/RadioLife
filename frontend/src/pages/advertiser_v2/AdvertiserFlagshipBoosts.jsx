// Phase F — Monetization M4: Boosted Flagship Slots · Advertiser page.
// Dual-design (Legacy dark + RadioLife light).  Three tabs:
//    Available Slots — open auctions the advertiser can bid on
//    My Bids            — status list + withdraw pending bids
//    My Activations — scheduled + live + completed activations with impressions
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Flame, MapPin, Radio, Trash2, AlertTriangle, X, CheckCircle2,
  TrendingUp, Eye, Info, Sparkles,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const TABS = [
  { id: "available",    label: "Available slots" },
  { id: "bids",              label: "My bids" },
  { id: "activations", label: "My activations" },
];


export default function AdvertiserFlagshipBoosts() {
  const adv = useAdvertiser();
  const business_id = adv?.active?.advertiser_id || adv?.activeId;
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [tab, setTab] = useState("available");

  if (!business_id) {
    return (
      <div className={`p-6 ${light ? "text-slate-900" : "text-white"}`}
                data-testid="advertiser-flagship-boosts-no-advertiser">
        Loading advertiser context…
      </div>
    );
  }

  const muted = light ? "text-slate-500" : "text-slate-400";
  return (
    <div data-testid="advertiser-flagship-boosts-page"
              data-variant={variant}>
      <div className="flex items-center justify-between mb-2">
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black inline-flex items-center gap-2 ${
                                        light ? "text-slate-900" : "text-white"}`}>
          <Flame className="text-orange-500" size={24} />
          Flagship Boosts
        </h1>
      </div>
      <p className={`text-sm ${muted} mb-5`}>
        Time-boxed premium placements on flagship stations. Bid to boost your
        brand into a slot for a bounded window — winning bid gets a
        &ldquo;🔥 Boosted&rdquo; chip on the flagship card in the target region.
      </p>

      {/* Tab bar */}
      <div className={`flex gap-1 mb-6 border-b ${
                                        light ? "border-slate-200" : "border-slate-800"}`}>
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
                          data-testid={`advertiser-flagship-boosts-tab-${t.id}`}
                          className={`px-4 py-2 text-xs font-black uppercase tracking-widest
                                                      -mb-px border-b-2 transition ${
                                                          tab === t.id
                                                              ? "border-orange-500 text-orange-500"
                                                              : light
                                                                    ? "border-transparent text-slate-500 hover:text-slate-900"
                                                                    : "border-transparent text-slate-400 hover:text-white"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "available"      && <AvailablePanel  bid={business_id} light={light} />}
      {tab === "bids"              && <MyBidsPanel      bid={business_id} light={light} />}
      {tab === "activations"  && <ActivationsPanel bid={business_id} light={light} />}
    </div>
  );
}


// ─── Panel: Available slots ─────────────────────────────────
function AvailablePanel({ bid, light }) {
  const [items, setItems] = useState(null);
  const [region, setRegion] = useState("");
  const [bidTarget, setBidTarget] = useState(null); // slot obj for modal
  const muted = light ? "text-slate-500" : "text-slate-400";

  const load = useCallback(async () => {
    try {
      const p = new URLSearchParams();
      if (region) p.set("region_code", region);
      const { data } = await axios.get(
        `${API}/advertiser/${bid}/flagship-boosts/available?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch {
      setItems([]);
    }
  }, [bid, region]);
  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="advertiser-flagship-boosts-available">
      <div className="flex items-center gap-2 mb-4">
        <input type="text" value={region}
                      onChange={(e) => setRegion(e.target.value)}
                      placeholder="Filter by region_code (ae · us · …)"
                      data-testid="advertiser-flagship-boosts-available-region"
                      className={`flex-1 px-3 py-2 rounded-lg text-sm ${
                                                light
                                                    ? "bg-white border border-slate-200 text-slate-900"
                                                    : "bg-slate-950 border border-slate-800 text-white"}`} />
      </div>
      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}>
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light} text="No open auction slots right now." />
      ) : (
        <div className="space-y-2">
          {items.map((s) => (
            <SlotCard key={s.slot_id} slot={s} light={light}
                                onBid={() => setBidTarget(s)} />
          ))}
        </div>
      )}
      {bidTarget && (
        <BidModal slot={bidTarget} bid={bid} light={light}
                            onClose={() => setBidTarget(null)}
                            onCreated={() => { setBidTarget(null); load(); }} />
      )}
    </div>
  );
}


function SlotCard({ slot, light, onBid }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const hasMy = !!slot.my_active_bid_cents;
  return (
    <div className={`${card} rounded-xl p-4`}
              data-testid={`advertiser-flagship-boosts-slot-${slot.slot_id}`}>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] font-mono uppercase tracking-widest
                                            text-orange-500">
              <MapPin size={10} className="inline mr-0.5" />
              {slot.region_code}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {slot.station_slot}
            </span>
          </div>
          <div className="text-sm font-black">
            Floor ${(slot.floor_price_cents / 100).toFixed(2)}
            <span className={`${muted} mx-2`}>·</span>
            {slot.active_bid_count} active bid{slot.active_bid_count === 1 ? "" : "s"}
          </div>
          <div className={`text-[11px] font-mono ${muted} mt-1`}>
            {fmt(slot.start_at)} → {fmt(slot.end_at)}
          </div>
          {slot.notes && (
            <div className={`text-[11px] italic mt-1 ${muted} truncate`}>
              {slot.notes}
            </div>
          )}
          {hasMy && (
            <div className="mt-1 text-[11px] text-orange-500 inline-flex items-center gap-1"
                        data-testid={`advertiser-flagship-boosts-slot-mine-${slot.slot_id}`}>
              <TrendingUp size={11} />
              Your active bid: ${(slot.my_active_bid_cents / 100).toFixed(2)}
            </div>
          )}
        </div>
        <button onClick={onBid}
                        data-testid={`advertiser-flagship-boosts-bid-${slot.slot_id}`}
                        className="shrink-0 px-4 py-2 rounded-full text-xs font-black
                                              bg-orange-500 text-slate-950 hover:bg-orange-400
                                              inline-flex items-center gap-1">
          <Flame size={12} />
          {hasMy ? "Bid again" : "Bid"}
        </button>
      </div>
    </div>
  );
}


function BidModal({ slot, bid, light, onClose, onCreated }) {
  const [amount, setAmount] = useState(slot.floor_price_cents);
  const [stationId, setStationId] = useState("");
  const [headline, setHeadline] = useState("");
  const [subtext, setSubtext] = useState("");
  const [badgeColor, setBadgeColor] = useState("orange");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [result, setResult] = useState(null);
  const [transparency, setTransparency] = useState(null);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const { data } = await axios.post(
        `${API}/advertiser/${bid}/flagship-boosts/slots/${slot.slot_id}/bid`,
        {
          bid_amount_cents: Number(amount),
          creative: {
            station_id_to_promote: stationId,
            display_headline: headline,
            subtext,
            badge_color: badgeColor,
          },
        }, { withCredentials: true });
      setResult(data);
      // Fetch transparency preview.
      try {
        const t = await axios.get(
          `${API}/advertiser/${bid}/flagship-boosts/bids/${data.bid_id}/transparency`,
          { withCredentials: true });
        setTransparency(t.data);
      } catch { /* ignore */ }
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  };

  const shell = light ? "bg-white text-slate-900 border border-slate-200"
                                          : "bg-slate-900 text-white border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const input = light ? "bg-white border border-slate-200 text-slate-900"
                                            : "bg-slate-950 border border-slate-800 text-white";

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start sm:items-center justify-center p-4"
              data-testid="advertiser-flagship-boosts-bid-modal">
      <div className={`${shell} rounded-2xl w-full max-w-md shadow-2xl`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b
                                        ${light ? "border-slate-200" : "border-slate-800"}`}>
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-orange-500">
              {slot.region_code} · {slot.station_slot}
            </div>
            <div className="text-sm font-black">
              Bid on this slot · floor ${(slot.floor_price_cents / 100).toFixed(2)}
            </div>
          </div>
          <button onClick={onClose}
                          data-testid="advertiser-flagship-boosts-bid-close"
                          className={muted}><X size={18} /></button>
        </div>

        {!result ? (
          <div className="p-5 space-y-3 text-sm">
            <Field label="Your bid (cents)" light={light}>
              <input type="number" min={slot.floor_price_cents}
                            value={amount}
                            onChange={(e) => setAmount(e.target.value)}
                            data-testid="advertiser-flagship-boosts-bid-amount"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
              <div className={`text-[10px] font-mono ${muted} mt-1`}>
                Must be ≥ floor · you&apos;ll be charged this amount if the admin approves
              </div>
            </Field>
            <Field label="Station ID to promote" light={light}>
              <input type="text" value={stationId}
                            onChange={(e) => setStationId(e.target.value)}
                            placeholder="e.g. imp_fun_talk_1003_uae"
                            data-testid="advertiser-flagship-boosts-bid-station"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <Field label="Display headline" light={light}>
              <input type="text" value={headline}
                            onChange={(e) => setHeadline(e.target.value)}
                            placeholder="🔥 Prime rush hour spotlight"
                            data-testid="advertiser-flagship-boosts-bid-headline"
                            maxLength={120}
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <Field label="Subtext (optional)" light={light}>
              <input type="text" value={subtext}
                            onChange={(e) => setSubtext(e.target.value)}
                            data-testid="advertiser-flagship-boosts-bid-subtext"
                            maxLength={200}
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <Field label="Badge color" light={light}>
              <select value={badgeColor}
                              onChange={(e) => setBadgeColor(e.target.value)}
                              data-testid="advertiser-flagship-boosts-bid-color"
                              className={`w-full px-3 py-2 rounded-lg ${input}`}>
                {["orange", "amber", "fuchsia", "emerald", "sky"].map((c) =>
                  <option key={c} value={c}>{c}</option>)}
              </select>
            </Field>
            {err && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                          text-red-400 text-xs px-3 py-2"
                          data-testid="advertiser-flagship-boosts-bid-error">
                {err}
              </div>
            )}
            <button onClick={submit} disabled={busy || !stationId || !headline}
                            data-testid="advertiser-flagship-boosts-bid-submit"
                            className="w-full py-3 rounded-full text-sm font-black
                                                  bg-orange-500 text-slate-950 hover:bg-orange-400
                                                  disabled:opacity-40 inline-flex items-center
                                                  justify-center gap-2">
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Submit bid
            </button>
          </div>
        ) : (
          <div className="p-5"
                      data-testid="advertiser-flagship-boosts-bid-success">
            <div className="w-12 h-12 mx-auto rounded-full grid place-items-center
                                        bg-emerald-500/15 border-2 border-emerald-500 mb-2">
              <CheckCircle2 className="w-6 h-6 text-emerald-500" />
            </div>
            <div className="text-center text-sm font-black mb-1">Bid submitted</div>
            <div className={`text-center text-[11px] font-mono ${muted}`}>
              {result.bid_id}
            </div>
            {transparency && (
              <div className={`mt-4 rounded-xl border p-3 text-xs
                                              ${light ? "bg-slate-50 border-slate-200"
                                                                  : "bg-slate-950/60 border-slate-800"}`}
                          data-testid="advertiser-flagship-boosts-transparency">
                <div className="text-[10px] font-mono uppercase tracking-widest
                                                text-orange-500 mb-2 inline-flex items-center gap-1">
                  <Info size={10} /> Auction transparency
                </div>
                <TransparencyRows t={transparency} muted={muted} />
              </div>
            )}
            <button onClick={onCreated}
                            data-testid="advertiser-flagship-boosts-bid-done"
                            className="w-full mt-4 py-2.5 rounded-full text-xs font-black
                                                  border border-orange-500 text-orange-500
                                                  hover:bg-orange-500/10">
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


function TransparencyRows({ t, muted }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <TxRow label="Your bid"
                    value={`$${((t.your_bid_cents || 0) / 100).toFixed(2)}`} muted={muted} />
      <TxRow label="Floor"
                    value={`$${((t.floor_price_cents || 0) / 100).toFixed(2)}`} muted={muted} />
      <TxRow label="Rank"
                    value={`#${t.rank}`} muted={muted}
                    testId="advertiser-flagship-boosts-transparency-rank" />
      <TxRow label="Competing bids"
                    value={t.competing_bid_count} muted={muted} />
      <TxRow label="Next-higher (approx.)"
                    value={t.next_higher_bid_bucket
                                        ? `~$${((t.next_higher_bid_bucket) / 100).toFixed(2)}`
                                        : "—"}
                    muted={muted}
                    testId="advertiser-flagship-boosts-transparency-next-higher" />
      <TxRow label="Status"
                    value={t.status} muted={muted} />
    </div>
  );
}
function TxRow({ label, value, muted, testId }) {
  return (
    <div>
      <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
        {label}
      </div>
      <div className="text-sm font-black" data-testid={testId}>{value}</div>
    </div>
  );
}


// ─── Panel: My Bids ────────────────────────────────────────
function MyBidsPanel({ bid, light }) {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("");
  const [busyId, setBusyId] = useState(null);
  const [err, setErr] = useState(null);
  const muted = light ? "text-slate-500" : "text-slate-400";

  const load = useCallback(async () => {
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/advertiser/${bid}/flagship-boosts/my-bids?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch { setItems([]); }
  }, [bid, status]);
  useEffect(() => { load(); }, [load]);

  const withdraw = async (bid_id) => {
    setBusyId(bid_id); setErr(null);
    try {
      await axios.delete(
        `${API}/advertiser/${bid}/flagship-boosts/bids/${bid_id}`,
        { withCredentials: true });
      load();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div data-testid="advertiser-flagship-boosts-mybids">
      <div className="flex flex-wrap gap-1.5 mb-4">
        {["", "pending", "approved", "outbid", "rejected", "cancelled"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                          data-testid={`advertiser-flagship-boosts-mybids-filter-${s || "all"}`}
                          className={`text-[10px] font-mono uppercase tracking-widest
                                                      px-3 py-1.5 rounded-full border transition ${
                                                          status === s
                                                              ? "border-orange-500 bg-orange-500/10 text-orange-500"
                                                              : light
                                                                  ? "border-slate-200 text-slate-600 hover:bg-slate-100"
                                                                  : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
            {s || "All"}
          </button>
        ))}
      </div>
      {err && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                      text-red-400 text-xs px-3 py-2 mb-3">
          {err}
        </div>
      )}
      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}>
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light} text="You haven't submitted any bids yet." />
      ) : (
        <div className="space-y-2">
          {items.map((b) => (
            <MyBidRow key={b.bid_id} bid={b} light={light}
                                busy={busyId === b.bid_id}
                                onWithdraw={() => withdraw(b.bid_id)}
                                advertiserId={bid} />
          ))}
        </div>
      )}
    </div>
  );
}


function MyBidRow({ bid, light, busy, onWithdraw, advertiserId }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const statusColor = {
    pending:    "text-orange-500",
    approved:  "text-emerald-500",
    outbid:      "text-slate-500",
    rejected:  "text-red-500",
    cancelled: "text-slate-500",
    expired:    "text-amber-500",
  }[bid.status] || "text-slate-400";

  const [transparency, setTransparency] = useState(null);
  const [showT, setShowT] = useState(false);
  const loadT = async () => {
    if (transparency) { setShowT((v) => !v); return; }
    try {
      const { data } = await axios.get(
        `${API}/advertiser/${advertiserId}/flagship-boosts/bids/${bid.bid_id}/transparency`,
        { withCredentials: true });
      setTransparency(data);
      setShowT(true);
    } catch { /* ignore */ }
  };

  return (
    <div className={`${card} rounded-xl p-3`}
              data-testid={`advertiser-flagship-boosts-mybid-${bid.bid_id}`}>
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-sm font-black tabular-nums">
            ${(bid.bid_amount_cents / 100).toFixed(2)}
            <span className={`${muted} ml-2 text-[11px] font-mono uppercase
                                              tracking-widest`}>
              {bid.currency}
            </span>
          </div>
          <div className={`text-[11px] ${muted} truncate mt-0.5`}>
            {bid.creative?.display_headline}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                      data-testid={`advertiser-flagship-boosts-mybid-status-${bid.bid_id}`}>
            {bid.status}
          </div>
          <div className={`text-[10px] font-mono ${muted}`}>
            {fmt(bid.submitted_at)}
          </div>
        </div>
      </div>
      <div className="flex gap-2 mt-2">
        <button onClick={loadT}
                        data-testid={`advertiser-flagship-boosts-mybid-transparency-${bid.bid_id}`}
                        className={`text-[11px] font-mono uppercase tracking-widest
                                                    px-3 py-1 rounded-full border ${
                                                        light ? "border-slate-200 text-slate-700 hover:bg-slate-100"
                                                                    : "border-slate-700 text-slate-300 hover:bg-slate-800/60"}`}>
          {showT ? "Hide" : "Why?"}
        </button>
        {bid.status === "pending" && (
          <button onClick={onWithdraw} disabled={busy}
                          data-testid={`advertiser-flagship-boosts-mybid-withdraw-${bid.bid_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1 rounded-full border border-red-500/40
                                                text-red-400 hover:bg-red-500/10
                                                disabled:opacity-40 inline-flex items-center gap-1">
            {busy ? <Loader2 className="w-3 h-3 animate-spin" /> :
                            <Trash2 className="w-3 h-3" />} Withdraw
          </button>
        )}
      </div>
      {showT && transparency && (
        <div className={`mt-3 rounded-lg border p-3 text-xs
                                        ${light ? "bg-slate-50 border-slate-200"
                                                            : "bg-slate-950/60 border-slate-800"}`}
                    data-testid={`advertiser-flagship-boosts-mybid-transparency-panel-${bid.bid_id}`}>
          <TransparencyRows t={transparency} muted={muted} />
        </div>
      )}
    </div>
  );
}


// ─── Panel: My Activations ─────────────────────────────
function ActivationsPanel({ bid, light }) {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("");
  const muted = light ? "text-slate-500" : "text-slate-400";

  const load = useCallback(async () => {
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/advertiser/${bid}/flagship-boosts/activations?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch { setItems([]); }
  }, [bid, status]);
  useEffect(() => { load(); }, [load]);

  const totalImpr = useMemo(
    () => (items || []).reduce((a, x) => a + (x.impression_count || 0), 0),
    [items]);

  return (
    <div data-testid="advertiser-flagship-boosts-activations">
      <div className="flex items-center gap-2 mb-4">
        {["", "scheduled", "live", "completed", "cancelled"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                          data-testid={`advertiser-flagship-boosts-activations-filter-${s || "all"}`}
                          className={`text-[10px] font-mono uppercase tracking-widest
                                                      px-3 py-1.5 rounded-full border transition ${
                                                          status === s
                                                              ? "border-orange-500 bg-orange-500/10 text-orange-500"
                                                              : light
                                                                  ? "border-slate-200 text-slate-600 hover:bg-slate-100"
                                                                  : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
            {s || "All"}
          </button>
        ))}
        <div className={`ml-auto text-[10px] font-mono uppercase tracking-widest ${muted}`}>
          <Eye size={10} className="inline mr-1" />
          {totalImpr} total impressions
        </div>
      </div>
      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}>
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light} text="No activations yet." />
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <ActivationRow key={a.activation_id} act={a} light={light} />
          ))}
        </div>
      )}
    </div>
  );
}


function ActivationRow({ act, light }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const statusColor = {
    scheduled: "text-orange-500",
    live:            "text-emerald-500",
    completed:  "text-slate-500",
    cancelled:  "text-red-500",
  }[act.status] || "text-slate-400";
  return (
    <div className={`${card} rounded-xl p-4`}
              data-testid={`advertiser-flagship-boosts-activation-${act.activation_id}`}>
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[10px] font-mono uppercase tracking-widest text-orange-500">
          <MapPin size={10} className="inline mr-0.5" />
          {act.region_code}
        </span>
        <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
          · {act.station_slot} · {act.station_id}
        </span>
        <span className={`text-[10px] font-mono uppercase tracking-widest ml-auto ${statusColor}`}
                    data-testid={`advertiser-flagship-boosts-activation-status-${act.activation_id}`}>
          {act.status}
        </span>
      </div>
      <div className="text-sm font-bold truncate">
        {act.creative?.display_headline}
      </div>
      <div className={`text-[11px] font-mono ${muted} mt-1`}>
        {fmt(act.active_from)} → {fmt(act.active_until)}
      </div>
      <div className="flex items-center gap-3 mt-2 text-[11px]">
        <span className={muted}>
          ${((act.amount_cents || 0) / 100).toFixed(2)} charged
        </span>
        <span className={muted}>·</span>
        <span className={muted}>
          <Eye size={10} className="inline mr-0.5" />
          {act.impression_count} impressions
        </span>
      </div>
    </div>
  );
}


// ─── Shared helpers ────────────────────────────────────────
function EmptyPanel({ light, text }) {
  return (
    <div className={`rounded-2xl p-8 text-center text-sm ${
                                    light ? "bg-slate-50 border border-slate-200 text-slate-500"
                                                : "bg-slate-900/60 border border-slate-800 text-slate-400"}`}
              data-testid="advertiser-flagship-boosts-empty">
      {text}
    </div>
  );
}
function Field({ label, light, children }) {
  const muted = light ? "text-slate-500" : "text-slate-400";
  return (
    <div>
      <label className={`block text-[10px] font-mono uppercase tracking-widest
                                          mb-1 ${muted}`}>{label}</label>
      {children}
    </div>
  );
}
function fmt(iso) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined,
      { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch { return iso; }
}
