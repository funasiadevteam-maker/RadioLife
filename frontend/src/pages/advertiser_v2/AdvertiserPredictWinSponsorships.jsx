// Phase AD.3 — Advertiser Predict & Win Sponsorships dashboard + 5-step wizard.
// Route: /advertiser/dashboard/predict-win-sponsorships
import { useEffect, useState, useRef } from "react";
import axios from "axios";
import {
  Plus, X, Loader2, AlertTriangle, CheckCircle2, ChevronRight,
  ChevronLeft, Trophy, Zap, Info,
} from "lucide-react";
import { useAdvertiser } from "@/pages/advertiser_v2/AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_STYLES = {
  draft:                        "bg-slate-500/15 text-slate-400 border border-slate-500/30",
  pending_admin:      "bg-amber-500/15 text-amber-400 border border-amber-500/30",
  approved:                "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  live:                          "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  rejected:                "bg-red-500/15 text-red-400 border border-red-500/30",
  requires_changes:  "bg-blue-500/15 text-blue-400 border border-blue-500/30",
  paused:                      "bg-orange-500/15 text-orange-400 border border-orange-500/30",
};

export default function AdvertiserPredictWinSponsorships() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active: advertiser, permissions } = useAdvertiser() || {};
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [hints, setHints] = useState(null);
  const [toast, setToast] = useState(null);

  const canManage = permissions?.has?.("can_manage_campaigns");
  const isBlocked = advertiser?.status === "blocked";
  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";
  const muted = light ? "text-slate-500" : "text-slate-400";

  const showToast = (kind, msg) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  async function load() {
    if (!advertiser) return;
    setLoading(true);
    try {
      const [r, h] = await Promise.all([
        axios.get(`${API}/advertiser/${advertiser.advertiser_id}/predict-win-sponsorships`,
          { withCredentials: true }),
        hints ? Promise.resolve({ data: hints })
                    : axios.get(`${API}/ad-pricing-hints`),
      ]);
      setItems(r.data.items || []);
      if (!hints) setHints(h.data);
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [advertiser?.advertiser_id]);

  if (!advertiser) {
    return <div className={`${bg} min-h-screen p-8`}>
      <div className={muted}>Loading…</div></div>;
  }

  return (
    <div className="space-y-6" data-testid="advertiser-pw-page">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
            Phase AD.3 · Predict & Win sponsorships
          </div>
          <h1 className="text-3xl md:text-4xl xl:text-5xl font-black inline-flex items-center gap-2 mt-1">
            <Trophy className="w-7 h-7 text-amber-500" />
            Sponsor a Predict & Win
          </h1>
          <p className={`text-sm mt-1 ${muted}`}>
            Attach your brand to a live Predict & Win campaign.
            Pay per entry OR per correct-answer impression — your choice.
          </p>
        </div>
        {canManage && (
          <button onClick={() => setWizardOpen(true)}
                          disabled={isBlocked}
                          data-testid="advertiser-pw-new-button"
                          className={`inline-flex items-center gap-2 font-black text-sm px-4 py-2.5 rounded-full shadow-lg transition ${
                                                      isBlocked
                                                          ? "bg-slate-500/40 text-slate-400 cursor-not-allowed shadow-none"
                                                          : "bg-amber-500 text-slate-900 hover:bg-amber-400 shadow-amber-500/30"}`}>
            <Plus className="w-4 h-4" /> New sponsorship
          </button>
        )}
      </div>

      {loading ? (
        <div className={`inline-flex items-center gap-2 ${muted}`}>
          <Loader2 className="w-4 h-4 animate-spin" /> Loading…
        </div>
      ) : error ? (
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm">
          {String(error)}
        </div>
      ) : (items || []).length === 0 ? (
        <div className={`rounded-2xl px-6 py-14 text-center ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
                    data-testid="advertiser-pw-empty">
          <Trophy className={`w-10 h-10 mx-auto mb-3 ${muted}`} />
          <div className="font-semibold">No sponsorships yet.</div>
          <p className={`text-sm mt-1 ${muted}`}>
            Attach your brand to any live Predict & Win campaign.
          </p>
        </div>
      ) : (
        <div className={`rounded-2xl overflow-hidden ${light ? "bg-white border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
                    data-testid="advertiser-pw-table">
          <div className={`hidden md:grid grid-cols-[2fr,110px,110px,140px,110px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                      light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                    : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
            <div>Brand · Parent</div><div>Status</div><div>Model</div>
            <div>Spend</div><div>Entries</div>
          </div>
          {items.map((s) => (
            <div key={s.sponsorship_id}
                        data-testid={`advertiser-pw-row-${s.sponsorship_id}`}
                        className={`grid md:grid-cols-[2fr,110px,110px,140px,110px] gap-3 px-5 py-4 items-center ${
                                                    light ? "border-b border-slate-100 last:border-0"
                                                                  : "border-b border-slate-800 last:border-0"}`}>
              <div className="min-w-0">
                <div className="font-black truncate">{s.brand_name}</div>
                <div className={`text-[11px] ${muted} truncate`}>
                  {(s.parent_snapshot || {}).title || s.parent_campaign_id}
                </div>
              </div>
              <div>
                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] uppercase font-semibold tracking-wider ${
                                            STATUS_STYLES[s.status] || "bg-slate-500/15 text-slate-400"}`}>
                  {s.status}
                </span>
              </div>
              <div className={`text-[11px] font-mono ${muted}`}>
                {s.pricing_model === "per_entry"
                  ? `CPE ${s.cpe_cents}¢`
                  : `CPI ${s.cpi_cents}¢`}
              </div>
              <div className="text-sm font-mono">
                ${((s.spent_cents || 0)/100).toFixed(2)} / ${((s.budget_cents || 0)/100).toFixed(2)}
              </div>
              <div className="text-sm font-mono">
                {s.entries_count || 0}e · {s.correct_impressions_count || 0}i
              </div>
            </div>
          ))}
        </div>
      )}

      {wizardOpen && (
        <SponsorshipWizard advertiser={advertiser} hints={hints}
                                                  light={light}
                                                  onClose={() => setWizardOpen(false)}
                                                  onDone={(msg) => {
                                                      showToast("success", msg);
                                                      setWizardOpen(false); load();
                                                  }} />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm"
                    data-testid="advertiser-pw-toast">
          <div className={`${toast.kind === "error"
                                            ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                            : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm`}>
            {toast.msg}
          </div>
        </div>
      )}
    </div>
  );
}


// ─── 5-step wizard ───────────────────────────────────────────────────
function SponsorshipWizard({ advertiser, hints, light, onClose, onDone }) {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [parents, setParents] = useState([]);
  const [sponsorshipId, setSponsorshipId] = useState(null);
  const [assetUploaded, setAssetUploaded] = useState(false);
  const [form, setForm] = useState({
    parent_campaign_id: "",
    brand_name: "",
    tagline: "",
    pricing_model: "per_entry",
    cpe_cents: 20,
    cpi_cents: 5,
    budget_cents: 50000,
    daily_cap_cents: 5000,
    targeting_json: { country_codes: ["AE"] },
  });
  const iconRef = useRef(null);

  const inputCls = light
    ? "w-full px-3 py-2 rounded-lg text-sm bg-white border border-slate-300"
    : "w-full px-3 py-2 rounded-lg text-sm bg-slate-900 border border-slate-700";
  const labelCls = `block text-[10px] uppercase tracking-widest mb-1 font-mono ${light ? "text-slate-500" : "text-slate-400"}`;

  useEffect(() => {
    if (step !== 1) return;
    axios.get(`${API}/advertiser/predict-win/available-campaigns?limit=30`,
                          { withCredentials: true })
      .then((r) => setParents(r.data.items || []))
      .catch(() => setParents([]));
  }, [step]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  async function saveDraft() {
    setBusy(true); setError(null);
    try {
      if (!sponsorshipId) {
        const { data } = await axios.post(
          `${API}/advertiser/${advertiser.advertiser_id}/predict-win/sponsorships`,
          form, { withCredentials: true });
        setSponsorshipId(data.sponsorship_id);
        return data.sponsorship_id;
      } else {
        await axios.patch(
          `${API}/advertiser/predict-win/sponsorships/${sponsorshipId}`,
          form, { withCredentials: true });
        return sponsorshipId;
      }
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
      return null;
    } finally { setBusy(false); }
  }

  async function uploadAsset(file) {
    let id = sponsorshipId;
    if (!id) id = await saveDraft();
    if (!id) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      await axios.post(
        `${API}/advertiser/predict-win/sponsorships/${id}/brand-asset`,
        fd, { withCredentials: true,
                    headers: { "Content-Type": "multipart/form-data" }});
      setAssetUploaded(true);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setBusy(false); }
  }

  async function submit() {
    setBusy(true); setError(null);
    try {
      const id = sponsorshipId || await saveDraft();
      if (!id) return;
      await axios.post(
        `${API}/advertiser/predict-win/sponsorships/${id}/publish`,
        {}, { withCredentials: true });
      onDone("Sponsorship submitted for review.");
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setBusy(false); }
  }

  const cardBg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";
  const chosenParent = parents.find(
    (p) => p.parent_campaign_id === form.parent_campaign_id);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm overflow-y-auto"
              data-testid="advertiser-pw-wizard"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${cardBg} border ${border} rounded-2xl shadow-2xl max-w-2xl w-full my-8 ${light ? "text-slate-900" : "text-white"}`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Step {step} / 5
            </div>
            <h2 className="text-lg font-black">
              {step === 1 && "Pick a parent campaign"}
              {step === 2 && "Brand identity"}
              {step === 3 && "Pricing model"}
              {step === 4 && "Budget + targeting"}
              {step === 5 && "Preview + submit"}
            </h2>
          </div>
          <button onClick={onClose} data-testid="advertiser-pw-wizard-close"
                          className={`p-1.5 rounded-md ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"}`}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {error && (
            <div className="rounded-lg px-4 py-2 bg-red-500/10 border border-red-500/40 text-red-400 text-sm"
                        data-testid="advertiser-pw-wizard-error">
              <AlertTriangle className="w-4 h-4 inline mr-1" /> {String(error)}
            </div>
          )}

          {step === 1 && (
            <div data-testid="advertiser-pw-wizard-step-1" className="space-y-2">
              {parents.length === 0 && (
                <div className={`text-sm ${light ? "text-slate-500" : "text-slate-400"}`}>
                  No open campaigns available.
                </div>
              )}
              {parents.map((p) => (
                <label key={p.parent_campaign_id}
                            data-testid={`advertiser-pw-wizard-parent-${p.parent_campaign_id}`}
                            className={`flex items-start gap-3 p-3 rounded-lg cursor-pointer border-2 transition ${
                                                        form.parent_campaign_id === p.parent_campaign_id
                                                            ? "border-amber-500 bg-amber-500/10"
                                                            : (light ? "border-slate-200 hover:border-slate-300"
                                                                          : "border-slate-800 hover:border-slate-700")}`}>
                  <input type="radio"
                                  checked={form.parent_campaign_id === p.parent_campaign_id}
                                  onChange={() => set("parent_campaign_id", p.parent_campaign_id)}
                                  className="mt-1 accent-amber-500" />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-black truncate">{p.title}</div>
                    <div className={`text-[11px] font-mono ${light ? "text-slate-500" : "text-slate-400"}`}>
                      {p.event_label} · {p.entries_so_far} entries · {p.active_sponsors} active sponsors
                    </div>
                  </div>
                </label>
              ))}
            </div>
          )}

          {step === 2 && (
            <div data-testid="advertiser-pw-wizard-step-2" className="space-y-3">
              <div>
                <label className={labelCls}>Brand name *</label>
                <input value={form.brand_name}
                              onChange={(e) => set("brand_name", e.target.value)}
                              data-testid="advertiser-pw-wizard-brand-name"
                              maxLength={80}
                              className={inputCls} placeholder="Nike" />
              </div>
              <div>
                <label className={labelCls}>Tagline (optional)</label>
                <input value={form.tagline}
                              onChange={(e) => set("tagline", e.target.value)}
                              maxLength={140}
                              className={inputCls} placeholder="Just Predict It." />
              </div>
              <div>
                <label className={labelCls}>Brand asset (required) — PNG/JPG/WEBP ≤1MB</label>
                <div className={`flex items-center gap-3 p-3 rounded-lg ${light ? "bg-slate-50" : "bg-slate-950"}`}>
                  {assetUploaded ? (
                    <span className="text-[11px] font-black text-emerald-400 inline-flex items-center gap-1">
                      <CheckCircle2 className="w-4 h-4" /> Asset uploaded
                    </span>
                  ) : (
                    <input type="file" ref={iconRef}
                                    accept="image/png,image/jpeg,image/webp"
                                    onChange={(e) => e.target.files?.[0] && uploadAsset(e.target.files[0])}
                                    data-testid="advertiser-pw-wizard-asset"
                                    className="text-xs" />
                  )}
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div data-testid="advertiser-pw-wizard-step-3" className="space-y-3">
              <label className={labelCls}>Pricing model</label>
              <div className="grid grid-cols-2 gap-2">
                <label className={`p-3 rounded-lg cursor-pointer border-2 ${
                                                      form.pricing_model === "per_entry"
                                                          ? "border-amber-500 bg-amber-500/10"
                                                          : (light ? "border-slate-200" : "border-slate-800")}`}
                              data-testid="advertiser-pw-wizard-model-per-entry">
                  <input type="radio" checked={form.pricing_model === "per_entry"}
                                  onChange={() => set("pricing_model", "per_entry")}
                                  className="accent-amber-500" />
                  <span className="ml-1 text-xs font-black">Per entry</span>
                  <div className={`text-[10px] font-mono mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                    Billed per user who enters the game.
                  </div>
                </label>
                <label className={`p-3 rounded-lg cursor-pointer border-2 ${
                                                      form.pricing_model === "per_correct_impression"
                                                          ? "border-amber-500 bg-amber-500/10"
                                                          : (light ? "border-slate-200" : "border-slate-800")}`}
                              data-testid="advertiser-pw-wizard-model-per-cpi">
                  <input type="radio" checked={form.pricing_model === "per_correct_impression"}
                                  onChange={() => set("pricing_model", "per_correct_impression")}
                                  className="accent-amber-500" />
                  <span className="ml-1 text-xs font-black">Per correct-impression</span>
                  <div className={`text-[10px] font-mono mt-1 ${light ? "text-slate-500" : "text-slate-400"}`}>
                    Billed when the user sees a correct-answer surface.
                  </div>
                </label>
              </div>
              {form.pricing_model === "per_entry" ? (
                <div>
                  <label className={labelCls}>CPE (cents per entry)</label>
                  <input type="number" min="1" max="10000"
                                value={form.cpe_cents}
                                onChange={(e) => set("cpe_cents", Number(e.target.value) || 0)}
                                data-testid="advertiser-pw-wizard-cpe"
                                className={inputCls} />
                  <div className={`text-[11px] mt-1 font-mono ${light ? "text-slate-500" : "text-slate-400"} inline-flex items-center gap-1`}>
                    <Info size={11} /> Recommended: {hints?.pw_sponsorship_default_cpe_cents ?? 20}¢ standard, {(hints?.pw_sponsorship_tiers || []).find((t) => t.tier === "high_volume")?.cpe ?? 35}¢ high-volume, {(hints?.pw_sponsorship_tiers || []).find((t) => t.tier === "niche")?.cpe ?? 10}¢ niche
                  </div>
                </div>
              ) : (
                <div>
                  <label className={labelCls}>CPI (cents per correct-impression)</label>
                  <input type="number" min="1" max="10000"
                                value={form.cpi_cents}
                                onChange={(e) => set("cpi_cents", Number(e.target.value) || 0)}
                                data-testid="advertiser-pw-wizard-cpi"
                                className={inputCls} />
                  <div className={`text-[11px] mt-1 font-mono ${light ? "text-slate-500" : "text-slate-400"} inline-flex items-center gap-1`}>
                    <Info size={11} /> Recommended: {hints?.pw_sponsorship_default_cpi_cents ?? 5}¢ standard
                  </div>
                </div>
              )}
            </div>
          )}

          {step === 4 && (
            <div data-testid="advertiser-pw-wizard-step-4" className="space-y-3">
              <div>
                <label className={labelCls}>Total budget (cents) *</label>
                <input type="number" min="100"
                              value={form.budget_cents}
                              onChange={(e) => set("budget_cents", Number(e.target.value))}
                              data-testid="advertiser-pw-wizard-budget"
                              className={inputCls} />
                <p className={`text-[11px] mt-1 font-mono ${light ? "text-slate-500" : "text-slate-400"}`}>
                  ${((form.budget_cents || 0)/100).toFixed(2)} total
                </p>
              </div>
              <div>
                <label className={labelCls}>Daily cap (cents) — 0 for none</label>
                <input type="number" min="0"
                              value={form.daily_cap_cents}
                              onChange={(e) => set("daily_cap_cents", Number(e.target.value) || 0)}
                              className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Target country codes (ISO-2)</label>
                <input value={(form.targeting_json?.country_codes || []).join(", ")}
                              onChange={(e) => set("targeting_json", {
                                ...form.targeting_json,
                                country_codes: e.target.value.split(",").map((s) => s.trim()).filter(Boolean),
                              })}
                              data-testid="advertiser-pw-wizard-countries"
                              className={inputCls} placeholder="AE, US" />
              </div>
            </div>
          )}

          {step === 5 && (
            <div data-testid="advertiser-pw-wizard-step-5" className="space-y-3">
              {/* Mockup preview */}
              <div className={`rounded-2xl p-5 ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-900 border border-slate-800"}`}>
                <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500 mb-3">
                  Preview — how customers will see it
                </div>
                <div className={`relative rounded-xl p-4 ${light ? "bg-white" : "bg-slate-950"} border border-amber-500/40`}>
                  <span className="absolute top-2 right-2 text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                    Sponsored · {form.brand_name || "Brand"}
                  </span>
                  <div className="text-xs font-black mb-1 flex items-center gap-2">
                    <Zap size={14} className="text-fuchsia-400" />
                    {(chosenParent || {}).title || "Predict & Win event"}
                  </div>
                  <div className={`text-[11px] ${light ? "text-slate-500" : "text-slate-400"}`}>
                    Powered by {form.brand_name || "your brand"} — {form.tagline || "your tagline"}
                  </div>
                </div>
              </div>
              <div className={`text-xs ${light ? "text-slate-600" : "text-slate-400"}`}>
                Submitting will send this to the Ad Review Queue.  It goes live after admin approval.
                Billing model: <span className="font-black">
                  {form.pricing_model === "per_entry"
                    ? `${form.cpe_cents}¢ per entry`
                    : `${form.cpi_cents}¢ per correct impression`}
                </span> · Budget: ${(form.budget_cents/100).toFixed(2)}
              </div>
            </div>
          )}
        </div>

        <div className={`px-6 py-4 border-t ${border} flex items-center justify-between gap-2`}>
          <button onClick={() => setStep((s) => Math.max(1, s - 1))}
                          disabled={step === 1 || busy}
                          data-testid="advertiser-pw-wizard-back"
                          className={`inline-flex items-center gap-1 text-sm px-3 py-2 rounded-full ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"} disabled:opacity-40`}>
            <ChevronLeft className="w-4 h-4" /> Back
          </button>
          <div className="text-[10px] font-mono opacity-60">Step {step}/5</div>
          {step < 5 ? (
            <button onClick={async () => {
                if (step === 2) await saveDraft();
                setStep((s) => Math.min(5, s + 1));
              }}
              disabled={busy
                                || (step === 1 && !form.parent_campaign_id)
                                || (step === 2 && (!form.brand_name || !assetUploaded))}
              data-testid="advertiser-pw-wizard-next"
              className="inline-flex items-center gap-1 text-sm font-black px-4 py-2 rounded-full bg-amber-500 text-slate-900 hover:bg-amber-400 disabled:opacity-40">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={submit} disabled={busy}
                            data-testid="advertiser-pw-wizard-submit"
                            className="inline-flex items-center gap-1 text-sm font-black px-4 py-2 rounded-full bg-emerald-500 text-slate-900 hover:bg-emerald-400 disabled:opacity-40">
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Submit for review
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
