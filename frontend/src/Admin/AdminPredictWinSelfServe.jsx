/** Phase 42-E1.3 — Admin: Predict & Win pricing + pending-approval queue.
 *
 *  Route: /admin/predict-win/self-serve
 *  Mounted under AdminSubNav → Predict & Win → Self-Serve.
 *
 *  Two tabs:
 *      - Pending Approval — list advertiser-submitted campaigns awaiting
 *          admin review.  Each row exposes Approve + Reject (with reason).
 *      - Pricing — edit `min_campaign_price_usd` + `per_participant_price_usd`.
 *
 *  Sibling of `Admin/PredictWinCampaigns.jsx` (which still hosts the
 *  existing campaign list + Predexon import).  Kept separate to avoid
 *  regressing the live campaign management surface.
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Trophy, DollarSign, Loader2, Check, X, AlertCircle, ChevronRight,
} from "lucide-react";
import AdminSubNav from "@/AdminSubNav";
import { API } from "@/AuthContext";

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export default function AdminPredictWinSelfServe() {
  const [tab, setTab] = useState("pending");

  return (
    <div data-testid="admin-pw-self-serve-page"
                style={{ display: "flex", minHeight: "100vh",
                              background: "#070710" }}>
      <Toaster richColors position="top-right" />
      <AdminSubNav />
      <main style={{ flex: 1, padding: "28px 32px",
                                  color: "#cbd5e1", overflowY: "auto" }}>
        <header style={{ display: "flex", justifyContent: "space-between",
                                      alignItems: "center", marginBottom: 22 }}>
          <h1 style={{ display: "inline-flex", alignItems: "center", gap: 10,
                                      color: "#fff", margin: 0, fontSize: 22 }}>
            <Trophy size={20} color="#fbbf24" /> Predict & Win — Self-Serve
          </h1>
        </header>

        <div style={{ display: "flex", gap: 6, marginBottom: 16 }}
                  data-testid="admin-pw-self-serve-tabs">
          {[
            { id: "pending", label: "Pending Approval" },
            { id: "pricing", label: "Pricing" },
          ].map(t => (
            <button key={t.id}
                            data-testid={`admin-pw-tab-${t.id}`}
                            data-active={tab === t.id ? "true" : "false"}
                            onClick={() => setTab(t.id)}
                            style={{
                              background: tab === t.id ? "#fbbf24" : "transparent",
                              color:      tab === t.id ? "#0b0b0b" : "#cbd5e1",
                              border: tab === t.id
                                ? "1px solid #fbbf24"
                                : "1px solid #25252f",
                              padding: "7px 14px", borderRadius: 8,
                              fontSize: 12, fontWeight: 600, cursor: "pointer",
                            }}>
              {t.label}
            </button>
          ))}
        </div>

        {tab === "pending" && <PendingTab />}
        {tab === "pricing" && <PricingTab />}
      </main>
    </div>
  );
}

// ─── Pending tab ────────────────────────────────────────────────
function PendingTab() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/predict-win/pending`,
                                                          { withCredentials: true });
      setRows(r.data?.items || []);
    } catch (e) {
      toast.error("Failed to load pending campaigns");
    }
    setLoading(false);
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const approve = async (id) => {
    try {
      await axios.post(`${API}/admin/predict-win/${id}/approve`,
                                          {}, { withCredentials: true });
      toast.success("Campaign approved and live");
      reload();
    } catch (e) { toast.error("Approve failed"); }
  };
  const reject = async (id) => {
    const reason = window.prompt("Rejection reason?");
    if (!reason || !reason.trim()) return;
    try {
      await axios.post(`${API}/admin/predict-win/${id}/reject`,
                                          { reason: reason.trim() },
                                          { withCredentials: true });
      toast.success("Campaign rejected");
      reload();
    } catch (e) { toast.error("Reject failed"); }
  };

  return (
    <section data-testid="admin-pw-pending-list">
      {loading ? (
        <div style={{ color: "#9aa3af", padding: 40,
                                  textAlign: "center" }}>Loading…</div>
      ) : rows.length === 0 ? (
        <div data-testid="admin-pw-pending-empty"
                  style={{ color: "#9aa3af", padding: 40,
                                  textAlign: "center",
                                  border: "1px dashed #25252f",
                                  borderRadius: 8 }}>
          No campaigns waiting for review.
        </div>
      ) : (
        rows.map(c => (
          <div key={c._id}
                    data-testid={`admin-pw-pending-row-${c._id}`}
                    style={{ background: "#0f0f15",
                                border: "1px solid #1f1f28",
                                borderRadius: 10, padding: 16,
                                marginBottom: 10 }}>
            <div style={{ display: "flex",
                                        justifyContent: "space-between",
                                        gap: 14 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ color: "#fff", fontWeight: 600,
                                            fontSize: 14, marginBottom: 4 }}>
                  {c.title}
                </div>
                <div style={{ color: "#9aa3af", fontSize: 12,
                                            marginBottom: 6 }}>
                  Submitted {fmtTime(c.submitted_at)} · Locks {fmtTime(c.lock_time)}
                </div>
                <div style={{ color: "#cbd5e1", fontSize: 12,
                                            background: "#16161f",
                                            padding: "8px 10px",
                                            borderRadius: 6,
                                            marginBottom: 8 }}>
                  {c.description}
                </div>
                {c.pricing_snapshot && (
                  <div style={{ color: "#fbbf24", fontSize: 12 }}>
                    Quote: <strong>${c.pricing_snapshot.total_quoted_usd}</strong>
                                  ·  {c.pricing_snapshot.expected_participants} participants
                                  ·  PI: <span style={{ fontFamily: "monospace",
                                                                          color: "#9aa3af" }}>
                      {c.payment_intent_id || "—"}
                    </span>
                  </div>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column",
                                          gap: 8, flexShrink: 0 }}>
                <button onClick={() => approve(c._id)}
                                  data-testid={`admin-pw-approve-${c._id}`}
                                  style={{ display: "inline-flex", gap: 6,
                                              alignItems: "center",
                                              background: "#4ade80",
                                              color: "#0a1a0a", border: 0,
                                              borderRadius: 6,
                                              padding: "8px 14px",
                                              fontSize: 12, fontWeight: 600,
                                              cursor: "pointer" }}>
                  <Check size={12} /> Approve
                </button>
                <button onClick={() => reject(c._id)}
                                  data-testid={`admin-pw-reject-${c._id}`}
                                  style={{ display: "inline-flex", gap: 6,
                                              alignItems: "center",
                                              background: "transparent",
                                              color: "#f87171",
                                              border: "1px solid #f87171",
                                              borderRadius: 6,
                                              padding: "8px 14px",
                                              fontSize: 12, fontWeight: 600,
                                              cursor: "pointer" }}>
                  <X size={12} /> Reject
                </button>
              </div>
            </div>
          </div>
        ))
      )}
    </section>
  );
}

// ─── Pricing tab ────────────────────────────────────────────────
function PricingTab() {
  const [pricing, setPricing] = useState(null);
  const [edit, setEdit] = useState({ min: "", per: "" });
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/predict-win/pricing`,
                                                          { withCredentials: true });
      setPricing(r.data);
      setEdit({ min: r.data?.min_campaign_price_usd ?? "",
                          per: r.data?.per_participant_price_usd ?? "" });
    } catch (e) { toast.error("Failed to load pricing"); }
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const save = async () => {
    setBusy(true);
    try {
      const r = await axios.patch(`${API}/admin/predict-win/pricing`, {
        min_campaign_price_usd:    Number(edit.min),
        per_participant_price_usd: Number(edit.per),
      }, { withCredentials: true });
      setPricing(r.data);
      toast.success("Pricing updated");
    } catch (e) { toast.error("Save failed"); }
    setBusy(false);
  };

  if (!pricing) {
    return <div style={{ color: "#9aa3af", padding: 40,
                                                  textAlign: "center" }}>Loading…</div>;
  }
  const dirty = (Number(edit.min) !== Number(pricing.min_campaign_price_usd)
                              || Number(edit.per) !== Number(pricing.per_participant_price_usd));

  return (
    <section data-testid="admin-pw-pricing"
                    style={{ maxWidth: 460 }}>
      <div style={{ background: "#0f0f15",
                                  border: "1px solid #1f1f28",
                                  borderRadius: 10, padding: 18 }}>
        <h3 style={{ color: "#fff", fontSize: 13,
                                  textTransform: "uppercase",
                                  letterSpacing: 1.3, marginTop: 0,
                                  marginBottom: 14,
                                  display: "inline-flex",
                                  alignItems: "center", gap: 6 }}>
          <DollarSign size={12} /> Pricing config
        </h3>
        <label style={{ display: "block", fontSize: 11,
                                    color: "#9aa3af", marginBottom: 12 }}>
          Minimum campaign price (USD)
          <input type="number" min={0} value={edit.min}
                        onChange={(e) => setEdit({ ...edit, min: e.target.value })}
                        data-testid="admin-pw-pricing-min"
                        style={inputStyle} />
        </label>
        <label style={{ display: "block", fontSize: 11,
                                    color: "#9aa3af", marginBottom: 14 }}>
          Per-participant price (USD)
          <input type="number" min={0} value={edit.per}
                        onChange={(e) => setEdit({ ...edit, per: e.target.value })}
                        data-testid="admin-pw-pricing-per"
                        style={inputStyle} />
        </label>
        <div style={{ color: "#666", fontSize: 11,
                                    fontFamily: "monospace",
                                    marginBottom: 14 }}>
          last updated {fmtTime(pricing.updated_at)} by {pricing.updated_by || "—"}
        </div>
        <button onClick={save} disabled={!dirty || busy}
                        data-testid="admin-pw-pricing-save"
                        style={{ display: "inline-flex", gap: 6,
                                      alignItems: "center",
                                      background: dirty ? "#fbbf24" : "#1f1f28",
                                      color: dirty ? "#0b0b0b" : "#666",
                                      border: 0, borderRadius: 8,
                                      padding: "9px 16px", fontSize: 12,
                                      fontWeight: 600,
                                      cursor: dirty ? "pointer" : "not-allowed" }}>
          {busy ? <Loader2 size={12} className="spin" /> : <Check size={12} />}
          Save
        </button>
      </div>
    </section>
  );
}

const inputStyle = {
  display: "block", width: "100%", marginTop: 4,
  background: "#0b0b0f", border: "1px solid #25252f",
  borderRadius: 6, padding: "9px 11px", color: "#fff",
  fontSize: 13, outline: "none",
};
