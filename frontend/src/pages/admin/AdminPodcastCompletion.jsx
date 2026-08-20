// Phase G — AD.9 Podcast Completion Points · Admin page.
// Legacy dark only.  List all campaigns across advertisers, approve/
// reject those in `pending_admin`, drill into details.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, Headphones, CheckCircle2, XCircle, ArrowRight,
  AlertTriangle, X, Coins, Ticket,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_admin", "active", "paused",
                                    "completed", "cancelled"];


export default function AdminPodcastCompletion() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("pending_admin");
  const [detail, setDetail] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/admin/podcast-completion-campaigns?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const openDetail = async (campaign_id) => {
    try {
      const { data } = await axios.get(
        `${API}/admin/podcast-completion-campaigns/${campaign_id}`,
        { withCredentials: true });
      setDetail(data);
    } catch { setDetail(null); }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white"
              data-testid="admin-podcast-completion-page">
      <div className="max-w-5xl mx-auto px-6 py-8">
        <Link to="/admin"
                    className="text-xs text-slate-400 hover:text-white
                                            inline-flex items-center gap-1 mb-4">← Admin</Link>
        <h1 className="text-3xl font-black inline-flex items-center gap-2 mb-1">
          <Headphones className="text-fuchsia-500" size={28} />
          Podcast Completion Campaigns
        </h1>
        <p className="text-slate-400 text-sm mb-6">
          Advertisers reward listeners with points or dollar-off vouchers when
          they finish a podcast episode. Campaigns with total budget ≥ $500
          require admin approval.
        </p>

        <div className="flex flex-wrap gap-1.5 mb-6">
          <span className="text-[10px] font-mono uppercase tracking-widest
                                        text-slate-500 self-center pr-2">Status</span>
          {STATUSES.map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)}
                            data-testid={`admin-pc-filter-${s || "all"}`}
                            className={`text-[10px] font-mono uppercase tracking-widest
                                                      px-3 py-1.5 rounded-full border ${
                                                          status === s
                                                              ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-500"
                                                              : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
              {s || "All"}
            </button>
          ))}
        </div>

        {err && (
          <div className="rounded-xl px-4 py-3 bg-red-500/10 border border-red-500/40
                                        text-red-400 text-sm mb-4"
                      data-testid="admin-pc-error">{err}</div>
        )}
        {items === null ? (
          <div className="text-slate-400 inline-flex items-center gap-2"
                      data-testid="admin-pc-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl bg-slate-900/60 border border-slate-800
                                        p-8 text-center text-slate-400 text-sm"
                      data-testid="admin-pc-empty">
            No campaigns in this state.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((c) => (
              <CampaignRow key={c.campaign_id} c={c}
                                          onClick={() => openDetail(c.campaign_id)} />
            ))}
          </div>
        )}
      </div>

      {detail && (
        <DetailDrawer detail={detail} onClose={() => setDetail(null)}
                                    onChanged={() => { openDetail(detail.campaign.campaign_id); load(); }} />
      )}
    </div>
  );
}


function CampaignRow({ c, onClick }) {
  const statusColor = {
    draft:              "text-slate-400",
    pending_admin: "text-fuchsia-500",
    active:            "text-emerald-500",
    paused:            "text-amber-500",
    completed:      "text-slate-500",
    cancelled:      "text-red-500",
  }[c.status] || "text-slate-400";
  return (
    <button onClick={onClick}
                    data-testid={`admin-pc-campaign-${c.campaign_id}`}
                    className="w-full text-left rounded-xl bg-slate-900/60
                                            border border-slate-800 hover:border-fuchsia-500/50
                                            transition p-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}>
              {c.status}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {c.currency === "bc"
                  ? <><Coins size={9} className="inline mr-0.5" />BigPoints</>
                  : <><Ticket size={9} className="inline mr-0.5" />USD voucher</>}
            </span>
            {c.admin_approval_required && (
              <span className="text-[10px] font-mono uppercase tracking-widest
                                                text-amber-500 ml-2 border border-amber-500/40
                                                px-1.5 py-0.5 rounded">
                approval required
              </span>
            )}
          </div>
          <div className="text-sm font-black truncate">
            {c.sponsor_message || "(no message)"}
          </div>
          <div className="text-[11px] font-mono text-slate-500 mt-0.5">
            {c.advertiser_business_id} · {c.podcast_id || "any podcast"} · {c.episode_id || "any episode"}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {c.awarded_count}/{c.max_total_completions} awarded ·
                    {" "}${(c.remaining_budget_cents / 100).toFixed(2)} remaining
                    of ${(c.total_budget_cents / 100).toFixed(2)}
          </div>
        </div>
        <ArrowRight size={16} className="text-slate-500 mt-1" />
      </div>
    </button>
  );
}


function DetailDrawer({ detail, onClose, onChanged }) {
  const c = detail.campaign || detail;
  const awards = detail.awards || [];
  const topEpisodes = detail.top_episodes || [];
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);

  const act = async (verb) => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/admin/podcast-completion-campaigns/${c.campaign_id}/${verb}`,
        { decision_note: note || null },
        { withCredentials: true });
      setNote("");
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start justify-end p-4 overflow-auto"
              data-testid="admin-pc-detail-drawer">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl
                                    w-full max-w-2xl shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4
                                        border-b border-slate-800">
          <div className="min-w-0">
            <div className="text-[10px] font-mono uppercase tracking-widest text-fuchsia-500">
              {c.status} · {c.currency}
            </div>
            <div className="text-sm font-black truncate mt-0.5">{c.sponsor_message}</div>
            <div className="text-[11px] font-mono text-slate-500 mt-0.5">
              {c.campaign_id} · {c.advertiser_business_id}
            </div>
          </div>
          <button onClick={onClose}
                          className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Reward" value={
              c.currency === "usd"
                ? `$${(c.points_reward / 100).toFixed(2)}`
                : `${c.points_reward} pts`} />
            <Stat label="Per completion cost"
                        value={`$${(c.cost_per_completion_cents / 100).toFixed(2)}`} />
            <Stat label="Total budget"
                        value={`$${(c.total_budget_cents / 100).toFixed(2)}`} />
            <Stat label="Awarded"
                        value={`${c.awarded_count}/${c.max_total_completions}`}
                        testId="admin-pc-detail-awarded" />
            <Stat label="Remaining"
                        value={`$${(c.remaining_budget_cents / 100).toFixed(2)}`} />
            <Stat label="Max per user" value={c.max_completions_per_user} />
          </div>

          {c.status === "pending_admin" && (
            <div className="rounded-xl bg-slate-950/60 border border-amber-500/40 p-4">
              <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-amber-500 mb-2">Admin decision required</div>
              <input type="text" value={note} onChange={(e) => setNote(e.target.value)}
                            placeholder="Decision note (optional)"
                            data-testid="admin-pc-decision-note"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-sm text-white mb-3" />
              <div className="flex gap-2">
                <button onClick={() => act("approve")} disabled={busy}
                                data-testid="admin-pc-approve"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                          bg-emerald-500 text-slate-950 hover:bg-emerald-400
                                                          disabled:opacity-40 inline-flex items-center
                                                          justify-center gap-1">
                  {busy ? <Loader2 className="w-3 h-3 animate-spin" /> :
                                  <CheckCircle2 className="w-3 h-3" />} Approve
                </button>
                <button onClick={() => act("reject")} disabled={busy}
                                data-testid="admin-pc-reject"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                          border border-red-500/40 text-red-400
                                                          hover:bg-red-500/10 inline-flex items-center
                                                          justify-center gap-1">
                  <XCircle className="w-3 h-3" /> Reject (refund)
                </button>
              </div>
              {err && (
                <div className="mt-2 text-xs text-red-400"
                            data-testid="admin-pc-decision-error">{err}</div>
              )}
            </div>
          )}

          {topEpisodes.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-slate-500 mb-2">Top episodes</div>
              <div className="space-y-1">
                {topEpisodes.map((ep) => (
                  <div key={ep.episode_id} className="flex items-center justify-between
                                                                              bg-slate-950/40 rounded px-3 py-1.5 text-xs"
                              data-testid={`admin-pc-top-episode-${ep.episode_id}`}>
                    <span className="font-mono truncate">{ep.episode_id}</span>
                    <span className="text-fuchsia-500 font-black">
                      {ep.award_count} awards
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {awards.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-slate-500 mb-2">
                Recent awards ({awards.length})
              </div>
              <div className="space-y-1 max-h-64 overflow-auto">
                {awards.slice(0, 20).map((a) => (
                  <div key={a.award_id}
                              data-testid={`admin-pc-award-${a.award_id}`}
                              className="flex items-center justify-between text-[11px]
                                                        bg-slate-950/40 rounded px-3 py-1.5">
                    <span className="font-mono text-slate-400 truncate">
                      {a.user_id}
                    </span>
                    <span className="text-fuchsia-500 font-mono">
                      {a.currency === "usd"
                        ? `$${(a.points_awarded / 100).toFixed(2)}`
                        : `+${a.points_awarded} pts`}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function Stat({ label, value, testId }) {
  return (
    <div className="rounded-lg bg-slate-950/60 border border-slate-800 p-3">
      <div className="text-[10px] font-mono uppercase tracking-widest
                                      text-slate-500">{label}</div>
      <div className="text-sm font-black mt-0.5" data-testid={testId}>{value}</div>
    </div>
  );
}
