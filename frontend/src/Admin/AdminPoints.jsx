/** Phase F-1 — Admin Points dashboard.
 *
 *  Routes:    /admin/points
 *  Mounted: under AdminSubNav (Operations group).
 *
 *  Two tabs:
 *  - Ledger:     paginated table, filters by user_id / source / date range,
 *                      with per-row Reverse action and a CSV export button.
 *  - Earn Rules: list of rule configs with editable cap inputs and
 *                      enable/disable toggle (PATCH to /api/admin/points/earn-rules/<id>).
 *
 *  Grant modal: lookup target user, enter delta + reason → POST
 *  /api/admin/points/grant.  Caps are bypassed (admin override).
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Coins, Plus, X, Search, RotateCcw, Download, ToggleLeft, ToggleRight,
  Loader2, Sparkles, AlertTriangle,
} from "lucide-react";
import AdminSubNav from "@/AdminSubNav";
import { API } from "@/AuthContext";

// ─── Helpers ──────────────────────────────────────────────────────
function fmt(n) {
  return Number(n || 0).toLocaleString();
}
function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString();
}
function downloadCsv(rows, name = "points_ledger.csv") {
  if (!rows.length) return;
  const cols = ["created_at", "user_id", "source", "delta",
                              "balance_after", "entry_id", "idempotency_key"];
  const escape = (v) => {
    if (v == null) return "";
    const s = String(v).replace(/"/g, '""');
    return /[",\n]/.test(s) ? `"${s}"` : s;
  };
  const csv = [cols.join(",")].concat(
    rows.map(r => cols.map(c => escape(r[c])).join(","))).join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = name; a.click();
  URL.revokeObjectURL(url);
}

// ─── Page ─────────────────────────────────────────────────────────
export default function AdminPoints() {
  const [tab, setTab] = useState("ledger");
  const [grantOpen, setGrantOpen] = useState(false);

  return (
    <div data-testid="admin-points-page"
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
            <Coins size={20} color="#fbbf24" /> Points Engine
          </h1>
          <button onClick={() => setGrantOpen(true)}
                          data-testid="admin-points-open-grant"
                          style={{ ...btnPrimary, padding: "9px 16px" }}>
            <Plus size={14} /> Grant Points
          </button>
        </header>

        {/* Tabs */}
        <div style={{ display: "flex", gap: 6, marginBottom: 16 }}
                data-testid="admin-points-tabs">
          {[
            { id: "ledger",            label: "Ledger" },
            { id: "earn-rules", label: "Earn Rules" },
          ].map(t => (
            <button key={t.id}
                            data-testid={`admin-points-tab-${t.id}`}
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

        {tab === "ledger" && <LedgerTab />}
        {tab === "earn-rules" && <EarnRulesTab />}
      </main>

      {grantOpen && <GrantModal onClose={() => setGrantOpen(false)} />}
    </div>
  );
}

// ─── Ledger Tab ──────────────────────────────────────────────────
function LedgerTab() {
  const [rows, setRows] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ user_id: "", source: "" });

  const reload = useCallback(async (append = false, cur = null) => {
    setLoading(true);
    try {
      const params = { limit: 100 };
      if (filters.user_id) params.user_id = filters.user_id.trim();
      if (filters.source)  params.source  = filters.source.trim();
      if (cur) params.cursor = cur;
      const r = await axios.get(`${API}/admin/points/ledger`,
                                                        { params, withCredentials: true });
      const items = r.data?.items || [];
      setRows((prev) => append ? [...prev, ...items] : items);
      setCursor(r.data?.next_cursor || null);
    } catch (e) {
      toast.error("Failed to load ledger");
    }
    setLoading(false);
  }, [filters]);

  useEffect(() => { reload(); }, [reload]);

  const reverseRow = async (entry_id) => {
    const reason = window.prompt("Reason for reversal?");
    if (!reason || !reason.trim()) return;
    try {
      await axios.post(`${API}/admin/points/reverse`,
                                          { entry_id, reason: reason.trim() },
                                          { withCredentials: true });
      toast.success("Entry reversed");
      reload();
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(code || "Reverse failed");
    }
  };

  return (
    <section data-testid="admin-points-ledger">
      {/* Filter bar */}
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap",
                                  marginBottom: 12 }}>
        <input type="text"
                    placeholder="Filter by user_id"
                    value={filters.user_id}
                    onChange={(e) => setFilters((f) => ({ ...f, user_id: e.target.value }))}
                    data-testid="admin-points-filter-user"
                    style={inputStyle} />
        <input type="text"
                    placeholder="Filter by source (e.g. predict_win_correct)"
                    value={filters.source}
                    onChange={(e) => setFilters((f) => ({ ...f, source: e.target.value }))}
                    data-testid="admin-points-filter-source"
                    style={{ ...inputStyle, minWidth: 280 }} />
        <button onClick={() => reload()}
                        data-testid="admin-points-filter-apply"
                        style={btnGhost}>
          <Search size={12} /> Apply
        </button>
        <button onClick={() => downloadCsv(rows)}
                        data-testid="admin-points-export-csv"
                        style={btnGhost}>
          <Download size={12} /> Export CSV ({rows.length})
        </button>
      </div>

      {/* Table */}
      <div style={{ background: "#0f0f15",
                                  border: "1px solid #1f1f28",
                                  borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse",
                                      fontSize: 12 }}>
          <thead>
            <tr style={{ background: "#16161f" }}>
              <th style={th}>When</th>
              <th style={th}>User</th>
              <th style={th}>Source</th>
              <th style={{ ...th, textAlign: "right" }}>Delta</th>
              <th style={{ ...th, textAlign: "right" }}>Balance</th>
              <th style={th}>Note</th>
              <th style={th}></th>
            </tr>
          </thead>
          <tbody>
            {rows.map(r => (
              <tr key={r.entry_id}
                        data-testid={`admin-points-ledger-row-${r.entry_id}`}
                        style={{ borderTop: "1px solid #1f1f28" }}>
                <td style={td}>{fmtTime(r.created_at)}</td>
                <td style={{ ...td, fontFamily: "monospace",
                                            color: "#9aa3af", maxWidth: 200,
                                            overflow: "hidden",
                                            textOverflow: "ellipsis",
                                            whiteSpace: "nowrap" }}
                          title={r.user_id}>{r.user_id}</td>
                <td style={td}>
                  <span style={{ background: "#1f1f28", padding: "2px 6px",
                                              borderRadius: 4, fontFamily: "monospace",
                                              fontSize: 10 }}>{r.source}</span>
                </td>
                <td style={{ ...td, textAlign: "right",
                                            color: r.delta > 0 ? "#4ade80" : "#f87171",
                                            fontVariantNumeric: "tabular-nums",
                                            fontWeight: 600 }}>
                  {r.delta > 0 ? "+" : ""}{fmt(r.delta)}
                </td>
                <td style={{ ...td, textAlign: "right",
                                            fontVariantNumeric: "tabular-nums" }}>
                  {fmt(r.balance_after)}
                </td>
                <td style={{ ...td, color: "#9aa3af",
                                            maxWidth: 180, overflow: "hidden",
                                            textOverflow: "ellipsis",
                                            whiteSpace: "nowrap" }}
                          title={r.metadata?.note || ""}>
                  {r.metadata?.note || r.metadata?.reason || ""}
                </td>
                <td style={td}>
                  <button onClick={() => reverseRow(r.entry_id)}
                                  data-testid={`admin-points-reverse-${r.entry_id}`}
                                  title="Reverse this entry"
                                  style={{ ...btnGhost, padding: "3px 7px",
                                              fontSize: 11 }}>
                    <RotateCcw size={10} />
                  </button>
                </td>
              </tr>
            ))}
            {!loading && !rows.length && (
              <tr><td colSpan={7} style={{ ...td,
                                              textAlign: "center", padding: 40,
                                              color: "#9aa3af" }}
                                data-testid="admin-points-ledger-empty">
                No ledger entries match these filters.
              </td></tr>
            )}
          </tbody>
        </table>
      </div>

      {cursor && (
        <button onClick={() => reload(true, cursor)}
                        data-testid="admin-points-ledger-load-more"
                        disabled={loading}
                        style={{ ...btnGhost, marginTop: 10,
                                    width: "100%", justifyContent: "center" }}>
          {loading ? <Loader2 size={12} className="spin" /> : "Load more"}
        </button>
      )}
    </section>
  );
}

// ─── Earn Rules Tab ──────────────────────────────────────────────
function EarnRulesTab() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(false);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/points/earn-rules`,
                                                        { withCredentials: true });
      setRules(r.data?.items || []);
    } catch (e) {
      toast.error("Failed to load earn rules");
    }
    setLoading(false);
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const patch = async (rule_id, body) => {
    try {
      const r = await axios.patch(`${API}/admin/points/earn-rules/${rule_id}`,
                                                            body, { withCredentials: true });
      toast.success(`Saved ${rule_id}`);
      // Optimistic merge.
      setRules((rs) => rs.map(x => x.rule_id === rule_id ? r.data : x));
    } catch (e) {
      toast.error("Save failed");
    }
  };

  return (
    <section data-testid="admin-points-earn-rules">
      <div style={{ display: "grid",
                                  gridTemplateColumns: "repeat(auto-fill,minmax(320px,1fr))",
                                  gap: 12 }}>
        {rules.map(r => (
          <RuleCard key={r.rule_id} rule={r}
                              onSave={(body) => patch(r.rule_id, body)} />
        ))}
        {!loading && !rules.length && (
          <div style={{ color: "#9aa3af", padding: 40,
                                      textAlign: "center" }}>
            No earn rules configured.
          </div>
        )}
      </div>
    </section>
  );
}

function RuleCard({ rule, onSave }) {
  const [edit, setEdit] = useState({
    base_points: rule.base_points ?? 0,
    daily_cap_per_user: rule.daily_cap_per_user ?? "",
    weekly_cap_per_user: rule.weekly_cap_per_user ?? "",
    monthly_cap_per_user: rule.monthly_cap_per_user ?? "",
  });
  const [saving, setSaving] = useState(false);
  const dirty = (
    Number(edit.base_points) !== Number(rule.base_points || 0) ||
    String(edit.daily_cap_per_user) !== String(rule.daily_cap_per_user ?? "") ||
    String(edit.weekly_cap_per_user) !== String(rule.weekly_cap_per_user ?? "") ||
    String(edit.monthly_cap_per_user) !== String(rule.monthly_cap_per_user ?? "")
  );

  const save = async () => {
    setSaving(true);
    const body = {
      base_points: Number(edit.base_points) || 0,
      daily_cap_per_user:    edit.daily_cap_per_user    === "" ? null : Number(edit.daily_cap_per_user),
      weekly_cap_per_user:   edit.weekly_cap_per_user  === "" ? null : Number(edit.weekly_cap_per_user),
      monthly_cap_per_user: edit.monthly_cap_per_user === "" ? null : Number(edit.monthly_cap_per_user),
    };
    await onSave(body);
    setSaving(false);
  };
  const toggleEnabled = () => onSave({ enabled: !rule.enabled });

  return (
    <div data-testid={`admin-points-rule-${rule.rule_id}`}
              style={{ background: "#0f0f15",
                          border: "1px solid #1f1f28",
                          borderRadius: 10, padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center",
                                  justifyContent: "space-between", marginBottom: 8 }}>
        <div>
          <div style={{ color: "#fff", fontWeight: 600, fontSize: 13 }}>
            {rule.label}
          </div>
          <div style={{ color: "#666", fontSize: 10,
                                      fontFamily: "monospace" }}>
            {rule.rule_id}
          </div>
        </div>
        <button onClick={toggleEnabled}
                        data-testid={`admin-points-rule-toggle-${rule.rule_id}`}
                        style={{ background: "transparent", border: 0,
                                    cursor: "pointer", color: rule.enabled
                                      ? "#4ade80" : "#666" }}>
          {rule.enabled ? <ToggleRight size={26} /> : <ToggleLeft size={26} />}
        </button>
      </div>
      <div style={{ display: "grid",
                                  gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <Field label="Base"
                      value={edit.base_points}
                      onChange={(v) => setEdit({ ...edit, base_points: v })}
                      testid={`admin-points-rule-base-${rule.rule_id}`} />
        <Field label="Daily cap"
                      placeholder="None"
                      value={edit.daily_cap_per_user}
                      onChange={(v) => setEdit({ ...edit, daily_cap_per_user: v })}
                      testid={`admin-points-rule-daily-${rule.rule_id}`} />
        <Field label="Weekly cap"
                      placeholder="None"
                      value={edit.weekly_cap_per_user}
                      onChange={(v) => setEdit({ ...edit, weekly_cap_per_user: v })}
                      testid={`admin-points-rule-weekly-${rule.rule_id}`} />
        <Field label="Monthly cap"
                      placeholder="None"
                      value={edit.monthly_cap_per_user}
                      onChange={(v) => setEdit({ ...edit, monthly_cap_per_user: v })}
                      testid={`admin-points-rule-monthly-${rule.rule_id}`} />
      </div>
      {dirty && (
        <button onClick={save} disabled={saving}
                        data-testid={`admin-points-rule-save-${rule.rule_id}`}
                        style={{ ...btnPrimary, marginTop: 10,
                                    width: "100%", justifyContent: "center" }}>
          {saving ? <Loader2 size={12} className="spin" /> : "Save"}
        </button>
      )}
    </div>
  );
}

function Field({ label, value, onChange, placeholder, testid }) {
  return (
    <label style={{ display: "block", fontSize: 11,
                                color: "#9aa3af" }}>
      {label}
      <input type="number" min={0}
                    value={value} placeholder={placeholder || ""}
                    onChange={(e) => onChange(e.target.value)}
                    data-testid={testid}
                    style={{ ...inputStyle, marginTop: 3,
                                width: "100%", fontSize: 12 }} />
    </label>
  );
}

// ─── Grant modal ─────────────────────────────────────────────────
function GrantModal({ onClose }) {
  const [user_id, setUid] = useState("");
  const [delta, setDelta] = useState(50);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!user_id.trim() || !Number(delta)) {
      toast.error("Enter user_id and a non-zero delta");
      return;
    }
    setBusy(true);
    try {
      const r = await axios.post(`${API}/admin/points/grant`,
                                                            { user_id: user_id.trim(),
                                                              delta: Number(delta),
                                                              reason: reason.trim() || null },
                                                            { withCredentials: true });
      toast.success(`Granted +${r.data?.delta}.  New balance ${r.data?.balance_after}.`);
      onClose();
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      toast.error(code || "Grant failed");
    }
    setBusy(false);
  };

  return (
    <div data-testid="admin-points-grant-modal"
              style={{
                position: "fixed", inset: 0,
                background: "rgba(0,0,0,0.7)", zIndex: 70,
                display: "flex", alignItems: "center", justifyContent: "center",
              }}
              onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()}
                style={{ background: "#0f0f15",
                            border: "1px solid #1f1f28", borderRadius: 12,
                            padding: 22, width: "min(420px,92vw)" }}>
        <div style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 14 }}>
          <h2 style={{ color: "#fff", margin: 0, fontSize: 16,
                                      display: "inline-flex", alignItems: "center", gap: 8 }}>
            <Sparkles size={14} color="#fbbf24" /> Grant Points
          </h2>
          <button onClick={onClose}
                          data-testid="admin-points-grant-cancel"
                          style={{ background: "transparent", border: 0,
                                      color: "#9aa3af", cursor: "pointer" }}>
            <X size={16} />
          </button>
        </div>
        <div style={{ display: "grid", gap: 10 }}>
          <label style={{ fontSize: 11, color: "#9aa3af" }}>
            Target user_id
            <input type="text" value={user_id}
                          onChange={(e) => setUid(e.target.value)}
                          placeholder="user_xxxxxxxxxxxx"
                          data-testid="admin-points-grant-user"
                          style={{ ...inputStyle, width: "100%",
                                      marginTop: 4 }} />
          </label>
          <label style={{ fontSize: 11, color: "#9aa3af" }}>
            Delta (positive earn, negative debit)
            <input type="number" value={delta}
                          onChange={(e) => setDelta(e.target.value)}
                          data-testid="admin-points-grant-delta"
                          style={{ ...inputStyle, width: "100%",
                                      marginTop: 4 }} />
          </label>
          <label style={{ fontSize: 11, color: "#9aa3af" }}>
            Reason
            <input type="text" value={reason}
                          onChange={(e) => setReason(e.target.value)}
                          placeholder="e.g. Twitter contest winner"
                          data-testid="admin-points-grant-reason"
                          style={{ ...inputStyle, width: "100%",
                                      marginTop: 4 }} />
          </label>
        </div>
        <div style={{ display: "flex", justifyContent: "flex-end",
                                  gap: 8, marginTop: 14 }}>
          <button onClick={onClose}
                          style={{ ...btnGhost, padding: "8px 14px" }}>Cancel</button>
          <button onClick={submit} disabled={busy}
                          data-testid="admin-points-grant-submit"
                          style={{ ...btnPrimary, padding: "8px 14px" }}>
            {busy ? <Loader2 size={12} className="spin" /> : "Grant"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Styles ──────────────────────────────────────────────────────
const inputStyle = {
  background: "#0b0b0f", border: "1px solid #25252f",
  borderRadius: 6, padding: "7px 10px", color: "#fff",
  fontSize: 12, outline: "none",
};
const th = { textAlign: "left", padding: "10px 12px",
                          color: "#9aa3af", textTransform: "uppercase",
                          fontSize: 10, letterSpacing: 1, fontWeight: 600 };
const td = { padding: "9px 12px", color: "#cbd5e1" };
const btnPrimary = {
  display: "inline-flex", alignItems: "center", gap: 6,
  background: "#fbbf24", color: "#0b0b0b", border: 0,
  borderRadius: 8, padding: "7px 12px", fontSize: 12,
  fontWeight: 600, cursor: "pointer",
};
const btnGhost = {
  display: "inline-flex", alignItems: "center", gap: 6,
  background: "transparent", color: "#cbd5e1",
  border: "1px solid #25252f", borderRadius: 8,
  padding: "6px 12px", fontSize: 12, fontWeight: 500,
  cursor: "pointer",
};
