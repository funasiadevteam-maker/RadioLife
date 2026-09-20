// Phase SC.2 — Admin: Merchants (replaces the SC.1 "Stripe Connect" page).
// Two tabs:
//   1. All Merchants   — the SC.1 table with the WARN fix
//   2. Pending Approval — SC.2 submitted queue with View Details drawer +
//                                        Approve / Reject modals + Mailgun send status.
//
// Both variants ride the legacy admin shell (admin routes are outside the
// FUUSICOverlay's screen map by design).
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import AdminStripeConnect from "@/AdminStripeConnect";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_TONE = {
  active:                  { bg: "#10b98122", fg: "#10b981", label: "Active"                        },
  approved:              { bg: "#10b98122", fg: "#10b981", label: "Approved"                    },
  submitted:            { bg: "#3b82f622", fg: "#3b82f6", label: "Submitted"                  },
  draft:                    { bg: "#64748b22", fg: "#94a3b8", label: "Draft"                        },
  rejected:              { bg: "#ef444422", fg: "#ef4444", label: "Rejected"                    },
  suspended:            { bg: "#f59e0b22", fg: "#f59e0b", label: "Suspended"                  },
  restricted:            { bg: "#ef444422", fg: "#ef4444", label: "Restricted"                  },
  payouts_disabled: { bg: "#f59e0b22", fg: "#f59e0b", label: "Payouts Disabled"    },
  verification_pending: { bg: "#eab30822", fg: "#eab308", label: "Verification Pending" },
  stripe_onboarding_pending: { bg: "#3b82f622", fg: "#3b82f6", label: "Stripe Pending" },
};


export default function AdminMerchants() {
  const [tab, setTab] = useState("all");    // "all" | "pending"

  return (
    <div style={styles.page} data-testid="admin-merchants-page">
      <div style={styles.header}>
        <div>
          <div style={styles.eyebrow}>Phase SC.2</div>
          <h1 style={styles.h1}>Merchants</h1>
          <div style={styles.subtitle}>
            Manage merchant applications, activation, and Stripe Connect status.
          </div>
        </div>
      </div>

      <div style={styles.tabs} data-testid="admin-merchants-tabs">
        <TabBtn active={tab === "all"} onClick={() => setTab("all")}
                    testId="admin-merchants-tab-all">All Merchants</TabBtn>
        <TabBtn active={tab === "pending"} onClick={() => setTab("pending")}
                    testId="admin-merchants-tab-pending">Pending Approval</TabBtn>
      </div>

      <div style={{ marginTop: 20 }}>
        {tab === "all" ? <AllMerchantsPane />
                                : <PendingApprovalPane />}
      </div>
    </div>
  );
}


function TabBtn({ active, onClick, testId, children }) {
  return (
    <button type="button" onClick={onClick} data-testid={testId}
                data-active={active ? "true" : "false"}
                style={{
                  background: active ? "linear-gradient(135deg,#00d4ff,#6366f1)" : "transparent",
                  color: active ? "#0d0d18" : "#94a3b8",
                  border: active ? 0 : "1px solid #334155",
                  borderRadius: 8, padding: "9px 18px", fontSize: 13,
                  fontWeight: 700, letterSpacing: 0.5,
                  textTransform: "uppercase", cursor: "pointer",
                  marginRight: 6,
                }}>{children}</button>
  );
}


// ─── Tab 1 · All Merchants (SC.1 table + WARN fix) ───────────────
function AllMerchantsPane() {
  return (
    <div data-testid="admin-merchants-all-pane">
      <AdminStripeConnect embedded />
    </div>
  );
}


// ─── Tab 2 · Pending Approval ────────────────────────────────────
function PendingApprovalPane() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);   // merchant_id
  const [details, setDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [modal, setModal] = useState(null);           // "approve" | "reject" | "suspend" | null

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/admin/merchants?status=pending&limit=100`,
        { withCredentials: true });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const openDetails = async (mid) => {
    setSelected(mid); setDetails(null); setDetailsLoading(true);
    try {
      const { data } = await axios.get(`${API}/admin/merchants/${mid}`,
                                                                { withCredentials: true });
      setDetails(data);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
      setSelected(null);
    } finally { setDetailsLoading(false); }
  };

  const onApprove = async () => {
    if (!selected) return;
    try {
      const { data } = await axios.post(
        `${API}/admin/merchants/${selected}/approve`, {},
        { withCredentials: true });
      toast.success(`Approved · email ${data.email?.ok ? "sent" : "failed"}`);
      setModal(null); setSelected(null); setDetails(null);
      await load();
    } catch (e) {
      toast.error(`Approve failed: ${e?.response?.data?.detail || e.message}`);
    }
  };

  const onReject = async (reason) => {
    if (!selected) return;
    try {
      const { data } = await axios.post(
        `${API}/admin/merchants/${selected}/reject`,
        { reason },
        { withCredentials: true });
      toast.success(`Rejected · email ${data.email?.ok ? "sent" : "failed"}`);
      setModal(null); setSelected(null); setDetails(null);
      await load();
    } catch (e) {
      const det = e?.response?.data?.detail;
      const msg = Array.isArray(det) ? det.map((d) => d.msg).join(", ") : det || e.message;
      toast.error(`Reject failed: ${msg}`);
    }
  };

  return (
    <div data-testid="admin-merchants-pending-pane">
      <div style={styles.toolbar}>
        <div style={{ color: "#94a3b8", fontSize: 13 }}>
          {loading ? "Loading…" : `${total} pending application${total === 1 ? "" : "s"}`}
        </div>
        <button type="button" onClick={load} disabled={loading}
                      style={styles.buttonPrimary}
                      data-testid="admin-merchants-pending-reload">
          {loading ? "Loading…" : "Reload"}
        </button>
      </div>

      <div style={styles.tableWrap}>
        <table style={styles.table} data-testid="admin-merchants-pending-table">
          <thead>
            <tr>
              <th style={styles.th}>Merchant</th>
              <th style={styles.th}>Owner</th>
              <th style={styles.th}>Category</th>
              <th style={styles.th}>Stripe</th>
              <th style={styles.th}>Submitted</th>
              <th style={styles.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((m) => {
              const tone = STATUS_TONE[m.effective_status]
                                || STATUS_TONE.submitted;
              const strTone = STATUS_TONE[m.stripe_onboarding_status]
                                || STATUS_TONE.draft;
              return (
                <tr key={m.merchant_id}
                          data-testid={`admin-merchants-pending-row-${m.merchant_id}`}
                          style={styles.tr}>
                  <td style={styles.td}>
                    <div style={styles.merchantName}>{m.name}</div>
                    <div style={styles.merchantMeta}>{m.merchant_id}</div>
                    <div style={{ marginTop: 6 }}>
                      <span style={{ ...styles.pill, background: tone.bg,
                                              color: tone.fg }}
                                data-testid={`admin-merchants-status-${m.merchant_id}`}>
                        {tone.label}
                      </span>
                    </div>
                  </td>
                  <td style={styles.td}>
                    <div style={{ fontSize: 12 }}>{m.owner_email || "—"}</div>
                    <div style={styles.merchantMeta}>{m.owner_user_id || ""}</div>
                  </td>
                  <td style={styles.td}>{m.category_id || "—"}</td>
                  <td style={styles.td}>
                    <span style={{ ...styles.pill,
                                            background: strTone.bg,
                                            color: strTone.fg }}>
                      {strTone.label}
                    </span>
                  </td>
                  <td style={styles.td}>
                    <span style={{ color: "#94a3b8", fontSize: 12 }}>
                      {fmtDate(m.submitted_at)}
                    </span>
                  </td>
                  <td style={{ ...styles.td, whiteSpace: "nowrap" }}>
                    <button type="button"
                                onClick={() => openDetails(m.merchant_id)}
                                data-testid={`admin-merchants-view-${m.merchant_id}`}
                                style={styles.buttonPrimary}>
                      View Details
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!loading && items.length === 0 && (
          <div style={{ padding: 32, color: "#94a3b8", textAlign: "center" }}
                    data-testid="admin-merchants-pending-empty">
            No pending applications.  New submissions arrive here.
          </div>
        )}
      </div>

      {selected && (
        <DetailsDrawer light={false}
                                loading={detailsLoading}
                                details={details}
                                onClose={() => { setSelected(null); setDetails(null); }}
                                onApprove={() => setModal("approve")}
                                onReject={() => setModal("reject")} />
      )}

      {modal === "approve" && (
        <ConfirmModal
          title="Approve this merchant?"
          body={<div>
            <p>Approving will elevate <b>{details?.owner_email || "the owner"}</b> to the <code>business</code> role and email them a welcome link.</p>
          </div>}
          confirmLabel="Approve"
          confirmTone="emerald"
          onConfirm={onApprove}
          onCancel={() => setModal(null)}
          testId="admin-merchants-approve-modal" />
      )}
      {modal === "reject" && (
        <RejectModal onCancel={() => setModal(null)}
                              onConfirm={onReject}/>
      )}
    </div>
  );
}


function DetailsDrawer({ loading, details, onClose, onApprove, onReject }) {
  return (
    <>
      <div onClick={onClose}
                style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)",
                              zIndex: 90 }} />
      <div data-testid="admin-merchants-drawer"
                style={{
                  position: "fixed", top: 0, right: 0, bottom: 0,
                  width: "min(560px, 100vw)", background: "#0d0d18",
                  borderLeft: "1px solid #2a2a3a", zIndex: 100,
                  overflowY: "auto", padding: "24px 26px",
                }}>
        {loading || !details ? (
          <div style={{ color: "#94a3b8" }}>Loading…</div>
        ) : (
          <>
            <div style={{ display: "flex", justifyContent: "space-between",
                                      alignItems: "flex-start", gap: 10, marginBottom: 20 }}>
              <div>
                <div style={styles.eyebrow}>Merchant details</div>
                <h2 style={{ fontSize: 22, fontWeight: 800, margin: "4px 0 6px",
                                          color: "#fff" }}>{details.name}</h2>
                <code style={{ ...styles.code, fontSize: 11 }}>{details.merchant_id}</code>
              </div>
              <button type="button" onClick={onClose}
                              data-testid="admin-merchants-drawer-close"
                              style={{ background: "transparent",
                                              color: "#94a3b8", border: 0, fontSize: 24,
                                              cursor: "pointer", padding: 0 }}>
                ×
              </button>
            </div>

            {details.logo_url && (
              <img src={(process.env.REACT_APP_BACKEND_URL || "") + details.logo_url}
                        alt="logo"
                        style={{ width: 96, height: 96, borderRadius: 16,
                                        objectFit: "cover", marginBottom: 20,
                                        border: "1px solid #2a2a3a" }}
                        data-testid="admin-merchants-drawer-logo" />
            )}

            <DrawerRow label="Owner"
                                value={<>
                                  <div>{details.owner_email}</div>
                                  <div style={styles.merchantMeta}>{details.owner_user_id}</div>
                                </>} />
            <DrawerRow label="Category" value={details.category_id} />
            {details.phone && <DrawerRow label="Phone" value={details.phone}/>}
            {details.website && <DrawerRow label="Website"
              value={<a href={details.website} target="_blank" rel="noreferrer"
                                  style={{ color: "#00d4ff" }}>{details.website}</a>}/>}
            <DrawerRow label="Description"
                                value={<div style={{ whiteSpace: "pre-wrap", fontSize: 13,
                                                                    lineHeight: 1.5 }}>{details.description}</div>} />

            {(details.locations || []).length > 0 && (
              <div style={{ marginTop: 18 }}>
                <div style={styles.drawerLabel}>Locations</div>
                {details.locations.map((l) => (
                  <div key={l.location_id}
                            data-testid={`admin-merchants-drawer-loc-${l.location_id}`}
                            style={{
                              background: "#1e293b", borderRadius: 10,
                              padding: "10px 12px", marginBottom: 8,
                              border: "1px solid #2a2a3a", fontSize: 12,
                            }}>
                    <div style={{ color: "#fff", fontWeight: 600 }}>
                      {l.name || l.address}
                      {l.primary && <span style={{ ...styles.pill,
                                    background: "#00d4ff22", color: "#00d4ff",
                                    marginLeft: 6, fontSize: 10 }}>Primary</span>}
                    </div>
                    <div style={{ color: "#94a3b8", marginTop: 2 }}>
                      {l.address}{l.city && ` · ${l.city}`}
                      {l.latitude && l.longitude && (
                        <> · {l.latitude.toFixed(3)}, {l.longitude.toFixed(3)}</>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {(details.photos || []).length > 0 && (
              <div style={{ marginTop: 18 }}>
                <div style={styles.drawerLabel}>Photos</div>
                <div style={{ display: "grid",
                                          gridTemplateColumns: "repeat(3,1fr)",
                                          gap: 6 }}
                          data-testid="admin-merchants-drawer-photos">
                  {details.photos.map((p, i) => (
                    <img key={i} alt=""
                              src={(process.env.REACT_APP_BACKEND_URL || "") + (p.url || "")}
                              style={{ width: "100%", aspectRatio: "1 / 1",
                                              objectFit: "cover", borderRadius: 8 }}/>
                  ))}
                </div>
              </div>
            )}

            <div style={{ marginTop: 18 }}>
              <div style={styles.drawerLabel}>Stripe Connect</div>
              <div style={{
                background: "#1e293b", borderRadius: 10, padding: "10px 12px",
                border: "1px solid #2a2a3a", fontSize: 12, color: "#e2e8f0",
              }}>
                <div><b>Status:</b> {details.stripe_onboarding_status}</div>
                <div style={{ marginTop: 4 }}>
                  <b>Account:</b> <code style={styles.code}>{details.stripe_account_id || "—"}</code>
                </div>
                <div style={{ marginTop: 4 }}>
                  Charges: {details.stripe_charges_enabled ? "✓" : "×"} ·
                  Payouts: {details.stripe_payouts_enabled ? " ✓" : " ×"} ·
                  Details: {details.stripe_details_submitted ? " ✓" : " ×"}
                </div>
                {(details.stripe_requirements_currently_due || []).length > 0 && (
                  <div style={{ marginTop: 4, color: "#f59e0b" }}>
                    Reqs due: {details.stripe_requirements_currently_due.join(", ")}
                  </div>
                )}
              </div>
            </div>

            <div style={{ marginTop: 22, display: "flex", gap: 8,
                                      flexWrap: "wrap" }}>
              <button type="button" onClick={onApprove}
                              data-testid="admin-merchants-drawer-approve"
                              style={{ ...styles.buttonPrimary,
                                              background: "linear-gradient(135deg,#10b981,#059669)",
                                              padding: "10px 18px" }}>
                Approve
              </button>
              <button type="button" onClick={onReject}
                              data-testid="admin-merchants-drawer-reject"
                              style={{ ...styles.buttonPrimary,
                                              background: "#ef4444", color: "#fff",
                                              padding: "10px 18px" }}>
                Reject
              </button>
              <button type="button" onClick={onClose}
                              style={styles.buttonGhost}>
                Close
              </button>
            </div>
          </>
        )}
      </div>
    </>
  );
}


function DrawerRow({ label, value }) {
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={styles.drawerLabel}>{label}</div>
      <div style={{ color: "#e2e8f0", fontSize: 13 }}>{value}</div>
    </div>
  );
}


function ConfirmModal({ title, body, confirmLabel, confirmTone = "cyan",
                                          onConfirm, onCancel, testId }) {
  const bg = confirmTone === "emerald"
    ? "linear-gradient(135deg,#10b981,#059669)"
    : confirmTone === "rose"
      ? "#ef4444"
      : "linear-gradient(135deg,#00d4ff,#6366f1)";
  return (
    <div style={styles.modalBackdrop} onClick={onCancel}>
      <div onClick={(e) => e.stopPropagation()}
                data-testid={testId}
                style={styles.modal}>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800,
                                color: "#fff", marginBottom: 10 }}>{title}</h3>
        <div style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5,
                                  marginBottom: 18 }}>{body}</div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
          <button type="button" onClick={onCancel}
                        style={styles.buttonGhost}>Cancel</button>
          <button type="button" onClick={onConfirm}
                        data-testid={`${testId}-confirm`}
                        style={{ ...styles.buttonPrimary, background: bg,
                                          color: confirmTone === "rose" ? "#fff" : "#0d0d18" }}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}


function RejectModal({ onCancel, onConfirm }) {
  const [reason, setReason] = useState("");
  const valid = reason.trim().length >= 20;
  return (
    <div style={styles.modalBackdrop} onClick={onCancel}>
      <div onClick={(e) => e.stopPropagation()}
                data-testid="admin-merchants-reject-modal"
                style={styles.modal}>
        <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800,
                                color: "#fff", marginBottom: 10 }}>
          Reject application
        </h3>
        <p style={{ color: "#cbd5e1", fontSize: 13, lineHeight: 1.5,
                              marginBottom: 12 }}>
          The reason is included in the email sent to the owner.  Minimum 20
          characters — be specific.
        </p>
        <textarea value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          rows={5}
                          data-testid="admin-merchants-reject-reason"
                          placeholder="Explain why the application is being rejected…"
                          style={{
                            width: "100%", background: "#0d0d18",
                            border: "1px solid #334155", borderRadius: 8,
                            padding: "10px 12px", color: "#e2e8f0",
                            fontSize: 13, resize: "none", outline: "none",
                          }}/>
        <div style={{ fontSize: 11, color: valid ? "#10b981" : "#94a3b8",
                                  marginTop: 6, textAlign: "right" }}>
          {reason.length} / 20 chars minimum
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8,
                                    marginTop: 14 }}>
          <button type="button" onClick={onCancel}
                        style={styles.buttonGhost}>Cancel</button>
          <button type="button" disabled={!valid}
                        onClick={() => onConfirm(reason.trim())}
                        data-testid="admin-merchants-reject-modal-confirm"
                        style={{ ...styles.buttonPrimary, background: "#ef4444",
                                          color: "#fff",
                                          opacity: valid ? 1 : 0.5,
                                          cursor: valid ? "pointer" : "not-allowed" }}>
            Reject & notify
          </button>
        </div>
      </div>
    </div>
  );
}


function fmtDate(v) {
  if (!v) return "—";
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
  header: { marginBottom: 20 },
  eyebrow: {
    fontSize: 11, letterSpacing: 2, textTransform: "uppercase",
    color: "#00d4ff", fontWeight: 700,
  },
  h1: {
    fontSize: 26, fontWeight: 800, margin: "4px 0 6px",
    letterSpacing: "-0.02em",
  },
  subtitle: { color: "#94a3b8", fontSize: 13 },
  tabs: { display: "flex", borderBottom: "1px solid #2a2a3a",
                    paddingBottom: 10, marginTop: 10 },
  toolbar: { display: "flex", justifyContent: "space-between",
                        alignItems: "center", gap: 8, marginBottom: 12 },
  tableWrap: {
    background: "#1e1e2e", borderRadius: 12,
    border: "1px solid #2a2a3a", overflowX: "auto",
  },
  table: { width: "100%", borderCollapse: "separate", borderSpacing: 0,
                    fontSize: 13 },
  th: {
    textAlign: "left", padding: "12px 14px", background: "#151521",
    color: "#94a3b8", fontSize: 11, textTransform: "uppercase",
    letterSpacing: 1, fontWeight: 700, borderBottom: "1px solid #2a2a3a",
  },
  tr: { borderBottom: "1px solid #2a2a3a" },
  td: { padding: "12px 14px", borderBottom: "1px solid #2a2a3a",
              verticalAlign: "top" },
  merchantName: { fontWeight: 700, color: "#e2e8f0" },
  merchantMeta: { fontSize: 11, color: "#64748b", marginTop: 2 },
  buttonPrimary: {
    background: "linear-gradient(135deg, #00d4ff, #6366f1)",
    color: "#0d0d18", border: 0, borderRadius: 8,
    padding: "8px 14px", fontSize: 12, fontWeight: 700,
    cursor: "pointer", textTransform: "uppercase", letterSpacing: 0.5,
  },
  buttonGhost: {
    background: "transparent", color: "#94a3b8",
    border: "1px solid #334155", borderRadius: 8,
    padding: "7px 13px", fontSize: 12, fontWeight: 600,
    cursor: "pointer", textTransform: "uppercase", letterSpacing: 0.5,
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
  modalBackdrop: {
    position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
    zIndex: 200, display: "flex", alignItems: "center",
    justifyContent: "center", padding: 20,
  },
  modal: {
    background: "#1e1e2e", border: "1px solid #2a2a3a",
    borderRadius: 12, padding: 24, width: "min(520px, 100%)",
  },
  drawerLabel: {
    fontSize: 10, color: "#64748b", textTransform: "uppercase",
    letterSpacing: 1.5, fontWeight: 700, marginBottom: 4,
  },
};
