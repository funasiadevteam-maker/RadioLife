// Phase 19a Part 5 FRONTEND — /admin/users
//
// List page with stats strip, filter bar (role / status / debounced search),
// users table, action menu (View / Change Role / Activate or Deactivate),
// and shared ChangeRoleModal + DeactivateModal + ActivateModal.
//
// Backend endpoints (commit 8fe0531):
//   GET    /api/admin/users           (paginated, role/status/search filters)
//   GET    /api/admin/users/stats     (counts + 7d windows)
//   PATCH  /api/admin/users/{id}/role
//   POST   /api/admin/users/{id}/deactivate
//   POST   /api/admin/users/{id}/activate?force=true
//
// Visual style follows AdminPodcasts.jsx: inline styles, dark base
// (#0a0a0c), amber accent (#f59e0b), green/red action buttons.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import AdminBreadcrumb from "./shell/AdminBreadcrumb";
import { useAuth } from "@/AuthContext";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

// ─── Style tokens (match AdminPodcasts.jsx) ─────────────────────────────
const COLORS = {
  bg: "#0a0a0c",
  surface: "rgba(255,255,255,0.02)",
  border: "rgba(255,255,255,0.06)",
  text: "#e7e7ea",
  muted: "#9aa3af",
  amber: "#f59e0b",
  green: "#22c55e",
  red: "#ef4444",
  inputBg: "#111114",
};

const ROLE_COLORS = {
  admin:               { bg: "rgba(245,158,11,0.15)",   fg: "#fbbf24" },
  creator:             { bg: "rgba(59,130,246,0.15)",   fg: "#60a5fa" },
  business_partner:    { bg: "rgba(168,85,247,0.15)",   fg: "#c084fc" },
  advertiser:          { bg: "rgba(236,72,153,0.15)",   fg: "#f472b6" },
  moderator:           { bg: "rgba(20,184,166,0.15)",   fg: "#5eead4" },
  listener:            { bg: "rgba(255,255,255,0.05)",  fg: "#9aa3af" },
  user:                { bg: "rgba(255,255,255,0.05)",  fg: "#9aa3af" },
};

const STATUS_COLORS = {
  active:    { bg: "rgba(34,197,94,0.15)",   fg: "#4ade80" },
  inactive:  { bg: "rgba(156,163,175,0.15)", fg: "#9ca3af" },
  suspended: { bg: "rgba(239,68,68,0.15)",   fg: "#fda4af" },
};

function Badge({ children, palette, testid }) {
  const c = palette || { bg: "rgba(255,255,255,0.05)", fg: COLORS.muted };
  return (
    <span data-testid={testid}
              style={{display: "inline-block", padding: "2px 8px",
                          borderRadius: 999, fontSize: 11, fontWeight: 600,
                          background: c.bg, color: c.fg,
                          textTransform: "capitalize"}}>
      {children || "—"}
    </span>
  );
}

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toISOString().slice(0, 10);
  } catch (_) { return "—"; }
}


// ════════════════════════════════════════════════════════════════════════
// Stats strip
// ════════════════════════════════════════════════════════════════════════
function StatsStrip({ stats, loading }) {
  const card = (label, value, testid) => (
    <div data-testid={testid}
            style={{flex: 1, minWidth: 160, padding: 14, borderRadius: 10,
                        background: COLORS.surface,
                        border: `1px solid ${COLORS.border}`}}>
      <div style={{fontSize: 11, color: COLORS.muted,
                          textTransform: "uppercase", letterSpacing: 0.5}}>
        {label}
      </div>
      <div style={{fontSize: 22, fontWeight: 700, color: COLORS.text,
                          marginTop: 4}}>
        {loading ? "…" : (value ?? 0).toLocaleString()}
      </div>
    </div>
  );
  const s = stats || {};
  const total     = s.total;
  const active    = s.by_status?.active;
  const inactive  = (s.by_status?.inactive || 0) + (s.by_status?.suspended || 0);
  const creators  = s.by_role?.creator;
  return (
    <div data-testid="admin-users-stats"
            style={{display: "flex", gap: 10, marginBottom: 14,
                        flexWrap: "wrap"}}>
      {card("Total Users",  total,    "stat-total-users")}
      {card("Active",       active,   "stat-active-users")}
      {card("Inactive",     inactive, "stat-inactive-users")}
      {card("Creators",     creators, "stat-creator-users")}
    </div>
  );
}


// ════════════════════════════════════════════════════════════════════════
// Filter bar
// ════════════════════════════════════════════════════════════════════════
function FilterBar({ role, setRole, status, setStatus, search, setSearch,
                                onClear, hasFilters }) {
  return (
    <div style={{display: "flex", gap: 8, marginBottom: 12,
                          alignItems: "center", flexWrap: "wrap"}}>
      <select value={role} onChange={(e) => setRole(e.target.value)}
                      data-testid="filter-role"
                      style={selectStyle}>
        <option value="">All roles</option>
        <option value="admin">Admin</option>
        <option value="creator">Creator</option>
        <option value="business_partner">Business Partner</option>
        <option value="advertiser">Advertiser</option>
        <option value="moderator">Moderator</option>
        <option value="listener">Listener</option>
        <option value="user">User</option>
      </select>
      <select value={status} onChange={(e) => setStatus(e.target.value)}
                      data-testid="filter-status"
                      style={selectStyle}>
        <option value="">All statuses</option>
        <option value="active">Active</option>
        <option value="inactive">Inactive</option>
        <option value="suspended">Suspended</option>
      </select>
      <input type="text" value={search} placeholder="Search email or name…"
                  onChange={(e) => setSearch(e.target.value)}
                  data-testid="filter-search"
                  style={{...selectStyle, minWidth: 220, flex: 1}} />
      {hasFilters && (
        <button onClick={onClear}
                        data-testid="filter-clear"
                        style={{padding: "6px 12px", borderRadius: 6,
                                    background: "transparent", color: COLORS.muted,
                                    border: `1px solid ${COLORS.border}`,
                                    cursor: "pointer"}}>
          Clear
        </button>
      )}
      <Link to="/admin/users/audit-log"
                data-testid="open-audit-log"
                style={{marginLeft: "auto", color: COLORS.amber, fontSize: 13,
                            textDecoration: "none"}}>
        View Audit Log →
      </Link>
    </div>
  );
}

const selectStyle = {
  padding: "6px 10px", borderRadius: 6, background: COLORS.inputBg,
  color: COLORS.text, border: `1px solid ${COLORS.border}`,
  fontSize: 13, outline: "none",
};


// ════════════════════════════════════════════════════════════════════════
// Users table
// ════════════════════════════════════════════════════════════════════════
function UsersTable({ rows, currentAdminId, onAction, loading }) {
  const navigate = useNavigate();
  const headStyle = {textAlign: "left", padding: "8px 10px",
                                fontSize: 11, color: COLORS.muted,
                                textTransform: "uppercase", letterSpacing: 0.5,
                                borderBottom: `1px solid ${COLORS.border}`};
  const cellStyle = {padding: "10px", fontSize: 13, color: COLORS.text,
                                borderBottom: `1px solid ${COLORS.border}`};
  return (
    <div data-testid="admin-users-table"
            style={{borderRadius: 10, overflow: "hidden",
                        border: `1px solid ${COLORS.border}`,
                        background: COLORS.surface}}>
      <table style={{width: "100%", borderCollapse: "collapse"}}>
        <thead>
          <tr>
            <th style={headStyle}>Email</th>
            <th style={headStyle}>Name</th>
            <th style={headStyle}>Role</th>
            <th style={headStyle}>Status</th>
            <th style={headStyle}>Created</th>
            <th style={headStyle}>Last Login</th>
            <th style={{...headStyle, textAlign: "right"}}>Actions</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr><td colSpan={7} style={{...cellStyle, color: COLORS.muted,
                                                          textAlign: "center"}}>
              Loading…
            </td></tr>
          )}
          {!loading && rows.length === 0 && (
            <tr><td colSpan={7} style={{...cellStyle, color: COLORS.muted,
                                                          textAlign: "center", padding: 20}}>
              No users match these filters.
            </td></tr>
          )}
          {rows.map((u) => {
            const isSelf = u.user_id === currentAdminId;
            const st = u.status || "active";
            return (
              <tr key={u.user_id}
                      data-testid={`user-row-${u.user_id}`}
                      onClick={() => navigate(`/admin/users/${u.user_id}`)}
                      style={{cursor: "pointer"}}>
                <td style={cellStyle}>
                  {u.email}
                  {isSelf && <span style={{marginLeft: 6, fontSize: 10,
                                                            color: COLORS.amber}}
                                            data-testid="you-tag">
                    (you)
                  </span>}
                </td>
                <td style={cellStyle}>{u.name || "—"}</td>
                <td style={cellStyle}>
                  <Badge palette={ROLE_COLORS[u.role] || ROLE_COLORS.user}
                              testid={`role-${u.user_id}`}>
                    {u.role || "user"}
                  </Badge>
                </td>
                <td style={cellStyle}>
                  <Badge palette={STATUS_COLORS[st]}
                              testid={`status-${u.user_id}`}>
                    {st}
                  </Badge>
                </td>
                <td style={cellStyle}>{fmtDate(u.created_at)}</td>
                <td style={cellStyle}>{fmtDate(u.last_login_at)}</td>
                <td style={{...cellStyle, textAlign: "right"}}
                      onClick={(e) => e.stopPropagation()}>
                  <RowActions user={u} isSelf={isSelf} onAction={onAction} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function RowActions({ user, isSelf, onAction }) {
  const [open, setOpen] = useState(false);
  const isActive = (user.status || "active") === "active";
  return (
    <div style={{position: "relative", display: "inline-block"}}>
      <button onClick={() => setOpen((v) => !v)}
                      data-testid={`row-actions-${user.user_id}`}
                      style={{padding: "4px 10px", borderRadius: 6,
                                  background: "transparent",
                                  border: `1px solid ${COLORS.border}`,
                                  color: COLORS.text, cursor: "pointer", fontSize: 12}}>
        ⋯
      </button>
      {open && (
        <>
          <div onClick={() => setOpen(false)}
                  style={{position: "fixed", inset: 0, zIndex: 10}} />
          <div data-testid={`row-actions-menu-${user.user_id}`}
                  style={{position: "absolute", right: 0, top: "100%",
                              marginTop: 4, zIndex: 11, minWidth: 160,
                              background: "#16161a", borderRadius: 8,
                              border: `1px solid ${COLORS.border}`,
                              boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                              overflow: "hidden"}}>
            <MenuItem onClick={() => { setOpen(false); onAction("view", user); }}
                              testid={`menu-view-${user.user_id}`}>View Details</MenuItem>
            <MenuItem onClick={() => { setOpen(false); onAction("role", user); }}
                              testid={`menu-role-${user.user_id}`}>Change Role</MenuItem>
            {isActive ? (
              <MenuItem onClick={() => { setOpen(false); onAction("deactivate", user); }}
                                testid={`menu-deactivate-${user.user_id}`}
                                disabled={isSelf}
                                color={COLORS.red}>
                Deactivate
              </MenuItem>
            ) : (
              <MenuItem onClick={() => { setOpen(false); onAction("activate", user); }}
                                testid={`menu-activate-${user.user_id}`}
                                color={COLORS.green}>
                Activate
              </MenuItem>
            )}
          </div>
        </>
      )}
    </div>
  );
}

function MenuItem({ children, onClick, testid, color, disabled }) {
  return (
    <button onClick={disabled ? undefined : onClick}
                    disabled={disabled}
                    data-testid={testid}
                    style={{display: "block", width: "100%", padding: "8px 12px",
                                background: "transparent", border: 0,
                                color: disabled ? "#52525b" : (color || COLORS.text),
                                textAlign: "left", fontSize: 13,
                                cursor: disabled ? "not-allowed" : "pointer"}}>
      {children}
    </button>
  );
}


// ════════════════════════════════════════════════════════════════════════
// Shared modal shell + Change Role / Deactivate / Activate
// ════════════════════════════════════════════════════════════════════════
export function ModalShell({ title, children, onClose, testid }) {
  return (
    <div data-testid={testid}
            onClick={onClose}
            style={{position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
                        display: "flex", alignItems: "center",
                        justifyContent: "center", zIndex: 50, padding: 20}}>
      <div onClick={(e) => e.stopPropagation()}
              style={{width: "min(520px, 100%)", background: "#16161a",
                          borderRadius: 12, border: `1px solid ${COLORS.border}`,
                          padding: 20, maxHeight: "90vh", overflowY: "auto"}}>
        <div style={{fontSize: 16, fontWeight: 700, color: COLORS.text,
                            marginBottom: 12}}>
          {title}
        </div>
        {children}
      </div>
    </div>
  );
}

const ROLE_OPTIONS = ["admin", "creator", "business_partner", "advertiser",
                                  "moderator", "listener", "user"];

export function ChangeRoleModal({ user, currentAdminId, adminCount, onClose,
                                                            onSuccess }) {
  const [newRole, setNewRole] = useState(() => {
    return ROLE_OPTIONS.find((r) => r !== user.role) || "creator";
  });
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isSelf = user.user_id === currentAdminId;
  const demotingSelf = isSelf && newRole !== "admin";
  const lastAdminGuard = user.role === "admin" && newRole !== "admin"
                                          && (adminCount || 0) <= 1;
  const reasonTooShort = reason.trim().length < 5;
  const noOp = newRole === user.role;
  const disabled = submitting || demotingSelf || lastAdminGuard
                              || reasonTooShort || noOp;

  const submit = async () => {
    setSubmitting(true); setError("");
    try {
      await axios.patch(`${API}/admin/users/${user.user_id}/role`,
                                          {new_role: newRole, reason: reason.trim()},
                                          {withCredentials: true});
      onSuccess?.(`Role updated to ${newRole}`);
    } catch (e) {
      const d = e?.response?.data?.detail || e?.response?.data;
      setError(typeof d === "string" ? d : (d?.status || "Update failed."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title={`Change role — ${user.email}`} onClose={onClose}
                          testid="change-role-modal">
      <div style={{fontSize: 13, color: COLORS.muted, marginBottom: 10}}>
        Current role:&nbsp;
        <Badge palette={ROLE_COLORS[user.role]}>{user.role || "user"}</Badge>
      </div>
      <label style={labelStyle}>New role</label>
      <select value={newRole} onChange={(e) => setNewRole(e.target.value)}
                      data-testid="new-role-select"
                      style={{...selectStyle, width: "100%", marginBottom: 12}}>
        {ROLE_OPTIONS.filter((r) => r !== user.role).map((r) => (
          <option key={r} value={r}>{r}</option>
        ))}
      </select>
      <label style={labelStyle}>
        Reason <span style={{color: COLORS.muted}}>
          ({reason.trim().length}/5 min)
        </span>
      </label>
      <textarea value={reason} onChange={(e) => setReason(e.target.value)}
                          data-testid="reason-textarea"
                          rows={3}
                          style={{...selectStyle, width: "100%", marginBottom: 12,
                                      resize: "vertical", fontFamily: "inherit"}} />
      {demotingSelf && (
        <Warn testid="warn-self">You cannot change your own role.</Warn>
      )}
      {lastAdminGuard && (
        <Warn testid="warn-last-admin">
          Cannot demote the last admin. Promote another user to admin first.
        </Warn>
      )}
      {error && <Warn testid="modal-error">{String(error)}</Warn>}
      <ModalButtons onClose={onClose} onConfirm={submit}
                              disabled={disabled} confirmTestId="confirm-role" />
    </ModalShell>
  );
}

export function DeactivateModal({ user, currentAdminId, adminCount, onClose,
                                                            onSuccess }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const isSelf = user.user_id === currentAdminId;
  const lastAdminGuard = user.role === "admin" && (adminCount || 0) <= 1;
  const reasonTooShort = reason.trim().length < 5;
  const disabled = submitting || isSelf || lastAdminGuard || reasonTooShort;

  const submit = async () => {
    setSubmitting(true); setError("");
    try {
      await axios.post(`${API}/admin/users/${user.user_id}/deactivate`,
                                  {reason: reason.trim()},
                                  {withCredentials: true});
      onSuccess?.(`${user.email} deactivated`);
    } catch (e) {
      const d = e?.response?.data?.detail || e?.response?.data;
      setError(typeof d === "string" ? d : (d?.status || "Deactivate failed."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title={`Deactivate — ${user.email}`} onClose={onClose}
                          testid="deactivate-modal">
      <div style={{fontSize: 13, color: COLORS.muted, marginBottom: 12}}>
        This will prevent the user from logging in. Active sessions may
        remain valid until expiry.
      </div>
      <label style={labelStyle}>
        Reason <span style={{color: COLORS.muted}}>
          ({reason.trim().length}/5 min)
        </span>
      </label>
      <textarea value={reason} onChange={(e) => setReason(e.target.value)}
                          data-testid="reason-textarea"
                          rows={3}
                          style={{...selectStyle, width: "100%", marginBottom: 12,
                                      resize: "vertical", fontFamily: "inherit"}} />
      {isSelf && <Warn testid="warn-self">You cannot deactivate yourself.</Warn>}
      {lastAdminGuard && (
        <Warn testid="warn-last-admin">Cannot deactivate the last admin.</Warn>
      )}
      {error && <Warn testid="modal-error">{String(error)}</Warn>}
      <ModalButtons onClose={onClose} onConfirm={submit} disabled={disabled}
                              confirmLabel="Deactivate"
                              confirmColor={COLORS.red}
                              confirmTestId="confirm-deactivate" />
    </ModalShell>
  );
}

export function ActivateModal({ user, onClose, onSuccess }) {
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const isSuspended = (user.status || "active") === "suspended";
  const needReason = isSuspended;
  const disabled = submitting || (needReason && reason.trim().length < 5);

  const submit = async () => {
    setSubmitting(true); setError("");
    try {
      await axios.post(
        `${API}/admin/users/${user.user_id}/activate${isSuspended ? "?force=true" : ""}`,
        {reason: reason.trim()},
        {withCredentials: true});
      onSuccess?.(`${user.email} reactivated`);
    } catch (e) {
      const d = e?.response?.data?.detail || e?.response?.data;
      setError(typeof d === "string" ? d : (d?.status || "Activate failed."));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell title={`Activate — ${user.email}`} onClose={onClose}
                          testid="activate-modal">
      {isSuspended && (
        <div style={{padding: 10, marginBottom: 12, borderRadius: 8,
                            background: "rgba(245,158,11,0.1)", color: "#fde68a",
                            border: "1px solid rgba(245,158,11,0.25)",
                            fontSize: 12}}>
          This user is suspended. Reactivation requires a justification and
          will be force-applied.
        </div>
      )}
      <label style={labelStyle}>
        Reason {needReason && <span style={{color: COLORS.muted}}>
          ({reason.trim().length}/5 min)
        </span>}
        {!needReason && <span style={{color: COLORS.muted}}> (optional)</span>}
      </label>
      <textarea value={reason} onChange={(e) => setReason(e.target.value)}
                          data-testid="reason-textarea"
                          rows={3}
                          style={{...selectStyle, width: "100%", marginBottom: 12,
                                      resize: "vertical", fontFamily: "inherit"}} />
      {error && <Warn testid="modal-error">{String(error)}</Warn>}
      <ModalButtons onClose={onClose} onConfirm={submit} disabled={disabled}
                              confirmLabel="Activate"
                              confirmColor={COLORS.green}
                              confirmTestId="confirm-activate" />
    </ModalShell>
  );
}

const labelStyle = {display: "block", fontSize: 12, color: COLORS.muted,
                                marginBottom: 4};

function Warn({ children, testid }) {
  return (
    <div data-testid={testid}
            style={{padding: 10, marginBottom: 10, borderRadius: 8,
                        background: "rgba(239,68,68,0.1)", color: "#fda4af",
                        border: "1px solid rgba(239,68,68,0.3)",
                        fontSize: 12}}>
      {children}
    </div>
  );
}

function ModalButtons({ onClose, onConfirm, disabled, confirmLabel = "Confirm",
                                          confirmColor, confirmTestId }) {
  return (
    <div style={{display: "flex", gap: 8, justifyContent: "flex-end",
                          marginTop: 6}}>
      <button onClick={onClose}
                      data-testid="modal-cancel"
                      style={{padding: "8px 14px", borderRadius: 6,
                                  background: "transparent", color: COLORS.text,
                                  border: `1px solid ${COLORS.border}`,
                                  cursor: "pointer"}}>
        Cancel
      </button>
      <button onClick={disabled ? undefined : onConfirm}
                      disabled={disabled}
                      data-testid={confirmTestId}
                      style={{padding: "8px 14px", borderRadius: 6,
                                  background: disabled ? "#3f3f46"
                                                          : (confirmColor || COLORS.amber),
                                  color: disabled ? "#71717a" : "#0a0a0c",
                                  border: 0, fontWeight: 600,
                                  cursor: disabled ? "not-allowed" : "pointer"}}>
        {confirmLabel}
      </button>
    </div>
  );
}


// ════════════════════════════════════════════════════════════════════════
// Toast (lightweight, dismisses after 3s)
// ════════════════════════════════════════════════════════════════════════
function useToast() {
  const [msg, setMsg] = useState(null);
  useEffect(() => {
    if (!msg) return undefined;
    const t = setTimeout(() => setMsg(null), 3000);
    return () => clearTimeout(t);
  }, [msg]);
  return [msg, setMsg];
}

export function ToastView({ msg }) {
  if (!msg) return null;
  return (
    <div data-testid="toast"
            style={{position: "fixed", bottom: 24, right: 24, zIndex: 100,
                        padding: "10px 16px", borderRadius: 8,
                        background: "#16161a", color: COLORS.text,
                        border: `1px solid ${COLORS.border}`,
                        boxShadow: "0 8px 24px rgba(0,0,0,0.4)",
                        fontSize: 13}}>
      {msg}
    </div>
  );
}


// ════════════════════════════════════════════════════════════════════════
// Top-level page
// ════════════════════════════════════════════════════════════════════════
export default function AdminUsers() {
  const { user } = useAuth();
  const currentAdminId = user?.user_id;

  const [stats, setStats] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [nextCursor, setNextCursor] = useState(null);

  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  const [modal, setModal] = useState(null);  // {kind, user}
  const [toast, setToast] = useToast();

  // Debounce search 350ms
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 350);
    return () => clearTimeout(t);
  }, [search]);

  const fetchStats = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/users/stats`,
                                                {withCredentials: true});
      setStats(r.data);
    } catch (e) {
      // non-blocking; table still renders.
    }
  }, []);

  const fetchUsers = useCallback(async (cursor = null) => {
    setLoading(true); setError("");
    try {
      const params = new URLSearchParams();
      if (role) params.set("role", role);
      if (status) params.set("status", status);
      if (debouncedSearch) params.set("search", debouncedSearch);
      params.set("limit", "25");
      if (cursor) params.set("cursor", cursor);
      const r = await axios.get(`${API}/admin/users?${params.toString()}`,
                                                {withCredentials: true});
      setRows((prev) => cursor ? [...prev, ...(r.data.items || [])]
                                                  : (r.data.items || []));
      setNextCursor(r.data.next_cursor || null);
    } catch (e) {
      setError(e?.response?.data?.detail || "Failed to load users.");
      if (!cursor) setRows([]);
    } finally {
      setLoading(false);
    }
  }, [role, status, debouncedSearch]);

  useEffect(() => { fetchStats(); }, [fetchStats]);
  useEffect(() => { fetchUsers(null); }, [fetchUsers]);

  const hasFilters = !!(role || status || debouncedSearch);
  const adminCount = stats?.by_role?.admin || 0;

  const onAction = (kind, u) => {
    if (kind === "view") {
      window.location.href = `/admin/users/${u.user_id}`;
      return;
    }
    setModal({ kind, user: u });
  };

  const onModalSuccess = (message) => {
    setModal(null);
    setToast(message);
    fetchStats();
    fetchUsers(null);
  };

  return (
    <div style={{padding: 24, color: COLORS.text, background: COLORS.bg,
                          minHeight: "100vh"}}
            data-testid="admin-users-page">
      <AdminBreadcrumb segments={[
        {label: "Admin", href: "/admin"},
        {label: "User Management"},
      ]} />
      <h1 style={{fontSize: 24, fontWeight: 700, marginBottom: 14}}>
        User Management
      </h1>

      <StatsStrip stats={stats} loading={!stats} />

      <FilterBar role={role} setRole={setRole}
                          status={status} setStatus={setStatus}
                          search={search} setSearch={setSearch}
                          hasFilters={hasFilters}
                          onClear={() => { setRole(""); setStatus(""); setSearch(""); }} />

      {error && (
        <div data-testid="users-error"
                style={{padding: 10, marginBottom: 10, borderRadius: 8,
                            background: "rgba(239,68,68,0.1)", color: "#fda4af",
                            border: "1px solid rgba(239,68,68,0.3)"}}>
          {String(error)}
        </div>
      )}

      <UsersTable rows={rows} currentAdminId={currentAdminId}
                            onAction={onAction} loading={loading && rows.length === 0} />

      {nextCursor && (
        <div style={{textAlign: "center", marginTop: 14}}>
          <button onClick={() => fetchUsers(nextCursor)}
                          data-testid="load-more"
                          style={{padding: "8px 16px", borderRadius: 6,
                                      background: "transparent", color: COLORS.amber,
                                      border: `1px solid ${COLORS.border}`,
                                      cursor: "pointer"}}>
            Load more
          </button>
        </div>
      )}

      {modal?.kind === "role" && (
        <ChangeRoleModal user={modal.user}
                                      currentAdminId={currentAdminId}
                                      adminCount={adminCount}
                                      onClose={() => setModal(null)}
                                      onSuccess={onModalSuccess} />
      )}
      {modal?.kind === "deactivate" && (
        <DeactivateModal user={modal.user}
                                      currentAdminId={currentAdminId}
                                      adminCount={adminCount}
                                      onClose={() => setModal(null)}
                                      onSuccess={onModalSuccess} />
      )}
      {modal?.kind === "activate" && (
        <ActivateModal user={modal.user}
                                    onClose={() => setModal(null)}
                                    onSuccess={onModalSuccess} />
      )}

      <ToastView msg={toast} />
    </div>
  );
}

// Re-export style tokens + helpers for the detail/audit pages.
export { COLORS, ROLE_COLORS, STATUS_COLORS, Badge, fmtDate };
