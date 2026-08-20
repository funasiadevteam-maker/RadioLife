// Phase G — AD.9 Podcast Completion Points · Advertiser page.
// Dual-design (Legacy dark + RadioLife light).  Advertisers create
// campaigns that reward listeners with points or dollar-off vouchers.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Headphones, Plus, X, Trash2, AlertTriangle, CheckCircle2,
  Coins, Ticket, Info, Sparkles,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_admin", "active", "paused",
                                    "completed", "cancelled"];


export default function AdvertiserPodcastCompletion() {
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
        `${API}/advertiser/${business_id}/podcast-completion-campaigns?${p}`,
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
                data-testid="advertiser-podcast-completion-no-advertiser">
        Loading advertiser context…
      </div>
    );
  }

  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div data-testid="advertiser-podcast-completion-page"
              data-variant={variant}>
      <div className="flex items-center justify-between mb-2">
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black inline-flex items-center gap-2 ${
                                        light ? "text-slate-900" : "text-white"}`}>
          <Headphones className="text-fuchsia-500" size={24} />
          Podcast Completion
        </h1>
        <button onClick={() => setShowCreate(true)}
                        data-testid="advertiser-pc-create"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                                                bg-fuchsia-500 text-white text-xs font-black
                                                hover:bg-fuchsia-400">
          <Plus size={14} /> New campaign
        </button>
      </div>
      <p className={`text-sm ${muted} mb-6`}>
        Reward listeners with points or dollar-off vouchers when they finish an
        episode. Fires on ≥90% completion.  Campaigns ≥ $500 total budget need
        admin approval before going live.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                          data-testid={`advertiser-pc-filter-${s || "all"}`}
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
                    data-testid="advertiser-pc-error">{err}</div>
      )}
      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}
                    data-testid="advertiser-pc-loading">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light} text="No campaigns yet — click 'New campaign' to start." />
      ) : (
        <div className="space-y-2">
          {items.map((c) => (
            <CampaignCard key={c.campaign_id} c={c} light={light}
                                        business_id={business_id} onChanged={load} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateCampaignModal light={light} business_id={business_id}
                                                  onClose={() => setShowCreate(false)}
                                                  onCreated={() => { setShowCreate(false); load(); }} />
      )}
    </div>
  );
}


function CampaignCard({ c, light, business_id, onChanged }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const statusColor = {
    draft:              muted,
    pending_admin: "text-fuchsia-500",
    active:            "text-emerald-500",
    paused:            "text-amber-500",
    completed:      muted,
    cancelled:      "text-red-500",
  }[c.status] || muted;
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  const act = async (action) => {
    setBusy(action); setErr(null);
    try {
      if (action === "confirm-payment") {
        await axios.post(
          `${API}/advertiser/${business_id}/podcast-completion-campaigns/${c.campaign_id}/confirm-payment`,
          {}, { withCredentials: true });
      } else if (action === "cancel") {
        if (!window.confirm(
              `Cancel this campaign and refund $${(c.remaining_budget_cents / 100).toFixed(2)}?`)) {
          setBusy(null); return;
        }
        await axios.post(
          `${API}/advertiser/${business_id}/podcast-completion-campaigns/${c.campaign_id}/cancel`,
          {}, { withCredentials: true });
      } else if (action === "pause" || action === "resume") {
        await axios.patch(
          `${API}/advertiser/${business_id}/podcast-completion-campaigns/${c.campaign_id}`,
          { status: action === "pause" ? "paused" : "active" },
          { withCredentials: true });
      }
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(null);
    }
  };

  const progress = c.max_total_completions > 0
    ? Math.round((c.awarded_count / c.max_total_completions) * 100) : 0;

  return (
    <div className={`${card} rounded-xl p-4`}
              data-testid={`advertiser-pc-card-${c.campaign_id}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`advertiser-pc-status-${c.campaign_id}`}>
              {c.status}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {c.currency === "bc"
                    ? <><Coins size={9} className="inline mr-0.5" />BigPoints</>
                    : <><Ticket size={9} className="inline mr-0.5" />USD voucher</>}
            </span>
          </div>
          <div className="text-sm font-black truncate">
            {c.sponsor_message || "(no message)"}
          </div>
          <div className={`text-[11px] font-mono ${muted} truncate mt-0.5`}>
            {c.podcast_id || "any podcast"} · {c.episode_id || "any episode"}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
            Reward
          </div>
          <div className="text-sm font-black">
            {c.currency === "usd"
              ? `$${(c.points_reward / 100).toFixed(2)}`
              : `${c.points_reward} pts`}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className={`flex justify-between text-[10px] font-mono ${muted}`}>
          <span>{c.awarded_count}/{c.max_total_completions} completed</span>
          <span>${(c.remaining_budget_cents / 100).toFixed(2)} / ${(c.total_budget_cents / 100).toFixed(2)}</span>
        </div>
        <div className={`h-1.5 rounded-full mt-1 overflow-hidden ${
                                        light ? "bg-slate-100" : "bg-slate-800"}`}>
          <div className="h-full bg-gradient-to-r from-fuchsia-500 to-emerald-500"
                      style={{ width: `${progress}%` }} />
        </div>
      </div>

      {err && <div className="mt-2 text-xs text-red-400">{err}</div>}

      <div className="flex flex-wrap gap-2 mt-3">
        {c.status === "draft" && (
          <button onClick={() => act("confirm-payment")} disabled={busy}
                          data-testid={`advertiser-pc-confirm-${c.campaign_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full bg-fuchsia-500 text-white
                                                hover:bg-fuchsia-400 inline-flex items-center gap-1">
            {busy === "confirm-payment" && <Loader2 className="w-3 h-3 animate-spin" />}
            Pay + activate
          </button>
        )}
        {c.status === "active" && (
          <button onClick={() => act("pause")} disabled={busy}
                          data-testid={`advertiser-pc-pause-${c.campaign_id}`}
                          className={`text-[11px] font-mono uppercase tracking-widest
                                                      px-3 py-1.5 rounded-full border ${
                                                          light ? "border-slate-300 text-slate-700 hover:bg-slate-100"
                                                                      : "border-slate-700 text-slate-300 hover:bg-slate-800/50"}`}>
            Pause
          </button>
        )}
        {c.status === "paused" && (
          <button onClick={() => act("resume")} disabled={busy}
                          data-testid={`advertiser-pc-resume-${c.campaign_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full bg-emerald-500 text-slate-950
                                                hover:bg-emerald-400">
            Resume
          </button>
        )}
        {["draft", "pending_admin", "active", "paused"].includes(c.status) && (
          <button onClick={() => act("cancel")} disabled={busy}
                          data-testid={`advertiser-pc-cancel-${c.campaign_id}`}
                          className="text-[11px] font-mono uppercase tracking-widest
                                                px-3 py-1.5 rounded-full border border-red-500/40
                                                text-red-400 hover:bg-red-500/10
                                                inline-flex items-center gap-1">
            {busy === "cancel" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                            <Trash2 className="w-3 h-3" />} Cancel + refund
          </button>
        )}
      </div>
    </div>
  );
}


function CreateCampaignModal({ light, business_id, onClose, onCreated }) {
  const nowIso = () => new Date(Date.now() - 60_000).toISOString().slice(0, 16);
  const endIso = () => new Date(Date.now() + 14 * 24 * 3600_000).toISOString().slice(0, 16);
  const [f, setF] = useState({
    podcast_id: "", episode_id: "",
    points_reward: 25, currency: "bc",
    sponsor_message: "",
    max_completions_per_user: 1, max_total_completions: 100,
    start_at: nowIso(), end_at: endIso(),
    cost_per_completion_cents: 100,
  });
  const [step, setStep] = useState("edit"); // edit | done
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);

  const totalBudget = useMemo(
    () => Number(f.cost_per_completion_cents || 0) *
                  Number(f.max_total_completions || 0),
    [f]);
  const needsAdminApproval = totalBudget >= 50_000;

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const body = {
        ...f,
        podcast_id: f.podcast_id.trim() || null,
        episode_id: f.episode_id.trim() || null,
        sponsor_message: f.sponsor_message.trim() || null,
        points_reward: Number(f.points_reward),
        max_completions_per_user: Number(f.max_completions_per_user),
        max_total_completions:      Number(f.max_total_completions),
        cost_per_completion_cents: Number(f.cost_per_completion_cents),
        start_at: new Date(f.start_at).toISOString(),
        end_at:    new Date(f.end_at).toISOString(),
      };
      const { data: campaign } = await axios.post(
        `${API}/advertiser/${business_id}/podcast-completion-campaigns`,
        body, { withCredentials: true });
      // Then confirm payment inline (Stripe pm_card_visa).
      const { data: paid } = await axios.post(
        `${API}/advertiser/${business_id}/podcast-completion-campaigns/${campaign.campaign_id}/confirm-payment`,
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
              data-testid="advertiser-pc-create-modal">
      <div className={`${shell} rounded-2xl w-full max-w-md shadow-2xl`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b
                                        ${light ? "border-slate-200" : "border-slate-800"}`}>
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <Headphones className="text-fuchsia-500" size={14} />
            New Campaign
          </h3>
          <button onClick={onClose}
                          data-testid="advertiser-pc-create-close"
                          className={muted}><X size={18} /></button>
        </div>

        {step === "edit" && (
          <div className="p-5 space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Podcast ID (optional)" light={light}>
                <input type="text" value={f.podcast_id}
                              onChange={(e) => setF({ ...f, podcast_id: e.target.value })}
                              placeholder="ch_xxx (any if blank)"
                              data-testid="advertiser-pc-create-podcast-id"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="Episode ID (optional)" light={light}>
                <input type="text" value={f.episode_id}
                              onChange={(e) => setF({ ...f, episode_id: e.target.value })}
                              placeholder="pep_xxx (any if blank)"
                              data-testid="advertiser-pc-create-episode-id"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>
            <Field label="Reward currency" light={light}>
              <select value={f.currency}
                              onChange={(e) => setF({ ...f, currency: e.target.value })}
                              data-testid="advertiser-pc-create-currency"
                              className={`w-full px-3 py-2 rounded-lg ${input}`}>
                <option value="bc">BigPoints points</option>
                <option value="usd">Dollar-off voucher (cents)</option>
              </select>
            </Field>
            <Field label={f.currency === "usd" ? "Voucher amount (cents)" : "Points reward"} light={light}>
              <input type="number" min="1" value={f.points_reward}
                            onChange={(e) => setF({ ...f, points_reward: e.target.value })}
                            data-testid="advertiser-pc-create-points-reward"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <Field label="Sponsor message (shown in listener toast)" light={light}>
              <input type="text" value={f.sponsor_message}
                            onChange={(e) => setF({ ...f, sponsor_message: e.target.value })}
                            placeholder="Thanks for listening! Visit our shop for 10% off."
                            maxLength={200}
                            data-testid="advertiser-pc-create-message"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Max per user" light={light}>
                <input type="number" min="1" value={f.max_completions_per_user}
                              onChange={(e) => setF({ ...f, max_completions_per_user: e.target.value })}
                              data-testid="advertiser-pc-create-max-per-user"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="Total completions" light={light}>
                <input type="number" min="1" value={f.max_total_completions}
                              onChange={(e) => setF({ ...f, max_total_completions: e.target.value })}
                              data-testid="advertiser-pc-create-max-total"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>
            <Field label="Cost per completion (cents advertiser pays)" light={light}>
              <input type="number" min="1" value={f.cost_per_completion_cents}
                            onChange={(e) => setF({ ...f, cost_per_completion_cents: e.target.value })}
                            data-testid="advertiser-pc-create-cost"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Start at (UTC)" light={light}>
                <input type="datetime-local" value={f.start_at}
                              onChange={(e) => setF({ ...f, start_at: e.target.value })}
                              data-testid="advertiser-pc-create-start"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="End at (UTC)" light={light}>
                <input type="datetime-local" value={f.end_at}
                              onChange={(e) => setF({ ...f, end_at: e.target.value })}
                              data-testid="advertiser-pc-create-end"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>

            <div className={`rounded-lg px-3 py-2 text-xs ${
                                            light ? "bg-slate-50 border border-slate-200"
                                                        : "bg-slate-950/60 border border-slate-800"}`}
                        data-testid="advertiser-pc-create-summary">
              <div className={muted}>Total Stripe charge</div>
              <div className="text-lg font-black">
                ${(totalBudget / 100).toFixed(2)}
              </div>
              {needsAdminApproval && (
                <div className="mt-1 text-amber-500 text-[11px] inline-flex items-center gap-1">
                  <Info size={11} /> Budget ≥ $500 — admin approval required after payment.
                </div>
              )}
            </div>
            {err && (
              <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                          text-red-400 text-xs px-3 py-2"
                          data-testid="advertiser-pc-create-error">{err}</div>
            )}
            <button onClick={submit} disabled={busy}
                            data-testid="advertiser-pc-create-submit"
                            className="w-full py-3 rounded-full text-sm font-black
                                                  bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                  disabled:opacity-40 inline-flex items-center
                                                  justify-center gap-2">
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              Pay ${(totalBudget / 100).toFixed(2)} + activate
            </button>
          </div>
        )}

        {step === "done" && created && (
          <div className="p-5" data-testid="advertiser-pc-create-success">
            <div className="w-14 h-14 mx-auto rounded-full grid place-items-center
                                        bg-emerald-500/15 border-2 border-emerald-500 mb-3">
              <CheckCircle2 className="w-7 h-7 text-emerald-500" />
            </div>
            <div className="text-center text-sm font-black">
              Campaign {created.campaign.status === "active" ? "live" : "pending admin"}
            </div>
            <div className={`text-center text-[11px] font-mono ${muted} mt-1`}>
              {created.campaign.campaign_id}
            </div>
            <div className={`mt-3 text-xs text-center ${muted}`}>
              Charged ${(created.campaign.total_budget_cents / 100).toFixed(2)} ·
              Transaction {created.transaction_id}
            </div>
            <button onClick={onCreated}
                            data-testid="advertiser-pc-create-done"
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
              data-testid="advertiser-pc-empty">
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
