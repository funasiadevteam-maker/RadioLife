// Phase SC.3 — Admin Commissions page (Rules / Overrides / Audit).
// Legacy dark shell, admin-only.
import React, { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TXN_TYPES = [
  "payment", "prepaid_meal", "gift_card", "paid_coupon",
  "event_ticket", "appointment_deposit",
  "station_promotion", "podcast_sponsorship",
];

const CATEGORIES = [
  "restaurant", "cafe", "grocery", "retail", "salon_spa",
  "medical_dental", "fitness", "entertainment", "movie_theater",
  "event_promoter", "concert_promoter", "club_lounge",
  "radio_station", "podcast_creator", "service_business", "other",
];


export default function AdminCommissions() {
  const [tab, setTab] = useState("rules");

  return (
    <div style={s.page} data-testid="admin-commissions-page">
      <div style={s.header}>
        <div>
          <div style={s.eyebrow}>Phase SC.3</div>
          <h1 style={s.h1}>Commissions</h1>
          <div style={s.sub}>
            Configure category × transaction-type rates.  Add merchant-specific
            overrides.  Audit every fee calculation.
          </div>
        </div>
      </div>

      <div style={s.tabs} data-testid="admin-commissions-tabs">
        <TabBtn active={tab === "rules"} onClick={() => setTab("rules")}
                    testId="admin-commissions-tab-rules">Rules</TabBtn>
        <TabBtn active={tab === "overrides"} onClick={() => setTab("overrides")}
                    testId="admin-commissions-tab-overrides">Overrides</TabBtn>
        <TabBtn active={tab === "audit"} onClick={() => setTab("audit")}
                    testId="admin-commissions-tab-audit">Audit Log</TabBtn>
      </div>

      <div style={{ marginTop: 20 }}>
        {tab === "rules"      && <RulesPane />}
        {tab === "overrides" && <OverridesPane />}
        {tab === "audit"        && <AuditPane />}
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


// ─── Rules Pane ───────────────────────────────────────────────────
function RulesPane() {
  const [rules, setRules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);   // rule or {} for new
  const [total, setTotal] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await axios.get(
        `${API}/admin/commission-rules?limit=500`,
        { withCredentials: true });
      setRules(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const deactivate = async (rule_id) => {
    try {
      await axios.post(`${API}/admin/commission-rules/${rule_id}/deactivate`,
                                    {}, { withCredentials: true });
      toast.success("Rule deactivated");
      await load();
    } catch (e) {
      toast.error(`Deactivate failed: ${e?.response?.data?.detail || e.message}`);
    }
  };

  return (
    <div data-testid="admin-commissions-rules-pane">
      <div style={s.toolbar}>
        <div style={{ color: "#94a3b8", fontSize: 13 }}>
          {loading ? "Loading…" : `${total} rules total`}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" onClick={load} disabled={loading}
                      style={s.btnGhost}
                      data-testid="admin-commissions-rules-reload">
            {loading ? "…" : "Reload"}
          </button>
          <button type="button" onClick={() => setEditing({})}
                      style={s.btnPrimary}
                      data-testid="admin-commissions-new-rule">
            + New Rule
          </button>
        </div>
      </div>

      <div style={s.tableWrap}>
        <table style={s.table} data-testid="admin-commissions-rules-table">
          <thead>
            <tr>
              <th style={s.th}>Name</th>
              <th style={s.th}>Category</th>
              <th style={s.th}>Txn Type</th>
              <th style={s.th}>%</th>
              <th style={s.th}>Fixed¢</th>
              <th style={s.th}>Min¢/Max¢</th>
              <th style={s.th}>Priority</th>
              <th style={s.th}>Active</th>
              <th style={s.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => (
              <tr key={r.rule_id}
                        style={{ ...s.tr,
                                        opacity: r.active ? 1 : 0.55,
                                        background: r.business_category === "*"
                                          ? "rgba(255,193,7,0.06)" : "transparent" }}
                        data-testid={`admin-commissions-rule-row-${r.rule_id}`}>
                <td style={s.td}>
                  <div style={{ fontWeight: 600 }}>{r.name}</div>
                  <div style={s.metaSm}>{r.rule_id}</div>
                </td>
                <td style={s.td}><code style={s.code}>{r.business_category}</code></td>
                <td style={s.td}><code style={s.code}>{r.transaction_type}</code></td>
                <td style={s.td}>
                  <span style={{ fontWeight: 700, color: "#00d4ff" }}
                              data-testid={`admin-commissions-rule-pct-${r.rule_id}`}>
                    {r.commission_percent.toFixed(2)}%
                  </span>
                </td>
                <td style={s.td}>{r.fixed_fee_cents || "—"}</td>
                <td style={s.td}>
                  {(r.min_fee_cents || 0)} / {r.max_fee_cents == null ? "—" : r.max_fee_cents}
                </td>
                <td style={s.td}>{r.priority}</td>
                <td style={s.td}>
                  <span style={{ ...s.pill,
                                          background: r.active ? "#10b98122" : "#64748b22",
                                          color: r.active ? "#10b981" : "#94a3b8" }}>
                    {r.active ? "Active" : "Inactive"}
                  </span>
                  {!r.deletable && (
                    <span style={{ ...s.pill, marginLeft: 4,
                                            background: "#f59e0b22", color: "#f59e0b",
                                            fontSize: 10 }}>Fallback</span>
                  )}
                </td>
                <td style={{ ...s.td, whiteSpace: "nowrap" }}>
                  <button type="button" onClick={() => setEditing(r)}
                                style={s.btnGhost}
                                data-testid={`admin-commissions-rule-edit-${r.rule_id}`}>
                    Edit
                  </button>
                  {r.active && r.deletable && (
                    <button type="button" onClick={() => deactivate(r.rule_id)}
                                  style={{ ...s.btnGhost, marginLeft: 4,
                                                  color: "#ef4444", borderColor: "#ef4444" }}
                                  data-testid={`admin-commissions-rule-deactivate-${r.rule_id}`}>
                      Deactivate
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {editing !== null && (
        <RuleModal rule={editing}
                              onClose={() => setEditing(null)}
                              onSaved={async () => { setEditing(null); await load(); }} />
      )}
    </div>
  );
}


function RuleModal({ rule, onClose, onSaved }) {
  const isNew = !rule.rule_id;
  const [f, setF] = useState({
    name:                                        rule.name ?? "",
    business_category:              rule.business_category ?? "restaurant",
    transaction_type:                  rule.transaction_type ?? "payment",
    commission_percent:              rule.commission_percent ?? 5.0,
    fixed_fee_cents:                    rule.fixed_fee_cents ?? 0,
    min_fee_cents:                          rule.min_fee_cents ?? 0,
    max_fee_cents:                          rule.max_fee_cents ?? "",
    stripe_fee_responsibility:  rule.stripe_fee_responsibility ?? "merchant",
    market:                                    rule.market ?? "",
    campaign_type:                        rule.campaign_type ?? "",
    priority:                                  rule.priority ?? 0,
    notes:                                        rule.notes ?? "",
    active:                                    rule.active ?? true,
  });
  const [busy, setBusy] = useState(false);

  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  const submit = async () => {
    setBusy(true);
    try {
      const body = {
        name:                                        f.name,
        commission_percent:              parseFloat(f.commission_percent),
        fixed_fee_cents:                    parseInt(f.fixed_fee_cents || 0),
        min_fee_cents:                          parseInt(f.min_fee_cents || 0),
        max_fee_cents:                          f.max_fee_cents === "" ? null : parseInt(f.max_fee_cents),
        stripe_fee_responsibility:  f.stripe_fee_responsibility,
        market:                                    (f.market || "").trim() || null,
        campaign_type:                        (f.campaign_type || "").trim() || null,
        priority:                                  parseInt(f.priority || 0),
        notes:                                        f.notes,
      };
      if (isNew) {
        await axios.post(`${API}/admin/commission-rules`,
          { ...body,
              business_category: f.business_category,
              transaction_type: f.transaction_type },
          { withCredentials: true });
        toast.success("Rule created");
      } else {
        await axios.put(`${API}/admin/commission-rules/${rule.rule_id}`,
          { ...body, active: !!f.active },
          { withCredentials: true });
        toast.success("Rule updated");
      }
      onSaved();
    } catch (e) {
      toast.error(`Save failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <div style={s.modalBg} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={s.modal}
                data-testid="admin-commissions-rule-modal">
        <h3 style={s.modalTitle}>{isNew ? "New Rule" : "Edit Rule"}</h3>

        <div style={s.grid2}>
          <Field label="Name" testId="admin-commissions-rule-name">
            <input style={s.input} value={f.name}
                        onChange={(e) => set("name", e.target.value)}
                        data-testid="admin-commissions-rule-name-input" />
          </Field>
          <Field label="Priority">
            <input style={s.input} type="number" value={f.priority}
                        onChange={(e) => set("priority", e.target.value)}
                        data-testid="admin-commissions-rule-priority-input" />
          </Field>
          <Field label="Business Category">
            <select style={s.input} value={f.business_category}
                          disabled={!isNew}
                          onChange={(e) => set("business_category", e.target.value)}
                          data-testid="admin-commissions-rule-category-select">
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
              <option value="*">* (fallback)</option>
            </select>
          </Field>
          <Field label="Transaction Type">
            <select style={s.input} value={f.transaction_type}
                          disabled={!isNew}
                          onChange={(e) => set("transaction_type", e.target.value)}
                          data-testid="admin-commissions-rule-txn-select">
              {TXN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
              <option value="*">* (fallback)</option>
            </select>
          </Field>
          <Field label="Commission %" testId="admin-commissions-rule-pct-field">
            <input style={s.input} type="number" step="0.01"
                        min={0} max={100}
                        value={f.commission_percent}
                        onChange={(e) => set("commission_percent", e.target.value)}
                        data-testid="admin-commissions-rule-pct-input"/>
          </Field>
          <Field label="Fixed Fee (cents)">
            <input style={s.input} type="number" min={0}
                        value={f.fixed_fee_cents}
                        onChange={(e) => set("fixed_fee_cents", e.target.value)}/>
          </Field>
          <Field label="Min Fee (cents)">
            <input style={s.input} type="number" min={0}
                        value={f.min_fee_cents}
                        onChange={(e) => set("min_fee_cents", e.target.value)}/>
          </Field>
          <Field label="Max Fee (cents, blank=none)">
            <input style={s.input} type="number" min={0}
                        value={f.max_fee_cents}
                        onChange={(e) => set("max_fee_cents", e.target.value)}/>
          </Field>
          <Field label="Stripe Fee Responsibility">
            <select style={s.input} value={f.stripe_fee_responsibility}
                          onChange={(e) => set("stripe_fee_responsibility", e.target.value)}>
              <option value="merchant">Merchant absorbs</option>
              <option value="platform">Platform absorbs</option>
            </select>
          </Field>
          <Field label="Market (ISO-2, blank=global)">
            <input style={s.input} value={f.market} maxLength={2}
                        placeholder="AE / US / …"
                        onChange={(e) => set("market", e.target.value.toUpperCase())}/>
          </Field>
        </div>

        <Field label="Notes">
          <textarea style={{ ...s.input, minHeight: 60, resize: "vertical" }}
                            value={f.notes}
                            onChange={(e) => set("notes", e.target.value)}/>
        </Field>

        {!isNew && (
          <label style={{ display: "flex", gap: 6, alignItems: "center",
                                      marginTop: 8, color: "#cbd5e1", fontSize: 13 }}>
            <input type="checkbox" checked={!!f.active}
                        onChange={(e) => set("active", e.target.checked)}
                        data-testid="admin-commissions-rule-active-toggle"/>
            Active
          </label>
        )}

        <div style={s.modalBtns}>
          <button type="button" onClick={onClose} style={s.btnGhost}>Cancel</button>
          <button type="button" onClick={submit} disabled={busy}
                        style={s.btnPrimary}
                        data-testid="admin-commissions-rule-save-btn">
            {busy ? "Saving…" : (isNew ? "Create" : "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}


// ─── Overrides Pane ───────────────────────────────────────────────
function OverridesPane() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [statusFilter, setStatusFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = statusFilter ? `?status=${statusFilter}&limit=500` : "?limit=500";
      const { data } = await axios.get(`${API}/admin/commission-overrides${q}`,
                                                                { withCredentials: true });
      setItems(data.items || []); setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  }, [statusFilter]);

  useEffect(() => { load(); }, [load]);

  const cancel = async (oid) => {
    try {
      await axios.put(`${API}/admin/commission-overrides/${oid}`,
        { status: "cancelled" }, { withCredentials: true });
      toast.success("Override cancelled");
      await load();
    } catch (e) {
      toast.error(`Cancel failed: ${e?.response?.data?.detail || e.message}`);
    }
  };

  return (
    <div data-testid="admin-commissions-overrides-pane">
      <div style={s.toolbar}>
        <div style={{ color: "#94a3b8", fontSize: 13 }}>
          {loading ? "Loading…" : `${total} override${total === 1 ? "" : "s"}`}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <select value={statusFilter}
                      onChange={(e) => setStatusFilter(e.target.value)}
                      style={s.select}
                      data-testid="admin-commissions-overrides-status-filter">
            <option value="">All statuses</option>
            <option value="active">Active</option>
            <option value="pending">Pending</option>
            <option value="expired">Expired</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <button type="button" onClick={load} disabled={loading}
                      style={s.btnGhost}>{loading ? "…" : "Reload"}</button>
          <button type="button" onClick={() => setEditing({})}
                      style={s.btnPrimary}
                      data-testid="admin-commissions-new-override">
            + New Override
          </button>
        </div>
      </div>

      <div style={s.tableWrap}>
        <table style={s.table} data-testid="admin-commissions-overrides-table">
          <thead>
            <tr>
              <th style={s.th}>Merchant</th>
              <th style={s.th}>Txn Type</th>
              <th style={s.th}>Custom %</th>
              <th style={s.th}>Custom Fixed¢</th>
              <th style={s.th}>Effective</th>
              <th style={s.th}>Status</th>
              <th style={s.th}>Approved By</th>
              <th style={s.th}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.map((o) => (
              <tr key={o.override_id} style={s.tr}
                        data-testid={`admin-commissions-override-row-${o.override_id}`}>
                <td style={s.td}>
                  <div style={{ fontWeight: 600 }}>{o.merchant_name || "—"}</div>
                  <div style={s.metaSm}>{o.merchant_id}</div>
                </td>
                <td style={s.td}>
                  <code style={s.code}>{o.transaction_type || "* (all)"}</code>
                </td>
                <td style={s.td}>
                  {o.custom_percent != null ? (
                    <span style={{ fontWeight: 700, color: "#00d4ff" }}>
                      {parseFloat(o.custom_percent).toFixed(2)}%
                    </span>
                  ) : "—"}
                </td>
                <td style={s.td}>{o.custom_fixed_fee_cents ?? "—"}</td>
                <td style={s.td}>
                  <div style={s.metaSm}>{o.effective_start?.slice(0,10)}</div>
                  <div style={s.metaSm}>→ {o.effective_end?.slice(0,10) || "∞"}</div>
                </td>
                <td style={s.td}>
                  <span style={{ ...s.pill, ...toneForStatus(o.status) }}>
                    {o.status}
                  </span>
                </td>
                <td style={s.td}>{o.approved_by || "—"}</td>
                <td style={{ ...s.td, whiteSpace: "nowrap" }}>
                  <button type="button" onClick={() => setEditing(o)}
                                style={s.btnGhost}
                                data-testid={`admin-commissions-override-edit-${o.override_id}`}>
                    Edit
                  </button>
                  {o.status === "active" && (
                    <button type="button" onClick={() => cancel(o.override_id)}
                                  style={{ ...s.btnGhost, marginLeft: 4,
                                                  color: "#ef4444", borderColor: "#ef4444" }}
                                  data-testid={`admin-commissions-override-cancel-${o.override_id}`}>
                      Cancel
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!loading && items.length === 0 && (
          <div style={{ padding: 30, color: "#94a3b8", textAlign: "center" }}
                    data-testid="admin-commissions-overrides-empty">
            No overrides configured.
          </div>
        )}
      </div>

      {editing !== null && (
        <OverrideModal ov={editing}
                                    onClose={() => setEditing(null)}
                                    onSaved={async () => { setEditing(null); await load(); }} />
      )}
    </div>
  );
}


function OverrideModal({ ov, onClose, onSaved }) {
  const isNew = !ov.override_id;
  const [f, setF] = useState({
    merchant_id:                      ov.merchant_id ?? "",
    transaction_type:            ov.transaction_type ?? "",
    custom_percent:                  ov.custom_percent ?? "",
    custom_fixed_fee_cents:  ov.custom_fixed_fee_cents ?? "",
    approval_notes:              ov.approval_notes ?? "",
    effective_end:                    ov.effective_end?.slice(0, 10) ?? "",
    status:                                ov.status ?? "active",
  });
  const [busy, setBusy] = useState(false);
  const [merchantSearch, setMerchantSearch] = useState("");
  const [searchResults, setSearchResults] = useState([]);

  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

  const doSearch = async (q) => {
    if (!q || q.length < 2) { setSearchResults([]); return; }
    try {
      const { data } = await axios.get(
        `${API}/admin/merchants?search=${encodeURIComponent(q)}&limit=8`,
        { withCredentials: true });
      setSearchResults(data.items || []);
    } catch { setSearchResults([]); }
  };

  const submit = async () => {
    setBusy(true);
    try {
      const body = {
        merchant_id:                        f.merchant_id,
        transaction_type:              (f.transaction_type || "").trim() || null,
        custom_percent:                  f.custom_percent === "" ? null : parseFloat(f.custom_percent),
        custom_fixed_fee_cents:  f.custom_fixed_fee_cents === "" ? null : parseInt(f.custom_fixed_fee_cents),
        approval_notes:              f.approval_notes || null,
        effective_end:                    f.effective_end ? new Date(f.effective_end).toISOString() : null,
      };
      if (isNew) {
        await axios.post(`${API}/admin/commission-overrides`, body,
                                        { withCredentials: true });
        toast.success("Override created");
      } else {
        await axios.put(`${API}/admin/commission-overrides/${ov.override_id}`,
          { ...body, status: f.status }, { withCredentials: true });
        toast.success("Override updated");
      }
      onSaved();
    } catch (e) {
      toast.error(`Save failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setBusy(false); }
  };

  return (
    <div style={s.modalBg} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={s.modal}
                data-testid="admin-commissions-override-modal">
        <h3 style={s.modalTitle}>{isNew ? "New Override" : "Edit Override"}</h3>

        {isNew && (
          <>
            <Field label="Find Merchant" testId="admin-commissions-override-search-field">
              <input style={s.input} value={merchantSearch}
                          placeholder="Search by name / email / id…"
                          onChange={(e) => { setMerchantSearch(e.target.value); doSearch(e.target.value); }}
                          data-testid="admin-commissions-override-search-input"/>
            </Field>
            {searchResults.length > 0 && (
              <div style={{ background: "#0d0d18",
                                        border: "1px solid #334155",
                                        borderRadius: 8, marginTop: -4, marginBottom: 12,
                                        maxHeight: 200, overflowY: "auto" }}>
                {searchResults.map((r) => (
                  <button key={r.merchant_id}
                                type="button"
                                onClick={() => { set("merchant_id", r.merchant_id); setSearchResults([]); setMerchantSearch(r.name); }}
                                data-testid={`admin-commissions-override-pick-${r.merchant_id}`}
                                style={{
                                  display: "block", width: "100%", textAlign: "left",
                                  padding: "8px 12px", border: 0, background: "transparent",
                                  color: "#e2e8f0", cursor: "pointer", fontSize: 12,
                                  borderBottom: "1px solid #1e293b",
                                }}>
                    <span style={{ fontWeight: 600 }}>{r.name}</span>{" "}
                    <span style={{ color: "#64748b" }}>· {r.merchant_id}</span>
                    <div style={s.metaSm}>{r.owner_email} · {r.merchant_status}</div>
                  </button>
                ))}
              </div>
            )}
          </>
        )}

        <Field label={isNew ? "Selected Merchant ID" : "Merchant ID"}>
          <input style={{ ...s.input, opacity: isNew ? 0.75 : 1 }}
                      value={f.merchant_id} disabled={!isNew}
                      onChange={(e) => set("merchant_id", e.target.value)}
                      data-testid="admin-commissions-override-mid-input"/>
        </Field>

        <div style={s.grid2}>
          <Field label="Transaction Type (blank = all)">
            <select style={s.input} value={f.transaction_type}
                          onChange={(e) => set("transaction_type", e.target.value)}
                          data-testid="admin-commissions-override-txn-select">
              <option value="">All transaction types</option>
              {TXN_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
          <Field label="Effective End (blank = never)">
            <input style={s.input} type="date"
                        value={f.effective_end}
                        onChange={(e) => set("effective_end", e.target.value)}/>
          </Field>
          <Field label="Custom % (blank = keep default %)">
            <input style={s.input} type="number" step="0.01" min={0} max={100}
                        value={f.custom_percent}
                        onChange={(e) => set("custom_percent", e.target.value)}
                        data-testid="admin-commissions-override-pct-input"/>
          </Field>
          <Field label="Custom Fixed Fee ¢ (blank = keep default)">
            <input style={s.input} type="number" min={0}
                        value={f.custom_fixed_fee_cents}
                        onChange={(e) => set("custom_fixed_fee_cents", e.target.value)}/>
          </Field>
        </div>

        <Field label="Approval Notes (visible to admins only)">
          <textarea style={{ ...s.input, minHeight: 60, resize: "vertical" }}
                            value={f.approval_notes}
                            onChange={(e) => set("approval_notes", e.target.value)}
                            data-testid="admin-commissions-override-notes-input"/>
        </Field>

        {!isNew && (
          <Field label="Status">
            <select style={s.input} value={f.status}
                          onChange={(e) => set("status", e.target.value)}
                          data-testid="admin-commissions-override-status-select">
              <option value="active">Active</option>
              <option value="pending">Pending</option>
              <option value="expired">Expired</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </Field>
        )}

        <div style={s.modalBtns}>
          <button type="button" onClick={onClose} style={s.btnGhost}>Cancel</button>
          <button type="button" onClick={submit} disabled={busy || !f.merchant_id}
                        style={s.btnPrimary}
                        data-testid="admin-commissions-override-save-btn">
            {busy ? "Saving…" : (isNew ? "Create" : "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}


// ─── Audit Pane ───────────────────────────────────────────────────
function AuditPane() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [merchantFilter, setMerchantFilter] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const q = merchantFilter
        ? `?merchant_id=${encodeURIComponent(merchantFilter)}&limit=200`
        : "?limit=200";
      const { data } = await axios.get(`${API}/admin/commission-audit${q}`,
                                                                { withCredentials: true });
      setItems(data.items || []); setTotal(data.total || 0);
    } catch (e) {
      toast.error(`Load failed: ${e?.response?.data?.detail || e.message}`);
    } finally { setLoading(false); }
  }, [merchantFilter]);

  useEffect(() => { load(); }, [load]);

  return (
    <div data-testid="admin-commissions-audit-pane">
      <div style={s.toolbar}>
        <div style={{ color: "#94a3b8", fontSize: 13 }}>
          {loading ? "Loading…" : `${total} entries · showing last ${items.length}`}
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <input placeholder="Filter by merchant_id" value={merchantFilter}
                      onChange={(e) => setMerchantFilter(e.target.value)}
                      style={{ ...s.input, height: 34, width: 260, padding: "6px 10px" }}
                      data-testid="admin-commissions-audit-filter"/>
          <button type="button" onClick={load} disabled={loading}
                      style={s.btnPrimary}>{loading ? "…" : "Reload"}</button>
        </div>
      </div>

      <div style={s.tableWrap}>
        <table style={s.table} data-testid="admin-commissions-audit-table">
          <thead>
            <tr>
              <th style={s.th}>Computed At</th>
              <th style={s.th}>Merchant</th>
              <th style={s.th}>Category</th>
              <th style={s.th}>Txn Type</th>
              <th style={s.th}>Amount ¢</th>
              <th style={s.th}>Fee ¢</th>
              <th style={s.th}>Source</th>
              <th style={s.th}>Rule / Override</th>
            </tr>
          </thead>
          <tbody>
            {items.map((a) => {
              const src = a.resolved_override_id ? "override"
                                : (a.resolved_rule_id === "cr_fallback_global"
                                    ? "fallback" : "rule");
              return (
                <tr key={a.audit_id} style={s.tr}
                          data-testid={`admin-commissions-audit-row-${a.audit_id}`}>
                  <td style={s.td}>{a.computed_at?.slice(0, 19)?.replace("T", " ")}</td>
                  <td style={s.td}><code style={s.code}>{a.merchant_id || "—"}</code></td>
                  <td style={s.td}><code style={s.code}>{a.category}</code></td>
                  <td style={s.td}><code style={s.code}>{a.transaction_type}</code></td>
                  <td style={s.td}>{a.amount_cents}</td>
                  <td style={s.td} data-testid={`admin-commissions-audit-fee-${a.audit_id}`}>
                    <span style={{ color: "#00d4ff", fontWeight: 700 }}>
                      {a.computed_commission_cents}
                    </span>
                  </td>
                  <td style={s.td}>
                    <span style={{ ...s.pill, ...toneForSource(src) }}>{src}</span>
                  </td>
                  <td style={s.td}>
                    <code style={s.code}>
                      {a.resolved_override_id || a.resolved_rule_id || "—"}
                    </code>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!loading && items.length === 0 && (
          <div style={{ padding: 30, color: "#94a3b8", textAlign: "center" }}
                    data-testid="admin-commissions-audit-empty">
            No audit entries.  The log grows as real charges use the resolver
            (SC.5).
          </div>
        )}
      </div>
    </div>
  );
}


// ─── Bits ─────────────────────────────────────────────────────────
function Field({ label, children, testId }) {
  return (
    <div style={{ marginBottom: 8 }} data-testid={testId}>
      <div style={s.label}>{label}</div>
      {children}
    </div>
  );
}


function toneForStatus(status) {
  switch (status) {
    case "active":        return { background: "#10b98122", color: "#10b981" };
    case "pending":      return { background: "#3b82f622", color: "#3b82f6" };
    case "expired":      return { background: "#64748b22", color: "#94a3b8" };
    case "cancelled":  return { background: "#ef444422", color: "#ef4444" };
    default:                  return { background: "#64748b22", color: "#94a3b8" };
  }
}


function toneForSource(src) {
  switch (src) {
    case "override":  return { background: "#a855f722", color: "#a855f7" };
    case "rule":          return { background: "#00d4ff22", color: "#00d4ff" };
    case "fallback":  return { background: "#f59e0b22", color: "#f59e0b" };
    default:                return { background: "#64748b22", color: "#94a3b8" };
  }
}


const s = {
  page: { minHeight: "100vh", background: "#0d0d18", color: "#e2e8f0",
                padding: "24px 28px 60px 244px",
                fontFamily: "ui-sans-serif, system-ui, sans-serif" },
  header: { marginBottom: 20 },
  eyebrow: { fontSize: 11, letterSpacing: 2, textTransform: "uppercase",
                        color: "#00d4ff", fontWeight: 700 },
  h1: { fontSize: 26, fontWeight: 800, margin: "4px 0 6px",
              letterSpacing: "-0.02em" },
  sub: { color: "#94a3b8", fontSize: 13 },
  tabs: { display: "flex", borderBottom: "1px solid #2a2a3a",
                    paddingBottom: 10, marginTop: 10 },
  toolbar: { display: "flex", justifyContent: "space-between",
                          alignItems: "center", gap: 8, marginBottom: 12 },
  tableWrap: { background: "#1e1e2e", borderRadius: 12,
                              border: "1px solid #2a2a3a", overflow: "auto" },
  table: { width: "100%", borderCollapse: "separate", borderSpacing: 0,
                    fontSize: 12 },
  th: { textAlign: "left", padding: "11px 13px", background: "#151521",
              color: "#94a3b8", fontSize: 10, textTransform: "uppercase",
              letterSpacing: 1, fontWeight: 700,
              borderBottom: "1px solid #2a2a3a" },
  tr: { borderBottom: "1px solid #2a2a3a" },
  td: { padding: "10px 13px", borderBottom: "1px solid #2a2a3a",
              verticalAlign: "top" },
  metaSm: { fontSize: 10, color: "#64748b", marginTop: 2 },
  btnPrimary: { background: "linear-gradient(135deg, #00d4ff, #6366f1)",
                          color: "#0d0d18", border: 0, borderRadius: 8,
                          padding: "8px 14px", fontSize: 12, fontWeight: 700,
                          cursor: "pointer", textTransform: "uppercase",
                          letterSpacing: 0.5 },
  btnGhost: { background: "transparent", color: "#94a3b8",
                          border: "1px solid #334155", borderRadius: 8,
                          padding: "7px 13px", fontSize: 11, fontWeight: 600,
                          cursor: "pointer", textTransform: "uppercase",
                          letterSpacing: 0.5 },
  pill: { display: "inline-block", padding: "3px 10px", borderRadius: 999,
                fontSize: 10, fontWeight: 700, letterSpacing: 0.5,
                textTransform: "uppercase" },
  code: { background: "#0d0d18", padding: "2px 6px", borderRadius: 4,
                  fontFamily: "ui-monospace, monospace", fontSize: 11,
                  color: "#94a3b8" },
  select: { background: "#0d0d18", color: "#e2e8f0",
                      border: "1px solid #334155", borderRadius: 8,
                      padding: "7px 10px", fontSize: 12, height: 34 },
  modalBg: { position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
                        zIndex: 200, display: "flex", alignItems: "center",
                        justifyContent: "center", padding: 20 },
  modal: { background: "#1e1e2e", border: "1px solid #2a2a3a",
                    borderRadius: 12, padding: 24,
                    width: "min(640px, 100%)", maxHeight: "90vh",
                    overflowY: "auto" },
  modalTitle: { margin: "0 0 16px", fontSize: 20, fontWeight: 800,
                            color: "#fff" },
  modalBtns: { display: "flex", justifyContent: "flex-end", gap: 8,
                            marginTop: 18 },
  grid2: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10,
                    marginBottom: 8 },
  input: { background: "#0d0d18", border: "1px solid #334155",
                    color: "#e2e8f0", borderRadius: 8, padding: "8px 10px",
                    width: "100%", fontSize: 12, height: 34, outline: "none",
                    boxSizing: "border-box" },
  label: { fontSize: 10, color: "#64748b", textTransform: "uppercase",
                    letterSpacing: 1.5, fontWeight: 700, marginBottom: 4 },
};
