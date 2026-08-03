/**
 * Phase 17a — Offer management pages on `/venue`.
 *
 * Routes added:
 *   /venue/offers              → list
 *   /venue/offers/new          → create form
 *   /venue/offers/import       → bulk CSV import (dry-run preview)
 *   /venue/offers/:offerId     → detail (Detail / Coupons / Analytics tabs)
 *   /venue/redeem/scan         → QR scanner PWA
 *
 * Adds an auto-pause "exhausted" banner to all venue pages via
 * `useExhaustedOffersBanner()` (polls `/api/venue/{id}/offers?status=exhausted`).
 */
import React, { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { useNavigate, useParams, NavLink } from "react-router-dom";
import { toast } from "sonner";
import {
  Plus, Upload, FileDown, Pause, Play, Archive, Camera, Sparkles,
  CheckCircle2, XCircle, Megaphone, ChevronRight, Ticket, AlertTriangle,
  ScanLine, Volume2, VolumeX, Search,
} from "lucide-react";
import { Card, Button } from "@/shell/primitives";

const API = process.env.REACT_APP_BACKEND_URL + "/api";
axios.defaults.withCredentials = true;

// ─── Shared exhausted-offer banner ──────────────────────────────────
export function VenueOffersPage({ Component, title }) {
  // Fetches the user's venue, renders the venue Shell + injects venue.
  const navigate = useNavigate();
  const [venue, setVenue] = useState(null);
  useEffect(() => {
    axios.get(`${API}/venue/me`).then(({ data }) => {
      const v = (data.venues || [])[0];
      if (!v) { navigate("/venue/onboard", { replace: true }); return; }
      setVenue(v);
    }).catch(() => navigate("/login", { replace: true }));
  }, [navigate]);
  if (!venue) {
    return (
      <div className="min-h-screen px-6 pt-10 text-center text-text-secondary">
        Loading…
      </div>
    );
  }
  // Reuse the existing Shell from `Venue.jsx` for the nav + framing.
  // (Doing this via dynamic import would over-complicate; we mirror
  // a slim shell here so the offers pages match the venue chrome.)
  return (
    <div className="min-h-screen px-6 sm:px-10 lg:px-14 pb-24 pt-6">
      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr] gap-10 max-w-7xl mx-auto">
        <VenueNav venue={venue} />
        <main className="space-y-6 min-w-0">
          <h1 className="font-display font-bold text-4xl tracking-display-tight">
            {title}
          </h1>
          <Component venue={venue} />
        </main>
      </div>
    </div>
  );
}

function VenueNav({ venue }) {
  const items = [
    ["/venue",                "Overview"],
    ["/venue/tvs",            "TVs"],
    ["/venue/trivia",         "Start trivia"],
    ["/venue/announcements","Announcements"],
    ["/venue/offers",         "Offers"],
    ["/venue/redeem/scan",   "Scan redeem"],
    ["/venue/players",        "Live players"],
    ["/venue/settings",       "Settings"],
  ];
  return (
    <aside className="space-y-1" data-testid="venue-nav">
      <div className="px-3 pb-4">
        <div className="text-[10px] tracking-[0.3em] uppercase text-text-secondary font-mono">
          Venue HQ
        </div>
        <div className="font-display font-bold text-2xl tracking-display-tight mt-1">
          {venue.name}
        </div>
        <div className="text-xs text-text-secondary mt-1 capitalize">
          {venue.plan_tier} · {venue.market}
        </div>
      </div>
      {items.map(([to, label]) => (
        <NavLink key={to} to={to} end={to === "/venue"}
                       className={({ isActive }) =>
                         `flex items-center gap-3 px-3 py-2 rounded-xl text-sm
                          ${isActive ? "bg-accent-magenta/15 text-accent-magenta"
                                          : "text-text-secondary hover:text-text-primary hover:bg-white/[0.04]"}`}>
          {label}
        </NavLink>
      ))}
    </aside>
  );
}

// ─── Shared exhausted-offer banner ──────────────────────────────────
export function ExhaustedOffersBanner({ venueId }) {
  const [list, setList] = useState([]);
  const tick = async () => {
    if (!venueId) return;
    try {
      const { data } = await axios.get(`${API}/venue/${venueId}/offers?status=exhausted&limit=10`);
      setList(data.offers || []);
    } catch (_) { /* */ }
  };
  useEffect(() => {
    tick();
    const t = setInterval(tick, 8000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [venueId]);
  if (!list.length) return null;
  return (
    <div className="rounded-2xl border-2 border-accent-magenta bg-accent-magenta/[0.08]
                              px-4 py-3 space-y-2"
          data-testid="venue-exhausted-banner">
      {list.map((o) => (
        <div key={o.id} className="flex items-center gap-3"
              data-testid={`venue-exhausted-row-${o.id}`}>
          <AlertTriangle size={16} className="text-accent-magenta flex-shrink-0" />
          <div className="flex-1 text-sm">
            <span className="font-display font-bold">{o.title}</span>
            {" "}hit its <span className="text-accent-magenta">
              {o.auto_paused_reason === "daily_cap"  ? "daily cap (auto-resumes at midnight)" :
                o.auto_paused_reason === "budget_cap" ? "budget cap" :
                "total cap"}
            </span>.
          </div>
          <button
            onClick={async () => {
              try { await axios.post(`${API}/venue/${venueId}/offers/${o.id}/resume`);
                      toast.success("Resumed."); tick(); }
              catch { toast.error("Couldn't resume."); }
            }}
            className="px-3 py-1 rounded-lg bg-accent-electric/15 text-accent-electric text-xs"
            data-testid={`venue-exhausted-resume-${o.id}`}>
            Resume
          </button>
        </div>
      ))}
    </div>
  );
}

// ─── /venue/offers ───────────────────────────────────────────────────
export function VenueOffers({ venue }) {
  const [tab, setTab] = useState("active");
  const [offers, setOffers] = useState([]);
  const refresh = async () => {
    if (!venue) return;
    const { data } = await axios.get(`${API}/venue/${venue.id}/offers?status=${tab}`);
    setOffers(data.offers || []);
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [venue, tab]);
  const navigate = useNavigate();
  if (!venue) return null;
  return (
    <div className="space-y-5">
      <ExhaustedOffersBanner venueId={venue.id} />
      <div className="flex items-center justify-between">
        <div className="flex gap-1 p-1 bg-bg-glass rounded-full text-sm" data-testid="offers-tabs">
          {["active", "paused", "exhausted", "archived"].map((t) => (
            <button key={t}
                          onClick={() => setTab(t)}
                          className={`px-3 py-1.5 rounded-full capitalize ${tab === t
                            ? "bg-accent-magenta/20 text-accent-magenta"
                            : "text-text-secondary hover:text-text-primary"}`}
                          data-testid={`offers-tab-${t}`}>
              {t}
            </button>
          ))}
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm"
                      onClick={() => navigate("/venue/offers/import")}
                      data-testid="offers-import-btn">
            <Upload size={12} /> Import CSV
          </Button>
          <Button variant="primary" size="sm"
                      onClick={() => navigate("/venue/offers/new")}
                      data-testid="offers-new-btn">
            <Plus size={12} /> New offer
          </Button>
        </div>
      </div>
      <Card className="p-4 space-y-2">
        {offers.length === 0 && (
          <div className="text-text-secondary text-sm py-6 text-center"
                data-testid="offers-empty">
            No offers in this tab yet.
          </div>
        )}
        {offers.map((o) => (
          <button key={o.id}
                        onClick={() => navigate(`/venue/offers/${o.id}`)}
                        className="w-full flex items-center gap-4 px-3 py-3 rounded-xl
                                          bg-white/[0.03] hover:bg-white/[0.06] text-left"
                        data-testid={`offers-row-${o.id}`}>
            <Ticket size={14} className="text-accent-magenta flex-shrink-0" />
            <div className="flex-1 min-w-0">
              <div className="font-display font-bold text-sm truncate">{o.title}</div>
              <div className="text-xs text-text-secondary">
                <span className="uppercase">{o.offer_type}</span>
                {o.discount_value ? <> · {o.discount_value}</> : null}
                {o.max_redemptions ? <> · cap {o.issued_count || 0}/{o.max_redemptions}</> : null}
              </div>
            </div>
            <ChevronRight size={14} className="text-text-secondary" />
          </button>
        ))}
      </Card>
    </div>
  );
}

// ─── /venue/offers/new ──────────────────────────────────────────────
export function VenueOfferNew({ venue }) {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    title: "", description: "", offer_type: "percent",
    discount_value: 10, max_redemptions: 100, daily_cap: "",
    budget_cap_usd: "", redemption_method: "qr_scan", terms: "",
  });
  const submit = async (e) => {
    e.preventDefault();
    if (!venue) return;
    const body = { ...form };
    ["max_redemptions","daily_cap","budget_cap_usd","discount_value"].forEach((k) => {
      if (body[k] === "" || body[k] == null) delete body[k];
      else body[k] = Number(body[k]);
    });
    try {
      const { data } = await axios.post(`${API}/venue/${venue.id}/offers`, body);
      toast.success("Offer created.");
      navigate(`/venue/offers/${data.offer.id}`);
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((d && typeof d === "object" && d.message) || d || "Couldn't create.");
    }
  };
  if (!venue) return null;
  return (
    <form onSubmit={submit} className="space-y-5" data-testid="venue-offer-new">
      <Card className="p-6 space-y-4">
        <FieldInput label="Title" v={form.title} onChange={(v)=>setForm({...form,title:v})}
                          required testId="offer-title" />
        <FieldInput label="Description" v={form.description} onChange={(v)=>setForm({...form,description:v})}
                          testId="offer-description" />
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono mb-1">Type</label>
            <select value={form.offer_type} onChange={(e)=>setForm({...form,offer_type:e.target.value})}
                        className="w-full px-3 py-2 rounded-xl bg-bg-glass border border-white/[0.10]"
                        data-testid="offer-type">
              {["percent","flat","free_item","bogo"].map((t)=><option key={t}>{t}</option>)}
            </select>
          </div>
          <FieldInput label="Discount value" type="number" v={form.discount_value}
                            onChange={(v)=>setForm({...form,discount_value:v})}
                            testId="offer-discount" />
          <FieldInput label="Total cap" type="number" v={form.max_redemptions}
                            onChange={(v)=>setForm({...form,max_redemptions:v})}
                            testId="offer-total-cap" />
          <FieldInput label="Daily cap" type="number" v={form.daily_cap}
                            onChange={(v)=>setForm({...form,daily_cap:v})}
                            testId="offer-daily-cap" />
          <FieldInput label="Budget cap (USD)" type="number" v={form.budget_cap_usd}
                            onChange={(v)=>setForm({...form,budget_cap_usd:v})}
                            testId="offer-budget-cap" />
        </div>
        <FieldInput label="Terms" v={form.terms} onChange={(v)=>setForm({...form,terms:v})}
                          testId="offer-terms" />
      </Card>
      <Button variant="primary" type="submit" data-testid="venue-offer-create-btn">
        <Sparkles size={14} /> Create offer
      </Button>
    </form>
  );
}

function FieldInput({ label, v, onChange, type="text", required, testId }) {
  return (
    <div>
      <label className="block text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono mb-1">
        {label}
      </label>
      <input type={type} value={v} required={!!required}
                onChange={(e) => onChange(e.target.value)}
                data-testid={testId}
                className="w-full px-3 py-2 rounded-xl bg-bg-glass border border-white/[0.10] outline-none" />
    </div>
  );
}

// ─── /venue/offers/import ──────────────────────────────────────────
export function VenueOfferImport({ venue }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [committing, setCommitting] = useState(false);
  const navigate = useNavigate();

  const run = async (dry = true) => {
    if (!file || !venue) return;
    setCommitting(!dry);
    const fd = new FormData();
    fd.append("file", file);
    try {
      const { data } = await axios.post(
        `${API}/venue/${venue.id}/offers/bulk_import?dry_run=${dry}`, fd,
        { headers: { "Content-Type": "multipart/form-data" } },
      );
      setPreview(data);
      if (!dry) {
        toast.success(`Imported ${data.created} offer(s).`);
        navigate("/venue/offers");
      }
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error((d && typeof d === "object" && d.message) || d || "Import failed.");
    }
    setCommitting(false);
  };
  if (!venue) return null;
  return (
    <div className="space-y-5">
      <Card className="p-6 space-y-4">
        <div className="text-text-secondary text-sm">
          Upload a CSV with these columns: title, description, offer_type,
          discount_value, start_time, end_time, max_redemptions,
          redemption_method, terms.  Max <span className="font-mono">500</span> rows.
        </div>
        <div className="flex gap-2">
          <input type="file" accept=".csv"
                    onChange={(e) => { setFile(e.target.files[0] || null); setPreview(null); }}
                    data-testid="offer-import-file"
                    className="flex-1 px-3 py-2 rounded-xl bg-bg-glass border border-white/[0.10]
                                      file:bg-accent-magenta/15 file:text-accent-magenta file:border-0
                                      file:rounded-lg file:px-3 file:py-1 text-sm" />
          <a href={`${API}/venue/offers/csv_template`} download
              className="px-3 py-2 rounded-xl bg-bg-glass border border-white/[0.10]
                                text-xs flex items-center gap-1 hover:border-white/[0.20]"
              data-testid="offer-import-template-btn">
            <FileDown size={12} /> Template
          </a>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={() => run(true)}
                      disabled={!file} data-testid="offer-import-dry-btn">
            <Search size={12} /> Validate
          </Button>
          <Button variant="primary" size="sm" onClick={() => run(false)}
                      disabled={!file || !preview || preview.failed > 0 || committing}
                      data-testid="offer-import-commit-btn">
            <Upload size={12} /> Commit import
          </Button>
        </div>
      </Card>
      {preview && (
        <Card className="p-4">
          <div className="font-display font-bold text-lg mb-2">
            Preview · {preview.would_create || preview.created || 0} ok ·
            <span className="text-accent-magenta"> {preview.failed} failed</span>
          </div>
          <div className="space-y-1 max-h-[400px] overflow-y-auto"
                data-testid="offer-import-preview">
            {(preview.results || []).map((r, i) => (
              <div key={i}
                    className={`px-3 py-2 rounded-lg text-xs font-mono flex items-center gap-2
                                      ${r.status === "failed"
                                        ? "bg-accent-magenta/[0.08] text-accent-magenta"
                                        : "bg-green-500/[0.06] text-green-400"}`}
                    data-testid={`offer-import-row-${r.row}`}>
                {r.status === "failed" ? <XCircle size={12} /> : <CheckCircle2 size={12} />}
                Row {r.row} · {r.status}
                {r.error ? <span className="text-text-secondary"> — {r.error}</span> : null}
                {r.offer_id ? <span className="text-text-secondary"> → {r.offer_id}</span> : null}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
// ─── Analytics tab — Phase 17b funnel + bar chart + drop-off ────────
export function OfferAnalyticsPanel({ venue, offerId }) {
  const [data, setData]        = useState(null);
  const [period, setPeriod]   = useState("month");
  const [confirm, setConfirm] = useState(false);
  const [boosting, setBoosting] = useState(false);
  const [boostInfo, setBoostInfo] = useState(null);
  const [offer, setOffer]        = useState(null);
  const refresh = () => {
    axios.get(`${API}/venue/${venue.id}/offers/${offerId}/funnel?period=${period}`)
      .then(({ data }) => setData(data))
      .catch(() => setData({ impressions: 0, saves: 0, scans: 0, redeems: 0,
                                          save_rate: 0, scan_rate: 0, redeem_rate: 0,
                                          time_buckets: [], top_drop: null,
                                          boost_eligible: false }));
    axios.get(`${API}/venue/${venue.id}/offers/${offerId}`)
      .then(({ data }) => setOffer(data?.offer || null))
      .catch(() => {});
  };
  useEffect(() => {
    if (!venue || !offerId) return;
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [venue, offerId, period]);
  if (!data) return <div className="text-text-secondary text-sm">Loading…</div>;

  const stages = [
    { k: "impressions", label: "Impressions", v: data.impressions, next_rate: data.save_rate,    next_label: "save"   },
    { k: "saves",        label: "Saves",        v: data.saves,        next_rate: data.scan_rate,    next_label: "scan"   },
    { k: "scans",        label: "Scans",        v: data.scans,        next_rate: data.redeem_rate, next_label: "redeem" },
    { k: "redeems",     label: "Redeems",     v: data.redeems,     next_rate: null,                next_label: null      },
  ];

  const doBoost = async () => {
    setBoosting(true);
    try {
      const { data: r } = await axios.post(
        `${API}/venue/${venue.id}/offers/${offerId}/boost`, {});
      setBoostInfo(r.boost);
      toast.success(`Boosted — push sent to ${r.boost.push_count} wallet users.`);
      setConfirm(false);
      refresh();
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : (d?.message || "Boost failed."));
    } finally { setBoosting(false); }
  };

  const boostActive = offer?.boost_active || boostInfo;
  const endsAt = offer?.boost_ends_at || boostInfo?.ends_at;

  return (
    <div className="space-y-5" data-testid="offer-tab-analytics-body">
      {/* Live "🔥 Boosted" banner — only while a boost is active. */}
      {boostActive && (
        <div className="rounded-2xl border-2 border-accent-magenta
                                  bg-accent-magenta/[0.12] px-4 py-3
                                  flex items-center justify-between"
              data-testid="analytics-boost-banner">
          <div className="text-sm">
            <span className="font-display font-bold">🔥 Boosted</span>
            {endsAt && (
              <span className="text-text-secondary text-xs ml-2">
                reverts <CountdownTimer to={endsAt} />
              </span>
            )}
          </div>
          <span className="text-[10px] uppercase tracking-widest text-accent-magenta">
            Active
          </span>
        </div>
      )}

      <div className="flex items-center justify-between">
        <div className="text-text-secondary text-xs">Funnel analytics</div>
        <div className="flex gap-1 p-1 bg-bg-glass rounded-full text-xs">
          {[["week", "7d"], ["month", "30d"]].map(([p, l]) => (
            <button key={p} onClick={() => setPeriod(p)}
                          className={`px-3 py-1 rounded-full ${period === p
                            ? "bg-accent-magenta/20 text-accent-magenta"
                            : "text-text-secondary"}`}
                          data-testid={`analytics-period-${p}`}>{l}</button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="analytics-stats">
        {stages.map((s) => (
          <div key={s.k} className="rounded-xl bg-white/[0.04] p-4"
                data-testid={`analytics-stat-${s.k}`}>
            <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono">
              {s.label}
            </div>
            <div className="font-display font-bold text-3xl tracking-display-tight mt-1">
              {(s.v || 0).toLocaleString()}
            </div>
            {s.next_rate !== null && (
              <div className="text-xs text-accent-electric mt-1">
                {(s.next_rate * 100).toFixed(1)}% → {s.next_label}
              </div>
            )}
          </div>
        ))}
      </div>
      {data.top_drop && (
        <div className="rounded-2xl border border-accent-magenta/40 bg-accent-magenta/[0.08]
                                  px-4 py-3 flex gap-3 items-start justify-between"
              data-testid="analytics-top-drop">
          <div className="flex gap-3 items-start min-w-0">
            <AlertTriangle size={16} className="text-accent-magenta mt-0.5 flex-shrink-0" />
            <div className="text-sm">
              <span className="font-display font-bold">{data.top_drop.drop_pct}% drop</span>
              {" "}from <span className="uppercase tracking-wider">{data.top_drop.from}</span>
              {" → "}<span className="uppercase tracking-wider">{data.top_drop.to}</span>.
              <div className="text-text-secondary text-xs mt-1">{data.top_drop.hint}</div>
            </div>
          </div>
          {data.boost_eligible && !boostActive && (
            <button
              type="button"
              onClick={() => setConfirm(true)}
              data-testid="analytics-boost-cta"
              className="flex-shrink-0 px-3 py-1.5 rounded-full bg-accent-magenta
                                  text-bg-base text-xs font-bold whitespace-nowrap
                                  inline-flex items-center gap-1">
              🔥 Boost this offer
            </button>
          )}
        </div>
      )}
      <div className="rounded-2xl bg-white/[0.03] p-4" data-testid="analytics-chart">
        <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono mb-3">
          Daily activity
        </div>
        <FunnelBarChart buckets={data.time_buckets} />
      </div>
      {/* Boost history (collapsed) */}
      <BoostHistory venue={venue} offerId={offerId} />

      {/* Confirm modal */}
      {confirm && (
        <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur-sm
                                flex items-center justify-center p-4"
              onClick={() => setConfirm(false)}>
          <div onClick={(e) => e.stopPropagation()}
                className="w-full max-w-md rounded-2xl bg-bg-base
                                  border border-accent-magenta/40 p-5 space-y-3"
                data-testid="analytics-boost-confirm">
            <div className="font-display font-bold text-xl tracking-display-tight">
              Fire a boost?
            </div>
            <p className="text-text-secondary text-sm">
              We'll push a notification to wallet users in your market who have
              saved offers from you in the last 90 days AND bump the discount
              by 5% for 24 hours. Cost: 1 boost (1 of 2 allowed in 14 days).
            </p>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button onClick={() => setConfirm(false)}
                            className="px-3 py-1.5 text-text-secondary text-sm">
                Cancel
              </button>
              <button onClick={doBoost} disabled={boosting}
                            data-testid="analytics-boost-confirm-yes"
                            className="px-4 py-2 rounded-full bg-accent-magenta
                                              text-bg-base text-sm font-bold disabled:opacity-50">
                {boosting ? "Boosting…" : "Fire boost"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


function CountdownTimer({ to }) {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => x + 1), 30000);
    return () => clearInterval(t);
  }, []);
  if (!to) return null;
  const ms = new Date(to).getTime() - Date.now();
  if (ms <= 0) return <span data-testid="boost-countdown-done">soon</span>;
  const h = Math.floor(ms / 3600000);
  const m = Math.floor((ms % 3600000) / 60000);
  return <span data-testid="boost-countdown">in {h}h {m}m</span>;
}


function BoostHistory({ venue, offerId }) {
  const [rows, setRows] = useState(null);
  useEffect(() => {
    if (!venue || !offerId) return;
    axios.get(`${API}/venue/${venue.id}/offers/${offerId}/boosts?limit=10`)
      .then(({ data }) => setRows(data.boosts || []))
      .catch(() => setRows([]));
  }, [venue, offerId]);
  if (!rows || rows.length === 0) return null;
  return (
    <div className="rounded-2xl bg-white/[0.03] p-4" data-testid="analytics-boost-history">
      <div className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono mb-2">
        Boost history
      </div>
      <div className="space-y-1 text-xs">
        {rows.map((b) => (
          <div key={b.id} className="flex items-center justify-between
                                                      border-b border-white/[0.05] pb-1">
            <span className="text-text-secondary">
              {new Date(b.started_at).toLocaleString()} · {b.status}
            </span>
            <span className="font-mono">
              {b.redeems_during} reds · push {b.push_count}
              {b.lift_abs !== 0 && (
                <span className={`ml-2 ${b.lift_abs > 0 ? "text-accent-electric" : "text-text-secondary"}`}>
                  {b.lift_abs > 0 ? "+" : ""}{b.lift_abs}
                </span>
              )}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function FunnelBarChart({ buckets }) {
  const [Recharts, setRecharts] = useState(null);
  useEffect(() => { import("recharts").then((m) => setRecharts(m)); }, []);
  if (!buckets || buckets.length === 0) {
    return <div className="text-text-secondary text-xs py-6 text-center">
      No activity in this window yet.
    </div>;
  }
  if (!Recharts) return <div className="text-text-secondary text-xs">Loading chart…</div>;
  const { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, CartesianGrid } = Recharts;
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={buckets}>
        <CartesianGrid stroke="rgba(255,255,255,0.06)" />
        <XAxis dataKey="day" stroke="#9aa0a6" fontSize={11} />
        <YAxis stroke="#9aa0a6" fontSize={11} />
        <Tooltip contentStyle={{ background: "#0a0a0c", border: "1px solid rgba(255,255,255,0.1)" }} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="impression" stackId="a" fill="#5b8def" />
        <Bar dataKey="save"        stackId="a" fill="#7fd1ff" />
        <Bar dataKey="scan"        stackId="a" fill="#f7c95c" />
        <Bar dataKey="redeem"     stackId="a" fill="#ff2d8a" />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ─── Variants tab — Phase 17b A/B testing ────────────────────────────
export function OfferVariantsPanel({ venue, offerId }) {
  const [variants, setVariants]    = useState(null);
  const [winnerSlug, setWinner]   = useState(null);
  const [form, setForm] = useState({ headline: "", description: "", weight: 50 });
  const refresh = async () => {
    if (!venue || !offerId) return;
    try {
      const { data } = await axios.get(
        `${API}/venue/${venue.id}/offers/${offerId}/variants/results?period=month`);
      setVariants(data.variants || []); setWinner(data.auto_winner_slug);
    } catch { setVariants([]); }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [venue, offerId]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.headline.trim()) return;
    try {
      await axios.post(`${API}/venue/${venue.id}/offers/${offerId}/variants`, form);
      setForm({ headline: "", description: "", weight: 50 });
      toast.success("Variant added.");
      refresh();
    } catch { toast.error("Couldn't add variant."); }
  };
  const promote = async (slug) => {
    try {
      await axios.post(`${API}/venue/${venue.id}/offers/${offerId}/variants/${slug}/promote`);
      toast.success(`Promoted ${slug} to 100% traffic.`);
      refresh();
    } catch { toast.error("Couldn't promote."); }
  };

  if (variants === null) return <div className="text-text-secondary text-sm">Loading…</div>;

  return (
    <div className="space-y-5" data-testid="offer-tab-variants-body">
      {winnerSlug && (
        <div className="rounded-2xl border-2 border-accent-electric bg-accent-electric/[0.08]
                                  px-4 py-3 flex items-center justify-between gap-3"
              data-testid="variants-auto-winner">
          <div className="text-sm">
            <span className="font-display font-bold">{winnerSlug}</span>
            {" is the auto-detected winner (95% confidence)."}
          </div>
          <button onClick={() => promote(winnerSlug)}
                        className="px-3 py-1 rounded-lg bg-accent-electric text-bg-base text-xs font-bold"
                        data-testid="variants-promote-winner">
            Promote
          </button>
        </div>
      )}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="variants-list">
        {variants.map((v) => (
          <div key={v.slug}
                className={`rounded-2xl p-4 space-y-2 border
                                ${v.slug === winnerSlug
                                  ? "border-accent-electric bg-accent-electric/[0.06]"
                                  : "border-white/[0.10] bg-white/[0.03]"}`}
                data-testid={`variant-card-${v.slug}`}>
            <div className="flex items-center justify-between">
              <span className="text-[10px] uppercase tracking-[0.25em] text-text-secondary font-mono">
                {v.slug} · weight {v.weight ?? 0}
              </span>
              {v.status && (
                <span className="text-[10px] uppercase tracking-widest text-text-secondary">
                  {v.status}
                </span>
              )}
            </div>
            <div className="font-display font-bold text-lg tracking-display-tight">
              {v.headline || "—"}
            </div>
            <div className="text-text-secondary text-xs space-y-1">
              <div>Impressions: <span className="font-mono">{v.impressions}</span></div>
              <div>Redeems: <span className="font-mono">{v.redeems}</span></div>
              <div>Rate: <span className="font-mono">{((v.redeem_rate || 0) * 100).toFixed(2)}%</span></div>
              <div>CI 95%: <span className="font-mono">
                [{((v.ci_lo || 0) * 100).toFixed(1)}%, {((v.ci_hi || 0) * 100).toFixed(1)}%]
              </span></div>
            </div>
            {v.slug !== "control" && v.slug !== winnerSlug && (
              <button onClick={() => promote(v.slug)}
                            className="text-xs text-accent-electric"
                            data-testid={`variant-promote-${v.slug}`}>
                Promote →
              </button>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={submit} className="rounded-2xl bg-white/[0.03] p-4 space-y-3"
                data-testid="variants-create-form">
        <div className="font-display font-bold text-sm tracking-display-tight">
          Add a new headline variant
        </div>
        <input
          type="text" placeholder="Headline (e.g. 'Tonight only — 50% off karak')"
          value={form.headline}
          onChange={(e) => setForm({ ...form, headline: e.target.value })}
          className="w-full px-3 py-2 rounded-xl bg-bg-base border border-white/[0.10] text-sm"
          data-testid="variants-headline-input"
        />
        <input
          type="text" placeholder="Description (optional)"
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          className="w-full px-3 py-2 rounded-xl bg-bg-base border border-white/[0.10] text-sm"
        />
        <div className="flex items-center gap-3 text-xs">
          <label className="text-text-secondary">Weight</label>
          <input type="number" min="1" max="100" value={form.weight}
                      onChange={(e) => setForm({ ...form, weight: Number(e.target.value) })}
                      className="w-20 px-2 py-1 rounded-lg bg-bg-base border border-white/[0.10] font-mono" />
          <span className="text-text-secondary">% of traffic</span>
        </div>
        <Button variant="primary" size="sm" type="submit" data-testid="variants-create-submit">
          Add variant
        </Button>
      </form>
    </div>
  );
}



// ─── /venue/offers/:offerId ─────────────────────────────────────────
export function VenueOfferDetail({ venue }) {
  const { offerId } = useParams();
  const [offer, setOffer] = useState(null);
  const [count, setCount] = useState(0);
  const [tab, setTab]      = useState("detail");
  const navigate = useNavigate();
  const refresh = async () => {
    if (!venue || !offerId) return;
    try {
      const { data } = await axios.get(`${API}/venue/${venue.id}/offers/${offerId}`);
      setOffer(data.offer); setCount(data.coupon_count || 0);
    } catch (_) { /* */ }
  };
  useEffect(() => { refresh(); /* eslint-disable-next-line */ }, [venue, offerId]);

  const togglePauseResume = async () => {
    const next = offer.status === "active" ? "paused" : "active";
    try {
      if (offer.status === "exhausted") {
        await axios.post(`${API}/venue/${venue.id}/offers/${offerId}/resume`);
      } else {
        await axios.patch(`${API}/venue/${venue.id}/offers/${offerId}`, { status: next });
      }
      refresh();
      toast.success(`Offer ${next === "active" ? "resumed" : "paused"}.`);
    } catch { toast.error("Couldn't update."); }
  };
  const archive = async () => {
    if (!window.confirm(`Archive "${offer.title}"? Existing coupons remain valid.`)) return;
    try {
      await axios.delete(`${API}/venue/${venue.id}/offers/${offerId}`);
      navigate("/venue/offers");
      toast.success("Offer archived.");
    } catch { toast.error("Couldn't archive."); }
  };

  if (!venue || !offer) return <div className="text-text-secondary py-10 text-center">Loading…</div>;
  const remaining = offer.max_redemptions
    ? Math.max(0, offer.max_redemptions - (offer.issued_count || 0))
    : "∞";
  return (
    <div className="space-y-5" data-testid="venue-offer-detail">
      <Card className="p-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono">
              {offer.offer_type} · {offer.status}
            </div>
            <h2 className="font-display font-bold text-3xl tracking-display-tight mt-1"
                  data-testid="venue-offer-title">
              {offer.title}
            </h2>
            {offer.description && (
              <p className="text-text-secondary text-sm mt-2 max-w-xl">{offer.description}</p>
            )}
          </div>
          <div className="flex gap-2 flex-shrink-0">
            <button onClick={togglePauseResume}
                          className="px-3 py-1.5 rounded-lg bg-bg-glass border border-white/[0.10]
                                            text-xs flex items-center gap-1"
                          data-testid="venue-offer-toggle">
              {offer.status === "active" ? <><Pause size={12} /> Pause</> : <><Play size={12} /> Resume</>}
            </button>
            {offer.status !== "archived" && (
              <button onClick={archive}
                            className="px-3 py-1.5 rounded-lg bg-accent-magenta/15 text-accent-magenta
                                              text-xs flex items-center gap-1"
                            data-testid="venue-offer-archive">
                <Archive size={12} /> Archive
              </button>
            )}
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 mt-5">
          <Stat2 label="Issued" v={offer.issued_count || 0} />
          <Stat2 label="Redeemed" v={offer.redeemed_count || 0} />
          <Stat2 label="Remaining" v={remaining} />
        </div>
      </Card>
      <div className="flex gap-1 p-1 bg-bg-glass rounded-full text-sm w-fit" data-testid="offer-detail-tabs">
        {[["detail", "Detail"], ["coupons", "Coupons"],
          ["analytics", "Analytics"], ["variants", "Variants"]].map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
                        data-testid={`offer-tab-${k}`}
                        className={`px-3 py-1.5 rounded-full ${tab === k
                          ? "bg-accent-magenta/20 text-accent-magenta"
                          : "text-text-secondary hover:text-text-primary"}`}>
            {l}
          </button>
        ))}
      </div>
      <Card className="p-6">
        {tab === "detail" && (
          <div className="space-y-3" data-testid="offer-tab-detail-body">
            <Row label="Discount" v={`${offer.discount_value} (${offer.offer_type})`} />
            <Row label="Total cap" v={offer.max_redemptions || "—"} />
            <Row label="Daily cap" v={offer.daily_cap || "—"} />
            <Row label="Budget cap" v={offer.budget_cap_usd ? `$${offer.budget_cap_usd}` : "—"} />
            <Row label="Method"     v={offer.redemption_method} />
            <Row label="Terms"      v={offer.terms || "—"} />
            <Row label="Start"        v={offer.start_time || "—"} />
            <Row label="End"          v={offer.end_time || "—"} />
            {offer.auto_paused_reason && (
              <Row label="Auto-paused" v={`${offer.auto_paused_reason} at ${offer.auto_paused_at}`} />
            )}
          </div>
        )}
        {tab === "coupons" && (
          <div className="text-sm" data-testid="offer-tab-coupons-body">
            <span className="font-display font-bold text-base">{count}</span> coupon(s) issued total.
            <div className="text-text-secondary text-xs mt-1">
              <NavLink to={`/venue/${venue.id}/payouts`} className="text-accent-electric">
                See payout report →
              </NavLink>
            </div>
          </div>
        )}
        {tab === "analytics" && (
          <OfferAnalyticsPanel venue={venue} offerId={offerId} />
        )}
        {tab === "variants" && (
          <OfferVariantsPanel venue={venue} offerId={offerId} />
        )}
      </Card>
    </div>
  );
}

function Row({ label, v }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-3 text-sm">
      <div className="text-text-secondary text-xs uppercase tracking-widest font-mono">{label}</div>
      <div>{String(v)}</div>
    </div>
  );
}

function Stat2({ label, v }) {
  return (
    <div className="rounded-xl bg-white/[0.04] px-4 py-3">
      <div className="text-[10px] uppercase tracking-[0.3em] text-text-secondary font-mono">{label}</div>
      <div className="font-display font-bold text-2xl tracking-display-tight mt-1">{v}</div>
    </div>
  );
}

// ─── /venue/redeem/scan — PWA QR scanner ────────────────────────────
const SOUND_KEY = "bigfm_scan_sound_on";

export function VenueScanRedeem({ venue }) {
  const [manual, setManual] = useState("");
  const [result, setResult]  = useState(null);   // {ok, message, color}
  const [scanning, setScanning] = useState(false);
  const [error, setError]    = useState(null);
  const [soundOn, setSoundOn] = useState(() => {
    try { return localStorage.getItem(SOUND_KEY) !== "off"; } catch { return true; }
  });
  const videoRef     = useRef(null);
  const streamRef   = useRef(null);
  const intervalRef = useRef(null);
  const scannerRef = useRef(null);   // html5-qrcode scanner (lazy)
  const lastCodeRef = useRef({ code: null, t: 0 });

  const playChime = (ok) => {
    if (!soundOn) return;
    try {
      const ac = new (window.AudioContext || window.webkitAudioContext)();
      const o = ac.createOscillator();
      const g = ac.createGain();
      o.connect(g); g.connect(ac.destination);
      o.type = "sine";
      o.frequency.value = ok ? 880 : 200;
      g.gain.setValueAtTime(0.15, ac.currentTime);
      g.gain.exponentialRampToValueAtTime(0.001, ac.currentTime + 0.4);
      o.start(); o.stop(ac.currentTime + 0.4);
    } catch (_) { /* */ }
  };

  const submit = async (code) => {
    if (!code || !venue) return;
    // De-dupe — ignore a re-scan of the same code within 3 s.
    const now = Date.now();
    if (lastCodeRef.current.code === code && now - lastCodeRef.current.t < 3000) return;
    lastCodeRef.current = { code, t: now };
    try {
      const { data } = await axios.post(`${API}/venue/${venue.id}/coupons/redeem`, { code });
      setResult({ ok: true, message: `Redeemed ${data.coupon_id}`, color: "green" });
      playChime(true);
    } catch (e) {
      const d = e?.response?.data?.detail;
      const code2 = (d && typeof d === "object" && d.code) || "redeem_failed";
      const msg = (d && typeof d === "object" && d.message)
                  || (typeof d === "string" ? d : "Couldn't redeem.");
      setResult({ ok: false, message: `${code2} — ${msg}`, color: "magenta" });
      playChime(false);
    }
    setTimeout(() => setResult(null), 3000);
    setManual("");
  };

  const startCamera = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }
      setScanning(true);
      // Lazy-load html5-qrcode for the live decode loop.
      try {
        const mod = await import("html5-qrcode");
        // Decode the live <video> via BarcodeDetector when available
        // (faster + zero extra bundle).  Fall back to html5-qrcode.
        const Detector = (typeof window !== "undefined" && "BarcodeDetector" in window)
                              ? new window.BarcodeDetector({ formats: ["qr_code"] }) : null;
        if (Detector) {
          intervalRef.current = setInterval(async () => {
            try {
              const codes = await Detector.detect(videoRef.current);
              if (codes && codes[0] && codes[0].rawValue) submit(codes[0].rawValue);
            } catch (_) { /* */ }
          }, 400);
        } else {
          // html5-qrcode UI in a hidden container.
          const Html5Qrcode = mod.Html5Qrcode || mod.default?.Html5Qrcode;
          scannerRef.current = new Html5Qrcode("scan-region", false);
          scannerRef.current.start(
            { facingMode: "environment" }, { fps: 6, qrbox: 240 },
            (txt) => submit(txt), () => {},
          ).catch(() => {});
        }
      } catch (_) { /* swallow; user can still use manual input */ }
    } catch (e) {
      setError(e?.name === "NotAllowedError"
                  ? "Camera permission denied. Tap 'Allow' in your browser, or use the manual input."
                  : "Couldn't access the camera. Try the manual input.");
      setScanning(false);
    }
  };

  const stopCamera = () => {
    if (intervalRef.current) clearInterval(intervalRef.current);
    if (scannerRef.current) { try { scannerRef.current.stop(); } catch {} }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    setScanning(false);
  };

  useEffect(() => () => stopCamera(), []);
  const toggleSound = () => {
    const next = !soundOn;
    setSoundOn(next);
    try { localStorage.setItem(SOUND_KEY, next ? "on" : "off"); } catch (_) {}
  };

  if (!venue) return null;
  return (
    <div className="space-y-5" data-testid="venue-scan-page">
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-display font-bold text-xl tracking-display-tight">
              Scan a coupon
            </div>
            <div className="text-text-secondary text-xs">
              Point the camera at the player's QR.  Hands-free; auto-resumes after each scan.
            </div>
          </div>
          <button onClick={toggleSound} className="text-text-secondary px-2"
                        data-testid="scan-sound-toggle">
            {soundOn ? <Volume2 size={16} /> : <VolumeX size={16} />}
          </button>
        </div>
        <div id="scan-region"
              className="relative aspect-square rounded-2xl bg-black overflow-hidden
                                border border-white/[0.10]"
              data-testid="scan-viewfinder">
          <video ref={videoRef}
                    playsInline muted autoPlay
                    className="absolute inset-0 w-full h-full object-cover" />
          {!scanning && (
            <div className="absolute inset-0 flex items-center justify-center text-text-secondary">
              <Camera size={32} />
            </div>
          )}
          {scanning && (
            <div className="absolute inset-0 pointer-events-none">
              <div className="absolute inset-10 border-2 border-accent-electric rounded-2xl" />
              <ScanLine className="absolute left-10 right-10 top-1/2 text-accent-electric/70 animate-pulse" />
            </div>
          )}
          {result && (
            <div className={`absolute inset-0 ${result.color === "green"
                                  ? "bg-green-500/20 border-4 border-green-400"
                                  : "bg-accent-magenta/30 border-4 border-accent-magenta"}
                                    flex items-center justify-center`}
                  data-testid="scan-flash">
              <div className="bg-bg-base/90 px-6 py-4 rounded-2xl font-display font-bold text-base text-center max-w-[85%]">
                {result.ok
                  ? <CheckCircle2 className="inline mr-2 text-green-400" size={20} />
                  : <XCircle className="inline mr-2 text-accent-magenta" size={20} />}
                {result.message}
              </div>
            </div>
          )}
        </div>
        {!scanning ? (
          <Button variant="primary" onClick={startCamera}
                      data-testid="scan-start-btn">
            <Camera size={14} /> Start camera
          </Button>
        ) : (
          <Button variant="ghost" onClick={stopCamera} data-testid="scan-stop-btn">
            Stop
          </Button>
        )}
        {error && (
          <div className="text-accent-magenta text-sm" data-testid="scan-error">
            {error}
          </div>
        )}
      </Card>
      <Card className="p-5 space-y-2">
        <div className="font-display font-bold text-sm tracking-display-tight">
          Manual code (low-light fallback)
        </div>
        <form onSubmit={(e) => { e.preventDefault(); submit(manual.trim()); }}
                  className="flex gap-2">
          <input
            value={manual}
            onChange={(e) => setManual(e.target.value)}
            placeholder="cpn_xxxxxxxxxxxx"
            className="flex-1 px-3 py-2 rounded-xl bg-bg-glass border border-white/[0.10] font-mono text-sm"
            data-testid="scan-manual-input"
          />
          <Button variant="primary" size="sm" type="submit" data-testid="scan-manual-submit">
            Redeem
          </Button>
        </form>
      </Card>
    </div>
  );
}
