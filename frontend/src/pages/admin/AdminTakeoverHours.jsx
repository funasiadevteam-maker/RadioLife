// Phase L — M5 Radio Takeover Hour · Admin moderation queue.
// Legacy dark theme (admin surfaces are always Legacy).
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import {
  Loader2, ArrowLeft, Check, X, Radio, AlertTriangle,
} from "lucide-react";
import { Link } from "react-router-dom";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "pending_admin", "pending_moderation",
                  "active", "live", "completed", "cancelled",
                  "rejected"];


export default function AdminTakeoverHours() {
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
        `${API}/admin/takeover-hours?${p}`, { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="admin-takeover-hours-page"
         className="min-h-screen bg-slate-950 text-white p-6">
      <Link to="/admin" data-testid="admin-th-back"
            className="inline-flex items-center gap-2 text-xs text-slate-400
                       hover:text-white mb-4">
        <ArrowLeft size={12} /> Back to admin
      </Link>
      <h1 className="text-2xl font-black inline-flex items-center gap-2">
        <Radio className="text-orange-500" size={22} />
        Radio Takeover Hours — Moderation
      </h1>

      <div className="flex flex-wrap gap-1.5 mt-3 mb-5">
        {STATUSES.map((s) => (
          <button key={s || "all"} onClick={() => setStatus(s)}
                  data-testid={`admin-th-filter-${s || "all"}`}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold border ${
                    status === s
                      ? "bg-white text-slate-900 border-white"
                      : "border-white/10 text-slate-300"}`}>
            {s || "All"}
          </button>
        ))}
      </div>

      {items === null && (
        <div className="text-slate-400 inline-flex items-center gap-2"
             data-testid="admin-th-loading">
          <Loader2 size={16} className="animate-spin" /> Loading…
        </div>
      )}
      {items?.length === 0 && (
        <div className="text-slate-400 text-sm"
             data-testid="admin-th-empty">
          No takeovers.
        </div>
      )}
      {err && (
        <div data-testid="admin-th-error"
             className="text-red-400 text-xs">{err}</div>
      )}

      <div className="grid gap-3">
        {(items || []).map((it) => (
          <div key={it.id} data-testid={`admin-th-row-${it.id}`}
               className="rounded-2xl p-4 bg-white/5 border border-white/10
                          hover:bg-white/10 cursor-pointer transition-colors"
               onClick={() => setDetail(it)}>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <div>
                <div className="font-black">
                  {it.branded_overlay?.advertiser_name || "Takeover"}
                  <span data-testid={`admin-th-status-${it.id}`}
                        className={`ml-2 text-[10px] px-2 py-0.5 rounded-full font-bold ${
                          it.status === "live"
                            ? "bg-orange-500"
                            : it.status === "pending_admin"
                                ? "bg-amber-500"
                                : it.status === "cancelled"
                                    ? "bg-slate-600"
                                    : "bg-emerald-500"}`}>
                    {it.status}
                  </span>
                </div>
                <div className="text-[11px] text-slate-400 mt-1">
                  {it.station_scope} ·{" "}
                  {it.station_id || it.region_code || "global"} ·{" "}
                  {new Date(it.start_at).toLocaleString()}
                </div>
              </div>
              <div className="text-right">
                <div className="font-black text-sm">
                  ${((it.total_cost_cents || 0) / 100).toFixed(2)}
                </div>
                <div className="text-[10px] text-slate-400">
                  {(it.rj_scripts || []).length} blocks ·{" "}
                  {(it.featured_deal_refs || []).length} deals ·{" "}
                  bonus {it.bonus_giveaway?.prize_type || "—"}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>

      {detail && (
        <DetailDrawer detail={detail} onClose={() => setDetail(null)}
                      reload={load} />
      )}
    </div>
  );
}


function DetailDrawer({ detail, onClose, reload }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const decide = async (action) => {
    setBusy(true); setErr(null);
    try {
      await axios.post(
        `${API}/admin/takeover-hours/${detail.id}/${action}`,
        { admin_notes: note },
        { withCredentials: true });
      await reload();
      onClose();
    } catch (e) {
      setErr(e?.response?.data?.detail?.detail
             || e?.response?.data?.detail?.code
             || e.message);
    }
    setBusy(false);
  };

  return (
    <div data-testid="admin-th-detail-drawer"
         className="fixed inset-0 z-40 bg-black/70 flex items-center
                    justify-center p-4">
      <div className="w-full max-w-2xl rounded-3xl bg-slate-900 border
                      border-white/10 p-6 max-h-[85vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <div className="font-black text-lg inline-flex items-center gap-2">
            <Radio size={18} className="text-orange-500" />
            {detail.branded_overlay?.advertiser_name}
          </div>
          <button onClick={onClose}
                  data-testid="admin-th-detail-close"
                  className="text-slate-400 hover:text-white">
            <X size={18} />
          </button>
        </div>

        <div className="grid grid-cols-2 gap-3 text-xs mb-4">
          <Kv k="Status" v={detail.status} />
          <Kv k="Total" v={`$${((detail.total_cost_cents || 0) / 100)
                                 .toFixed(2)}`}
              testid="admin-th-detail-total" />
          <Kv k="Media" v={`$${((detail.media_cost_cents || 0) / 100)
                                 .toFixed(2)}`} />
          <Kv k="Fee (40%)"
              v={`$${((detail.platform_fee_cents || 0) / 100).toFixed(2)}`} />
          <Kv k="Scope"
              v={`${detail.station_scope} · ${
                    detail.station_id || detail.region_code || "global"}`} />
          <Kv k="Persona"
              v={detail.rj_persona_name || detail.rj_persona_id} />
          <Kv k="Starts" v={new Date(detail.start_at).toLocaleString()} />
          <Kv k="Ends" v={new Date(detail.end_at).toLocaleString()} />
        </div>

        <div className="text-xs mb-3">
          <div className="font-bold mb-1 text-slate-300">
            Branded overlay
          </div>
          <div className="p-3 rounded-xl bg-white/5 border border-white/10
                          text-slate-200">
            {detail.branded_overlay?.tagline || "(no tagline)"}
            {detail.branded_overlay?.cta_url && (
              <span className="ml-2 text-slate-400">
                → {detail.branded_overlay.cta_url}
              </span>
            )}
          </div>
        </div>

        <div className="text-xs mb-3">
          <div className="font-bold mb-1 text-slate-300">
            RJ scripts ({(detail.rj_scripts || []).length})
          </div>
          {(detail.rj_scripts || []).map((s) => (
            <div key={s.block_index}
                 className="mt-2 p-3 rounded-xl bg-white/5 border
                            border-white/10">
              <div className="font-bold text-slate-300 mb-1">
                Block {s.block_index}
                {s.audio_url && (
                  <a href={s.audio_url} target="_blank" rel="noreferrer"
                     className="ml-2 text-orange-400 underline"
                     data-testid={`admin-th-detail-block-audio-${s.block_index}`}>
                    audio
                  </a>
                )}
              </div>
              <div className="text-slate-200 whitespace-pre-wrap">
                {s.script_text}
              </div>
            </div>
          ))}
        </div>

        <div className="text-xs mb-3">
          <div className="font-bold mb-1 text-slate-300">
            Featured deals ({(detail.featured_deal_refs || []).length})
          </div>
          {(detail.featured_deal_refs || []).map((r, i) => (
            <div key={i} className="text-slate-300">
              · {r.source_type} :: {r.source_id}
            </div>
          ))}
        </div>

        <div className="text-xs mb-3">
          <div className="font-bold mb-1 text-slate-300">
            Bonus giveaway
          </div>
          <div className="text-slate-200">
            After {detail.bonus_giveaway?.threshold_listen_seconds || 0}s,{" "}
            award {detail.bonus_giveaway?.prize_amount || 0}{" "}
            {detail.bonus_giveaway?.prize_type || "—"}
            {detail.bonus_giveaway?.max_winners
              ? ` (max ${detail.bonus_giveaway.max_winners})` : ""}
          </div>
        </div>

        {detail.moderation_result && (
          <div className="text-xs mb-3">
            <div className="font-bold mb-1 text-slate-300">
              Moderation result
            </div>
            <pre className="text-[10px] p-2 rounded-xl bg-black/40
                            text-slate-300 overflow-x-auto">
              {JSON.stringify(detail.moderation_result, null, 2)}
            </pre>
          </div>
        )}

        {detail.status === "pending_admin" && (
          <>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Notes for the advertiser (optional)"
              data-testid="admin-th-decision-note"
              className="w-full mt-2 rounded-lg bg-white/5 border
                         border-white/10 p-2 text-xs text-white" />
            <div className="flex gap-2 mt-3">
              <button onClick={() => decide("approve")} disabled={busy}
                      data-testid="admin-th-approve"
                      className="flex-1 py-2 rounded-full bg-emerald-500
                                 hover:bg-emerald-400 text-white text-xs
                                 font-black disabled:opacity-40
                                 inline-flex items-center justify-center gap-1">
                <Check size={12} /> {busy ? "…" : "Approve"}
              </button>
              <button onClick={() => decide("reject")} disabled={busy}
                      data-testid="admin-th-reject"
                      className="flex-1 py-2 rounded-full bg-red-500
                                 hover:bg-red-400 text-white text-xs
                                 font-black disabled:opacity-40
                                 inline-flex items-center justify-center gap-1">
                <X size={12} /> {busy ? "…" : "Reject + refund"}
              </button>
            </div>
            {err && (
              <div data-testid="admin-th-decision-error"
                   className="text-red-400 text-xs mt-2">{err}</div>
            )}
          </>
        )}
      </div>
    </div>
  );
}


function Kv({ k, v, testid }) {
  return (
    <div>
      <div className="text-[10px] uppercase text-slate-500 font-bold
                      tracking-wide">
        {k}
      </div>
      <div className="text-slate-200" data-testid={testid}>{v || "—"}</div>
    </div>
  );
}
