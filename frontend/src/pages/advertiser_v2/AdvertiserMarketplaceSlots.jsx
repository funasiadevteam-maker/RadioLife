// Phase K — M3 Marketplace · Advertiser featured-slot dashboard.
// Dual-design.  Wizard lets advertiser pick from ANY active marketplace
// listing (typically their own coupons/offers, but we don't restrict —
// the auction handles bid competition).
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Sparkles, Plus, X, Trash2, Info, Check,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";
import FlagshipSponsorUpsellBanner from "@/components/FlagshipSponsorUpsellBanner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_admin", "active",
                                  "completed", "cancelled"];
const REGIONS = ["ae", "us", "in", "sa", "eg", "gb"];


export default function AdvertiserMarketplaceSlots() {
  const adv = useAdvertiser();
  const business_id = adv?.active?.advertiser_id || adv?.activeId;
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    if (!business_id) return;
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/advertiser/${business_id}/marketplace-featured-slots?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [business_id, status]);
  useEffect(() => { load(); }, [load]);

  if (!business_id) {
    return (
      <div className={`p-6 ${light ? "text-slate-900" : "text-white"}`}
                data-testid="advertiser-mfs-no-advertiser">
        Loading advertiser context…
      </div>
    );
  }

  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div data-testid="advertiser-mfs-page" data-variant={variant}>
      <FlagshipSponsorUpsellBanner business_id={business_id}
                                    source_page="advertiser_marketplace_slots" />
      <div className="flex items-center justify-between mb-2">
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black inline-flex items-center gap-2 ${
                                        light ? "text-slate-900" : "text-white"}`}>
          <Sparkles className="text-fuchsia-500" size={24} />
          Marketplace Featured Slots
        </h1>
        <button onClick={() => setShowCreate(true)}
                        data-testid="advertiser-mfs-create"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                                                bg-fuchsia-500 text-white text-xs font-black
                                                hover:bg-fuchsia-400">
          <Plus size={14} /> Buy featured slot
        </button>
      </div>
      <p className={`text-sm ${muted} mb-6`}>
        Get your coupon or offer to the top of the listener marketplace
        (positions 1-3) for a given region.  Charge model: `cost_per_day`
        once per unique viewer per calendar-day.  Fee: 25% of media spend.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                          data-testid={`advertiser-mfs-filter-${s || "all"}`}
                          className={`text-[10px] font-mono uppercase tracking-widest
                                                      px-3 py-1.5 rounded-full border transition ${
                                                          status === s
                                                              ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-500"
                                                              : light
                                                                  ? "border-slate-200 text-slate-600 hover:bg-slate-100"
                                                                  : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
            {s || "All"}
          </button>
        ))}
      </div>

      {err && <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                                          text-red-400 text-xs px-3 py-2 mb-3"
                                            data-testid="advertiser-mfs-error">{err}</div>}

      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}
                    data-testid="advertiser-mfs-loading">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light}
                              text="No featured-slot purchases yet — click 'Buy featured slot' to promote one of your deals." />
      ) : (
        <div className="space-y-2">
          {items.map((s) => (
            <SlotCard key={s.slot_id} s={s} light={light}
                                      business_id={business_id} onChanged={load} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateModal light={light} business_id={business_id}
                                  onClose={() => setShowCreate(false)}
                                  onDone={() => { setShowCreate(false); load(); }} />
      )}
    </div>
  );
}


function SlotCard({ s, light, business_id, onChanged }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const statusColor = {
    draft:              muted,
    pending_admin: "text-fuchsia-500",
    active:            "text-emerald-500",
    completed:      muted,
    cancelled:      "text-red-500",
  }[s.status] || muted;
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  const act = async (verb) => {
    setBusy(verb); setErr(null);
    try {
      if (verb === "confirm-payment") {
        await axios.post(
          `${API}/advertiser/${business_id}/marketplace-featured-slots/${s.slot_id}/confirm-payment`,
          {}, { withCredentials: true });
      } else if (verb === "cancel") {
        if (!window.confirm(
              `Cancel and refund $${((s.remaining_budget_cents || 0) * 1.25 / 100).toFixed(2)}?`))
          { setBusy(null); return; }
        await axios.post(
          `${API}/advertiser/${business_id}/marketplace-featured-slots/${s.slot_id}/cancel`,
          { reason: "advertiser_cancelled" },
          { withCredentials: true });
      }
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(null); }
  };

  const progress = s.days_purchased > 0
    ? Math.round((s.days_delivered / s.days_purchased) * 100) : 0;

  return (
    <div className={`${card} rounded-xl p-4`}
              data-testid={`advertiser-mfs-card-${s.slot_id}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`advertiser-mfs-status-${s.slot_id}`}>
              {s.status}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {s.region_code?.toUpperCase()} · pos #{s.slot_position}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {s.listing_ref?.source_type}
            </span>
          </div>
          <div className="text-sm font-black truncate">
            {s.listing_ref?.source_id}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
            Total charge
          </div>
          <div className="text-sm font-black"
                      data-testid={`advertiser-mfs-cost-${s.slot_id}`}>
            ${(s.total_budget_cents / 100).toFixed(2)}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className={`flex justify-between text-[10px] font-mono ${muted}`}>
          <span>{s.days_delivered}/{s.days_purchased} days delivered</span>
          <span>${(s.remaining_budget_cents / 100).toFixed(2)} remaining</span>
        </div>
        <div className={`h-1.5 rounded-full mt-1 overflow-hidden ${
                                        light ? "bg-slate-100" : "bg-slate-800"}`}>
          <div className="h-full bg-gradient-to-r from-fuchsia-500 to-emerald-500"
                      style={{ width: `${progress}%` }} />
        </div>
      </div>

      {err && <div className="mt-2 text-xs text-red-400"
                                  data-testid={`advertiser-mfs-error-${s.slot_id}`}>{err}</div>}

      <div className="flex flex-wrap gap-2 mt-3">
        {s.status === "draft" && (
          <button onClick={() => act("confirm-payment")} disabled={!!busy}
                          data-testid={`advertiser-mfs-confirm-${s.slot_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full bg-fuchsia-500 text-white
                                                hover:bg-fuchsia-400 inline-flex items-center gap-1">
            {busy === "confirm-payment" && <Loader2 className="w-3 h-3 animate-spin" />}
            Pay + activate (${(s.total_budget_cents / 100).toFixed(2)})
          </button>
        )}
        {["pending_admin", "active", "paused"].includes(s.status) && (
          <button onClick={() => act("cancel")} disabled={!!busy}
                          data-testid={`advertiser-mfs-cancel-${s.slot_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full border border-red-500/40
                                                text-red-400 hover:bg-red-500/10
                                                inline-flex items-center gap-1">
            {busy === "cancel" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                            <Trash2 className="w-3 h-3" />} Cancel + refund
          </button>
        )}
        {s.status === "cancelled" && s.refunded_amount_cents > 0 && (
          <div className={`text-[10px] font-mono ${muted}`}
                      data-testid={`advertiser-mfs-refunded-${s.slot_id}`}>
            Refunded ${(s.refunded_amount_cents / 100).toFixed(2)}
          </div>
        )}
      </div>
    </div>
  );
}


function CreateModal({ light, business_id, onClose, onDone }) {
  const [f, setF] = useState({
    source_type:              "coupon_campaign",
    source_id:                "",
    region_code:              "ae",
    slot_position:          1,
    cost_per_day_cents: 200,
    days_purchased:        7,
    start_at:                    new Date(Date.now() - 60_000).toISOString().slice(0, 16),
    end_at:                        new Date(Date.now() + 14 * 24 * 3600_000).toISOString().slice(0, 16),
  });
  const [browse, setBrowse] = useState([]);
  const [browseErr, setBrowseErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);

  useEffect(() => {
    // Load listings from marketplace (public endpoint) — advertiser
    // picks one to bind their slot to.
    (async () => {
      try {
        const { data } = await axios.get(
          `${API}/marketplace/listings?limit=30&region_code=${f.region_code}`,
          { withCredentials: true });
        setBrowse(data.items || []);
      } catch (e) {
        setBrowseErr(e?.response?.data?.detail?.code || e.message);
      }
    })();
  }, [f.region_code]);

  const budget = useMemo(() => {
    const media = Number(f.days_purchased || 0) * Number(f.cost_per_day_cents || 0);
    const fee = Math.floor(media * 0.25);
    return { media, fee, total: media + fee,
                    needsAdmin: (media + fee) >= 50_000 };
  }, [f.days_purchased, f.cost_per_day_cents]);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const body = {
        listing_ref: { source_type: f.source_type,
                                    source_id:    f.source_id.trim() },
        region_code:            f.region_code,
        slot_position:        Number(f.slot_position),
        cost_per_day_cents: Number(f.cost_per_day_cents),
        days_purchased:      Number(f.days_purchased),
        start_at:                    new Date(f.start_at).toISOString(),
        end_at:                        new Date(f.end_at).toISOString(),
      };
      const { data: s } = await axios.post(
        `${API}/advertiser/${business_id}/marketplace-featured-slots`,
        body, { withCredentials: true });
      const { data: paid } = await axios.post(
        `${API}/advertiser/${business_id}/marketplace-featured-slots/${s.slot_id}/confirm-payment`,
        {}, { withCredentials: true });
      setCreated(paid);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(false); }
  };

  const shell = light ? "bg-white text-slate-900 border border-slate-200"
                                          : "bg-slate-900 text-white border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const input = light ? "bg-white border border-slate-200 text-slate-900"
                                            : "bg-slate-950 border border-slate-800 text-white";

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start sm:items-center justify-center p-4 overflow-auto"
              data-testid="advertiser-mfs-create-modal">
      <div className={`${shell} rounded-2xl w-full max-w-lg shadow-2xl`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b
                                        ${light ? "border-slate-200" : "border-slate-800"}`}>
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <Sparkles className="text-fuchsia-500" size={14} />
            {created ? "Featured slot live" : "Buy featured slot"}
          </h3>
          <button onClick={onClose}
                          data-testid="advertiser-mfs-create-close"
                          className={muted}><X size={18} /></button>
        </div>

        {!created && (
          <div className="p-5 space-y-3 text-sm">
            <Field label="Region" light={light}>
              <select value={f.region_code}
                              onChange={(e) => setF({ ...f, region_code: e.target.value })}
                              data-testid="advertiser-mfs-create-region"
                              className={`w-full px-3 py-2 rounded-lg ${input}`}>
                {REGIONS.map((r) => <option key={r} value={r}>{r.toUpperCase()}</option>)}
              </select>
            </Field>

            <Field label="Bind to listing (choose one)" light={light}>
              <select value={`${f.source_type}|${f.source_id}`}
                              onChange={(e) => {
                                const [st, sid] = e.target.value.split("|");
                                setF({ ...f, source_type: st, source_id: sid });
                              }}
                              data-testid="advertiser-mfs-create-listing"
                              className={`w-full px-3 py-2 rounded-lg ${input}`}>
                <option value="|">— pick a marketplace listing —</option>
                {browse.map((it) => (
                  <option key={it.listing_id}
                                  value={`${it.source_type}|${it.source_id}`}>
                    [{it.source_type}] {it.title?.slice(0, 40)} · ${(it.deal_value_cents / 100).toFixed(2)}
                  </option>
                ))}
              </select>
              {browseErr && <div className="text-[10px] text-red-400 mt-1">{browseErr}</div>}
            </Field>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Slot position (1-3)" light={light}>
                <input type="number" min="1" max="3" value={f.slot_position}
                              onChange={(e) => setF({ ...f, slot_position: e.target.value })}
                              data-testid="advertiser-mfs-create-position"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="Cost per day (¢)" light={light}>
                <input type="number" min="100" value={f.cost_per_day_cents}
                              onChange={(e) => setF({ ...f, cost_per_day_cents: e.target.value })}
                              data-testid="advertiser-mfs-create-cost"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>
            <Field label="Days purchased" light={light}>
              <input type="number" min="1" value={f.days_purchased}
                            onChange={(e) => setF({ ...f, days_purchased: e.target.value })}
                            data-testid="advertiser-mfs-create-days"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Start at" light={light}>
                <input type="datetime-local" value={f.start_at}
                              onChange={(e) => setF({ ...f, start_at: e.target.value })}
                              data-testid="advertiser-mfs-create-start"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="End at" light={light}>
                <input type="datetime-local" value={f.end_at}
                              onChange={(e) => setF({ ...f, end_at: e.target.value })}
                              data-testid="advertiser-mfs-create-end"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>

            <div className={`rounded-lg px-3 py-2 text-xs ${
                                            light ? "bg-slate-50 border border-slate-200"
                                                        : "bg-slate-950/60 border border-slate-800"}`}
                        data-testid="advertiser-mfs-create-summary">
              <div className="flex justify-between">
                <span className={muted}>Media spend</span>
                <span>${(budget.media / 100).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className={muted}>Platform fee (25%)</span>
                <span>${(budget.fee / 100).toFixed(2)}</span>
              </div>
              <div className={`flex justify-between mt-1 pt-1 border-t ${
                                              light ? "border-slate-200" : "border-slate-800"}`}>
                <span className="font-black">Total Stripe charge</span>
                <span className="font-black text-lg"
                            data-testid="advertiser-mfs-create-total">
                  ${(budget.total / 100).toFixed(2)}
                </span>
              </div>
              {budget.needsAdmin && (
                <div className="mt-1 text-amber-500 text-[11px] inline-flex items-center gap-1"
                            data-testid="advertiser-mfs-create-admin-warning">
                  <Info size={11} /> Budget ≥ $500 — admin approval required.
                </div>
              )}
            </div>
            {err && <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                                              text-red-400 text-xs px-3 py-2"
                                                data-testid="advertiser-mfs-create-error">{err}</div>}
            <button onClick={submit}
                            disabled={busy || !f.source_id || budget.total === 0}
                            data-testid="advertiser-mfs-create-submit"
                            className="w-full py-3 rounded-full text-sm font-black
                                                  bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                  disabled:opacity-40 inline-flex items-center
                                                  justify-center gap-2">
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Pay ${(budget.total / 100).toFixed(2)} + activate
            </button>
          </div>
        )}

        {created && (
          <div className="p-5" data-testid="advertiser-mfs-create-success">
            <div className="w-14 h-14 mx-auto rounded-full grid place-items-center
                                        bg-emerald-500/15 border-2 border-emerald-500 mb-3">
              <Check className="w-7 h-7 text-emerald-500" />
            </div>
            <div className="text-center text-sm font-black">
              {created.slot?.status === "active"
                ? "Slot live in the marketplace"
                : "Awaiting admin approval"}
            </div>
            <div className={`text-center text-[11px] font-mono ${muted} mt-1`}
                        data-testid="advertiser-mfs-create-id">
              {created.slot?.slot_id}
            </div>
            <div className={`text-center text-xs ${muted} mt-3`}>
              Charged ${(created.slot?.total_budget_cents / 100).toFixed(2)}
            </div>
            <button onClick={onDone}
                            data-testid="advertiser-mfs-create-done"
                            className="w-full mt-4 py-2.5 rounded-full text-xs font-black
                                                  border border-fuchsia-500 text-fuchsia-500
                                                  hover:bg-fuchsia-500/10">
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


function EmptyPanel({ light, text }) {
  return (
    <div className={`rounded-2xl p-8 text-center text-sm ${
                                    light ? "bg-slate-50 border border-slate-200 text-slate-500"
                                                : "bg-slate-900/60 border border-slate-800 text-slate-400"}`}
              data-testid="advertiser-mfs-empty">
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
