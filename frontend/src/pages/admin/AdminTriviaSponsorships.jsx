// Phase H — AD.5 Trivia Sponsorship · Admin page (Legacy dark).
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, Sparkles, CheckCircle2, XCircle, ArrowRight, X,
  AlertTriangle, Trophy,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "draft", "pending_admin", "active", "paused",
                                    "completed", "cancelled"];


export default function AdminTriviaSponsorships() {
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
        `${API}/admin/trivia-sponsorships?${p}`, { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  const openDetail = async (id) => {
    try {
      const { data } = await axios.get(
        `${API}/admin/trivia-sponsorships/${id}`, { withCredentials: true });
      setDetail(data);
    } catch { setDetail(null); }
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white"
              data-testid="admin-trivia-sponsorships-page">
      <div className="max-w-5xl mx-auto px-6 py-8">
        <Link to="/admin" className="text-xs text-slate-400 hover:text-white
                                                                  inline-flex items-center gap-1 mb-4">← Admin</Link>
        <h1 className="text-3xl font-black inline-flex items-center gap-2 mb-1">
          <Sparkles className="text-fuchsia-500" size={28} />
          Trivia Sponsorships
        </h1>
        <p className="text-slate-400 text-sm mb-6">
          Advertiser-funded prize pools attached to trivia rooms or categories.
          Sponsorships with ≥ $500 budget require admin approval before going live.
        </p>

        <div className="flex flex-wrap gap-1.5 mb-6">
          {STATUSES.map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)}
                            data-testid={`admin-ts-filter-${s || "all"}`}
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
                      data-testid="admin-ts-error">{err}</div>
        )}
        {items === null ? (
          <div className="text-slate-400 inline-flex items-center gap-2"
                      data-testid="admin-ts-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-2xl bg-slate-900/60 border border-slate-800
                                        p-8 text-center text-slate-400 text-sm"
                      data-testid="admin-ts-empty">
            No sponsorships in this state.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((s) => (
              <SponsorshipRow key={s.sponsorship_id} s={s}
                                                onClick={() => openDetail(s.sponsorship_id)} />
            ))}
          </div>
        )}
      </div>

      {detail && (
        <DetailDrawer detail={detail} onClose={() => setDetail(null)}
                                    onChanged={() => { openDetail(detail.sponsorship.sponsorship_id); load(); }} />
      )}
    </div>
  );
}


function SponsorshipRow({ s, onClick }) {
  const statusColor = {
    draft:              "text-slate-400",
    pending_admin: "text-fuchsia-500",
    active:            "text-emerald-500",
    completed:      "text-slate-500",
    cancelled:      "text-red-500",
  }[s.status] || "text-slate-400";
  return (
    <button onClick={onClick}
                    data-testid={`admin-ts-sponsorship-${s.sponsorship_id}`}
                    className="w-full text-left rounded-xl bg-slate-900/60
                                            border border-slate-800 hover:border-fuchsia-500/50
                                            transition p-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}>
              {s.status}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {s.sponsor_target_type} · {s.target_id || "any"}
            </span>
            {s.admin_approval_required && (
              <span className="text-[10px] font-mono uppercase tracking-widest
                                              text-amber-500 ml-2 border border-amber-500/40
                                              px-1.5 py-0.5 rounded">
                approval required
              </span>
            )}
          </div>
          <div className="text-sm font-black truncate">{s.display_name}</div>
          <div className="text-[11px] font-mono text-slate-500 mt-0.5 truncate">
            {s.advertiser_business_id} · {s.winner_selection}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">
            {s.awarded_count}/{s.max_total_awards} awarded ·
            ${(s.remaining_budget_cents / 100).toFixed(2)} remaining
            of ${(s.cost_cents / 100).toFixed(2)}
          </div>
        </div>
        <ArrowRight size={16} className="text-slate-500 mt-1" />
      </div>
    </button>
  );
}


function DetailDrawer({ detail, onClose, onChanged }) {
  const s = detail.sponsorship || detail;
  const stats = detail.stats || {};
  const awards = detail.awards || [];
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);

  const act = async (verb) => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/admin/trivia-sponsorships/${s.sponsorship_id}/${verb}`,
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
              data-testid="admin-ts-detail-drawer">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl
                                    w-full max-w-2xl shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4
                                        border-b border-slate-800">
          <div className="min-w-0">
            <div className="text-[10px] font-mono uppercase tracking-widest text-fuchsia-500">
              {s.status} · {s.sponsor_target_type}
            </div>
            <div className="text-sm font-black truncate mt-0.5">{s.display_name}</div>
            <div className="text-[11px] font-mono text-slate-500 mt-0.5">
              {s.sponsorship_id}
            </div>
          </div>
          <button onClick={onClose}
                          className="text-slate-400 hover:text-white"><X size={18} /></button>
        </div>

        <div className="p-5 space-y-4">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Total budget" value={`$${(s.cost_cents / 100).toFixed(2)}`} />
            <Stat label="Platform fee (25%)" value={`$${(s.platform_fee_cents / 100).toFixed(2)}`} />
            <Stat label="Remaining" value={`$${(s.remaining_budget_cents / 100).toFixed(2)}`} />
            <Stat label="Awarded"
                        value={`${s.awarded_count}/${s.max_total_awards}`}
                        testId="admin-ts-detail-awarded" />
            <Stat label="Claimed" value={stats.claimed || 0} />
            <Stat label="Redemption rate"
                        value={`${Math.round((stats.redemption_rate || 0) * 100)}%`} />
          </div>

          {s.status === "pending_admin" && (
            <div className="rounded-xl bg-slate-950/60 border border-amber-500/40 p-4">
              <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-amber-500 mb-2">Admin decision required</div>
              <input type="text" value={note} onChange={(e) => setNote(e.target.value)}
                            placeholder="Decision note (optional)"
                            data-testid="admin-ts-decision-note"
                            className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                  border border-slate-800 text-sm text-white mb-3" />
              <div className="flex gap-2">
                <button onClick={() => act("approve")} disabled={busy}
                                data-testid="admin-ts-approve"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                          bg-emerald-500 text-slate-950 hover:bg-emerald-400
                                                          disabled:opacity-40 inline-flex items-center
                                                          justify-center gap-1">
                  {busy ? <Loader2 className="w-3 h-3 animate-spin" /> :
                                  <CheckCircle2 className="w-3 h-3" />} Approve
                </button>
                <button onClick={() => act("reject")} disabled={busy}
                                data-testid="admin-ts-reject"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                          border border-red-500/40 text-red-400
                                                          hover:bg-red-500/10 inline-flex items-center
                                                          justify-center gap-1">
                  <XCircle className="w-3 h-3" /> Reject (refund)
                </button>
              </div>
              {err && (
                <div className="mt-2 text-xs text-red-400"
                            data-testid="admin-ts-decision-error">{err}</div>
              )}
            </div>
          )}

          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-slate-500 mb-2">Prize pool</div>
            <div className="space-y-1">
              {(s.prize_pool || []).map((p) => (
                <div key={p.rank} className="flex items-center justify-between
                                                                            bg-slate-950/40 rounded px-3 py-1.5 text-xs"
                            data-testid={`admin-ts-prize-${p.rank}`}>
                  <span>Rank #{p.rank} · ×{p.quantity || 1}</span>
                  <span className="text-fuchsia-500 font-black">
                    {p.currency === "usd"
                      ? `$${(p.points_reward / 100).toFixed(2)}`
                      : `+${p.points_reward} bc`}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {awards.length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-slate-500 mb-2">
                Awards ({awards.length})
              </div>
              <div className="space-y-1 max-h-64 overflow-auto">
                {awards.slice(0, 30).map((a) => (
                  <div key={a.award_id}
                              data-testid={`admin-ts-award-${a.award_id}`}
                              className="flex items-center justify-between text-[11px]
                                                        bg-slate-950/40 rounded px-3 py-1.5">
                    <span className="font-mono text-slate-400 truncate">
                      #{a.rank} · {a.user_name || a.user_id}
                    </span>
                    <span className="text-fuchsia-500 font-mono">
                      {a.currency === "usd"
                        ? `$${(a.points_awarded / 100).toFixed(2)}`
                        : `+${a.points_awarded} bc`}
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
      <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className="text-sm font-black mt-0.5" data-testid={testId}>{value}</div>
    </div>
  );
}
