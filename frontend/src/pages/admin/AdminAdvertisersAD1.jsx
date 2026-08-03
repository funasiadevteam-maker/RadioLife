// Phase AD.1 — Admin approval UI for the new advertiser stack.
// Route: /admin/advertisers  ·  Requires role=admin.

import { useEffect, useState } from "react";
import axios from "axios";
import {
  Users, Megaphone, Check, X, Loader2, Building2, ExternalLink,
  ChevronRight, AlertTriangle,
} from "lucide-react";

import { useAuth } from "@/AuthContext";
import { useEffectivePageVariant } from "@/hooks/useDesignVariant";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const fmt = (cents) => `$${((cents || 0) / 100).toFixed(2)}`;

const TABS = [
  { id: "advertisers", label: "Advertisers", Icon: Users },
  { id: "campaigns",   label: "Campaigns",   Icon: Megaphone },
];

export default function AdminAdvertisersAD1() {
  const variant = useEffectivePageVariant();
  const light = variant === "radiolife";
  const { user, loading: authLoading } = useAuth();
  const [tab, setTab] = useState("advertisers");
  const [statusFilter, setStatusFilter] = useState("pending_approval");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refresher, setRefresher] = useState(0);

  useEffect(() => {
    if (authLoading || user?.role !== "admin") return;
    setLoading(true);
    (async () => {
      try {
        const url = tab === "advertisers"
          ? `${API}/admin/ad1/advertisers${statusFilter ? `?status=${statusFilter}` : ""}`
          : `${API}/admin/ad1/ad-campaigns${statusFilter ? `?status=${statusFilter}` : ""}`;
        const { data } = await axios.get(url);
        setItems(data.items || []);
      } catch (_) {}
      finally { setLoading(false); }
    })();
  }, [tab, statusFilter, refresher, user, authLoading]);

  if (authLoading) return null;
  if (user?.role !== "admin") {
    return (
      <div className={`${light ? "bg-white text-slate-900" : "bg-slate-950 text-white"} min-h-screen p-8 flex items-center justify-center`}
                data-testid="admin-advertisers-forbidden">
        <div className="max-w-md text-center">
          <AlertTriangle className="w-10 h-10 text-red-500 mx-auto" />
          <div className="mt-3 font-bold text-lg">Admin access required</div>
        </div>
      </div>
    );
  }

  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"}`;

  return (
    <div className={`${light ? "bg-slate-50 text-slate-900" : "bg-slate-950 text-white"} min-h-screen`}
              data-testid="admin-advertisers-page">
      <div className="max-w-6xl mx-auto p-6 sm:p-8">
        <div className="text-xs uppercase tracking-widest font-mono text-amber-500">Admin</div>
        <h1 className="text-3xl font-bold mt-1">Advertiser + Campaign approval</h1>

        {/* Tabs */}
        <div className="mt-6 flex gap-1 rounded-full p-1 max-w-md border border-slate-800/40 bg-slate-800/10 w-fit"
                    data-testid="admin-advertisers-tabs">
          {TABS.map((t) => (
            <button key={t.id} onClick={() => setTab(t.id)}
                            data-testid={`admin-advertisers-tab-${t.id}`}
                            className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-full text-sm font-semibold transition ${
                                tab === t.id ? "bg-amber-500 text-slate-950" :
                                                            (light ? "text-slate-700 hover:bg-slate-100" : "text-slate-300 hover:bg-slate-800")
                            }`}>
              <t.Icon className="w-4 h-4" /> {t.label}
            </button>
          ))}
        </div>

        {/* Status filter */}
        <div className="mt-4 flex gap-2 flex-wrap" data-testid="admin-advertisers-filter">
          {["pending_approval", "active", "rejected", "draft", null].map((s) => (
            <button key={s || "all"} onClick={() => setStatusFilter(s)}
                            data-testid={`admin-advertisers-filter-${s || "all"}`}
                            className={`px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider ${
                                statusFilter === s
                                  ? "bg-amber-500 text-slate-950"
                                  : (light ? "border border-slate-300 text-slate-600 hover:bg-slate-100"
                                                  : "border border-slate-700 text-slate-400 hover:bg-slate-800")
                            }`}>{s ? s.replace(/_/g, " ") : "all"}</button>
          ))}
        </div>

        {loading ? (
          <Loader2 className="w-6 h-6 animate-spin text-amber-500 mx-auto mt-16" />
        ) : items.length === 0 ? (
          <div className={`${cardCls} mt-6 rounded-2xl p-10 text-center`}
                      data-testid="admin-advertisers-empty">
            <div className={light ? "text-slate-600" : "text-slate-400"}>Nothing here yet.</div>
          </div>
        ) : (
          <div className="mt-6 space-y-3">
            {tab === "advertisers" && items.map((a) => (
              <AdvertiserRow key={a.advertiser_id} item={a} light={light}
                                            onDone={() => setRefresher((n) => n + 1)} />
            ))}
            {tab === "campaigns" && items.map((c) => (
              <CampaignRow key={c.campaign_id} item={c} light={light}
                                        onDone={() => setRefresher((n) => n + 1)} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AdvertiserRow({ item, light, onDone }) {
  const [busy, setBusy] = useState(false);
  const [rejectMode, setRejectMode] = useState(false);
  const [reason, setReason] = useState("");
  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"} rounded-2xl p-5`;

  async function approve() {
    setBusy(true);
    try {
      await axios.post(`${API}/admin/ad1/advertisers/${item.advertiser_id}/approve`);
      onDone();
    } finally { setBusy(false); }
  }
  async function reject() {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      await axios.post(`${API}/admin/ad1/advertisers/${item.advertiser_id}/reject`, { reason });
      onDone();
    } finally { setBusy(false); }
  }

  return (
    <div className={cardCls} data-testid={`admin-advertiser-row-${item.advertiser_id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4 text-slate-500" />
            <div className="font-bold text-lg truncate">{item.name}</div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider ${
                                        item.status === "active" ? "bg-emerald-500/15 text-emerald-500"
                                                                              : item.status === "pending_approval" ? "bg-amber-500/15 text-amber-500"
                                                                              : "bg-slate-500/15 text-slate-400"
                                    }`}>{item.status.replace(/_/g, " ")}</span>
          </div>
          <div className={`mt-1 text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
            {item.contact_email} · {item.industry || "—"} · {item.website || "no website"}
          </div>
          {item.rejected_reason && (
            <div className="mt-2 text-xs text-red-400">Previously rejected: {item.rejected_reason}</div>
          )}
        </div>
        <div className="flex gap-2">
          {item.status === "pending_approval" && !rejectMode && (
            <>
              <button onClick={approve} disabled={busy}
                              data-testid={`admin-advertiser-approve-${item.advertiser_id}`}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500 text-white text-xs font-semibold hover:bg-emerald-400 disabled:opacity-50">
                <Check className="w-3.5 h-3.5" /> Approve
              </button>
              <button onClick={() => setRejectMode(true)} disabled={busy}
                              data-testid={`admin-advertiser-reject-btn-${item.advertiser_id}`}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-500/15 text-red-400 text-xs font-semibold hover:bg-red-500/25 disabled:opacity-50">
                <X className="w-3.5 h-3.5" /> Reject
              </button>
            </>
          )}
        </div>
      </div>
      {rejectMode && (
        <div className="mt-3 flex gap-2 items-center" data-testid={`admin-advertiser-reject-form-${item.advertiser_id}`}>
          <input value={reason} onChange={(e) => setReason(e.target.value)}
                        placeholder="Reason for rejection…"
                        className={`flex-1 px-3 py-1.5 rounded-lg border text-sm ${
                            light ? "border-slate-300 bg-white" : "border-slate-700 bg-slate-800"
                        }`}
                        data-testid={`admin-advertiser-reject-reason-${item.advertiser_id}`} />
          <button onClick={reject} disabled={busy || !reason.trim()}
                          data-testid={`admin-advertiser-reject-confirm-${item.advertiser_id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-500 text-white text-xs font-semibold hover:bg-red-400 disabled:opacity-50">
            Confirm
          </button>
          <button onClick={() => setRejectMode(false)}
                          className={`px-3 py-1.5 rounded-full text-xs ${light ? "text-slate-500 hover:bg-slate-100" : "text-slate-400 hover:bg-slate-800"}`}>
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}

function CampaignRow({ item, light, onDone }) {
  const [busy, setBusy] = useState(false);
  const [rejectMode, setRejectMode] = useState(false);
  const [reason, setReason] = useState("");
  const cardCls = `${light ? "bg-white border border-slate-200" : "bg-slate-900 border border-slate-800"} rounded-2xl p-5`;

  async function approve() {
    setBusy(true);
    try {
      await axios.post(`${API}/admin/ad1/ad-campaigns/${item.campaign_id}/approve`);
      onDone();
    } finally { setBusy(false); }
  }
  async function reject() {
    if (!reason.trim()) return;
    setBusy(true);
    try {
      await axios.post(`${API}/admin/ad1/ad-campaigns/${item.campaign_id}/reject`, { reason });
      onDone();
    } finally { setBusy(false); }
  }

  const creative = item.creative || {};

  return (
    <div className={cardCls} data-testid={`admin-campaign-row-${item.campaign_id}`}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Megaphone className="w-4 h-4 text-slate-500" />
            <div className="font-bold text-lg truncate">{item.name}</div>
            <span className={`text-[10px] px-2 py-0.5 rounded-full font-semibold uppercase tracking-wider ${
                                        item.status === "active" ? "bg-emerald-500/15 text-emerald-500"
                                                                              : item.status === "pending_approval" ? "bg-amber-500/15 text-amber-500"
                                                                              : "bg-slate-500/15 text-slate-400"
                                    }`}>{item.status.replace(/_/g, " ")}</span>
          </div>
          <div className={`mt-1 text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
            {item.advertiser?.name || item.advertiser_id} · {item.campaign_type.replace(/_/g, " ")} · budget {fmt(item.budget_total_cents)}
          </div>

          {/* Creative preview */}
          {(creative.headline || creative.body) && (
            <div className={`mt-3 p-3 rounded-lg ${light ? "bg-slate-50 border border-slate-200" : "bg-slate-800/50 border border-slate-700"}`}
                        data-testid={`admin-campaign-creative-${item.campaign_id}`}>
              {creative.headline && <div className="font-bold">{creative.headline}</div>}
              {creative.body && <div className={`text-sm mt-1 ${light ? "text-slate-600" : "text-slate-300"}`}>{creative.body}</div>}
              {creative.click_url && (
                <a href={creative.click_url} target="_blank" rel="noreferrer"
                      className="mt-1 inline-flex items-center gap-1 text-xs text-amber-500 hover:underline">
                  {creative.click_url} <ExternalLink className="w-3 h-3" />
                </a>
              )}
            </div>
          )}
          {item.campaign_type === "sponsored_game" && creative.sponsored_game_campaign_id && (
            <div className={`mt-2 text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
              Sponsoring merchant game: <code>{creative.sponsored_game_campaign_id}</code>
            </div>
          )}
          <div className={`mt-2 text-xs ${light ? "text-slate-500" : "text-slate-500"}`}>
            Targeting: {(item.targeting?.cities || []).join(", ") || "(all cities)"} ·
              segments {(item.targeting?.user_segments || []).join(", ") || "all"} ·
              dayparts {(item.targeting?.dayparts || []).join(", ") || "any"}
          </div>
        </div>
        <div className="flex gap-2">
          {item.status === "pending_approval" && !rejectMode && (
            <>
              <button onClick={approve} disabled={busy}
                              data-testid={`admin-campaign-approve-${item.campaign_id}`}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-emerald-500 text-white text-xs font-semibold hover:bg-emerald-400 disabled:opacity-50">
                <Check className="w-3.5 h-3.5" /> Approve
              </button>
              <button onClick={() => setRejectMode(true)} disabled={busy}
                              data-testid={`admin-campaign-reject-btn-${item.campaign_id}`}
                              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-500/15 text-red-400 text-xs font-semibold hover:bg-red-500/25 disabled:opacity-50">
                <X className="w-3.5 h-3.5" /> Reject
              </button>
            </>
          )}
        </div>
      </div>
      {rejectMode && (
        <div className="mt-3 flex gap-2 items-center">
          <input value={reason} onChange={(e) => setReason(e.target.value)}
                        placeholder="Reason for rejection…"
                        className={`flex-1 px-3 py-1.5 rounded-lg border text-sm ${
                            light ? "border-slate-300 bg-white" : "border-slate-700 bg-slate-800"
                        }`}
                        data-testid={`admin-campaign-reject-reason-${item.campaign_id}`} />
          <button onClick={reject} disabled={busy || !reason.trim()}
                          data-testid={`admin-campaign-reject-confirm-${item.campaign_id}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-red-500 text-white text-xs font-semibold hover:bg-red-400 disabled:opacity-50">
            Confirm
          </button>
          <button onClick={() => setRejectMode(false)}
                          className={`px-3 py-1.5 rounded-full text-xs ${light ? "text-slate-500 hover:bg-slate-100" : "text-slate-400 hover:bg-slate-800"}`}>
            Cancel
          </button>
        </div>
      )}
    </div>
  );
}
