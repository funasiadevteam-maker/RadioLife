// Phase SC.6 — Admin Refunds Console.
//
// Admin can:
//   - Look up a transaction by transaction_id and issue a refund
//   - See a paginated list of all refunds (across merchants)
//   - Filter by merchant_id + status
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, AlertTriangle, Undo2, X } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_TINTS = {
  requested:    { bg: "rgba(59,130,246,0.15)", fg: "#3b82f6" },
  processing:  { bg: "rgba(234,179,8,0.15)",    fg: "#eab308" },
  succeeded:    { bg: "rgba(16,185,129,0.15)", fg: "#10b981" },
  failed:            { bg: "rgba(244,63,94,0.15)",    fg: "#f43f5e" },
};

const REASON_OPTIONS = [
  { value: "requested_by_customer", label: "Requested by customer" },
  { value: "duplicate",                            label: "Duplicate charge" },
  { value: "fraudulent",                          label: "Fraudulent" },
  { value: "expired_uncaptured_charge", label: "Expired uncaptured" },
];


export default function AdminRefunds() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [merchantFilter, setMerchantFilter] = useState("");
  const [showIssueModal, setShowIssueModal] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (merchantFilter) params.merchant_id = merchantFilter;
      const { data } = await axios.get(`${API}/admin/refunds`,
                                                                      { params, withCredentials: true });
      setRows(data.rows || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter, merchantFilter]);

  return (
    <div style={{ marginLeft: 220, padding: 24,
                              minHeight: "100vh", background: "#0d0d18", color: "#e2e8f0" }}
              data-testid="admin-refunds-page">
      <div style={{ display: "flex", alignItems: "center",
                                gap: 12, marginBottom: 20 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: -0.5,
                                  margin: 0, flex: 1 }}>Refunds</h1>
        <button onClick={() => setShowIssueModal(true)}
                        data-testid="admin-refunds-issue-btn"
                        style={{ background: "linear-gradient(135deg,#F72585,#B5179E)",
                                          color: "#fff", border: 0, borderRadius: 999,
                                          padding: "10px 20px", fontWeight: 700,
                                          fontSize: 13, cursor: "pointer" }}>
          + Issue Refund
        </button>
        <button onClick={load}
                        style={{ background: "transparent", border: "1px solid #2a2a3a",
                                          color: "#94a3b8", borderRadius: 8, padding: "8px 12px",
                                          fontSize: 12, cursor: "pointer" }}>
          <RefreshCw size={13} style={{ display: "inline", marginRight: 4 }}/> Refresh
        </button>
      </div>

      {/* Filters */}
      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <input placeholder="Filter by merchant_id"
                    value={merchantFilter}
                    onChange={(e) => setMerchantFilter(e.target.value)}
                    data-testid="admin-refunds-merchant-filter"
                    style={{ background: "#161628", border: "1px solid #2a2a3a",
                                      color: "#e2e8f0", borderRadius: 6, padding: "8px 10px",
                                      fontSize: 12, width: 240 }}/>
        <select value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        data-testid="admin-refunds-status-filter"
                        style={{ background: "#161628", border: "1px solid #2a2a3a",
                                          color: "#e2e8f0", borderRadius: 6, padding: "8px 10px",
                                          fontSize: 12 }}>
          <option value="">All statuses</option>
          <option value="requested">Requested</option>
          <option value="processing">Processing</option>
          <option value="succeeded">Succeeded</option>
          <option value="failed">Failed</option>
        </select>
        <div style={{ marginLeft: "auto", color: "#64748b", fontSize: 12,
                                  alignSelf: "center" }}>
          {loading ? "Loading…" : `${total} refund${total === 1 ? "" : "s"}`}
        </div>
      </div>

      {/* Table */}
      <div style={{ background: "#161628", border: "1px solid #2a2a3a",
                                borderRadius: 12, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#0d0d18", color: "#64748b",
                                      textTransform: "uppercase", fontSize: 10,
                                      letterSpacing: 1 }}>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Refund ID</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Merchant</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Transaction</th>
              <th style={{ padding: "12px 14px", textAlign: "right" }}>Amount</th>
              <th style={{ padding: "12px 14px", textAlign: "center" }}>App Fee?</th>
              <th style={{ padding: "12px 14px", textAlign: "center" }}>Status</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Requested</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Reason</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Date</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={9} style={{ padding: 24, textAlign: "center",
                                                                            color: "#64748b" }}>
                No refunds yet.
              </td></tr>
            ) : rows.map((r) => {
              const tint = STATUS_TINTS[r.status] || {};
              return (
                <tr key={r.refund_id}
                      data-testid={`admin-refund-row-${r.refund_id}`}
                      style={{ borderTop: "1px solid #2a2a3a" }}>
                  <td style={{ padding: "10px 14px", fontFamily: "monospace",
                                              fontSize: 11, color: "#94a3b8" }}>{r.refund_id}</td>
                  <td style={{ padding: "10px 14px" }}>
                    <div style={{ fontWeight: 600 }}>{r.merchant_name || "—"}</div>
                    <div style={{ fontSize: 10, color: "#64748b",
                                              fontFamily: "monospace" }}>{r.merchant_id}</div>
                  </td>
                  <td style={{ padding: "10px 14px", fontFamily: "monospace",
                                              fontSize: 11, color: "#94a3b8" }}>{r.transaction_id}</td>
                  <td style={{ padding: "10px 14px", textAlign: "right",
                                              fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                    {(r.amount_cents / 100).toFixed(2)} <span style={{
                      fontSize: 10, color: "#64748b" }}>{r.currency}</span>
                  </td>
                  <td style={{ padding: "10px 14px", textAlign: "center" }}>
                    {r.refund_application_fee ? "✓" : "—"}
                  </td>
                  <td style={{ padding: "10px 14px", textAlign: "center" }}>
                    <span style={{ background: tint.bg, color: tint.fg,
                                              padding: "3px 10px", borderRadius: 999,
                                              fontSize: 10, fontWeight: 700,
                                              textTransform: "uppercase" }}>
                      {r.status}
                    </span>
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#64748b" }}>
                    {r.requested_by_role}
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#94a3b8" }}>
                    {(r.reason || "").replace(/_/g, " ")}
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#64748b" }}>
                    {r.created_at ? new Date(r.created_at).toLocaleString(undefined,
                      { month: "short", day: "numeric", hour: "2-digit",
                        minute: "2-digit" }) : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {showIssueModal && (
        <IssueRefundModal onClose={() => setShowIssueModal(false)}
                                                onSuccess={() => { setShowIssueModal(false); load(); }}/>
      )}
    </div>
  );
}


function IssueRefundModal({ onClose, onSuccess }) {
  const [transactionId, setTransactionId] = useState("");
  const [amountUsd, setAmountUsd] = useState("");
  const [reason, setReason] = useState("requested_by_customer");
  const [refundAppFee, setRefundAppFee] = useState(true);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);

  const submit = async () => {
    if (!transactionId.trim()) { setErr("Transaction ID is required"); return; }
    setBusy(true); setErr(null);
    try {
      const body = { transaction_id: transactionId.trim(), reason,
                                  refund_application_fee: refundAppFee };
      if (amountUsd && parseFloat(amountUsd) > 0)
        body.amount_cents = Math.round(parseFloat(amountUsd) * 100);
      if (note.trim()) body.note = note.trim();
      const { data } = await axios.post(`${API}/admin/refunds`, body,
                                                                        { withCredentials: true });
      toast.success(`Refund ${data.refund_id} · ${data.status}`);
      onSuccess();
    } catch (e) {
      const det = e?.response?.data?.detail;
      const msg = det?.detail || det?.code || det || e.message;
      setErr(`${msg}`);
    } finally { setBusy(false); }
  };

  return (
    <div onClick={onClose} data-testid="admin-refunds-modal-backdrop"
              style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
                              zIndex: 100, display: "flex", alignItems: "center",
                              justifyContent: "center", padding: 20 }}>
      <div onClick={(e) => e.stopPropagation()}
                data-testid="admin-refunds-modal"
                style={{ background: "#161628", border: "1px solid #2a2a3a",
                                  borderRadius: 12, padding: 24, width: 480, maxWidth: "100%",
                                  color: "#e2e8f0" }}>
        <div style={{ display: "flex", alignItems: "center", marginBottom: 16 }}>
          <Undo2 size={18} color="#F72585" style={{ marginRight: 8 }}/>
          <h2 style={{ fontSize: 18, fontWeight: 800, margin: 0, flex: 1 }}>Issue Refund</h2>
          <button onClick={onClose} data-testid="admin-refunds-modal-close"
                        style={{ background: "transparent", border: 0, color: "#64748b",
                                          cursor: "pointer" }}><X size={20}/></button>
        </div>

        <Label>Transaction ID</Label>
        <input value={transactionId}
                    onChange={(e) => setTransactionId(e.target.value)}
                    placeholder="tx5_..."
                    data-testid="admin-refunds-tx-input"
                    style={inputStyle}/>

        <Label>Amount (leave blank for full refund)</Label>
        <div style={{ position: "relative" }}>
          <span style={{ position: "absolute", left: 10, top: 10,
                                    color: "#64748b", fontSize: 13 }}>$</span>
          <input type="number" step="0.01" min="0"
                      value={amountUsd}
                      onChange={(e) => setAmountUsd(e.target.value)}
                      placeholder="0.00"
                      data-testid="admin-refunds-amount-input"
                      style={{ ...inputStyle, paddingLeft: 24 }}/>
        </div>

        <Label>Reason</Label>
        <select value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        data-testid="admin-refunds-reason-select"
                        style={inputStyle}>
          {REASON_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        <label style={{ display: "flex", alignItems: "center", gap: 8,
                                      marginBottom: 12, fontSize: 13, cursor: "pointer" }}>
          <input type="checkbox" checked={refundAppFee}
                      onChange={(e) => setRefundAppFee(e.target.checked)}
                      data-testid="admin-refunds-app-fee-checkbox"/>
          <span>Also refund platform commission (application_fee)</span>
        </label>

        <Label>Note (optional)</Label>
        <textarea value={note} rows={2}
                            onChange={(e) => setNote(e.target.value)}
                            placeholder="Internal note visible to admin/merchant only"
                            data-testid="admin-refunds-note-input"
                            style={{ ...inputStyle, minHeight: 60, resize: "vertical",
                                              fontFamily: "inherit" }}/>

        {err && (
          <div style={{ background: "rgba(244,63,94,0.15)", color: "#f43f5e",
                                    padding: "10px 12px", borderRadius: 8, fontSize: 12,
                                    marginBottom: 12, display: "flex", alignItems: "center", gap: 6 }}
                    data-testid="admin-refunds-error">
            <AlertTriangle size={14}/> {err}
          </div>
        )}

        <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
          <button onClick={onClose}
                        style={{ flex: 1, background: "transparent",
                                          border: "1px solid #2a2a3a", color: "#94a3b8",
                                          borderRadius: 999, padding: "10px 16px",
                                          fontSize: 13, fontWeight: 600, cursor: "pointer" }}>
            Cancel
          </button>
          <button onClick={submit} disabled={busy}
                        data-testid="admin-refunds-submit-btn"
                        style={{ flex: 1, background: busy
                                          ? "#333"
                                          : "linear-gradient(135deg,#F72585,#B5179E)",
                                          color: "#fff", border: 0, borderRadius: 999,
                                          padding: "10px 16px", fontSize: 13, fontWeight: 700,
                                          cursor: busy ? "not-allowed" : "pointer" }}>
            {busy ? "Processing…" : "Refund"}
          </button>
        </div>
      </div>
    </div>
  );
}

function Label({ children }) {
  return <div style={{ fontSize: 10, fontWeight: 700, letterSpacing: 1,
                                            color: "#64748b", textTransform: "uppercase",
                                            marginBottom: 6, marginTop: 12 }}>{children}</div>;
}
const inputStyle = {
  width: "100%", background: "#0d0d18", border: "1px solid #2a2a3a",
  color: "#e2e8f0", borderRadius: 6, padding: "10px 12px",
  fontSize: 13, boxSizing: "border-box",
};
