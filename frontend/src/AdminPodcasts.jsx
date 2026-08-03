import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import AdminBreadcrumb from "./shell/AdminBreadcrumb";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

// Phase 19a Part 3 — fixes:
//   • ApplicationsPanel: optimistic-remove on approve/reject; visible error
//   • ChannelsPanel: read `items` (not `channels`); default filter to
//     `approved` so the 546 existing approved channels show; status filter

export default function AdminPodcasts() {
  const [tab, setTab] = useState("applications");
  const subLabel = tab === "applications" ? "Applications" : "Channels";
  return (
    <div style={{padding: 24, color: "#e7e7ea", background: "#0a0a0c",
                          minHeight: "100vh"}}
            data-testid="admin-podcasts">
      <AdminBreadcrumb segments={[
        {label: "Admin", href: "/admin"},
        {label: "Podcasts", href: "/admin/podcasts/applications"},
        {label: subLabel},
      ]} />
      <h1 style={{fontSize: 24, fontWeight: 700, marginBottom: 12}}>
        Podcast Moderation
      </h1>
      <div style={{display: "flex", gap: 6, marginBottom: 14}}>
        {["applications", "channels"].map((t) => (
          <button key={t} onClick={() => setTab(t)}
                          data-testid={`admin-podcasts-tab-${t}`}
                          style={{padding: "6px 12px", borderRadius: 8,
                                      background: tab === t ? "#f59e0b" : "transparent",
                                      color: tab === t ? "#0a0a0c" : "#9aa3af",
                                      border: "1px solid rgba(255,255,255,0.08)"}}>
            {t}
          </button>
        ))}
      </div>
      {tab === "applications" && <ApplicationsPanel />}
      {tab === "channels" && <ChannelsPanel />}
    </div>
  );
}


function ApplicationsPanel() {
  const [rows, setRows] = useState([]);
  const [error, setError] = useState("");
  const refresh = useCallback(() => {
    setError("");
    axios.get(`${API}/admin/podcasts/creator-applications?status=pending`,
                  {withCredentials: true})
            .then((r) => setRows(r.data.applications || []))
            .catch((e) => {
              setRows([]);
              setError(e?.response?.data?.detail || "Failed to load applications.");
            });
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const act = (id, kind, reason = "") => {
    return axios.post(
      `${API}/admin/podcasts/creator-applications/${id}/${kind}`,
      kind === "reject" ? {reason} : {},
      {withCredentials: true})
      .then(() => refresh())
      .catch((e) => setError(e?.response?.data?.detail
        || `Could not ${kind} application. Please retry.`));
  };

  return (
    <div data-testid="admin-applications-list">
      {error && (
        <div data-testid="admin-applications-error"
                style={{padding: 10, marginBottom: 10, borderRadius: 8,
                            background: "rgba(239,68,68,0.1)", color: "#fda4af",
                            border: "1px solid rgba(239,68,68,0.3)"}}>
          {String(error)}
        </div>
      )}
      {rows.length === 0 && !error && (
        <div data-testid="admin-applications-empty"
                style={{color: "#9aa3af", padding: 14, borderRadius: 10,
                            background: "rgba(255,255,255,0.02)",
                            border: "1px solid rgba(255,255,255,0.06)"}}>
          No pending applications.{" "}
          <a href="/admin/podcasts/channels"
              data-testid="admin-applications-empty-channels-link"
              style={{color: "#f59e0b", textDecoration: "underline"}}>
            View active creators &amp; channels →
          </a>
        </div>
      )}
      {rows.map((r) => (
        <div key={r.id} data-testid={`application-${r.id}`}
                style={{padding: 14, marginBottom: 8, borderRadius: 10,
                            background: "rgba(255,255,255,0.02)",
                            border: "1px solid rgba(255,255,255,0.06)"}}>
          <div style={{fontWeight: 600}}>{r.display_name}</div>
          <div style={{fontSize: 12, color: "#9aa3af", marginTop: 4}}>
            {r.contact_email} · {r.market}
          </div>
          <div style={{fontSize: 13, marginTop: 6}}>{r.bio}</div>
          <div style={{marginTop: 10, display: "flex", gap: 8}}>
            <button onClick={() => act(r.id, "approve")}
                            data-testid={`approve-${r.id}`}
                            style={{padding: "6px 12px", background: "#22c55e",
                                        color: "#0a0a0c", borderRadius: 6, fontWeight: 600}}>
              Approve
            </button>
            <button onClick={() => act(r.id, "reject", "Insufficient detail")}
                            data-testid={`reject-${r.id}`}
                            style={{padding: "6px 12px", background: "#ef4444",
                                        color: "#fff", borderRadius: 6, fontWeight: 600}}>
              Reject
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}


function ChannelsPanel() {
  const [rows, setRows] = useState([]);
  const [status, setStatus] = useState("approved");  // P19a3: default to approved
  const [error, setError] = useState("");
  const [total, setTotal] = useState(0);

  const refresh = useCallback(() => {
    setError("");
    axios.get(`${API}/admin/podcasts/channels?approval_status=${status}`,
                  {withCredentials: true})
            .then((r) => {
              // P19a3: backend returns `items`, not `channels`
              setRows(r.data.items || r.data.channels || []);
              setTotal(r.data.total_count
                || (r.data.items || r.data.channels || []).length);
            })
            .catch((e) => {
              setRows([]); setTotal(0);
              setError(e?.response?.data?.detail || "Failed to load channels.");
            });
  }, [status]);

  useEffect(() => { refresh(); }, [refresh]);

  const act = (id, kind) => {
    return axios.post(
      `${API}/admin/podcasts/channels/${id}/${kind}`, {},
      {withCredentials: true})
      .then(() => refresh())
      .catch((e) => setError(e?.response?.data?.detail
        || `Could not ${kind} channel. Please retry.`));
  };

  return (
    <div data-testid="admin-channels-list">
      <div style={{display: "flex", gap: 6, marginBottom: 10,
                            alignItems: "center"}}>
        <label style={{fontSize: 12, color: "#9aa3af"}}>
          Filter:&nbsp;
          <select value={status} onChange={(e) => setStatus(e.target.value)}
                          data-testid="admin-channels-status-filter"
                          style={{padding: "4px 8px", borderRadius: 6,
                                      background: "#111114", color: "#e7e7ea",
                                      border: "1px solid rgba(255,255,255,0.1)"}}>
            <option value="approved">Approved</option>
            <option value="pending">Pending</option>
            <option value="rejected">Rejected</option>
            <option value="">All</option>
          </select>
        </label>
        <div style={{fontSize: 12, color: "#9aa3af", marginLeft: "auto"}}
                data-testid="admin-channels-count">
          {total} channel{total === 1 ? "" : "s"}
        </div>
      </div>
      {error && (
        <div data-testid="admin-channels-error"
                style={{padding: 10, marginBottom: 10, borderRadius: 8,
                            background: "rgba(239,68,68,0.1)", color: "#fda4af",
                            border: "1px solid rgba(239,68,68,0.3)"}}>
          {String(error)}
        </div>
      )}
      {rows.length === 0 && !error && (
        <div style={{color: "#9aa3af"}}>
          No {status || "matching"} channels.
        </div>
      )}
      {rows.map((c) => (
        <div key={c.id} data-testid={`channel-row-${c.id}`}
                style={{padding: 14, marginBottom: 8, borderRadius: 10,
                            background: "rgba(255,255,255,0.02)",
                            border: "1px solid rgba(255,255,255,0.06)"}}>
          <div style={{fontWeight: 600}}>{c.title}</div>
          <div style={{fontSize: 12, color: "#9aa3af", marginTop: 4}}>
            {c.category} · {c.language}
            {c.approval_status ? ` · ${c.approval_status}` : ""}
          </div>
          {status === "pending" && (
            <div style={{marginTop: 10, display: "flex", gap: 8}}>
              <button onClick={() => act(c.id, "approve")}
                              data-testid={`channel-approve-${c.id}`}
                              style={{padding: "6px 12px", background: "#22c55e",
                                          color: "#0a0a0c", borderRadius: 6, fontWeight: 600}}>
                Approve
              </button>
              <button onClick={() => act(c.id, "reject")}
                              data-testid={`channel-reject-${c.id}`}
                              style={{padding: "6px 12px", background: "#ef4444",
                                          color: "#fff", borderRadius: 6, fontWeight: 600}}>
                Reject
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
