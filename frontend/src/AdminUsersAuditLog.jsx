// Phase 19a Part 5 FRONTEND — /admin/users/audit-log
//
// Global audit log view.  Filters by action + admin_id, paginated.
import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import AdminBreadcrumb from "./shell/AdminBreadcrumb";
import { COLORS, Badge, fmtDate } from "./AdminUsers";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const ACTIONS = ["role_change", "activate", "deactivate", "suspend", "unsuspend"];

const selectStyle = {
  padding: "6px 10px", borderRadius: 6, background: "#111114",
  color: COLORS.text, border: `1px solid ${COLORS.border}`,
  fontSize: 13, outline: "none",
};
const th = {textAlign: "left", padding: "8px 10px", fontSize: 11,
                      color: COLORS.muted, textTransform: "uppercase",
                      letterSpacing: 0.5,
                      borderBottom: `1px solid ${COLORS.border}`};
const td = {padding: "8px 10px", fontSize: 13, color: COLORS.text,
                      borderBottom: `1px solid ${COLORS.border}`,
                      verticalAlign: "top"};

export default function AdminUsersAuditLog() {
  const [items, setItems] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [action, setAction] = useState("");
  const [adminId, setAdminId] = useState("");
  const [admins, setAdmins] = useState([]);

  // Populate admin filter dropdown.
  useEffect(() => {
    axios.get(`${API}/admin/users?role=admin&limit=100`,
                      {withCredentials: true})
            .then((r) => setAdmins(r.data.items || []))
            .catch(() => setAdmins([]));
  }, []);

  const load = useCallback(async (cursor = null) => {
    setLoading(true); setError("");
    try {
      const p = new URLSearchParams({ limit: "50" });
      if (action) p.set("action", action);
      if (adminId) p.set("admin_id", adminId);
      if (cursor) p.set("cursor", cursor);
      const r = await axios.get(`${API}/admin/users/audit-log?${p.toString()}`,
                                                {withCredentials: true});
      setItems((prev) => cursor ? [...prev, ...(r.data.items || [])]
                                                  : (r.data.items || []));
      setNext(r.data.next_cursor || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load audit log.");
      if (!cursor) setItems([]);
    } finally {
      setLoading(false);
    }
  }, [action, adminId]);

  useEffect(() => { load(null); }, [load]);

  return (
    <div style={{padding: 24, color: COLORS.text, background: COLORS.bg,
                          minHeight: "100vh"}}
            data-testid="admin-users-audit-log">
      <AdminBreadcrumb segments={[
        {label: "Admin", href: "/admin"},
        {label: "User Management", href: "/admin/users"},
        {label: "Audit Log"},
      ]} />
      <h1 style={{fontSize: 22, fontWeight: 700, marginBottom: 14}}>
        User Management — Audit Log
      </h1>

      <div style={{display: "flex", gap: 8, marginBottom: 12,
                            alignItems: "center", flexWrap: "wrap"}}>
        <select value={action} onChange={(e) => setAction(e.target.value)}
                        data-testid="audit-filter-action"
                        style={selectStyle}>
          <option value="">All actions</option>
          {ACTIONS.map((a) => <option key={a} value={a}>{a}</option>)}
        </select>
        <select value={adminId} onChange={(e) => setAdminId(e.target.value)}
                        data-testid="audit-filter-admin"
                        style={selectStyle}>
          <option value="">All admins</option>
          {admins.map((a) => (
            <option key={a.user_id} value={a.user_id}>{a.email}</option>
          ))}
        </select>
        {(action || adminId) && (
          <button onClick={() => { setAction(""); setAdminId(""); }}
                          data-testid="audit-filter-clear"
                          style={{...selectStyle, cursor: "pointer",
                                      color: COLORS.muted}}>
            Clear
          </button>
        )}
      </div>

      {error && (
        <div data-testid="audit-error"
                style={{padding: 10, marginBottom: 10, borderRadius: 8,
                            background: "rgba(239,68,68,0.1)", color: "#fda4af",
                            border: "1px solid rgba(239,68,68,0.3)"}}>
          {String(error)}
        </div>
      )}

      <div style={{background: COLORS.surface, borderRadius: 10,
                            border: `1px solid ${COLORS.border}`,
                            overflow: "hidden"}}>
        <table style={{width: "100%", borderCollapse: "collapse"}}>
          <thead>
            <tr>
              <th style={th}>When</th>
              <th style={th}>Target User</th>
              <th style={th}>Action</th>
              <th style={th}>Admin</th>
              <th style={th}>Diff</th>
              <th style={th}>Reason</th>
            </tr>
          </thead>
          <tbody>
            {loading && items.length === 0 && (
              <tr><td colSpan={6}
                        style={{...td, color: COLORS.muted, textAlign: "center"}}>
                Loading…
              </td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={6}
                        data-testid="audit-empty"
                        style={{...td, color: COLORS.muted, textAlign: "center",
                                    padding: 20}}>
                No audit entries match these filters.
              </td></tr>
            )}
            {items.map((r) => (
              <tr key={r.audit_id} data-testid={`audit-row-${r.audit_id}`}>
                <td style={td}>{fmtDate(r.created_at)}</td>
                <td style={td}>
                  <Link to={`/admin/users/${r.user_id}`}
                            style={{color: COLORS.amber, textDecoration: "none"}}>
                    {r.user_id}
                  </Link>
                </td>
                <td style={td}>
                  <Badge palette={{bg: "rgba(245,158,11,0.15)",
                                              fg: COLORS.amber}}>
                    {r.action}
                  </Badge>
                </td>
                <td style={td}>{r.changed_by_admin_id || "—"}</td>
                <td style={td}>
                  {String(r.old_value ?? "—")} → {String(r.new_value ?? "—")}
                </td>
                <td style={td}>{r.reason || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {next && (
        <div style={{textAlign: "center", marginTop: 14}}>
          <button onClick={() => load(next)}
                          data-testid="audit-load-more"
                          style={{padding: "8px 16px", borderRadius: 6,
                                      background: "transparent", color: COLORS.amber,
                                      border: `1px solid ${COLORS.border}`,
                                      cursor: "pointer"}}>
            Load more
          </button>
        </div>
      )}
    </div>
  );
}
