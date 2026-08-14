// Admin — Sales Tax Rules (jurisdiction rate table + AI estimate helper).
// Origin-based rates applied to marketplace orders. Legacy dark shell, admin-only.
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const EMPTY = { country: "", state: "", county: "", city: "", rate_percent: "", label: "", active: true };

export default function AdminTaxRules() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [aiBusy, setAiBusy] = useState(false);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await axios.get(`${API}/admin/tax/rules`); setRules(r.data.items || []); }
    catch { toast.error("Failed to load tax rules"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const reset = () => { setForm(EMPTY); setEditId(null); };

  const aiEstimate = async () => {
    if (!form.country) { toast.error("Enter a country first"); return; }
    setAiBusy(true);
    try {
      const r = await axios.post(`${API}/admin/tax/ai-estimate`, {
        country: form.country, state: form.state || null, county: form.county || null, city: form.city || null,
      });
      setForm((f) => ({ ...f, rate_percent: r.data.rate_percent, label: r.data.label }));
      toast.success(`AI estimate: ${r.data.rate_percent}%`, { description: r.data.disclaimer });
    } catch { toast.error("AI estimate unavailable"); }
    finally { setAiBusy(false); }
  };

  const save = async () => {
    if (!form.country || form.rate_percent === "") { toast.error("Country and rate are required"); return; }
    setSaving(true);
    const body = {
      country: form.country.trim(), state: form.state || null, county: form.county || null, city: form.city || null,
      rate_percent: Number(form.rate_percent), label: form.label || null, active: !!form.active,
    };
    try {
      if (editId) await axios.patch(`${API}/admin/tax/rules/${editId}`, body);
      else await axios.post(`${API}/admin/tax/rules`, body);
      toast.success(editId ? "Rule updated" : "Rule added");
      reset(); load();
    } catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };

  const edit = (r) => {
    setEditId(r.rule_id);
    setForm({ country: r.country || "", state: r.state || "", county: r.county || "",
      city: r.city || "", rate_percent: r.rate_percent, label: r.label || "", active: r.active !== false });
  };

  const del = async (r) => {
    if (!window.confirm(`Delete rule for ${r.country}${r.state ? " / " + r.state : ""}?`)) return;
    try { await axios.delete(`${API}/admin/tax/rules/${r.rule_id}`); toast.success("Deleted"); load(); }
    catch { toast.error("Delete failed"); }
  };

  return (
    <div style={s.page} data-testid="admin-tax-page">
      <div style={s.header}>
        <div style={s.eyebrow}>Marketplace</div>
        <h1 style={s.h1}>Sales Tax Rules</h1>
        <div style={s.sub}>Jurisdiction rate table (country → state → county → city). Origin-based: an order uses the store&apos;s most-specific matching rate. Merchants remain responsible for filing &amp; remitting.</div>
      </div>

      {/* Add / edit form */}
      <div style={s.card} data-testid="admin-tax-form">
        <div style={s.formTitle}>{editId ? "Edit rule" : "Add rule"}</div>
        <div style={s.grid}>
          <Field label="Country *"><input style={s.input} data-testid="tax-form-country" value={form.country} onChange={(e) => setForm((f) => ({ ...f, country: e.target.value }))} placeholder="AE / US" /></Field>
          <Field label="State"><input style={s.input} data-testid="tax-form-state" value={form.state} onChange={(e) => setForm((f) => ({ ...f, state: e.target.value }))} placeholder="CA" /></Field>
          <Field label="County"><input style={s.input} data-testid="tax-form-county" value={form.county} onChange={(e) => setForm((f) => ({ ...f, county: e.target.value }))} placeholder="Los Angeles" /></Field>
          <Field label="City"><input style={s.input} data-testid="tax-form-city" value={form.city} onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))} placeholder="Los Angeles" /></Field>
          <Field label="Rate %"><input style={s.input} type="number" min={0} max={40} step={0.01} data-testid="tax-form-rate" value={form.rate_percent} onChange={(e) => setForm((f) => ({ ...f, rate_percent: e.target.value }))} placeholder="5" /></Field>
          <Field label="Label"><input style={s.input} data-testid="tax-form-label" value={form.label} onChange={(e) => setForm((f) => ({ ...f, label: e.target.value }))} placeholder="UAE VAT" /></Field>
        </div>
        <label style={s.checkRow}>
          <input type="checkbox" data-testid="tax-form-active" checked={form.active} onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))} /> Active
        </label>
        <div style={s.formActions}>
          <button style={s.btnGhost} onClick={aiEstimate} disabled={aiBusy} data-testid="tax-form-ai">{aiBusy ? "Estimating…" : "✨ AI estimate rate"}</button>
          <div style={{ flex: 1 }} />
          {editId && <button style={s.btnGhost} onClick={reset} data-testid="tax-form-cancel">Cancel</button>}
          <button style={s.btnPrimary} onClick={save} disabled={saving} data-testid="tax-form-save">{saving ? "Saving…" : editId ? "Update rule" : "Add rule"}</button>
        </div>
      </div>

      {/* Rules table */}
      <div style={s.tableWrap} data-testid="admin-tax-table">
        <table style={s.table}>
          <thead>
            <tr>
              {["Country", "State", "County", "City", "Rate", "Label", "Status", ""].map((h) => <th key={h} style={s.th}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {loading && <tr><td style={s.td} colSpan={8}>Loading…</td></tr>}
            {!loading && rules.length === 0 && <tr><td style={s.td} colSpan={8}>No rules yet. Add one above.</td></tr>}
            {rules.map((r) => (
              <tr key={r.rule_id} style={s.tr} data-testid={`tax-rule-${r.rule_id}`}>
                <td style={s.td}>{r.country}</td>
                <td style={s.td}>{r.state || "—"}</td>
                <td style={s.td}>{r.county || "—"}</td>
                <td style={s.td}>{r.city || "—"}</td>
                <td style={{ ...s.td, fontWeight: 800, color: "#00d4ff" }}>{r.rate_percent}%</td>
                <td style={s.td}>{r.label || "—"}</td>
                <td style={s.td}><span style={{ ...s.pill, background: r.active ? "#134e2a" : "#3a1414", color: r.active ? "#4ade80" : "#f87171" }}>{r.active ? "Active" : "Off"}</span></td>
                <td style={s.td}>
                  <button style={s.btnGhost} onClick={() => edit(r)} data-testid={`tax-edit-${r.rule_id}`}>Edit</button>{" "}
                  <button style={{ ...s.btnGhost, color: "#f87171", borderColor: "#5a2020" }} onClick={() => del(r)} data-testid={`tax-del-${r.rule_id}`}>Delete</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Field({ label, children }) {
  return <div><div style={s.fieldLabel}>{label}</div>{children}</div>;
}

const s = {
  page: { minHeight: "100vh", background: "#0d0d18", color: "#e2e8f0", padding: "24px 28px 60px", fontFamily: "ui-sans-serif, system-ui, sans-serif" },
  header: { marginBottom: 20 },
  eyebrow: { fontSize: 11, letterSpacing: 2, textTransform: "uppercase", color: "#00d4ff", fontWeight: 700 },
  h1: { fontSize: 26, fontWeight: 800, margin: "4px 0 6px", letterSpacing: "-0.02em" },
  sub: { color: "#94a3b8", fontSize: 13, maxWidth: 760 },
  card: { background: "#1e1e2e", border: "1px solid #2a2a3a", borderRadius: 12, padding: 18, marginBottom: 20 },
  formTitle: { fontSize: 14, fontWeight: 800, marginBottom: 12 },
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: 10 },
  fieldLabel: { fontSize: 10, textTransform: "uppercase", letterSpacing: 1, color: "#94a3b8", fontWeight: 700, marginBottom: 4 },
  input: { width: "100%", background: "#0d0d18", border: "1px solid #334155", borderRadius: 8, padding: "9px 11px", color: "#e2e8f0", fontSize: 13, boxSizing: "border-box" },
  checkRow: { display: "flex", alignItems: "center", gap: 8, marginTop: 12, fontSize: 13, color: "#cbd5e1" },
  formActions: { display: "flex", alignItems: "center", gap: 8, marginTop: 16 },
  tableWrap: { background: "#1e1e2e", borderRadius: 12, border: "1px solid #2a2a3a", overflow: "auto" },
  table: { width: "100%", borderCollapse: "separate", borderSpacing: 0, fontSize: 12 },
  th: { textAlign: "left", padding: "11px 13px", background: "#151521", color: "#94a3b8", fontSize: 10, textTransform: "uppercase", letterSpacing: 1, fontWeight: 700, borderBottom: "1px solid #2a2a3a" },
  tr: { borderBottom: "1px solid #2a2a3a" },
  td: { padding: "10px 13px", borderBottom: "1px solid #2a2a3a", verticalAlign: "middle" },
  btnPrimary: { background: "linear-gradient(135deg, #00d4ff, #6366f1)", color: "#0d0d18", border: 0, borderRadius: 8, padding: "8px 14px", fontSize: 12, fontWeight: 700, cursor: "pointer", textTransform: "uppercase", letterSpacing: 0.5 },
  btnGhost: { background: "transparent", color: "#94a3b8", border: "1px solid #334155", borderRadius: 8, padding: "7px 13px", fontSize: 11, fontWeight: 600, cursor: "pointer" },
  pill: { display: "inline-block", padding: "3px 10px", borderRadius: 999, fontSize: 10, fontWeight: 700, letterSpacing: 0.5, textTransform: "uppercase" },
};
