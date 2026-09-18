// V2 Soft-Launch Admin — premium New Look V2 surfaces for the soft-launch
// program: business Applications, Approved storefronts, Launch-Ready, and a
// Market-Readiness snapshot. Consumes the SHARED admin merchant APIs
// (/api/admin/merchants, /approve, /reject) — no design-specific logic.
import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import {
  ArrowLeft, Rocket, Loader2, Check, X, Store, Clock, CheckCircle2,
  TrendingUp, RefreshCw, ExternalLink, ShieldCheck,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TABS = [
  { key: "all_pending", label: "Applications", Icon: Clock },
  { key: "approved",      label: "Approved",        Icon: CheckCircle2 },
  { key: "launch_ready", label: "Launch Ready", Icon: Rocket },
  { key: "readiness",      label: "Market Readiness", Icon: TrendingUp },
];

export default function AdminSoftLaunch() {
  const [tab, setTab] = useState("all_pending");
  const [rows, setRows] = useState([]);
  const [counts, setCounts] = useState({});
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);

  const load = async () => {
    setLoading(true);
    try {
      // Fetch the buckets we summarise + the active tab's list.
      const [pending, approved] = await Promise.all([
        axios.get(`${API}/admin/merchants`, { params: { status: "all_pending", limit: 100 }, withCredentials: true }),
        axios.get(`${API}/admin/merchants`, { params: { status: "approved", limit: 200 }, withCredentials: true }),
      ]);
      const pendingItems = pending.data.items || [];
      const approvedItems = approved.data.items || [];
      const launchReady = approvedItems.filter(
        (m) => m.stripe_onboarding_status === "complete" || m.effective_status === "active");
      setCounts({
        all_pending: pending.data.total ?? pendingItems.length,
        approved: approved.data.total ?? approvedItems.length,
        launch_ready: launchReady.length,
      });
      if (tab === "all_pending") setRows(pendingItems);
      else if (tab === "approved") setRows(approvedItems);
      else if (tab === "launch_ready") setRows(launchReady);
      else setRows([]);
    } catch (e) {
      toast.error("Couldn't load soft-launch data");
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [tab]);

  const approve = async (m) => {
    setBusyId(m.merchant_id);
    try {
      await axios.post(`${API}/admin/merchants/${m.merchant_id}/approve`, {}, { withCredentials: true });
      toast.success(`Approved ${m.name}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Approve failed");
    } finally { setBusyId(null); }
  };
  const reject = async (m) => {
    const reason = window.prompt(`Reject "${m.name}"? Add a short reason:`, "Incomplete application");
    if (reason == null) return;
    setBusyId(m.merchant_id);
    try {
      await axios.post(`${API}/admin/merchants/${m.merchant_id}/reject`, { reason }, { withCredentials: true });
      toast.success(`Rejected ${m.name}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Reject failed");
    } finally { setBusyId(null); }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white" data-testid="admin-soft-launch-page">
      <div className="max-w-5xl mx-auto p-6 sm:p-8">
        <Link to="/admin" data-testid="admin-soft-launch-back"
                    className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white mb-5">
          <ArrowLeft size={14} /> Admin Home
        </Link>

        <div className="flex items-center justify-between gap-3 flex-wrap mb-6">
          <div className="flex items-center gap-3">
            <span className="w-11 h-11 rounded-2xl grid place-items-center text-white"
                        style={{ background: "linear-gradient(135deg,#A020F0,#EC4899)" }}>
              <Rocket size={20} />
            </span>
            <div>
              <h1 className="text-2xl font-black tracking-tight">Soft Launch</h1>
              <p className="text-sm text-slate-400">Applications · approvals · launch readiness · market snapshot</p>
            </div>
          </div>
          <button onClick={load} disabled={loading} data-testid="admin-soft-launch-refresh"
                        className="inline-flex items-center gap-1.5 px-3 h-9 rounded-full bg-slate-800 text-slate-100 text-xs font-bold hover:bg-slate-700 disabled:opacity-50">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />} Refresh
          </button>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 overflow-x-auto pb-1 mb-6" data-testid="admin-soft-launch-tabs">
          {TABS.map(({ key, label, Icon }) => {
            const active = tab === key;
            const n = counts[key];
            return (
              <button key={key} onClick={() => setTab(key)}
                            data-testid={`admin-soft-launch-tab-${key}`}
                            className={`inline-flex items-center gap-2 px-4 h-10 rounded-full text-sm font-bold whitespace-nowrap border transition-colors ${
                              active ? "border-purple-500 bg-purple-500/15 text-purple-200"
                                        : "border-slate-800 bg-slate-900 text-slate-300 hover:border-slate-700"}`}>
                <Icon size={14} /> {label}
                {typeof n === "number" && key !== "readiness" && (
                  <span className={`ml-1 text-[10px] font-black px-1.5 py-0.5 rounded-full ${
                    active ? "bg-purple-400 text-slate-950" : "bg-slate-800 text-slate-300"}`}>{n}</span>
                )}
              </button>
            );
          })}
        </div>

        {tab === "readiness" ? (
          <MarketReadiness counts={counts} />
        ) : loading ? (
          <div className="py-20 text-center text-slate-400" data-testid="admin-soft-launch-loading">
            <Loader2 size={22} className="animate-spin mx-auto mb-2" /> Loading…
          </div>
        ) : rows.length === 0 ? (
          <div className="py-20 text-center rounded-2xl border border-slate-800 bg-slate-900"
                    data-testid="admin-soft-launch-empty">
            <Store size={26} className="mx-auto mb-3 text-slate-600" />
            <div className="text-sm text-slate-400">Nothing here right now.</div>
          </div>
        ) : (
          <div className="space-y-3" data-testid="admin-soft-launch-list">
            {rows.map((m) => (
              <div key={m.merchant_id} data-testid={`admin-soft-launch-row-${m.merchant_id}`}
                        className="flex items-center gap-4 rounded-2xl border border-slate-800 bg-slate-900 p-4">
                <div className="w-11 h-11 rounded-xl grid place-items-center bg-slate-800 text-slate-300 shrink-0 overflow-hidden">
                  {m.logo_url ? <img src={m.logo_url} alt="" className="w-full h-full object-cover" />
                                        : <Store size={18} />}
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-black text-white truncate">{m.name || "(unnamed)"}</div>
                  <div className="text-[11px] text-slate-400 truncate">
                    {m.owner_email || "—"} · <StatusPill status={m.effective_status || m.merchant_status} />
                  </div>
                </div>
                {tab === "all_pending" ? (
                  <div className="flex items-center gap-2 shrink-0">
                    <button onClick={() => reject(m)} disabled={busyId === m.merchant_id}
                                  data-testid={`admin-soft-launch-reject-${m.merchant_id}`}
                                  className="inline-flex items-center gap-1 px-3 h-9 rounded-full bg-slate-800 text-slate-200 text-xs font-bold hover:bg-slate-700 disabled:opacity-50">
                      <X size={13} /> Reject
                    </button>
                    <button onClick={() => approve(m)} disabled={busyId === m.merchant_id}
                                  data-testid={`admin-soft-launch-approve-${m.merchant_id}`}
                                  className="inline-flex items-center gap-1 px-3 h-9 rounded-full text-slate-950 text-xs font-black hover:opacity-90 disabled:opacity-50"
                                  style={{ background: "linear-gradient(135deg,#10b981,#22c55e)" }}>
                      {busyId === m.merchant_id ? <Loader2 size={13} className="animate-spin" /> : <Check size={13} />} Approve
                    </button>
                  </div>
                ) : (
                  <Link to={`/admin/merchants`} data-testid={`admin-soft-launch-view-${m.merchant_id}`}
                              className="inline-flex items-center gap-1 px-3 h-9 rounded-full bg-slate-800 text-slate-200 text-xs font-bold hover:bg-slate-700 shrink-0">
                    <ExternalLink size={13} /> Manage
                  </Link>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const s = (status || "draft").toLowerCase();
  const tint = s === "active" || s === "approved"
    ? "text-emerald-300"
    : s === "submitted" || s === "verification_pending" ? "text-amber-300"
    : s === "rejected" || s === "suspended" ? "text-rose-300" : "text-slate-400";
  return <span className={`font-bold uppercase tracking-wide ${tint}`}>{s.replace(/_/g, " ")}</span>;
}

function MarketReadiness({ counts }) {
  const pending = counts.all_pending || 0;
  const approved = counts.approved || 0;
  const ready = counts.launch_ready || 0;
  const readyPct = approved > 0 ? Math.round((ready / approved) * 100) : 0;
  const cards = [
    { label: "Pending applications", value: pending, Icon: Clock, tint: "text-amber-300" },
    { label: "Approved storefronts", value: approved, Icon: CheckCircle2, tint: "text-emerald-300" },
    { label: "Launch-ready", value: ready, Icon: Rocket, tint: "text-purple-300" },
  ];
  return (
    <div data-testid="admin-soft-launch-readiness">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-5">
        {cards.map((c) => (
          <div key={c.label} className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-black uppercase tracking-widest text-slate-500">{c.label}</span>
              <c.Icon size={15} className={c.tint} />
            </div>
            <div className={`mt-2 text-3xl font-black tabular-nums ${c.tint}`}>{c.value}</div>
          </div>
        ))}
      </div>
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex items-center gap-2 mb-2">
          <ShieldCheck size={15} className="text-cyan-300" />
          <span className="text-sm font-black">Launch readiness</span>
          <span className="ml-auto text-2xl font-black tabular-nums text-cyan-300"
                      data-testid="admin-soft-launch-readiness-pct">{readyPct}%</span>
        </div>
        <div className="h-2.5 rounded-full bg-slate-800 overflow-hidden">
          <div className="h-full rounded-full" style={{ width: `${readyPct}%`, background: "linear-gradient(90deg,#06b6d4,#8b5cf6)" }} />
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {ready} of {approved} approved storefronts have completed Stripe onboarding and are ready to go live.
        </p>
      </div>
    </div>
  );
}
