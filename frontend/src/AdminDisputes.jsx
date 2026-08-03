// Phase SC.6 — Admin Disputes (read-only ledger).
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw, ExternalLink } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_TINTS = {
  needs_response:                  { bg: "rgba(244,63,94,0.15)",    fg: "#f43f5e" },
  warning_needs_response:  { bg: "rgba(244,63,94,0.15)",    fg: "#f43f5e" },
  under_review:                      { bg: "rgba(234,179,8,0.15)",    fg: "#eab308" },
  won:                                          { bg: "rgba(16,185,129,0.15)", fg: "#10b981" },
  lost:                                        { bg: "rgba(148,163,184,0.15)", fg: "#94a3b8" },
  warning_closed:                  { bg: "rgba(148,163,184,0.15)", fg: "#94a3b8" },
  charge_refunded:              { bg: "rgba(148,163,184,0.15)", fg: "#94a3b8" },
};


export default function AdminDisputes() {
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [merchantFilter, setMerchantFilter] = useState("");

  const load = async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter) params.status = statusFilter;
      if (merchantFilter) params.merchant_id = merchantFilter;
      const { data } = await axios.get(`${API}/admin/disputes`,
                                                                      { params, withCredentials: true });
      setRows(data.rows || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [statusFilter, merchantFilter]);

  const openInStripe = async (merchantId) => {
    try {
      const { data } = await axios.post(`${API}/stripe/connect/dashboard-link`,
                                                                          { merchant_id: merchantId },
                                                                          { withCredentials: true });
      if (data.url) window.open(data.url, "_blank");
      else toast.error("No dashboard URL returned");
    } catch (e) {
      toast.error(`Stripe link failed: ${e?.response?.data?.detail || e.message}`);
    }
  };

  return (
    <div style={{ marginLeft: 220, padding: 24,
                              minHeight: "100vh", background: "#0d0d18", color: "#e2e8f0" }}
              data-testid="admin-disputes-page">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: -0.5,
                                  margin: 0, flex: 1 }}>Disputes</h1>
        <button onClick={load}
                        style={{ background: "transparent", border: "1px solid #2a2a3a",
                                          color: "#94a3b8", borderRadius: 8, padding: "8px 12px",
                                          fontSize: 12, cursor: "pointer" }}>
          <RefreshCw size={13} style={{ display: "inline", marginRight: 4 }}/> Refresh
        </button>
      </div>

      <div style={{ display: "flex", gap: 10, marginBottom: 16 }}>
        <input placeholder="Filter by merchant_id"
                    value={merchantFilter}
                    onChange={(e) => setMerchantFilter(e.target.value)}
                    data-testid="admin-disputes-merchant-filter"
                    style={{ background: "#161628", border: "1px solid #2a2a3a",
                                      color: "#e2e8f0", borderRadius: 6, padding: "8px 10px",
                                      fontSize: 12, width: 240 }}/>
        <select value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        data-testid="admin-disputes-status-filter"
                        style={{ background: "#161628", border: "1px solid #2a2a3a",
                                          color: "#e2e8f0", borderRadius: 6, padding: "8px 10px",
                                          fontSize: 12 }}>
          <option value="">All statuses</option>
          <option value="warning_needs_response">Warning · Needs response</option>
          <option value="needs_response">Needs response</option>
          <option value="under_review">Under review</option>
          <option value="won">Won</option>
          <option value="lost">Lost</option>
          <option value="warning_closed">Closed</option>
        </select>
        <div style={{ marginLeft: "auto", color: "#64748b", fontSize: 12,
                                  alignSelf: "center" }}>
          {loading ? "Loading…" : `${total} dispute${total === 1 ? "" : "s"}`}
        </div>
      </div>

      <div style={{ background: "#161628", border: "1px solid #2a2a3a",
                                borderRadius: 12, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "#0d0d18", color: "#64748b",
                                      textTransform: "uppercase", fontSize: 10,
                                      letterSpacing: 1 }}>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Merchant</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Transaction</th>
              <th style={{ padding: "12px 14px", textAlign: "right" }}>Amount</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Reason</th>
              <th style={{ padding: "12px 14px", textAlign: "center" }}>Status</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Evidence Due</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Created</th>
              <th style={{ padding: "12px 14px" }}></th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={8} style={{ padding: 24, textAlign: "center",
                                                                            color: "#64748b" }}>
                No disputes yet.  Disputes will appear here when a customer
                initiates a chargeback.
              </td></tr>
            ) : rows.map((d) => {
              const tint = STATUS_TINTS[d.status] || STATUS_TINTS.under_review;
              return (
                <tr key={d.stripe_dispute_id}
                      data-testid={`admin-dispute-row-${d.stripe_dispute_id}`}
                      style={{ borderTop: "1px solid #2a2a3a" }}>
                  <td style={{ padding: "10px 14px" }}>
                    <div style={{ fontWeight: 600 }}>{d.merchant_name || "—"}</div>
                    <div style={{ fontSize: 10, color: "#64748b",
                                              fontFamily: "monospace" }}>{d.merchant_id}</div>
                  </td>
                  <td style={{ padding: "10px 14px", fontFamily: "monospace",
                                              fontSize: 11, color: "#94a3b8" }}>{d.transaction_id || d.stripe_charge_id}</td>
                  <td style={{ padding: "10px 14px", textAlign: "right",
                                              fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                    {(d.amount_cents / 100).toFixed(2)} <span style={{
                      fontSize: 10, color: "#64748b" }}>{d.currency}</span>
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#94a3b8" }}>
                    {(d.reason || "").replace(/_/g, " ")}
                  </td>
                  <td style={{ padding: "10px 14px", textAlign: "center" }}>
                    <span style={{ background: tint.bg, color: tint.fg,
                                              padding: "3px 10px", borderRadius: 999,
                                              fontSize: 10, fontWeight: 700,
                                              textTransform: "uppercase" }}>
                      {(d.status || "").replace(/_/g, " ")}
                    </span>
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#f43f5e" }}>
                    {d.evidence_due_by ? new Date(d.evidence_due_by)
                          .toLocaleDateString(undefined, { month: "short", day: "numeric" })
                          : "—"}
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#64748b" }}>
                    {d.created_at ? new Date(d.created_at).toLocaleDateString(undefined,
                      { month: "short", day: "numeric", year: "numeric" }) : ""}
                  </td>
                  <td style={{ padding: "10px 14px" }}>
                    <button onClick={() => openInStripe(d.merchant_id)}
                                  data-testid={`admin-dispute-open-stripe-${d.stripe_dispute_id}`}
                                  style={{ background: "rgba(99,91,255,0.15)",
                                                    color: "#635BFF", border: 0,
                                                    borderRadius: 999, padding: "6px 12px",
                                                    fontSize: 11, fontWeight: 700,
                                                    cursor: "pointer", display: "inline-flex",
                                                    alignItems: "center", gap: 4 }}>
                      <ExternalLink size={11}/> Stripe
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
