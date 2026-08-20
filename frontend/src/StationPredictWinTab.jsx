/** Sub-Phase E3 — Predict & Win business builder tab.
 *
 * Lives at `/station/:slug/predict-win`.  Only renderable by the station
 * owner of a business_radio station (server returns 403 otherwise).
 *
 *  • Campaign list with status + approval pills.
 *  • Wizard modal: create a draft campaign (event_type restricted to
 *      restaurant_bar / club_event / business_custom, 2-4 answer options,
 *      lock_time picker, 1 prize, then submit-for-approval).
 *  • Per-campaign "Pair TV" button (returns 8-char code) + QR display.
 *  • Per-campaign "Resolve Now" button (only renderable post-lock).
 *  • Analytics panel: total entries, unique users, distribution bars,
 *      timeseries (Recharts).
 *
 *  Compliance: server-side _guard_lexicon rejects any forbidden words
 *  in title/description/option label/prize title.  Front-end mirrors a
 *  small client-side message; backend is the source of truth.
 */
/* eslint-disable react-hooks/set-state-in-effect, react-hooks/purity */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import QRCode from "react-qr-code";
import {
  PartyPopper, Wallet, ClipboardList, Trophy, Tv2, QrCode, Clock,
  Plus, X, BarChart3, ChevronRight, Sparkles, ShieldCheck, AlertCircle,
} from "lucide-react";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  LineChart, Line, CartesianGrid,
} from "recharts";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
axios.defaults.withCredentials = true;

const BUSINESS_EVENT_TYPES = [
  { value: "restaurant_bar", label: "Restaurant / Bar" },
  { value: "club_event",       label: "Club night / event" },
  { value: "business_custom", label: "Custom (other)" },
];

const STATUS_PILL = {
  draft:       { label: "Draft",         color: "#94a3b8", bg: "rgba(148,163,184,0.12)" },
  scheduled: { label: "Scheduled", color: "#38bdf8", bg: "rgba(56,189,248,0.12)" },
  live:         { label: "Live",            color: "#22c55e", bg: "rgba(34,197,94,0.12)" },
  locked:      { label: "Locked",        color: "#f59e0b", bg: "rgba(245,158,11,0.12)" },
  resolved:  { label: "Resolved",     color: "#a78bfa", bg: "rgba(167,139,250,0.18)" },
  cancelled: { label: "Cancelled",   color: "#f87171", bg: "rgba(248,113,113,0.12)" },
};
const APPROVAL_PILL = {
  draft:                { label: "Not submitted",      color: "#94a3b8" },
  pending_review: { label: "Pending review",   color: "#fbbf24" },
  approved:           { label: "Approved",              color: "#22c55e" },
  rejected:           { label: "Rejected",                color: "#f87171" },
};

function _toIsoLocal(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}T`
              + `${pad(date.getHours())}:${pad(date.getMinutes())}`;
}
function _isoFromLocal(local) {
  if (!local) return null;
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}
function _fmtCountdown(secs) {
  if (secs == null) return "—";
  if (secs <= 0) return "LOCKED";
  const m = Math.floor(secs / 60), s = secs % 60;
  return `${m}m ${String(s).padStart(2,"0")}s`;
}

export default function StationPredictWinTab() {
  const { slug } = useParams();
  const [station, setStation]   = useState(null);
  const [items, setItems]         = useState([]);
  const [loading, setLoading]  = useState(true);
  const [error, setError]         = useState(null);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [pairFor, setPairFor]   = useState(null);
  const [resolveFor, setResolveFor] = useState(null);
  const [analyticsFor, setAnalyticsFor] = useState(null);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const r = await axios.get(
        `${API}/business/predict-win/stations/${encodeURIComponent(slug)}/campaigns`);
      setStation(r.data.station);
      setItems(r.data.items || []);
      setError(null);
    } catch (e) {
      const detail = e.response?.data?.detail;
      setError(detail?.message || detail?.code || "Unable to load campaigns.");
    } finally {
      setLoading(false);
    }
  }, [slug]);
  useEffect(() => { load(); }, [load]);

  const onCreated = () => { setWizardOpen(false); load(); };
  const onTVPaired = () => { setPairFor(null); load(); };
  const onResolved = () => { setResolveFor(null); load(); };

  if (loading) {
    return (
      <div data-testid="predict-win-tab-loading" style={page}>
        <div style={muted}>Loading your campaigns…</div>
      </div>);
  }
  if (error) {
    return (
      <div data-testid="predict-win-tab-error" style={page}>
        <div style={errorPanel}>
          <AlertCircle size={20}/> {error}
        </div>
      </div>);
  }

  return (
    <div data-testid="predict-win-tab" style={page}>
      <div style={headerRow}>
        <div style={{ minWidth: 0 }}>
          <div style={breadcrumb}>
            <Link to={`/station/${slug}`} style={crumbLink}>
              {station?.name || slug}
            </Link>
            <ChevronRight size={14}/>
            <span>Predict &amp; Win</span>
          </div>
          <h1 data-testid="predict-win-tab-title" style={pageTitle}>
            Predict &amp; Win campaigns
          </h1>
          <div style={subText}>
            Create venue prediction campaigns, pair an in-store TV, and credit
            prizes automatically when you call the winning pick.  All campaigns
            still require admin approval before they go live.
          </div>
        </div>
        <button data-testid="create-campaign-btn"
                  style={primaryBtn}
                  onClick={() => setWizardOpen(true)}>
          <Plus size={16}/> Create campaign
        </button>
      </div>

      <div style={complianceBanner} data-testid="predict-win-compliance-note">
        <ShieldCheck size={16}/>
        <span>
          <strong>No purchase necessary</strong> on any prediction campaign.
          Customers must be physically at your venue (check-in QR is enforced).
          The server rejects forbidden terminology — use words like
          <em>pick</em>, <em>predict</em>, or <em>guess</em> instead.
        </span>
      </div>

      <div style={listGrid} data-testid="predict-win-campaigns-list">
        {items.length === 0 && (
          <div style={emptyState} data-testid="predict-win-empty">
            <Sparkles size={48} color="rgba(255,255,255,0.18)" />
            <h2>No campaigns yet.</h2>
            <p>Create your first venue prediction to engage customers in person.</p>
            <button onClick={() => setWizardOpen(true)}
                          style={primaryBtn}
                          data-testid="empty-create-campaign-btn">
              <Plus size={16}/> Create your first
            </button>
          </div>
        )}
        {items.map((c) => (
          <CampaignRow key={c.campaign_id}
                              campaign={c}
                              onPairTV={() => setPairFor(c)}
                              onResolve={() => setResolveFor(c)}
                              onAnalytics={() => setAnalyticsFor(c)} />
        ))}
      </div>

      {wizardOpen && (
        <WizardModal slug={slug} onClose={() => setWizardOpen(false)}
                            onCreated={onCreated} />)}
      {pairFor && (
        <PairTVModal campaign={pairFor} onClose={() => setPairFor(null)}
                            onPaired={onTVPaired}/>)}
      {resolveFor && (
        <ResolveModal campaign={resolveFor} onClose={() => setResolveFor(null)}
                              onResolved={onResolved}/>)}
      {analyticsFor && (
        <AnalyticsModal campaign={analyticsFor}
                                  onClose={() => setAnalyticsFor(null)}/>)}
    </div>
  );
}

// ─── Row ─────────────────────────────────────────────────────────────
function CampaignRow({ campaign, onPairTV, onResolve, onAnalytics }) {
  const status = STATUS_PILL[campaign.status] || STATUS_PILL.draft;
  const approval = APPROVAL_PILL[campaign.approval_status] || APPROVAL_PILL.draft;
  const lockTime = campaign.lock_time ? new Date(campaign.lock_time) : null;
  const locked = lockTime && lockTime.getTime() <= Date.now();
  const canResolve = (campaign.approval_status === "approved")
                                  && locked
                                  && campaign.status !== "resolved"
                                  && campaign.status !== "cancelled";
  return (
    <div data-testid={`campaign-row-${campaign.campaign_id}`}
            data-campaign-status={campaign.status}
            data-campaign-approval={campaign.approval_status}
            style={card}>
      <div style={{ display: "flex", justifyContent: "space-between",
                              gap: 12, marginBottom: 8 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <h3 style={{ ...cardTitle, marginBottom: 6 }}>{campaign.title}</h3>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap",
                                  marginBottom: 8 }}>
            <span style={pill(status.color, status.bg)}>{status.label}</span>
            <span style={pillOutline(approval.color)}>{approval.label}</span>
            {campaign.checkin_required && (
              <span style={pillOutline("#06b6d4")}
                          data-testid={`campaign-checkin-required-${campaign.campaign_id}`}>
                <QrCode size={11} style={{verticalAlign: "-2px"}}/> Check-in required
              </span>)}
          </div>
          <div style={metaRow}>
            <span><strong>{campaign.entry_count}</strong> entries</span>
            <span style={dot}>·</span>
            <span><strong>{campaign.prize_count}</strong> prize(s)</span>
            <span style={dot}>·</span>
            <span><strong>{campaign.award_count}</strong> awarded</span>
            {lockTime && (
              <>
                <span style={dot}>·</span>
                <Clock size={12} style={{ verticalAlign: "-2px" }}/>
                <span>{lockTime.toLocaleString()}</span>
              </>)}
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6,
                                alignItems: "stretch", flexShrink: 0 }}>
          <button data-testid={`campaign-analytics-btn-${campaign.campaign_id}`}
                          style={secondaryBtn}
                          onClick={onAnalytics}>
            <BarChart3 size={13}/> Analytics
          </button>
          <button data-testid={`campaign-pair-tv-btn-${campaign.campaign_id}`}
                          style={secondaryBtn}
                          onClick={onPairTV}>
            <Tv2 size={13}/> Pair TV
          </button>
          {canResolve && (
            <button data-testid={`campaign-resolve-btn-${campaign.campaign_id}`}
                            style={dangerBtn}
                            onClick={onResolve}>
              <Trophy size={13}/> Resolve now
            </button>)}
        </div>
      </div>
    </div>);
}

// ─── Wizard ──────────────────────────────────────────────────────────
function WizardModal({ slug, onClose, onCreated }) {
  const [title, setTitle]            = useState("");
  const [description, setDesc]     = useState("");
  const [eventType, setEventType] = useState("restaurant_bar");
  const [eventLabel, setEventLbl] = useState("");
  const [city, setCity]               = useState("");
  const [prompt, setPrompt]        = useState("");
  const [options, setOptions]    = useState(["", ""]);
  const [start, setStart] = useState(
    _toIsoLocal(new Date(Date.now() + 10 * 60 * 1000)));   // now + 10m
  const [lock, setLock]   = useState(
    _toIsoLocal(new Date(Date.now() + 60 * 60 * 1000)));   // now + 60m
  const [prizeTitle, setPrizeTitle] = useState("");
  const [prizeKind, setPrizeKind] = useState("bigcoin");
  const [prizeValue, setPrizeValue] = useState("100");
  const [checkinRequired, setCheckinRequired] = useState(true);
  const [busy, setBusy] = useState(false);
  const [err, setErr]    = useState(null);

  const addOption = () => options.length < 5 && setOptions([...options, ""]);
  const setOption = (i, v) => {
    const o = [...options]; o[i] = v; setOptions(o);
  };
  const removeOption = (i) => {
    if (options.length <= 2) return;
    setOptions(options.filter((_, idx) => idx !== i));
  };

  const canSubmit = useMemo(() => {
    if (!title || title.length < 4)  return false;
    if (!prompt || prompt.length < 4) return false;
    if (options.filter(o => o.trim()).length < 2) return false;
    if (!prizeTitle) return false;
    if (!start || !lock) return false;
    return true;
  }, [title, prompt, options, prizeTitle, start, lock]);

  const submit = async (alsoSubmitForApproval) => {
    setBusy(true); setErr(null);
    try {
      const cleanOptions = options
        .map((o, i) => ({ label: o.trim(), kind: "multiple_choice",
                                  option_id: `opt_${i+1}` }))
        .filter(o => o.label);
      const body = {
        title, description: description || null, event_type: eventType,
        event_label: eventLabel || null, city: city || null,
        question: { prompt, answer_options: cleanOptions },
        start_time: _isoFromLocal(start), lock_time: _isoFromLocal(lock),
        winner_rules: { scoring: "winner_takes_all", max_winners: 1,
                                  tiebreaker: "first_to_pick" },
        checkin_required: checkinRequired,
      };
      const cr = await axios.post(
        `${API}/business/predict-win/stations/${encodeURIComponent(slug)}/campaigns`,
        body);
      const cid = cr.data.campaign.campaign_id;
      const pv = parseFloat(prizeValue);
      await axios.post(
        `${API}/business/predict-win/campaigns/${cid}/prizes`,
        { rank: 1, title: prizeTitle, prize_kind: prizeKind,
          value_amount: Number.isFinite(pv) ? pv : 0,
          value_currency: prizeKind === "bigcoin" ? "BC" : "USD",
          inventory_total: 1 });
      if (alsoSubmitForApproval) {
        await axios.post(
          `${API}/business/predict-win/campaigns/${cid}/submit-approval`);
      }
      onCreated();
    } catch (e) {
      const d = e.response?.data?.detail;
      setErr(d?.message || d?.code || e.message || "Could not create campaign.");
    } finally { setBusy(false); }
  };

  return (
    <Modal onClose={onClose} testId="wizard-modal" maxWidth={780} title="Create campaign">
      <div style={{ display: "grid", gap: 18 }}>
        <Field label="Title">
          <input data-testid="wizard-title" value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      placeholder="Friday Karaoke Pick" style={inp}/>
        </Field>
        <Field label="Description (optional)">
          <textarea data-testid="wizard-desc" value={description}
                            onChange={(e) => setDesc(e.target.value)}
                            rows={2} style={inp}/>
        </Field>
        <div style={twoCol}>
          <Field label="Event type">
            <select data-testid="wizard-event-type" value={eventType}
                          onChange={(e) => setEventType(e.target.value)} style={inp}>
              {BUSINESS_EVENT_TYPES.map(et => (
                <option key={et.value} value={et.value}>{et.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Event label (optional)">
            <input data-testid="wizard-event-label" value={eventLabel}
                          onChange={(e) => setEventLbl(e.target.value)}
                          placeholder="Karaoke Night" style={inp}/>
          </Field>
        </div>
        <div style={twoCol}>
          <Field label="City (optional)">
            <input data-testid="wizard-city" value={city}
                          onChange={(e) => setCity(e.target.value)}
                          placeholder="Dubai" style={inp}/>
          </Field>
          <Field label="Check-in required">
            <label style={{ display: "flex", alignItems: "center", gap: 8,
                                      padding: "10px 12px",
                                      background: "rgba(0,217,255,0.06)",
                                      border: "1px solid rgba(0,217,255,0.18)",
                                      borderRadius: 10 }}>
              <input data-testid="wizard-checkin-toggle" type="checkbox"
                          checked={checkinRequired}
                          onChange={(e) => setCheckinRequired(e.target.checked)}/>
              <span style={{ fontSize: 13 }}>
                Customers must scan venue QR before picking
              </span>
            </label>
          </Field>
        </div>
        <Field label="Question prompt">
          <input data-testid="wizard-prompt" value={prompt}
                      onChange={(e) => setPrompt(e.target.value)}
                      placeholder="Who'll win the karaoke contest tonight?"
                      style={inp}/>
        </Field>
        <Field label="Answer options (2–5)">
          <div style={{ display: "grid", gap: 6 }}>
            {options.map((o, i) => (
              <div key={i} style={{ display: "flex", gap: 6 }}>
                <input value={o}
                              data-testid={`wizard-option-${i}`}
                              placeholder={`Option ${i+1}`}
                              onChange={(e) => setOption(i, e.target.value)}
                              style={{ ...inp, flex: 1 }}/>
                {options.length > 2 && (
                  <button onClick={() => removeOption(i)}
                                  data-testid={`wizard-option-remove-${i}`}
                                  style={iconBtn}>
                    <X size={14}/>
                  </button>)}
              </div>
            ))}
            {options.length < 5 && (
              <button onClick={addOption} style={ghostBtn}
                              data-testid="wizard-add-option">
                <Plus size={13}/> Add another option
              </button>)}
          </div>
        </Field>
        <div style={twoCol}>
          <Field label="Start time">
            <input data-testid="wizard-start" type="datetime-local"
                          value={start} onChange={(e) => setStart(e.target.value)}
                          style={inp}/>
          </Field>
          <Field label="Lock time">
            <input data-testid="wizard-lock" type="datetime-local"
                          value={lock} onChange={(e) => setLock(e.target.value)}
                          style={inp}/>
          </Field>
        </div>
        <div style={{ ...sectionDivider }} />
        <div style={twoCol}>
          <Field label="Prize title">
            <input data-testid="wizard-prize-title" value={prizeTitle}
                          onChange={(e) => setPrizeTitle(e.target.value)}
                          placeholder="100 BigPoints reward" style={inp}/>
          </Field>
          <Field label="Prize kind">
            <select data-testid="wizard-prize-kind" value={prizeKind}
                          onChange={(e) => setPrizeKind(e.target.value)} style={inp}>
              <option value="bigcoin">BigPoints (auto-credit)</option>
              <option value="points">Points</option>
              <option value="experience">Experience</option>
              <option value="merchandise">Merchandise</option>
            </select>
          </Field>
        </div>
        <Field label="Prize value">
          <input data-testid="wizard-prize-value" value={prizeValue}
                      onChange={(e) => setPrizeValue(e.target.value)}
                      placeholder="100" style={inp}/>
        </Field>
        {err && (
          <div style={errorPanel} data-testid="wizard-error">
            <AlertCircle size={14}/> {err}
          </div>)}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} style={ghostBtn}
                          data-testid="wizard-cancel">Cancel</button>
          <button onClick={() => submit(false)}
                          disabled={!canSubmit || busy}
                          style={canSubmit && !busy ? secondaryBtn : disabledBtn}
                          data-testid="wizard-save-draft">
            Save as draft
          </button>
          <button onClick={() => submit(true)}
                          disabled={!canSubmit || busy}
                          style={canSubmit && !busy ? primaryBtn : disabledBtn}
                          data-testid="wizard-submit-approval">
            <Sparkles size={14}/>
            {busy ? "Submitting…" : "Submit for approval"}
          </button>
        </div>
      </div>
    </Modal>);
}

// ─── Pair TV ─────────────────────────────────────────────────────────
function PairTVModal({ campaign, onClose, onPaired }) {
  const [pair, setPair] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr]    = useState(null);
  const run = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      const r = await axios.post(
        `${API}/business/predict-win/campaigns/${campaign.campaign_id}/pair-tv`,
        { label: "Main floor TV" });
      setPair(r.data);
      onPaired && onPaired();
    } catch (e) {
      setErr(e.response?.data?.detail?.message || e.message);
    } finally { setBusy(false); }
  }, [campaign.campaign_id, onPaired]);
  useEffect(() => { run(); }, [run]);

  const kioskUrl = pair
    ? `${window.location.origin}${pair.kiosk_url_path}` : "";

  return (
    <Modal onClose={onClose} testId="pair-tv-modal"
                  maxWidth={520} title="Pair an in-store TV">
      {busy && <div style={muted}>Issuing pairing code…</div>}
      {err && <div style={errorPanel}><AlertCircle size={14}/> {err}</div>}
      {pair && (
        <div style={{ textAlign: "center" }}>
          <div style={{ ...muted, marginBottom: 8 }}>
            On your TV, navigate to:
          </div>
          <div data-testid="pair-tv-url"
                  style={{ fontFamily: "monospace",
                              fontSize: 14, color: "#cbd5e1",
                              wordBreak: "break-all",
                              padding: "8px 12px",
                              background: "rgba(255,255,255,0.04)",
                              borderRadius: 8,
                              marginBottom: 18 }}>
            {kioskUrl}
          </div>
          <div data-testid="pair-tv-code"
                  style={{ fontFamily: "monospace", fontSize: 42,
                              letterSpacing: "0.12em",
                              fontWeight: 800, color: "#00d9ff",
                              padding: "12px 18px",
                              background: "rgba(0,217,255,0.08)",
                              border: "1px solid rgba(0,217,255,0.3)",
                              borderRadius: 14, display: "inline-block",
                              marginBottom: 18 }}>
            {pair.pairing_code}
          </div>
          <div style={{ background: "#fff", padding: 14,
                                  borderRadius: 14, display: "inline-block",
                                  margin: "0 auto", lineHeight: 0 }}>
            <QRCode value={kioskUrl} size={200}
                          bgColor="#fff" fgColor="#0b0b0b"
                          data-testid="pair-tv-qr"/>
          </div>
          <div style={{ ...muted, marginTop: 14, fontSize: 12 }}>
            Pairing expires {new Date(pair.pairing_expires_at).toLocaleTimeString()}.
            Re-pair anytime to refresh the code.
          </div>
        </div>)}
    </Modal>);
}

// ─── Resolve ─────────────────────────────────────────────────────────
function ResolveModal({ campaign, onClose, onResolved }) {
  const [opts, setOpts]       = useState([]);
  const [pick, setPick]       = useState(null);
  const [notes, setNotes]   = useState("");
  const [busy, setBusy]      = useState(false);
  const [err, setErr]         = useState(null);
  const [result, setResult] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(
          `${API}/business/predict-win/campaigns/${campaign.campaign_id}`);
        const o = r.data.campaign?.question?.answer_options || [];
        setOpts(o);
        if (o.length) setPick(o[0].option_id);
      } catch (_) { /* ignore */ }
    })();
  }, [campaign.campaign_id]);

  const submit = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await axios.post(
        `${API}/business/predict-win/campaigns/${campaign.campaign_id}/resolve`,
        { winning_option_id: pick, audit_notes: notes || null });
      setResult(r.data);
      onResolved && onResolved();
    } catch (e) {
      setErr(e.response?.data?.detail?.message
                  || e.response?.data?.detail?.code || e.message);
    } finally { setBusy(false); }
  };

  return (
    <Modal onClose={onClose} testId="resolve-modal"
                  maxWidth={560} title="Resolve the winning pick">
      {!result && (
        <div style={{ display: "grid", gap: 14 }}>
          <div style={muted}>
            Resolving will lock entry statuses (winner / loser) and trigger the
            award pipeline (BigPoints credit, badges, wallet items).  This is
            irreversible.
          </div>
          <Field label="Winning option">
            <div style={{ display: "grid", gap: 6 }}>
              {opts.map((o) => (
                <label key={o.option_id}
                              data-testid={`resolve-option-${o.option_id}`}
                              style={{ display: "flex", alignItems: "center",
                                          gap: 10, padding: 10, borderRadius: 10,
                                          border: `1px solid ${pick === o.option_id
                                            ? "#00d9ff" : "rgba(255,255,255,0.08)"}`,
                                          background: pick === o.option_id
                                            ? "rgba(0,217,255,0.06)" : "transparent",
                                          cursor: "pointer" }}>
                  <input type="radio" checked={pick === o.option_id}
                                onChange={() => setPick(o.option_id)} />
                  <span>{o.label}</span>
                </label>
              ))}
            </div>
          </Field>
          <Field label="Notes (optional, internal)">
            <textarea data-testid="resolve-notes" value={notes}
                              onChange={(e) => setNotes(e.target.value)}
                              rows={2} style={inp}/>
          </Field>
          {err && <div style={errorPanel}><AlertCircle size={14}/> {err}</div>}
          <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
            <button onClick={onClose} style={ghostBtn}>Cancel</button>
            <button onClick={submit} disabled={busy || !pick}
                            style={pick && !busy ? dangerBtn : disabledBtn}
                            data-testid="resolve-submit">
              <Trophy size={14}/>
              {busy ? "Resolving…" : "Resolve and award prizes"}
            </button>
          </div>
        </div>)}
      {result && (
        <div data-testid="resolve-success"
                style={{ textAlign: "center", padding: 12 }}>
          <PartyPopper size={48} color="#fbbf24"
                                  style={{ marginBottom: 14 }}/>
          <h3 style={{ marginBottom: 6 }}>Resolved!</h3>
          <div style={{ ...muted, marginBottom: 16 }}>
            Winning pick: <strong>{
              opts.find(o => o.option_id === result.resolution?.winning_option_id)?.label
                || result.resolution?.winning_option_id
            }</strong>
          </div>
          {result.award_pipeline && (
            <div style={{ ...metaRow, justifyContent: "center", gap: 10 }}>
              <span><Wallet size={12}/> winners credited: {
                result.award_pipeline.winners_credited ?? 0
              }</span>
              <span><strong>·</strong></span>
              <span>awards inserted: {result.award_pipeline.awards_created ?? 0}</span>
            </div>)}
          <button onClick={onClose}
                          style={{ ...primaryBtn, marginTop: 16 }}
                          data-testid="resolve-success-close">Done</button>
        </div>)}
    </Modal>);
}

// ─── Analytics ───────────────────────────────────────────────────────
function AnalyticsModal({ campaign, onClose }) {
  const [data, setData] = useState(null);
  const [err, setErr]    = useState(null);
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(
          `${API}/business/predict-win/campaigns/${campaign.campaign_id}/analytics`);
        setData(r.data);
      } catch (e) {
        setErr(e.response?.data?.detail?.message || e.message);
      }
    })();
  }, [campaign.campaign_id]);
  return (
    <Modal onClose={onClose} testId="analytics-modal"
                  maxWidth={720} title={`Analytics: ${campaign.title}`}>
      {err && <div style={errorPanel}>{err}</div>}
      {!data && !err && <div style={muted}>Loading analytics…</div>}
      {data && (
        <div style={{ display: "grid", gap: 18 }}>
          <div style={{ display: "grid",
                                  gridTemplateColumns: "repeat(4, 1fr)",
                                  gap: 10 }}>
            <KpiTile label="Total entries"
                        value={data.total_entries}
                        testId="kpi-total-entries"/>
            <KpiTile label="Unique users"
                        value={data.unique_users}
                        testId="kpi-unique-users"/>
            <KpiTile label="Awards"
                        value={data.award_count}
                        testId="kpi-awards"/>
            <KpiTile label="Delivered"
                        value={data.delivered_count}
                        testId="kpi-delivered"/>
          </div>
          <div data-testid="analytics-distribution">
            <h4 style={{ marginBottom: 8 }}>Community pick distribution</h4>
            <div style={{ width: "100%", height: 200 }}>
              <ResponsiveContainer>
                <BarChart data={data.distribution || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                  <XAxis dataKey="label" stroke="#9aa3af" />
                  <YAxis stroke="#9aa3af" allowDecimals={false}/>
                  <Tooltip contentStyle={{ background: "#0a0a0a",
                                                              border: "1px solid #1f2937" }} />
                  <Bar dataKey="count" fill="#00d9ff" radius={[6,6,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
          {data.timeseries_minute?.length > 0 && (
            <div data-testid="analytics-timeseries">
              <h4 style={{ marginBottom: 8 }}>Entries per minute (last 60m)</h4>
              <div style={{ width: "100%", height: 180 }}>
                <ResponsiveContainer>
                  <LineChart data={data.timeseries_minute}>
                    <CartesianGrid strokeDasharray="3 3"
                                          stroke="rgba(255,255,255,0.06)" />
                    <XAxis dataKey="minute" stroke="#9aa3af" tick={{ fontSize: 10 }}/>
                    <YAxis stroke="#9aa3af" allowDecimals={false} />
                    <Tooltip contentStyle={{ background: "#0a0a0a",
                                                                border: "1px solid #1f2937" }} />
                    <Line type="monotone" dataKey="count" stroke="#a78bfa"
                                strokeWidth={2} dot={{ fill: "#a78bfa", r: 3 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>)}
        </div>)}
    </Modal>);
}

// ─── Atoms ───────────────────────────────────────────────────────────
function Modal({ children, onClose, title, maxWidth = 560, testId }) {
  return (
    <div data-testid={`${testId}-backdrop`}
            style={{ position: "fixed", inset: 0, zIndex: 90,
                        background: "rgba(0,0,0,0.6)",
                        backdropFilter: "blur(6px)",
                        display: "flex", alignItems: "center",
                        justifyContent: "center", padding: 20 }}
            onClick={onClose}>
      <div data-testid={testId}
              onClick={(e) => e.stopPropagation()}
              style={{ background: "#0b1018",
                          border: "1px solid rgba(255,255,255,0.08)",
                          borderRadius: 18, padding: 22,
                          width: "100%", maxWidth, maxHeight: "92vh",
                          overflow: "auto", color: "#f1f5f9" }}>
        <div style={{ display: "flex", justifyContent: "space-between",
                                gap: 12, marginBottom: 14 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, margin: 0 }}>{title}</h2>
          <button onClick={onClose} style={iconBtn}
                          data-testid={`${testId}-close`}>
            <X size={16}/>
          </button>
        </div>
        {children}
      </div>
    </div>);
}

function Field({ label, children }) {
  return (
    <label style={{ display: "grid", gap: 6 }}>
      <span style={{ fontSize: 12, fontWeight: 600, letterSpacing: "0.04em",
                              color: "#94a3b8", textTransform: "uppercase" }}>
        {label}
      </span>
      {children}
    </label>);
}

function KpiTile({ label, value, testId }) {
  return (
    <div data-testid={testId}
            style={{ background: "rgba(255,255,255,0.04)",
                        border: "1px solid rgba(255,255,255,0.06)",
                        borderRadius: 12, padding: 12, textAlign: "left" }}>
      <div style={{ fontSize: 28, fontWeight: 800, color: "#00d9ff" }}>
        {value ?? 0}
      </div>
      <div style={{ fontSize: 11, color: "#94a3b8",
                              textTransform: "uppercase", letterSpacing: "0.06em",
                              marginTop: 2 }}>{label}</div>
    </div>);
}

// ─── Styles ──────────────────────────────────────────────────────────
const page = { padding: "32px 24px", maxWidth: 1200, margin: "0 auto",
                          color: "#f1f5f9", fontFamily: "Inter, system-ui" };
const headerRow = { display: "flex", justifyContent: "space-between",
                                  gap: 14, alignItems: "flex-end", marginBottom: 22 };
const pageTitle = { fontSize: 28, fontWeight: 800, margin: "4px 0" };
const breadcrumb = { display: "flex", alignItems: "center", gap: 6,
                                      color: "#9aa3af", fontSize: 12 };
const crumbLink = { color: "#cbd5e1", textDecoration: "none" };
const subText = { color: "#9aa3af", maxWidth: 700, lineHeight: 1.45 };
const complianceBanner = {
  display: "flex", gap: 10, alignItems: "flex-start",
  background: "rgba(0,217,255,0.05)",
  border: "1px solid rgba(0,217,255,0.2)",
  color: "#cbd5e1", padding: "12px 14px", borderRadius: 12,
  marginBottom: 22, fontSize: 13,
};
const listGrid = { display: "grid", gap: 12 };
const emptyState = { textAlign: "center", padding: "60px 20px",
                                    border: "1px dashed rgba(255,255,255,0.08)",
                                    borderRadius: 16,
                                    color: "#94a3b8" };
const card = { background: "rgba(255,255,255,0.03)",
                        border: "1px solid rgba(255,255,255,0.06)",
                        padding: 18, borderRadius: 14 };
const cardTitle = { margin: 0, fontSize: 17, fontWeight: 700 };
const metaRow = { display: "flex", gap: 8, flexWrap: "wrap",
                              alignItems: "center", color: "#9aa3af", fontSize: 12 };
const dot = { color: "rgba(255,255,255,0.3)" };
const pill = (color, bg) => ({
  display: "inline-block", padding: "3px 10px", borderRadius: 999,
  fontSize: 11, fontWeight: 700, color, background: bg,
  textTransform: "uppercase", letterSpacing: "0.06em",
});
const pillOutline = (color) => ({
  display: "inline-block", padding: "3px 10px", borderRadius: 999,
  fontSize: 11, fontWeight: 700, color, background: "transparent",
  border: `1px solid ${color}40`,
  textTransform: "uppercase", letterSpacing: "0.06em",
});
const primaryBtn = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "9px 14px", borderRadius: 999,
  background: "#00d9ff", color: "#062533",
  fontWeight: 700, border: "none", cursor: "pointer",
  fontSize: 13,
};
const secondaryBtn = {
  ...primaryBtn, background: "rgba(255,255,255,0.06)", color: "#cbd5e1",
  border: "1px solid rgba(255,255,255,0.08)",
};
const ghostBtn = {
  ...primaryBtn, background: "transparent", color: "#cbd5e1",
  border: "1px solid rgba(255,255,255,0.1)",
};
const dangerBtn = {
  ...primaryBtn, background: "#fbbf24", color: "#1f2937",
};
const disabledBtn = {
  ...primaryBtn, background: "rgba(255,255,255,0.05)",
  color: "rgba(255,255,255,0.3)", cursor: "not-allowed",
};
const iconBtn = { background: "rgba(255,255,255,0.06)", color: "#cbd5e1",
                              border: "none", borderRadius: 8, padding: 8,
                              cursor: "pointer" };
const inp = { background: "rgba(255,255,255,0.03)", color: "#f1f5f9",
                      border: "1px solid rgba(255,255,255,0.08)",
                      padding: "10px 12px", borderRadius: 10, fontSize: 13,
                      width: "100%", fontFamily: "inherit" };
const twoCol = { display: "grid", gap: 12, gridTemplateColumns: "1fr 1fr" };
const sectionDivider = { borderTop: "1px dashed rgba(255,255,255,0.08)",
                                          margin: "4px 0" };
const muted = { color: "#94a3b8", fontSize: 13 };
const errorPanel = { background: "rgba(248,113,113,0.08)",
                                    border: "1px solid rgba(248,113,113,0.3)",
                                    color: "#fca5a5",
                                    padding: "10px 14px", borderRadius: 12,
                                    display: "flex", alignItems: "center", gap: 8,
                                    fontSize: 13 };
