// Phase ADMOD.1 — Ad Review page (Admin + Ad Manager)
// Route: /admin/ad-review
// Four tabs: Queue · Analytics · Blocked Advertisers · Audit Log.
import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  ShieldCheck, AlertTriangle, CheckCircle2, XCircle, RotateCw,
  Sparkles, TrendingUp, Ban, ClipboardList, Loader2, Search,
  ChevronRight, RefreshCw, Users,
} from "lucide-react";
import AdReviewDetailModal from "./AdReviewDetailModal";
import { useEffectivePageVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const AD_TYPE_LABELS = {
  advertiser_campaign:          "Advertiser Campaign",
  coupon_campaign:                "Coupon (AD.4)",
  banner:                              "Banner (AD.11)",
  notification:                    "Notification (AD.12)",
  preroll_audio:                  "Preroll Audio",
  sponsored_game:                "Sponsored Game",
  sponsored_predict_win:  "Sponsored Predict & Win",
  sponsored_trivia:              "Sponsored Trivia",
};

const STATUS_STYLES = {
  pending:                    "bg-amber-500/15 text-amber-400 border border-amber-500/30",
  approved:                  "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30",
  rejected:                  "bg-red-500/15 text-red-400 border border-red-500/30",
  requires_changes:  "bg-blue-500/15 text-blue-400 border border-blue-500/30",
};

const fmtDt = (s) => (s ? new Date(s).toLocaleString() : "—");

export default function AdReview() {
  const variant = useEffectivePageVariant();
  const light = variant === "radiolife";
  const [tab, setTab] = useState("queue");
  const bg = light ? "bg-white text-slate-900" : "bg-slate-950 text-white";
  const muted = light ? "text-slate-500" : "text-slate-400";

  return (
    <div className={`${bg} min-h-screen`} data-testid="ad-review-page">
      <div className="max-w-6xl mx-auto px-4 py-8">
        <div className="flex items-center justify-between flex-wrap gap-3 mb-6">
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              Phase ADMOD.1 · Ad Manager
            </div>
            <h1 className="text-3xl font-black inline-flex items-center gap-2 mt-1">
              <ShieldCheck className="w-7 h-7 text-amber-500" />
              Ad Review
            </h1>
            <p className={`text-sm mt-1 ${muted}`}>
              Unified queue for advertiser creatives across all ad types.
              Approve, reject, request changes, block advertisers.
            </p>
          </div>
        </div>

        <div className="flex flex-wrap gap-2 mb-6">
          {[
            {k: "queue",        label: "Queue",                          icon: ClipboardList},
            {k: "analytics", label: "Analytics",                  icon: TrendingUp},
            {k: "blocked",    label: "Blocked Advertisers",  icon: Ban},
            {k: "audit",        label: "Audit Log",                  icon: Users},
          ].map((t) => (
            <button key={t.k} onClick={() => setTab(t.k)}
                            data-testid={`ad-review-tab-${t.k}`}
                            className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-black transition ${
                                                    tab === t.k
                                                        ? "bg-amber-500 text-slate-900 shadow-lg shadow-amber-500/25"
                                                        : (light ? "bg-slate-100 text-slate-600 hover:bg-slate-200"
                                                                                : "bg-slate-800 text-slate-400 hover:bg-slate-700")}`}>
              <t.icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>

        {tab === "queue"        && <QueueTab light={light} muted={muted} />}
        {tab === "analytics" && <AnalyticsTab light={light} muted={muted} />}
        {tab === "blocked"    && <BlockedTab light={light} muted={muted} />}
        {tab === "audit"        && <AuditTab light={light} muted={muted} />}
      </div>
    </div>
  );
}


// ─── Queue Tab ────────────────────────────────────────────────────────
function QueueTab({ light, muted }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("pending");
  const [adTypeFilter, setAdTypeFilter] = useState("");
  const [flaggedOnly, setFlaggedOnly] = useState(false);
  const [selected, setSelected] = useState({});
  const [openReview, setOpenReview] = useState(null);
  const [toast, setToast] = useState(null);

  const showToast = (kind, msg) => {
    setToast({ kind, msg });
    setTimeout(() => setToast(null), 3500);
  };

  async function load() {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set("status", statusFilter);
      if (adTypeFilter) params.set("ad_type", adTypeFilter);
      if (flaggedOnly)  params.set("flagged_only", "true");
      const { data } = await axios.get(`${API}/ad-review/queue?${params}`,
                                                                                      { withCredentials: true });
      setItems(data.items || []);
      setError(null);
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
    } finally { setLoading(false); }
  }
  useEffect(() => { load(); },
                        [statusFilter, adTypeFilter, flaggedOnly]);

  async function bulk(action) {
    const ids = Object.keys(selected).filter((k) => selected[k]);
    if (ids.length === 0) return;
    try {
      if (action === "approve") {
        await axios.post(`${API}/ad-review/queue/bulk-approve`,
                                                { review_ids: ids }, { withCredentials: true });
        showToast("success", `Bulk-approved ${ids.length} row(s).`);
      } else if (action === "reject") {
        const reason = window.prompt("Reject reason (required)?");
        if (!reason) return;
        await axios.post(`${API}/ad-review/queue/bulk-reject`,
                                                { review_ids: ids, reason }, { withCredentials: true });
        showToast("success", `Bulk-rejected ${ids.length} row(s).`);
      }
      setSelected({});
      load();
    } catch (err) {
      showToast("error", err?.response?.data?.detail?.code || err.message);
    }
  }

  const cardCls = light ? "bg-white border border-slate-200"
                                              : "bg-slate-900/60 border border-slate-800";
  const selectedCount = useMemo(
    () => Object.values(selected).filter(Boolean).length, [selected]);

  return (
    <div className="space-y-4">
      {/* Filters + bulk action bar */}
      <div className={`${cardCls} rounded-2xl p-4 flex items-center gap-3 flex-wrap`}>
        <div className="flex items-center gap-2">
          <label className="text-xs font-bold uppercase tracking-wider opacity-70">Status</label>
          <select value={statusFilter}
                          onChange={(e) => setStatusFilter(e.target.value)}
                          data-testid="ad-review-filter-status"
                          className={`text-sm rounded-md px-2 py-1 ${light ? "bg-white border border-slate-300" : "bg-slate-800 border border-slate-700"}`}>
            <option value="pending">Pending</option>
            <option value="requires_changes">Requires Changes</option>
            <option value="approved">Approved</option>
            <option value="rejected">Rejected</option>
            <option value="all">All</option>
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-bold uppercase tracking-wider opacity-70">Type</label>
          <select value={adTypeFilter}
                          onChange={(e) => setAdTypeFilter(e.target.value)}
                          data-testid="ad-review-filter-type"
                          className={`text-sm rounded-md px-2 py-1 ${light ? "bg-white border border-slate-300" : "bg-slate-800 border border-slate-700"}`}>
            <option value="">All types</option>
            {Object.entries(AD_TYPE_LABELS).map(([v, l]) => (
              <option key={v} value={v}>{l}</option>
            ))}
          </select>
        </div>
        <label className="text-sm inline-flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={flaggedOnly}
                        onChange={(e) => setFlaggedOnly(e.target.checked)}
                        data-testid="ad-review-filter-flagged" />
          <Sparkles className="w-3.5 h-3.5 text-amber-500" /> AI-flagged only
        </label>
        <button onClick={load}
                        data-testid="ad-review-refresh"
                        className={`ml-auto inline-flex items-center gap-1 text-xs font-bold px-3 py-1.5 rounded-full ${light ? "bg-slate-100 hover:bg-slate-200" : "bg-slate-800 hover:bg-slate-700"}`}>
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
        {selectedCount > 0 && (
          <>
            <span className="text-xs opacity-70">{selectedCount} selected</span>
            <button onClick={() => bulk("approve")}
                            data-testid="ad-review-bulk-approve"
                            className="inline-flex items-center gap-1 text-xs font-black px-3 py-1.5 rounded-full bg-emerald-500 text-slate-900 hover:bg-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" /> Bulk approve
            </button>
            <button onClick={() => bulk("reject")}
                            data-testid="ad-review-bulk-reject"
                            className="inline-flex items-center gap-1 text-xs font-black px-3 py-1.5 rounded-full bg-red-500 text-white hover:bg-red-400">
              <XCircle className="w-3.5 h-3.5" /> Bulk reject
            </button>
          </>
        )}
      </div>

      {loading ? (
        <div className="flex items-center gap-2 py-8"><Loader2 className="w-4 h-4 animate-spin" /> Loading queue…</div>
      ) : error ? (
        <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2"
                    data-testid="ad-review-error">
          <AlertTriangle className="w-4 h-4" /> {String(error)}
        </div>
      ) : (
        <div className={`${cardCls} rounded-2xl overflow-hidden`}
                      data-testid="ad-review-queue-table">
          <div className={`hidden md:grid grid-cols-[24px,140px,1fr,140px,90px,110px,120px] gap-3 px-5 py-3 text-[10px] uppercase tracking-widest font-mono ${
                                    light ? "text-slate-500 bg-slate-50 border-b border-slate-200"
                                                  : "text-slate-500 bg-slate-950 border-b border-slate-800"}`}>
            <div></div>
            <div>Type</div>
            <div>Advertiser · Creative</div>
            <div>Submitted</div>
            <div>Priority</div>
            <div>AI Flag</div>
            <div>Actions</div>
          </div>
          {(items || []).length === 0 ? (
            <div className={`py-12 text-center text-sm ${muted}`}
                        data-testid="ad-review-empty">
              No creatives in this bucket.  Try switching filters.
            </div>
          ) : (items.map((r) => {
            const aiFlagged = r?.auto_moderation_result?.action_taken === "flagged";
            return (
              <div key={r.review_id}
                            className={`grid md:grid-cols-[24px,140px,1fr,140px,90px,110px,120px] gap-3 px-5 py-4 items-center ${
                                        light ? "border-b border-slate-100 last:border-0 hover:bg-slate-50"
                                                      : "border-b border-slate-800 last:border-0 hover:bg-slate-900"} transition`}
                            data-testid={`ad-review-row-${r.review_id}`}>
                <div>
                  <input type="checkbox"
                                  checked={!!selected[r.review_id]}
                                  onChange={(e) => setSelected((s) => ({...s, [r.review_id]: e.target.checked}))}
                                  data-testid={`ad-review-checkbox-${r.review_id}`} />
                </div>
                <div className="min-w-0">
                  <div className="text-xs font-bold uppercase tracking-wider text-amber-500 truncate">
                    {AD_TYPE_LABELS[r.ad_type] || r.ad_type}
                  </div>
                  <span className={`inline-flex items-center px-2 py-0.5 mt-1 rounded-full text-[10px] font-semibold ${STATUS_STYLES[r.review_status] || "bg-slate-500/15 text-slate-400"}`}>
                    {r.review_status}
                  </span>
                </div>
                <div className="min-w-0">
                  <div className="font-semibold truncate">
                    {r?.creative_snapshot?.title || r?.creative_snapshot?.name
                        || r?.creative_snapshot?.headline || r.target_id}
                  </div>
                  <div className={`text-[11px] ${muted} truncate flex items-center gap-1`}>
                    {r?.advertiser?.logo_url && (
                      <img src={r.advertiser.logo_url} alt=""
                                className="w-3.5 h-3.5 rounded object-cover" />
                    )}
                    {r?.advertiser?.name || r.advertiser_id || "—"}
                  </div>
                </div>
                <div className={`text-xs ${muted}`}>{fmtDt(r.submitted_at)}</div>
                <div className="text-sm font-mono">{r.priority_score}</div>
                <div>
                  {aiFlagged ? (
                    <span data-testid={`ad-review-ai-flag-${r.review_id}`}
                                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black bg-red-500/15 text-red-400 border border-red-500/30">
                      <Sparkles className="w-3 h-3" /> {r.auto_moderation_result?.highest_category || "flagged"}
                    </span>
                  ) : r?.auto_moderation_result?.action_taken === "clean" ? (
                    <span className={`text-[10px] font-mono ${muted}`}>clean</span>
                  ) : (
                    <span className={`text-[10px] font-mono ${muted}`}>—</span>
                  )}
                </div>
                <div>
                  <button onClick={() => setOpenReview(r.review_id)}
                                  data-testid={`ad-review-open-${r.review_id}`}
                                  className="inline-flex items-center gap-1 text-xs font-black px-3 py-1.5 rounded-full bg-amber-500 text-slate-900 hover:bg-amber-400">
                    Review <ChevronRight className="w-3 h-3" />
                  </button>
                </div>
              </div>
            );
          }))}
        </div>
      )}

      {openReview && (
        <AdReviewDetailModal
          reviewId={openReview}
          light={light}
          onClose={() => setOpenReview(null)}
          onDone={(msg, kind = "success") => {
            setOpenReview(null);
            showToast(kind, msg);
            load();
          }}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-50 max-w-sm"
                    data-testid="ad-review-toast">
          <div className={`${toast.kind === "error"
                                            ? "bg-red-500/15 border border-red-500/40 text-red-300"
                                            : "bg-emerald-500/15 border border-emerald-500/40 text-emerald-300"}
                                    rounded-lg px-4 py-3 shadow-xl text-sm font-medium`}>{toast.msg}</div>
        </div>
      )}
    </div>
  );
}


// ─── Analytics Tab ────────────────────────────────────────────────────
function AnalyticsTab({ light, muted }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    axios.get(`${API}/ad-review/analytics`, { withCredentials: true })
      .then((r) => setData(r.data))
      .catch(() => setData({ by_status: {}, by_day: [], top_rejected: [] }))
      .finally(() => setLoading(false));
  }, []);
  if (loading) return <Loader2 className="w-4 h-4 animate-spin" />;
  const t = data?.by_status || {};
  const cardCls = light ? "bg-white border border-slate-200"
                                              : "bg-slate-900/60 border border-slate-800";
  return (
    <div className="space-y-4" data-testid="ad-review-analytics">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi light={light} label="Approval rate"
                  value={`${data?.approval_rate_pct || 0}%`}
                  accent testid="analytics-approval-rate" />
        <Kpi light={light} label="Pending" value={t.pending || 0}
                  testid="analytics-pending" />
        <Kpi light={light} label="Requires changes" value={t.requires_changes || 0}
                  testid="analytics-changes" />
        <Kpi light={light} label="Avg time to review"
                  value={`${Math.round((data?.avg_secs_to_review || 0)/60)}m`}
                  testid="analytics-ttr" />
      </div>
      <div className={`${cardCls} rounded-2xl p-4`}>
        <div className="text-xs uppercase font-mono tracking-widest opacity-70 mb-2">Last {data?.window_days} days · Submissions</div>
        <div className="grid grid-cols-7 md:grid-cols-14 gap-1">
          {(data?.by_day || []).slice(-14).map((row) => {
            const total = (row.submitted || 0);
            const height = Math.min(80, 12 + total * 12);
            return (
              <div key={row._id} className="flex flex-col items-center gap-1">
                <div className={`w-full rounded-md ${light ? "bg-amber-500" : "bg-amber-500"}`}
                              style={{ height: `${height}px` }}
                              data-testid={`analytics-day-${row._id}`} />
                <span className={`text-[10px] font-mono ${muted}`}>{row._id.slice(-2)}</span>
              </div>
            );
          })}
        </div>
      </div>
      {/* Phase PREROLL.EXT — Top Spenders panel with priority-bump */}
      <TopSpendersPanel light={light} muted={muted} />
      <div className={`${cardCls} rounded-2xl overflow-hidden`}>
        <div className="px-5 py-3 text-xs font-black uppercase tracking-widest opacity-70">
          Top rejected advertisers
        </div>
        {(data?.top_rejected || []).length === 0 ? (
          <div className={`px-5 py-6 text-sm ${muted}`}>No rejects yet.</div>
        ) : (data.top_rejected.map((r) => (
          <div key={r.advertiser_id}
                        className={`grid grid-cols-[1fr,80px] gap-3 px-5 py-3 ${
                                  light ? "border-t border-slate-100" : "border-t border-slate-800"}`}>
            <div className="text-sm font-semibold">{r.advertiser_name}</div>
            <div className="text-right text-sm font-mono text-red-400">×{r.reject_count}</div>
          </div>
        )))}
      </div>
    </div>
  );
}


// Phase PREROLL.EXT — Top Advertisers by Spend + VIP priority-bump.
// ~45min addition per user brief: bump=+5 for VIP, restrict=-5 for
// slow/problematic advertisers.  Both immediately re-score any pending
// review rows for that advertiser (see adjust_priority_score_boost).
const AD_TYPE_FILTERS = [
  { v: "",                                          l: "All types" },
  { v: "advertiser_campaign",          l: "Campaign" },
  { v: "coupon_campaign",                  l: "Coupon" },
  { v: "preroll_audio",                      l: "Preroll" },
  { v: "banner",                                l: "Banner (idle)" },
  { v: "notification",                      l: "Notification (idle)" },
  { v: "sponsored_game",                  l: "Sponsored Game" },
  { v: "sponsored_predict_win",      l: "Sponsored PW (idle)" },
  { v: "sponsored_trivia",              l: "Sponsored Trivia (idle)" },
];

function TopSpendersPanel({ light, muted }) {
  const [rows, setRows] = useState(null);
  const [ad_type, setAdType] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  async function load() {
    const params = new URLSearchParams({
      window_days: "30", limit: "10",
    });
    if (ad_type) params.set("ad_type", ad_type);
    try {
      const { data } = await axios.get(
        `${API}/ad-review/analytics/top-spenders?${params}`,
        { withCredentials: true });
      setRows(data.items || []);
    } catch (_e) { setRows([]); }
  }
  useEffect(() => { load(); }, [ad_type]);

  async function bumpPriority(id, delta) {
    setBusy(true);
    try {
      const { data } = await axios.post(
        `${API}/ad-review/advertisers/${id}/priority-adjust`,
        { delta }, { withCredentials: true });
      setNote({ kind: "success",
                        msg: `${data.advertiser_name}: priority boost → ${data.priority_score_boost} (Δ${delta > 0 ? "+" : ""}${delta})` });
      setTimeout(() => setNote(null), 3500);
      load();
    } catch (e) {
      setNote({ kind: "error",
                        msg: e?.response?.data?.detail?.code || e.message });
      setTimeout(() => setNote(null), 3500);
    } finally { setBusy(false); }
  }

  async function block(id) {
    const reason = window.prompt("Block advertiser reason?");
    if (!reason) return;
    try {
      await axios.post(`${API}/ad-review/advertisers/${id}/block`,
                                        { reason }, { withCredentials: true });
      setNote({ kind: "success", msg: "Blocked." });
      setTimeout(() => setNote(null), 3500);
      load();
    } catch (e) {
      setNote({ kind: "error",
                        msg: e?.response?.data?.detail?.code || e.message });
    }
  }

  const cardCls = light ? "bg-white border border-slate-200"
                                              : "bg-slate-900/60 border border-slate-800";
  const fmt = (c) => (c || 0) >= 100
    ? `$${((c || 0)/100).toLocaleString(undefined, {maximumFractionDigits: 2})}`
    : `${c || 0}¢`;

  return (
    <div className={`${cardCls} rounded-2xl overflow-hidden`}
              data-testid="ad-review-top-spenders-panel">
      <div className="flex items-center gap-3 px-5 py-3 flex-wrap">
        <div className="text-xs font-black uppercase tracking-widest opacity-70">
          Top advertisers by 30-day spend
        </div>
        <select value={ad_type} onChange={(e) => setAdType(e.target.value)}
                        data-testid="ad-review-top-spenders-filter"
                        className={`ml-auto text-xs rounded-md px-2 py-1 ${
                                            light ? "bg-white border border-slate-300"
                                                          : "bg-slate-800 border border-slate-700"}`}>
          {AD_TYPE_FILTERS.map((f) => (
            <option key={f.v} value={f.v}>{f.l}</option>
          ))}
        </select>
      </div>
      {rows === null ? (
        <div className={`px-5 py-6 text-sm ${muted}`}><Loader2 className="w-4 h-4 animate-spin inline" /> loading…</div>
      ) : rows.length === 0 ? (
        <div className={`px-5 py-6 text-sm ${muted}`}
                    data-testid="ad-review-top-spenders-empty">
          No spend in the selected window/filter yet.
        </div>
      ) : (
        <div data-testid="ad-review-top-spenders-table">
          <div className={`hidden md:grid grid-cols-[1fr,120px,90px,90px,90px,180px] gap-3 px-5 py-2 text-[10px] uppercase tracking-widest font-mono ${
                                    light ? "text-slate-500 bg-slate-50 border-y border-slate-200"
                                                  : "text-slate-500 bg-slate-950 border-y border-slate-800"}`}>
            <div>Advertiser</div>
            <div>Spend (30d)</div>
            <div>Reject %</div>
            <div>Avg TTR</div>
            <div>Boost</div>
            <div>Actions</div>
          </div>
          {rows.map((r) => (
            <div key={r.advertiser_id}
                          data-testid={`ad-review-top-spenders-row-${r.advertiser_id}`}
                          className={`grid md:grid-cols-[1fr,120px,90px,90px,90px,180px] gap-3 px-5 py-3 items-center ${
                                    light ? "border-b border-slate-100 last:border-0"
                                                  : "border-b border-slate-800 last:border-0"}`}>
              <div className="min-w-0 flex items-center gap-2">
                {r.logo_url && (
                  <img src={r.logo_url} alt=""
                                className="w-6 h-6 rounded-md object-cover" />
                )}
                <div className="min-w-0">
                  <div className="font-semibold truncate">{r.advertiser_name}</div>
                  <div className={`text-[10px] ${muted} font-mono`}>{r.advertiser_id}</div>
                </div>
              </div>
              <div className="text-sm font-mono">{fmt(r.spend_cents)}</div>
              <div className={`text-sm font-mono ${r.reject_rate_pct > 20 ? "text-red-400" : ""}`}>
                {r.reject_rate_pct}%
              </div>
              <div className={`text-sm font-mono ${muted}`}>
                {r.avg_ttr_secs ? `${Math.round(r.avg_ttr_secs/60)}m` : "—"}
              </div>
              <div className={`text-sm font-black ${
                                          r.priority_score_boost > 0 ? "text-emerald-400"
                                          : r.priority_score_boost < 0 ? "text-orange-400"
                                          : muted}`}>
                {r.priority_score_boost > 0 ? "+" : ""}{r.priority_score_boost}
              </div>
              <div className="flex gap-1 flex-wrap">
                <button onClick={() => bumpPriority(r.advertiser_id, 5)}
                                disabled={busy}
                                data-testid={`ad-review-priority-bump-${r.advertiser_id}`}
                                title="Bump priority (VIP)"
                                className="text-[10px] font-black px-2 py-1 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/25 disabled:opacity-40">
                  ⬆ Bump
                </button>
                <button onClick={() => bumpPriority(r.advertiser_id, -5)}
                                disabled={busy}
                                data-testid={`ad-review-priority-restrict-${r.advertiser_id}`}
                                title="Restrict priority"
                                className="text-[10px] font-black px-2 py-1 rounded-full bg-orange-500/15 text-orange-400 border border-orange-500/30 hover:bg-orange-500/25 disabled:opacity-40">
                  ⬇ Restrict
                </button>
                <button onClick={() => block(r.advertiser_id)}
                                data-testid={`ad-review-top-spenders-block-${r.advertiser_id}`}
                                title="Block advertiser"
                                className="text-[10px] font-black px-2 py-1 rounded-full bg-red-500/15 text-red-400 border border-red-500/30 hover:bg-red-500/25">
                  ⊗ Block
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {note && (
        <div className={`px-5 py-2 text-xs ${note.kind === "error" ? "text-red-400" : "text-emerald-400"}`}
                    data-testid="ad-review-top-spenders-note">
          {note.msg}
        </div>
      )}
    </div>
  );
}


// ─── Blocked Advertisers Tab ──────────────────────────────────────────
function BlockedTab({ light, muted }) {
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  async function load() {
    setLoading(true);
    try {
      const { data } = await axios.get(`${API}/ad-review/blocked-advertisers`,
                                                                                      { withCredentials: true });
      setItems(data.items || []);
    } catch (e) { setError(e?.response?.data?.detail?.code || e.message); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, []);

  async function unblock(id) {
    if (!window.confirm("Unblock this advertiser?")) return;
    await axios.post(`${API}/ad-review/advertisers/${id}/unblock`, {},
                                            { withCredentials: true });
    load();
  }
  const cardCls = light ? "bg-white border border-slate-200"
                                              : "bg-slate-900/60 border border-slate-800";
  if (loading) return <Loader2 className="w-4 h-4 animate-spin" />;
  if (error) return <div className="text-red-400 text-sm">{error}</div>;

  return (
    <div className={`${cardCls} rounded-2xl overflow-hidden`}
              data-testid="ad-review-blocked-table">
      {(items || []).length === 0 ? (
        <div className={`py-12 text-center text-sm ${muted}`}
                    data-testid="ad-review-blocked-empty">
          No blocked advertisers.  Block from a queue row&apos;s detail modal.
        </div>
      ) : (items.map((a) => (
        <div key={a.advertiser_id}
                      className={`grid grid-cols-[1fr,180px,110px] gap-3 px-5 py-4 items-center ${
                                light ? "border-b border-slate-100 last:border-0"
                                              : "border-b border-slate-800 last:border-0"}`}
                      data-testid={`ad-review-blocked-row-${a.advertiser_id}`}>
          <div className="min-w-0">
            <div className="font-semibold truncate">{a.name || a.advertiser_id}</div>
            <div className={`text-[11px] ${muted} truncate`}>
              Reason: {a.blocked_reason || "—"}
            </div>
          </div>
          <div className={`text-xs ${muted}`}>{fmtDt(a.blocked_at)}</div>
          <button onClick={() => unblock(a.advertiser_id)}
                          data-testid={`ad-review-unblock-${a.advertiser_id}`}
                          className="inline-flex items-center gap-1 text-xs font-black px-3 py-1.5 rounded-full bg-emerald-500 text-slate-900 hover:bg-emerald-400">
            <RotateCw className="w-3 h-3" /> Unblock
          </button>
        </div>
      )))}
    </div>
  );
}


// ─── Audit Log Tab ────────────────────────────────────────────────────
function AuditTab({ light, muted }) {
  const [items, setItems] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    axios.get(`${API}/ad-review/audit-log`, { withCredentials: true })
      .then((r) => setItems(r.data.items || []))
      .finally(() => setLoading(false));
  }, []);
  const cardCls = light ? "bg-white border border-slate-200"
                                              : "bg-slate-900/60 border border-slate-800";
  if (loading) return <Loader2 className="w-4 h-4 animate-spin" />;
  return (
    <div className={`${cardCls} rounded-2xl overflow-hidden`}
              data-testid="ad-review-audit-table">
      {(items || []).length === 0 ? (
        <div className={`py-12 text-center text-sm ${muted}`}
                    data-testid="ad-review-audit-empty">
          No audit entries yet.
        </div>
      ) : (items.map((a) => (
        <div key={a.audit_id}
                      className={`grid grid-cols-[140px,120px,1fr,180px] gap-3 px-5 py-3 items-center ${
                                light ? "border-b border-slate-100 last:border-0"
                                              : "border-b border-slate-800 last:border-0"} text-sm`}
                      data-testid={`ad-review-audit-row-${a.audit_id}`}>
          <div className={`text-xs ${muted}`}>{fmtDt(a.created_at)}</div>
          <div className="text-xs font-bold uppercase tracking-wider text-amber-500">{a.action}</div>
          <div className={`text-xs ${muted} truncate`}>
            {a.notes || a.reason || `${a.before_status || "—"} → ${a.after_status || "—"}`}
          </div>
          <div className={`text-[11px] font-mono ${muted} truncate`}>{a.review_id}</div>
        </div>
      )))}
    </div>
  );
}


function Kpi({ light, label, value, accent, testid }) {
  return (
    <div className={`rounded-2xl p-4 ${light ? "bg-white border border-slate-200" : "bg-slate-900/60 border border-slate-800"}`}
              data-testid={testid}>
      <div className={`text-[10px] uppercase tracking-widest font-mono ${light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
      <div className={`mt-1 text-2xl font-black ${
                                  accent ? (light ? "text-amber-600" : "text-amber-400")
                                                    : (light ? "text-slate-900" : "text-white")}`}>{value}</div>
    </div>
  );
}
