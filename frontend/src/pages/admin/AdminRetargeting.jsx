// Phase M — M6 Retargeting · Admin view.
// Legacy dark. Two lists: Audiences + Campaigns (moderation).
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  Loader2, ArrowLeft, Target, Check, X, Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import AdminPageHeader from "@/components/AdminPageHeader";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;


export default function AdminRetargeting() {
  const [tab, setTab] = useState("campaigns");
  return (
    <div data-testid="admin-retargeting-page"
         className="min-h-screen bg-slate-950 text-white p-6">
      <AdminPageHeader
        title="Retargeting — Admin"
        subtitle="Manage retargeting audiences and campaigns."
        Icon={Target}
        tint="text-orange-500"
        pinLabel="Retargeting"
        breadcrumbs={[{ label: "Ad Monetization" },
                                        { label: "Retargeting" }]} />
      <div className="flex gap-2 mt-3 mb-4">
        <button onClick={() => setTab("campaigns")}
                data-testid="admin-rt-tab-campaigns"
                className={`px-3 py-1.5 rounded-full text-xs font-bold ${
                  tab === "campaigns"
                    ? "bg-white text-slate-900"
                    : "bg-white/5 text-slate-300 hover:bg-white/10"}`}>
          Campaigns
        </button>
        <button onClick={() => setTab("audiences")}
                data-testid="admin-rt-tab-audiences"
                className={`px-3 py-1.5 rounded-full text-xs font-bold ${
                  tab === "audiences"
                    ? "bg-white text-slate-900"
                    : "bg-white/5 text-slate-300 hover:bg-white/10"}`}>
          Audiences
        </button>
      </div>
      {tab === "campaigns" ? <CampaignsTab /> : <AudiencesTab />}
    </div>
  );
}


function CampaignsTab() {
  const [status, setStatus] = useState("pending_admin");
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/admin/retargeting-campaigns?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const decide = async (id, action) => {
    setBusy(id); setErr(null);
    try {
      await axios.post(
        `${API}/admin/retargeting-campaigns/${id}/${action}`,
        { admin_notes: "" }, { withCredentials: true });
      await load();
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(null);
  };

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-3">
        {["", "pending_admin", "active", "cancelled", "completed"].map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                  data-testid={`admin-rt-campaign-filter-${s || "all"}`}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold border ${
                    status === s
                      ? "bg-white text-slate-900 border-white"
                      : "border-white/10 text-slate-300"}`}>
            {s || "All"}
          </button>
        ))}
      </div>
      {items === null && (
        <div className="text-slate-400" data-testid="admin-rt-campaign-loading">
          <Loader2 size={16} className="animate-spin inline" /> Loading…
        </div>
      )}
      {items?.length === 0 && (
        <div className="text-slate-400 text-sm"
             data-testid="admin-rt-campaign-empty">
          No campaigns.
        </div>
      )}
      {err && (
        <div data-testid="admin-rt-campaign-error"
             className="text-red-400 text-xs">{err}</div>
      )}
      <div className="grid gap-3">
        {(items || []).map((c) => (
          <div key={c.id} data-testid={`admin-rt-campaign-row-${c.id}`}
               className="rounded-2xl p-4 bg-white/5 border border-white/10">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <div className="font-black">
                  {c.advertiser_business_id}
                  <span data-testid={`admin-rt-campaign-status-${c.id}`}
                        className={`ml-2 text-[10px] px-2 py-0.5 rounded-full font-bold ${
                          c.status === "active"
                            ? "bg-emerald-500"
                            : c.status === "pending_admin"
                                ? "bg-amber-500"
                                : c.status === "cancelled"
                                    ? "bg-slate-600"
                                    : "bg-slate-500"}`}>
                    {c.status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  {c.base_ad_type} · {c.base_ad_id} · audience{" "}
                  {c.audience_id} · boost ×{c.boost_multiplier}
                </div>
              </div>
              <div className="text-right">
                <div className="font-black text-sm">
                  ${((c.grand_total_cents || 0) / 100).toFixed(2)}
                </div>
                <div className="text-[10px] text-slate-400">
                  cpi {c.cost_per_impression_cents}¢ · served{" "}
                  {c.plays_delivered || 0}
                </div>
              </div>
            </div>
            {c.status === "pending_admin" && (
              <div className="flex gap-2 mt-3">
                <button onClick={() => decide(c.id, "approve")}
                        disabled={busy === c.id}
                        data-testid={`admin-rt-campaign-approve-${c.id}`}
                        className="text-xs px-3 py-1.5 rounded-full font-bold
                                   bg-emerald-500 text-white hover:bg-emerald-400
                                   inline-flex items-center gap-1
                                   disabled:opacity-40">
                  <Check size={12} /> Approve
                </button>
                <button onClick={() => decide(c.id, "reject")}
                        disabled={busy === c.id}
                        data-testid={`admin-rt-campaign-reject-${c.id}`}
                        className="text-xs px-3 py-1.5 rounded-full font-bold
                                   bg-red-500 text-white hover:bg-red-400
                                   inline-flex items-center gap-1
                                   disabled:opacity-40">
                  <X size={12} /> Reject + refund
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


function AudiencesTab() {
  const [items, setItems] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const { data } = await axios.get(
        `${API}/admin/retargeting-audiences`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div>
      {items === null && (
        <div className="text-slate-400"
             data-testid="admin-rt-audience-loading">
          <Loader2 size={16} className="animate-spin inline" /> Loading…
        </div>
      )}
      {items?.length === 0 && (
        <div className="text-slate-400 text-sm"
             data-testid="admin-rt-audience-empty">
          No audiences.
        </div>
      )}
      {err && (
        <div data-testid="admin-rt-audience-error"
             className="text-red-400 text-xs">{err}</div>
      )}
      <div className="grid gap-3">
        {(items || []).map((a) => (
          <div key={a.id} data-testid={`admin-rt-audience-row-${a.id}`}
               className="rounded-2xl p-4 bg-white/5 border border-white/10">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <div className="font-black">
                  <Users size={12} className="inline mr-1" />
                  {a.name}
                  <span data-testid={`admin-rt-audience-status-${a.id}`}
                        className={`ml-2 text-[10px] px-2 py-0.5 rounded-full font-bold ${
                          a.status === "active"
                            ? "bg-emerald-500" : "bg-slate-600"}`}>
                    {a.status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  advertiser {a.advertiser_business_id} ·{" "}
                  {(a.rules || []).length} rules · logic{" "}
                  {a.rule_logic}
                </div>
              </div>
              <div className="text-right font-black text-sm">
                {a.estimated_size || 0}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
