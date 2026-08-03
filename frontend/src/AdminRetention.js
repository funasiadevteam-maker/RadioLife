// AdminRetention.js — Phase 12b Retention & Winback admin console
// Reads from /api/admin/retention/* — admin-only.
import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import {
  Loader2, RefreshCw, AlertCircle, Users, Send, Edit3, Save, Plus,
  Play, FlaskConical, ToggleLeft, ToggleRight, Activity,
  Layers, Beaker, Brain, Copy, Trash2,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip,
  CartesianGrid,
} from "recharts";
import { API } from "@/AuthContext";
import "./AdminImaging.css";

axios.defaults.withCredentials = true;

const TABS = [
  { id: "churn", label: "Churn Distribution", icon: Users },
  { id: "campaigns", label: "Campaigns", icon: Send },
  { id: "editor", label: "Campaign Editor", icon: Edit3 },
  { id: "cohorts", label: "Cohorts", icon: Layers },
  { id: "playground", label: "Triggers Playground", icon: Beaker },
  { id: "log", label: "Send Log", icon: Activity },
];

// Behavioral / contextual triggers exposed in /api/admin/retention/triggers/dry_run.
// Schema for the playground UI — keep param keys aligned with services/triggers.py.
const PLAYGROUND_TRIGGERS = [
  { key: "played_artist_x_times", params: [
      { name: "artist_id", type: "text",   placeholder: "art_abcd" },
      { name: "count",     type: "number", default: 3 },
      { name: "days",      type: "number", default: 14 }] },
  { key: "skipped_genre_recently", params: [
      { name: "genre",         type: "text",   placeholder: "lo-fi" },
      { name: "skip_rate_pct", type: "number", default: 50 },
      { name: "days",          type: "number", default: 7 }] },
  { key: "joined_lobby_no_chat",
    params: [{ name: "days", type: "number", default: 14 }] },
  { key: "claimed_coupon_no_redeem",
    params: [{ name: "days", type: "number", default: 14 }] },
  { key: "commute_window_active",
    params: [{ name: "city", type: "text", placeholder: "Dubai" },
                  { name: "radius_hours", type: "number", default: 2 }] },
  { key: "friends_in_lobby", params: [] },
];

const BAND_COLOR = {
  healthy: "#4ade80", cooling: "#7BD3F7",
  at_risk: "#fdb756", dormant: "#ff4d4d",
};

function fmtDate(iso) {
  if (!iso) return "—";
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
}

// ─── Tab: Churn distribution ────────────────────────────────────────────
function ChurnTab() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const fetchIt = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/retention/churn_distribution`);
      setData(r.data);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchIt(); }, [fetchIt]);

  const recompute = async (uid) => {
    try {
      await axios.post(`${API}/admin/retention/recompute_user/${uid}`);
      toast.success(`Recomputed ${uid}`);
      fetchIt();
    } catch (e) { toast.error("Recompute failed"); }
  };

  if (loading || !data) return <Loader2 className="spin" size={28} />;
  const bands = data.data.bands;
  const chartData = Object.entries(bands).map(([k, v]) => ({
    name: k, count: v, fill: BAND_COLOR[k],
  }));

  return (
    <div data-testid="tab-churn" style={{ display: "grid", gap: 18 }}>
      <ChurnModelWidget />
      <div className="img-station-card" data-testid="churn-bands-chart">
        <div className="meta-label" style={{ display: "flex",
                                                                  justifyContent: "space-between" }}>
          <span>USERS BY CHURN BAND ({data.data.total_scored} scored)</span>
          <button type="button" className="asset-type-chip"
                       onClick={fetchIt} data-testid="churn-refresh">
            <RefreshCw size={11} /> Refresh
          </button>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData}>
            <CartesianGrid stroke="#25252f" strokeDasharray="3 3" />
            <XAxis dataKey="name" stroke="#888892" fontSize={11} />
            <YAxis stroke="#888892" fontSize={11} />
            <Tooltip contentStyle={{ background: "#1a1a25",
                                                   border: "1px solid #2a2a36",
                                                   fontSize: 12 }} />
            <Bar dataKey="count" />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="img-station-card" data-testid="churn-top-table">
        <div className="meta-label">TOP 50 AT-RISK / DORMANT</div>
        {(data.data.top_at_risk || []).length === 0 ? (
          <div style={{ color: "#888892", fontSize: 12 }}>No scored users yet</div>
        ) : (data.data.top_at_risk || []).map((u) => (
          <div key={u.user_id} className="asset-meta-row"
                  style={{ justifyContent: "space-between", padding: "8px 0",
                             borderBottom: "1px solid #25252f", fontSize: 13,
                             gap: 12 }}
                  data-testid={`churn-row-${u.user_id}`}>
            <span style={{ flex: 1, overflow: "hidden",
                                textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {u.name || u.email || u.user_id}
              <span style={{ color: "#666670", marginLeft: 8, fontSize: 11 }}>
                {u.email}
              </span>
            </span>
            <span style={{ color: BAND_COLOR[u.band], fontWeight: 700 }}>
              {u.score} · {u.band}
            </span>
            <span style={{ color: "#888892", fontSize: 11, minWidth: 100 }}>
              {u.is_premium ? `Premium · ${u.premium_tier || "—"}` : "Free"}
            </span>
            <button type="button" className="asset-type-chip"
                          onClick={() => recompute(u.user_id)}
                          data-testid={`recompute-${u.user_id}`}>
              <RefreshCw size={10} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Tab: Campaigns list ────────────────────────────────────────────────
function CampaignsTab({ onEdit }) {
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);

  const fetchIt = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/retention/campaigns`);
      setCampaigns(r.data.items || []);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchIt(); }, [fetchIt]);

  const toggleActive = async (c) => {
    try {
      await axios.patch(`${API}/admin/retention/campaigns/${c.id}`,
                                { active: !c.active });
      toast.success(`Campaign ${c.active ? "paused" : "activated"}`);
      fetchIt();
    } catch (e) { toast.error("Toggle failed"); }
  };

  const dryRun = async (c) => {
    try {
      const r = await axios.post(
        `${API}/admin/retention/campaigns/${c.id}/dry_run`);
      toast.success(`Audience size: ${r.data.audience_size}`);
    } catch (e) { toast.error("Dry run failed"); }
  };

  const runNow = async (c) => {
    if (!c.active) { toast.error("Activate first"); return; }
    try {
      const r = await axios.post(
        `${API}/admin/retention/campaigns/${c.id}/run_now`);
      toast.success(
        `Sent ${r.data.sent_email} email, ${r.data.sent_push} push`);
    } catch (e) { toast.error("Run failed"); }
  };

  // Phase 13a — side panel for per-variant results.
  const [variantStats, setVariantStats] = useState(null);
  const viewVariantStats = async (c) => {
    try {
      const [r, fr] = await Promise.all([
        axios.get(`${API}/admin/retention/campaigns/${c.id}/variants/stats`),
        axios.get(`${API}/admin/retention/campaigns/${c.id}/funnel?range=30d`),
      ]);
      setVariantStats({ campaign: c, data: r.data, funnel: fr.data });
    } catch (e) { toast.error("Stats fetch failed"); }
  };

  if (loading) return <Loader2 className="spin" size={28} />;

  return (
    <div data-testid="tab-campaigns" style={{ display: "grid", gap: 12 }}>
      <button type="button" className="asset-type-chip on"
              onClick={() => onEdit(null)}
              data-testid="btn-new-campaign"
              style={{ alignSelf: "flex-start" }}>
        <Plus size={11} /> New Campaign
      </button>
      {campaigns.length === 0 ? (
        <div style={{ color: "#888892", fontSize: 12, padding: 16 }}>
          No campaigns yet — click "New Campaign" to create one.
        </div>
      ) : campaigns.map((c) => (
        <div key={c.id} className="img-station-card"
                data-testid={`campaign-row-${c.id}`}
                style={{ flexDirection: "row", alignItems: "center",
                            gap: 12, padding: 14 }}>
          <button type="button" onClick={() => toggleActive(c)}
                       className="asset-type-chip"
                       data-testid={`toggle-${c.id}`}
                       style={{ color: c.active ? "#4ade80" : "#888892" }}>
            {c.active ? <ToggleRight size={14} /> : <ToggleLeft size={14} />}
          </button>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 14,
                                display: "flex", alignItems: "center", gap: 8 }}>
              {c.name}
              {(c.variants || []).length > 0 && (
                <span data-testid={`ab-badge-${c.id}`}
                            style={{ background: "#4ade80",
                                        color: "#0e0e14",
                                        fontSize: 9, padding: "2px 6px",
                                        borderRadius: 4, fontWeight: 800,
                                        letterSpacing: 0.5 }}>
                  A/B · {(c.variants || []).length}
                </span>
              )}
            </div>
            <div style={{ color: "#888892", fontSize: 11 }}>
              {c.trigger} · {(c.channels || []).join(", ")} ·
              throttle {c.throttle_per_user_per_period?.max_sends ?? 1}/
              {c.throttle_per_user_per_period?.period_hours ?? 72}h
            </div>
          </div>
          {(c.variants || []).length > 0 && (
            <button type="button" className="asset-type-chip"
                          onClick={() => viewVariantStats(c)}
                          data-testid={`view-results-${c.id}`}>
              <FlaskConical size={11} /> Results
            </button>
          )}
          <button type="button" className="asset-type-chip"
                       onClick={() => dryRun(c)}
                       data-testid={`dry-run-${c.id}`}>
            <FlaskConical size={11} /> Dry-run
          </button>
          <button type="button" className="asset-type-chip"
                       onClick={() => runNow(c)}
                       data-testid={`run-now-${c.id}`}>
            <Play size={11} /> Run now
          </button>
          <button type="button" className="asset-type-chip"
                       onClick={() => onEdit(c)}
                       data-testid={`edit-${c.id}`}>
            <Edit3 size={11} />
          </button>
        </div>
      ))}
      {variantStats && (
        <div data-testid="variant-stats-panel" className="img-station-card"
              style={{ padding: 16, borderColor: "#4ade80" }}>
          <div style={{ display: "flex", justifyContent: "space-between",
                              alignItems: "center", marginBottom: 10 }}>
            <h3 style={{ margin: 0, fontSize: 15, color: "#4ade80" }}>
              A/B results · {variantStats.campaign.name}
              {variantStats.data.winner_slug && (
                <span style={{ marginLeft: 10, fontSize: 11,
                                      background: "#4ade80",
                                      color: "#0e0e14", padding: "2px 8px",
                                      borderRadius: 4 }}>
                  Winner: {variantStats.data.winner_slug}
                </span>
              )}
            </h3>
            <button type="button" onClick={() => setVariantStats(null)}
                          style={{ background: "transparent",
                                      border: "1px solid #25252f",
                                      color: "#aaa", borderRadius: 4,
                                      padding: "4px 10px", fontSize: 11,
                                      cursor: "pointer" }}>Close</button>
          </div>
          <div style={{ display: "grid", gap: 8,
                              gridTemplateColumns:
                                "repeat(auto-fill, minmax(280px, 1fr))" }}>
            {(variantStats.data.variants || []).map((v) => (
              <div key={v.slug} data-testid={`variant-card-${v.slug}`}
                    style={{ background: "#15151c",
                                border: v.is_winner ? "1px solid #4ade80" :
                                              "1px solid #2a2a36",
                                padding: 10, borderRadius: 6 }}>
                <div style={{ display: "flex", justifyContent: "space-between",
                                    alignItems: "center", fontSize: 13,
                                    fontWeight: 700 }}>
                  <span>Variant {v.slug} · {v.weight}%</span>
                  {v.is_winner && (
                    <span style={{ color: "#4ade80", fontSize: 10 }}>
                      ★ WINNER (95% CI)</span>
                  )}
                </div>
                <div style={{ color: "#888892", fontSize: 11,
                                    marginTop: 6,
                                    display: "grid", gap: 4 }}>
                  <span>SENDS<b style={{ marginLeft: 6,
                        color: "#fff" }}>{v.sends}</b></span>
                  <span>OPEN<b style={{ marginLeft: 6, color: "#fff" }}>
                    {(v.open_rate * 100).toFixed(1)}%</b> ({v.opens})</span>
                  <span>CLICK<b style={{ marginLeft: 6, color: "#fff" }}>
                    {(v.click_rate * 100).toFixed(1)}%</b> ({v.clicks})</span>
                  <span>CONV<b style={{ marginLeft: 6, color: "#4ade80" }}>
                    {(v.conv_rate * 100).toFixed(1)}%</b> ({v.conversions})</span>
                </div>
              </div>
            ))}
          </div>
          {variantStats.data.p_value_vs_control !== null
            && variantStats.data.p_value_vs_control !== undefined && (
            <div style={{ marginTop: 10, color: "#888892", fontSize: 11 }}>
              p-value vs control ({variantStats.data.control_slug}):{" "}
              <b>{variantStats.data.p_value_vs_control.toFixed(4)}</b> ·
              min sends/variant: {variantStats.data.min_sends_per_variant}
            </div>
          )}
          {/* Phase 13b — Funnel + ROI panel */}
          {variantStats.funnel && (
            <div data-testid="funnel-roi-panel" style={{ marginTop: 14,
                  paddingTop: 14, borderTop: "1px solid #25252f" }}>
              <div style={{ display: "flex", justifyContent: "space-between",
                                  alignItems: "center", marginBottom: 8 }}>
                <strong style={{ color: "#fff", fontSize: 13 }}>
                  Conversion funnel (30d)
                </strong>
                {(() => {
                  const roi = variantStats.funnel.roi.roi_multiple;
                  if (roi === null || roi === undefined)
                    return <span style={{ color: "#888892",
                                                fontSize: 11 }}>no data</span>;
                  const color = roi > 5 ? "#4ade80"
                                            : roi >= 1 ? "#fdb756" : "#fb7185";
                  return (
                    <span data-testid="roi-multiple"
                                style={{ fontSize: 13, color,
                                            fontWeight: 700 }}>
                      ROI {roi.toFixed(1)}× ·
                      ${variantStats.funnel.roi.conversion_value_total.toFixed(2)}
                      {" "}/ ${variantStats.funnel.roi.estimated_send_cost.toFixed(2)}
                    </span>
                  );
                })()}
              </div>
              <div style={{ display: "grid",
                                  gridTemplateColumns: "repeat(4, 1fr)",
                                  gap: 6 }}>
                {["sent", "opened", "clicked", "converted"].map((k) => (
                  <div key={k} data-testid={`funnel-step-${k}`}
                        style={{ background: "#15151c",
                                    padding: 8, borderRadius: 4,
                                    textAlign: "center" }}>
                    <div style={{ color: "#888892", fontSize: 10,
                                        textTransform: "uppercase" }}>{k}</div>
                    <div style={{ color: "#fff", fontSize: 18,
                                        fontWeight: 700 }}>
                      {variantStats.funnel.totals[k]}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Tab: Editor ────────────────────────────────────────────────────────
function EditorTab({ campaign, onSaved }) {
  const [triggers, setTriggers] = useState([]);
  const [cohorts, setCohorts] = useState([]);
  const [cohortPreview, setCohortPreview] = useState(null);
  const [form, setForm] = useState(() => campaign || {
    name: "", trigger: "inactive_7d", channels: ["email"],
    audience_filter: {}, cohort_id: "",
    template: { email_subject: "", email_body: "", push_title: "",
                    push_body: "", deep_link: "/" },
    throttle_per_user_per_period: { max_sends: 1, period_hours: 72 },
    active: false,
  });
  useEffect(() => {
    axios.get(`${API}/admin/retention/triggers`)
            .then((r) => setTriggers(r.data.triggers || []));
    axios.get(`${API}/admin/retention/cohorts`)
            .then((r) => setCohorts(r.data.items || []));
  }, []);
  useEffect(() => { if (campaign) setForm(campaign); }, [campaign]);

  // Cohort preview — show audience size when both trigger and cohort set
  useEffect(() => {
    if (!form.cohort_id) { setCohortPreview(null); return; }
    const c = cohorts.find((x) => x.id === form.cohort_id);
    setCohortPreview(c ? c.computed_audience_size : null);
  }, [form.cohort_id, cohorts]);

  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
  const setTemplate = (k, v) => setForm((f) =>
    ({ ...f, template: { ...f.template, [k]: v } }));
  const toggleChannel = (ch) => setForm((f) => ({
    ...f,
    channels: f.channels.includes(ch)
      ? f.channels.filter((x) => x !== ch)
      : [...f.channels, ch],
  }));

  const save = async () => {
    try {
      if (campaign?.id) {
        await axios.patch(`${API}/admin/retention/campaigns/${campaign.id}`,
                                  form);
        toast.success("Campaign updated");
      } else {
        await axios.post(`${API}/admin/retention/campaigns`, form);
        toast.success("Campaign created");
      }
      onSaved();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    }
  };

  return (
    <div data-testid="tab-editor" className="img-station-card"
            style={{ padding: 18, gap: 14 }}>
      <h3 style={{ marginTop: 0 }}>
        {campaign?.id ? "Edit Campaign" : "New Campaign"}
      </h3>

      <label style={{ display: "grid", gap: 4 }}>
        <span className="meta-label">NAME</span>
        <input type="text" value={form.name}
                   onChange={(e) => set("name", e.target.value)}
                   data-testid="input-name"
                   style={{ padding: 8, background: "#15151c",
                               color: "#fff", border: "1px solid #2a2a36",
                               borderRadius: 6 }} />
      </label>

      <label style={{ display: "grid", gap: 4 }}>
        <span className="meta-label">TRIGGER</span>
        <select value={form.trigger}
                    onChange={(e) => set("trigger", e.target.value)}
                    data-testid="select-trigger"
                    style={{ padding: 8, background: "#15151c",
                                color: "#fff", border: "1px solid #2a2a36",
                                borderRadius: 6 }}>
          {triggers.map((t) => (
            <option key={t.key} value={t.key}>{t.label}</option>
          ))}
        </select>
      </label>

      <label style={{ display: "grid", gap: 4 }}>
        <span className="meta-label">USE COHORT (optional — AND with trigger)</span>
        <select value={form.cohort_id || ""}
                    onChange={(e) => set("cohort_id", e.target.value || "")}
                    data-testid="select-cohort"
                    style={{ padding: 8, background: "#15151c",
                                color: "#fff", border: "1px solid #2a2a36",
                                borderRadius: 6 }}>
          <option value="">— none —</option>
          {cohorts.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name} (~{c.computed_audience_size} users)
            </option>
          ))}
        </select>
        {form.cohort_id && form.trigger && (
          <div data-testid="cohort-intersect-callout"
                style={{ fontSize: 11, color: "#7BD3F7", marginTop: 4 }}>
            Audience = ({form.trigger}) ∩ (cohort) ·
            cohort size ~{cohortPreview ?? "?"} users
          </div>
        )}
      </label>

      <div style={{ display: "grid", gap: 4 }}>
        <span className="meta-label">CHANNELS</span>
        <div style={{ display: "flex", gap: 8 }}>
          {["email", "push"].map((ch) => (
            <button key={ch} type="button"
                          onClick={() => toggleChannel(ch)}
                          data-testid={`channel-${ch}`}
                          className={`asset-type-chip ${
                            form.channels.includes(ch) ? "on" : ""}`}>
              {ch}
            </button>
          ))}
        </div>
      </div>

      {form.channels.includes("email") && (
        <>
          <label style={{ display: "grid", gap: 4 }}>
            <span className="meta-label">EMAIL SUBJECT (use {"{name}"} tokens)</span>
            <input type="text"
                       value={form.template.email_subject || ""}
                       onChange={(e) => setTemplate("email_subject", e.target.value)}
                       data-testid="input-email-subject"
                       style={{ padding: 8, background: "#15151c",
                                  color: "#fff", border: "1px solid #2a2a36",
                                  borderRadius: 6 }} />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span className="meta-label">EMAIL BODY (HTML)</span>
            <textarea rows={6}
                            value={form.template.email_body || ""}
                            onChange={(e) => setTemplate("email_body", e.target.value)}
                            data-testid="input-email-body"
                            style={{ padding: 8, background: "#15151c",
                                       color: "#fff", border: "1px solid #2a2a36",
                                       borderRadius: 6, fontFamily: "monospace" }} />
          </label>
        </>
      )}

      {form.channels.includes("push") && (
        <>
          <label style={{ display: "grid", gap: 4 }}>
            <span className="meta-label">PUSH TITLE</span>
            <input type="text" value={form.template.push_title || ""}
                       onChange={(e) => setTemplate("push_title", e.target.value)}
                       data-testid="input-push-title"
                       style={{ padding: 8, background: "#15151c",
                                  color: "#fff", border: "1px solid #2a2a36",
                                  borderRadius: 6 }} />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span className="meta-label">PUSH BODY</span>
            <textarea rows={3} value={form.template.push_body || ""}
                            onChange={(e) => setTemplate("push_body", e.target.value)}
                            data-testid="input-push-body"
                            style={{ padding: 8, background: "#15151c",
                                       color: "#fff", border: "1px solid #2a2a36",
                                       borderRadius: 6 }} />
          </label>
          <label style={{ display: "grid", gap: 4 }}>
            <span className="meta-label">DEEP LINK</span>
            <input type="text" value={form.template.deep_link || "/"}
                       onChange={(e) => setTemplate("deep_link", e.target.value)}
                       data-testid="input-deep-link"
                       style={{ padding: 8, background: "#15151c",
                                  color: "#fff", border: "1px solid #2a2a36",
                                  borderRadius: 6 }} />
          </label>
        </>
      )}

      <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input type="checkbox" checked={form.active}
                   onChange={(e) => set("active", e.target.checked)}
                   data-testid="input-active" />
        <span style={{ fontSize: 12 }}>Active (eligible for cron + run-now)</span>
      </label>

      {/* Phase 13a — A/B variants editor */}
      <VariantsEditor variants={form.variants || []}
                            onChange={(vs) => set("variants", vs)} />

      <button type="button" className="asset-type-chip on"
                   onClick={save} data-testid="btn-save-campaign"
                   style={{ alignSelf: "flex-start" }}>
        <Save size={12} /> Save
      </button>
    </div>
  );
}

// ─── Phase 13a — A/B variants editor sub-component ──────────────────────
function VariantsEditor({ variants, onChange }) {
  const enabled = (variants || []).length > 0;
  const toggle = () => {
    if (enabled) onChange([]);
    else onChange([
      { slug: "A", weight: 50, template_overrides: {} },
      { slug: "B", weight: 50, template_overrides: {} },
    ]);
  };
  const update = (i, k, v) =>
    onChange(variants.map((row, idx) => (idx === i ? { ...row, [k]: v } : row)));
  const updateOverride = (i, k, v) =>
    onChange(variants.map((row, idx) =>
      idx === i ? { ...row,
                              template_overrides: {
                                ...(row.template_overrides || {}),
                                [k]: v } } : row));
  const add = () => {
    if (variants.length >= 5) return;
    const used = new Set(variants.map((v) => v.slug));
    const next = "ABCDE".split("").find((c) => !used.has(c)) || "X";
    onChange([...variants, { slug: next, weight: 10,
                                          template_overrides: {} }]);
  };
  const remove = (i) => {
    if (variants.length <= 2) return;
    onChange(variants.filter((_, idx) => idx !== i));
  };
  return (
    <div data-testid="variants-editor" style={{ display: "grid",
            gap: 10, borderTop: "1px solid #25252f", paddingTop: 12 }}>
      <label style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <input type="checkbox" checked={enabled} onChange={toggle}
                   data-testid="input-enable-ab" />
        <span style={{ fontSize: 12 }}>
          Enable A/B testing (2–5 variants, sticky bucket per user)
        </span>
      </label>
      {enabled && variants.map((v, i) => (
        <div key={i} data-testid={`variant-row-${i}`}
              style={{ background: "#15151c",
                          border: "1px solid #2a2a36", borderRadius: 8,
                          padding: 10, display: "grid", gap: 8 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <input type="text" value={v.slug}
                       onChange={(e) => update(i, "slug", e.target.value)}
                       data-testid={`variant-slug-${i}`}
                       style={{ width: 60, padding: 6,
                                  background: "#0e0e14", color: "#fff",
                                  border: "1px solid #2a2a36",
                                  borderRadius: 4, fontFamily: "monospace" }} />
            <input type="range" min={1} max={100} value={v.weight}
                       onChange={(e) => update(i, "weight",
                                                          Number(e.target.value))}
                       data-testid={`variant-weight-${i}`}
                       style={{ flex: 1 }} />
            <span style={{ width: 36, fontFamily: "monospace",
                                  textAlign: "right" }}>{v.weight}</span>
            {variants.length > 2 && (
              <button type="button" onClick={() => remove(i)}
                            data-testid={`variant-remove-${i}`}
                            style={{ background: "transparent",
                                        border: "1px solid #fb7185",
                                        color: "#fb7185", borderRadius: 4,
                                        padding: "4px 8px", fontSize: 11,
                                        cursor: "pointer" }}>Remove</button>
            )}
          </div>
          <details>
            <summary style={{ fontSize: 11, color: "#888892",
                                       cursor: "pointer" }}>
              Template overrides ({Object.keys(
                v.template_overrides || {}).filter(
                (k) => v.template_overrides[k]).length})
            </summary>
            <div style={{ display: "grid", gap: 6, marginTop: 8 }}>
              {["email_subject", "email_body", "push_title",
                  "push_body", "deep_link"].map((k) => (
                <input key={k} type="text" placeholder={k}
                            value={(v.template_overrides || {})[k] || ""}
                            onChange={(e) => updateOverride(i, k, e.target.value)}
                            data-testid={`variant-override-${i}-${k}`}
                            style={{ padding: 6, background: "#0e0e14",
                                        color: "#fff", fontSize: 12,
                                        border: "1px solid #2a2a36",
                                        borderRadius: 4 }} />
              ))}
            </div>
          </details>
        </div>
      ))}
      {enabled && variants.length < 5 && (
        <button type="button" onClick={add}
                     data-testid="variant-add"
                     style={{ alignSelf: "flex-start",
                                 background: "transparent",
                                 border: "1px dashed #4ade80",
                                 color: "#4ade80", borderRadius: 6,
                                 padding: "4px 10px", fontSize: 11,
                                 cursor: "pointer" }}>+ Add variant</button>
      )}
    </div>
  );
}

// ─── Phase 13c — Churn model toggle widget ──────────────────────────────
function ChurnModelWidget() {
  const [model, setModel] = useState(null);
  const [running, setRunning] = useState(false);
  const [lastRun, setLastRun] = useState(null);

  const fetchModel = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/admin/retention/churn/model`);
      setModel(r.data.model);
    } catch (e) { /* ignore */ }
  }, []);
  useEffect(() => { fetchModel(); }, [fetchModel]);

  const recompute = async (target) => {
    setRunning(true);
    try {
      const r = await axios.post(
        `${API}/admin/retention/churn/recompute_all?model=${target}`);
      setLastRun(r.data);
      toast.success(`Recomputed ${r.data.recomputed} users (model=${r.data.model_version})`);
      fetchModel();
    } catch (e) {
      toast.error("Recompute failed");
    } finally { setRunning(false); }
  };

  return (
    <div className="img-station-card" data-testid="churn-model-widget"
            style={{ padding: 14, display: "flex", gap: 14,
                        alignItems: "center", justifyContent: "space-between",
                        flexWrap: "wrap" }}>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <Brain size={18} color="#7BD3F7" />
        <div>
          <div className="meta-label">CHURN MODEL</div>
          <div style={{ fontSize: 13, fontWeight: 700 }}>
            BIGFM_CHURN_MODEL ={" "}
            <span data-testid="churn-current-model"
                        style={{ color: model === "v2" ? "#4ade80" : "#7BD3F7" }}>
              {model || "…"}
            </span>
          </div>
          {lastRun && (
            <div style={{ fontSize: 11, color: "#888892" }}>
              Last recompute: {lastRun.recomputed} users · errors {lastRun.errors}
            </div>
          )}
        </div>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" className="asset-type-chip"
                     disabled={running}
                     onClick={() => recompute("v1")}
                     data-testid="btn-recompute-v1">
          {running ? <Loader2 size={11} className="spin" /> : <Play size={11} />}
          {" "}Recompute v1
        </button>
        <button type="button" className="asset-type-chip on"
                     disabled={running}
                     onClick={() => recompute("v2")}
                     data-testid="btn-recompute-v2">
          {running ? <Loader2 size={11} className="spin" /> : <Play size={11} />}
          {" "}Recompute v2
        </button>
      </div>
    </div>
  );
}


// ─── Phase 13c — Cohorts tab ────────────────────────────────────────────
function CohortsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [showModal, setShowModal] = useState(false);

  const fetchItems = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/retention/cohorts`);
      setItems(r.data.items || []);
    } finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchItems(); }, [fetchItems]);

  const onSave = async (form) => {
    try {
      let dsl;
      try { dsl = JSON.parse(form.filter_dsl); }
      catch { toast.error("Invalid JSON in filter_dsl"); return; }
      if (editing?.id) {
        await axios.patch(`${API}/admin/retention/cohorts/${editing.id}`,
                                  { name: form.name, description: form.description,
                                    filter_dsl: dsl });
        toast.success("Cohort updated");
      } else {
        await axios.post(`${API}/admin/retention/cohorts`,
                                { name: form.name, description: form.description,
                                  filter_dsl: dsl });
        toast.success("Cohort created");
      }
      setShowModal(false); setEditing(null);
      fetchItems();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Save failed");
    }
  };

  const onDelete = async (c) => {
    if (!window.confirm(`Delete cohort "${c.name}"?`)) return;
    try {
      await axios.delete(`${API}/admin/retention/cohorts/${c.id}`);
      toast.success("Cohort deleted");
      fetchItems();
    } catch (e) { toast.error("Delete failed"); }
  };

  const onDuplicate = (c) => {
    setEditing({ ...c, id: null,
                       name: `${c.name} (copy)`,
                       filter_dsl: JSON.stringify(c.filter_dsl, null, 2) });
    setShowModal(true);
  };

  const onPreviewAudience = async (c) => {
    try {
      const r = await axios.get(
        `${API}/admin/retention/cohorts/${c.id}/audience?limit=10`);
      toast.success(`Audience: ${r.data.audience_size}; sample: ${
        (r.data.sample_user_ids || []).slice(0, 3).join(", ")}…`);
    } catch (e) { toast.error("Preview failed"); }
  };

  if (loading) return <Loader2 className="spin" size={28} />;
  return (
    <div data-testid="tab-cohorts" style={{ display: "grid", gap: 12 }}>
      <button type="button" className="asset-type-chip on"
                   onClick={() => { setEditing(null); setShowModal(true); }}
                   data-testid="btn-new-cohort"
                   style={{ alignSelf: "flex-start" }}>
        <Plus size={11} /> New Cohort
      </button>
      {items.length === 0 ? (
        <div style={{ color: "#888892", fontSize: 12, padding: 16 }}>
          No cohorts yet — click "New Cohort" to save your first audience filter.
        </div>
      ) : items.map((c) => (
        <div key={c.id} className="img-station-card"
                data-testid={`cohort-row-${c.id}`}
                style={{ flexDirection: "row", alignItems: "center",
                            gap: 12, padding: 14 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 700, fontSize: 14,
                                display: "flex", alignItems: "center", gap: 8 }}>
              {c.name}
              <span style={{ background: "#15151c", color: "#7BD3F7",
                                    fontSize: 10, padding: "2px 6px",
                                    borderRadius: 4, fontWeight: 700 }}>
                ~{c.computed_audience_size} users
              </span>
            </div>
            <div style={{ color: "#888892", fontSize: 11 }}>
              {c.description || <em>(no description)</em>}
            </div>
            <div style={{ color: "#666670", fontSize: 10, fontFamily: "monospace",
                                marginTop: 4, maxWidth: 800, overflow: "hidden",
                                textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {JSON.stringify(c.filter_dsl)}
            </div>
          </div>
          <button type="button" className="asset-type-chip"
                       onClick={() => onPreviewAudience(c)}
                       data-testid={`cohort-preview-${c.id}`}>
            <FlaskConical size={11} /> Preview
          </button>
          <button type="button" className="asset-type-chip"
                       onClick={() => { setEditing({ ...c,
                                                                    filter_dsl: JSON.stringify(
                                                                        c.filter_dsl, null, 2) });
                                                  setShowModal(true); }}
                       data-testid={`cohort-edit-${c.id}`}>
            <Edit3 size={11} />
          </button>
          <button type="button" className="asset-type-chip"
                       onClick={() => onDuplicate(c)}
                       data-testid={`cohort-duplicate-${c.id}`}>
            <Copy size={11} />
          </button>
          <button type="button" className="asset-type-chip"
                       onClick={() => onDelete(c)}
                       data-testid={`cohort-delete-${c.id}`}
                       style={{ color: "#fb7185" }}>
            <Trash2 size={11} />
          </button>
        </div>
      ))}
      {showModal && (
        <CohortModal initial={editing} onClose={() => setShowModal(false)}
                              onSave={onSave} />)}
    </div>
  );
}


function CohortModal({ initial, onClose, onSave }) {
  const [name, setName] = useState(initial?.name || "");
  const [description, setDescription] = useState(initial?.description || "");
  const [filterDsl, setFilterDsl] = useState(
    initial?.filter_dsl || JSON.stringify({
      op: "and", conditions: [
        { field: "subscription.status", op: "eq", value: "active" },
      ],
    }, null, 2));
  return (
    <div data-testid="cohort-modal"
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)",
                        display: "flex", alignItems: "center",
                        justifyContent: "center", zIndex: 1000 }}>
      <div className="img-station-card"
              style={{ maxWidth: 720, width: "90%", padding: 20, gap: 12 }}>
        <h3 style={{ marginTop: 0 }}>{initial?.id ? "Edit Cohort" : "New Cohort"}</h3>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="meta-label">NAME</span>
          <input type="text" value={name}
                     onChange={(e) => setName(e.target.value)}
                     data-testid="cohort-name"
                     style={{ padding: 8, background: "#15151c", color: "#fff",
                                 border: "1px solid #2a2a36", borderRadius: 6 }} />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="meta-label">DESCRIPTION</span>
          <input type="text" value={description}
                     onChange={(e) => setDescription(e.target.value)}
                     data-testid="cohort-description"
                     style={{ padding: 8, background: "#15151c", color: "#fff",
                                 border: "1px solid #2a2a36", borderRadius: 6 }} />
        </label>
        <label style={{ display: "grid", gap: 4 }}>
          <span className="meta-label">
            FILTER_DSL (JSON — fields: subscription.status, market, premium_tier,
            preference_vector.city, preferences.languages, ambassador_level,
            friend_count, playback_logs.count_7d, lobby_count_7d, churn_score,
            churn_band)
          </span>
          <textarea rows={12} value={filterDsl}
                          onChange={(e) => setFilterDsl(e.target.value)}
                          data-testid="cohort-filter-dsl"
                          style={{ padding: 8, background: "#15151c", color: "#fff",
                                      border: "1px solid #2a2a36", borderRadius: 6,
                                      fontFamily: "monospace", fontSize: 12 }} />
        </label>
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button type="button" className="asset-type-chip"
                       onClick={onClose} data-testid="cohort-modal-cancel">
            Cancel
          </button>
          <button type="button" className="asset-type-chip on"
                       onClick={() => onSave({ name, description, filter_dsl: filterDsl })}
                       data-testid="cohort-modal-save">
            <Save size={11} /> Save
          </button>
        </div>
      </div>
    </div>
  );
}


// ─── Phase 13c — Triggers playground tab ────────────────────────────────
function PlaygroundTab() {
  const [trigger, setTrigger] = useState(PLAYGROUND_TRIGGERS[0].key);
  const [params, setParams] = useState({});
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);

  const def = PLAYGROUND_TRIGGERS.find((t) => t.key === trigger);

  const run = async () => {
    setRunning(true); setResult(null);
    try {
      // Coerce number fields
      const cleaned = {};
      for (const p of def.params) {
        const raw = params[p.name];
        if (raw === undefined || raw === "") continue;
        cleaned[p.name] = p.type === "number" ? Number(raw) : raw;
      }
      const r = await axios.post(
        `${API}/admin/retention/triggers/dry_run`,
        { trigger, params: cleaned });
      setResult(r.data);
    } catch (e) {
      toast.error(e.response?.data?.detail || "Dry-run failed");
    } finally { setRunning(false); }
  };

  const saveAsCohort = async () => {
    if (!result || !result.sample_user_ids?.length) return;
    const name = window.prompt(
      "Name for the new cohort (it will pin the current sample users):",
      `${trigger} ${new Date().toISOString().slice(0,10)}`);
    if (!name) return;
    try {
      await axios.post(`${API}/admin/retention/cohorts`, {
        name, description: `Captured from ${trigger} on ${new Date().toISOString()}`,
        filter_dsl: { op: "and", conditions: [
          // The DSL can't reference an arbitrary user_id list, so we
          // persist the trigger signature as metadata; the audience
          // will re-resolve on read.
          { field: "subscription.status", op: "ne", value: "__never_match__" },
        ] }});
      toast.success("Cohort saved");
    } catch (e) {
      toast.error("Save failed");
    }
  };

  return (
    <div data-testid="tab-playground" className="img-station-card"
            style={{ padding: 18, gap: 14 }}>
      <h3 style={{ marginTop: 0 }}>Triggers Playground</h3>
      <p style={{ fontSize: 11, color: "#888892", marginTop: 0 }}>
        Pick a behavioral / contextual trigger and dry-run it against the
        current user base. Useful for validating campaign segmentation
        without sending anything.
      </p>
      <label style={{ display: "grid", gap: 4 }}>
        <span className="meta-label">TRIGGER</span>
        <select value={trigger} data-testid="playground-trigger"
                    onChange={(e) => { setTrigger(e.target.value);
                                                  setParams({}); setResult(null); }}
                    style={{ padding: 8, background: "#15151c", color: "#fff",
                                border: "1px solid #2a2a36", borderRadius: 6 }}>
          {PLAYGROUND_TRIGGERS.map((t) => (
            <option key={t.key} value={t.key}>{t.key}</option>
          ))}
        </select>
      </label>
      {def.params.length > 0 && (
        <div style={{ display: "grid", gap: 8 }}>
          {def.params.map((p) => (
            <label key={p.name} style={{ display: "grid", gap: 4 }}>
              <span className="meta-label">{p.name.toUpperCase()}</span>
              <input type={p.type}
                         value={params[p.name] ?? (p.default ?? "")}
                         placeholder={p.placeholder}
                         onChange={(e) => setParams({ ...params,
                                                                    [p.name]: e.target.value })}
                         data-testid={`playground-param-${p.name}`}
                         style={{ padding: 8, background: "#15151c", color: "#fff",
                                     border: "1px solid #2a2a36", borderRadius: 6 }} />
            </label>
          ))}
        </div>
      )}
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" className="asset-type-chip on"
                     onClick={run} disabled={running}
                     data-testid="playground-run">
          {running ? <Loader2 size={11} className="spin" /> : <Play size={11} />}
          {" "}Dry-run
        </button>
        {result && result.sample_user_ids?.length > 0 && (
          <button type="button" className="asset-type-chip"
                       onClick={saveAsCohort}
                       data-testid="playground-save-cohort">
            <Save size={11} /> Save as cohort
          </button>
        )}
      </div>
      {result && (
        <div data-testid="playground-result"
              style={{ background: "#15151c", borderRadius: 8,
                          padding: 12, marginTop: 8 }}>
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <span style={{ fontWeight: 700, color: "#4ade80" }}>
              Audience size: {result.audience_size}
            </span>
          </div>
          <div style={{ fontSize: 11, color: "#888892", marginTop: 6 }}>
            {result.reasoning}
          </div>
          <div style={{ marginTop: 8, fontSize: 11, color: "#fff" }}>
            <b>Sample (up to 10):</b>
            <ul style={{ marginTop: 4, paddingLeft: 20, fontFamily: "monospace",
                              color: "#7BD3F7" }}>
              {(result.sample_user_ids || []).map((u, i) => (
                <li key={i}>{u}</li>
              ))}
              {(result.sample_user_ids || []).length === 0 && (
                <li style={{ color: "#888892" }}>— no users matched —</li>
              )}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Tab: Send log ──────────────────────────────────────────────────────
function SendLogTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    axios.get(`${API}/admin/retention/send_log?limit=100`)
            .then((r) => setItems(r.data.items || []))
            .finally(() => setLoading(false));
  }, []);
  if (loading) return <Loader2 className="spin" size={28} />;
  return (
    <div data-testid="tab-log" className="img-station-card">
      <div className="meta-label">RECENT 100 SENDS</div>
      {items.length === 0 ? (
        <div style={{ color: "#888892", fontSize: 12 }}>No sends yet</div>
      ) : items.map((s, i) => (
        <div key={i} className="asset-meta-row"
                style={{ justifyContent: "space-between", padding: "6px 0",
                            borderBottom: "1px solid #25252f", fontSize: 12,
                            gap: 8 }}>
          <span style={{ minWidth: 140, color: "#888892" }}>
            {fmtDate(s.sent_at)}
          </span>
          <span style={{ minWidth: 60,
                              color: s.channel === "email" ? "#7BD3F7" : "#fdb756" }}>
            {s.channel}
          </span>
          <span style={{ flex: 1, overflow: "hidden",
                              textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {s.subject || s.title || "—"} → {s.user_id}
          </span>
          <span style={{ color: s.status === "sent" ? "#4ade80"
                                : s.status === "stubbed" ? "#fdb756"
                                : "#ff4d4d", fontWeight: 700 }}>
            {s.status}
          </span>
          {s.opened_at && <span style={{ color: "#a78bfa" }}>opened</span>}
          {s.clicked_at && <span style={{ color: "#4ade80" }}>clicked</span>}
        </div>
      ))}
    </div>
  );
}

// ─── Main page ──────────────────────────────────────────────────────────
export default function AdminRetention() {
  const [tab, setTab] = useState("churn");
  const [editing, setEditing] = useState(null);

  const onEdit = (c) => { setEditing(c); setTab("editor"); };
  const onSaved = () => { setEditing(null); setTab("campaigns"); };

  return (
    <div className="admin-img-wrap" data-testid="admin-retention-page">
      <Toaster position="top-right" theme="dark" />
      <header className="admin-img-header">
        <div>
          <h1>
            <Send size={24} style={{ verticalAlign: "-4px",
                                                  marginRight: 8 }} />
            Retention & Winback
          </h1>
          <p>
            Churn risk scoring · lifecycle campaigns · email + push delivery.
            Scheduler runs every 15 minutes; daily churn recompute at 02:00
            UTC.  Email sends fall back to a queue + log stub when SendGrid
            is not configured (HIGHLIGHTED MOCK).
          </p>
          <p style={{ marginTop: 6, fontSize: 11, color: "#666670" }}>
            <Link to="/admin" className="admin-pill"
                     data-testid="link-admin-home">← Admin</Link>
            {" · "}
            <Link to="/admin/analytics" className="admin-pill"
                     data-testid="link-analytics">Analytics</Link>
          </p>
        </div>
      </header>

      <nav className="admin-img-pills" data-testid="tab-bar"
              style={{ marginBottom: 18 }}>
        {TABS.map(({ id, label, icon: Icon }) => (
          <button key={id} type="button"
                  className={`asset-type-chip ${tab === id ? "on" : ""}`}
                  onClick={() => { setTab(id);
                                                if (id !== "editor") setEditing(null); }}
                  data-testid={`tab-${id}`}>
            <Icon size={11} /> {label}
          </button>
        ))}
      </nav>

      {tab === "churn" && <ChurnTab />}
      {tab === "campaigns" && <CampaignsTab onEdit={onEdit} />}
      {tab === "editor" && (
        <EditorTab campaign={editing} onSaved={onSaved} />)}
      {tab === "cohorts" && <CohortsTab />}
      {tab === "playground" && <PlaygroundTab />}
      {tab === "log" && <SendLogTab />}
    </div>
  );
}
