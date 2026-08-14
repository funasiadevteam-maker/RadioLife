// Phase SC.1 — Admin: Stripe Connect merchants table.  Legacy + RadioLife
// both render this at /admin/stripe-connect.  Basic styling — will get
// designed properly in SC.2 when the merchant self-service portal ships.
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

const STATUS_TONE = {
  active:                                                                  { bg: "#10b98122", fg: "#10b981", label: "Active"                       },
  payouts_disabled:                                                { bg: "#f59e0b22", fg: "#f59e0b", label: "Payouts Disabled" },
  verification_pending:                                          { bg: "#eab30822", fg: "#eab308", label: "Verification Pending" },
  onboarding_in_progress:                                    { bg: "#3b82f622", fg: "#3b82f6", label: "In Progress"                   },
  onboarding_incomplete:                                        { bg: "#64748b22", fg: "#94a3b8", label: "Incomplete"                    },
  not_started:                                                            { bg: "#64748b22", fg: "#94a3b8", label: "Not Started"                  },
  restricted:                                                              { bg: "#ef444422", fg: "#ef4444", label: "Restricted"                    },
  rejected:                                                                { bg: "#ef444422", fg: "#ef4444", label: "Rejected"                        },
};

export default function AdminStripeConnect({ embedded = false } = {}) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [rowBusy, setRowBusy] = useState({});     // {merchant_id: "refresh"|"onboard"|"dashboard"}
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const qs = statusFilter ? `?status=${statusFilter}&limit=200` : "?limit=200";
      const { data } = await axios.get(`${API}/admin/stripe/connect/all-merchants${qs}`,
                                                              { withCredentials: true });
      setItems(data?.items || []);
      setTotal(data?.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message || "unknown"}`);
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const setBusy = (id, mode) =>
    setRowBusy((prev) => ({ ...prev, [id]: mode }));
  const clearBusy = (id) =>
    setRowBusy((prev) => { const n = { ...prev }; delete n[id]; return n; });

  const handleRefresh = async (merchant) => {
    setBusy(merchant.merchant_id, "refresh");
    try {
      const { data } = await axios.post(
        `${API}/stripe/connect/status/refresh`,
        { merchant_id: merchant.merchant_id },
        { withCredentials: true });
      toast.success(`Refreshed · status=${data.stripe_onboarding_status}`);
      await load();
    } catch (e) {
      toast.error(`Refresh failed: ${e?.response?.data?.detail || e.message}`);
    } finally { clearBusy(merchant.merchant_id); }
  };

  const handleOnboard = async (merchant) => {
    setBusy(merchant.merchant_id, "onboard");
    try {
      const { data } = await axios.post(
        `${API}/stripe/connect/onboarding/start`,
        { merchant_id: merchant.merchant_id },
        { withCredentials: true });
      if (data.onboarding_url) {
        window.open(data.onboarding_url, "_blank", "noopener,noreferrer");
        toast.success("Onboarding link opened in a new tab");
        // Reflect status change locally without waiting for the next load
        setItems((prev) => prev.map((m) =>
          m.merchant_id === merchant.merchant_id
            ? { ...m, stripe_account_id: data.stripe_account_id,
                stripe_onboarding_status: "onboarding_in_progress" }
            : m));
      }
    } catch (e) {
      toast.error(`Onboarding start failed: ${e?.response?.data?.detail || e.message}`);
    } finally { clearBusy(merchant.merchant_id); }
  };

  const handleDashboard = async (merchant) => {
    setBusy(merchant.merchant_id, "dashboard");
    try {
      const { data } = await axios.post(
        `${API}/stripe/connect/dashboard-link`,
        { merchant_id: merchant.merchant_id },
        { withCredentials: true });
      if (data.login_url) {
        window.open(data.login_url, "_blank", "noopener,noreferrer");
        toast.success("Stripe dashboard opened");
      }
    } catch (e) {
      toast.error(`Dashboard link failed: ${e?.response?.data?.detail || e.message}`);
    } finally { clearBusy(merchant.merchant_id); }
  };

  return (
    <div style={{
                    ...styles.page,
                    // When embedded inside AdminMerchants tab-1, we drop the
                    // page-level sidebar offset + top spacing so the table sits
                    // flush under the tab bar.
                    ...(embedded ? { padding: 0, background: "transparent",
                                                    minHeight: 0 } : {}),
                  }} data-testid="admin-stripe-connect-page">
      {embedded ? (
        <div style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", gap: 8, marginBottom: 12 }}>
          <div style={{ color: "#94a3b8", fontSize: 13 }}
                    data-testid="admin-sc-embedded-count">
            {loading ? "Loading…" : `${total} merchants${statusFilter ? ` · filter: ${statusFilter}` : ""}`}
          </div>
          <div style={styles.toolbar}>
            <select value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        data-testid="admin-sc-status-filter"
                        style={styles.select}>
              <option value="">All statuses</option>
              <option value="not_started">Not Started</option>
              <option value="onboarding_in_progress">In Progress</option>
              <option value="onboarding_incomplete">Incomplete</option>
              <option value="verification_pending">Verification Pending</option>
              <option value="active">Active</option>
              <option value="payouts_disabled">Payouts Disabled</option>
              <option value="restricted">Restricted</option>
              <option value="rejected">Rejected</option>
            </select>
            <button type="button" onClick={load} disabled={loading}
                        data-testid="admin-sc-reload-btn"
                        style={styles.buttonPrimary}>
              {loading ? "Loading…" : "Reload"}
            </button>
          </div>
        </div>
      ) : (
      <div style={styles.header}>
        <div>
          <div style={styles.eyebrow}>Phase SC.1</div>
          <h1 style={styles.h1}>Stripe Connect · Merchants</h1>
          <div style={styles.subtitle}>
            {loading ? "Loading…" : `${total} merchants${statusFilter ? ` · filter: ${statusFilter}` : ""}`}
          </div>
        </div>
        <div style={styles.toolbar}>
          <select value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      data-testid="admin-sc-status-filter"
                      style={styles.select}>
            <option value="">All statuses</option>
            <option value="not_started">Not Started</option>
            <option value="onboarding_in_progress">In Progress</option>
            <option value="onboarding_incomplete">Incomplete</option>
            <option value="verification_pending">Verification Pending</option>
            <option value="active">Active</option>
            <option value="payouts_disabled">Payouts Disabled</option>
            <option value="restricted">Restricted</option>
            <option value="rejected">Rejected</option>
          </select>
          <button type="button" onClick={load}
                      disabled={loading}
                      data-testid="admin-sc-reload-btn"
                      style={styles.buttonPrimary}>
            {loading ? "Loading…" : "Reload"}
          </button>
        </div>
      </div>
      )}

      <div style={styles.tableWrap}>
        <table style={styles.table} data-testid="admin-sc-table">
          <thead>
            <tr>
              <th style={styles.th}>Merchant</th>
              <th style={styles.th}>Stripe Account ID</th>
              <th style={styles.th}>Status</th>
              <th style={styles.th}>Charges</th>
              <th style={styles.th}>Payouts</th>
              <th style={styles.th}>Reqs Due</th>
              <th style={styles.th}>Synced</th>
              <th style={styles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => {
              const tone = STATUS_TONE[m.stripe_onboarding_status] || STATUS_TONE.not_started;
              const busy = rowBusy[m.merchant_id];
              const reqDue = (m.requirements_currently_due?.length || 0)
                              + (m.requirements_past_due?.length || 0);
              return (
                <tr key={m.merchant_id}
                      data-testid={`admin-sc-row-${m.merchant_id}`}
                      style={styles.tr}>
                  <td style={styles.td}>
                    <div style={styles.merchantName}>{m.name || "—"}</div>
                    <div style={styles.merchantMeta}>{m.slug || m.merchant_id}</div>
                  </td>
                  <td style={styles.td}>
                    <code style={styles.code} data-testid={`admin-sc-acctid-${m.merchant_id}`}>
                      {m.stripe_account_id || "—"}
                    </code>
                  </td>
                  <td style={styles.td}>
                    <span style={{ ...styles.pill, background: tone.bg, color: tone.fg }}
                              data-testid={`admin-sc-status-${m.merchant_id}`}>
                      {tone.label}
                    </span>
                  </td>
                  <td style={styles.td}>
                    <BoolCheck value={m.charges_enabled}
                                        testId={`admin-sc-charges-${m.merchant_id}`} />
                  </td>
                  <td style={styles.td}>
                    <BoolCheck value={m.payouts_enabled}
                                        testId={`admin-sc-payouts-${m.merchant_id}`} />
                  </td>
                  <td style={styles.td}>
                    {reqDue > 0 ? (
                      <span style={{ ...styles.pill, background: "#f59e0b22", color: "#f59e0b" }}>
                        {reqDue}
                      </span>
                    ) : <span style={styles.subtle}>0</span>}
                  </td>
                  <td style={styles.td}>
                    <span style={styles.subtle}>{fmtDate(m.status_synced_at)}</span>
                  </td>
                  <td style={{ ...styles.td, whiteSpace: "nowrap" }}>
                    <button type="button" onClick={() => handleRefresh(m)}
                                disabled={!!busy || !m.stripe_account_id}
                                data-testid={`admin-sc-refresh-btn-${m.merchant_id}`}
                                style={styles.buttonGhost}>
                      {busy === "refresh" ? "…" : "Refresh"}
                    </button>
                    {m.stripe_onboarding_status !== "active" && (
                      <button type="button" onClick={() => handleOnboard(m)}
                                  disabled={!!busy}
                                  data-testid={`admin-sc-onboard-btn-${m.merchant_id}`}
                                  style={styles.buttonPrimary}>
                        {busy === "onboard" ? "…" : "Onboarding Link"}
                      </button>
                    )}
                    {(() => {
                      // Phase SC.1 WARN fix — Stripe Dashboard button now
                      // renders UNCONDITIONALLY on every row so admins can
                      // discover the affordance.  Disabled with a helpful
                      // tooltip until the merchant reaches an activated
                      // state (Stripe rejects login-link creation for
                      // incomplete accounts).
                      const dashOk = m.stripe_onboarding_status === "active"
                                              || m.stripe_onboarding_status === "payouts_disabled";
                      const disabled = !!busy || !dashOk;
                      const tip = dashOk
                        ? "Open Stripe Express dashboard"
                        : "Available after merchant activation";
                      return (
                        <button type="button"
                                    onClick={() => handleDashboard(m)}
                                    disabled={disabled}
                                    title={tip}
                                    aria-label={tip}
                                    data-testid={`admin-sc-dashboard-btn-${m.merchant_id}`}
                                    data-enabled={dashOk ? "true" : "false"}
                                    style={{
                                      ...styles.buttonSecondary,
                                      opacity: dashOk ? 1 : 0.45,
                                      cursor: dashOk ? "pointer" : "not-allowed",
                                    }}>
                          {busy === "dashboard" ? "…" : "Stripe Dashboard"}
                        </button>
                      );
                    })()}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!loading && items.length === 0 && (
          <div style={{ padding: 28, color: "#94a3b8", textAlign: "center" }}
                    data-testid="admin-sc-empty">
            No merchants match the current filter.
          </div>
        )}
      </div>
    </div>
  );
}

function BoolCheck({ value, testId }) {
  return (
    <span data-testid={testId} style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 22, height: 22, borderRadius: 6,
      background: value ? "#10b98122" : "#64748b22",
      color: value ? "#10b981" : "#64748b",
      fontWeight: 700, fontSize: 12,
    }}>
      {value ? "✓" : "×"}
    </span>
  );
}

function fmtDate(v) {
  if (!v) return "never";
  try {
    const d = new Date(v);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
    return d.toLocaleDateString();
  } catch { return String(v); }
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#0d0d18",
    color: "#e2e8f0",
    padding: "24px 28px 60px",
    fontFamily: "ui-sans-serif, system-ui, sans-serif",
  },
  header: {
    display: "flex", justifyContent: "space-between",
    alignItems: "flex-start", gap: 16, marginBottom: 24, flexWrap: "wrap",
  },
  eyebrow: {
    fontSize: 11, letterSpacing: 2, textTransform: "uppercase",
    color: "#00d4ff", fontWeight: 700,
  },
  h1: {
    fontSize: 24, fontWeight: 800, margin: "4px 0 6px",
    letterSpacing: "-0.02em",
  },
  subtitle: { color: "#94a3b8", fontSize: 13 },
  toolbar: { display: "flex", gap: 8, alignItems: "center" },
  select: {
    background: "#1e293b", color: "#e2e8f0",
    border: "1px solid #334155", borderRadius: 8,
    padding: "8px 10px", fontSize: 13,
  },
  buttonPrimary: {
    background: "linear-gradient(135deg, #00d4ff, #6366f1)",
    color: "#0d0d18", border: 0, borderRadius: 8,
    padding: "8px 14px", fontSize: 12, fontWeight: 700,
    cursor: "pointer", textTransform: "uppercase", letterSpacing: 0.5,
    marginRight: 6,
  },
  buttonSecondary: {
    background: "#334155", color: "#e2e8f0", border: 0, borderRadius: 8,
    padding: "8px 14px", fontSize: 12, fontWeight: 600,
    cursor: "pointer", textTransform: "uppercase", letterSpacing: 0.5,
    marginRight: 6,
  },
  buttonGhost: {
    background: "transparent", color: "#94a3b8",
    border: "1px solid #334155", borderRadius: 8,
    padding: "7px 13px", fontSize: 12, fontWeight: 600,
    cursor: "pointer", textTransform: "uppercase", letterSpacing: 0.5,
    marginRight: 6,
  },
  tableWrap: {
    background: "#1e1e2e", borderRadius: 12,
    border: "1px solid #2a2a3a", overflowX: "auto",
  },
  table: {
    width: "100%", borderCollapse: "separate", borderSpacing: 0,
    fontSize: 13,
  },
  th: {
    textAlign: "left", padding: "12px 14px", background: "#151521",
    color: "#94a3b8", fontSize: 11, textTransform: "uppercase",
    letterSpacing: 1, fontWeight: 700, borderBottom: "1px solid #2a2a3a",
  },
  tr: { borderBottom: "1px solid #2a2a3a" },
  td: {
    padding: "12px 14px", borderBottom: "1px solid #2a2a3a",
    verticalAlign: "top",
  },
  merchantName: { fontWeight: 700, color: "#e2e8f0" },
  merchantMeta: {
    fontSize: 11, color: "#64748b", marginTop: 2,
    textTransform: "uppercase", letterSpacing: 0.8,
  },
  pill: {
    display: "inline-block", padding: "3px 10px", borderRadius: 999,
    fontSize: 11, fontWeight: 700, letterSpacing: 0.5,
    textTransform: "uppercase",
  },
  code: {
    background: "#0d0d18", padding: "3px 8px", borderRadius: 6,
    fontFamily: "ui-monospace, monospace", fontSize: 12,
    color: "#94a3b8",
  },
  subtle: { color: "#64748b", fontSize: 12 },
};
