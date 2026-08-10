// Marketplace Phase A — Admin console (BigPoints economics, categories,
// commission rules, business approvals).  Legacy dark shell, admin-only.
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api/admin/marketplace`;
const CFG = { withCredentials: true };

export default function AdminMarketplacePhaseA() {
  const [tab, setTab] = useState("economics");
  return (
    <div style={s.page} data-testid="admin-marketplace-page">
      <div style={s.header}>
        <div style={s.eyebrow}>Super Marketplace · Phase A</div>
        <h1 style={s.h1}>Marketplace</h1>
        <div style={s.sub}>BigPoints economics ($0.03/point default), categories,
          commission rules, and business approvals.</div>
      </div>
      <div style={s.tabs}>
        {[["economics", "BigPoints Economics"], ["categories", "Categories"],
          ["commission", "Commission Rules"], ["loyalty", "Loyalty Tiers"], ["approvals", "Approvals"]].map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`mkt-tab-${k}`}
            style={{ ...s.tabBtn, ...(tab === k ? s.tabActive : {}) }}>{label}</button>
        ))}
      </div>
      {tab === "economics" && <Economics />}
      {tab === "categories" && <Categories />}
      {tab === "commission" && <Commission />}
      {tab === "loyalty" && <Loyalty />}
      {tab === "approvals" && <Approvals />}
    </div>
  );
}

function Economics() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ scope: "global", cost_per_point_cents: 3, category: "", market: "", merchant_id: "" });
  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/bigpoint-rates`, CFG); setItems(data.items || []); }
    catch { toast.error("Failed to load rates"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    try {
      await axios.post(`${API}/bigpoint-rates`, {
        scope: form.scope, cost_per_point_cents: Number(form.cost_per_point_cents),
        category: form.category || null, market: form.market || null,
        merchant_id: form.merchant_id || null, active: true }, CFG);
      toast.success("Rate added"); load();
    } catch { toast.error("Failed"); }
  };
  return (
    <div data-testid="mkt-economics">
      <div style={s.card}>
        <div style={s.cardTitle}>Add issuance-cost rate ($ per BigPoint)</div>
        <div style={s.row}>
          <select style={s.input} value={form.scope} data-testid="rate-scope"
            onChange={(e) => setForm({ ...form, scope: e.target.value })}>
            <option value="global">Global</option><option value="market">Market</option>
            <option value="category">Category</option><option value="merchant">Merchant</option>
          </select>
          <input style={s.input} type="number" step="0.01" placeholder="cents/point (e.g. 3)"
            data-testid="rate-cost" value={form.cost_per_point_cents}
            onChange={(e) => setForm({ ...form, cost_per_point_cents: e.target.value })} />
          <input style={s.input} placeholder="category (opt)" value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })} />
          <input style={s.input} placeholder="market (opt)" value={form.market}
            onChange={(e) => setForm({ ...form, market: e.target.value })} />
          <button style={s.primary} onClick={add} data-testid="rate-add-btn">Add</button>
        </div>
      </div>
      {items.map((r) => (
        <div key={r.rate_id} style={s.listRow} data-testid={`rate-${r.rate_id}`}>
          <b>${(r.cost_per_point_cents / 100).toFixed(3)}</b> /point · {r.scope}
          {r.category ? ` · ${r.category}` : ""}{r.market ? ` · ${r.market}` : ""}
          <span style={{ ...s.badge, background: r.active ? "#134e2a" : "#4b1113" }}>
            {r.active ? "active" : "inactive"}</span>
        </div>
      ))}
    </div>
  );
}

function Categories() {
  const [items, setItems] = useState([]);
  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/categories`, CFG); setItems(data.items || []); }
    catch { toast.error("Failed to load categories"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const save = async (c, patch) => {
    try { await axios.patch(`${API}/categories/${c.key}`, { ...c, ...patch }, CFG); toast.success("Saved"); load(); }
    catch { toast.error("Failed"); }
  };
  return (
    <div data-testid="mkt-categories">
      {items.map((c) => (
        <div key={c.key} style={s.listRow} data-testid={`cat-${c.key}`}>
          <div style={{ flex: 1 }}><b>{c.name}</b> <span style={s.dim}>({c.key})</span></div>
          <label style={s.inline}>Comm %
            <input style={s.miniInput} type="number" defaultValue={c.commission_pct}
              data-testid={`cat-comm-${c.key}`}
              onBlur={(e) => save(c, { commission_pct: Number(e.target.value) })} /></label>
          <label style={s.inline}>Min pts
            <input style={s.miniInput} type="number" defaultValue={c.min_bigpoints}
              onBlur={(e) => save(c, { min_bigpoints: Number(e.target.value) })} /></label>
          <button style={c.active ? s.ghost : s.primary}
            data-testid={`cat-toggle-${c.key}`}
            onClick={() => save(c, { active: !c.active })}>{c.active ? "Active" : "Inactive"}</button>
        </div>
      ))}
    </div>
  );
}

function Commission() {
  const [items, setItems] = useState([]);
  const [form, setForm] = useState({ scope: "category", commission_pct: 15, category: "", market: "", merchant_id: "", fixed_fee_cents: 0, min_fee_cents: 0, max_fee_cents: "" });
  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/commission-rules`, CFG); setItems(data.items || []); }
    catch { toast.error("Failed to load rules"); }
  }, []);
  useEffect(() => { load(); }, [load]);
  const add = async () => {
    try {
      await axios.post(`${API}/commission-rules`, {
        scope: form.scope, commission_pct: Number(form.commission_pct),
        fixed_fee_cents: Number(form.fixed_fee_cents), min_fee_cents: Number(form.min_fee_cents),
        max_fee_cents: form.max_fee_cents === "" ? null : Number(form.max_fee_cents),
        category: form.category || null, market: form.market || null,
        merchant_id: form.merchant_id || null, active: true }, CFG);
      toast.success("Rule added"); load();
    } catch { toast.error("Failed"); }
  };
  return (
    <div data-testid="mkt-commission">
      <div style={s.card}>
        <div style={s.cardTitle}>Add commission rule</div>
        <div style={s.row}>
          <select style={s.input} value={form.scope} data-testid="comm-scope"
            onChange={(e) => setForm({ ...form, scope: e.target.value })}>
            <option value="global">Global</option><option value="category">Category</option>
            <option value="market">Market</option><option value="market_category">Market+Category</option>
            <option value="merchant">Merchant</option>
          </select>
          <input style={s.input} type="number" step="0.1" placeholder="commission %"
            data-testid="comm-pct" value={form.commission_pct}
            onChange={(e) => setForm({ ...form, commission_pct: e.target.value })} />
          <input style={s.input} placeholder="category (opt)" value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })} />
          <input style={s.input} placeholder="market (opt)" value={form.market}
            onChange={(e) => setForm({ ...form, market: e.target.value })} />
          <button style={s.primary} onClick={add} data-testid="comm-add-btn">Add</button>
        </div>
      </div>
      {items.map((r) => (
        <div key={r.rule_id} style={s.listRow} data-testid={`comm-${r.rule_id}`}>
          <b>{r.commission_pct}%</b> · {r.scope}
          {r.category ? ` · ${r.category}` : ""}{r.market ? ` · ${r.market}` : ""}
          {r.fixed_fee_cents ? ` · +$${(r.fixed_fee_cents / 100).toFixed(2)}` : ""}
          <span style={{ ...s.badge, background: r.active ? "#134e2a" : "#4b1113" }}>
            {r.active ? "active" : "inactive"}</span>
        </div>
      ))}
    </div>
  );
}

function Loyalty() {
  const [tiers, setTiers] = useState([]);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/loyalty`, CFG); setTiers(data.tiers || []); }
    catch { toast.error("Failed to load loyalty tiers"); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const upd = (i, patch) => setTiers((t) => t.map((x, idx) => (idx === i ? { ...x, ...patch } : x)));
  const addTier = () => setTiers((t) => [...t, { key: `tier${t.length + 1}`, name: "New Tier", min_points: 0, bonus_pct: 0, color: "#888888", perks: [] }]);
  const removeTier = (i) => setTiers((t) => t.filter((_, idx) => idx !== i));
  const save = async () => {
    setSaving(true);
    try {
      const body = { tiers: tiers.map((t) => ({ key: t.key.trim(), name: t.name.trim(), min_points: Number(t.min_points) || 0, bonus_pct: Number(t.bonus_pct) || 0, color: t.color || "#888888", perks: (Array.isArray(t.perks) ? t.perks : String(t.perks || "").split(",")).map((p) => p.trim()).filter(Boolean) })) };
      const { data } = await axios.put(`${API}/loyalty`, body, CFG);
      setTiers(data.tiers || []); toast.success("Loyalty tiers saved");
    } catch (e) { toast.error(e?.response?.data?.detail?.code || "Save failed (base tier must start at 0, keys unique)"); }
    finally { setSaving(false); }
  };

  return (
    <div data-testid="mkt-loyalty">
      <div style={s.card}>
        <div style={s.cardTitle}>Loyalty ladder — thresholds & bonus % (from lifetime BigPoints)</div>
        <div style={s.dim}>The lowest tier must start at 0 points. Bonus % is applied on marketplace rewards.</div>
      </div>
      {tiers.map((t, i) => (
        <div key={i} style={s.listRow} data-testid={`loy-tier-${i}`}>
          <input type="color" value={t.color || "#888888"} data-testid={`loy-color-${i}`}
            onChange={(e) => upd(i, { color: e.target.value })} style={{ width: 34, height: 34, border: "none", background: "none", cursor: "pointer" }} />
          <input style={{ ...s.miniInput, width: 90 }} value={t.key} placeholder="key" data-testid={`loy-key-${i}`}
            onChange={(e) => upd(i, { key: e.target.value })} />
          <input style={{ ...s.miniInput, width: 110 }} value={t.name} placeholder="name" data-testid={`loy-name-${i}`}
            onChange={(e) => upd(i, { name: e.target.value })} />
          <label style={s.inline}>Min pts
            <input style={s.miniInput} type="number" value={t.min_points} data-testid={`loy-min-${i}`}
              onChange={(e) => upd(i, { min_points: e.target.value })} /></label>
          <label style={s.inline}>Bonus %
            <input style={s.miniInput} type="number" value={t.bonus_pct} data-testid={`loy-bonus-${i}`}
              onChange={(e) => upd(i, { bonus_pct: e.target.value })} /></label>
          <input style={{ ...s.input, flex: 1, minWidth: 160 }} placeholder="perks (comma separated)"
            value={Array.isArray(t.perks) ? t.perks.join(", ") : t.perks} data-testid={`loy-perks-${i}`}
            onChange={(e) => upd(i, { perks: e.target.value.split(",") })} />
          <button style={s.danger} onClick={() => removeTier(i)} data-testid={`loy-remove-${i}`}>Remove</button>
        </div>
      ))}
      <div style={s.row}>
        <button style={s.ghost} onClick={addTier} data-testid="loy-add">+ Add tier</button>
        <button style={s.primary} onClick={save} disabled={saving} data-testid="loy-save">{saving ? "Saving…" : "Save Loyalty Tiers"}</button>
      </div>
    </div>
  );
}

function Approvals() {
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("pending");
  const load = useCallback(async () => {
    try { const { data } = await axios.get(`${API}/businesses?status=${filter}`, CFG); setItems(data.items || []); }
    catch { toast.error("Failed to load businesses"); }
  }, [filter]);
  useEffect(() => { load(); }, [load]);
  const act = async (b, action) => {
    try {
      await axios.post(`${API}/businesses/${b.business_id}/${action}`,
        action === "reject" ? { reason: "Did not meet requirements" } : {}, CFG);
      toast.success(`${action}d`); load();
    } catch { toast.error("Failed"); }
  };
  return (
    <div data-testid="mkt-approvals">
      <div style={s.row}>
        {["pending", "approved", "rejected"].map((f) => (
          <button key={f} onClick={() => setFilter(f)} data-testid={`appr-filter-${f}`}
            style={{ ...s.ghost, ...(filter === f ? s.tabActive : {}) }}>{f}</button>
        ))}
      </div>
      {items.length === 0 && <div style={s.dim}>No {filter} businesses.</div>}
      {items.map((b) => (
        <div key={b.business_id} style={s.listRow} data-testid={`appr-${b.business_id}`}>
          <div style={{ flex: 1 }}>
            <b>{b.public_name}</b> <span style={s.dim}>· {b.category} · {b.market || "—"}</span>
            <div style={s.dim}>{b.legal_name} · {(b.bigpoints || {}).default_points || 0} BigPoints/txn</div>
          </div>
          {b.status === "pending" && (
            <>
              <button style={s.primary} onClick={() => act(b, "approve")}
                data-testid={`appr-approve-${b.business_id}`}>Approve</button>
              <button style={s.danger} onClick={() => act(b, "reject")}
                data-testid={`appr-reject-${b.business_id}`}>Reject</button>
            </>
          )}
          {b.status !== "pending" && <span style={{ ...s.badge, background: b.status === "approved" ? "#134e2a" : "#4b1113" }}>{b.status}</span>}
        </div>
      ))}
    </div>
  );
}

const s = {
  page: { minHeight: "100vh", background: "#0a0a0c", color: "#e7e7ea", padding: "28px 20px", fontFamily: "system-ui, sans-serif" },
  header: { maxWidth: 1000, margin: "0 auto 18px" },
  eyebrow: { color: "#F26B2A", fontWeight: 800, fontSize: 12, letterSpacing: 1 },
  h1: { fontSize: 30, fontWeight: 900, margin: "4px 0" },
  sub: { color: "#9a9aa2", fontSize: 14 },
  tabs: { maxWidth: 1000, margin: "0 auto 18px", display: "flex", gap: 8, flexWrap: "wrap" },
  tabBtn: { padding: "10px 16px", borderRadius: 999, border: "1px solid #26262c", background: "#141418", color: "#c9c9d0", fontWeight: 700, cursor: "pointer" },
  tabActive: { background: "#F26B2A", color: "#fff", borderColor: "#F26B2A" },
  card: { maxWidth: 1000, margin: "0 auto 14px", background: "#141418", border: "1px solid #26262c", borderRadius: 14, padding: 16 },
  cardTitle: { fontWeight: 800, marginBottom: 10 },
  row: { display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center", maxWidth: 1000, margin: "0 auto 10px" },
  input: { padding: "9px 12px", borderRadius: 10, border: "1px solid #26262c", background: "#0f0f13", color: "#e7e7ea", minWidth: 120 },
  miniInput: { width: 70, padding: "6px 8px", borderRadius: 8, border: "1px solid #26262c", background: "#0f0f13", color: "#e7e7ea", marginLeft: 6 },
  primary: { padding: "9px 16px", borderRadius: 10, border: "none", background: "#F26B2A", color: "#fff", fontWeight: 800, cursor: "pointer" },
  ghost: { padding: "9px 16px", borderRadius: 10, border: "1px solid #26262c", background: "#141418", color: "#c9c9d0", fontWeight: 700, cursor: "pointer" },
  danger: { padding: "9px 16px", borderRadius: 10, border: "1px solid #7f1d1d", background: "#2a1113", color: "#fca5a5", fontWeight: 800, cursor: "pointer" },
  listRow: { maxWidth: 1000, margin: "0 auto 8px", display: "flex", alignItems: "center", gap: 10, background: "#141418", border: "1px solid #26262c", borderRadius: 12, padding: "12px 14px" },
  badge: { padding: "3px 10px", borderRadius: 999, fontSize: 11, fontWeight: 800, marginLeft: "auto" },
  dim: { color: "#8a8a92", fontSize: 13 },
  inline: { display: "inline-flex", alignItems: "center", color: "#c9c9d0", fontSize: 13 },
};
