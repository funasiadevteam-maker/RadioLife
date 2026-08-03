// Phase H — AD.5 Trivia Sponsorship · Advertiser page.
// Dual-design (Legacy dark + RadioLife light).  Advertisers fund a
// prize pool for a trivia room, category, or "any room" fan-out.
// Winners get BigCoin points or dollar-off vouchers.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Sparkles, Plus, X, Trash2, AlertTriangle, CheckCircle2,
  Coins, Ticket, Info, Trophy, Gift,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_admin", "active",
                                  "completed", "cancelled"];
const TARGET_TYPES = [
  { value: "any",                    label: "Any trivia room" },
  { value: "category",          label: "Category" },
  { value: "question_set",  label: "Question set" },
];
const SELECTION_MODES = [
  { value: "top_n",                    label: "Top N winners" },
  { value: "score_threshold",  label: "Everyone above a score threshold" },
];


export default function AdvertiserTriviaSponsorships() {
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
        `${API}/advertiser/${business_id}/trivia-sponsorships?${p}`,
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
                data-testid="advertiser-trivia-sponsorships-no-advertiser">
        Loading advertiser context…
      </div>
    );
  }

  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div data-testid="advertiser-trivia-sponsorships-page"
              data-variant={variant}>
      <div className="flex items-center justify-between mb-2">
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black inline-flex items-center gap-2 ${
                                        light ? "text-slate-900" : "text-white"}`}>
          <Sparkles className="text-fuchsia-500" size={24} />
          Trivia Sponsorships
        </h1>
        <button onClick={() => setShowCreate(true)}
                        data-testid="advertiser-ts-create"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                                                bg-fuchsia-500 text-white text-xs font-black
                                                hover:bg-fuchsia-400">
          <Plus size={14} /> New sponsorship
        </button>
      </div>
      <p className={`text-sm ${muted} mb-6`}>
        Fund a prize pool for trivia room winners.  Prepay via Stripe.
        Sponsorships ≥ $500 total budget need admin approval before going live.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                          data-testid={`advertiser-ts-filter-${s || "all"}`}
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

      {err && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                      text-red-400 text-xs px-3 py-2 mb-3"
                    data-testid="advertiser-ts-error">{err}</div>
      )}
      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}
                    data-testid="advertiser-ts-loading">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light}
                              text="No sponsorships yet — click 'New sponsorship' to fund your first prize pool." />
      ) : (
        <div className="space-y-2">
          {items.map((s) => (
            <SponsorshipCard key={s.sponsorship_id} s={s} light={light}
                                                business_id={business_id} onChanged={load} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateSponsorshipModal light={light} business_id={business_id}
                                                            onClose={() => setShowCreate(false)}
                                                            onCreated={() => { setShowCreate(false); load(); }} />
      )}
    </div>
  );
}


function SponsorshipCard({ s, light, business_id, onChanged }) {
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

  const act = async (action) => {
    setBusy(action); setErr(null);
    try {
      if (action === "confirm-payment") {
        await axios.post(
          `${API}/advertiser/${business_id}/trivia-sponsorships/${s.sponsorship_id}/confirm-payment`,
          {}, { withCredentials: true });
      } else if (action === "cancel") {
        const feePct = 25;
        const unspentFee = Math.round((s.remaining_budget_cents || 0) * feePct / 100);
        const refundTotal = (s.remaining_budget_cents || 0) + unspentFee;
        if (!window.confirm(
              `Cancel this sponsorship and refund $${(refundTotal / 100).toFixed(2)}?`)) {
          setBusy(null); return;
        }
        await axios.post(
          `${API}/advertiser/${business_id}/trivia-sponsorships/${s.sponsorship_id}/cancel`,
          {}, { withCredentials: true });
      }
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(null);
    }
  };

  const progress = s.max_total_awards > 0
    ? Math.round((s.awarded_count / s.max_total_awards) * 100) : 0;
  const targetLabel = s.sponsor_target_type === "any"
    ? "Any room"
    : `${s.sponsor_target_type} · ${s.target_id || "-"}`;

  return (
    <div className={`${card} rounded-xl p-4`}
              data-testid={`advertiser-ts-card-${s.sponsorship_id}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`advertiser-ts-status-${s.sponsorship_id}`}>
              {s.status}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {targetLabel}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {s.winner_selection === "top_n"
                    ? "top N"
                    : `≥ ${s.score_threshold || 0} pts`}
            </span>
          </div>
          <div className="text-sm font-black truncate inline-flex items-center gap-1.5">
            <Trophy size={12} className="text-fuchsia-500" />
            {s.display_name || "(untitled)"}
          </div>
          {s.tagline && (
            <div className={`text-[11px] ${muted} truncate mt-0.5`}>
              {s.tagline}
            </div>
          )}
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
            Prize tiers
          </div>
          <div className="text-sm font-black" data-testid={`advertiser-ts-tiers-${s.sponsorship_id}`}>
            {(s.prize_pool || []).length}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className={`flex justify-between text-[10px] font-mono ${muted}`}>
          <span>{s.awarded_count}/{s.max_total_awards} awarded</span>
          <span>${(s.remaining_budget_cents / 100).toFixed(2)} / ${(s.cost_cents / 100).toFixed(2)}</span>
        </div>
        <div className={`h-1.5 rounded-full mt-1 overflow-hidden ${
                                        light ? "bg-slate-100" : "bg-slate-800"}`}>
          <div className="h-full bg-gradient-to-r from-fuchsia-500 to-emerald-500"
                      style={{ width: `${progress}%` }} />
        </div>
      </div>

      <div className={`mt-3 flex flex-wrap gap-1.5 text-[10px] font-mono ${muted}`}>
        {(s.prize_pool || []).slice(0, 4).map((p) => (
          <span key={p.rank}
                      className={`px-2 py-0.5 rounded-full border ${
                                            light ? "border-slate-200" : "border-slate-700"}`}
                      data-testid={`advertiser-ts-prize-${s.sponsorship_id}-${p.rank}`}>
            #{p.rank}: {p.currency === "usd"
              ? `$${(p.points_reward / 100).toFixed(2)}`
              : `${p.points_reward} bc`}
            {p.quantity > 1 && ` ×${p.quantity}`}
          </span>
        ))}
      </div>

      {err && <div className="mt-2 text-xs text-red-400"
                                  data-testid={`advertiser-ts-error-${s.sponsorship_id}`}>{err}</div>}

      <div className="flex flex-wrap gap-2 mt-3">
        {s.status === "draft" && (
          <button onClick={() => act("confirm-payment")} disabled={busy}
                          data-testid={`advertiser-ts-confirm-${s.sponsorship_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full bg-fuchsia-500 text-white
                                                hover:bg-fuchsia-400 inline-flex items-center gap-1">
            {busy === "confirm-payment" && <Loader2 className="w-3 h-3 animate-spin" />}
            Pay + activate (${(s.cost_cents / 100).toFixed(2)})
          </button>
        )}
        {["draft", "pending_admin", "active"].includes(s.status) && (
          <button onClick={() => act("cancel")} disabled={busy}
                          data-testid={`advertiser-ts-cancel-${s.sponsorship_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full border border-red-500/40
                                                text-red-400 hover:bg-red-500/10
                                                inline-flex items-center gap-1">
            {busy === "cancel" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                            <Trash2 className="w-3 h-3" />} Cancel + refund
          </button>
        )}
      </div>

      {s.status === "cancelled" && s.refunded_amount_cents > 0 && (
        <div className={`mt-2 text-[10px] font-mono ${muted}`}
                    data-testid={`advertiser-ts-refunded-${s.sponsorship_id}`}>
          Refunded ${(s.refunded_amount_cents / 100).toFixed(2)}
        </div>
      )}
    </div>
  );
}


function CreateSponsorshipModal({ light, business_id, onClose, onCreated }) {
  const nowIso = () => new Date(Date.now() - 60_000).toISOString().slice(0, 16);
  const endIso = () => new Date(Date.now() + 14 * 24 * 3600_000).toISOString().slice(0, 16);
  const [f, setF] = useState({
    sponsor_target_type:    "any",
    target_id:                        "",
    display_name:                  "",
    tagline:                            "",
    winner_selection:            "top_n",
    score_threshold:              50,
    start_at:                          nowIso(),
    end_at:                              endIso(),
  });
  const [prizePool, setPrizePool] = useState([
    { rank: 1, points_reward: 200, currency: "bc", quantity: 1 },
  ]);
  const [step, setStep] = useState("edit"); // edit | done
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);

  // Live budget preview — mirrors _compute_costs in the backend.
  //   prize_cost += reward * quantity (BigCoin: 1 pt = 1¢; USD: reward already cents)
  //   fee = 25% platform take
  const budget = useMemo(() => {
    let prizeCost = 0;
    let maxAwards = 0;
    for (const p of prizePool) {
      const r = Number(p.points_reward || 0);
      const q = Number(p.quantity || 1);
      prizeCost += r * q;
      maxAwards += q;
    }
    const fee = Math.floor(prizeCost * 0.25);
    return {
      prizeCost, fee,
      total: prizeCost + fee,
      maxAwards,
      needsAdmin: (prizeCost + fee) >= 50_000,
    };
  }, [prizePool]);

  const addTier = () => {
    const nextRank = (prizePool[prizePool.length - 1]?.rank || 0) + 1;
    setPrizePool([...prizePool, {
      rank: nextRank, points_reward: 100, currency: "bc", quantity: 1,
    }]);
  };
  const removeTier = (i) => {
    if (prizePool.length <= 1) return;
    setPrizePool(prizePool.filter((_, idx) => idx !== i));
  };
  const updateTier = (i, patch) => {
    const copy = [...prizePool];
    copy[i] = { ...copy[i], ...patch };
    setPrizePool(copy);
  };

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const body = {
        sponsor_target_type:  f.sponsor_target_type,
        target_id:                      f.target_id.trim() || null,
        display_name:                f.display_name.trim(),
        tagline:                        f.tagline.trim() || null,
        winner_selection:          f.winner_selection,
        score_threshold:            f.winner_selection === "score_threshold"
                                                          ? Number(f.score_threshold) : null,
        prize_pool:                    prizePool.map((p) => ({
          rank:            Number(p.rank),
          points_reward: Number(p.points_reward),
          currency:      p.currency,
          quantity:      Number(p.quantity || 1),
        })),
        start_at:                        new Date(f.start_at).toISOString(),
        end_at:                            new Date(f.end_at).toISOString(),
      };
      const { data: sponsorship } = await axios.post(
        `${API}/advertiser/${business_id}/trivia-sponsorships`,
        body, { withCredentials: true });
      // Then confirm payment inline (Stripe pm_card_visa).
      const { data: paid } = await axios.post(
        `${API}/advertiser/${business_id}/trivia-sponsorships/${sponsorship.sponsorship_id}/confirm-payment`,
        {}, { withCredentials: true });
      setCreated(paid);
      setStep("done");
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
                                  flex items-start sm:items-center justify-center p-4 overflow-auto"
              data-testid="advertiser-ts-create-modal">
      <div className={`${shell} rounded-2xl w-full max-w-lg shadow-2xl`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b
                                        ${light ? "border-slate-200" : "border-slate-800"}`}>
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <Sparkles className="text-fuchsia-500" size={14} />
            New Trivia Sponsorship
          </h3>
          <button onClick={onClose}
                          data-testid="advertiser-ts-create-close"
                          className={muted}><X size={18} /></button>
        </div>

        {step === "edit" && (
          <div className="p-5 space-y-3 text-sm">
            <Field label="Sponsor display name" light={light}>
              <input type="text" value={f.display_name}
                            onChange={(e) => setF({ ...f, display_name: e.target.value })}
                            placeholder="Acme Coffee Co"
                            maxLength={80}
                            data-testid="advertiser-ts-create-display-name"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <Field label="Tagline (optional)" light={light}>
              <input type="text" value={f.tagline}
                            onChange={(e) => setF({ ...f, tagline: e.target.value })}
                            placeholder="Fueling your trivia champs"
                            maxLength={120}
                            data-testid="advertiser-ts-create-tagline"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Target scope" light={light}>
                <select value={f.sponsor_target_type}
                                onChange={(e) => setF({ ...f, sponsor_target_type: e.target.value })}
                                data-testid="advertiser-ts-create-target-type"
                                className={`w-full px-3 py-2 rounded-lg ${input}`}>
                  {TARGET_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </Field>
              <Field label={f.sponsor_target_type === "any"
                                          ? "Target ID (not required)"
                                          : "Target ID (category or set)"}
                            light={light}>
                <input type="text" value={f.target_id}
                              onChange={(e) => setF({ ...f, target_id: e.target.value })}
                              placeholder={f.sponsor_target_type === "any"
                                                            ? "leave blank" : "cat_xxx"}
                              disabled={f.sponsor_target_type === "any"}
                              data-testid="advertiser-ts-create-target-id"
                              className={`w-full px-3 py-2 rounded-lg ${input} disabled:opacity-40`} />
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Winner selection" light={light}>
                <select value={f.winner_selection}
                                onChange={(e) => setF({ ...f, winner_selection: e.target.value })}
                                data-testid="advertiser-ts-create-selection"
                                className={`w-full px-3 py-2 rounded-lg ${input}`}>
                  {SELECTION_MODES.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </Field>
              {f.winner_selection === "score_threshold" && (
                <Field label="Min score (pts)" light={light}>
                  <input type="number" min="0" value={f.score_threshold}
                                onChange={(e) => setF({ ...f, score_threshold: e.target.value })}
                                data-testid="advertiser-ts-create-threshold"
                                className={`w-full px-3 py-2 rounded-lg ${input}`} />
                </Field>
              )}
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Start at (UTC)" light={light}>
                <input type="datetime-local" value={f.start_at}
                              onChange={(e) => setF({ ...f, start_at: e.target.value })}
                              data-testid="advertiser-ts-create-start"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="End at (UTC)" light={light}>
                <input type="datetime-local" value={f.end_at}
                              onChange={(e) => setF({ ...f, end_at: e.target.value })}
                              data-testid="advertiser-ts-create-end"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
                  Prize pool ({prizePool.length} tier{prizePool.length !== 1 ? "s" : ""})
                </label>
                <button onClick={addTier}
                                data-testid="advertiser-ts-create-add-tier"
                                className="text-[10px] font-mono uppercase tracking-widest
                                                      px-2 py-0.5 rounded-full border border-fuchsia-500/40
                                                      text-fuchsia-500 hover:bg-fuchsia-500/10">
                  + Add tier
                </button>
              </div>
              <div className="space-y-1.5">
                {prizePool.map((p, i) => (
                  <div key={i}
                              className={`grid grid-cols-12 gap-1.5 items-center p-2 rounded-lg ${
                                                              light ? "bg-slate-50" : "bg-slate-950/40"}`}
                              data-testid={`advertiser-ts-create-tier-${i}`}>
                    <input type="number" min="1" max="100" value={p.rank}
                                  onChange={(e) => updateTier(i, { rank: e.target.value })}
                                  data-testid={`advertiser-ts-create-tier-${i}-rank`}
                                  aria-label="rank"
                                  className={`col-span-2 px-2 py-1.5 text-xs rounded ${input}`} />
                    <input type="number" min="1" value={p.points_reward}
                                  onChange={(e) => updateTier(i, { points_reward: e.target.value })}
                                  data-testid={`advertiser-ts-create-tier-${i}-reward`}
                                  aria-label="reward"
                                  className={`col-span-4 px-2 py-1.5 text-xs rounded ${input}`} />
                    <select value={p.currency}
                                    onChange={(e) => updateTier(i, { currency: e.target.value })}
                                    data-testid={`advertiser-ts-create-tier-${i}-currency`}
                                    aria-label="currency"
                                    className={`col-span-3 px-1 py-1.5 text-xs rounded ${input}`}>
                      <option value="bc">BigCoin</option>
                      <option value="usd">USD¢</option>
                    </select>
                    <input type="number" min="1" max="1000" value={p.quantity}
                                  onChange={(e) => updateTier(i, { quantity: e.target.value })}
                                  data-testid={`advertiser-ts-create-tier-${i}-quantity`}
                                  aria-label="quantity"
                                  className={`col-span-2 px-2 py-1.5 text-xs rounded ${input}`} />
                    <button onClick={() => removeTier(i)}
                                    disabled={prizePool.length <= 1}
                                    data-testid={`advertiser-ts-create-tier-${i}-remove`}
                                    aria-label="remove tier"
                                    className="col-span-1 flex items-center justify-center
                                                                text-red-400 hover:text-red-300 disabled:opacity-30">
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
                <div className={`grid grid-cols-12 gap-1.5 text-[10px] font-mono ${muted} px-2`}>
                  <span className="col-span-2">rank</span>
                  <span className="col-span-4">reward</span>
                  <span className="col-span-3">currency</span>
                  <span className="col-span-2">qty</span>
                </div>
              </div>
            </div>

            <div className={`rounded-lg px-3 py-2 text-xs ${
                                            light ? "bg-slate-50 border border-slate-200"
                                                        : "bg-slate-950/60 border border-slate-800"}`}
                        data-testid="advertiser-ts-create-summary">
              <div className="flex justify-between">
                <span className={muted}>Prize cost</span>
                <span>${(budget.prizeCost / 100).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className={muted}>Platform fee (25%)</span>
                <span>${(budget.fee / 100).toFixed(2)}</span>
              </div>
              <div className={`flex justify-between mt-1 pt-1 border-t ${
                                              light ? "border-slate-200" : "border-slate-800"}`}>
                <span className="font-black">Total Stripe charge</span>
                <span className="font-black text-lg" data-testid="advertiser-ts-create-total">
                  ${(budget.total / 100).toFixed(2)}
                </span>
              </div>
              <div className={`text-[10px] font-mono ${muted} mt-1`}>
                Up to {budget.maxAwards} winner{budget.maxAwards !== 1 ? "s" : ""} across all tiers.
              </div>
              {budget.needsAdmin && (
                <div className="mt-1 text-amber-500 text-[11px] inline-flex items-center gap-1"
                            data-testid="advertiser-ts-create-admin-warning">
                  <Info size={11} /> Budget ≥ $500 — admin approval required after payment.
                </div>
              )}
            </div>
            {err && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                          text-red-400 text-xs px-3 py-2"
                          data-testid="advertiser-ts-create-error">{err}</div>
            )}
            <button onClick={submit}
                            disabled={busy || !f.display_name.trim() || budget.prizeCost === 0}
                            data-testid="advertiser-ts-create-submit"
                            className="w-full py-3 rounded-full text-sm font-black
                                                  bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                  disabled:opacity-40 inline-flex items-center
                                                  justify-center gap-2">
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Pay ${(budget.total / 100).toFixed(2)} + activate
            </button>
          </div>
        )}

        {step === "done" && created && (
          <div className="p-5" data-testid="advertiser-ts-create-success">
            <div className="w-14 h-14 mx-auto rounded-full grid place-items-center
                                        bg-emerald-500/15 border-2 border-emerald-500 mb-3">
              <CheckCircle2 className="w-7 h-7 text-emerald-500" />
            </div>
            <div className="text-center text-sm font-black">
              Sponsorship {created.sponsorship?.status === "active"
                                              ? "live" : "pending admin"}
            </div>
            <div className={`text-center text-[11px] font-mono ${muted} mt-1`}
                        data-testid="advertiser-ts-create-sponsorship-id">
              {created.sponsorship?.sponsorship_id}
            </div>
            <div className={`mt-3 text-xs text-center ${muted}`}>
              Charged ${(created.sponsorship?.cost_cents / 100).toFixed(2)} ·
              Transaction {created.transaction_id}
            </div>
            <div className={`mt-3 text-xs text-center inline-flex items-center gap-1.5 ${muted}`}>
              <Gift size={12} className="text-fuchsia-500" />
              Bind to a room via the trivia lobby&apos;s sponsorship field on room create.
            </div>
            <button onClick={onCreated}
                            data-testid="advertiser-ts-create-done"
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
              data-testid="advertiser-ts-empty">
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
