// Phase 19a Part 5 FRONTEND — /admin/users/:user_id
//
// Single-user detail page.  Fetches GET /api/admin/users/{user_id} for the
// profile + last-10 audit log, plus GET /api/admin/users/{user_id}/audit-log
// for the paginated Audit tab.  Reuses ChangeRoleModal / DeactivateModal /
// ActivateModal from AdminUsers.jsx.
import React, { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import axios from "axios";
import AdminBreadcrumb from "./shell/AdminBreadcrumb";
import { useAuth } from "@/AuthContext";
import {
  COLORS, ROLE_COLORS, STATUS_COLORS, Badge, fmtDate,
  ChangeRoleModal, DeactivateModal, ActivateModal, ToastView,
} from "./AdminUsers";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function ProfileCard({ u }) {
  const st = u.status || "active";
  return (
    <div data-testid="user-profile-card"
            style={{padding: 18, borderRadius: 12, background: COLORS.surface,
                        border: `1px solid ${COLORS.border}`, marginBottom: 18}}>
      <div style={{display: "flex", gap: 14, alignItems: "baseline",
                            flexWrap: "wrap"}}>
        <div style={{fontSize: 18, fontWeight: 700, color: COLORS.text}}
                data-testid="profile-email">
          {u.email}
        </div>
        <Badge palette={ROLE_COLORS[u.role]} testid="profile-role">
          {u.role || "user"}
        </Badge>
        <Badge palette={STATUS_COLORS[st]} testid="profile-status">
          {st}
        </Badge>
      </div>
      <div style={{fontSize: 13, color: COLORS.muted, marginTop: 6}}>
        {u.name || "—"} · created {fmtDate(u.created_at)} · last login {fmtDate(u.last_login_at)}
      </div>
      {st !== "active" && (
        <div style={{marginTop: 10, padding: 10, borderRadius: 8,
                            background: "rgba(239,68,68,0.05)",
                            border: "1px solid rgba(239,68,68,0.2)",
                            fontSize: 12, color: "#fda4af"}}
                data-testid="profile-deactivation-info">
          Deactivated {fmtDate(u.deactivated_at)} — {u.deactivation_reason || "no reason recorded"}
        </div>
      )}
    </div>
  );
}

function Tab({ active, onClick, children, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
                    style={{padding: "8px 14px", borderRadius: 8,
                                background: active ? COLORS.amber : "transparent",
                                color: active ? "#0a0a0c" : COLORS.muted,
                                border: `1px solid ${COLORS.border}`,
                                fontWeight: active ? 600 : 400, cursor: "pointer",
                                fontSize: 13}}>
      {children}
    </button>
  );
}

function ActivityTab({ u }) {
  return (
    <div data-testid="tab-activity"
            style={{padding: 14, background: COLORS.surface,
                        border: `1px solid ${COLORS.border}`, borderRadius: 10}}>
      <Row label="Last login"     value={fmtDate(u.last_login_at)} />
      <Row label="Created"        value={fmtDate(u.created_at)} />
      <Row label="Market"         value={u.market || "—"} />
      <Row label="Premium"        value={u.is_premium ? "Yes" : "No"} />
      <Row label="Advertiser"     value={u.is_advertiser ? "Yes" : "No"} />
    </div>
  );
}

function AuditTab({ userId }) {
  const [items, setItems] = useState([]);
  const [next, setNext] = useState(null);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async (cursor = null) => {
    setLoading(true);
    try {
      const p = new URLSearchParams({ limit: "50" });
      if (cursor) p.set("cursor", cursor);
      const r = await axios.get(
        `${API}/admin/users/${userId}/audit-log?${p.toString()}`,
        {withCredentials: true});
      setItems((prev) => cursor ? [...prev, ...(r.data.items || [])]
                                                  : (r.data.items || []));
      setNext(r.data.next_cursor || null);
    } finally {
      setLoading(false);
    }
  }, [userId]);
  useEffect(() => { load(null); }, [load]);
  return (
    <div data-testid="tab-audit-log">
      <AuditTable items={items} loading={loading} />
      {next && (
        <div style={{textAlign: "center", marginTop: 12}}>
          <button onClick={() => load(next)}
                          data-testid="audit-load-more"
                          style={{padding: "8px 14px", borderRadius: 6,
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

function ResourcesTab({ u }) {
  return (
    <div data-testid="tab-resources"
            style={{padding: 14, background: COLORS.surface,
                        border: `1px solid ${COLORS.border}`, borderRadius: 10}}>
      {u.creator_profile && (
        <div style={{marginBottom: 12}}>
          <div style={{fontSize: 12, color: COLORS.muted,
                                textTransform: "uppercase", marginBottom: 4}}>
            Creator profile
          </div>
          <Row label="Display name" value={u.creator_profile.display_name || "—"} />
          <Row label="Status"
                  value={u.creator_profile.application_status || "—"} />
          <Row label="Approved at"
                  value={fmtDate(u.creator_profile.approved_at)} />
        </div>
      )}
      {Array.isArray(u.businesses) && u.businesses.length > 0 && (
        <div>
          <div style={{fontSize: 12, color: COLORS.muted,
                                textTransform: "uppercase", marginBottom: 4}}>
            Businesses
          </div>
          {u.businesses.map((b, i) => (
            <Row key={i} label={b.name || b.business_id}
                      value={b.market || b.city || "—"} />
          ))}
        </div>
      )}
      {!u.creator_profile && !(u.businesses?.length) && (
        <div style={{color: COLORS.muted, fontSize: 13}}>
          No associated resources.
        </div>
      )}
    </div>
  );
}

function Row({ label, value }) {
  return (
    <div style={{display: "flex", padding: "6px 0", fontSize: 13,
                          borderBottom: `1px solid ${COLORS.border}`}}>
      <div style={{width: 140, color: COLORS.muted}}>{label}</div>
      <div style={{color: COLORS.text}}>{value}</div>
    </div>
  );
}

function AuditTable({ items, loading }) {
  if (loading && items.length === 0) {
    return <div style={{color: COLORS.muted, padding: 14}}>Loading…</div>;
  }
  if (items.length === 0) {
    return (
      <div data-testid="audit-empty"
              style={{color: COLORS.muted, padding: 14, borderRadius: 10,
                          background: COLORS.surface,
                          border: `1px solid ${COLORS.border}`}}>
        No audit entries.
      </div>
    );
  }
  return (
    <div style={{background: COLORS.surface, borderRadius: 10,
                          border: `1px solid ${COLORS.border}`,
                          overflow: "hidden"}}>
      <table style={{width: "100%", borderCollapse: "collapse"}}>
        <thead>
          <tr>
            <th style={th}>When</th>
            <th style={th}>Action</th>
            <th style={th}>Changed By</th>
            <th style={th}>Diff</th>
            <th style={th}>Reason</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.audit_id} data-testid={`audit-row-${r.audit_id}`}>
              <td style={td}>{fmtDate(r.created_at)}</td>
              <td style={td}>
                <Badge palette={{bg: "rgba(245,158,11,0.15)", fg: COLORS.amber}}>
                  {r.action}
                </Badge>
              </td>
              <td style={td}>{r.changed_by_admin_id || "—"}</td>
              <td style={td}>{String(r.old_value ?? "—")} → {String(r.new_value ?? "—")}</td>
              <td style={td}>{r.reason || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const th = {textAlign: "left", padding: "8px 10px", fontSize: 11,
                      color: COLORS.muted, textTransform: "uppercase",
                      letterSpacing: 0.5,
                      borderBottom: `1px solid ${COLORS.border}`};
const td = {padding: "8px 10px", fontSize: 13, color: COLORS.text,
                      borderBottom: `1px solid ${COLORS.border}`};

export default function AdminUserDetail() {
  const { user_id } = useParams();
  const { user: me } = useAuth();
  const [u, setU] = useState(null);
  const [error, setError] = useState("");
  const [tab, setTab] = useState("activity");
  const [modal, setModal] = useState(null);
  const [toast, setToast] = useState(null);
  const [adminCount, setAdminCount] = useState(0);

  const fetchUser = useCallback(async () => {
    setError("");
    try {
      const r = await axios.get(`${API}/admin/users/${user_id}`,
                                                {withCredentials: true});
      setU(r.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load user.");
    }
  }, [user_id]);

  const fetchAdminCount = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/users/stats`,
                                                {withCredentials: true});
      setAdminCount(r.data?.by_role?.admin || 0);
    } catch (_) { /* non-blocking */ }
  }, []);

  useEffect(() => { fetchUser(); fetchAdminCount(); },
                  [fetchUser, fetchAdminCount]);

  // Auto-dismiss toast.
  useEffect(() => {
    if (!toast) return undefined;
    const t = setTimeout(() => setToast(null), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  if (error) {
    return (
      <div style={{padding: 24, color: COLORS.text, background: COLORS.bg,
                            minHeight: "100vh"}}>
        <AdminBreadcrumb segments={[
          {label: "Admin", href: "/admin"},
          {label: "User Management", href: "/admin/users"},
          {label: user_id},
        ]} />
        <div data-testid="detail-error"
                style={{padding: 14, borderRadius: 10,
                            background: "rgba(239,68,68,0.1)", color: "#fda4af",
                            border: "1px solid rgba(239,68,68,0.3)"}}>
          {String(error)}
        </div>
      </div>
    );
  }
  if (!u) {
    return (
      <div style={{padding: 24, color: COLORS.muted, background: COLORS.bg,
                            minHeight: "100vh"}}
              data-testid="detail-loading">
        Loading…
      </div>
    );
  }

  const onSuccess = (m) => {
    setModal(null);
    setToast(m);
    fetchUser();
    fetchAdminCount();
  };
  const isActive = (u.status || "active") === "active";

  return (
    <div style={{padding: 24, color: COLORS.text, background: COLORS.bg,
                          minHeight: "100vh"}}
            data-testid="admin-user-detail">
      <AdminBreadcrumb segments={[
        {label: "Admin", href: "/admin"},
        {label: "User Management", href: "/admin/users"},
        {label: u.email || user_id},
      ]} />

      <div style={{display: "flex", justifyContent: "space-between",
                            alignItems: "baseline", marginBottom: 14}}>
        <h1 style={{fontSize: 22, fontWeight: 700}}>{u.email}</h1>
        <div style={{display: "flex", gap: 8}}>
          <Link to="/admin/users"
                    data-testid="back-to-list"
                    style={{padding: "6px 12px", borderRadius: 6,
                                color: COLORS.muted,
                                border: `1px solid ${COLORS.border}`,
                                fontSize: 13, textDecoration: "none"}}>
            ← All users
          </Link>
          <button onClick={() => setModal({kind: "role"})}
                          data-testid="action-change-role"
                          style={btnStyle("amber")}>
            Change Role
          </button>
          {isActive ? (
            <button onClick={() => setModal({kind: "deactivate"})}
                            data-testid="action-deactivate"
                            disabled={u.user_id === me?.user_id}
                            style={btnStyle("red",
                                                  u.user_id === me?.user_id)}>
              Deactivate
            </button>
          ) : (
            <button onClick={() => setModal({kind: "activate"})}
                            data-testid="action-activate"
                            style={btnStyle("green")}>
              Activate
            </button>
          )}
        </div>
      </div>

      <ProfileCard u={u} />

      <div style={{display: "flex", gap: 8, marginBottom: 12}}>
        <Tab active={tab === "activity"} onClick={() => setTab("activity")}
                  testid="tab-btn-activity">Activity</Tab>
        <Tab active={tab === "audit"} onClick={() => setTab("audit")}
                  testid="tab-btn-audit">Audit Log</Tab>
        <Tab active={tab === "resources"} onClick={() => setTab("resources")}
                  testid="tab-btn-resources">Resources</Tab>
      </div>

      {tab === "activity" && <ActivityTab u={u} />}
      {tab === "audit" && <AuditTab userId={u.user_id} />}
      {tab === "resources" && <ResourcesTab u={u} />}

      {modal?.kind === "role" && (
        <ChangeRoleModal user={u}
                                      currentAdminId={me?.user_id}
                                      adminCount={adminCount}
                                      onClose={() => setModal(null)}
                                      onSuccess={onSuccess} />
      )}
      {modal?.kind === "deactivate" && (
        <DeactivateModal user={u}
                                      currentAdminId={me?.user_id}
                                      adminCount={adminCount}
                                      onClose={() => setModal(null)}
                                      onSuccess={onSuccess} />
      )}
      {modal?.kind === "activate" && (
        <ActivateModal user={u}
                                    onClose={() => setModal(null)}
                                    onSuccess={onSuccess} />
      )}

      <ToastView msg={toast} />
    </div>
  );
}

function btnStyle(kind, disabled) {
  const map = {
    amber: COLORS.amber,
    red:   COLORS.red,
    green: COLORS.green,
  };
  return {
    padding: "6px 12px", borderRadius: 6,
    background: disabled ? "#3f3f46" : map[kind],
    color: disabled ? "#71717a" : (kind === "red" ? "#fff" : "#0a0a0c"),
    border: 0, fontWeight: 600, fontSize: 13,
    cursor: disabled ? "not-allowed" : "pointer",
  };
}
