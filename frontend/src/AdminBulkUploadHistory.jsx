// Phase 22g FRONTEND — Bulk Upload Job History tab.
//
// Companion to AdminBulkUpload.jsx.  Lives in the same panel; tab-switched
// at the page level.  Renders the paginated history list, a status-filter
// dropdown, and a click-to-open detail modal showing the full
// `per_file_results_json` payload from the audit row.
import { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { API } from "@/AuthContext";


function StatusBadge({ status }) {
  const map = {
    running:        "#60a5fa",
    completed:    "#22c55e",
    partial:        "#f59e0b",
    failed:          "#ef4444",
    abandoned:    "#9ca3af",
  };
  const color = map[status] || "#9ca3af";
  return (
    <span data-testid={`job-status-${status}`}
                style={{display: "inline-block", padding: "2px 8px",
                            borderRadius: 999, fontSize: 11, fontWeight: 600,
                            background: `${color}22`, color}}>
      {status || "—"}
    </span>
  );
}


function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toISOString().replace("T", " ").slice(0, 16) + "Z";
  } catch (_) { return "—"; }
}

function fmtDuration(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.floor((ms % 60000) / 1000);
  return `${m}m${s}s`;
}


// ════════════════════════════════════════════════════════════════════════
// Detail modal
// ════════════════════════════════════════════════════════════════════════
function JobDetailModal({ jobId, onClose }) {
  const [job, setJob] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const r = await axios.get(
          `${API}/admin/tracks/bulk-upload/jobs/${jobId}`,
          {withCredentials: true});
        if (!cancelled) setJob(r.data);
      } catch (e) {
        if (!cancelled) {
          setError(e?.response?.data?.detail || "Failed to load job.");
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [jobId]);

  return (
    <div onClick={onClose}
            data-testid="job-detail-modal"
            style={{position: "fixed", inset: 0,
                        background: "rgba(0,0,0,0.7)",
                        display: "flex", alignItems: "center",
                        justifyContent: "center", zIndex: 60, padding: 20}}>
      <div onClick={(e) => e.stopPropagation()}
              style={{width: "min(900px, 100%)", maxHeight: "90vh",
                          overflowY: "auto",
                          background: "#16161a", borderRadius: 12,
                          border: "1px solid rgba(255,255,255,0.08)",
                          padding: 20, color: "#e7e7ea"}}>
        {!job && !error && <div>Loading…</div>}
        {error && <div style={{color: "#fda4af"}}>{String(error)}</div>}
        {job && (
          <>
            <div style={{display: "flex", justifyContent: "space-between",
                                    alignItems: "baseline", marginBottom: 10}}>
              <div style={{fontSize: 14, fontWeight: 700}}
                      data-testid="modal-job-id">
                {job.job_id}
              </div>
              <button onClick={onClose}
                              data-testid="modal-close"
                              style={{background: "transparent", color: "#9aa3af",
                                          border: 0, fontSize: 18, cursor: "pointer"}}>
                ×
              </button>
            </div>
            <div style={{display: "grid",
                                    gridTemplateColumns: "repeat(4, 1fr)",
                                    gap: 10, fontSize: 12, marginBottom: 12}}>
              <Stat label="Status">
                <StatusBadge status={job.status} />
              </Stat>
              <Stat label="Started">{fmtDate(job.started_at)}</Stat>
              <Stat label="Duration">{fmtDuration(job.duration_ms)}</Stat>
              <Stat label="Storage">{job.storage_provider}</Stat>
              <Stat label="Inputs">{job.total_inputs}</Stat>
              <Stat label="Uploaded">{job.uploaded_count}</Stat>
              <Stat label="Duplicates">{job.duplicate_count}</Stat>
              <Stat label="Failed">{job.failed_count}</Stat>
            </div>
            {job.failure_reason && (
              <div data-testid="modal-failure-reason"
                      style={{padding: 10, marginBottom: 10, borderRadius: 8,
                                  background: "rgba(239,68,68,0.1)",
                                  color: "#fda4af",
                                  border: "1px solid rgba(239,68,68,0.3)",
                                  fontFamily: "monospace", fontSize: 11,
                                  whiteSpace: "pre-wrap"}}>
                {job.failure_reason}
              </div>
            )}
            <div style={{fontSize: 12, color: "#9aa3af", marginBottom: 6}}>
              Per-file results ({(job.per_file_results_json || []).length}
              {job.per_file_results_truncated && " — truncated"})
            </div>
            <table style={{width: "100%", borderCollapse: "collapse",
                                          fontSize: 12}}>
              <thead>
                <tr style={{color: "#9aa3af"}}>
                  <th style={cellHead}>Filename</th>
                  <th style={cellHead}>Status</th>
                  <th style={cellHead}>Track / Reason</th>
                </tr>
              </thead>
              <tbody>
                {(job.per_file_results_json || []).map((it, i) => (
                  <tr key={i}
                        style={{borderTop: "1px solid rgba(255,255,255,0.04)"}}>
                    <td style={cellBody}>{it.archive ? `${it.archive} / ` : ""}{it.filename}</td>
                    <td style={cellBody}>{it.status}</td>
                    <td style={cellBody}>
                      {it.track_id || it.existing_track_id
                                          || it.reason || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </div>
    </div>
  );
}

function Stat({ label, children }) {
  return (
    <div style={{padding: 8, background: "rgba(255,255,255,0.02)",
                          borderRadius: 8,
                          border: "1px solid rgba(255,255,255,0.06)"}}>
      <div style={{fontSize: 10, color: "#9aa3af",
                          textTransform: "uppercase",
                          letterSpacing: 0.5, marginBottom: 2}}>{label}</div>
      <div style={{fontSize: 13, color: "#e7e7ea"}}>{children}</div>
    </div>
  );
}

const cellHead = {textAlign: "left", padding: "6px 8px",
                                  fontSize: 10, textTransform: "uppercase",
                                  letterSpacing: 0.5};
const cellBody = {padding: "6px 8px", color: "#e7e7ea"};


// ════════════════════════════════════════════════════════════════════════
// Top-level Job History tab
// ════════════════════════════════════════════════════════════════════════
export default function AdminBulkUploadHistory() {
  const [rows, setRows] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [openJobId, setOpenJobId] = useState(null);

  const load = useCallback(async (cursor = null) => {
    setLoading(true); setError("");
    try {
      const p = new URLSearchParams({ limit: "25" });
      if (status) p.set("status", status);
      if (cursor) p.set("cursor", cursor);
      const r = await axios.get(
        `${API}/admin/tracks/bulk-upload/jobs?${p.toString()}`,
        {withCredentials: true});
      setRows((prev) => cursor ? [...prev, ...(r.data.items || [])]
                                                  : (r.data.items || []));
      setNext(r.data.next_cursor || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load history.");
      if (!cursor) setRows([]);
    } finally {
      setLoading(false);
    }
  }, [status]);

  const sweepStale = useCallback(async () => {
    try {
      await axios.post(
        `${API}/admin/tracks/bulk-upload/jobs/sweep-stale`,
        {}, {withCredentials: true});
      load(null);
    } catch (e) { /* non-blocking */ }
  }, [load]);

  useEffect(() => { load(null); }, [load]);

  return (
    <div data-testid="bulk-upload-history-panel"
            style={{padding: 14, color: "#e7e7ea"}}>
      <div style={{display: "flex", alignItems: "center", gap: 10,
                            marginBottom: 12, flexWrap: "wrap"}}>
        <select value={status} onChange={(e) => setStatus(e.target.value)}
                        data-testid="history-status-filter"
                        style={selectStyle}>
          <option value="">All statuses</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="partial">Partial</option>
          <option value="failed">Failed</option>
          <option value="abandoned">Abandoned</option>
        </select>
        <button onClick={() => load(null)}
                        data-testid="history-refresh"
                        style={btnStyle}>
          Refresh
        </button>
        <button onClick={sweepStale}
                        data-testid="history-sweep-stale"
                        style={{...btnStyle, color: "#fbbf24"}}>
          Sweep stale (&gt;30m)
        </button>
      </div>

      {error && (
        <div data-testid="history-error"
                style={{padding: 10, marginBottom: 10, borderRadius: 8,
                            background: "rgba(239,68,68,0.1)", color: "#fda4af",
                            border: "1px solid rgba(239,68,68,0.3)"}}>
          {String(error)}
        </div>
      )}

      <div style={{borderRadius: 10, overflow: "hidden",
                            border: "1px solid rgba(255,255,255,0.06)",
                            background: "rgba(255,255,255,0.02)"}}>
        <table style={{width: "100%", borderCollapse: "collapse"}}>
          <thead>
            <tr style={{color: "#9aa3af"}}>
              <th style={th}>Started</th>
              <th style={th}>Status</th>
              <th style={th}>User</th>
              <th style={th}>Inputs</th>
              <th style={th}>Uploaded</th>
              <th style={th}>Failed</th>
              <th style={th}>Duration</th>
            </tr>
          </thead>
          <tbody>
            {loading && rows.length === 0 && (
              <tr><td colSpan={7}
                          style={{...td, textAlign: "center",
                                      color: "#9aa3af"}}>Loading…</td></tr>
            )}
            {!loading && rows.length === 0 && (
              <tr><td colSpan={7}
                          data-testid="history-empty"
                          style={{...td, textAlign: "center",
                                      color: "#9aa3af", padding: 20}}>
                No jobs yet.
              </td></tr>
            )}
            {rows.map((r) => (
              <tr key={r.job_id}
                      onClick={() => setOpenJobId(r.job_id)}
                      data-testid={`history-row-${r.job_id}`}
                      style={{cursor: "pointer",
                                  borderTop: "1px solid rgba(255,255,255,0.04)"}}>
                <td style={td}>{fmtDate(r.started_at)}</td>
                <td style={td}><StatusBadge status={r.status} /></td>
                <td style={td}>{r.started_by_user_id || "—"}</td>
                <td style={td}>{r.total_inputs}</td>
                <td style={td}>{r.uploaded_count}</td>
                <td style={td}>{r.failed_count}</td>
                <td style={td}>{fmtDuration(r.duration_ms)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {next && (
        <div style={{textAlign: "center", marginTop: 12}}>
          <button onClick={() => load(next)}
                          data-testid="history-load-more"
                          style={btnStyle}>
            Load more
          </button>
        </div>
      )}

      {openJobId && (
        <JobDetailModal jobId={openJobId}
                                      onClose={() => setOpenJobId(null)} />
      )}
    </div>
  );
}


// ════════════════════════════════════════════════════════════════════════
// "Your recent uploads" widget — shown above the upload form so the user
// can see the history of their own attempts without leaving the page.
// ════════════════════════════════════════════════════════════════════════
export function MyRecentUploadsWidget() {
  const [rows, setRows] = useState([]);
  const [loaded, setLoaded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    axios.get(`${API}/me/bulk-upload/jobs?limit=5`,
                          {withCredentials: true})
              .then((r) => { if (!cancelled) {
                setRows(r.data.items || []); setLoaded(true);
              } })
              .catch(() => { if (!cancelled) setLoaded(true); });
    return () => { cancelled = true; };
  }, []);
  if (!loaded) return null;
  if (rows.length === 0) return null;
  return (
    <div data-testid="my-recent-uploads-widget"
            style={{padding: 10, marginBottom: 14, borderRadius: 8,
                        background: "rgba(255,255,255,0.02)",
                        border: "1px solid rgba(255,255,255,0.06)"}}>
      <div style={{fontSize: 11, color: "#9aa3af",
                          textTransform: "uppercase", letterSpacing: 0.5,
                          marginBottom: 6}}>
        Your recent uploads
      </div>
      <div style={{display: "flex", gap: 8, flexWrap: "wrap"}}>
        {rows.map((r) => (
          <div key={r.job_id}
                  data-testid={`recent-job-${r.job_id}`}
                  style={{padding: "6px 10px", borderRadius: 6,
                              background: "rgba(255,255,255,0.03)",
                              fontSize: 12, color: "#e7e7ea"}}>
            <StatusBadge status={r.status} />{" "}
            <span style={{color: "#9aa3af"}}>{fmtDate(r.started_at)}</span>{" "}
            <span>{r.uploaded_count}/{r.total_inputs} uploaded</span>
            {r.failed_count > 0 && (
              <span style={{color: "#fda4af"}}> · {r.failed_count} failed</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


const selectStyle = {
  padding: "6px 10px", borderRadius: 6, background: "#111114",
  color: "#e7e7ea", border: "1px solid rgba(255,255,255,0.06)",
  fontSize: 13, outline: "none",
};
const btnStyle = {
  padding: "6px 12px", borderRadius: 6, background: "transparent",
  color: "#e7e7ea", border: "1px solid rgba(255,255,255,0.06)",
  cursor: "pointer", fontSize: 13,
};
const th = {textAlign: "left", padding: "8px 10px", fontSize: 10,
                      textTransform: "uppercase", letterSpacing: 0.5};
const td = {padding: "8px 10px", fontSize: 13, color: "#e7e7ea"};
