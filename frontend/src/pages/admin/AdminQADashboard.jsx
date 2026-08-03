// Phase Q — QA Dashboard admin page (legacy dark theme).
// Consolidates system health + data quality + recent activity + revenue
// across every shipped phase.  Auto-refreshes every 30 s.
//
// URL: /admin/qa   (admin only — the endpoints 403 non-admin).
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, RefreshCw, AlertTriangle, ShieldCheck, Activity, Clock,
  Wallet, TrendingUp, ChevronDown, ChevronRight, XCircle, CheckCircle2,
  Zap, ArrowLeft,
} from "lucide-react";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const SEVERITY_STYLES = {
  critical: { bg: "bg-red-500/15",    border: "border-red-500/40",   text: "text-red-400" },
  warn:     { bg: "bg-amber-500/15",  border: "border-amber-500/40", text: "text-amber-400" },
  info:     { bg: "bg-blue-500/15",   border: "border-blue-500/40",  text: "text-blue-400" },
};

function fmtDur(sec) {
  if (sec == null) return "—";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
function fmtUsd(cents) {
  if (cents == null) return "$0.00";
  return `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function AdminQADashboard() {
  const [data, setData] = useState(null);
  const [err, setErr]   = useState(null);
  const [busy, setBusy] = useState(false);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastFetchedAt, setLastFetchedAt] = useState(null);

  const load = useCallback(async (force = false) => {
    setErr(null);
    try {
      const url = force
        ? `${API}/admin/qa/refresh`
        : `${API}/admin/qa/summary`;
      const method = force ? "post" : "get";
      const { data: d } = await axios({
        method, url, withCredentials: true });
      setData(d);
      setLastFetchedAt(new Date());
    } catch (e) {
      setErr(e?.response?.data?.detail?.code
              || e?.response?.data?.detail
              || e.message);
    }
  }, []);

  useEffect(() => { load(false); }, [load]);
  useEffect(() => {
    if (!autoRefresh) return;
    const t = setInterval(() => load(false), 30_000);
    return () => clearInterval(t);
  }, [autoRefresh, load]);

  const onRefresh = async () => {
    setBusy(true);
    try { await load(true); }
    finally { setBusy(false); }
  };

  if (!data && !err) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8 flex items-center justify-center"
           data-testid="admin-qa-loading">
        <Loader2 className="w-6 h-6 animate-spin text-purple-500" />
      </div>
    );
  }
  if (err) {
    return (
      <div className="min-h-screen bg-slate-950 text-white p-8 flex items-center justify-center"
           data-testid="admin-qa-error">
        <div className="text-center">
          <AlertTriangle className="w-10 h-10 text-red-500 mx-auto" />
          <div className="mt-3 font-bold text-lg">QA dashboard unavailable</div>
          <div className="mt-1 text-sm text-slate-400">{String(err)}</div>
          <button onClick={() => load(false)}
                  data-testid="admin-qa-retry"
                  className="mt-4 px-4 py-2 rounded-full bg-purple-500 text-white text-sm font-bold hover:bg-purple-400">
            Retry
          </button>
        </div>
      </div>
    );
  }

  const sys = data.system_health || {};
  const dq  = data.data_quality || {};
  const ra  = data.recent_activity || {};
  const rev = data.revenue_summary || {};
  const alerts = data.open_alerts || [];
  const activeCampaigns = (dq.per_collection || []).reduce(
    (n, c) => n + (c.active || 0), 0);

  return (
    <div className="min-h-screen bg-slate-950 text-white"
         data-testid="admin-qa-page">
      <div className="max-w-7xl xl:max-w-[1600px] mx-auto p-6 sm:p-8">
        <AdminPageHeader
          title="QA Dashboard"
          subtitle={`Real-time system health · data quality · revenue.  Cache 30 s.  Auto-refresh: ${autoRefresh ? "ON" : "OFF"}${lastFetchedAt ? ` · Last fetched ${lastFetchedAt.toLocaleTimeString()}` : ""}${data.cached ? " · (served from cache)" : ""}`}
          Icon={ShieldCheck}
          tint="text-purple-500"
          pinLabel="QA Dashboard"
          breadcrumbs={[{ label: "Home & Analytics" },
                                          { label: "QA Dashboard" }]}
          actions={
            <>
              <label className="inline-flex items-center gap-1.5 text-xs text-slate-400 cursor-pointer"
                              data-testid="admin-qa-autorefresh-toggle">
                <input type="checkbox" checked={autoRefresh}
                              onChange={(e) => setAutoRefresh(e.target.checked)}
                              data-testid="admin-qa-autorefresh-checkbox" />
                Auto (30 s)
              </label>
              <button onClick={onRefresh} disabled={busy}
                              data-testid="admin-qa-refresh"
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
                                                bg-purple-500 text-white text-xs font-bold
                                                hover:bg-purple-400 disabled:opacity-50">
                {busy ? <Loader2 className="w-3 h-3 animate-spin" />
                            : <RefreshCw className="w-3 h-3" />}
                Refresh
              </button>
            </>
          } />

        {/* Hero cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4 mb-6"
             data-testid="admin-qa-hero-row">
          <HeroCard label="UPTIME"          value={fmtDur(sys.uptime_seconds)}
                    Icon={Clock}       tint="text-emerald-400"
                    testid="admin-qa-hero-uptime" />
          <HeroCard label="GROSS 30 D"      value={fmtUsd(rev.last_30d?.gross_cents)}
                    Icon={Wallet}      tint="text-amber-400"
                    testid="admin-qa-hero-revenue" />
          <HeroCard label="ACTIVE CAMPAIGNS" value={activeCampaigns}
                    Icon={Activity}    tint="text-cyan-400"
                    testid="admin-qa-hero-active" />
          <HeroCard label="OPEN ALERTS"      value={alerts.length}
                    Icon={AlertTriangle}
                    tint={alerts.length ? "text-red-400" : "text-emerald-400"}
                    testid="admin-qa-hero-alerts" />
        </div>

        {/* System health */}
        <section className="mb-6" data-testid="admin-qa-system-health">
          <SectionHeader title="System Health" Icon={ShieldCheck} />
          <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-3">
            <MiniStat label="DB ping"      value={`${sys.db_ping_ms ?? "—"} ms`} />
            <MiniStat label="WS sessions"  value={sys.active_websocket_sessions ?? 0} />
            <MiniStat label="Env"          value={sys.env || "unset"} />
            <MiniStat label="Stripe"       value={sys.stripe_mode || "—"}
                       tint={sys.stripe_mode === "live" ? "text-emerald-400"
                                                        : "text-amber-400"} />
            <IntegPill label="Emergent LLM"    ok={sys.emergent_llm_configured} />
            <IntegPill label="ElevenLabs"      ok={sys.elevenlabs_configured} />
            <IntegPill label="Tigris"          ok={sys.tigris_configured} />
            <IntegPill label="Google Maps"    ok={sys.google_maps_configured} />
            <IntegPill label="OpenAI (raw)"   ok={sys.openai_configured} />
          </div>
          <div className="mt-3 rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
               data-testid="admin-qa-bgtasks">
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">
              Background tasks
            </div>
            <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-2">
              {(sys.background_tasks_status || []).map((t) => (
                <div key={t.task_name}
                     data-testid={`admin-qa-bg-${t.task_name}`}
                     className="flex items-center gap-2 text-xs">
                  <span className={`w-2 h-2 rounded-full ${
                      t.status === "healthy"  ? "bg-emerald-500"
                    : t.status === "completed" ? "bg-slate-400"
                    : t.status === "crashed"  ? "bg-red-500"
                    : "bg-slate-600"}`} />
                  <span className="font-mono text-slate-400">{t.task_name}</span>
                  <span className={`ml-auto text-[10px] uppercase tracking-widest ${
                      t.status === "healthy"  ? "text-emerald-400"
                    : t.status === "completed" ? "text-slate-500"
                    : t.status === "crashed"  ? "text-red-400"
                    : "text-slate-500"}`}>
                    {t.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Split row: Data quality (left) + Recent activity (right) */}
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-6 mb-6">
          {/* Data quality + open alerts */}
          <section data-testid="admin-qa-data-quality">
            <SectionHeader title="Data Quality — Open Alerts" Icon={AlertTriangle} />
            {alerts.length === 0 ? (
              <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-8 text-center"
                   data-testid="admin-qa-alerts-empty">
                <CheckCircle2 className="w-8 h-8 text-emerald-500 mx-auto" />
                <div className="mt-2 font-bold">All clear.</div>
                <div className="text-xs text-slate-400 mt-1">
                  No open alerts.  Sweepers on track.
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                {alerts.map((a) => (
                  <AlertRow key={a.alert_type} alert={a}
                            onDismissed={() => load(true)} />
                ))}
              </div>
            )}

            {/* Per-collection counts */}
            <div className="mt-4 rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
                 data-testid="admin-qa-per-collection">
              <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3">
                Per-collection counts
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                      <th className="text-left py-1.5 pr-2">Collection</th>
                      <th className="text-right py-1.5 px-2">Total</th>
                      <th className="text-right py-1.5 px-2">Active</th>
                      <th className="text-right py-1.5 px-2">Paused</th>
                      <th className="text-right py-1.5 pl-2">Completed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(dq.per_collection || []).map((r) => (
                      <tr key={r.collection} className="border-t border-slate-800"
                          data-testid={`admin-qa-pc-${r.collection}`}>
                        <td className="py-1.5 pr-2">
                          <div className="font-mono text-slate-400">{r.collection}</div>
                          <div className="text-[10px] text-slate-500">{r.phase}</div>
                        </td>
                        <td className="text-right px-2 tabular-nums">{r.total}</td>
                        <td className="text-right px-2 tabular-nums text-emerald-400">{r.active}</td>
                        <td className="text-right px-2 tabular-nums text-amber-400">{r.paused}</td>
                        <td className="text-right pl-2 tabular-nums text-slate-500">{r.completed}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </section>

          {/* Recent activity */}
          <section data-testid="admin-qa-recent-activity">
            <SectionHeader title="Recent Activity — Last 24 h" Icon={Zap} />
            <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4 space-y-2 text-sm">
              <ActivityRow label="New user signups"        value={ra.new_user_signups_24h} testid="admin-qa-ra-signups" />
              <ActivityRow label="New advertiser signups"  value={ra.new_advertiser_signups_24h} testid="admin-qa-ra-adv-signups" />
              <ActivityRow label="Payments succeeded"
                           value={`${ra.payments_24h?.count ?? 0} · ${fmtUsd(ra.payments_24h?.sum_cents)}`}
                           testid="admin-qa-ra-payments" />
              <ActivityRow label="Refunds"
                           value={`${ra.refunds_24h?.count ?? 0} · ${fmtUsd(ra.refunds_24h?.sum_cents)}`}
                           testid="admin-qa-ra-refunds"
                           tint={ra.refunds_24h?.count ? "text-amber-400" : "text-slate-400"} />
              <ActivityRow label="Podcast completions"      value={ra.podcast_completions_24h} testid="admin-qa-ra-podcast" />
              <ActivityRow label="Trivia rooms completed"  value={ra.trivia_rooms_completed_24h} testid="admin-qa-ra-trivia" />
              <ActivityRow label="Scan-to-pay transactions" value={ra.scan_to_pay_txns_24h} testid="admin-qa-ra-scan" />
              <ActivityRow label="Marketplace saves"        value={ra.marketplace_saves_24h} testid="admin-qa-ra-marketplace" />
              <ActivityRow label="Retargeting impressions"  value={ra.retargeting_impressions_24h} testid="admin-qa-ra-retargeting" />
            </div>

            {(ra.campaigns_activated_24h || []).length > 0 && (
              <div className="mt-3 rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
                   data-testid="admin-qa-ra-campaigns">
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">
                  Campaigns touched (24 h)
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-1.5 text-xs">
                  {ra.campaigns_activated_24h.map((c) => (
                    <div key={c.collection} className="flex items-center justify-between gap-2"
                         data-testid={`admin-qa-ra-camp-${c.collection}`}>
                      <span className="text-slate-400 truncate">{c.phase}</span>
                      <span className="tabular-nums text-emerald-400 font-bold">{c.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(ra.notifications_top10_24h || []).length > 0 && (
              <div className="mt-3 rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
                   data-testid="admin-qa-ra-notifs">
                <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">
                  Top notification recipes fired (24 h)
                </div>
                <div className="space-y-1 text-xs">
                  {ra.notifications_top10_24h.map((n) => (
                    <div key={n.recipe_id} className="flex items-center justify-between">
                      <span className="font-mono text-slate-400 truncate">{n.recipe_id}</span>
                      <span className="tabular-nums text-cyan-400 font-bold">{n.count}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </section>
        </div>

        {/* Revenue */}
        <section className="mb-6" data-testid="admin-qa-revenue">
          <SectionHeader title="Revenue Summary" Icon={TrendingUp} />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mb-4">
            <RevenueCard label="ALL TIME · GROSS"        value={fmtUsd(rev.all_time?.gross_cents)}
                          sub={`${rev.all_time?.count ?? 0} txns · platform ${fmtUsd(rev.all_time?.platform_cents)}`}
                          testid="admin-qa-rev-alltime" />
            <RevenueCard label="LAST 30 D · GROSS"        value={fmtUsd(rev.last_30d?.gross_cents)}
                          sub={`${rev.last_30d?.count ?? 0} txns · platform ${fmtUsd(rev.last_30d?.platform_cents)}`}
                          testid="admin-qa-rev-30d" />
          </div>
          <RevenueByPhaseChart rows={rev.revenue_by_phase || []} />
          <div className="mt-4 rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
               data-testid="admin-qa-top-advertisers">
            <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-2">
              Top 5 advertisers by 30 d spend
            </div>
            {(rev.top_advertisers_30d || []).length === 0 ? (
              <div className="text-xs text-slate-500">No spend recorded in the last 30 days.</div>
            ) : (
              <div className="space-y-1.5 text-sm">
                {rev.top_advertisers_30d.map((a) => (
                  <div key={a.advertiser_id}
                       className="flex items-center justify-between gap-3"
                       data-testid={`admin-qa-top-adv-${a.advertiser_id}`}>
                    <div>
                      <div className="font-medium">{a.display_name}</div>
                      <div className="text-[10px] font-mono text-slate-500">
                        {a.advertiser_id} · {a.txn_count} txn
                      </div>
                    </div>
                    <div className="tabular-nums text-amber-400 font-bold">
                      {fmtUsd(a.spend_cents)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

// ── Sub-components ──────────────────────────────────────────────

function SectionHeader({ title, Icon }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <Icon className="w-4 h-4 text-purple-500" />
      <h2 className="text-sm md:text-base font-bold uppercase tracking-widest font-mono
                        text-slate-300">
        {title}
      </h2>
    </div>
  );
}

function HeroCard({ label, value, Icon, tint, testid }) {
  return (
    <div className="rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950
                        border border-slate-800 p-5"
         data-testid={testid}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
          {label}
        </div>
        <Icon className={`w-5 h-5 ${tint || "text-slate-400"}`} />
      </div>
      <div className="text-3xl xl:text-4xl font-black tabular-nums">
        {value}
      </div>
    </div>
  );
}

function MiniStat({ label, value, tint }) {
  return (
    <div className="rounded-xl bg-slate-900/60 border border-slate-800 px-3 py-2">
      <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className={`text-sm font-bold tabular-nums ${tint || ""}`}>
        {value}
      </div>
    </div>
  );
}

function IntegPill({ label, ok }) {
  return (
    <div className={`rounded-xl border px-3 py-2 ${
        ok ? "bg-emerald-500/10 border-emerald-500/30"
           : "bg-red-500/10 border-red-500/30"}`}
         data-testid={`admin-qa-integ-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
      <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className={`text-xs font-bold ${ok ? "text-emerald-400" : "text-red-400"}`}>
        {ok ? "OK" : "MISSING"}
      </div>
    </div>
  );
}

function ActivityRow({ label, value, testid, tint }) {
  return (
    <div className="flex items-center justify-between gap-2 border-b border-slate-800/70
                         pb-1.5 last:border-0 last:pb-0"
         data-testid={testid}>
      <span className="text-slate-400">{label}</span>
      <span className={`tabular-nums font-bold ${tint || "text-slate-100"}`}>
        {value ?? 0}
      </span>
    </div>
  );
}

function RevenueCard({ label, value, sub, testid }) {
  return (
    <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
         data-testid={testid}>
      <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className="text-2xl xl:text-3xl font-black tabular-nums text-amber-400 mt-1">
        {value}
      </div>
      <div className="text-xs text-slate-500 mt-1">{sub}</div>
    </div>
  );
}

function RevenueByPhaseChart({ rows }) {
  if (!rows.length) {
    return (
      <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-6 text-xs text-slate-500 text-center"
           data-testid="admin-qa-rev-by-phase-empty">
        No revenue yet.
      </div>
    );
  }
  const max = rows.reduce((n, r) => Math.max(n, r.gross_cents || 0), 1);
  return (
    <div className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
         data-testid="admin-qa-rev-by-phase">
      <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500 mb-3">
        Revenue by phase (all time)
      </div>
      <div className="space-y-1.5">
        {rows.map((r) => {
          const pct = Math.max(2, Math.round((r.gross_cents / max) * 100));
          return (
            <div key={r.flow} className="text-xs"
                 data-testid={`admin-qa-rev-bar-${r.flow}`}>
              <div className="flex items-center justify-between gap-2 mb-0.5">
                <span className="text-slate-400 truncate">{r.phase}</span>
                <span className="tabular-nums text-amber-400 font-bold">
                  {fmtUsd(r.gross_cents)}
                </span>
              </div>
              <div className="h-2 rounded-full bg-slate-800 overflow-hidden">
                <div className="h-full bg-gradient-to-r from-amber-500 to-fuchsia-500 transition-all"
                     style={{ width: `${pct}%` }} />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function AlertRow({ alert, onDismissed }) {
  const [open, setOpen]   = useState(false);
  const [rows, setRows]   = useState(null);
  const [err, setErr]     = useState(null);
  const [busy, setBusy]   = useState(false);
  const style = SEVERITY_STYLES[alert.severity] || SEVERITY_STYLES.info;

  const loadDetails = async () => {
    setErr(null);
    setRows(null);
    try {
      const { data } = await axios.get(
        `${API}/admin/qa/alert/${encodeURIComponent(alert.alert_type)}/details?limit=25`,
        { withCredentials: true });
      setRows(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
              || e?.response?.data?.detail
              || e.message);
    }
  };

  const toggle = () => {
    const next = !open;
    setOpen(next);
    if (next && rows === null) loadDetails();
  };

  const dismiss = async () => {
    setBusy(true);
    try {
      await axios.post(
        `${API}/admin/qa/alerts/${encodeURIComponent(alert.alert_type)}/dismiss`,
        { hours: 24 }, { withCredentials: true });
      onDismissed && onDismissed();
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`rounded-2xl ${style.bg} border ${style.border} p-3`}
         data-testid={`admin-qa-alert-${alert.alert_type}`}>
      <div className="flex items-center gap-3">
        <button type="button" onClick={toggle}
                data-testid={`admin-qa-alert-expand-${alert.alert_type}`}
                className="text-slate-300 hover:text-white transition-colors">
          {open ? <ChevronDown className="w-4 h-4" />
                : <ChevronRight className="w-4 h-4" />}
        </button>
        <span className={`text-[10px] font-mono uppercase tracking-widest font-bold ${style.text}`}>
          {alert.severity}
        </span>
        <span className="tabular-nums font-black text-white">{alert.count}</span>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium truncate">{alert.message}</div>
          <div className="text-[10px] font-mono text-slate-500 truncate"
               data-testid={`admin-qa-alert-type-${alert.alert_type}`}>
            {alert.alert_type}
          </div>
        </div>
        <button type="button" onClick={dismiss} disabled={busy}
                data-testid={`admin-qa-alert-dismiss-${alert.alert_type}`}
                className="text-xs px-3 py-1 rounded-full bg-slate-800 hover:bg-slate-700
                                text-slate-300 disabled:opacity-50 inline-flex items-center gap-1">
          {busy ? <Loader2 className="w-3 h-3 animate-spin" />
                : <XCircle className="w-3 h-3" />}
          Dismiss 24 h
        </button>
      </div>
      {open && (
        <div className="mt-3 rounded-xl bg-slate-900/80 border border-slate-800 p-3"
             data-testid={`admin-qa-alert-details-${alert.alert_type}`}>
          {err ? (
            <div className="text-xs text-red-400">Failed to load: {String(err)}</div>
          ) : rows === null ? (
            <div className="text-xs text-slate-500 inline-flex items-center gap-2">
              <Loader2 className="w-3 h-3 animate-spin" /> Loading records…
            </div>
          ) : rows.length === 0 ? (
            <div className="text-xs text-slate-500">No records (may have cleared).</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px] font-mono">
                <thead>
                  <tr className="text-slate-500 text-[10px] uppercase tracking-widest">
                    {Object.keys(rows[0]).map((k) => (
                      <th key={k} className="text-left py-1 pr-2">{k}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className="border-t border-slate-800/70"
                        data-testid={`admin-qa-alert-row-${alert.alert_type}-${i}`}>
                      {Object.keys(rows[0]).map((k) => (
                        <td key={k} className="py-1 pr-2 text-slate-300 whitespace-nowrap">
                          {String(r[k] ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
