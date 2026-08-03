// Phase D — Admin moderation queue for user-uploaded tracks.
//
// Route: `/admin/moderation/tracks` (admin only).  Lists jobs in
// `pending_admin_review` state with: title/artist (from ID3), uploader,
// station, OpenAI moderation flags, audio preview, approve / reject.
//
// Calls:
//   GET   /api/admin/moderation/tracks?status=pending_admin_review
//   POST  /api/admin/moderation/tracks/{job_id}/approve
//   POST  /api/admin/moderation/tracks/{job_id}/reject  { reason }
//
// Reject opens a modal with a required reason textarea.

/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  ShieldAlert, Check, X, Loader2, Music, Filter,
  AlertTriangle, ExternalLink,
} from "lucide-react";
import AdminSubNav from "@/AdminSubNav";

const API = process.env.REACT_APP_BACKEND_URL;

function api(method, url, body) {
  return axios({ method, url, data: body, withCredentials: true })
    .then((r) => r.data)
    .catch((err) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail
                              : detail?.message || err.message;
      const wrapped = new Error(msg || "Request failed");
      wrapped.detail = detail;
      wrapped.status = err?.response?.status;
      throw wrapped;
    });
}

const STATUS_FILTERS = [
  { value: "pending_admin_review", label: "Pending review", color: "#f59e0b" },
  { value: "approved",                          label: "Approved",          color: "#22c55e" },
  { value: "rejected",                          label: "Rejected",          color: "#ef4444" },
  { value: "all",                                  label: "All",                    color: "#a1a1aa" },
];


export default function AdminTrackModeration() {
  const [filter, setFilter] = useState("pending_admin_review");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [rejecting, setRejecting] = useState(null);  // job being rejected

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api("GET",
        `${API}/api/admin/moderation/tracks?status=${filter}&limit=100`);
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      toast.error(e.message || "Failed to load");
    } finally { setLoading(false); }
  }, [filter]);

  useEffect(() => { reload(); }, [reload]);

  async function approve(jobId) {
    if (!window.confirm("Approve this track?  It will be added to the "
        + "uploader's station (if station audience is Adult).")) return;
    try {
      await api("POST",
        `${API}/api/admin/moderation/tracks/${jobId}/approve`);
      toast.success("Approved.");
      reload();
    } catch (e) {
      toast.error(e.message || "Approve failed");
    }
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh",
                        background: "#080809" }}>
      <Toaster theme="dark" position="bottom-right" richColors />
      <AdminSubNav />
      <main data-testid="admin-track-moderation-page"
              style={{ flex: 1, padding: 24, maxWidth: 1240 }}>
        <div style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 11, color: "#9aa3af",
                              letterSpacing: 0.8 }}>
            PHASE D · CONTENT MODERATION · ADMIN
          </div>
          <h1 style={{ margin: "6px 0 0", fontSize: 22, color: "#e7e7ea" }}>
            Track moderation queue
          </h1>
          <p style={{ fontSize: 12, color: "#9aa3af", margin: "6px 0 0",
                            maxWidth: 720 }}>
            User-uploaded tracks flagged by OpenAI moderation appear here.
            Approve to add to the catalog with <code>explicit_flag=true</code>
            and (if station audience is Adult) auto-add to the uploader's
            station.  Reject to quarantine — uploader sees the reason in
            their upload UI.
          </p>
        </div>

        {/* Filter chips */}
        <div data-testid="filter-row"
                style={{ display: "flex", gap: 6, marginBottom: 18 }}>
          <Filter size={12} color="#9aa3af"
                          style={{ alignSelf: "center", marginRight: 2 }} />
          {STATUS_FILTERS.map((f) => (
            <button key={f.value}
                          onClick={() => setFilter(f.value)}
                          data-testid={`filter-${f.value}`}
                          style={{
                            padding: "5px 12px", borderRadius: 999,
                            border: "1px solid",
                            fontSize: 11, fontWeight: 600, cursor: "pointer",
                            textTransform: "uppercase", letterSpacing: 0.4,
                            background: filter === f.value
                              ? `${f.color}22` : "#0c0c10",
                            color: filter === f.value ? f.color : "#9aa3af",
                            borderColor: filter === f.value
                              ? f.color : "rgba(255,255,255,0.08)",
                          }}>
              {f.label}
            </button>
          ))}
        </div>

        {loading ? (
          <div style={emptyStyle}><Loader2 size={20} className="spin" /></div>
        ) : items.length === 0 ? (
          <div data-testid="queue-empty" style={emptyStyle}>
            <ShieldAlert size={20} style={{ marginBottom: 8 }} />
            <div style={{ fontSize: 13, color: "#9aa3af" }}>
              No items in this state.  Uploads with `verdict=block` or
              `verdict=warn` from OpenAI moderation land here.
            </div>
          </div>
        ) : (
          <>
            <div style={{ fontSize: 11, color: "#71717a", marginBottom: 8 }}>
              {items.length} of {total}
            </div>
            <div data-testid="queue-list"
                    style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {items.map((j) => (
                <Card key={j.job_id} job={j}
                              onApprove={() => approve(j.job_id)}
                              onReject={() => setRejecting(j)} />
              ))}
            </div>
          </>
        )}

        {rejecting && (
          <RejectModal job={rejecting}
                                  onClose={() => setRejecting(null)}
                                  onDone={() => { setRejecting(null); reload(); }} />
        )}
      </main>
    </div>
  );
}


function Card({ job, onApprove, onReject }) {
  return (
    <div data-testid={`queue-row-${job.job_id}`}
            style={{ background: "#0c0c10",
                        border: "1px solid rgba(255,255,255,0.06)",
                        borderRadius: 10, padding: 14,
                        display: "grid",
                        gridTemplateColumns: "1fr auto",
                        gap: 12, alignItems: "start" }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", gap: 6, alignItems: "center",
                            flexWrap: "wrap", marginBottom: 4 }}>
          <Music size={14} color="#22d3ee" />
          <span style={{ fontSize: 14, color: "#e7e7ea", fontWeight: 600 }}>
            {job.candidate_title || "(no title)"}
          </span>
          {job.candidate_artist && (
            <span style={{ fontSize: 12, color: "#9aa3af" }}>
              · {job.candidate_artist}
            </span>
          )}
          {job.moderation_verdict && (
            <span style={verdictPillStyle(job.moderation_verdict)}>
              {job.moderation_verdict.toUpperCase()}
            </span>
          )}
        </div>
        <div style={{ fontSize: 11, color: "#71717a", marginBottom: 6 }}>
          job: <code>{job.job_id}</code> · station:{" "}
          <a href={`/station/${job.station_slug}`} target="_blank"
              rel="noreferrer"
              style={{ color: "#9aa3af" }}>
            {job.station_slug}<ExternalLink size={9}
              style={{ verticalAlign: -1, marginLeft: 2 }} />
          </a>
          {" · "}uploader: <code>{job.user_id}</code>
          {" · "}submitted: {new Date(job.created_at).toLocaleString(undefined,
            { dateStyle: "medium", timeStyle: "short" })}
        </div>
        {job.moderation_categories?.length > 0 && (
          <div style={{ fontSize: 11, color: "#fbbf24",
                              background: "rgba(251,191,36,0.06)",
                              border: "1px solid rgba(251,191,36,0.30)",
                              borderRadius: 4, padding: 6, marginBottom: 6,
                              display: "flex", flexWrap: "wrap", gap: 4,
                              alignItems: "center" }}>
            <AlertTriangle size={11} />
            Flagged: {job.moderation_categories.map((c) => (
              <code key={c} style={{ background: "#fbbf2422", padding: "1px 4px",
                                                  borderRadius: 3, fontSize: 10 }}>{c}</code>
            ))}
            {job.moderation_score != null && (
              <span style={{ marginLeft: 6 }}>
                score: {(job.moderation_score * 100).toFixed(0)}%
              </span>
            )}
          </div>
        )}
        {job.decision_reason && (
          <div style={{ fontSize: 11, color: "#9aa3af", marginBottom: 6 }}>
            Pipeline note: {job.decision_reason}
          </div>
        )}
        {/* Audio preview — only renders if uploader is admin (file path
              is in storage).  Browser will silently fail otherwise. */}
        {job.final_file_path && (
          <audio controls preload="none"
                      data-testid={`audio-${job.job_id}`}
                      style={{ width: "100%", marginTop: 4, height: 28 }}>
            <source src={`${API}${
              job.final_file_path.replace(/^\/app\/backend\/storage/,
                                                                      "/api/static")}`} />
          </audio>
        )}
        {job.status === "rejected" && job.rejection_reason && (
          <div data-testid={`rejection-${job.job_id}`}
                  style={{ fontSize: 11, color: "#fca5a5",
                              background: "rgba(239,68,68,0.06)",
                              border: "1px solid rgba(239,68,68,0.30)",
                              borderRadius: 4, padding: 6, marginTop: 6 }}>
            <X size={11} style={{ verticalAlign: -1, marginRight: 4 }} />
            Rejected: {job.rejection_reason}
          </div>
        )}
        {job.status === "approved" && job.target_track_id && (
          <div style={{ fontSize: 11, color: "#22c55e", marginTop: 4 }}>
            <Check size={11} style={{ verticalAlign: -1, marginRight: 4 }} />
            Approved → track {job.target_track_id}
          </div>
        )}
      </div>
      {job.status === "pending_admin_review" && (
        <div style={{ display: "flex", flexDirection: "column",
                            gap: 6, alignItems: "stretch" }}>
          <button onClick={onApprove}
                      data-testid={`approve-${job.job_id}`}
                      style={btnSuccessStyle}>
            <Check size={12} /> Approve
          </button>
          <button onClick={onReject}
                      data-testid={`reject-${job.job_id}`}
                      style={btnDangerStyle}>
            <X size={12} /> Reject
          </button>
        </div>
      )}
    </div>
  );
}


function RejectModal({ job, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (reason.trim().length < 4) {
      toast.error("Reason must be at least 4 characters.");
      return;
    }
    setSaving(true);
    try {
      await api("POST",
        `${API}/api/admin/moderation/tracks/${job.job_id}/reject`,
        { reason: reason.trim() });
      toast.success("Rejected.");
      onDone();
    } catch (e) {
      toast.error(e.message || "Reject failed");
    } finally { setSaving(false); }
  }

  return (
    <div data-testid="reject-modal-backdrop"
            onClick={onClose}
            style={{ position: "fixed", inset: 0,
                        background: "rgba(0,0,0,0.6)",
                        display: "flex", alignItems: "center",
                        justifyContent: "center", zIndex: 50 }}>
      <div onClick={(e) => e.stopPropagation()}
              data-testid="reject-modal"
              style={{ background: "#0a0a0c",
                          border: "1px solid rgba(255,255,255,0.10)",
                          borderRadius: 10, padding: 16,
                          maxWidth: 480, width: "100%" }}>
        <div style={{ fontSize: 11, color: "#9aa3af", letterSpacing: 0.4 }}>
          REJECT TRACK · {job.job_id}
        </div>
        <h3 style={{ margin: "4px 0 12px", color: "#e7e7ea", fontSize: 16 }}>
          {job.candidate_title}
        </h3>
        <p style={{ fontSize: 11, color: "#9aa3af", marginBottom: 8 }}>
          Reason will be shown to the uploader in their station UI.
        </p>
        <textarea value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          rows={4}
                          placeholder="Explain why this track is being rejected (≥4 chars)…"
                          data-testid="reject-reason-input"
                          style={{
                            width: "100%", padding: "8px 10px",
                            background: "#0c0c10",
                            border: "1px solid rgba(255,255,255,0.10)",
                            borderRadius: 6, color: "#e7e7ea", fontSize: 12,
                            outline: "none", minHeight: 90, resize: "vertical",
                          }} />
        <div style={{ display: "flex", justifyContent: "flex-end",
                            gap: 8, marginTop: 12 }}>
          <button onClick={onClose}
                      data-testid="reject-modal-cancel"
                      style={btnGhostStyle}>Cancel</button>
          <button onClick={submit} disabled={saving}
                      data-testid="reject-modal-confirm"
                      style={btnDangerStyle}>
            {saving ? <Loader2 size={12} className="spin" /> : <X size={12} />}
            Confirm reject
          </button>
        </div>
      </div>
    </div>
  );
}


function verdictPillStyle(verdict) {
  const color = verdict === "block" ? "#ef4444"
                            : verdict === "warn" ? "#fbbf24"
                            : "#22c55e";
  return {
    fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
    padding: "2px 6px", borderRadius: 4,
    background: `${color}22`, color: color,
  };
}


// ─── Style tokens ────────────────────────────────────────────────────
const btnSuccessStyle = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "7px 12px", background: "#22c55e", border: "none",
  borderRadius: 6, color: "#0a0a0c", fontSize: 12, fontWeight: 700,
  cursor: "pointer", letterSpacing: 0.3,
};
const btnDangerStyle = {
  ...btnSuccessStyle, background: "#ef4444", color: "#fff",
};
const btnGhostStyle = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "6px 10px", background: "transparent",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 5, color: "#e7e7ea", fontSize: 12, cursor: "pointer",
};
const emptyStyle = {
  padding: 32, textAlign: "center", color: "#9aa3af",
  border: "1px dashed rgba(255,255,255,0.10)", borderRadius: 8,
};
