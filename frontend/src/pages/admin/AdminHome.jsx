// Phase T — Admin Home dashboard.  Consolidates Phase Q + Phase S +
// recent activity + latest payments + latest advertisers + system-status
// indicator.  Auto-refreshes every 60 s.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Activity, AlertTriangle, ArrowRight, Bell, Building2,
  CheckCircle2, Clock, Loader2, MapPin, Megaphone, RefreshCw,
  Search, ShieldCheck, TrendingUp, Wallet, Zap,
} from "lucide-react";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_STYLES = {
  green: { bg: "bg-emerald-500/15", border: "border-emerald-500/40",
                 text: "text-emerald-400", label: "All systems operational" },
  amber: { bg: "bg-amber-500/15",     border: "border-amber-500/40",
                 text: "text-amber-400",     label: "Attention needed" },
  red:   { bg: "bg-red-500/15",           border: "border-red-500/40",
                 text: "text-red-400",         label: "Critical alerts open" },
};

function fmtUsd(cents) {
  if (cents == null) return "$0.00";
  return `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
function fmtDur(sec) {
  if (sec == null) return "—";
  const d = Math.floor(sec / 86400);
  const h = Math.floor((sec % 86400) / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (d > 0) return `${d}d ${h}h`;
  if (h > 0) return `${h}h ${m}m`;
  return `${m}m ${sec % 60}s`;
}
function fmtRel(ts) {
  if (!ts) return "—";
  const t = new Date(ts).getTime();
  const s = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

export default function AdminHome() {
  const [data, setData]     = useState(null);
  const [busy, setBusy]     = useState(true);
  const [err, setErr]       = useState(null);

  const load = useCallback(async (force = false) => {
    setBusy(true); setErr(null);
    try {
      const q = force ? "?force=true" : "";
      const { data: d } = await axios.get(
        `${API}/admin/home/summary${q}`, { withCredentials: true });
      setData(d);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code
              || e?.response?.data?.detail
              || e.message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => { load(false); }, [load]);
  useEffect(() => {
    const t = setInterval(() => load(false), 60_000);
    return () => clearInterval(t);
  }, [load]);

  const status = STATUS_STYLES[data?.system_status || "green"];

  return (
    <div className="min-h-screen bg-slate-950 text-white"
              data-testid="admin-home-page">
      <div className="max-w-7xl xl:max-w-[1600px] mx-auto p-6 sm:p-8">
        <AdminPageHeader
          title="Admin Home"
          subtitle="Operational snapshot across every phase. Auto-refresh 60 s. Cmd/Ctrl+K to search."
          Icon={ShieldCheck}
          tint="text-purple-500"
          pinLabel="Admin Home"
          actions={
            <>
              <button type="button" onClick={() => load(true)}
                              disabled={busy}
                              data-testid="admin-home-refresh"
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full
                                              bg-purple-500 text-white text-xs font-bold
                                              hover:bg-purple-400 disabled:opacity-50">
                {busy ? <Loader2 className="w-3 h-3 animate-spin" />
                            : <RefreshCw className="w-3 h-3" />}
                Refresh
              </button>
            </>
          } />

        {err && (
          <div className="mb-4 rounded-2xl bg-red-500/10 border border-red-500/30 p-3 text-sm text-red-400"
                    data-testid="admin-home-error">
            {String(err)}
          </div>
        )}

        {/* System status ribbon */}
        <div className={`mb-6 rounded-2xl ${status.bg} border ${status.border} p-3
                                    flex items-center gap-3`}
                  data-testid="admin-home-status-ribbon"
                  data-status={data?.system_status || "loading"}>
          {data?.system_status === "green" ? (
            <CheckCircle2 className={`w-4 h-4 ${status.text}`} />
          ) : (
            <AlertTriangle className={`w-4 h-4 ${status.text}`} />
          )}
          <div className="text-sm">
            <span className={`font-bold ${status.text}`}>System status:</span>{" "}
            <span className="text-slate-300">{status.label}</span>
            {data?.qa_compact?.open_alerts > 0 && (
              <>
                {" · "}
                <Link to="/admin/qa" className="underline text-slate-300 hover:text-white"
                            data-testid="admin-home-open-alerts-link">
                  {data.qa_compact.open_alerts} open alert{data.qa_compact.open_alerts !== 1 ? "s" : ""}
                </Link>
              </>
            )}
          </div>
          <div className="ml-auto text-[10px] font-mono text-slate-500">
            {data?.cached ? "cached · 60 s TTL" : "live"}
            {data?.generated_at && ` · ${fmtRel(data.generated_at)}`}
          </div>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6"
                  data-testid="admin-home-kpis">
          <KpiCard label="UPTIME" value={fmtDur(data?.qa_compact?.uptime_seconds)}
                        Icon={Clock} tint="text-emerald-400"
                        testid="admin-home-kpi-uptime" />
          <KpiCard label="GROSS 30 D"
                        value={fmtUsd(data?.qa_compact?.gross_30d_cents)}
                        Icon={Wallet} tint="text-amber-400"
                        testid="admin-home-kpi-gross" />
          <KpiCard label="ACTIVE CAMPAIGNS"
                        value={data?.qa_compact?.active_campaigns ?? 0}
                        Icon={Activity} tint="text-cyan-400"
                        testid="admin-home-kpi-campaigns" />
          <KpiCard label="OPEN ALERTS"
                        value={data?.qa_compact?.open_alerts ?? 0}
                        Icon={AlertTriangle}
                        tint={(data?.qa_compact?.open_alerts ?? 0)
                                ? "text-red-400" : "text-emerald-400"}
                        testid="admin-home-kpi-alerts" />
        </div>

        {/* 12-col main grid: left 8 = activity, right 4 = snapshots */}
        <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
          <div className="xl:col-span-8 space-y-6">
            <RecentPayments payments={data?.latest_payments || []} />
            <LatestAdvertisers items={data?.latest_advertisers || []} />
            <RecentActions items={data?.recent_actions || []} />
          </div>

          <div className="xl:col-span-4 space-y-6">
            <LocationSnapshot compact={data?.location_compact} />
            <NotificationSnapshot
              count={data?.notification_recipe_count || 0} />
            <QuickLinks />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Sub-components ─────────────────────────────────────

function KpiCard({ label, value, Icon, tint, testid }) {
  return (
    <div className="rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950
                              border border-slate-800 p-4"
              data-testid={testid}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
          {label}
        </div>
        <Icon className={`w-4 h-4 ${tint || "text-slate-400"}`} />
      </div>
      <div className="text-2xl xl:text-3xl font-black tabular-nums truncate">
        {value}
      </div>
    </div>
  );
}

function Section({ title, Icon, viewAllTo, viewAllTestid,
                            testid, children }) {
  return (
    <section className="rounded-2xl bg-slate-900/60 border border-slate-800 p-4"
                    data-testid={testid}>
      <div className="flex items-center gap-2 mb-3">
        <Icon className="w-4 h-4 text-purple-500" />
        <h2 className="text-[10px] font-mono uppercase tracking-widest font-bold text-slate-500">
          {title}
        </h2>
        {viewAllTo && (
          <Link to={viewAllTo}
                      data-testid={viewAllTestid}
                      className="ml-auto text-[10px] font-mono text-slate-500 hover:text-slate-300 inline-flex items-center gap-1">
            View all <ArrowRight className="w-3 h-3" />
          </Link>
        )}
      </div>
      {children}
    </section>
  );
}

function RecentPayments({ payments }) {
  return (
    <Section title="Latest payments" Icon={Wallet}
                    viewAllTo="/admin/revenue/live"
                    viewAllTestid="admin-home-payments-viewall"
                    testid="admin-home-payments">
      {payments.length === 0 ? (
        <div className="text-xs text-slate-500">No payments yet.</div>
      ) : (
        <div className="space-y-2">
          {payments.map((p) => (
            <div key={p.transaction_id || p.succeeded_at}
                      data-testid={`admin-home-payment-${p.transaction_id}`}
                      className="flex items-center gap-3 text-xs border-t border-slate-800/60 pt-2 first:border-0 first:pt-0">
              <span className="tabular-nums text-amber-400 font-bold w-20 shrink-0">
                {fmtUsd(p.amount_cents)}
              </span>
              <span className="text-slate-300 font-mono truncate">{p.flow}</span>
              <span className="text-slate-500 truncate">
                {p.advertiser_id || p.merchant_id || "—"}
              </span>
              <span className="ml-auto text-[10px] font-mono text-slate-500 shrink-0">
                {fmtRel(p.succeeded_at)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function LatestAdvertisers({ items }) {
  return (
    <Section title="New advertisers" Icon={Megaphone}
                    viewAllTo="/admin/advertisers"
                    viewAllTestid="admin-home-advertisers-viewall"
                    testid="admin-home-advertisers">
      {items.length === 0 ? (
        <div className="text-xs text-slate-500">No signups.</div>
      ) : (
        <div className="space-y-2">
          {items.map((a) => (
            <div key={a.advertiser_id}
                      data-testid={`admin-home-adv-${a.advertiser_id}`}
                      className="flex items-center gap-3 text-xs border-t border-slate-800/60 pt-2 first:border-0 first:pt-0">
              <Building2 className="w-3 h-3 text-slate-500 shrink-0" />
              <span className="font-medium truncate flex-1">
                {a.name || a.advertiser_id}
              </span>
              <span className="text-[10px] font-mono text-slate-500">
                {a.market || "—"}
              </span>
              <span className={`text-[10px] font-mono uppercase tracking-widest ${
                  a.status === "active" ? "text-emerald-400" : "text-slate-500"}`}>
                {a.status || "—"}
              </span>
              <span className="ml-auto text-[10px] font-mono text-slate-500 shrink-0">
                {fmtRel(a.created_at)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function RecentActions({ items }) {
  return (
    <Section title="Recent admin actions" Icon={Activity}
                    viewAllTo="/admin/users/audit-log"
                    viewAllTestid="admin-home-actions-viewall"
                    testid="admin-home-actions">
      {items.length === 0 ? (
        <div className="text-xs text-slate-500">
          No recent actions on record.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((r, i) => (
            <div key={i}
                      data-testid={`admin-home-action-${i}`}
                      className="flex items-center gap-3 text-xs border-t border-slate-800/60 pt-2 first:border-0 first:pt-0">
              <span className="text-slate-300 font-mono truncate flex-1">
                {r.event}
              </span>
              <span className="text-slate-500 truncate">{r.target || "—"}</span>
              <span className="ml-auto text-[10px] font-mono text-slate-500 shrink-0">
                {fmtRel(r.created_at)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

function LocationSnapshot({ compact }) {
  return (
    <Section title="Location intel" Icon={MapPin}
                    viewAllTo="/admin/location-intel"
                    viewAllTestid="admin-home-locintel-viewall"
                    testid="admin-home-locintel">
      <div className="grid grid-cols-2 gap-2 text-xs">
        <MiniStat label="Total pings" value={compact?.total_pings ?? 0}
                        tint="text-cyan-400" />
        <MiniStat label="Unique users" value={compact?.unique_users ?? 0}
                        tint="text-emerald-400" />
        <MiniStat label="Top city" value={compact?.top_city || "—"}
                        tint="text-fuchsia-400" />
        <MiniStat label="Peak hour"
                        value={compact?.most_active_hour != null
                                  ? `${String(compact.most_active_hour).padStart(2, "0")}:00`
                                  : "—"}
                        tint="text-purple-400" />
      </div>
    </Section>
  );
}

function NotificationSnapshot({ count }) {
  return (
    <Section title="Notification recipes" Icon={Bell}
                    viewAllTo="/admin/campaigns/queue"
                    viewAllTestid="admin-home-recipes-viewall"
                    testid="admin-home-recipes">
      <div className="flex items-baseline gap-2">
        <div className="text-3xl font-black tabular-nums text-purple-400"
                  data-testid="admin-home-recipes-count">
          {count}
        </div>
        <div className="text-xs text-slate-500">recipes registered</div>
      </div>
    </Section>
  );
}

function QuickLinks() {
  const links = [
    { to: "/admin/qa",                        label: "QA Dashboard",       tid: "admin-home-ql-qa" },
    { to: "/admin/location-intel",      label: "Location Intel",       tid: "admin-home-ql-locintel" },
    { to: "/admin/news",                      label: "News Radio",            tid: "admin-home-ql-news" },
    { to: "/admin/flagship-boosts",  label: "Flagship Boosts",      tid: "admin-home-ql-flagship" },
    { to: "/admin/coupon-charges",    label: "Coupon Charges",      tid: "admin-home-ql-coupons" },
    { to: "/admin/retargeting",          label: "Retargeting",            tid: "admin-home-ql-retargeting" },
  ];
  return (
    <Section title="Quick links" Icon={Zap} testid="admin-home-quicklinks">
      <div className="grid grid-cols-2 gap-2">
        {links.map((l) => (
          <Link key={l.to} to={l.to}
                      data-testid={l.tid}
                      className="text-xs text-slate-300 hover:text-white
                                        px-3 py-2 rounded-lg bg-slate-950/60 border border-slate-800
                                        hover:border-purple-500/50 truncate inline-flex items-center justify-between gap-1">
            {l.label} <ArrowRight className="w-3 h-3 text-slate-500" />
          </Link>
        ))}
      </div>
    </Section>
  );
}

function MiniStat({ label, value, tint }) {
  return (
    <div className="rounded-xl bg-slate-950/60 border border-slate-800 px-3 py-2">
      <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className={`text-lg font-black tabular-nums truncate ${tint}`}>
        {value}
      </div>
    </div>
  );
}
