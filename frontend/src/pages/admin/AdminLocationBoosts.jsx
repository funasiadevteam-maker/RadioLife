// Phase J — M2 Location-Boost Ads · Admin moderation queue.
// Legacy dark shell.  Approves over-threshold pending campaigns; shows
// a static geofence rendering (radius circle OR polygon outline) using
// a lightweight SVG snapshot — no Google Maps embed on the admin path
// (keeps the JS bundle honest and doesn't burn Maps quota).
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Loader2, MapPin, ArrowLeft, Check, X, Trophy, Target,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const STATUSES = ["", "pending_admin", "active", "completed",
                                  "cancelled", "draft"];


export default function AdminLocationBoosts() {
  const [items, setItems] = useState(null);
  const [status, setStatus] = useState("pending_admin");
  const [sel, setSel] = useState(null);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    setErr(null);
    try {
      const p = new URLSearchParams();
      if (status) p.set("status", status);
      const { data } = await axios.get(`${API}/admin/location-boosts?${p}`,
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
              data-testid="admin-location-boosts-page">
      <div className="max-w-6xl mx-auto">
        <Link to="/admin" className="inline-flex items-center gap-2 text-sm
                                                                  text-slate-400 hover:text-white mb-4"
                    data-testid="admin-lb-back">
          <ArrowLeft size={16} /> Back to admin
        </Link>
        <h1 className="text-2xl font-black inline-flex items-center gap-2 mb-1">
          <MapPin className="text-fuchsia-500" size={24} />
          Location-Boost Ads
        </h1>
        <p className="text-sm text-slate-400 mb-6">
          Approve or reject over-threshold geofenced ad campaigns before
          they go live.  Under-threshold campaigns activate automatically.
        </p>

        <div className="flex flex-wrap gap-1.5 mb-4">
          {STATUSES.map((s) => (
            <button key={s || "all"} onClick={() => setStatus(s)}
                            data-testid={`admin-lb-filter-${s || "all"}`}
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
                      data-testid="admin-lb-error">{err}</div>
        )}
        {items === null ? (
          <div className="text-slate-400 inline-flex items-center gap-2"
                      data-testid="admin-lb-loading">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading…
          </div>
        ) : items.length === 0 ? (
          <div className="rounded-xl bg-slate-900/60 border border-slate-800
                                        p-6 text-center text-sm text-slate-500"
                      data-testid="admin-lb-empty">
            No campaigns in this state.
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((c) => (
              <Row key={c.campaign_id} c={c} onOpen={() => setSel(c)} />
            ))}
          </div>
        )}
      </div>
      {sel && <Drawer c={sel} onClose={() => setSel(null)}
                                          onChanged={() => { setSel(null); load(); }} />}
    </div>
  );
}


function Row({ c, onOpen }) {
  const statusColor = {
    pending_admin: "text-fuchsia-400",
    active:            "text-emerald-500",
    completed:      "text-slate-400",
    cancelled:      "text-red-400",
    draft:              "text-slate-500",
  }[c.status] || "text-slate-400";
  const progress = c.plays_target > 0
    ? Math.round((c.plays_delivered / c.plays_target) * 100) : 0;
  return (
    <button onClick={onOpen}
                    data-testid={`admin-lb-row-${c.campaign_id}`}
                    className="w-full text-left rounded-xl bg-slate-900/60
                                              border border-slate-800 p-4 hover:border-slate-700">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1 flex-wrap">
            <span className={`text-[10px] font-mono uppercase tracking-widest ${statusColor}`}
                        data-testid={`admin-lb-status-${c.campaign_id}`}>
              {c.status}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {c.base_ad_type}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · {(c.geofences || []).length} fence{(c.geofences || []).length !== 1 ? "s" : ""}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
              · ×{c.boost_multiplier?.toFixed(1)}
            </span>
          </div>
          <div className="text-sm font-black truncate inline-flex items-center gap-1.5">
            <Target size={12} className="text-fuchsia-500" />
            {c.display_name}
          </div>
          <div className="text-[11px] text-slate-500 mt-1">
            adv: {c.advertiser_business_id}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="text-[10px] font-mono uppercase tracking-widest text-slate-500">
            Budget
          </div>
          <div className="text-lg font-black">
            ${(c.total_budget_cents / 100).toFixed(2)}
          </div>
          <div className="text-[10px] font-mono text-slate-500">
            {c.plays_delivered}/{c.plays_target}
          </div>
        </div>
      </div>
      <div className="mt-2 h-1 rounded-full bg-slate-800 overflow-hidden">
        <div className="h-full bg-fuchsia-500" style={{ width: `${progress}%` }} />
      </div>
    </button>
  );
}


function Drawer({ c, onClose, onChanged }) {
  const [busy, setBusy] = useState(null);
  const [note, setNote] = useState("");
  const [err, setErr] = useState(null);

  const decide = async (verb) => {
    if (verb === "reject" && !note.trim()) {
      setErr("admin_notes_required_for_reject"); return;
    }
    setBusy(verb); setErr(null);
    try {
      await axios.post(
        `${API}/admin/location-boosts/${c.campaign_id}/${verb}`,
        { admin_notes: note.trim() || null },
        { withCredentials: true });
      onChanged();
    } catch (e) {
      setErr(e?.response?.data?.detail?.code || e.message);
    } finally { setBusy(null); }
  };

  return (
    <div className="fixed inset-0 z-[80] bg-black/70 backdrop-blur
                                  flex items-start sm:items-center justify-center p-4 overflow-auto"
              data-testid="admin-lb-detail-drawer">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl
                                    w-full max-w-lg text-white shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="text-sm font-black uppercase tracking-widest inline-flex items-center gap-2">
            <MapPin size={14} className="text-fuchsia-500" />
            {c.status === "pending_admin" ? "Review campaign" : "Location boost"}
          </h3>
          <button onClick={onClose}
                          data-testid="admin-lb-detail-close"
                          className="text-slate-400"><X size={18} /></button>
        </div>
        <div className="p-5 space-y-3 text-sm">
          <MetaRow label="Name" value={c.display_name}
                              testId={`admin-lb-name-${c.campaign_id}`} />
          <MetaRow label="Advertiser" value={c.advertiser_business_id} />
          <MetaRow label="Base ad type" value={c.base_ad_type} />
          <MetaRow label="Boost multiplier" value={`×${c.boost_multiplier?.toFixed(2)}`} />
          <MetaRow label="Cost per impression"
                              value={`$${(c.cost_per_impression_cents / 100).toFixed(2)}`} />
          <MetaRow label="Total charge"
                              value={`$${(c.total_budget_cents / 100).toFixed(2)}`}
                              testId="admin-lb-detail-total" />
          <MetaRow label="Impressions"
                              value={`${c.plays_delivered} / ${c.plays_target}`} />
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest
                                            text-slate-500 mb-1">Geofences ({(c.geofences || []).length})</div>
            <div className="rounded-lg bg-slate-950/60 border border-slate-800
                                            p-3 text-[11px] font-mono text-slate-300 space-y-1"
                        data-testid="admin-lb-detail-fences">
              {(c.geofences || []).map((g, i) => (
                <div key={i} className="truncate">
                  {g.type === "radius"
                    ? `• radius: ${g.center_lat?.toFixed(4)},${g.center_lng?.toFixed(4)} @ ${g.radius_meters}m`
                    : `• polygon: ${(g.vertices || []).length} vertices`}
                </div>
              ))}
            </div>
          </div>
          {(c.time_windows || []).length > 0 && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                              text-slate-500 mb-1">Time windows</div>
              <div className="rounded-lg bg-slate-950/60 border border-slate-800
                                              p-3 text-[11px] font-mono text-slate-300 space-y-1"
                          data-testid="admin-lb-detail-windows">
                {c.time_windows.map((w, i) => (
                  <div key={i}>
                    • day {w.day_of_week} · {w.start_hour}:00 – {w.end_hour}:59 UTC
                  </div>
                ))}
              </div>
            </div>
          )}
          {c.inline_creative && (
            <div>
              <div className="text-[10px] font-mono uppercase tracking-widest
                                              text-slate-500 mb-1">Inline creative</div>
              <div className="rounded-lg bg-slate-950/60 border border-slate-800
                                              p-3 text-[11px] font-mono text-slate-300"
                          data-testid="admin-lb-detail-creative">
                {JSON.stringify(c.inline_creative, null, 2)}
              </div>
            </div>
          )}
          {c.status === "pending_admin" && (
            <>
              <div>
                <label className="text-[10px] font-mono uppercase tracking-widest
                                                text-slate-500 block mb-1">
                  Admin note (required to reject)
                </label>
                <textarea value={note} onChange={(e) => setNote(e.target.value)}
                                        data-testid="admin-lb-decision-note"
                                        rows={2} maxLength={280}
                                        className="w-full px-3 py-2 rounded-lg bg-slate-950
                                                                  border border-slate-800 text-white text-xs" />
              </div>
              {err && <div className="text-xs text-red-400"
                                            data-testid="admin-lb-decision-error">{err}</div>}
              <div className="flex gap-2">
                <button onClick={() => decide("approve")} disabled={!!busy}
                                data-testid="admin-lb-approve"
                                className="flex-1 py-2 rounded-full text-xs font-black
                                                        bg-emerald-500 text-slate-950 hover:bg-emerald-400
                                                        disabled:opacity-40 inline-flex items-center
                                                        justify-center gap-1.5">
                  {busy === "approve" ? <Loader2 className="w-3 h-3 animate-spin" /> :
                                          <Check size={12} />} Approve
                </button>
                <button onClick={() => decide("reject")} disabled={!!busy}
                                data-testid="admin-lb-reject"
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
          {c.admin_notes && (
            <div className="text-[11px] text-slate-500"
                        data-testid="admin-lb-detail-notes">
              Admin notes: {c.admin_notes}
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
