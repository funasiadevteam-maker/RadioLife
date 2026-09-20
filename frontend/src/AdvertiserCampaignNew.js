// AdvertiserCampaignNew.js — Phase 4.5: self-serve 6-step campaign wizard.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, ChevronLeft, ChevronRight, Check, Sparkles, Volume2,
  Building2, Target, DollarSign, Megaphone, FileText, Send,
} from "lucide-react";
import "./AdminImaging.css";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const STEPS = [
  { id: 1, label: "Business",   icon: Building2 },
  { id: 2, label: "Brief",      icon: FileText },
  { id: 3, label: "Targeting",  icon: Target },
  { id: 4, label: "Budget",     icon: DollarSign },
  { id: 5, label: "AI Creative",icon: Sparkles },
  { id: 6, label: "Review",     icon: Send },
];

const MARKETS = [{ id: "dubai", label: "🇦🇪 Dubai" }, { id: "dfw", label: "🇺🇸 DFW" }];
const DAYPARTS = [
  { id: "morning_drive",  label: "Morning Drive" },
  { id: "lunch_rush",     label: "Lunch Rush" },
  { id: "evening_drive",  label: "Evening Drive" },
  { id: "weekend_brunch", label: "Weekend Brunch" },
  { id: "overnight_lounge", label: "Overnight Lounge" },
];
const LANGUAGES = ["hindi", "english", "punjabi", "tamil", "telugu", "malayalam"];
// Phase 9b — Smart trigger vocab.  Keep aligned with backend
// services/route_ad_engine.py.
const WEATHER_TRIGGERS = [
  { id: "rain",         label: "Rain" },
  { id: "thunderstorm", label: "Thunderstorm" },
  { id: "hot",          label: "Hot" },
  { id: "cold",         label: "Cold" },
  { id: "clear",        label: "Clear" },
  { id: "cloudy",       label: "Cloudy" },
  { id: "haze",         label: "Haze" },
  { id: "snow",         label: "Snow" },
];
const TRAFFIC_TRIGGERS = [
  { id: "light",     label: "Light" },
  { id: "moderate",  label: "Moderate" },
  { id: "heavy",     label: "Heavy" },
];
const COMMUTE_MODES = [
  { id: "driver",    label: "Driver" },
  { id: "passenger", label: "Passenger" },
  { id: "transit",   label: "Transit" },
];
const SMART_DAYPARTS = [
  { id: "morning_drive", label: "Morning Drive" },
  { id: "midday",        label: "Midday" },
  { id: "lunch",         label: "Lunch" },
  { id: "afternoon",     label: "Afternoon" },
  { id: "evening_drive", label: "Evening Drive" },
  { id: "dinner",        label: "Dinner" },
  { id: "night",         label: "Night" },
  { id: "late_night",    label: "Late Night" },
];
const VOICES = [
  { key: "veer_dubai", label: "Veer (Dubai male, smooth)" },
  { key: "monika_dubai", label: "Monika (Dubai female, warm)" },
  { key: "dj_dubai", label: "DJ Charlie (party host)" },
  { key: "aanya_hindi", label: "Aanya (Hindi female)" },
  { key: "dhruv_punjabi", label: "Dhruv (Punjabi male)" },
];

export default function AdvertiserCampaignNew() {
  const navigate = useNavigate();
  const [step, setStep] = useState(1);
  const [profile, setProfile] = useState(null);
  const [businesses, setBusinesses] = useState([]);
  const [creating, setCreating] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [aiResult, setAiResult] = useState(null);

  const [form, setForm] = useState({
    business_id: "", new_business: null,           // step 1
    campaign_name: "", brief: "",                  // step 2
    market: "dubai", dayparts: [], languages: [],  // step 3
    // Phase 9b — Smart triggers
    weather_triggers: [], traffic_triggers: [],
    commute_modes: [], temperature_band: null,
    budget_cents: 5000, daily_budget_cents: 1000,
    bid_cents_per_impression: 200, pacing: "even", // step 4
    voice_key: "aanya_hindi", duration_sec: 20,
    tone: "warm-energetic", action_labels: [],     // step 5
    creative_id: null,
  });
  const [smartOpen, setSmartOpen] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [me, biz] = await Promise.all([
          axios.get(`${API}/advertiser/me`),
          axios.get(`${API}/advertiser/businesses`),
        ]);
        setProfile(me.data); setBusinesses(biz.data.items || []);
        if (biz.data.items?.length) {
          setForm((f) => ({ ...f, business_id: biz.data.items[0].business_id }));
        }
      } catch (e) {
        toast.error("Apply as advertiser first");
        navigate("/advertiser");
      }
    })();
  }, [navigate]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const toggleInList = (k, v) => setForm((f) => ({
    ...f, [k]: f[k].includes(v) ? f[k].filter((x) => x !== v) : [...f[k], v],
  }));

  const createBusiness = async () => {
    if (!form.new_business?.name) return toast.error("Name required");
    setCreating(true);
    try {
      const r = await axios.post(`${API}/advertiser/businesses`, form.new_business);
      setBusinesses((b) => [...b, r.data]);
      set("business_id", r.data.business_id); set("new_business", null);
      toast.success("Business created");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Create failed");
    } finally { setCreating(false); }
  };

  const generateCreative = async () => {
    if (!form.brief) return toast.error("Add a brief first (step 2)");
    setGenerating(true); setAiResult(null);
    try {
      const r = await axios.post(`${API}/advertiser/creative/ai_sponsor_read`, {
        business_id: form.business_id, brief: form.brief,
        voice_key: form.voice_key, duration_sec: form.duration_sec,
        tone: form.tone, action_labels: form.action_labels,
      });
      setAiResult(r.data);
      set("creative_id", r.data.creative_id);
      toast.success("AI sponsor read generated");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Generation failed");
    } finally { setGenerating(false); }
  };

  const submit = async () => {
    if (!form.creative_id) return toast.error("Generate the AI creative first (step 5)");
    setSubmitting(true);
    try {
      const r = await axios.post(`${API}/advertiser/campaigns`, {
        name: form.campaign_name || "Untitled campaign",
        campaign_type: "sponsor_read",
        business_id: form.business_id,
        budget_cents: form.budget_cents, daily_budget_cents: form.daily_budget_cents,
        bid_cents_per_impression: form.bid_cents_per_impression,
        pacing: form.pacing,
        targeting: {
          markets: [form.market],
          dayparts: form.dayparts,
          languages: form.languages,
          // Phase 9b — Smart triggers (omit if empty arrays so backend
          // treats them as "any")
          ...(form.weather_triggers.length && {weather_triggers: form.weather_triggers}),
          ...(form.traffic_triggers.length && {traffic_triggers: form.traffic_triggers}),
          ...(form.commute_modes.length && {commute_modes: form.commute_modes}),
          ...(form.temperature_band &&
              form.temperature_band.min_c != null &&
              form.temperature_band.max_c != null && {
            temperature_band: form.temperature_band}),
        },
        creative_ids: [form.creative_id],
        frequency_cap: { per_hour: 1, per_day: 3, per_week: 8 },
      });
      toast.success(`Campaign created. Status: ${r.data.status}`);
      setTimeout(() => navigate("/advertiser"), 1000);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Submit failed");
    } finally { setSubmitting(false); }
  };

  if (!profile) {
    return <div className="admin-img-wrap"><Loader2 className="spin" size={28} /></div>;
  }

  return (
    <div className="admin-img-wrap" data-testid="campaign-wizard">
      <header className="admin-img-header">
        <div>
          <Link to="/advertiser" style={{ color: "#888892", fontSize: 12, textDecoration: "none" }} data-testid="back-to-advertiser">
            <ChevronLeft size={11} style={{ verticalAlign: "-1px" }} /> back to advertiser dashboard
          </Link>
          <h1><Megaphone size={24} style={{ verticalAlign: "-4px", marginRight: 8 }} />New campaign</h1>
          <p>Self-serve 6-step wizard: business → brief → targeting → budget → AI creative → review.</p>
        </div>
      </header>

      {/* Stepper */}
      <nav className="admin-img-pills" data-testid="wizard-stepper" style={{ flexWrap: "wrap", marginBottom: 24 }}>
        {STEPS.map((s) => {
          const Icon = s.icon;
          const active = step === s.id;
          const done = step > s.id;
          return (
            <button key={s.id} className={`asset-type-chip ${active ? "on" : ""}`}
              style={{ opacity: done ? 0.7 : 1 }}
              onClick={() => setStep(s.id)} data-testid={`step-${s.id}`}>
              {done ? <Check size={12} /> : <Icon size={12} />} {s.id}. {s.label}
            </button>
          );
        })}
      </nav>

      {/* Step 1 — Business */}
      {step === 1 && (
        <section className="img-station-card" data-testid="step-1-business">
          <div className="meta-label"><Building2 size={11} /> SELECT OR CREATE BUSINESS</div>
          {businesses.length > 0 && (
            <select className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%", maxWidth: 480, marginTop: 8 }}
              value={form.business_id} onChange={(e) => set("business_id", e.target.value)}
              data-testid="biz-select">
              {businesses.map((b) => (
                <option key={b.business_id} value={b.business_id}>
                  {b.name} ({b.market})
                </option>
              ))}
            </select>
          )}
          <button className="asset-type-chip" style={{ marginTop: 12 }}
            onClick={() => set("new_business", form.new_business ? null : { name: "", category: "restaurant", market: profile.market || "dubai" })}
            data-testid="toggle-new-biz">
            {form.new_business ? "Cancel new" : "+ Create new business"}
          </button>
          {form.new_business && (
            <div style={{ marginTop: 12, padding: 14, background: "#0f0f15", borderRadius: 6 }} data-testid="new-biz-form">
              <label className="meta-label">NAME</label>
              <input className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%" }}
                value={form.new_business.name}
                onChange={(e) => set("new_business", { ...form.new_business, name: e.target.value })}
                data-testid="biz-name" />
              <label className="meta-label" style={{ marginTop: 8 }}>CATEGORY</label>
              <select className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%" }}
                value={form.new_business.category}
                onChange={(e) => set("new_business", { ...form.new_business, category: e.target.value })}
                data-testid="biz-category">
                <option value="restaurant">Restaurant</option>
                <option value="spa">Spa / Salon</option>
                <option value="retail">Retail</option>
                <option value="event">Event</option>
                <option value="service">Service</option>
              </select>
              <label className="meta-label" style={{ marginTop: 8 }}>ADDRESS</label>
              <input className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%" }}
                value={form.new_business.address || ""}
                onChange={(e) => set("new_business", { ...form.new_business, address: e.target.value })}
                data-testid="biz-address" />
              <button className="img-regenerate-btn" onClick={createBusiness} disabled={creating}
                style={{ marginTop: 14 }} data-testid="biz-create-btn">
                {creating ? <Loader2 className="spin" size={14} /> : <Check size={14} />}
                {creating ? " Creating..." : " Create business"}
              </button>
            </div>
          )}
        </section>
      )}

      {/* Step 2 — Brief */}
      {step === 2 && (
        <section className="img-station-card" data-testid="step-2-brief">
          <label className="meta-label"><FileText size={11} /> CAMPAIGN NAME</label>
          <input className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%" }}
            value={form.campaign_name} onChange={(e) => set("campaign_name", e.target.value)}
            placeholder="e.g. Karama Friday brunch — Apr"
            data-testid="campaign-name" />
          <label className="meta-label" style={{ marginTop: 12 }}>OFFER / KEY MESSAGE</label>
          <textarea
            value={form.brief} onChange={(e) => set("brief", e.target.value)}
            rows={6} data-testid="brief-input"
            placeholder="Describe the offer or what should be said. e.g. 'Friday brunch buffet at Ravi's Karama, AED 89 unlimited karak. Tap save to claim 20% off until Sunday.'"
            style={{ width: "100%", background: "#0f0f15", color: "#fff", padding: 12,
                      fontSize: 13, borderRadius: 6, border: "1px solid #25252f", marginTop: 8 }} />
          <p style={{ color: "#888892", fontSize: 11, marginTop: 8 }}>
            Our 2-stage AI script pipeline (OpenAI draft → Naturalness rewrite → ElevenLabs voice → loudnorm) will turn this into a 15-30s sponsor read.
          </p>
        </section>
      )}

      {/* Step 3 — Targeting */}
      {step === 3 && (
        <section className="img-station-card" data-testid="step-3-targeting">
          <label className="meta-label"><Target size={11} /> MARKET</label>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            {MARKETS.map((m) => (
              <button key={m.id} className={`asset-type-chip ${form.market === m.id ? "on" : ""}`}
                onClick={() => set("market", m.id)} data-testid={`market-${m.id}`}>{m.label}</button>
            ))}
          </div>
          <label className="meta-label" style={{ marginTop: 16 }}>DAYPARTS (when to play)</label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {DAYPARTS.map((d) => (
              <button key={d.id} className={`asset-type-chip ${form.dayparts.includes(d.id) ? "on" : ""}`}
                onClick={() => toggleInList("dayparts", d.id)} data-testid={`daypart-${d.id}`}>{d.label}</button>
            ))}
          </div>
          <label className="meta-label" style={{ marginTop: 16 }}>LANGUAGES (listener preference overlap)</label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {LANGUAGES.map((l) => (
              <button key={l} className={`asset-type-chip ${form.languages.includes(l) ? "on" : ""}`}
                onClick={() => toggleInList("languages", l)} data-testid={`lang-${l}`}>{l}</button>
            ))}
          </div>

          {/* Phase 9b — Smart triggers (collapsible) */}
          <div style={{ marginTop: 24, borderTop: "1px solid #1c1c26", paddingTop: 16 }} data-testid="smart-triggers-section">
            <button type="button" className="asset-type-chip"
              onClick={() => setSmartOpen((v) => !v)}
              data-testid="toggle-smart-triggers"
              style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <Sparkles size={11} /> Smart triggers {smartOpen ? "▴" : "▾"}
            </button>
            <div style={{ color: "#888892", fontSize: 11, marginTop: 6, lineHeight: 1.4 }}>
              Optional — only fire this ad on the right route, weather, traffic, daypart or commute mode. Leave blank for "any".
            </div>
            {smartOpen && (
              <div style={{ marginTop: 14 }} data-testid="smart-triggers-body">
                <label className="meta-label">WEATHER (any-match)</label>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {WEATHER_TRIGGERS.map((w) => (
                    <button key={w.id} type="button"
                      className={`asset-type-chip ${form.weather_triggers.includes(w.id) ? "on" : ""}`}
                      onClick={() => toggleInList("weather_triggers", w.id)}
                      data-testid={`weather-${w.id}`}>{w.label}</button>
                  ))}
                </div>
                <label className="meta-label" style={{ marginTop: 14 }}>TRAFFIC (any-match)</label>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {TRAFFIC_TRIGGERS.map((t) => (
                    <button key={t.id} type="button"
                      className={`asset-type-chip ${form.traffic_triggers.includes(t.id) ? "on" : ""}`}
                      onClick={() => toggleInList("traffic_triggers", t.id)}
                      data-testid={`traffic-${t.id}`}>{t.label}</button>
                  ))}
                </div>
                <label className="meta-label" style={{ marginTop: 14 }}>SMART DAYPARTS (commute-aware)</label>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {SMART_DAYPARTS.map((d) => (
                    <button key={`smart-dp-${d.id}`} type="button"
                      className={`asset-type-chip ${form.dayparts.includes(d.id) ? "on" : ""}`}
                      onClick={() => toggleInList("dayparts", d.id)}
                      data-testid={`smart-daypart-${d.id}`}>{d.label}</button>
                  ))}
                </div>
                <label className="meta-label" style={{ marginTop: 14 }}>COMMUTE MODES (only fire for these listeners)</label>
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 6 }}>
                  {COMMUTE_MODES.map((m) => (
                    <button key={m.id} type="button"
                      className={`asset-type-chip ${form.commute_modes.includes(m.id) ? "on" : ""}`}
                      onClick={() => toggleInList("commute_modes", m.id)}
                      data-testid={`commute-mode-${m.id}`}>{m.label}</button>
                  ))}
                </div>
                <label className="meta-label" style={{ marginTop: 14 }}>TEMPERATURE BAND (optional °C)</label>
                <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
                  <input className="asset-btn" type="number"
                    placeholder="min °C"
                    style={{ background: "#15151e", padding: 9, fontSize: 13, width: 110 }}
                    value={form.temperature_band?.min_c ?? ""}
                    onChange={(e) => set("temperature_band", {
                      ...(form.temperature_band || {}),
                      min_c: e.target.value === "" ? null : Number(e.target.value),
                    })}
                    data-testid="temp-min-c" />
                  <input className="asset-btn" type="number"
                    placeholder="max °C"
                    style={{ background: "#15151e", padding: 9, fontSize: 13, width: 110 }}
                    value={form.temperature_band?.max_c ?? ""}
                    onChange={(e) => set("temperature_band", {
                      ...(form.temperature_band || {}),
                      max_c: e.target.value === "" ? null : Number(e.target.value),
                    })}
                    data-testid="temp-max-c" />
                </div>
              </div>
            )}
          </div>
        </section>
      )}

      {/* Step 4 — Budget */}
      {step === 4 && (
        <section className="img-station-card" data-testid="step-4-budget">
          <label className="meta-label"><DollarSign size={11} /> TOTAL BUDGET (USD cents)</label>
          <input className="asset-btn" type="number" style={{ background: "#15151e", padding: 11, fontSize: 14, width: 240, marginTop: 8 }}
            value={form.budget_cents} onChange={(e) => set("budget_cents", Number(e.target.value))}
            data-testid="budget-total" />
          <label className="meta-label" style={{ marginTop: 16 }}>DAILY BUDGET (cents)</label>
          <input className="asset-btn" type="number" style={{ background: "#15151e", padding: 11, fontSize: 14, width: 240 }}
            value={form.daily_budget_cents} onChange={(e) => set("daily_budget_cents", Number(e.target.value))}
            data-testid="budget-daily" />
          <label className="meta-label" style={{ marginTop: 16 }}>BID (cents per impression)</label>
          <input className="asset-btn" type="number" style={{ background: "#15151e", padding: 11, fontSize: 14, width: 240 }}
            value={form.bid_cents_per_impression} onChange={(e) => set("bid_cents_per_impression", Number(e.target.value))}
            data-testid="budget-bid" />
          <label className="meta-label" style={{ marginTop: 16 }}>PACING</label>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            {["even", "asap", "smart"].map((p) => (
              <button key={p} className={`asset-type-chip ${form.pacing === p ? "on" : ""}`}
                onClick={() => set("pacing", p)} data-testid={`pacing-${p}`}>{p}</button>
            ))}
          </div>
        </section>
      )}

      {/* Step 5 — AI Creative */}
      {step === 5 && (
        <section className="img-station-card" data-testid="step-5-creative">
          <label className="meta-label"><Sparkles size={11} /> VOICE</label>
          <select className="asset-btn" style={{ background: "#15151e", padding: 11, fontSize: 14, width: "100%", maxWidth: 480, marginTop: 8 }}
            value={form.voice_key} onChange={(e) => set("voice_key", e.target.value)}
            data-testid="voice-key-select">
            {VOICES.map((v) => (<option key={v.key} value={v.key}>{v.label}</option>))}
          </select>
          <label className="meta-label" style={{ marginTop: 12 }}>DURATION</label>
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            {[15, 20, 30].map((d) => (
              <button key={d} className={`asset-type-chip ${form.duration_sec === d ? "on" : ""}`}
                onClick={() => set("duration_sec", d)} data-testid={`dur-${d}`}>{d}s</button>
            ))}
          </div>
          <label className="meta-label" style={{ marginTop: 12 }}>TONE</label>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {["warm-energetic", "smooth-late-night", "hyped-club", "narrative-storytelling"].map((t) => (
              <button key={t} className={`asset-type-chip ${form.tone === t ? "on" : ""}`}
                onClick={() => set("tone", t)} data-testid={`tone-${t}`}>{t}</button>
            ))}
          </div>
          <button className="img-regenerate-btn" onClick={generateCreative} disabled={generating || !form.brief}
            style={{ marginTop: 18 }} data-testid="generate-creative-btn">
            {generating ? <Loader2 className="spin" size={14} /> : <Sparkles size={14} />}
            {generating ? " Generating (15-30s)..." : " Generate AI sponsor read"}
          </button>
          {aiResult && (
            <div style={{ marginTop: 18, padding: 14, background: "#0f0f15", borderRadius: 6 }} data-testid="ai-preview">
              <div className="meta-label" style={{ color: "#4ade80" }}>
                <Check size={11} /> CREATIVE GENERATED · {aiResult.duration_sec?.toFixed(1)}s
              </div>
              <p style={{ color: "#fff", fontSize: 13, marginTop: 8, lineHeight: 1.6 }}>{aiResult.transcript}</p>
              <audio controls src={`${process.env.REACT_APP_BACKEND_URL}${aiResult.audio_url}`}
                style={{ width: "100%", marginTop: 12 }} data-testid="ai-audio-preview" />
              <p style={{ color: "#888892", fontSize: 10, marginTop: 8 }}>
                Creative will go to admin queue for approval; once approved + campaign approved, it will start playing on listener segments.
              </p>
            </div>
          )}
        </section>
      )}

      {/* Step 6 — Review */}
      {step === 6 && (
        <section className="img-station-card" data-testid="step-6-review">
          <div className="meta-label"><Send size={11} /> REVIEW &amp; SUBMIT</div>
          <table style={{ width: "100%", marginTop: 12, color: "#ddd", fontSize: 13, lineHeight: 1.8 }}>
            <tbody>
              <tr><td style={{ color: "#888" }}>Business</td><td><b>{businesses.find((b) => b.business_id === form.business_id)?.name || "—"}</b></td></tr>
              <tr><td style={{ color: "#888" }}>Campaign name</td><td><b>{form.campaign_name || "—"}</b></td></tr>
              <tr><td style={{ color: "#888" }}>Market</td><td><b>{form.market}</b></td></tr>
              <tr><td style={{ color: "#888" }}>Dayparts</td><td>{form.dayparts.join(", ") || "any"}</td></tr>
              <tr><td style={{ color: "#888" }}>Languages</td><td>{form.languages.join(", ") || "any"}</td></tr>
              <tr><td style={{ color: "#888" }}>Total budget</td><td><b style={{ color: "#4ade80" }}>${(form.budget_cents / 100).toFixed(2)}</b></td></tr>
              <tr><td style={{ color: "#888" }}>Daily budget</td><td>${(form.daily_budget_cents / 100).toFixed(2)}</td></tr>
              <tr><td style={{ color: "#888" }}>Bid CPM</td><td>{form.bid_cents_per_impression}¢ ($. {(form.bid_cents_per_impression * 10 / 100).toFixed(2)} CPM)</td></tr>
              <tr><td style={{ color: "#888" }}>Pacing</td><td>{form.pacing}</td></tr>
              <tr><td style={{ color: "#888" }}>Voice</td><td>{form.voice_key} · {form.duration_sec}s</td></tr>
              <tr><td style={{ color: "#888" }}>AI Creative</td>
                  <td>{form.creative_id ? <b style={{ color: "#4ade80" }}><Volume2 size={11} /> {form.creative_id}</b> : <b style={{ color: "#fb7185" }}>NOT GENERATED</b>}</td></tr>
            </tbody>
          </table>
          <p style={{ color: "#fdb756", fontSize: 12, marginTop: 16 }}>
            Once submitted, your campaign goes to <b>pending_approval</b> status. A FUUSIC admin
            reviews the brief and creative; once approved, the campaign starts spending against
            the daily budget on matching listener segments.
          </p>
          <button className="img-regenerate-btn" onClick={submit}
            disabled={submitting || !form.creative_id || !form.business_id}
            style={{ marginTop: 18 }} data-testid="submit-campaign-btn">
            {submitting ? <Loader2 className="spin" size={14} /> : <Send size={14} />}
            {submitting ? " Submitting..." : " SUBMIT CAMPAIGN"}
          </button>
        </section>
      )}

      {/* Navigation */}
      <nav style={{ display: "flex", justifyContent: "space-between", marginTop: 20 }} data-testid="wizard-nav">
        <button className="asset-type-chip" onClick={() => setStep((s) => Math.max(1, s - 1))} disabled={step === 1} data-testid="prev-step">
          <ChevronLeft size={12} /> Back
        </button>
        <button className="asset-type-chip on" onClick={() => setStep((s) => Math.min(6, s + 1))} disabled={step === 6} data-testid="next-step">
          Next <ChevronRight size={12} />
        </button>
      </nav>
    </div>
  );
}
