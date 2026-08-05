// Phase I — M1 Sponsored AI-RJ Reads · Advertiser dashboard.
// Dual-design (Legacy dark + RadioLife light).  End-to-end wizard:
//     persona + stations + product spec → auto-draft (LLM) OR paste
//     script → edit → submit (moderation gate) → Stripe prepay →
//     ElevenLabs TTS render → LIVE on the AI-RJ stream.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Loader2, Sparkles, Plus, X, PlayCircle, Volume2, Trash2,
  Check, Info, Radio, MessageSquare,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_moderation", "pending_admin",
                                  "active", "completed", "cancelled", "rejected"];
const DISCLOSURE_PREFIXES = ["Paid sponsorship", "Sponsored by", "Presented by"];


export default function AdvertiserRJSponsoredReads() {
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
        `${API}/advertiser/${business_id}/rj-sponsored-reads?${p}`,
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
                data-testid="advertiser-rjsr-no-advertiser">
        Loading advertiser context…
      </div>
    );
  }

  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div data-testid="advertiser-rjsr-page" data-variant={variant}>
      <div className="flex items-center justify-between mb-2">
        <h1 className={`text-2xl md:text-3xl xl:text-4xl font-black inline-flex items-center gap-2 ${
                                        light ? "text-slate-900" : "text-white"}`}>
          <Radio className="text-fuchsia-500" size={24} />
          Sponsored AI-RJ Reads
        </h1>
        <button onClick={() => setShowCreate(true)}
                        data-testid="advertiser-rjsr-create"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full
                                                bg-fuchsia-500 text-white text-xs font-black
                                                hover:bg-fuchsia-400">
          <Plus size={14} /> New read
        </button>
      </div>
      <p className={`text-sm ${muted} mb-6`}>
        Buy short, scripted host reads voiced by a RadioLife persona.  Reads
        get injected between songs on the AI-RJ stream on the stations
        you pick.  Total budget = plays × cost/play + 30% platform fee.
      </p>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                          data-testid={`advertiser-rjsr-filter-${s || "all"}`}
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
                    data-testid="advertiser-rjsr-error">{err}</div>
      )}

      {items === null ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}
                    data-testid="advertiser-rjsr-loading">
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : items.length === 0 ? (
        <EmptyPanel light={light}
                              text="No sponsored reads yet — click 'New read' to create one." />
      ) : (
        <div className="space-y-2">
          {items.map((s) => (
            <ReadCard key={s.sponsored_read_id} s={s} light={light}
                                      business_id={business_id} onChanged={load} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateWizard light={light} business_id={business_id}
                                    onClose={() => setShowCreate(false)}
                                    onDone={() => { setShowCreate(false); load(); }} />
      )}
    </div>
  );
}


function ReadCard({ s, light, business_id, onChanged }) {
  const card = light ? "bg-white border border-slate-200 shadow-sm"
                                          : "bg-slate-900/60 border border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";
  const statusColor = {
    draft:                          muted,
    pending_moderation:  "text-fuchsia-500",
    pending_admin:            "text-fuchsia-500",
    active:                        "text-emerald-500",
    completed:                  muted,
    cancelled:                  "text-red-500",
    rejected:                    "text-red-500",
  }[s.status] || muted;
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  const cancel = async () => {
    if (!window.confirm(
          `Cancel and refund remaining $${((s.remaining_budget_cents || 0) * 1.3 / 100).toFixed(2)}?`))
      return;
    setBusy("cancel"); setErr(null);
    try {
      await axios.post(
        `${API}/advertiser/${business_id}/rj-sponsored-reads/${s.sponsored_read_id}/cancel`,
        { reason: "advertiser_cancelled" },
        { withCredentials: true });
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(null);
    }
  };

  const progress = s.plays_target > 0
    ? Math.round((s.plays_delivered / s.plays_target) * 100) : 0;

  return (
    <div className={`${card} rounded-xl p-4`}
              data-testid={`advertiser-rjsr-card-${s.sponsored_read_id}`}>
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`advertiser-rjsr-status-${s.sponsored_read_id}`}>
              {s.status}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {s.persona_name || s.persona_id}
            </span>
            <span className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              · {s.any_station ? "any station" : `${(s.station_ids || []).length} stations`}
            </span>
          </div>
          <div className="text-sm font-black truncate inline-flex items-center gap-1.5">
            <MessageSquare size={12} className="text-fuchsia-500" />
            {s.final_script || s.script_body || "(script pending)"}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
            Total charge
          </div>
          <div className="text-sm font-black" data-testid={`advertiser-rjsr-cost-${s.sponsored_read_id}`}>
            ${(s.total_cost_cents / 100).toFixed(2)}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <div className={`flex justify-between text-[10px] font-mono ${muted}`}>
          <span>{s.plays_delivered}/{s.plays_target} plays</span>
          <span>${(s.remaining_budget_cents / 100).toFixed(2)} remaining</span>
        </div>
        <div className={`h-1.5 rounded-full mt-1 overflow-hidden ${
                                        light ? "bg-slate-100" : "bg-slate-800"}`}>
          <div className="h-full bg-gradient-to-r from-fuchsia-500 to-emerald-500"
                      style={{ width: `${progress}%` }} />
        </div>
      </div>

      {s.audio_url && (
        <div className="mt-3">
          <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}
                                          mb-1 inline-flex items-center gap-1`}>
            <Volume2 size={11} /> {s.duration_seconds
              ? `${s.duration_seconds.toFixed(1)}s preview` : "Preview"}
          </div>
          <audio controls src={s.audio_url} className="w-full"
                          data-testid={`advertiser-rjsr-audio-${s.sponsored_read_id}`} />
        </div>
      )}

      {err && <div className="mt-2 text-xs text-red-400"
                                  data-testid={`advertiser-rjsr-cancel-error-${s.sponsored_read_id}`}>
        {err}</div>}

      <div className="flex flex-wrap gap-2 mt-3">
        {["pending_moderation", "pending_admin", "active", "paused"]
              .includes(s.status) && (
          <button onClick={cancel} disabled={!!busy}
                          data-testid={`advertiser-rjsr-cancel-${s.sponsored_read_id}`}
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
                      data-testid={`advertiser-rjsr-refunded-${s.sponsored_read_id}`}>
            Refunded ${(s.refunded_amount_cents / 100).toFixed(2)}
          </div>
        )}
        {s.status === "rejected" && (
          <div className="text-[10px] font-mono text-red-400"
                      data-testid={`advertiser-rjsr-rejected-${s.sponsored_read_id}`}>
            {s.cancel_reason === "moderation_flagged"
              ? "Rejected by automatic moderation"
              : `Rejected: ${s.cancel_reason || "unknown"}`}
          </div>
        )}
      </div>
    </div>
  );
}


// ─── Create wizard (multi-step: pick → draft → submit + pay) ─────
function CreateWizard({ light, business_id, onClose, onDone }) {
  const [step, setStep] = useState("pick"); // pick | edit | done
  const [personas, setPersonas] = useState(null);
  const [stations, setStations] = useState(null);
  const [f, setF] = useState({
    persona_id:                "",
    any_station:              true,
    station_ids:              [],
    disclosure_prefix:  "Paid sponsorship",
    product_name:            "",
    key_message:              "",
    cta:                            "",
    plays_target:            50,
    cost_per_play_cents: 10,
    start_at:                    new Date(Date.now() - 60_000).toISOString().slice(0, 16),
    end_at:                      new Date(Date.now() + 14 * 24 * 3600_000).toISOString().slice(0, 16),
    auto_draft:              true,
    script_body:              "",
  });
  const [draft, setDraft] = useState({ sponsored_read_id: null,
                                                                              script_body: "",
                                                                              final_script: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [created, setCreated] = useState(null);

  useEffect(() => {
    // Load personas (admin-open endpoint returns active list).
    (async () => {
      try {
        const r = await axios.get(`${API}/rj/personas`,
                                                                { withCredentials: true });
        setPersonas(r.data.items || r.data.personas || []);
      } catch {
        setPersonas([]);
      }
    })();
    (async () => {
      try {
        const r = await axios.get(`${API}/radio/stations?limit=50`,
                                                                { withCredentials: true });
        const items = r.data.items || r.data.stations || r.data || [];
        setStations(items.slice(0, 30));
      } catch {
        setStations([]);
      }
    })();
  }, []);

  const budget = useMemo(() => {
    const prize = Number(f.plays_target || 0) * Number(f.cost_per_play_cents || 0);
    const fee = Math.floor(prize * 0.3);
    return {
      prizeCost: prize, fee, total: prize + fee,
      needsAdmin: (prize + fee) >= 50_000,
    };
  }, [f.plays_target, f.cost_per_play_cents]);

  const proceedToEdit = async () => {
    setBusy(true); setErr(null);
    try {
      const body = {
        persona_id:                    f.persona_id,
        any_station:                  f.any_station,
        station_ids:                  f.any_station ? [] : f.station_ids,
        disclosure_prefix:      f.disclosure_prefix,
        plays_target:                Number(f.plays_target),
        cost_per_play_cents:  Number(f.cost_per_play_cents),
        start_at:                        new Date(f.start_at).toISOString(),
        end_at:                            new Date(f.end_at).toISOString(),
        script_body:                  f.auto_draft ? "auto" : f.script_body,
        product_name:                f.product_name,
        key_message:                  f.key_message,
        cta:                                f.cta,
      };
      const { data } = await axios.post(
        `${API}/advertiser/${business_id}/rj-sponsored-reads`,
        body, { withCredentials: true });
      setDraft({
        sponsored_read_id: data.sponsored_read_id,
        script_body:            data.script_body,
        final_script:            data.script_body,
      });
      setStep("edit");
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  };

  const submitAndPay = async () => {
    setBusy(true); setErr(null);
    try {
      const submitted = await axios.post(
        `${API}/advertiser/${business_id}/rj-sponsored-reads/${draft.sponsored_read_id}/submit`,
        { final_script: draft.final_script.trim() },
        { withCredentials: true });
      if (submitted.data?.status === "rejected") {
        setErr(`moderation_${submitted.data.cancel_reason}`);
        setCreated({ sponsored_read: submitted.data });
        setStep("done");
        return;
      }
      const paid = await axios.post(
        `${API}/advertiser/${business_id}/rj-sponsored-reads/${draft.sponsored_read_id}/confirm-payment`,
        {}, { withCredentials: true });
      setCreated(paid.data);
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
              data-testid="advertiser-rjsr-create-modal">
      <div className={`${shell} rounded-2xl w-full max-w-lg shadow-2xl`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b
                                        ${light ? "border-slate-200" : "border-slate-800"}`}>
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <Sparkles className="text-fuchsia-500" size={14} />
            New sponsored read · {step === "pick" ? "1. Setup"
              : step === "edit" ? "2. Copy & pay" : "3. Live"}
          </h3>
          <button onClick={onClose}
                          data-testid="advertiser-rjsr-create-close"
                          className={muted}><X size={18} /></button>
        </div>

        {step === "pick" && (
          <div className="p-5 space-y-3 text-sm">
            <Field label="Persona (voice)" light={light}>
              <select value={f.persona_id}
                              onChange={(e) => setF({ ...f, persona_id: e.target.value })}
                              data-testid="advertiser-rjsr-create-persona"
                              className={`w-full px-3 py-2 rounded-lg ${input}`}>
                <option value="">Pick a persona…</option>
                {(personas || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · {p.personality || p.voice_provider}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Station targeting" light={light}>
              <label className="text-xs inline-flex items-center gap-2">
                <input type="checkbox" checked={f.any_station}
                              onChange={(e) => setF({ ...f, any_station: e.target.checked })}
                              data-testid="advertiser-rjsr-create-any-station" />
                Fan out to every station
              </label>
            </Field>
            {!f.any_station && (
              <div className={`max-h-32 overflow-auto rounded-lg p-2 space-y-1 ${
                                              light ? "bg-slate-50 border border-slate-200"
                                                          : "bg-slate-950 border border-slate-800"}`}
                        data-testid="advertiser-rjsr-create-station-picker">
                {(stations || []).map((s) => {
                  const sid = s.station_id || s.id;
                  const on = f.station_ids.includes(sid);
                  return (
                    <label key={sid} className="text-xs flex items-center gap-2">
                      <input type="checkbox" checked={on}
                                    onChange={() => {
                                      setF({ ...f, station_ids: on
                                                ? f.station_ids.filter((x) => x !== sid)
                                                : [...f.station_ids, sid] });
                                    }} />
                      <span className="truncate">{s.name || s.station_name || sid}</span>
                    </label>
                  );
                })}
                {(stations || []).length === 0 && (
                  <div className={muted}>No stations available.</div>
                )}
              </div>
            )}

            <div className="grid grid-cols-2 gap-2">
              <Field label="Plays target" light={light}>
                <input type="number" min="10" value={f.plays_target}
                              onChange={(e) => setF({ ...f, plays_target: e.target.value })}
                              data-testid="advertiser-rjsr-create-plays"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="Cost per play (¢)" light={light}>
                <input type="number" min="5" value={f.cost_per_play_cents}
                              onChange={(e) => setF({ ...f, cost_per_play_cents: e.target.value })}
                              data-testid="advertiser-rjsr-create-cpp"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Disclosure phrase (mandatory)" light={light}>
                <select value={f.disclosure_prefix}
                                onChange={(e) => setF({ ...f, disclosure_prefix: e.target.value })}
                                data-testid="advertiser-rjsr-create-disclosure"
                                className={`w-full px-3 py-2 rounded-lg ${input}`}>
                  {DISCLOSURE_PREFIXES.map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </Field>
              <Field label="Auto-draft with AI?" light={light}>
                <label className="text-xs inline-flex items-center gap-2 mt-2">
                  <input type="checkbox" checked={f.auto_draft}
                                onChange={(e) => setF({ ...f, auto_draft: e.target.checked })}
                                data-testid="advertiser-rjsr-create-auto" />
                  {f.auto_draft ? "AI-drafted" : "I'll write the script"}
                </label>
              </Field>
            </div>

            <Field label="Product / brand name" light={light}>
              <input type="text" value={f.product_name}
                            onChange={(e) => setF({ ...f, product_name: e.target.value })}
                            maxLength={60}
                            data-testid="advertiser-rjsr-create-product"
                            placeholder="Big Coffee Roasters"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <Field label="Key message" light={light}>
              <input type="text" value={f.key_message}
                            onChange={(e) => setF({ ...f, key_message: e.target.value })}
                            maxLength={120}
                            data-testid="advertiser-rjsr-create-key-msg"
                            placeholder="Fresh arabica beans, hand-roasted in Dubai"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>
            <Field label="Call-to-action" light={light}>
              <input type="text" value={f.cta}
                            onChange={(e) => setF({ ...f, cta: e.target.value })}
                            maxLength={80}
                            data-testid="advertiser-rjsr-create-cta"
                            placeholder="Order online today"
                            className={`w-full px-3 py-2 rounded-lg ${input}`} />
            </Field>

            <div className="grid grid-cols-2 gap-2">
              <Field label="Start at" light={light}>
                <input type="datetime-local" value={f.start_at}
                              onChange={(e) => setF({ ...f, start_at: e.target.value })}
                              data-testid="advertiser-rjsr-create-start"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
              <Field label="End at" light={light}>
                <input type="datetime-local" value={f.end_at}
                              onChange={(e) => setF({ ...f, end_at: e.target.value })}
                              data-testid="advertiser-rjsr-create-end"
                              className={`w-full px-3 py-2 rounded-lg ${input}`} />
              </Field>
            </div>

            <div className={`rounded-lg px-3 py-2 text-xs ${
                                            light ? "bg-slate-50 border border-slate-200"
                                                        : "bg-slate-950/60 border border-slate-800"}`}
                        data-testid="advertiser-rjsr-create-summary">
              <div className="flex justify-between">
                <span className={muted}>Media spend</span>
                <span>${(budget.prizeCost / 100).toFixed(2)}</span>
              </div>
              <div className="flex justify-between">
                <span className={muted}>Platform fee (30%)</span>
                <span>${(budget.fee / 100).toFixed(2)}</span>
              </div>
              <div className={`flex justify-between mt-1 pt-1 border-t ${
                                              light ? "border-slate-200" : "border-slate-800"}`}>
                <span className="font-black">Total Stripe charge</span>
                <span className="font-black text-lg"
                            data-testid="advertiser-rjsr-create-total">
                  ${(budget.total / 100).toFixed(2)}
                </span>
              </div>
              {budget.needsAdmin && (
                <div className="mt-1 text-amber-500 text-[11px] inline-flex items-center gap-1"
                            data-testid="advertiser-rjsr-create-admin-warning">
                  <Info size={11} /> Budget ≥ $500 — admin approval required after payment.
                </div>
              )}
            </div>

            {err && <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                                              text-red-400 text-xs px-3 py-2"
                                                data-testid="advertiser-rjsr-create-error">{err}</div>}
            <button onClick={proceedToEdit} disabled={busy || !f.persona_id
                                                                          || (f.auto_draft && !f.product_name.trim())
                                                                          || (!f.any_station && f.station_ids.length === 0)}
                            data-testid="advertiser-rjsr-create-next"
                            className="w-full py-3 rounded-full text-sm font-black
                                                  bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                  disabled:opacity-40 inline-flex items-center
                                                  justify-center gap-2">
              {busy && <Loader2 className="w-4 h-4 animate-spin" />}
              {f.auto_draft ? "AI-draft the script" : "Write the script"}
            </button>
          </div>
        )}

        {step === "edit" && (
          <div className="p-5 space-y-3 text-sm">
            <div className={`text-[10px] font-mono uppercase tracking-widest ${muted}`}>
              Draft script — edit as needed.  The first sentence MUST
              contain &ldquo;{f.disclosure_prefix}&rdquo;.
            </div>
            <textarea value={draft.final_script}
                                    onChange={(e) => setDraft({ ...draft, final_script: e.target.value })}
                                    data-testid="advertiser-rjsr-create-script"
                                    rows={7} maxLength={600}
                                    className={`w-full px-3 py-2 rounded-lg text-sm ${input}`} />
            <div className={`text-[10px] font-mono ${muted}`}>
              {draft.final_script.length} / 600 characters
            </div>
            {err && <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                                              text-red-400 text-xs px-3 py-2"
                                                data-testid="advertiser-rjsr-create-edit-error">{err}</div>}
            <div className="flex gap-2">
              <button onClick={() => setStep("pick")}
                              className={`flex-1 py-2.5 rounded-full text-xs font-black
                                                      border ${light ? "border-slate-300 text-slate-700"
                                                                                : "border-slate-700 text-slate-400"}`}>
                Back
              </button>
              <button onClick={submitAndPay} disabled={busy || draft.final_script.length < 20}
                              data-testid="advertiser-rjsr-create-submit"
                              className="flex-[2] py-2.5 rounded-full text-xs font-black
                                                    bg-fuchsia-500 text-white hover:bg-fuchsia-400
                                                    disabled:opacity-40 inline-flex items-center
                                                    justify-center gap-2">
                {busy && <Loader2 className="w-4 h-4 animate-spin" />}
                Submit + pay ${(budget.total / 100).toFixed(2)}
              </button>
            </div>
          </div>
        )}

        {step === "done" && (
          <div className="p-5" data-testid="advertiser-rjsr-create-success">
            {created?.sponsored_read?.status === "rejected" ? (
              <>
                <div className="w-14 h-14 mx-auto rounded-full grid place-items-center
                                                bg-red-500/15 border-2 border-red-500 mb-3">
                  <X className="w-7 h-7 text-red-500" />
                </div>
                <div className="text-center text-sm font-black">
                  Read rejected
                </div>
                <div className={`text-center text-[11px] font-mono ${muted} mt-1`}>
                  {created.sponsored_read.cancel_reason}
                </div>
              </>
            ) : (
              <>
                <div className="w-14 h-14 mx-auto rounded-full grid place-items-center
                                                bg-emerald-500/15 border-2 border-emerald-500 mb-3">
                  <Check className="w-7 h-7 text-emerald-500" />
                </div>
                <div className="text-center text-sm font-black">
                  {created?.sponsored_read?.status === "active"
                    ? "Read live on-air"
                    : "Awaiting admin approval"}
                </div>
                <div className={`text-center text-[11px] font-mono ${muted} mt-1`}
                            data-testid="advertiser-rjsr-create-id">
                  {created?.sponsored_read?.sponsored_read_id}
                </div>
                <div className={`text-center text-xs ${muted} mt-3`}>
                  Charged ${(created?.sponsored_read?.total_cost_cents / 100).toFixed(2)}
                </div>
                {created?.sponsored_read?.audio_url && (
                  <div className="mt-3">
                    <div className={`text-[10px] font-mono ${muted} inline-flex items-center gap-1 mb-1`}>
                      <PlayCircle size={11} /> Preview
                    </div>
                    <audio controls src={created.sponsored_read.audio_url}
                                    className="w-full"
                                    data-testid="advertiser-rjsr-create-audio" />
                  </div>
                )}
              </>
            )}
            <button onClick={onDone}
                            data-testid="advertiser-rjsr-create-done"
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
              data-testid="advertiser-rjsr-empty">
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
