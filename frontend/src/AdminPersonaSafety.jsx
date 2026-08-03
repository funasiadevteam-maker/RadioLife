/**
 * Phase 39 Session 2 — Admin tile: Persona Safety Audit.
 *
 * Visible at /admin/personas/safety. Lists every persona with its
 * stored safety_classification, a re-classify-all button (POST
 * /api/admin/personas/reclassify_all), and a last_classified_at
 * timestamp so the admin sees when the blocklist was last re-run.
 */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import { ShieldCheck, RefreshCw, ShieldAlert } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL || "";


export default function AdminPersonaSafety() {
  const [rows, setRows]                  = useState([]);
  const [summary, setSummary]          = useState({ total: 0, safe: 0, unsafe: 0 });
  const [busy, setBusy]                  = useState(false);
  const [loading, setLoading]          = useState(true);

  const refresh = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/personas/safety_audit`,
                                              { withCredentials: true });
      setRows(r.data?.personas || []);
      setSummary({ total: r.data?.total || 0,
                              safe:  r.data?.safe  || 0,
                              unsafe: r.data?.unsafe || 0 });
    } catch (e) {
      toast.error("Couldn't load persona audit.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { refresh(); }, []);

  const reclassify = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/admin/personas/reclassify_all`,
                                                  {}, { withCredentials: true });
      toast.success(`Re-classified ${r.data.examined} personas. `
        + `Newly unsafe: ${r.data.became_unsafe.length}`);
      await refresh();
    } catch (e) {
      toast.error("Re-classify failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="admin-persona-safety-page"
            style={{ maxWidth: 1100, margin: "0 auto", padding: 24 }}>
      <header style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 18 }}>
        <h1 style={{ color: "#fff", fontSize: 22, fontWeight: 700,
                                margin: 0, display: "flex", alignItems: "center", gap: 8 }}>
          <ShieldCheck size={20} color="#10b981" /> Persona Safety Audit
        </h1>
        <button data-testid="admin-persona-reclassify-btn"
                        onClick={reclassify} disabled={busy}
                        style={{ background: "#10b981", color: "#0b0b0b",
                                    border: "none", padding: "8px 14px",
                                    borderRadius: 6, fontWeight: 600,
                                    display: "inline-flex", alignItems: "center", gap: 6,
                                    cursor: busy ? "wait" : "pointer",
                                    opacity: busy ? 0.6 : 1 }}>
          <RefreshCw size={14} className={busy ? "animate-spin" : ""} />
          {busy ? "Re-classifying…" : "Re-classify all"}
        </button>
      </header>

      <div style={{ display: "flex", gap: 16, marginBottom: 20 }}>
        <StatCard label="Total"  value={summary.total}  color="#3b82f6" />
        <StatCard label="Safe"    value={summary.safe}    color="#10b981" />
        <StatCard label="Unsafe" value={summary.unsafe} color="#ef4444"
                          danger={summary.unsafe > 0} />
      </div>

      {loading ? (
        <div style={{ color: "#9aa3af", padding: 24 }}>Loading…</div>
      ) : (
        <table data-testid="admin-persona-safety-table"
                      style={{ width: "100%", borderCollapse: "collapse",
                                  fontSize: 13, color: "#d1d5db" }}>
          <thead>
            <tr style={{ color: "#9aa3af", textAlign: "left",
                                  borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
              <th style={{ padding: "8px 6px" }}>persona_id</th>
              <th style={{ padding: "8px 6px" }}>display_name</th>
              <th style={{ padding: "8px 6px" }}>voice_key</th>
              <th style={{ padding: "8px 6px" }}>is_safe</th>
              <th style={{ padding: "8px 6px" }}>flags</th>
              <th style={{ padding: "8px 6px" }}>classified_at</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p) => {
              const sc = p.safety_classification || {};
              const safe = sc.is_safe === true;
              return (
                <tr key={p.persona_id}
                        data-testid={`admin-persona-row-${p.persona_id}`}
                        style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}>
                  <td style={{ padding: "8px 6px", fontFamily: "monospace" }}>
                    {p.persona_id}
                  </td>
                  <td style={{ padding: "8px 6px" }}>{p.display_name}</td>
                  <td style={{ padding: "8px 6px", color: "#9aa3af" }}>
                    {p.voice_key}
                  </td>
                  <td style={{ padding: "8px 6px",
                                          color: safe ? "#10b981" : "#ef4444" }}>
                    {safe ? "✓" : <span><ShieldAlert size={12}
                          style={{ display: "inline", verticalAlign: -2 }}/> NO</span>}
                  </td>
                  <td style={{ padding: "8px 6px", color: "#f59e0b",
                                          fontFamily: "monospace", fontSize: 11 }}>
                    {(sc.flags || []).join(", ") || "—"}
                  </td>
                  <td style={{ padding: "8px 6px", color: "#6b7280",
                                          fontSize: 11 }}>
                    {sc.classified_at?.slice(0, 19) || "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}


function StatCard({ label, value, color, danger }) {
  return (
    <div style={{ background: "#1f2937", borderRadius: 8,
                          padding: "12px 18px",
                          border: danger ? `1px solid ${color}` : "none" }}>
      <div style={{ color: "#9aa3af", fontSize: 12,
                              textTransform: "uppercase", letterSpacing: 1 }}>
        {label}
      </div>
      <div style={{ color, fontSize: 22, fontWeight: 700,
                              marginTop: 2 }}>{value}</div>
    </div>
  );
}
