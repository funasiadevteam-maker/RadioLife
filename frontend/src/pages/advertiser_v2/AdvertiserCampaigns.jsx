// Phase AD.1 — Campaigns tab: table + 4-step Create wizard.
import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import {
  Plus, X, Loader2, ChevronRight, Play, Pause, Ban,
  Megaphone, Trophy, Radio, ChevronLeft, Check, ArrowRight,
} from "lucide-react";

import { useAdvertiser } from "./AdvertiserShell";
import { useDesignVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const fmt = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;

const TYPES = [
  { id: "display_banner",              label: "Display Banner",        Icon: Megaphone,
      desc: "Rectangular ad on the home hero + player card." },
  { id: "sponsored_game",           label: "Sponsored Game",     Icon: Trophy,
      desc: "Attach your brand to an existing merchant Play & Win campaign." },
  { id: "audio_preroll_stub",       label: "Audio Preroll (stub)", Icon: Radio,
      desc: "15-second audio ad before a listener joins a station." },
];

const STATUS_COLORS = {
  draft:                        "bg-slate-500/15 text-slate-400",
  pending_approval:  "bg-amber-500/15 text-amber-500",
  active:                      "bg-emerald-500/15 text-emerald-500",
  paused:                    "bg-blue-500/15 text-blue-400",
  ended:                       "bg-slate-500/15 text-slate-500",
  rejected:                  "bg-red-500/15 text-red-400",
};

export default function AdvertiserCampaigns() {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const { active } = useAdvertiser();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [refresher, setRefresher] = useState(0);

  useEffect(() => {
    if (!active) return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/ad1/advertiser/${active.advertiser_id}/campaigns`);
        setItems(data.items || []);
      } catch (_) {}
      finally { setLoading(false); }
    })();
  }, [active, refresher]);

  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"}`;

  return (
    <div className="space-y-6" data-testid="advertiser-campaigns-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Campaigns</div>
          <h1 className="text-3xl font-bold mt-1">Ad campaigns</h1>
        </div>
        <button onClick={() => setWizardOpen(true)}
                        data-testid="advertiser-campaigns-new-btn"
                        disabled={active?.status !== "active"}
                        title={active?.status !== "active" ? "Advertiser account not yet approved" : ""}
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-amber-500 text-slate-950 text-sm font-semibold hover:bg-amber-400 disabled:opacity-50 transition">
          <Plus className="w-4 h-4" /> New Campaign
        </button>
      </div>

      {loading ? (
        <Loader2 className="w-6 h-6 animate-spin text-amber-500 mx-auto" />
      ) : items.length === 0 ? (
        <div className={`${cardCls} rounded-2xl p-10 text-center`}
                    data-testid="advertiser-campaigns-empty">
          <Megaphone className="w-10 h-10 text-slate-500 mx-auto" />
          <div className="mt-3 font-bold">No campaigns yet</div>
          <p className={`mt-1 text-sm ${light ? "text-slate-600" : "text-slate-400"}`}>
            Create your first ad campaign to reach BigFM listeners.
          </p>
        </div>
      ) : (
        <div className={`${cardCls} rounded-2xl overflow-hidden`}
                    data-testid="advertiser-campaigns-table">
          <div className={`grid grid-cols-[1fr,110px,90px,110px,110px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                light ? "border-b border-slate-200 text-slate-500 bg-slate-50" :
                                              "border-b border-slate-800 text-slate-500 bg-slate-950"
                            }`}>
            <div>Name</div><div>Type</div><div>Status</div>
            <div className="text-right">Budget</div><div className="text-right">Actions</div>
          </div>
          {items.map((c) => (
            <CampaignRow key={c.campaign_id} campaign={c} light={light}
                                      advertiserId={active.advertiser_id}
                                      onRefresh={() => setRefresher((n) => n + 1)} />
          ))}
        </div>
      )}

      {wizardOpen && (
        <CreateWizard onClose={() => setWizardOpen(false)}
                                    advertiserId={active.advertiser_id}
                                    onCreated={() => { setWizardOpen(false); setRefresher((n) => n + 1); }} />
      )}
    </div>
  );
}

function CampaignRow({ campaign: c, light, advertiserId, onRefresh }) {
  const [busy, setBusy] = useState(false);
  const TypeIcon = TYPES.find((t) => t.id === c.campaign_type)?.Icon || Megaphone;

  async function act(url, method = "post") {
    setBusy(true);
    try {
      await axios[method](url);
      onRefresh();
    } finally { setBusy(false); }
  }

  const canSubmit = c.status === "draft" || c.status === "rejected";
  const canPause = c.status === "active";
  const canEnd = c.status === "active" || c.status === "paused";

  return (
    <div className={`grid grid-cols-[1fr,110px,90px,110px,110px] gap-3 px-5 py-4 items-center ${
                          light ? "border-b border-slate-100" : "border-b border-slate-800"
                        }`}
                data-testid={`advertiser-campaign-row-${c.campaign_id}`}>
      <div className="min-w-0">
        <div className="font-semibold truncate">{c.name}</div>
        <div className={`text-xs mt-0.5 ${light ? "text-slate-500" : "text-slate-500"}`}>
          {c.campaign_id}
        </div>
      </div>
      <div className={`inline-flex items-center gap-1 text-xs ${light ? "text-slate-700" : "text-slate-300"}`}>
        <TypeIcon className="w-3.5 h-3.5" /> {c.campaign_type.replace(/_/g, " ")}
      </div>
      <div className={`inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider ${STATUS_COLORS[c.status]}`}>
        {c.status.replace(/_/g, " ")}
      </div>
      <div className="text-right text-sm">
        <div>{fmt(c.budget_total_cents)}</div>
        <div className={`text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
          spent {fmt(c.budget_spent_cents)}
        </div>
      </div>
      <div className="text-right flex items-center justify-end gap-1.5">
        {canSubmit && (
          <button disabled={busy}
                          onClick={() => act(`${API}/ad1/advertiser/${advertiserId}/campaigns/${c.campaign_id}/submit-for-approval`)}
                          data-testid={`advertiser-campaign-submit-${c.campaign_id}`}
                          className="px-2 py-1 rounded-md text-[10px] uppercase tracking-wider bg-amber-500/15 text-amber-500 hover:bg-amber-500/25 disabled:opacity-50">
            Submit
          </button>
        )}
        {canPause && (
          <button disabled={busy}
                          onClick={() => act(`${API}/ad1/advertiser/${advertiserId}/campaigns/${c.campaign_id}/pause`)}
                          data-testid={`advertiser-campaign-pause-${c.campaign_id}`}
                          className="p-1.5 rounded-md hover:bg-slate-800/20" title="Pause">
            <Pause className="w-3.5 h-3.5" />
          </button>
        )}
        {canEnd && (
          <button disabled={busy}
                          onClick={() => act(`${API}/ad1/advertiser/${advertiserId}/campaigns/${c.campaign_id}/end`)}
                          data-testid={`advertiser-campaign-end-${c.campaign_id}`}
                          className="p-1.5 rounded-md text-red-400 hover:bg-red-500/10" title="End">
            <Ban className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

// ─── Create Wizard ──────────────────────────────────────────────
function CreateWizard({ onClose, advertiserId, onCreated }) {
  const variant = useDesignVariant();
  const light = variant === "radiolife";
  const [step, setStep] = useState(1);
  const [campaignType, setCampaignType] = useState("display_banner");
  const [name, setName] = useState("");
  const [budget, setBudget] = useState(10000);      // $100
  const [pricingModel, setPricingModel] = useState("cpm");
  const [cpmBid, setCpmBid] = useState(500);          // $5.00 CPM
  const [cpcBid, setCpcBid] = useState(50);           // $0.50 CPC
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");
  const [dailyCap, setDailyCap] = useState(0);
  const [cities, setCities] = useState("");
  const [segments, setSegments] = useState(new Set(["all"]));
  const [dayparts, setDayparts] = useState(new Set());
  const [headline, setHeadline] = useState("");
  const [body, setBody] = useState("");
  const [imageUrl, setImageUrl] = useState("");
  const [clickUrl, setClickUrl] = useState("");
  const [sponsorGameId, setSponsorGameId] = useState("");
  const [gameOptions, setGameOptions] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (campaignType !== "sponsored_game") return;
    (async () => {
      try {
        const { data } = await axios.get(`${API}/games/discover`);
        setGameOptions(data.items || data || []);
      } catch (_) {}
    })();
  }, [campaignType]);

  const inputCls = `w-full px-3 py-2 rounded-lg border ${
    light ? "border-slate-300 bg-white focus:border-amber-500" :
                    "border-slate-700 bg-slate-900 focus:border-amber-500"
  } focus:outline-none text-sm`;

  function toggleSet(setter, currentSet, value) {
    const next = new Set(currentSet);
    if (next.has(value)) next.delete(value);
    else next.add(value);
    setter(next);
  }

  async function submit() {
    setError(null);
    if (!name.trim()) { setError("Campaign name required."); return; }
    if (budget <= 0) { setError("Budget must be > $0."); return; }
    if (campaignType === "sponsored_game" && !sponsorGameId) {
      setError("Pick a game to sponsor."); return;
    }
    setSubmitting(true);
    try {
      const payload = {
        name, campaign_type: campaignType,
        budget_total_cents: parseInt(budget, 10),
        daily_cap_cents:     dailyCap ? parseInt(dailyCap, 10) : null,
        start_at: startAt || null, end_at: endAt || null,
        pricing_model: pricingModel,
        cpm_bid_cents: pricingModel === "cpm" ? parseInt(cpmBid, 10) : null,
        cpc_bid_cents: pricingModel === "cpc" ? parseInt(cpcBid, 10) : null,
        targeting: {
          cities: cities ? cities.split(",").map((s) => s.trim()).filter(Boolean) : [],
          user_segments: Array.from(segments),
          dayparts: Array.from(dayparts),
        },
        creative: {
          headline: headline || null,
          body: body || null,
          image_url: imageUrl || null,
          click_url: clickUrl || null,
          sponsored_game_campaign_id: campaignType === "sponsored_game" ? sponsorGameId : null,
        },
      };
      await axios.post(`${API}/ad1/advertiser/${advertiserId}/campaigns`, payload);
      onCreated();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === "object" ? (detail.code || JSON.stringify(detail)) : (detail || err.message));
    } finally { setSubmitting(false); }
  }

  const shellCls = `${light ? "bg-white text-slate-900" : "bg-slate-900 text-white"} rounded-2xl max-w-2xl w-full`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
              onClick={(e) => e.target === e.currentTarget && onClose()}
              data-testid="advertiser-campaign-wizard">
      <div className={`${shellCls} max-h-[90vh] overflow-y-auto`}>
        <div className={`flex items-center justify-between px-6 py-4 ${
                                light ? "border-b border-slate-200" : "border-b border-slate-800"
                            }`}>
          <div>
            <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Step {step} / 4</div>
            <h3 className="font-bold text-lg mt-0.5">
              {step === 1 && "Choose campaign type"}
              {step === 2 && "Targeting + budget"}
              {step === 3 && "Creative"}
              {step === 4 && "Review & submit"}
            </h3>
          </div>
          <button onClick={onClose} data-testid="advertiser-campaign-wizard-close" className="p-2 rounded-lg hover:bg-slate-800/20">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-6 space-y-4">
          {/* STEP 1 — Type + Name */}
          {step === 1 && (
            <>
              <div className="grid gap-3">
                {TYPES.map((t) => (
                  <button key={t.id} type="button"
                                  data-testid={`advertiser-campaign-type-${t.id}`}
                                  onClick={() => setCampaignType(t.id)}
                                  className={`text-left px-4 py-3 rounded-xl border-2 transition ${
                                      campaignType === t.id
                                        ? "border-amber-500 bg-amber-500/10"
                                        : light ? "border-slate-200 hover:border-slate-300"
                                                        : "border-slate-800 hover:border-slate-700"
                                  }`}>
                    <div className="flex items-center gap-2 font-semibold">
                      <t.Icon className="w-4 h-4 text-amber-500" /> {t.label}
                    </div>
                    <div className={`text-xs mt-1 ${light ? "text-slate-600" : "text-slate-400"}`}>{t.desc}</div>
                  </button>
                ))}
              </div>
              <label className="block">
                <div className="text-xs uppercase tracking-widest font-mono text-slate-500 mb-1.5">Campaign name</div>
                <input value={name} onChange={(e) => setName(e.target.value)}
                              className={inputCls} placeholder="Summer sale — Dubai"
                              data-testid="advertiser-campaign-name" />
              </label>
              {campaignType === "sponsored_game" && (
                <label className="block">
                  <div className="text-xs uppercase tracking-widest font-mono text-slate-500 mb-1.5">
                    Merchant game to sponsor
                  </div>
                  <select value={sponsorGameId} onChange={(e) => setSponsorGameId(e.target.value)}
                                    className={inputCls} data-testid="advertiser-campaign-sponsor-game">
                    <option value="">— Select an active game —</option>
                    {gameOptions.map((g) => (
                      <option key={g.campaign_id} value={g.campaign_id}>
                        {g.name} · {(g.merchant && g.merchant.name) || g.merchant_id}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </>
          )}

          {/* STEP 2 — Targeting + budget */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <Field label="Total budget (cents)">
                  <input type="number" value={budget} onChange={(e) => setBudget(e.target.value)}
                                className={inputCls} min="100"
                                data-testid="advertiser-campaign-budget" />
                </Field>
                <Field label="Daily cap (optional, cents)">
                  <input type="number" value={dailyCap} onChange={(e) => setDailyCap(e.target.value)}
                                className={inputCls} min="0"
                                data-testid="advertiser-campaign-daily-cap" />
                </Field>
              </div>
              <div className="grid grid-cols-3 gap-3">
                <Field label="Pricing model">
                  <select value={pricingModel} onChange={(e) => setPricingModel(e.target.value)}
                                    className={inputCls} data-testid="advertiser-campaign-pricing-model">
                    <option value="cpm">CPM</option>
                    <option value="cpc">CPC</option>
                    <option value="flat">Flat</option>
                  </select>
                </Field>
                <Field label="CPM bid (cents/1000 imps)">
                  <input type="number" value={cpmBid} onChange={(e) => setCpmBid(e.target.value)}
                                className={inputCls} min="0"
                                disabled={pricingModel !== "cpm"}
                                data-testid="advertiser-campaign-cpm-bid" />
                </Field>
                <Field label="CPC bid (cents/click)">
                  <input type="number" value={cpcBid} onChange={(e) => setCpcBid(e.target.value)}
                                className={inputCls} min="0"
                                disabled={pricingModel !== "cpc"}
                                data-testid="advertiser-campaign-cpc-bid" />
                </Field>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Start at (ISO or empty for immediate)">
                  <input type="datetime-local" value={startAt} onChange={(e) => setStartAt(e.target.value)}
                                className={inputCls} data-testid="advertiser-campaign-start" />
                </Field>
                <Field label="End at (ISO or empty)">
                  <input type="datetime-local" value={endAt} onChange={(e) => setEndAt(e.target.value)}
                                className={inputCls} data-testid="advertiser-campaign-end" />
                </Field>
              </div>
              <Field label="Cities (comma-separated)">
                <input type="text" value={cities} onChange={(e) => setCities(e.target.value)}
                              className={inputCls} placeholder="Dubai, Abu Dhabi"
                              data-testid="advertiser-campaign-cities" />
              </Field>
              <Field label="User segments">
                <div className="flex gap-2 flex-wrap">
                  {["all", "free", "premium"].map((s) => (
                    <button type="button" key={s}
                                    onClick={() => toggleSet(setSegments, segments, s)}
                                    data-testid={`advertiser-campaign-segment-${s}`}
                                    className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${
                                        segments.has(s) ? "bg-amber-500 text-slate-950" :
                                                                        (light ? "border border-slate-300 text-slate-700" : "border border-slate-700 text-slate-300")
                                    }`}>{s}</button>
                  ))}
                </div>
              </Field>
              <Field label="Dayparts">
                <div className="flex gap-2 flex-wrap">
                  {["morning", "afternoon", "evening", "night"].map((d) => (
                    <button type="button" key={d}
                                    onClick={() => toggleSet(setDayparts, dayparts, d)}
                                    data-testid={`advertiser-campaign-daypart-${d}`}
                                    className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${
                                        dayparts.has(d) ? "bg-amber-500 text-slate-950" :
                                                                          (light ? "border border-slate-300 text-slate-700" : "border border-slate-700 text-slate-300")
                                    }`}>{d}</button>
                  ))}
                </div>
              </Field>
            </div>
          )}

          {/* STEP 3 — Creative */}
          {step === 3 && (
            <div className="space-y-4">
              <Field label="Headline">
                <input type="text" value={headline} onChange={(e) => setHeadline(e.target.value)}
                              className={inputCls} placeholder="Fresh karak, always ready."
                              data-testid="advertiser-campaign-headline" />
              </Field>
              <Field label="Body">
                <textarea value={body} onChange={(e) => setBody(e.target.value)}
                                    className={inputCls} rows={3}
                                    placeholder="Visit our Karama branch — 20% off with this ad."
                                    data-testid="advertiser-campaign-body" />
              </Field>
              <Field label="Image URL">
                <input type="url" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)}
                              className={inputCls} placeholder="https://.../ad.jpg"
                              data-testid="advertiser-campaign-image-url" />
              </Field>
              <Field label="Click URL">
                <input type="url" value={clickUrl} onChange={(e) => setClickUrl(e.target.value)}
                              className={inputCls} placeholder="https://acme.com/landing"
                              data-testid="advertiser-campaign-click-url" />
              </Field>
            </div>
          )}

          {/* STEP 4 — Review */}
          {step === 4 && (
            <div className="space-y-3" data-testid="advertiser-campaign-review">
              <Row k="Type" v={campaignType.replace(/_/g, " ")} light={light} />
              <Row k="Name" v={name} light={light} />
              <Row k="Budget" v={fmt(budget)} light={light} />
              <Row k="Pricing model" v={pricingModel.toUpperCase()} light={light} />
              {pricingModel === "cpm" && <Row k="CPM bid" v={`${fmt(cpmBid)} / 1k impressions`} light={light} />}
              {pricingModel === "cpc" && <Row k="CPC bid" v={fmt(cpcBid) + " / click"} light={light} />}
              <Row k="Segments" v={Array.from(segments).join(", ") || "all"} light={light} />
              <Row k="Dayparts" v={Array.from(dayparts).join(", ") || "(any)"} light={light} />
              <Row k="Cities" v={cities || "(all)"} light={light} />
              <Row k="Headline" v={headline || "(none)"} light={light} />
              {campaignType === "sponsored_game" && (
                <Row k="Sponsoring game" v={sponsorGameId || "(none picked)"} light={light} />
              )}
              <div className="rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-500 text-xs p-3 mt-4">
                Campaign will be created in <b>draft</b> status.  Submit it for admin approval from the campaigns table.
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-400"
                        data-testid="advertiser-campaign-wizard-error">
              {error}
            </div>
          )}
        </div>

        {/* Nav */}
        <div className={`px-6 py-4 flex items-center justify-between ${
                                light ? "border-t border-slate-200" : "border-t border-slate-800"
                            }`}>
          {step > 1 ? (
            <button onClick={() => setStep(step - 1)}
                            data-testid="advertiser-campaign-wizard-back"
                            className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm ${
                                light ? "text-slate-700 hover:bg-slate-100" : "text-slate-300 hover:bg-slate-800"
                            }`}>
              <ChevronLeft className="w-4 h-4" /> Back
            </button>
          ) : <div />}
          {step < 4 ? (
            <button onClick={() => setStep(step + 1)}
                            data-testid={`advertiser-campaign-wizard-next-${step}`}
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-amber-500 text-slate-950 text-sm font-semibold hover:bg-amber-400">
              Next <ChevronRight className="w-4 h-4" />
            </button>
          ) : (
            <button onClick={submit} disabled={submitting}
                            data-testid="advertiser-campaign-wizard-submit"
                            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-full bg-amber-500 text-slate-950 text-sm font-semibold hover:bg-amber-400 disabled:opacity-50">
              {submitting ? <><Loader2 className="w-4 h-4 animate-spin" /> Creating…</> :
                                            <><Check className="w-4 h-4" /> Create draft</>}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return (
    <label className="block">
      <div className="text-xs uppercase tracking-widest font-mono text-slate-500 mb-1.5">{label}</div>
      {children}
    </label>
  );
}

function Row({ k, v, light }) {
  return (
    <div className={`flex items-center justify-between text-sm py-1 border-b ${light ? "border-slate-100" : "border-slate-800"}`}>
      <span className={light ? "text-slate-500" : "text-slate-400"}>{k}</span>
      <span className="font-semibold text-right max-w-[60%] truncate">{v}</span>
    </div>
  );
}
