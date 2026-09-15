// Admin — Rail Ads moderation. Approve / reject the right-rail banner
// campaigns advertisers buy (banner_ads_v2 slot campaigns).
//   • GET  /api/ads/admin/banner-campaigns?status=…
//   • POST /api/ads/admin/banner-campaigns/{cid}/approve
//   • POST /api/ads/admin/banner-campaigns/{cid}/reject  {reason}
import React, { useEffect, useState } from "react";
import axios from "axios";
import { CheckCircle2, XCircle, Loader2, ExternalLink, ShieldCheck, RefreshCw } from "lucide-react";
import { API } from "@/AuthContext";

const CFG = { withCredentials: true };
const TABS = ["pending", "active", "rejected", "all"];
const RAIL = new Set(["right_rail_mpu_1", "right_rail_mpu_2", "right_rail_mpu_3"]);

const STATUS_STYLE = {
  pending: "bg-amber-500/15 text-amber-400",
  pending_payment: "bg-slate-500/15 text-slate-400",
  active: "bg-emerald-500/15 text-emerald-400",
  rejected: "bg-red-500/15 text-red-400",
  paused: "bg-slate-500/15 text-slate-400",
  completed: "bg-blue-500/15 text-blue-400",
};

export default function AdminRailAds() {
  const [status, setStatus] = useState("pending");
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  async function load() {
    setItems(null); setErr(null);
    try {
      const { data } = await axios.get(`${API}/ads/admin/banner-campaigns?status=${status}`, CFG);
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e?.response?.data?.detail || e.message);
      setItems([]);
    }
  }
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [status]);

  async function approve(cid) {
    setBusy(cid);
    try { await axios.post(`${API}/ads/admin/banner-campaigns/${cid}/approve`, {}, CFG); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || e.message); }
    finally { setBusy(null); }
  }
  async function reject(cid) {
    const reason = window.prompt("Reason for rejection (optional):") ?? "";
    setBusy(cid);
    try { await axios.post(`${API}/ads/admin/banner-campaigns/${cid}/reject`, { reason }, CFG); await load(); }
    catch (e) { setErr(e?.response?.data?.detail || e.message); }
    finally { setBusy(null); }
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white px-4 sm:px-8 py-8" data-testid="admin-rail-ads-page">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center gap-2 mb-1">
          <ShieldCheck className="w-5 h-5 text-fuchsia-400" />
          <h1 className="text-2xl font-black">Rail Ads · Moderation</h1>
        </div>
        <p className="text-sm text-slate-400 mb-5">
          Approve or reject the right-rail banner campaigns advertisers buy. Approved campaigns go live in the New Look V2 home right rail.
        </p>

        <div className="flex items-center gap-2 mb-5 flex-wrap">
          {TABS.map((t) => (
            <button key={t} onClick={() => setStatus(t)} data-testid={`admin-rail-tab-${t}`}
              className={`px-3 py-1.5 rounded-full text-xs font-bold uppercase tracking-wide transition ${status === t
                ? "bg-fuchsia-500 text-white" : "bg-slate-900 text-slate-400 hover:text-white border border-slate-800"}`}>
              {t}
            </button>
          ))}
          <button onClick={load} data-testid="admin-rail-refresh"
            className="ml-auto inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-semibold bg-slate-900 border border-slate-800 hover:text-white text-slate-400">
            <RefreshCw className="w-3.5 h-3.5" /> Refresh
          </button>
        </div>

        {err && (
          <div className="mb-4 rounded-lg px-4 py-2 text-sm bg-red-500/10 border border-red-500/40 text-red-400" data-testid="admin-rail-error">
            {String(err)}
          </div>
        )}

        {items === null ? (
          <div className="flex items-center gap-2 text-slate-400 text-sm py-10 justify-center">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading campaigns…
          </div>
        ) : items.length === 0 ? (
          <div className="text-slate-500 text-sm py-10 text-center" data-testid="admin-rail-empty">
            No {status === "all" ? "" : status} campaigns.
          </div>
        ) : (
          <div className="space-y-3" data-testid="admin-rail-list">
            {items.map((c) => {
              const isRail = (c.slot_keys || []).some((k) => RAIL.has(k));
              return (
                <div key={c.campaign_id} data-testid={`admin-rail-camp-${c.campaign_id}`}
                  className="rounded-2xl bg-slate-900 border border-slate-800 p-4 flex flex-col sm:flex-row gap-4">
                  {c.creative_image_url
                    ? <img src={c.creative_image_url} alt="" className="w-full sm:w-40 h-28 rounded-lg object-cover bg-slate-800" />
                    : <div className="w-full sm:w-40 h-28 rounded-lg bg-slate-800 grid place-items-center text-xs text-slate-500">no creative</div>}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full ${STATUS_STYLE[c.status] || "bg-slate-500/15 text-slate-400"}`}>{c.status}</span>
                      {isRail && <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-full bg-fuchsia-500/15 text-fuchsia-300">Right Rail</span>}
                      <span className="text-[11px] font-mono text-slate-500">{c.campaign_id}</span>
                    </div>
                    <div className="mt-1.5 text-sm font-mono text-slate-300 truncate">{(c.slot_keys || []).join(", ")}</div>
                    {c.click_url && (
                      <a href={c.click_url} target="_blank" rel="noreferrer"
                        className="mt-1 inline-flex items-center gap-1 text-[12px] text-fuchsia-400 hover:underline truncate max-w-full">
                        {c.click_url} <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                    )}
                    <div className="mt-1 text-[11px] text-slate-500">
                      Budget ${Number(c.total_budget || 0).toLocaleString()} · advertiser {c.advertiser_id}
                    </div>
                    {c.rejected_reason && <div className="mt-1 text-[11px] text-red-400">Rejected: {c.rejected_reason}</div>}
                  </div>
                  {(c.status === "pending" || c.status === "paused") && (
                    <div className="flex sm:flex-col gap-2 shrink-0">
                      <button onClick={() => approve(c.campaign_id)} disabled={busy === c.campaign_id}
                        data-testid={`admin-rail-approve-${c.campaign_id}`}
                        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-500 text-slate-900 text-xs font-black hover:bg-emerald-400 disabled:opacity-40">
                        {busy === c.campaign_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />} Approve
                      </button>
                      <button onClick={() => reject(c.campaign_id)} disabled={busy === c.campaign_id}
                        data-testid={`admin-rail-reject-${c.campaign_id}`}
                        className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg bg-red-500/90 text-white text-xs font-black hover:bg-red-500 disabled:opacity-40">
                        <XCircle className="w-3.5 h-3.5" /> Reject
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
