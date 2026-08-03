// Phase Π+1 — Production-readiness dashboard.
//
// Polls /api/admin/system/health every 30s and renders a clear
// traffic-light view: overall green/red light, kill-switch chips,
// integration key chips, background-task panel, and the live blocker
// list with one-line remediation hints.
//
// The endpoint already returns everything; this page is pure display.
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { CheckCircle2, XCircle, AlertTriangle, RefreshCw,
          ChevronDown, ChevronRight, Server, Key, ToggleRight,
          Clock, Activity, ShieldAlert, ShieldCheck,
          CloudUpload, Database, Loader2 } from "lucide-react";
import { Card, Button, Chip } from "@/shell/primitives";
import { useAuth } from "@/AuthContext";
// Phase FUN.1.1 — Flagship fleet health card.
import AdminFlagshipHealthCard from "@/pages/admin/AdminFlagshipHealthCard";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const POLL_MS = 30_000;

// ────────────────────── classification rules ──────────────────────
// For each kill-switch we declare its prod-safe value.  A switch is
// `green` when its current value === prod-safe.  Booleans that are
// "true=safe" (e.g. webhook signature verify) get green when true;
// booleans that are "false=safe" (debug/dev/dual-write) get green
// when false.  String switches match against a literal.
const SWITCH_RULES = {
  ENV:                                                  { type: "string", safe: "production",
                                                                      dev: "development" },
  BIGFM_DEV_ESCAPE_HATCHES:      { type: "bool",      safe: false },
  BIGFM_DEBUG_GEO:                              { type: "bool",      safe: false },
  BIGCOIN_LEGACY_DUAL_WRITE:  { type: "bool",      safe: false },
  MAILGUN_WEBHOOK_VERIFY_SIGNATURE:
                                                                          { type: "bool",      safe: true },
  STRIPE_WEBHOOK_VERIFY_SIGNATURE:
                                                                          { type: "bool",      safe: true },
  STRIPE_MODE:                                  { type: "string", safe: "live"   },
  INVITE_EMAIL_LIVE:                  { type: "bool",      safe: true },
  NEWS_PROVIDER:                          { type: "string", safe: "newsapi" },
};

// CORS lockdown is checked separately because we don't surface the raw
// origins in the health payload — we derive it from the cors_wildcard
// issue if present.

const KEY_LABELS = {
  openai_text:              "OpenAI Text",
  openai_image:            "OpenAI Image",
  elevenlabs:                  "ElevenLabs",
  newsapi:                          "NewsAPI",
  mailgun:                          "Mailgun (send)",
  mailgun_webhook:      "Mailgun Webhook Key",
  stripe_secret:              "Stripe Secret",
  stripe_publishable: "Stripe Publishable",
  stripe_webhook:          "Stripe Webhook Secret",
  google_maps:                "Google Maps",
  google_routes:          "Google Routes",
  google_places:          "Google Places",
  google_weather:          "Google Weather",
  predexon:                      "Predexon",
  tigris:                          "Tigris (storage)",
  livekit:                          "LiveKit (lobbies)",
};

// Integrations where missing = high-priority blocker.  Other keys
// (Google *) are advisory while Phase H is BLOCKED.
const KEY_BLOCKER = new Set([
  "mailgun_webhook", "stripe_webhook",
]);


// ────────────────────── helpers ──────────────────────
function fmtSwitchValue(v) {
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

function classifySwitch(key, value) {
  const rule = SWITCH_RULES[key];
  if (!rule) return "neutral";
  if (rule.type === "bool") {
    return value === rule.safe ? "green" : "yellow";
  }
  if (rule.type === "string") {
    if (value === rule.safe) return "green";
    if (rule.dev && value === rule.dev) return "yellow";
    return "yellow";
  }
  return "neutral";
}


// ────────────────────── main page ──────────────────────
export default function AdminHealth() {
  const { user } = useAuth();
  const [data, setData]            = useState(null);
  const [loading, setLoading]  = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr]              = useState(null);
  const [showSwitches, setShowSwitches] = useState(true);
  const [showKeys, setShowKeys]              = useState(true);
  const [showAssets, setShowAssets]      = useState(true);
  const [showTasks, setShowTasks]            = useState(false);
  const [showBlockers, setShowBlockers]  = useState(true);

  const load = useCallback(async (silent = false) => {
    if (!silent) setRefreshing(true);
    try {
      const r = await axios.get(`${API}/admin/system/health`);
      setData(r.data);
      setErr(null);
    } catch (e) {
      setErr(e?.response?.data?.detail || "load_failed");
      if (!silent) toast.error("Couldn't load health snapshot.");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    const t = setInterval(() => load(true), POLL_MS);
    return () => clearInterval(t);
  }, [load]);

  if (!user || (user.role !== "admin" && !user.is_admin)) {
    return (
      <div data-testid="admin-health-denied"
              className="min-h-screen grid place-items-center text-text-secondary">
        Admins only.
      </div>
    );
  }

  if (loading && !data) {
    return (
      <div className="min-h-screen grid place-items-center text-text-secondary"
              data-testid="admin-health-loading">
        <Loader2 size={22} className="animate-spin" />
      </div>
    );
  }

  if (err || !data) {
    return (
      <div data-testid="admin-health-error"
              className="min-h-screen grid place-items-center px-4">
        <Card className="max-w-md w-full p-6 text-center space-y-3">
          <XCircle size={28} className="text-rose-400 mx-auto" />
          <h2 className="font-display font-bold text-xl">
            Couldn&apos;t load health snapshot
          </h2>
          <p className="text-xs text-text-secondary">
            {err || "Unknown error"}
          </p>
          <Button variant="outline" onClick={() => load()}
                          data-testid="admin-health-retry">
            <RefreshCw size={14} /> Retry
          </Button>
        </Card>
      </div>
    );
  }

  const productionReady = !!data.production_ready;
  const highIssues = (data.issues || []).filter((i) => i.severity === "high");
  const infoIssues = (data.issues || []).filter((i) => i.severity === "info");
  const am                = data.asset_migration || null;

  return (
    <div data-testid="admin-health-page"
            className="min-h-screen bg-bg-base px-4 sm:px-6 py-8 pb-20
                              max-w-5xl mx-auto space-y-5">
      <Toaster richColors theme="dark" position="bottom-right" />

      {/* ── Header ────────────────────────────────────────── */}
      <header className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary flex items-center gap-2">
            <Activity size={11} /> Admin · System Health
          </div>
          <h1 className="font-display font-bold text-3xl sm:text-4xl
                                  tracking-display-tight">
            Production <span className={productionReady
                                                                ? "text-emerald-400" : "text-rose-400"}>
              readiness
            </span>
          </h1>
          <p className="text-xs text-text-secondary mt-1">
            Polling every {POLL_MS / 1000}s · last refreshed{" "}
            {new Date(data.ts).toLocaleTimeString()}
          </p>
        </div>
        <Button variant="outline" onClick={() => load()}
                        disabled={refreshing}
                        data-testid="admin-health-refresh">
          {refreshing
            ? <Loader2 size={14} className="animate-spin" />
            : <RefreshCw size={14} />}
          Refresh
        </Button>
      </header>

      {/* Phase FUN.1.1 — Flagship fleet health widget. */}
      <AdminFlagshipHealthCard />

      {/* ── 1. Production Readiness traffic light ──────────── */}
      <Card data-testid="admin-health-readiness-strip"
                  className={`p-6 sm:p-8 flex flex-col sm:flex-row items-start
                                    sm:items-center gap-4 sm:gap-6 border-2
                                    ${productionReady
                                            ? "border-emerald-500/40 bg-emerald-500/[0.06]"
                                            : "border-rose-500/40 bg-rose-500/[0.06]"}`}>
        <div className={`w-20 h-20 rounded-full grid place-items-center
                                  ${productionReady
                                          ? "bg-emerald-500/20 text-emerald-300"
                                          : "bg-rose-500/20 text-rose-300"}`}>
          {productionReady
            ? <CheckCircle2 size={42} />
            : <XCircle size={42} />}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="font-display font-bold text-2xl sm:text-3xl
                                  tracking-display-tight">
            {productionReady
              ? "Production-ready ✓"
              : "Not production-ready"}
          </h2>
          <p className="text-sm text-text-secondary mt-1">
            {productionReady
              ? "All high-severity blockers cleared. Safe to flip ENV=production."
              : `${highIssues.length} high-severity blocker${highIssues.length === 1 ? "" : "s"}`
                  + (infoIssues.length ? ` · ${infoIssues.length} info` : "")}
          </p>
        </div>
      </Card>

      {/* ── 2. Blockers (always expanded when present) ───────── */}
      {(highIssues.length > 0 || infoIssues.length > 0) && (
        <Card data-testid="admin-health-blockers" className="p-5 space-y-3">
          <button onClick={() => setShowBlockers((v) => !v)}
                          className="w-full flex items-center justify-between"
                          data-testid="admin-health-blockers-toggle">
            <h3 className="font-display font-bold text-lg tracking-display-tight
                                    flex items-center gap-2">
              <ShieldAlert size={16} className="text-rose-400" />
              Blockers ({highIssues.length} high · {infoIssues.length} info)
            </h3>
            {showBlockers
              ? <ChevronDown size={16} className="text-text-secondary" />
              : <ChevronRight size={16} className="text-text-secondary" />}
          </button>
          {showBlockers && (
            <ul className="space-y-2" data-testid="admin-health-blockers-list">
              {highIssues.map((i) => (
                <li key={i.code}
                    data-testid={`admin-health-blocker-${i.code}`}
                    className="flex items-start gap-3 p-3 rounded-token-md
                                  bg-rose-500/[0.05] border border-rose-500/20">
                  <XCircle size={16} className="text-rose-400 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <div className="text-sm text-rose-200 font-semibold capitalize">
                      {i.code.replace(/_/g, " ")}
                    </div>
                    <div className="text-xs text-text-secondary mt-0.5">
                      {i.msg}
                    </div>
                  </div>
                </li>
              ))}
              {infoIssues.map((i) => (
                <li key={i.code}
                    data-testid={`admin-health-info-${i.code}`}
                    className="flex items-start gap-3 p-3 rounded-token-md
                                  bg-yellow-500/[0.05] border border-yellow-500/20">
                  <AlertTriangle size={16}
                                                className="text-yellow-400 mt-0.5 flex-shrink-0" />
                  <div className="flex-1">
                    <div className="text-sm text-yellow-200 font-semibold capitalize">
                      {i.code.replace(/_/g, " ")}
                    </div>
                    <div className="text-xs text-text-secondary mt-0.5">
                      {i.msg}
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}

      {/* ── 3. Kill switches strip ─────────────────────────── */}
      <Card data-testid="admin-health-switches" className="p-5 space-y-3">
        <button onClick={() => setShowSwitches((v) => !v)}
                        className="w-full flex items-center justify-between"
                        data-testid="admin-health-switches-toggle">
          <h3 className="font-display font-bold text-lg tracking-display-tight
                                  flex items-center gap-2">
            <ToggleRight size={16} className="text-accent-electric" />
            Kill switches
          </h3>
          {showSwitches
            ? <ChevronDown size={16} className="text-text-secondary" />
            : <ChevronRight size={16} className="text-text-secondary" />}
        </button>
        {showSwitches && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2"
                  data-testid="admin-health-switches-grid">
            {Object.entries(data.kill_switches || {}).map(([k, v]) => {
              const tone = classifySwitch(k, v);
              const cls =
                tone === "green"
                  ? "border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-200"
                  : tone === "yellow"
                  ? "border-yellow-500/30 bg-yellow-500/[0.06] text-yellow-100"
                  : "border-white/[0.08] bg-white/[0.03] text-text-secondary";
              const icon =
                tone === "green" ? <CheckCircle2 size={14} className="text-emerald-400" />
                : tone === "yellow" ? <AlertTriangle size={14} className="text-yellow-400" />
                : <Server size={14} className="text-text-secondary" />;
              return (
                <div key={k}
                          data-testid={`admin-health-switch-${k}`}
                          className={`rounded-token-md border p-3 flex items-center
                                          justify-between gap-2 ${cls}`}>
                  <div className="flex items-center gap-2 min-w-0">
                    {icon}
                    <span className="font-mono text-[11px] truncate">{k}</span>
                  </div>
                  <span className="font-mono text-[11px] font-semibold">
                    {fmtSwitchValue(v)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ── 4. Keys present strip ──────────────────────────── */}
      <Card data-testid="admin-health-keys" className="p-5 space-y-3">
        <button onClick={() => setShowKeys((v) => !v)}
                        className="w-full flex items-center justify-between"
                        data-testid="admin-health-keys-toggle">
          <h3 className="font-display font-bold text-lg tracking-display-tight
                                  flex items-center gap-2">
            <Key size={16} className="text-accent-gold" />
            Integrations & keys
          </h3>
          {showKeys
            ? <ChevronDown size={16} className="text-text-secondary" />
            : <ChevronRight size={16} className="text-text-secondary" />}
        </button>
        {showKeys && (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2"
                  data-testid="admin-health-keys-grid">
            {Object.entries(data.keys_present || {}).map(([k, present]) => {
              const blocker = !present && KEY_BLOCKER.has(k);
              const cls = present
                ? "border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-200"
                : blocker
                ? "border-rose-500/30 bg-rose-500/[0.06] text-rose-200"
                : "border-white/[0.08] bg-white/[0.03] text-text-secondary";
              const icon = present
                ? <CheckCircle2 size={12} className="text-emerald-400" />
                : blocker
                ? <XCircle size={12} className="text-rose-400" />
                : <AlertTriangle size={12} className="text-yellow-400 opacity-60" />;
              return (
                <div key={k}
                          data-testid={`admin-health-key-${k}`}
                          className={`rounded-token-md border p-2.5 flex
                                          items-center gap-2 ${cls}`}>
                  {icon}
                  <span className="text-[11px] truncate">
                    {KEY_LABELS[k] || k}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </Card>

      {/* ── 4b. Asset migration / Tigris fallback CDN strip ── */}
      {am && (
        <Card data-testid="admin-health-assets" className="p-5 space-y-3">
          <button onClick={() => setShowAssets((v) => !v)}
                          className="w-full flex items-center justify-between"
                          data-testid="admin-health-assets-toggle">
            <h3 className="font-display font-bold text-lg tracking-display-tight
                                    flex items-center gap-2">
              <CloudUpload size={16}
                                          className={am.status === "green"
                                                              ? "text-emerald-400"
                                                              : am.status === "yellow"
                                                              ? "text-yellow-400"
                                                              : "text-rose-400"} />
              Asset migration · Tigris fallback CDN
              <span className={`ml-2 inline-flex items-center gap-1 rounded-full
                                              px-2 py-0.5 text-[10px] font-mono uppercase
                                              tracking-widest
                                              ${am.status === "green"
                                                      ? "bg-emerald-500/15 text-emerald-300"
                                                      : am.status === "yellow"
                                                      ? "bg-yellow-500/15 text-yellow-200"
                                                      : "bg-rose-500/15 text-rose-300"}`}
                              data-testid="admin-health-assets-status-pill">
                {am.status}
              </span>
            </h3>
            {showAssets
              ? <ChevronDown size={16} className="text-text-secondary" />
              : <ChevronRight size={16} className="text-text-secondary" />}
          </button>
          {showAssets && (
            <div className="space-y-3" data-testid="admin-health-assets-body">

              {/* Strategy + bucket + last-run row */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                <div data-testid="admin-health-assets-strategy"
                          className="rounded-token-md border border-white/[0.08]
                                                  bg-white/[0.03] p-3">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary">URL strategy</div>
                  <div className="font-display font-semibold text-sm
                                          text-text-primary mt-1">
                    {am.tigris_url_strategy || "n/a"}
                  </div>
                </div>
                <div data-testid="admin-health-assets-bucket"
                          className="rounded-token-md border border-white/[0.08]
                                                  bg-white/[0.03] p-3">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary">Bucket</div>
                  <div className="font-mono text-sm text-text-primary mt-1 truncate">
                    {am.bucket || "—"}
                  </div>
                </div>
                <div data-testid="admin-health-assets-last-run"
                          className="rounded-token-md border border-white/[0.08]
                                                  bg-white/[0.03] p-3">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary">Last migration</div>
                  <div className="font-mono text-[11px] text-text-primary mt-1">
                    {am.last_run_at
                      ? new Date(am.last_run_at).toLocaleString()
                      : "never"}
                  </div>
                </div>
              </div>

              {/* Static + tracks counts */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div data-testid="admin-health-assets-static-uploaded"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary flex items-center gap-1">
                    <Database size={9} /> Static · synced
                  </div>
                  <div className="font-display font-bold text-xl text-emerald-300 mt-0.5">
                    {Number(
                      (am.static_summary?.uploaded || 0)
                      + (am.static_summary?.skipped || 0)
                    ).toLocaleString()}
                  </div>
                </div>
                <div data-testid="admin-health-assets-static-failed"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary flex items-center gap-1">
                    <XCircle size={9} /> Static · failed
                  </div>
                  <div className={`font-display font-bold text-xl mt-0.5
                                                  ${(am.static_summary?.failed || 0) > 0
                                                          ? "text-rose-300"
                                                          : "text-text-primary"}`}>
                    {Number(am.static_summary?.failed || 0).toLocaleString()}
                  </div>
                </div>
                <div data-testid="admin-health-assets-tracks-migrated"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary flex items-center gap-1">
                    <Database size={9} /> Tracks · migrated
                  </div>
                  <div className="font-display font-bold text-xl text-text-primary mt-0.5">
                    {Number(
                      (am.tracks_summary?.migrated || 0)
                      + (am.tracks_summary?.skipped_already_migrated || 0)
                    ).toLocaleString()}
                  </div>
                </div>
                <div data-testid="admin-health-assets-tracks-missing"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary flex items-center gap-1">
                    <AlertTriangle size={9} /> Tracks · missing local
                  </div>
                  <div className={`font-display font-bold text-xl mt-0.5
                                                  ${(am.tracks_summary?.missing_local_file || 0) > 0
                                                          ? "text-yellow-300"
                                                          : "text-text-primary"}`}>
                    {Number(am.tracks_summary?.missing_local_file || 0).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* Live fallback counters */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                <div data-testid="admin-health-assets-fallback-today"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary">Fallback · today</div>
                  <div className="font-display font-bold text-xl
                                          text-accent-electric mt-0.5">
                    {Number(am.fallback?.today || 0).toLocaleString()}
                  </div>
                </div>
                <div data-testid="admin-health-assets-fallback-lifetime"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary">Fallback · total</div>
                  <div className="font-display font-bold text-xl text-text-primary mt-0.5">
                    {Number(am.fallback?.lifetime || 0).toLocaleString()}
                  </div>
                </div>
                <div data-testid="admin-health-assets-fallback-cache"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary">HEAD cache · entries</div>
                  <div className="font-display font-bold text-xl text-text-primary mt-0.5">
                    {Number(am.fallback?.cache_entries || 0).toLocaleString()}
                  </div>
                </div>
                <div data-testid="admin-health-assets-backend"
                          className="rounded-token-md bg-white/[0.04] p-2.5">
                  <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-text-secondary">Storage backend</div>
                  <div className="font-mono text-sm text-text-primary mt-1">
                    {am.tigris_backend || "—"}
                  </div>
                </div>
              </div>

              {am.notes && (
                <p className="text-[11px] text-text-secondary italic
                                          border-l-2 border-white/[0.10] pl-3"
                    data-testid="admin-health-assets-notes">
                  {am.notes}
                </p>
              )}
            </div>
          )}
        </Card>
      )}

      {/* ── 5. Background tasks panel ─────────────────────── */}
      <Card data-testid="admin-health-tasks" className="p-5 space-y-3">
        <button onClick={() => setShowTasks((v) => !v)}
                        className="w-full flex items-center justify-between"
                        data-testid="admin-health-tasks-toggle">
          <h3 className="font-display font-bold text-lg tracking-display-tight
                                  flex items-center gap-2">
            <Clock size={16} className="text-accent-magenta" />
            Background tasks ({Object.values(data.background_tasks || {})
                                              .filter((s) => s === "running").length}
            /{Object.keys(data.background_tasks || {}).length} running)
          </h3>
          {showTasks
            ? <ChevronDown size={16} className="text-text-secondary" />
            : <ChevronRight size={16} className="text-text-secondary" />}
        </button>
        {showTasks && (
          <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2"
                  data-testid="admin-health-tasks-grid">
            {Object.entries(data.background_tasks || {}).map(([name, status]) => {
              const cls = status === "running"
                ? "border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-200"
                : status === "not_started"
                ? "border-rose-500/30 bg-rose-500/[0.06] text-rose-200"
                : "border-yellow-500/30 bg-yellow-500/[0.06] text-yellow-200";
              return (
                <li key={name}
                    data-testid={`admin-health-task-${name}`}
                    className={`rounded-token-md border p-2.5 flex
                                    items-center justify-between gap-2 ${cls}`}>
                  <span className="font-mono text-[11px] truncate">{name}</span>
                  <Chip tone={status === "running" ? "emerald" : "danger"}>
                    {status}
                  </Chip>
                </li>
              );
            })}
          </ul>
        )}
      </Card>

      {/* ── 6. Counts (always visible, dense) ────────────── */}
      <Card data-testid="admin-health-counts" className="p-5">
        <h3 className="font-display font-bold text-lg tracking-display-tight
                                flex items-center gap-2 mb-3">
          <ShieldCheck size={16} className="text-accent-electric" />
          Collection sizes
        </h3>
        <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
          {Object.entries(data.counts || {}).map(([k, v]) => (
            <div key={k}
                      data-testid={`admin-health-count-${k}`}
                      className="rounded-token-md bg-white/[0.04] p-2.5">
              <div className="text-[10px] font-mono uppercase tracking-widest
                                      text-text-secondary truncate">{k}</div>
              <div className="font-display font-bold text-xl text-text-primary mt-0.5">
                {Number(v || 0).toLocaleString()}
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
