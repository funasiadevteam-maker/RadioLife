// Phase SC.6 — Admin Payouts (cross-merchant ledger).
import { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { RefreshCw } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const STATUS_TINTS = {
  pending:            { bg: "rgba(234,179,8,0.15)",    fg: "#eab308" },
  in_transit:      { bg: "rgba(59,130,246,0.15)", fg: "#3b82f6" },
  paid:                    { bg: "rgba(16,185,129,0.15)", fg: "#10b981" },
  failed:                { bg: "rgba(244,63,94,0.15)",    fg: "#f43f5e" },
  canceled:            { bg: "rgba(148,163,184,0.15)", fg: "#94a3b8" },
};


export default function AdminPayouts() {
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
      const { data } = await axios.get(`${API}/admin/payouts`,
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
              data-testid="admin-payouts-page">
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
        <h1 style={{ fontSize: 28, fontWeight: 800, letterSpacing: -0.5,
                                  margin: 0, flex: 1 }}>Payouts</h1>
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
                    data-testid="admin-payouts-merchant-filter"
                    style={{ background: "#161628", border: "1px solid #2a2a3a",
                                      color: "#e2e8f0", borderRadius: 6, padding: "8px 10px",
                                      fontSize: 12, width: 240 }}/>
        <select value={statusFilter}
                        onChange={(e) => setStatusFilter(e.target.value)}
                        data-testid="admin-payouts-status-filter"
                        style={{ background: "#161628", border: "1px solid #2a2a3a",
                                          color: "#e2e8f0", borderRadius: 6, padding: "8px 10px",
                                          fontSize: 12 }}>
          <option value="">All statuses</option>
          <option value="pending">Pending</option>
          <option value="in_transit">In transit</option>
          <option value="paid">Paid</option>
          <option value="failed">Failed</option>
          <option value="canceled">Canceled</option>
        </select>
        <div style={{ marginLeft: "auto", color: "#64748b", fontSize: 12,
                                  alignSelf: "center" }}>
          {loading ? "Loading…" : `${total} payout${total === 1 ? "" : "s"}`}
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
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Payout ID</th>
              <th style={{ padding: "12px 14px", textAlign: "right" }}>Amount</th>
              <th style={{ padding: "12px 14px", textAlign: "center" }}>Status</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Method</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Arrival</th>
              <th style={{ padding: "12px 14px", textAlign: "left" }}>Created</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: 24, textAlign: "center",
                                                                            color: "#64748b" }}>
                No payouts yet.  Payouts will appear here once Stripe wires
                them to the platform webhook.
              </td></tr>
            ) : rows.map((p) => {
              const tint = STATUS_TINTS[p.status] || {};
              return (
                <tr key={p.stripe_payout_id}
                      data-testid={`admin-payout-row-${p.stripe_payout_id}`}
                      style={{ borderTop: "1px solid #2a2a3a" }}>
                  <td style={{ padding: "10px 14px" }}>
                    <div style={{ fontWeight: 600 }}>{p.merchant_name || "—"}</div>
                    <div style={{ fontSize: 10, color: "#64748b",
                                              fontFamily: "monospace" }}>{p.merchant_id}</div>
                  </td>
                  <td style={{ padding: "10px 14px", fontFamily: "monospace",
                                              fontSize: 11, color: "#94a3b8" }}>{p.stripe_payout_id}</td>
                  <td style={{ padding: "10px 14px", textAlign: "right",
                                              fontVariantNumeric: "tabular-nums", fontWeight: 600 }}>
                    {(p.amount_cents / 100).toFixed(2)} <span style={{
                      fontSize: 10, color: "#64748b" }}>{p.currency}</span>
                  </td>
                  <td style={{ padding: "10px 14px", textAlign: "center" }}>
                    <span style={{ background: tint.bg, color: tint.fg,
                                              padding: "3px 10px", borderRadius: 999,
                                              fontSize: 10, fontWeight: 700,
                                              textTransform: "uppercase" }}>
                      {p.status}
                    </span>
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11,
                                              color: "#94a3b8" }}>{p.method}</td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#94a3b8" }}>
                    {p.arrival_date ? new Date(p.arrival_date)
                                                                .toLocaleDateString(undefined,
                          { month: "short", day: "numeric", year: "numeric" }) : "—"}
                  </td>
                  <td style={{ padding: "10px 14px", fontSize: 11, color: "#64748b" }}>
                    {p.created_at ? new Date(p.created_at).toLocaleString(undefined,
                      { month: "short", day: "numeric", hour: "2-digit",
                        minute: "2-digit" }) : ""}
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
