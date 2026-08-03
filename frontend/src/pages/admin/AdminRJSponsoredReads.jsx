// Phase I — M1 Sponsored AI-RJ Reads · Admin moderation queue.
// Legacy dark shell.  Reviews the ≥$500 pending_admin backlog + all
// rejected/cancelled/completed reads with an inline audio player.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, Radio, ArrowLeft, ShieldCheck, ShieldAlert, PlayCircle,
  Check, X, Volume2,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "pending_admin", "active", "completed",
                                  "cancelled", "rejected"];


export default function AdminRJSponsoredReads() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("pending_admin");
  const [sel, setSel] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(
        `${API}/admin/rj-sponsored-reads?${p}`,
        { withCredentials: true });
      setItems(data.items || []);
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
      setItems([]);
    }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="min-h-screen bg-slate-950 text-white p-6"
              data-testid="admin-rj-sponsored-reads-page">
      <div className="max-w-6xl mx-auto">
        <Link to="/admin" className="inline-flex items-center gap-2 text-sm
                                                                  text-slate-400 hover:text-white mb-4"
                    data-testid="admin-rjsr-back">
          <ArrowLeft size={16} /> Back to admin
        </Link>
        <h1 className="text-2xl font-black inline-flex items-center gap-2 mb-1">
          <Radio className="text-fuchsia-500" size={24} />
          AI-RJ Sponsored Reads
        </h1>
        <p className="text-sm text-slate-400 mb-6">
          Approve or reject over-threshold sponsored host reads before they
          go live on the AI-RJ stream.
        </p>

        <div className="flex flex-wrap gap-1.5 mb-4">
          {STATUSES.map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)}
                            data-testid={`admin-rjsr-filter-${s || "all"}`}
                            className={`text-[10px] font-mono uppercase tracking-widest
                                                        px-3 py-1.5 rounded-full border transition ${
                                                            status === s
                                                                ? "border-fuchsia-500 bg-fuchsia-500/10 text-fuchsia-400"
                                                                : "border-slate-800 text-slate-400 hover:bg-slate-800/40"}`}>
              {s || "All"}
            </button>
          ))}
        </div>

        {err && (
          <div className="rounded-lg bg-red-500/10 border border-red-500/40
                                        text-red-400 text-xs px-3 py-2 mb-3"
                      data-testid="admin-rjsr-error">{err}</div>
        )}

        {items === null ? (
          <div className="text-slate-400 inline-flex items-center gap-2"
                      data-testid="admin-rjsr-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl bg-slate-900/60 border border-slate-800
                                        p-6 text-center text-sm text-slate-500"
                      data-testid="admin-rjsr-empty">
            No sponsored reads in this state.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((s) => (
              <ReadRow key={s.sponsored_read_id} s={s}
                                          onOpen={() => setSel(s)} />
            ))}
          </div>
        )}
      </div>

      {sel && (
        <DetailDrawer s={sel}
                                    onClose={() => setSel(null)}
                                    onChanged={() => { setSel(null); load(); }} />
      )}
    </div>
  );
}


function ReadRow({ s, onOpen }) {
  const statusColor = {
    pending_admin: "text-fuchsia-400",
    active:            "text-emerald-500",
    completed:      "text-slate-400",
    cancelled:      "text-red-400",
    rejected:        "text-red-400",
  }[s.status] || "text-slate-400";
  const progress = s.plays_target > 0
    ? Math.round((s.plays_delivered / s.plays_target) * 100) : 0;
  return (
    <button onClick={onOpen}
                    data-testid={`admin-rjsr-row-${s.sponsored_read_id}`}
                    className="w-full text-left rounded-xl bg-slate-900/60
                                              border border-slate-800 p-4
                                              hover:border-slate-700 transition">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`admin-rjsr-status-${s.sponsored_read_id}`}>
              {s.status}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {s.persona_name || s.persona_id}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {s.any_station ? "any station" : `${(s.station_ids || []).length} stations`}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {s.disclosure_prefix}
            </span>
          </div>
          <div className="text-sm font-black truncate">
            {s.final_script || s.script_body || "(no script yet)"}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            adv: {s.advertiser_business_id}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
            Total charge
          </div>
          <div className="text-lg font-black">
            ${(s.total_cost_cents / 100).toFixed(2)}
          </div>
          <div className="text-[10px] font-mono text-slate-500">
            {s.plays_delivered}/{s.plays_target} plays
          </div>
        </div>
      </div>
      <div className="mt-2 h-1 rounded-full bg-slate-800 overflow-hidden">
        <div className="h-full bg-fuchsia-500" style={{ width: `${progress}%` }} />
      </div>
    </button>
  );
}


function DetailDrawer({ s, onClose, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);

  const decide = async (verb) => {
    if (verb === "reject" && !note.trim()) {
      setErr("admin_notes_required_for_reject");
      return;
    }
    setBusy(verb); setErr(null);
    try {
      await axios.post(
        `${API}/admin/rj-sponsored-reads/${s.sponsored_read_id}/${verb}`,
        { admin_notes: note.trim() || null },
        { withCredentials: true });
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally {
      setBusy(null);
    }
  };

  const mod = s.moderation_result || {};

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start sm:items-center justify-center p-4 overflow-auto"
              data-testid="admin-rjsr-detail-drawer">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl
                                    w-full max-w-lg text-white shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <Radio size={14} className="text-fuchsia-500" />
            {s.status === "pending_admin" ? "Review sponsored read" : "Sponsored read"}
          </h3>
          <button onClick={onClose} className="text-slate-400"
                          data-testid="admin-rjsr-detail-close"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3 text-sm">
          <MetaRow label="Advertiser" value={s.advertiser_business_id}
                              testId={`admin-rjsr-detail-advertiser-${s.sponsored_read_id}`} />
          <MetaRow label="Persona" value={s.persona_name || s.persona_id} />
          <MetaRow label="Disclosure prefix" value={s.disclosure_prefix} />
          <MetaRow label="Target"
                              value={s.any_station
                                            ? "Any station"
                                            : (s.station_ids || []).join(", ") || "—"} />
          <MetaRow label="Budget"
                              value={`$${(s.total_cost_cents / 100).toFixed(2)} · ${s.plays_target} plays × $${(s.cost_per_play_cents / 100).toFixed(2)}`}
                              testId="admin-rjsr-detail-cost" />
          <MetaRow label="Plays delivered"
                              value={`${s.plays_delivered} / ${s.plays_target}`}
                              testId="admin-rjsr-detail-plays" />
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-slate-500 mb-1">Final script</div>
            <div className="rounded-lg bg-slate-950/60 border border-slate-800
                                            p-3 text-sm whitespace-pre-wrap"
                        data-testid="admin-rjsr-detail-script">
              {s.final_script || "(pending advertiser edit)"}
            </div>
          </div>
          {s.audio_url && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                              text-slate-500 mb-1 inline-flex items-center gap-1">
                <Volume2 size={11} /> Audio preview · {s.duration_seconds
                    ? `${s.duration_seconds.toFixed(1)}s` : "?"}
              </div>
              <audio controls src={s.audio_url}
                              className="w-full"
                              data-testid={`admin-rjsr-detail-audio-${s.sponsored_read_id}`} />
            </div>
          )}
          <div className={`rounded-lg p-3 text-xs ${
                                            mod.flagged
                                                ? "bg-red-500/10 border border-red-500/40"
                                                : "bg-emerald-500/10 border border-emerald-500/30"}`}
                      data-testid="admin-rjsr-detail-moderation">
            <div className="font-black inline-flex items-center gap-1.5">
              {mod.flagged
                ? <><ShieldAlert size={12} className="text-red-400" /> Moderation flagged</>
                : <><ShieldCheck size={12} className="text-emerald-400" /> Moderation clean</>}
            </div>
            <div className="mt-1 text-slate-400 font-mono text-[10px]">
              action: {mod.action_taken || "—"} · highest: {mod.highest_category || "—"} · score: {(mod.highest_score || 0).toFixed(3)}
            </div>
          </div>

          {s.status === "pending_admin" && (
            <>
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest text-slate-500 block mb-1">
                  Admin note (required to reject)
                </label>
                <textarea value={note} onChange={(e) => setNote(e.target.value)}
                                        data-testid="admin-rjsr-decision-note"
                                        rows={2} maxLength={280}
                                        placeholder="Optional for approval · required for reject."
                                        className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                                  border border-slate-800 text-white text-xs" />
              </div>
              {err && <div className="text-xs text-red-400"
                                            data-testid="admin-rjsr-decision-error">{err}</div>}
              <div className="flex gap-2">
                <button onClick={() => decide("approve")} disabled={!!busy}
                                data-testid="admin-rjsr-approve"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                        bg-emerald-500 text-slate-950 hover:bg-emerald-400
                                                        disabled:opacity-40 inline-flex items-center
                                                        justify-center gap-1.5">
                  {busy === "approve" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                                          <Check size={12} />} Approve
                </button>
                <button onClick={() => decide("reject")} disabled={!!busy}
                                data-testid="admin-rjsr-reject"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                        border border-red-500/40 text-red-400
                                                        hover:bg-red-500/10 disabled:opacity-40
                                                        inline-flex items-center justify-center gap-1.5">
                  {busy === "reject" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                                          <X size={12} />} Reject + refund
                </button>
              </div>
            </>
          )}
          {s.admin_notes && (
            <div className="text-[11px] text-slate-500"
                        data-testid="admin-rjsr-detail-notes">
              Admin notes: {s.admin_notes}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}


function MetaRow({ label, value, testId }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
        {label}
      </span>
      <span className="text-xs font-mono text-white truncate max-w-[65%]"
                  data-testid={testId}>{value}</span>
    </div>
  );
}
