// Phase 18a — 5-step campaign creation wizard.
import { useEffect, useState } from "react";
import axios from "axios";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, Upload, Check, AlertTriangle, X, Loader2 } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

const OBJECTIVES = [
  { id: "awareness",    title: "Awareness",     blurb: "Maximize reach" },
  { id: "coupon_save",  title: "Coupon Save", blurb: "Drive coupon saves" },
  { id: "store_visit",   title: "Store Visit",   blurb: "Drive foot traffic" },
  { id: "ticket_sale",   title: "Ticket Sale",   blurb: "Sell event tickets" },
];

const TAKEOVER_THRESHOLD = 1000;

const TIME_OF_DAY = ["morning", "afternoon", "evening", "late_night"];
const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const WEATHER = ["rainy", "hot", "cool", "cold"];
const CHANNELS = ["morning_masala", "bollywood_mehfil", "party_dubai",
                          "punjabi_beats", "late_night_drive", "devotional_hour",
                          "retro_lounge", "workout_wala"];


export default function CampaignWizard() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [advs, setAdvs] = useState([]);
  const [advId, setAdvId] = useState(localStorage.getItem("bigfm_active_advertiser") || "");
  const [name, setName] = useState("");
  const [obj, setObj] = useState("awareness");
  const [t, setT] = useState({
    market: "dubai", time_of_day: [], days_of_week: [],
    weather: [], channel_slugs: [], interests: [],
  });
  const [sched, setSched] = useState({
    start_date: "", end_date: "",
  });
  const [bud, setBud] = useState({ budget_total_usd: 80, budget_daily_usd: 20 });
  const [attributionWindowHours, setAttributionWindowHours] = useState(24);
  const [takeover, setTakeover] = useState({
    enabled: false, channel_slug: "morning_masala",
    window_start: "", window_end: "",
    windows_per_day: 1, exclusive: true,
  });
  const [creatives, setCreatives] = useState([]);  // local list of uploaded {id, status, brand_safety_check}
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/advertiser/me`);
        const list = r.data.items || [];
        setAdvs(list);
        if (!advId && list.length) {
          setAdvId(list[0].advertiser_id);
          setT((p) => ({ ...p, market: list[0].market || "dubai" }));
        }
      } catch {}
    })();
  }, []);

  const toggle = (arr, v) => arr.includes(v) ? arr.filter((x) => x !== v) : [...arr, v];

  const uploadCreative = async (file) => {
    if (!advId) { toast.error("No advertiser selected"); return; }
    if (file.size > 5 * 1024 * 1024) { toast.error("Audio over 5MB"); return; }
    const fd = new FormData();
    fd.append("audio", file);
    fd.append("title", file.name.replace(/\.[^.]+$/, "") || "Untitled creative");
    fd.append("transcript", "");
    try {
      const r = await axios.post(`${API}/advertiser/${advId}/creatives`,
                                                    fd, {
                                                    headers: { "Content-Type": "multipart/form-data" }});
      setCreatives((p) => [...p, r.data]);
      toast.success(`Uploaded · ${r.data.brand_safety_check?.verdict}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    }
  };

  const submit = async () => {
    if (!advId) { toast.error("No advertiser"); return; }
    if (creatives.length === 0) { toast.error("Add at least one creative"); return; }
    if (!bud.budget_total_usd || bud.budget_total_usd <= 0) { toast.error("Budget must be > 0"); return; }
    setSubmitting(true);
    try {
      const c = await axios.post(`${API}/advertiser/${advId}/campaigns`, {
        name: name || "Untitled campaign", objective: obj,
        budget_total_usd: parseFloat(bud.budget_total_usd),
        budget_daily_usd: parseFloat(bud.budget_daily_usd || 0) || null,
        start_date: sched.start_date || null,
        end_date:    sched.end_date || null,
        targeting:   t,
        creative_ids: creatives.map((x) => x.creative_id),
        takeover_config: (obj === "channel_takeover" && takeover.enabled)
                                      ? takeover : null,
        attribution_window_hours: parseInt(attributionWindowHours) || 24,
      });
      const cid = c.data.campaign_id;
      const r = await axios.post(`${API}/advertiser/${advId}/campaigns/${cid}/submit`);
      const final = r.data?.status;
      toast.success(`Campaign ${final === "active" ? "auto-approved + live" : "submitted for review"}`);
      navigate(`/advertiser/campaigns/${cid}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || "Submit failed");
    } finally { setSubmitting(false); }
  };

  const next = () => setStep((s) => Math.min(5, s+1));
  const prev = () => setStep((s) => Math.max(1, s-1));

  const estImpressions = Math.round((parseFloat(bud.budget_total_usd)||0) / 5 * 1000);

  return (
    <div className="min-h-screen bg-bg-base text-text-primary" data-testid="campaign-wizard">
      <header className="border-b border-white/[0.06] px-6 py-4 flex items-center justify-between">
        <h1 className="font-display font-bold text-xl">New campaign · Step {step} of 5</h1>
        <button onClick={() => navigate("/advertiser/campaigns")}
                    className="text-text-secondary text-sm" data-testid="wizard-close">
          <X size={16} />
        </button>
      </header>

      <div className="max-w-3xl mx-auto p-6 space-y-6">
        {/* Step indicator */}
        <div className="flex gap-2">
          {[1,2,3,4,5].map((i) => (
            <div key={i} className={`flex-1 h-1.5 rounded-full
                          ${i <= step ? "bg-accent-electric" : "bg-white/[0.08]"}`} />
          ))}
        </div>

        {/* ── 1 OBJECTIVE ──────────────────────────────────────── */}
        {step === 1 && (
          <div className="space-y-4" data-testid="wizard-step-1">
            <h2 className="font-display font-bold text-2xl">Pick your goal</h2>
            <input type="text" className="bigfm-input" placeholder="Campaign name"
                  value={name} onChange={(e) => setName(e.target.value)}
                  data-testid="wizard-name" />
            <div className="grid grid-cols-2 gap-3">
              {OBJECTIVES.map((o) => (
                <button key={o.id} onClick={() => setObj(o.id)}
                            data-testid={`wizard-obj-${o.id}`}
                            className={`rounded-2xl p-4 text-left border transition-colors
                              ${obj===o.id ? "border-accent-electric bg-accent-electric/[0.08]"
                                                  : "border-white/[0.08] hover:bg-white/[0.04]"}`}>
                  <div className="font-display font-bold text-lg">{o.title}</div>
                  <div className="text-xs text-text-secondary">{o.blurb}</div>
                </button>
              ))}
            </div>

            {/* Phase 18b — Channel takeover SKU (unlocks at $1k budget). */}
            {(parseFloat(bud.budget_total_usd) || 0) >= TAKEOVER_THRESHOLD ? (
              <button data-testid="wizard-obj-channel_takeover"
                            onClick={() => { setObj("channel_takeover");
                                                    setTakeover((p) => ({...p, enabled: true})); }}
                            className={`w-full rounded-2xl p-4 text-left border transition-colors
                              ${obj==="channel_takeover"
                                ? "border-amber-400 bg-amber-400/[0.08]"
                                : "border-amber-400/30 hover:bg-amber-400/[0.04]"}`}>
                <div className="flex items-center gap-2">
                  <span className="text-xl">🌟</span>
                  <div>
                    <div className="font-display font-bold text-lg">
                      Channel takeover · 2hr
                    </div>
                    <div className="text-xs text-text-secondary">
                      Own 100% of inter-song slots on one channel · min $1,000 / window
                    </div>
                  </div>
                </div>
              </button>
            ) : (
              <div data-testid="wizard-takeover-locked"
                      className="rounded-2xl p-3 border border-dashed border-white/[0.1] text-xs text-text-secondary">
                Channel takeover SKU unlocks at $1,000+ total budget.
              </div>
            )}

            {/* Takeover detail panel */}
            {obj === "channel_takeover" && (
              <div data-testid="wizard-takeover-panel"
                      className="rounded-2xl p-4 border border-amber-400/30 space-y-3">
                <div className="text-xs text-amber-300 font-semibold">
                  TAKEOVER · channel + window
                </div>
                <Group label="Channel">
                  <select className="bigfm-input" data-testid="takeover-channel"
                              value={takeover.channel_slug}
                              onChange={(e) => setTakeover({...takeover, channel_slug: e.target.value})}>
                    {CHANNELS.map((c) => <option key={c} value={c}>{c}</option>)}
                  </select>
                </Group>
                <div className="grid grid-cols-2 gap-3">
                  <Group label="Window start">
                    <input type="datetime-local" className="bigfm-input"
                                data-testid="takeover-window-start"
                                value={takeover.window_start}
                                onChange={(e) => setTakeover({...takeover, window_start: e.target.value})} />
                  </Group>
                  <Group label="Window end (≤2h)">
                    <input type="datetime-local" className="bigfm-input"
                                data-testid="takeover-window-end"
                                value={takeover.window_end}
                                onChange={(e) => setTakeover({...takeover, window_end: e.target.value})} />
                  </Group>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" data-testid="takeover-exclusive"
                              checked={takeover.exclusive}
                              onChange={(e) => setTakeover({...takeover, exclusive: e.target.checked})} />
                  Exclusive (no other ads run on this channel during the window)
                </label>
              </div>
            )}
          </div>
        )}

        {/* ── 2 TARGETING ──────────────────────────────────────── */}
        {step === 2 && (
          <div className="space-y-4" data-testid="wizard-step-2">
            <h2 className="font-display font-bold text-2xl">Targeting</h2>
            <Group label="Market">
              <select className="bigfm-input" value={t.market}
                          onChange={(e) => setT({...t, market: e.target.value})}>
                <option value="dubai">🇦🇪 Dubai</option>
                <option value="dfw">🇺🇸 DFW</option>
              </select>
            </Group>
            <Group label="Time of day">
              <Chips options={TIME_OF_DAY} selected={t.time_of_day}
                          onToggle={(v) => setT({...t, time_of_day: toggle(t.time_of_day, v)})} />
            </Group>
            <Group label="Days of week">
              <Chips options={DAYS} selected={DAYS.filter((_,i) => t.days_of_week.includes(i))}
                          onToggle={(v) => {
                            const i = DAYS.indexOf(v);
                            setT({...t, days_of_week: t.days_of_week.includes(i)
                              ? t.days_of_week.filter((x)=>x!==i) : [...t.days_of_week, i]});
                          }} />
            </Group>
            <Group label="Weather (optional)">
              <Chips options={WEATHER} selected={t.weather}
                          onToggle={(v) => setT({...t, weather: toggle(t.weather, v)})} />
            </Group>
            <Group label="Channels (optional)">
              <Chips options={CHANNELS} selected={t.channel_slugs}
                          onToggle={(v) => setT({...t, channel_slugs: toggle(t.channel_slugs, v)})} />
            </Group>
          </div>
        )}

        {/* ── 3 SCHEDULE ──────────────────────────────────────── */}
        {step === 3 && (
          <div className="space-y-4" data-testid="wizard-step-3">
            <h2 className="font-display font-bold text-2xl">Schedule</h2>
            <Group label="Start date">
              <input type="date" className="bigfm-input"
                        value={sched.start_date} data-testid="wizard-start-date"
                        onChange={(e) => setSched({...sched, start_date: e.target.value})} />
            </Group>
            <Group label="End date">
              <input type="date" className="bigfm-input"
                        value={sched.end_date} data-testid="wizard-end-date"
                        onChange={(e) => setSched({...sched, end_date: e.target.value})} />
            </Group>
            <p className="text-xs text-text-secondary">
              Both optional — leave blank to run indefinitely.
            </p>
          </div>
        )}

        {/* ── 4 BUDGET ──────────────────────────────────────── */}
        {step === 4 && (
          <div className="space-y-4" data-testid="wizard-step-4">
            <h2 className="font-display font-bold text-2xl">Budget</h2>
            <Group label="Total budget (USD)">
              <input type="number" min="0" className="bigfm-input"
                        data-testid="advertiser-budget-total"
                        data-legacy-testid="wizard-budget"
                        value={bud.budget_total_usd}
                        onChange={(e) => setBud({...bud, budget_total_usd: e.target.value})} />
            </Group>
            <Group label="Daily budget (optional, USD)">
              <input type="number" min="0" className="bigfm-input"
                        data-testid="advertiser-budget-daily"
                        value={bud.budget_daily_usd}
                        onChange={(e) => setBud({...bud, budget_daily_usd: e.target.value})} />
            </Group>
            <Group label="Attribution window (hours)">
              <input type="number" min="1" max="720" className="bigfm-input"
                          data-testid="advertiser-attribution-window"
                          data-legacy-testid="wizard-attribution-window-hours"
                          value={attributionWindowHours}
                          onChange={(e) => setAttributionWindowHours(e.target.value)} />
              <p className="text-[10px] text-text-secondary mt-1">
                Coupon saves / redemptions only count toward this campaign if
                they happen within this many hours of the ad serve. Default 24h.
              </p>
            </Group>
            <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-4">
              <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
                Estimated impressions
              </div>
              <div className="text-3xl font-display font-bold text-accent-electric mt-1"
                          data-testid="wizard-est-impressions">
                {estImpressions.toLocaleString()}
              </div>
              <div className="text-xs text-text-secondary mt-1">at $5 CPM</div>
            </div>
            {bud.budget_total_usd <= 100 && (
              <div className="text-xs text-accent-electric">
                ✓ Under $100 — campaigns auto-approve if creatives pass safety review.
              </div>
            )}
          </div>
        )}

        {/* ── 5 CREATIVE ──────────────────────────────────────── */}
        {step === 5 && (
          <div className="space-y-4" data-testid="wizard-step-5">
            <h2 className="font-display font-bold text-2xl">Creative</h2>
            <label className="rounded-2xl border border-dashed border-white/[0.20] p-6 flex flex-col items-center gap-2 cursor-pointer hover:border-accent-electric"
                        data-testid="wizard-upload-label">
              <Upload size={28} className="text-accent-electric" />
              <span className="text-sm">Upload 15s audio + optional image</span>
              <span className="text-[10px] text-text-secondary">MP3 ≤30s ≤5MB · image ≤1MB</span>
              <input type="file" accept="audio/*" className="hidden"
                        data-testid="wizard-audio-input"
                        onChange={(e) => e.target.files?.[0] && uploadCreative(e.target.files[0])} />
            </label>

            {creatives.length > 0 && (
              <div className="space-y-2" data-testid="wizard-creative-list">
                {creatives.map((cr) => {
                  const v = cr.brand_safety_check?.verdict;
                  const tone = v === "approved" ? "#4ade80" :
                                  v === "rejected" ? "#fb7185" : "#fdb756";
                  const Icon = v === "approved" ? Check :
                                    v === "rejected" ? X : AlertTriangle;
                  return (
                    <div key={cr.creative_id}
                              data-testid={`wizard-creative-${v}`}
                              className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 flex items-center gap-3">
                      <Icon size={18} style={{color: tone}} />
                      <div className="flex-1 min-w-0">
                        <div className="text-sm truncate">{cr.creative_id}</div>
                        <div className="text-[10px] uppercase tracking-widest font-mono"
                                  style={{color: tone}}>
                          {v} · confidence {Math.round((cr.brand_safety_check?.confidence||0)*100)}%
                        </div>
                        {cr.brand_safety_check?.issues?.length > 0 && (
                          <details className="mt-1 text-[10px] text-text-secondary">
                            <summary>{cr.brand_safety_check.issues.length} issues</summary>
                            <ul className="list-disc pl-4">
                              {cr.brand_safety_check.issues.map((i, k) => (
                                <li key={k}>{i.category} ({i.severity})</li>
                              ))}
                            </ul>
                          </details>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* nav */}
        <div className="flex gap-2 pt-4">
          {step > 1 && <button className="bigfm-cta-ghost" onClick={prev}
                                                  data-testid="wizard-prev">
            <ArrowLeft size={14} /> Back</button>}
          <div className="flex-1" />
          {step < 5 && <button className="bigfm-cta" onClick={next} data-testid="wizard-next">
            Continue <ArrowRight size={14} /></button>}
          {step === 5 && <button className="bigfm-cta" onClick={submit} disabled={submitting}
                                                  data-testid="wizard-submit">
            {submitting ? <Loader2 className="animate-spin" size={14} /> : <Check size={14} />}
            {submitting ? " Submitting..." : " Submit campaign"}
          </button>}
        </div>
      </div>
    </div>
  );
}


function Group({ label, children }) {
  return <label className="block">
    <span className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">{label}</span>
    <div className="mt-1">{children}</div>
  </label>;
}

function Chips({ options, selected, onToggle }) {
  return <div className="flex gap-2 flex-wrap">
    {options.map((o) => (
      <button key={o} onClick={() => onToggle(o)}
                  data-testid={`chip-${o}`}
                  className={`text-xs px-3 py-1.5 rounded-full border
                      ${selected.includes(o) ? "border-accent-electric bg-accent-electric/[0.08] text-accent-electric"
                                                          : "border-white/[0.10] text-text-secondary hover:bg-white/[0.04]"}`}>{o}</button>
    ))}
  </div>;
}
