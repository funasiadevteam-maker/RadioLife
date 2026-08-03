// Phase ADMOD.1 — Ad Review Detail Modal
// Full creative preview + AI moderation + Approve/Reject/Require-Changes/Block.
import { useEffect, useState } from "react";
import axios from "axios";
import {
  X, CheckCircle2, XCircle, RotateCw, Ban, Loader2, Sparkles,
  Store, Megaphone, AlertTriangle,
} from "lucide-react";

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

export default function AdReviewDetailModal({ reviewId, light, onClose, onDone }) {
  const [detail, setDetail] = useState(null);
  const [busy, setBusy] = useState(false);
  const [action, setAction] = useState(null);   // approve|reject|require-changes|block|null
  const [notes, setNotes] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!reviewId) return;
    axios.get(`${API}/ad-review/queue/${reviewId}`, { withCredentials: true })
      .then((r) => setDetail(r.data))
      .catch((e) => setError(e?.response?.data?.detail?.code || e.message));
  }, [reviewId]);

  async function run() {
    if (!action) return;
    setBusy(true);
    try {
      if (action === "approve") {
        await axios.post(`${API}/ad-review/queue/${reviewId}/approve`,
                                                { notes }, { withCredentials: true });
        onDone("Approved.");
      } else if (action === "reject") {
        if (!reason.trim()) { setError("Reason is required"); setBusy(false); return; }
        await axios.post(`${API}/ad-review/queue/${reviewId}/reject`,
                                                { reason, notes }, { withCredentials: true });
        onDone("Rejected.");
      } else if (action === "require-changes") {
        if (!notes.trim()) { setError("Notes are required"); setBusy(false); return; }
        await axios.post(`${API}/ad-review/queue/${reviewId}/require-changes`,
                                                { notes }, { withCredentials: true });
        onDone("Sent back to advertiser.");
      } else if (action === "block") {
        if (!reason.trim()) { setError("Reason is required"); setBusy(false); return; }
        await axios.post(
          `${API}/ad-review/advertisers/${detail.advertiser_id}/block`,
          { reason }, { withCredentials: true });
        onDone("Advertiser blocked.");
      }
    } catch (err) {
      setError(err?.response?.data?.detail?.code || err.message);
      setBusy(false);
    }
  }

  const bg = light ? "bg-white" : "bg-slate-900";
  const border = light ? "border-slate-200" : "border-slate-800";
  const muted = light ? "text-slate-500" : "text-slate-400";

  if (!detail && !error) return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
      <Loader2 className="w-6 h-6 animate-spin text-amber-500" />
    </div>
  );

  const snap = detail?.creative_snapshot || {};
  const mod = detail?.auto_moderation_result || null;
  const aiFlagged = mod?.action_taken === "flagged";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm overflow-y-auto"
              data-testid="ad-review-detail-modal"
              onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`${bg} border ${border} rounded-2xl shadow-2xl max-w-2xl w-full my-8 ${light ? "text-slate-900" : "text-white"}`}>
        <div className={`px-6 py-4 border-b ${border} flex items-center justify-between`}>
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono text-amber-500">
              {AD_TYPE_LABELS[detail?.ad_type] || detail?.ad_type}
            </div>
            <h2 className="text-lg font-black">
              {snap.title || snap.name || snap.headline || detail?.target_id}
            </h2>
          </div>
          <button onClick={onClose}
                          data-testid="ad-review-detail-close"
                          className={`p-1.5 rounded-md ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"}`}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-6 space-y-4 max-h-[70vh] overflow-y-auto">
          {error && (
            <div className="rounded-lg px-4 py-2 bg-red-500/10 border border-red-500/40 text-red-400 text-sm inline-flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" /> {String(error)}
            </div>
          )}

          {/* Advertiser strip */}
          <div className={`rounded-xl p-3 flex items-center gap-3 ${light ? "bg-slate-50" : "bg-slate-950"}`}
                      data-testid="ad-review-detail-advertiser">
            {detail?.advertiser?.logo_url && (
              <img src={detail.advertiser.logo_url}
                          className="w-10 h-10 rounded-lg object-cover" alt="" />
            )}
            <div className="min-w-0 flex-1">
              <div className="text-sm font-black truncate">
                <Megaphone className="w-4 h-4 inline mr-1 opacity-60" />
                {detail?.advertiser?.name || detail?.advertiser_id}
              </div>
              <div className={`text-[11px] ${muted}`}>
                Status: <b>{detail?.advertiser?.status || "active"}</b> · Past rejects: <b>{detail?.advertiser_past_reject_count ?? 0}</b>
              </div>
            </div>
            {detail?.advertiser?.status !== "blocked" && (
              <button onClick={() => setAction("block")}
                              data-testid="ad-review-detail-block-advertiser"
                              className="inline-flex items-center gap-1 text-xs font-bold px-3 py-1.5 rounded-full bg-red-500/15 text-red-400 hover:bg-red-500/25 border border-red-500/30">
                <Ban className="w-3 h-3" /> Block advertiser
              </button>
            )}
          </div>

          {/* AI moderation card */}
          {mod && (
            <div className={`rounded-xl p-3 ${aiFlagged
                                  ? "bg-red-500/10 border border-red-500/40"
                                  : (light ? "bg-emerald-50 border border-emerald-200"
                                                        : "bg-emerald-500/10 border border-emerald-500/30")}`}
                        data-testid="ad-review-detail-ai-moderation">
              <div className={`text-xs font-black uppercase tracking-widest mb-1 flex items-center gap-1 ${aiFlagged ? "text-red-400" : (light ? "text-emerald-700" : "text-emerald-400")}`}>
                <Sparkles className="w-3.5 h-3.5" /> AI moderation ({mod.action_taken})
              </div>
              {mod.error ? (
                <div className={`text-xs ${muted}`}>Skipped: {mod.error}</div>
              ) : (
                <>
                  <div className="text-xs">
                    Highest signal: <b>{mod.highest_category || "—"}</b>
                    {mod.highest_score !== undefined && (
                      <span className={`ml-2 font-mono`}>({(mod.highest_score * 100).toFixed(1)}%)</span>
                    )}
                  </div>
                  {mod.highest_score >= 0.35 && (
                    <div className={`text-[11px] mt-1 ${muted}`}>
                      Reviewer&apos;s call — this is an assist signal, not an auto-decision.
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Creative preview */}
          <div className={`rounded-xl p-4 ${light ? "bg-slate-50" : "bg-slate-950"}`}
                      data-testid="ad-review-detail-creative">
            {snap.hero_image_url && (
              <img src={snap.hero_image_url}
                          className="w-full h-40 rounded-lg object-cover mb-3" alt="" />
            )}
            {snap.audio_url && (
              <audio controls src={snap.audio_url}
                              data-testid="ad-review-detail-audio"
                              className="w-full mb-3" />
            )}
            <div className="grid grid-cols-1 gap-2 text-sm">
              {["title", "name", "headline"].map((k) => snap[k] && (
                <Row key={k} label={k} value={snap[k]} light={light} />
              ))}
              {snap.description && <Row label="description" value={snap.description} light={light} multi />}
              {snap.terms       && <Row label="terms"          value={snap.terms}        light={light} multi />}
              {snap.companion_headline && <Row label="companion" value={snap.companion_headline} light={light} />}
              {snap.creative?.headline && <Row label="headline" value={snap.creative.headline} light={light} />}
              {snap.creative?.body      && <Row label="body"      value={snap.creative.body}      light={light} multi />}
              {snap.cost_per_save_cents !== undefined && (
                <Row label="CPS" value={`$${(snap.cost_per_save_cents/100).toFixed(2)}`} light={light} />
              )}
              {snap.budget_cents !== undefined && (
                <Row label="budget" value={`$${(snap.budget_cents/100).toFixed(2)}`} light={light} />
              )}
              {snap.total_inventory !== undefined && (
                <Row label="inventory" value={snap.total_inventory} light={light} />
              )}
              {snap.sponsoring_merchant_id && (
                <Row label="sponsor" value={snap.sponsoring_merchant_id} light={light} />
              )}
            </div>
          </div>

          {/* Action form */}
          {action && (
            <div className={`rounded-xl p-4 border-2 ${light ? "border-amber-400 bg-amber-50" : "border-amber-500 bg-amber-500/10"}`}
                        data-testid="ad-review-detail-action-form">
              <div className="text-sm font-black mb-2">
                Confirm: {action === "approve" ? "Approve"
                                          : action === "reject" ? "Reject"
                                          : action === "require-changes" ? "Send back for changes"
                                          : "Block advertiser"}
              </div>
              {(action === "reject" || action === "block") && (
                <div className="mb-2">
                  <label className={`block text-[10px] uppercase tracking-wider mb-1 ${muted}`}>Reason *</label>
                  <input value={reason} onChange={(e) => setReason(e.target.value)}
                                data-testid="ad-review-detail-reason"
                                className={`w-full px-3 py-2 rounded-lg text-sm ${light ? "bg-white border border-slate-300" : "bg-slate-900 border border-slate-700"}`}
                                placeholder="Short reason shown to advertiser." />
                </div>
              )}
              <div className="mb-3">
                <label className={`block text-[10px] uppercase tracking-wider mb-1 ${muted}`}>
                  Notes{action === "require-changes" ? " *" : " (optional)"}
                </label>
                <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                                    rows={3}
                                    data-testid="ad-review-detail-notes"
                                    className={`w-full px-3 py-2 rounded-lg text-sm ${light ? "bg-white border border-slate-300" : "bg-slate-900 border border-slate-700"}`}
                                    placeholder={action === "require-changes"
                                                              ? "Explain what the advertiser needs to change."
                                                              : "Optional internal notes."} />
              </div>
              <div className="flex gap-2 justify-end">
                <button onClick={() => { setAction(null); setError(null); }}
                                disabled={busy}
                                className={`px-4 py-2 rounded-full text-sm font-semibold ${light ? "hover:bg-slate-100" : "hover:bg-slate-800"}`}>
                  Cancel
                </button>
                <button onClick={run} disabled={busy}
                                data-testid="ad-review-detail-confirm"
                                className={`inline-flex items-center gap-2 px-5 py-2 rounded-full text-sm font-black transition ${
                                                  action === "approve"
                                                      ? "bg-emerald-500 text-slate-900 hover:bg-emerald-400"
                                                      : action === "reject" || action === "block"
                                                          ? "bg-red-500 text-white hover:bg-red-400"
                                                          : "bg-blue-500 text-white hover:bg-blue-400"} disabled:opacity-50`}>
                  {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : null} Confirm
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer action bar (main entry points) */}
        {detail?.review_status === "pending" && !action && (
          <div className={`px-6 py-4 border-t ${border} flex flex-wrap gap-2 justify-end`}>
            <button onClick={() => setAction("require-changes")}
                            data-testid={`ad-review-require-changes-${detail.review_id}`}
                            className={`inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-black ${light ? "bg-blue-100 text-blue-700 hover:bg-blue-200" : "bg-blue-500/20 text-blue-400 hover:bg-blue-500/30"}`}>
              <RotateCw className="w-3.5 h-3.5" /> Require changes
            </button>
            <button onClick={() => setAction("reject")}
                            data-testid={`ad-review-reject-${detail.review_id}`}
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-black bg-red-500 text-white hover:bg-red-400">
              <XCircle className="w-3.5 h-3.5" /> Reject
            </button>
            <button onClick={() => setAction("approve")}
                            data-testid={`ad-review-approve-${detail.review_id}`}
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-full text-sm font-black bg-emerald-500 text-slate-900 hover:bg-emerald-400">
              <CheckCircle2 className="w-3.5 h-3.5" /> Approve
            </button>
          </div>
        )}
        {detail?.review_status !== "pending" && (
          <div className={`px-6 py-3 border-t ${border} text-xs ${muted}`}>
            Status: <b>{detail?.review_status}</b>
            {detail?.review_notes && <> · notes: {detail.review_notes}</>}
            {detail?.reject_reason && <> · reason: {detail.reject_reason}</>}
          </div>
        )}
      </div>
    </div>
  );
}


function Row({ label, value, light, multi }) {
  return (
    <div className="flex gap-2 items-start">
      <div className={`text-[10px] font-mono uppercase tracking-widest w-24 shrink-0 ${light ? "text-slate-500" : "text-slate-500"}`}>{label}</div>
      <div className={`${multi ? "" : "truncate"} text-sm ${light ? "text-slate-800" : "text-slate-200"}`}>{value}</div>
    </div>
  );
}
