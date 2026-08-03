// Sub-Phase E1 — Admin: Predict & Win campaigns workspace.
//
// Admin-only.  Implements:
//  • List + status filters
//  • Create campaign wizard (drawer)
//  • Detail drawer with prize CRUD, submit/approve/reject buttons,
//    force-resolve modal, cancel modal
//  • Compliance settings inline panel (create + select)
//
// Compliance guardrails:
//  • `live_sports_moment` event type renders disabled with a tooltip
//  • Backend rejects forbidden contest language in any text field
//    (matched in this file: title, description, prompt, answer_option
//    label, prize title, prize description) so the UI just surfaces
//    the server error toast
//
// Routes used:
//   GET     /api/admin/predict-win/event-types
//   GET     /api/admin/predict-win/providers
//   GET     /api/admin/predict-win/compliance
//   POST    /api/admin/predict-win/compliance
//   GET     /api/admin/predict-win/campaigns?status=&approval_status=
//   POST    /api/admin/predict-win/campaigns
//   GET     /api/admin/predict-win/campaigns/{id}
//   PATCH   /api/admin/predict-win/campaigns/{id}
//   POST    /api/admin/predict-win/campaigns/{id}/prizes
//   DELETE  /api/admin/predict-win/campaigns/{id}/prizes/{prize_id}
//   POST    /api/admin/predict-win/campaigns/{id}/submit-approval
//   POST    /api/admin/predict-win/campaigns/{id}/approve
//   POST    /api/admin/predict-win/campaigns/{id}/reject
//   POST    /api/admin/predict-win/campaigns/{id}/lock
//   POST    /api/admin/predict-win/campaigns/{id}/force-resolve
//   POST    /api/admin/predict-win/campaigns/{id}/cancel

/* eslint-disable react-hooks/set-state-in-effect */

import { useCallback, useEffect, useMemo, useState } from "react";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Plus, X, Check, Loader2, ShieldCheck, AlertTriangle, Trash2,
  ChevronRight, Sparkles, Lock, Flag, FileText, Trophy, Database,
} from "lucide-react";
import AdminSubNav from "@/AdminSubNav";
// Sub-Phase E5 — Predexon import modal.
import ImportPredexonModal from "@/Admin/ImportPredexonModal";
// Phase PDX.1 — Auto-curator dashboard section.
import PdxAutoCuratedPanel from "@/Admin/PdxAutoCuratedPanel";

const API = process.env.REACT_APP_BACKEND_URL;
const PW = `${API}/api/admin/predict-win`;

const STATUS_FILTERS = [
  { value: "all",                label: "All",                  color: "#a1a1aa" },
  { value: "draft",              label: "Draft",                color: "#a1a1aa" },
  { value: "scheduled",      label: "Scheduled",      color: "#3b82f6" },
  { value: "live",                label: "Live",                  color: "#22c55e" },
  { value: "locked",            label: "Locked",            color: "#f59e0b" },
  { value: "resolved",        label: "Resolved",        color: "#a855f7" },
  { value: "cancelled",      label: "Cancelled",      color: "#71717a" },
];

const APPROVAL_FILTERS = [
  { value: "all",                          label: "All approvals" },
  { value: "draft",                      label: "Draft" },
  { value: "pending_review",  label: "Pending review" },
  { value: "approved",              label: "Approved" },
  { value: "rejected",              label: "Rejected" },
];


// ─── Helpers ──────────────────────────────────────────────────────────
function fmtDate(s) {
  if (!s) return "—";
  try { return new Date(s).toLocaleString(undefined,
        { dateStyle: "medium", timeStyle: "short" }); }
  catch { return s; }
}

function api(method, url, body) {
  return axios({ method, url, data: body, withCredentials: true })
    .then((r) => r.data)
    .catch((err) => {
      const detail = err?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail
                  : detail?.message || err.message;
      throw new Error(msg || "Request failed");
    });
}


// ─── Status pill ──────────────────────────────────────────────────────
function StatusPill({ status, approval }) {
  const def = STATUS_FILTERS.find((s) => s.value === status);
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <span data-testid={`status-pill-${status}`}
              style={{ fontSize: 10, letterSpacing: 0.7, fontWeight: 700,
                          padding: "3px 8px", borderRadius: 999,
                          textTransform: "uppercase",
                          background: `${def?.color || "#666"}22`,
                          color: def?.color || "#aaa" }}>
        {def?.label || status}
      </span>
      {approval === "pending_review" && (
        <span data-testid="approval-pill-pending"
                style={{ fontSize: 10, letterSpacing: 0.7, fontWeight: 700,
                            padding: "3px 8px", borderRadius: 999,
                            textTransform: "uppercase",
                            background: "#fbbf2422", color: "#fbbf24" }}>
          PENDING REVIEW
        </span>
      )}
      {approval === "rejected" && (
        <span data-testid="approval-pill-rejected"
                style={{ fontSize: 10, letterSpacing: 0.7, fontWeight: 700,
                            padding: "3px 8px", borderRadius: 999,
                            textTransform: "uppercase",
                            background: "#ef444422", color: "#ef4444" }}>
          REJECTED
        </span>
      )}
    </div>
  );
}


// ─── Compliance panel ─────────────────────────────────────────────────
function CompliancePanel({ items, onCreate, creating, onSelect, selectedId }) {
  const [form, setForm] = useState({
    name: "", region: "", terms_text: "",
    no_purchase_necessary_text: "No purchase necessary to enter. All entries are free.",
    void_where_prohibited: "Void where prohibited by law.",
    age_restriction: 18, is_default: false,
  });
  const [open, setOpen] = useState(items.length === 0);

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  async function submit() {
    if (!form.name || form.terms_text.length < 10) {
      toast.error("Name and terms text (≥10 chars) are required.");
      return;
    }
    await onCreate(form);
    setForm({
      name: "", region: "", terms_text: "",
      no_purchase_necessary_text: form.no_purchase_necessary_text,
      void_where_prohibited: form.void_where_prohibited,
      age_restriction: 18, is_default: false,
    });
  }

  return (
    <div data-testid="compliance-panel"
            style={{ background: "#0c0c10",
                        border: "1px solid rgba(255,255,255,0.08)",
                        borderRadius: 10, padding: 16, marginBottom: 18 }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                          alignItems: "center", marginBottom: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <ShieldCheck size={14} color="#22c55e" />
          <h3 style={{ margin: 0, fontSize: 14, color: "#e7e7ea" }}>
            Compliance settings
          </h3>
          <span style={{ fontSize: 11, color: "#71717a" }}>
            {items.length} on file
          </span>
        </div>
        <button onClick={() => setOpen(!open)}
                    data-testid="compliance-toggle"
                    style={{ background: "transparent", border: "1px solid rgba(255,255,255,0.12)",
                                color: "#e7e7ea", padding: "5px 10px", borderRadius: 6,
                                fontSize: 11, cursor: "pointer" }}>
          {open ? "Hide" : "Manage"}
        </button>
      </div>
      <p style={{ fontSize: 11, color: "#9aa3af", margin: "0 0 12px" }}>
        Every campaign must link a compliance row before it can be submitted for
        approval.  Terms must mention &quot;no purchase necessary&quot; and &quot;void where prohibited&quot;.
      </p>
      {open && (
        <>
          <div style={{ display: "grid",
                              gridTemplateColumns: "1fr 1fr",
                              gap: 12, marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: "#9aa3af" }}>
              Name
              <input value={form.name}
                          onChange={(e) => set("name", e.target.value)}
                          placeholder="e.g. UAE General Default"
                          data-testid="compliance-name-input"
                          style={inputStyle} />
            </label>
            <label style={{ fontSize: 11, color: "#9aa3af" }}>
              Region (optional)
              <input value={form.region}
                          onChange={(e) => set("region", e.target.value)}
                          placeholder="UAE, US, IN…"
                          data-testid="compliance-region-input"
                          style={inputStyle} />
            </label>
          </div>
          <label style={{ fontSize: 11, color: "#9aa3af", display: "block",
                                marginBottom: 12 }}>
            Terms text *
            <textarea value={form.terms_text} rows={4}
                              onChange={(e) => set("terms_text", e.target.value)}
                              placeholder="Free promotional prediction contest.  No purchase necessary.  Void where prohibited.  Participants 18+ only.  …"
                              data-testid="compliance-terms-input"
                              style={{ ...inputStyle, fontFamily: "ui-monospace, monospace",
                                          minHeight: 90, resize: "vertical" }} />
          </label>
          <div style={{ display: "grid",
                              gridTemplateColumns: "1fr 1fr 100px",
                              gap: 12, marginBottom: 12 }}>
            <label style={{ fontSize: 11, color: "#9aa3af" }}>
              &quot;No purchase necessary&quot; copy
              <input value={form.no_purchase_necessary_text}
                          onChange={(e) => set("no_purchase_necessary_text", e.target.value)}
                          data-testid="compliance-npn-input"
                          style={inputStyle} />
            </label>
            <label style={{ fontSize: 11, color: "#9aa3af" }}>
              &quot;Void where prohibited&quot; copy
              <input value={form.void_where_prohibited}
                          onChange={(e) => set("void_where_prohibited", e.target.value)}
                          data-testid="compliance-void-input"
                          style={inputStyle} />
            </label>
            <label style={{ fontSize: 11, color: "#9aa3af" }}>
              Age 18+
              <input type="number" value={form.age_restriction}
                          onChange={(e) => set("age_restriction", Number(e.target.value || 18))}
                          data-testid="compliance-age-input"
                          style={inputStyle} />
            </label>
          </div>
          <label style={{ fontSize: 12, color: "#e7e7ea",
                                display: "flex", alignItems: "center", gap: 6,
                                marginBottom: 12 }}>
            <input type="checkbox" checked={form.is_default}
                        data-testid="compliance-default-input"
                        onChange={(e) => set("is_default", e.target.checked)} />
            Set as default for new campaigns
          </label>
          <button onClick={submit} disabled={creating}
                      data-testid="compliance-create-btn"
                      style={btnPrimaryStyle}>
            {creating ? <Loader2 size={12} className="spin" /> : <Plus size={12} />}
            Save compliance row
          </button>

          {items.length > 0 && (
            <div style={{ marginTop: 16,
                                borderTop: "1px solid rgba(255,255,255,0.06)",
                                paddingTop: 12 }}>
              <div style={{ fontSize: 11, color: "#9aa3af", marginBottom: 8 }}>
                Existing rows ({items.length})
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {items.map((c) => (
                  <button key={c.settings_id}
                                onClick={() => onSelect(c.settings_id)}
                                data-testid={`compliance-row-${c.settings_id}`}
                                style={{ ...listRowStyle,
                                            borderColor: selectedId === c.settings_id
                                              ? "#22c55e" : "rgba(255,255,255,0.06)",
                                            background: selectedId === c.settings_id
                                              ? "rgba(34,197,94,0.06)" : "#0a0a0c" }}>
                    <div style={{ flex: 1, textAlign: "left" }}>
                      <div style={{ fontSize: 13, color: "#e7e7ea", fontWeight: 600 }}>
                        {c.name}
                        {c.is_default && (
                          <span style={{ fontSize: 9, color: "#22c55e",
                                              marginLeft: 6, fontWeight: 700,
                                              letterSpacing: 0.5 }}>DEFAULT</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: "#9aa3af", marginTop: 2 }}>
                        {c.region || "Global"} · Age {c.age_restriction}+
                          · {c.terms_text.slice(0, 80)}{c.terms_text.length > 80 ? "…" : ""}
                      </div>
                    </div>
                    {selectedId === c.settings_id && (
                      <Check size={14} color="#22c55e" />
                    )}
                  </button>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}


// ─── Create / Edit drawer ─────────────────────────────────────────────
function CampaignWizard({ open, onClose, onCreated, meta, complianceItems }) {
  const [form, setForm] = useState(emptyForm());
  const [saving, setSaving] = useState(false);

  function emptyForm() {
    const inMin = (m) => {
      const d = new Date();  d.setMinutes(d.getMinutes() + m);
      return d.toISOString().slice(0, 16); // datetime-local format
    };
    return {
      title: "", description: "", event_type: "club_event",
      event_label: "", city: "", region: "", language: "en",
      prompt: "", options: [{ label: "" }, { label: "" }],
      start_time: inMin(15),
      lock_time: inMin(90),
      compliance_settings_id: "",
      winner_rules: {
        scoring: "winner_takes_all",
        max_winners: 1,
        tiebreaker: "first_to_pick",
      },
    };
  }

  useEffect(() => { if (open) setForm(emptyForm()); }, [open]);
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    // Default to the default compliance row
    if (open && !form.compliance_settings_id) {
      const def = complianceItems.find((c) => c.is_default) || complianceItems[0];
      if (def) setForm((f) => ({ ...f, compliance_settings_id: def.settings_id }));
    }
  }, [open, complianceItems]);  // eslint-disable-line react-hooks/exhaustive-deps
  /* eslint-enable react-hooks/set-state-in-effect */

  if (!open) return null;

  function set(k, v) { setForm((f) => ({ ...f, [k]: v })); }

  function addOption() {
    setForm((f) => ({ ...f, options: [...f.options, { label: "" }] }));
  }
  function removeOption(i) {
    setForm((f) => ({ ...f, options: f.options.filter((_, j) => j !== i) }));
  }
  function setOption(i, value) {
    setForm((f) => ({ ...f,
        options: f.options.map((o, j) => j === i ? { ...o, label: value } : o) }));
  }

  async function submit() {
    const cleanOptions = form.options.map((o) => o.label.trim()).filter(Boolean);
    if (form.title.trim().length < 4) {
      toast.error("Title must be at least 4 characters.");
      return;
    }
    if (form.prompt.trim().length < 4) {
      toast.error("Question prompt is required.");
      return;
    }
    if (cleanOptions.length < 2) {
      toast.error("At least 2 answer options are required.");
      return;
    }
    if (!form.compliance_settings_id) {
      toast.error("Pick a compliance settings row before creating.");
      return;
    }
    const lockMs = new Date(form.lock_time).getTime();
    const startMs = new Date(form.start_time).getTime();
    if (lockMs <= startMs) {
      toast.error("Lock time must be after start time.");
      return;
    }
    setSaving(true);
    try {
      const payload = {
        title: form.title.trim(),
        description: form.description.trim() || null,
        event_type: form.event_type,
        event_label: form.event_label.trim() || null,
        city: form.city.trim() || null,
        region: form.region.trim() || null,
        language: form.language || "en",
        question: {
          prompt: form.prompt.trim(),
          answer_options: cleanOptions.map((label) => ({ label })),
        },
        start_time: new Date(form.start_time).toISOString(),
        lock_time: new Date(form.lock_time).toISOString(),
        compliance_settings_id: form.compliance_settings_id,
        winner_rules: form.winner_rules,
      };
      const r = await api("POST", `${PW}/campaigns`, payload);
      toast.success("Campaign created in draft state.");
      onCreated(r.campaign);
      onClose();
    } catch (err) {
      toast.error(err.message || "Create failed");
    } finally {
      setSaving(false);
    }
  }

  const eventTypes = meta?.event_types || [];

  return (
    <div data-testid="campaign-wizard-backdrop"
            onClick={onClose}
            style={backdropStyle}>
      <div data-testid="campaign-wizard"
              onClick={(e) => e.stopPropagation()}
              style={{ ...drawerStyle, maxWidth: 640 }}>
        <div style={drawerHeaderStyle}>
          <div>
            <div style={{ fontSize: 11, color: "#9aa3af", letterSpacing: 0.5 }}>
              CREATE PREDICT &amp; WIN CAMPAIGN
            </div>
            <h2 style={{ margin: "4px 0 0", color: "#e7e7ea", fontSize: 18 }}>
              New community prediction
            </h2>
          </div>
          <button onClick={onClose} style={iconBtnStyle}
                      data-testid="wizard-close"><X size={16} /></button>
        </div>
        <div style={drawerBodyStyle}>
          <Field label="Title *">
            <input value={form.title}
                        onChange={(e) => set("title", e.target.value)}
                        placeholder="Friday Night Karaoke Prediction"
                        data-testid="wizard-title-input"
                        style={inputStyle} />
          </Field>
          <Field label="Description">
            <textarea value={form.description} rows={2}
                              onChange={(e) => set("description", e.target.value)}
                              placeholder="Who will sing the most songs tonight?"
                              data-testid="wizard-description-input"
                              style={{ ...inputStyle, minHeight: 56,
                                          fontFamily: "ui-sans-serif" }} />
          </Field>
          <div style={twoColStyle}>
            <Field label="Event type *">
              <select value={form.event_type}
                            onChange={(e) => set("event_type", e.target.value)}
                            data-testid="wizard-event-type-select"
                            style={inputStyle}>
                {eventTypes.map((e) => (
                  <option key={e.value} value={e.value}
                                disabled={e.disabled}
                                data-testid={`event-type-option-${e.value}`}
                                title={e.disabled_reason || ""}>
                    {e.label}{e.disabled ? " — DISABLED (legal review)" : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Event label">
              <input value={form.event_label}
                          onChange={(e) => set("event_label", e.target.value)}
                          placeholder="Karaoke Night @ Smoke Karak"
                          data-testid="wizard-event-label-input"
                          style={inputStyle} />
            </Field>
          </div>
          <div style={twoColStyle}>
            <Field label="City">
              <input value={form.city}
                          onChange={(e) => set("city", e.target.value)}
                          placeholder="Dubai"
                          data-testid="wizard-city-input"
                          style={inputStyle} />
            </Field>
            <Field label="Region">
              <input value={form.region}
                          onChange={(e) => set("region", e.target.value)}
                          placeholder="UAE"
                          data-testid="wizard-region-input"
                          style={inputStyle} />
            </Field>
          </div>

          <div style={sectionDividerStyle}>QUESTION</div>
          <Field label="Prompt *">
            <input value={form.prompt}
                        onChange={(e) => set("prompt", e.target.value)}
                        placeholder="Who will sing the most songs?"
                        data-testid="wizard-prompt-input"
                        style={inputStyle} />
          </Field>
          <Field label={`Answer options * (${form.options.length}, need ≥ 2)`}>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {form.options.map((o, i) => (
                <div key={i} style={{ display: "flex", gap: 6 }}>
                  <input value={o.label}
                              onChange={(e) => setOption(i, e.target.value)}
                              placeholder={`Option ${i + 1}`}
                              data-testid={`wizard-option-${i}-input`}
                              style={{ ...inputStyle, marginTop: 0, flex: 1 }} />
                  {form.options.length > 2 && (
                    <button onClick={() => removeOption(i)}
                                data-testid={`wizard-option-${i}-remove`}
                                style={iconBtnStyle}>
                      <X size={14} />
                    </button>
                  )}
                </div>
              ))}
              <button onClick={addOption}
                          data-testid="wizard-add-option"
                          style={{ ...btnGhostStyle, alignSelf: "flex-start" }}>
                <Plus size={12} /> Add option
              </button>
            </div>
          </Field>

          <div style={sectionDividerStyle}>SCHEDULE</div>
          <div style={twoColStyle}>
            <Field label="Start time *">
              <input type="datetime-local" value={form.start_time}
                          onChange={(e) => set("start_time", e.target.value)}
                          data-testid="wizard-start-time-input"
                          style={inputStyle} />
            </Field>
            <Field label="Lock time * (must be > start + 5 min)">
              <input type="datetime-local" value={form.lock_time}
                          onChange={(e) => set("lock_time", e.target.value)}
                          data-testid="wizard-lock-time-input"
                          style={inputStyle} />
            </Field>
          </div>

          <div style={sectionDividerStyle}>WINNER RULES</div>
          <div style={twoColStyle}>
            <Field label="Scoring">
              <select value={form.winner_rules.scoring}
                            onChange={(e) => set("winner_rules",
                                { ...form.winner_rules, scoring: e.target.value })}
                            data-testid="wizard-scoring-select"
                            style={inputStyle}>
                <option value="winner_takes_all">Winner takes all</option>
                <option value="points_per_correct">Points per correct</option>
              </select>
            </Field>
            <Field label="Tiebreaker">
              <select value={form.winner_rules.tiebreaker}
                            onChange={(e) => set("winner_rules",
                                { ...form.winner_rules, tiebreaker: e.target.value })}
                            data-testid="wizard-tiebreaker-select"
                            style={inputStyle}>
                <option value="first_to_pick">First to pick</option>
                <option value="random">Random</option>
              </select>
            </Field>
          </div>

          <div style={sectionDividerStyle}>COMPLIANCE</div>
          <Field label="Linked compliance row *">
            <select value={form.compliance_settings_id}
                          onChange={(e) => set("compliance_settings_id", e.target.value)}
                          data-testid="wizard-compliance-select"
                          style={inputStyle}>
              <option value="">— Pick a compliance row —</option>
              {complianceItems.map((c) => (
                <option key={c.settings_id} value={c.settings_id}>
                  {c.name}{c.is_default ? " (default)" : ""}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div style={drawerFooterStyle}>
          <button onClick={onClose} style={btnGhostStyle}
                      data-testid="wizard-cancel">Cancel</button>
          <button onClick={submit} disabled={saving}
                      data-testid="wizard-submit"
                      style={btnPrimaryStyle}>
            {saving ? <Loader2 size={12} className="spin" /> : <Plus size={12} />}
            Create draft
          </button>
        </div>
      </div>
    </div>
  );
}


// ─── Detail drawer ────────────────────────────────────────────────────
function CampaignDetail({ campaignId, onClose, onMutated }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    if (!campaignId) return;
    setLoading(true);
    try {
      const r = await api("GET", `${PW}/campaigns/${campaignId}`);
      setData(r);
    } catch (e) {
      toast.error(e.message || "Load failed");
    } finally { setLoading(false); }
  }, [campaignId]);

  useEffect(() => { refresh(); }, [refresh]);

  const action = useCallback(async (verb, body) => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setBusy(true);
    try {
      await api("POST", `${PW}/campaigns/${campaignId}/${verb}`, body || {});
      toast.success(`Action '${verb}' applied.`);
      await refresh();
      onMutated?.();
    } catch (e) {
      toast.error(e.message || `${verb} failed`);
    } finally {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setBusy(false);
    }
  }, [campaignId, refresh, onMutated]);

  async function addPrize() {
    const title = prompt("Prize title:");
    if (!title) return;
    const points = prompt("Prize amount (number, optional):");
    setBusy(true);
    try {
      await api("POST", `${PW}/campaigns/${campaignId}/prizes`, {
        rank: (data?.prizes?.length || 0) + 1,
        title: title.trim(),
        prize_kind: "points",
        value_amount: points ? Number(points) : null,
        value_currency: points ? "BC" : null,
        inventory_total: 1,
      });
      toast.success("Prize added.");
      await refresh();
      onMutated?.();
    } catch (e) {
      toast.error(e.message || "Prize add failed");
    } finally { setBusy(false); }
  }

  async function deletePrize(pid) {
    if (!window.confirm("Remove this prize?")) return;
    setBusy(true);
    try {
      await api("DELETE", `${PW}/campaigns/${campaignId}/prizes/${pid}`);
      toast.success("Prize removed.");
      await refresh();
      onMutated?.();
    } catch (e) {
      toast.error(e.message || "Prize remove failed");
    } finally { setBusy(false); }
  }

  if (!campaignId) return null;
  return (
    <div data-testid="campaign-detail-backdrop"
            onClick={onClose}
            style={backdropStyle}>
      <div data-testid="campaign-detail"
              onClick={(e) => e.stopPropagation()}
              style={drawerStyle}>
        <div style={drawerHeaderStyle}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, color: "#9aa3af", letterSpacing: 0.5 }}>
              CAMPAIGN · {campaignId}
            </div>
            <h2 style={{ margin: "4px 0 0", color: "#e7e7ea", fontSize: 18,
                                whiteSpace: "nowrap", overflow: "hidden",
                                textOverflow: "ellipsis" }}>
              {data?.campaign?.title || "—"}
            </h2>
            {data && (
              <div style={{ marginTop: 6 }}>
                <StatusPill status={data.campaign.status}
                                      approval={data.campaign.approval_status} />
              </div>
            )}
          </div>
          <button onClick={onClose} style={iconBtnStyle}
                      data-testid="detail-close"><X size={16} /></button>
        </div>

        {loading || !data ? (
          <div style={{ padding: 32, textAlign: "center", color: "#9aa3af" }}>
            <Loader2 size={20} className="spin" />
          </div>
        ) : (
          <div style={drawerBodyStyle}>
            {data.campaign.approval_status === "rejected" && (
              <div data-testid="detail-rejection-banner"
                      style={{ background: "rgba(239,68,68,0.10)",
                                  border: "1px solid rgba(239,68,68,0.35)",
                                  padding: 10, borderRadius: 6,
                                  fontSize: 12, color: "#fca5a5",
                                  marginBottom: 12 }}>
                <AlertTriangle size={12} style={{ verticalAlign: -1, marginRight: 4 }} />
                Rejected: {data.campaign.approval_reason || "no reason supplied"}
              </div>
            )}

            <DetailRow label="Event" value={`${data.campaign.event_type}${
              data.campaign.event_label ? ` · ${data.campaign.event_label}` : ""}`} />
            <DetailRow label="City / Region"
                          value={`${data.campaign.city || "—"} / ${data.campaign.region || "—"}`} />
            <DetailRow label="Start" value={fmtDate(data.campaign.start_time)} />
            <DetailRow label="Lock"   value={fmtDate(data.campaign.lock_time)} />
            <DetailRow label="Description"
                          value={data.campaign.description || "—"} />

            <div style={sectionDividerStyle}>QUESTION</div>
            <DetailRow label="Prompt" value={data.campaign.question?.prompt || "—"} />
            <div style={{ display: "flex", flexDirection: "column", gap: 4,
                                marginTop: 6 }}>
              {(data.campaign.question?.answer_options || []).map((o) => (
                <div key={o.option_id}
                        data-testid={`detail-option-${o.option_id}`}
                        style={{ background: "#0a0a0c",
                                    border: "1px solid rgba(255,255,255,0.06)",
                                    padding: "6px 10px", borderRadius: 6,
                                    fontSize: 12, color: "#e7e7ea",
                                    display: "flex", justifyContent: "space-between" }}>
                  <span>{o.label}</span>
                  {data.resolution && data.resolution.winning_option_id === o.option_id && (
                    <span style={{ fontSize: 10, color: "#22c55e", fontWeight: 700,
                                          letterSpacing: 0.5 }}>
                      <Trophy size={10} style={{ verticalAlign: -1, marginRight: 2 }} /> WINNER
                    </span>
                  )}
                </div>
              ))}
            </div>

            <div style={sectionDividerStyle}>
              PRIZES ({data.prizes.length})
              {(data.campaign.approval_status === "draft" ||
                  data.campaign.approval_status === "rejected") && (
                <button onClick={addPrize} disabled={busy}
                            data-testid="detail-prize-add"
                            style={{ ...btnGhostStyle, marginLeft: "auto",
                                        padding: "3px 8px", fontSize: 11 }}>
                  <Plus size={11} /> Add prize
                </button>
              )}
            </div>
            {data.prizes.length === 0 ? (
              <div style={{ fontSize: 12, color: "#71717a",
                                  padding: 12, textAlign: "center",
                                  border: "1px dashed rgba(255,255,255,0.10)",
                                  borderRadius: 6 }}>
                No prizes yet — campaign cannot submit for approval until at least one is added.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {data.prizes.map((p) => (
                  <div key={p.prize_id}
                          data-testid={`detail-prize-${p.prize_id}`}
                          style={{ ...listRowStyle, padding: "8px 10px" }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 12, color: "#e7e7ea", fontWeight: 600 }}>
                        #{p.rank} · {p.title}
                      </div>
                      <div style={{ fontSize: 11, color: "#9aa3af", marginTop: 2 }}>
                        {p.prize_kind}
                        {p.value_amount != null
                          ? ` · ${p.value_amount} ${p.value_currency || ""}` : ""}
                        {" · "}inv {p.inventory_remaining}/{p.inventory_total}
                      </div>
                    </div>
                    {(data.campaign.approval_status === "draft" ||
                        data.campaign.approval_status === "rejected") && (
                      <button onClick={() => deletePrize(p.prize_id)}
                                  data-testid={`detail-prize-delete-${p.prize_id}`}
                                  style={iconBtnStyle}>
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}

            {data.compliance && (
              <>
                <div style={sectionDividerStyle}>COMPLIANCE</div>
                <DetailRow label="Linked" value={data.compliance.name} />
                <DetailRow label="Region"
                              value={data.compliance.region || "Global"} />
                <DetailRow label="Age"
                              value={`${data.compliance.age_restriction}+`} />
                <div style={{ fontSize: 11, color: "#9aa3af", marginTop: 8,
                                    background: "#0a0a0c", padding: 8, borderRadius: 4,
                                    fontFamily: "ui-monospace, monospace",
                                    whiteSpace: "pre-wrap" }}>
                  {data.compliance.terms_text}
                </div>
              </>
            )}

            <div style={sectionDividerStyle}>ACTIONS</div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {data.campaign.approval_status === "draft" && (
                <button onClick={() => action("submit-approval")}
                            disabled={busy}
                            data-testid="action-submit-approval"
                            style={btnPrimaryStyle}>
                  <Sparkles size={12} /> Submit for approval
                </button>
              )}
              {data.campaign.approval_status === "pending_review" && (
                <>
                  <button onClick={() => action("approve")}
                              disabled={busy}
                              data-testid="action-approve"
                              style={btnSuccessStyle}>
                    <Check size={12} /> Approve
                  </button>
                  <button onClick={() => setRejectOpen(true)}
                              disabled={busy}
                              data-testid="action-reject"
                              style={btnDangerStyle}>
                    <X size={12} /> Reject
                  </button>
                </>
              )}
              {data.campaign.status === "live" && (
                <button onClick={() => action("lock")}
                            disabled={busy}
                            data-testid="action-lock"
                            style={btnGhostStyle}>
                  <Lock size={12} /> Lock now
                </button>
              )}
              {(data.campaign.status === "locked" || data.campaign.status === "live") && (
                <button onClick={() => setResolveOpen(true)}
                            disabled={busy}
                            data-testid="action-force-resolve"
                            style={btnPrimaryStyle}>
                  <Flag size={12} /> Force resolve
                </button>
              )}
              {data.campaign.status !== "resolved" &&
                  data.campaign.status !== "cancelled" && (
                <button onClick={() => setCancelOpen(true)}
                            disabled={busy}
                            data-testid="action-cancel"
                            style={btnGhostStyle}>
                  <AlertTriangle size={12} /> Cancel
                </button>
              )}
            </div>
          </div>
        )}

        {rejectOpen && (
          <ReasonModal title="Reject campaign"
                                placeholder="Reason for rejection (≥4 chars)"
                                testId="reject-modal"
                                onCancel={() => setRejectOpen(false)}
                                onSubmit={async (reason) => {
                                  await action("reject", { reason });
                                  setRejectOpen(false);
                                }} />
        )}
        {cancelOpen && (
          <ReasonModal title="Cancel campaign"
                                placeholder="Reason for cancellation"
                                testId="cancel-modal"
                                onCancel={() => setCancelOpen(false)}
                                onSubmit={async (reason) => {
                                  await action("cancel", { reason });
                                  setCancelOpen(false);
                                }} />
        )}
        {resolveOpen && data && (
          <ResolveModal options={data.campaign.question?.answer_options || []}
                                  onCancel={() => setResolveOpen(false)}
                                  onSubmit={async (body) => {
                                    await action("force-resolve", body);
                                    setResolveOpen(false);
                                  }} />
        )}
      </div>
    </div>
  );
}


// ─── Reason modal (reject / cancel) ───────────────────────────────────
function ReasonModal({ title, placeholder, testId, onCancel, onSubmit }) {
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <div data-testid={`${testId}-backdrop`}
            onClick={onCancel}
            style={{ ...backdropStyle, zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()}
              style={{ ...drawerStyle, maxWidth: 480, height: "auto",
                          alignSelf: "center" }}
              data-testid={testId}>
        <div style={drawerHeaderStyle}>
          <h3 style={{ margin: 0, color: "#e7e7ea", fontSize: 15 }}>{title}</h3>
          <button onClick={onCancel} style={iconBtnStyle}><X size={16} /></button>
        </div>
        <div style={{ ...drawerBodyStyle, paddingBottom: 0 }}>
          <textarea value={text} rows={5}
                            onChange={(e) => setText(e.target.value)}
                            placeholder={placeholder}
                            data-testid={`${testId}-input`}
                            style={{ ...inputStyle, minHeight: 100,
                                        fontFamily: "ui-sans-serif", resize: "vertical" }} />
        </div>
        <div style={drawerFooterStyle}>
          <button onClick={onCancel} style={btnGhostStyle}
                      data-testid={`${testId}-cancel`}>Back</button>
          <button onClick={async () => {
                          if (text.trim().length < 4) {
                            toast.error("Reason must be at least 4 chars."); return;
                          }
                          setSaving(true);
                          try { await onSubmit(text.trim()); }
                          finally { setSaving(false); }
                        }}
                      disabled={saving}
                      data-testid={`${testId}-confirm`}
                      style={btnDangerStyle}>
            {saving ? <Loader2 size={12} className="spin" /> : <Check size={12} />}
            Confirm
          </button>
        </div>
      </div>
    </div>
  );
}


// ─── Force-resolve modal ──────────────────────────────────────────────
function ResolveModal({ options, onCancel, onSubmit }) {
  const [winning, setWinning] = useState(options[0]?.option_id || "");
  const [notes, setNotes] = useState("");
  const [source, setSource] = useState("");
  const [saving, setSaving] = useState(false);
  return (
    <div data-testid="resolve-modal-backdrop"
            onClick={onCancel}
            style={{ ...backdropStyle, zIndex: 60 }}>
      <div onClick={(e) => e.stopPropagation()}
              style={{ ...drawerStyle, maxWidth: 480, height: "auto",
                          alignSelf: "center" }}
              data-testid="resolve-modal">
        <div style={drawerHeaderStyle}>
          <h3 style={{ margin: 0, color: "#e7e7ea", fontSize: 15 }}>Force resolve</h3>
          <button onClick={onCancel} style={iconBtnStyle}><X size={16} /></button>
        </div>
        <div style={drawerBodyStyle}>
          <Field label="Winning option *">
            <select value={winning}
                          onChange={(e) => setWinning(e.target.value)}
                          data-testid="resolve-winning-select"
                          style={inputStyle}>
              {options.map((o) => (
                <option key={o.option_id} value={o.option_id}>{o.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Audit notes">
            <textarea value={notes} rows={3}
                              onChange={(e) => setNotes(e.target.value)}
                              data-testid="resolve-notes-input"
                              placeholder="What was the observed outcome?"
                              style={{ ...inputStyle, minHeight: 80,
                                          resize: "vertical" }} />
          </Field>
          <Field label="Source URL (optional)">
            <input value={source}
                        onChange={(e) => setSource(e.target.value)}
                        placeholder="https://"
                        data-testid="resolve-source-input"
                        style={inputStyle} />
          </Field>
        </div>
        <div style={drawerFooterStyle}>
          <button onClick={onCancel} style={btnGhostStyle}>Back</button>
          <button onClick={async () => {
                          if (!winning) { toast.error("Pick a winning option"); return; }
                          setSaving(true);
                          try {
                            await onSubmit({
                              winning_option_id: winning,
                              audit_notes: notes.trim() || null,
                              data_source_url: source.trim() || null,
                            });
                          } finally { setSaving(false); }
                        }}
                      disabled={saving}
                      data-testid="resolve-confirm"
                      style={btnPrimaryStyle}>
            {saving ? <Loader2 size={12} className="spin" /> : <Flag size={12} />}
            Resolve
          </button>
        </div>
      </div>
    </div>
  );
}


// ─── Main page ────────────────────────────────────────────────────────
export default function PredictWinCampaigns() {
  const [meta, setMeta] = useState(null);
  const [compliance, setCompliance] = useState([]);
  const [selectedCompliance, setSelectedCompliance] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [statusFilter, setStatusFilter] = useState("all");
  const [approvalFilter, setApprovalFilter] = useState("all");
  const [wizardOpen, setWizardOpen] = useState(false);
  const [predexonOpen, setPredexonOpen] = useState(false);
  const [openCampaign, setOpenCampaign] = useState(null);
  const [creatingCompliance, setCreatingCompliance] = useState(false);

  const loadMeta = useCallback(async () => {
    try {
      const [m, p] = await Promise.all([
        api("GET", `${PW}/event-types`),
        api("GET", `${PW}/providers`),
      ]);
      setMeta({ ...m, providers: p.items });
    } catch (e) { toast.error(e.message); }
  }, []);

  const loadCompliance = useCallback(async () => {
    try {
      const r = await api("GET", `${PW}/compliance`);
      setCompliance(r.items);
      const def = r.items.find((c) => c.is_default);
      if (def) setSelectedCompliance(def.settings_id);
    } catch (e) { toast.error(e.message); }
  }, []);

  const loadList = useCallback(async () => {
    setLoadingList(true);
    try {
      const params = new URLSearchParams();
      if (statusFilter !== "all") params.append("status", statusFilter);
      if (approvalFilter !== "all") params.append("approval_status", approvalFilter);
      const url = `${PW}/campaigns${params.toString() ? "?" + params.toString() : ""}`;
      const r = await api("GET", url);
      setCampaigns(r.items);
    } catch (e) {
      toast.error(e.message || "List load failed");
    } finally { setLoadingList(false); }
  }, [statusFilter, approvalFilter]);

  useEffect(() => { loadMeta(); }, [loadMeta]);
  useEffect(() => { loadCompliance(); }, [loadCompliance]);
  useEffect(() => { loadList(); }, [loadList]);

  const createCompliance = useCallback(async (payload) => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setCreatingCompliance(true);
    try {
      const r = await api("POST", `${PW}/compliance`, payload);
      toast.success("Compliance row saved.");
      await loadCompliance();
      setSelectedCompliance(r.settings.settings_id);
    } catch (e) {
      toast.error(e.message || "Compliance save failed");
    } finally {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setCreatingCompliance(false);
    }
  }, [loadCompliance]);

  // Live count summary
  const counts = useMemo(() => {
    const m = {};
    for (const c of campaigns) m[c.status] = (m[c.status] || 0) + 1;
    return m;
  }, [campaigns]);
  const pendingCount = useMemo(
    () => campaigns.filter((c) => c.approval_status === "pending_review").length,
    [campaigns],
  );

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#080809" }}>
      <Toaster theme="dark" position="bottom-right" richColors />
      <AdminSubNav />
      <main style={{ flex: 1, padding: 24, maxWidth: 1180 }}
              data-testid="predict-win-page">
        <div style={{ display: "flex", justifyContent: "space-between",
                            alignItems: "flex-start", marginBottom: 18,
                            flexWrap: "wrap", gap: 12 }}>
          <div>
            <div style={{ fontSize: 11, color: "#9aa3af", letterSpacing: 0.8 }}>
              SUB-PHASE E1 · PROMOTIONAL CONTESTS · ADMIN ONLY
            </div>
            <h1 style={{ margin: "6px 0 0", fontSize: 22, color: "#e7e7ea" }}>
              Predict &amp; Win campaigns
            </h1>
            <p style={{ fontSize: 12, color: "#9aa3af", margin: "6px 0 0",
                              maxWidth: 720 }}>
              Free promotional prediction contests. No purchase required. Listeners
              make picks and win prizes based on correct outcomes. Every campaign must
              link a compliance row and have at least one prize before submission.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button onClick={() => setPredexonOpen(true)}
                        data-testid="open-predexon-btn"
                        style={{ ...btnGhostStyle, padding: "8px 14px",
                                    fontSize: 13, borderColor: "rgba(34,211,238,0.3)",
                                    color: "#22d3ee" }}>
              <Database size={14} /> Import from Predexon
            </button>
            <button onClick={() => setWizardOpen(true)}
                        data-testid="open-wizard-btn"
                        style={{ ...btnPrimaryStyle, padding: "8px 14px",
                                    fontSize: 13 }}>
              <Plus size={14} /> New campaign
            </button>
          </div>
        </div>

        {/* Stat strip */}
        <div data-testid="stat-strip"
                style={{ display: "grid",
                            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                            gap: 10, marginBottom: 18 }}>
          {[
            { label: "Total", value: campaigns.length, color: "#e7e7ea",
              icon: FileText, testid: "stat-total" },
            { label: "Pending review", value: pendingCount, color: "#fbbf24",
              icon: AlertTriangle, testid: "stat-pending" },
            { label: "Scheduled", value: counts.scheduled || 0, color: "#3b82f6",
              icon: Sparkles, testid: "stat-scheduled" },
            { label: "Live", value: counts.live || 0, color: "#22c55e",
              icon: ShieldCheck, testid: "stat-live" },
            { label: "Resolved", value: counts.resolved || 0, color: "#a855f7",
              icon: Trophy, testid: "stat-resolved" },
          ].map((s) => (
            <div key={s.label} data-testid={s.testid}
                    style={{ background: "#0c0c10",
                                border: "1px solid rgba(255,255,255,0.06)",
                                borderRadius: 8, padding: 12,
                                display: "flex", gap: 10, alignItems: "center" }}>
              <s.icon size={16} color={s.color} />
              <div>
                <div style={{ fontSize: 18, color: s.color, fontWeight: 700 }}>{s.value}</div>
                <div style={{ fontSize: 10, color: "#9aa3af",
                                    textTransform: "uppercase", letterSpacing: 0.6 }}>
                  {s.label}
                </div>
              </div>
            </div>
          ))}
        </div>

        <CompliancePanel items={compliance}
                                      onCreate={createCompliance}
                                      creating={creatingCompliance}
                                      onSelect={setSelectedCompliance}
                                      selectedId={selectedCompliance} />

        {/* Phase PDX.1 — Predexon auto-curator dashboard section. */}
        <PdxAutoCuratedPanel />

        {/* Filter chips */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6,
                            marginBottom: 12 }}
                data-testid="status-filter-row">
          {STATUS_FILTERS.map((f) => (
            <button key={f.value}
                          onClick={() => setStatusFilter(f.value)}
                          data-testid={`status-filter-${f.value}`}
                          style={{
                            ...chipStyle,
                            background: statusFilter === f.value
                              ? `${f.color}22` : "#0c0c10",
                            color: statusFilter === f.value ? f.color : "#9aa3af",
                            borderColor: statusFilter === f.value
                              ? f.color : "rgba(255,255,255,0.08)",
                          }}>
              {f.label}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6,
                            marginBottom: 18 }}
                data-testid="approval-filter-row">
          {APPROVAL_FILTERS.map((f) => (
            <button key={f.value}
                          onClick={() => setApprovalFilter(f.value)}
                          data-testid={`approval-filter-${f.value}`}
                          style={{
                            ...chipStyle,
                            background: approvalFilter === f.value
                              ? "rgba(245,158,11,0.10)" : "#0c0c10",
                            color: approvalFilter === f.value ? "#f59e0b" : "#9aa3af",
                            borderColor: approvalFilter === f.value
                              ? "#f59e0b" : "rgba(255,255,255,0.08)",
                          }}>
              {f.label}
            </button>
          ))}
        </div>

        {/* List */}
        {loadingList ? (
          <div style={{ padding: 32, textAlign: "center", color: "#9aa3af" }}>
            <Loader2 size={20} className="spin" />
          </div>
        ) : campaigns.length === 0 ? (
          <div data-testid="campaigns-empty"
                  style={{ padding: 32, textAlign: "center", color: "#9aa3af",
                              border: "1px dashed rgba(255,255,255,0.10)",
                              borderRadius: 8, fontSize: 13 }}>
            No campaigns yet. Create your first prediction contest above.
          </div>
        ) : (
          <div data-testid="campaign-list"
                  style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {campaigns.map((c) => (
              <button key={c.campaign_id}
                            onClick={() => setOpenCampaign(c.campaign_id)}
                            data-testid={`campaign-row-${c.campaign_id}`}
                            style={{ ...listRowStyle, cursor: "pointer",
                                        padding: 14, gap: 12 }}>
                <div style={{ flex: 1, textAlign: "left", minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center",
                                      flexWrap: "wrap" }}>
                    <span style={{ fontSize: 14, color: "#e7e7ea", fontWeight: 600 }}>
                      {c.title}
                    </span>
                    <StatusPill status={c.status}
                                          approval={c.approval_status} />
                  </div>
                  <div style={{ fontSize: 11, color: "#9aa3af", marginTop: 4 }}>
                    {c.event_type} · {c.city || "Global"}
                      {" · "}{c.prize_count} prize{c.prize_count !== 1 ? "s" : ""}
                      {" · "}{c.entry_count} pick{c.entry_count !== 1 ? "s" : ""}
                      {" · lock "}{fmtDate(c.lock_time)}
                  </div>
                  {c.event_type === "live_sports_moment" && (
                    <div style={{ fontSize: 10, color: "#ef4444", marginTop: 4 }}>
                      <AlertTriangle size={10}
                          style={{ verticalAlign: -1, marginRight: 2 }} />
                      Legacy live_sports_moment row — disabled pending legal review.
                    </div>
                  )}
                </div>
                <ChevronRight size={16} color="#71717a" />
              </button>
            ))}
          </div>
        )}
      </main>

      {wizardOpen && (
        <CampaignWizard open={wizardOpen}
                                    meta={meta}
                                    complianceItems={compliance}
                                    onClose={() => setWizardOpen(false)}
                                    onCreated={() => { loadList(); }} />
      )}
      <ImportPredexonModal open={predexonOpen}
                                          onClose={() => setPredexonOpen(false)}
                                          onImported={() => loadList()} />
      {openCampaign && (
        <CampaignDetail campaignId={openCampaign}
                                    onClose={() => setOpenCampaign(null)}
                                    onMutated={() => loadList()} />
      )}
    </div>
  );
}


// ─── Small layout helpers ─────────────────────────────────────────────
function Field({ label, children }) {
  return (
    <label style={{ fontSize: 11, color: "#9aa3af", display: "block",
                          marginBottom: 12 }}>
      {label}
      {children}
    </label>
  );
}

function DetailRow({ label, value }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between",
                        alignItems: "flex-start", gap: 12,
                        padding: "6px 0",
                        borderBottom: "1px solid rgba(255,255,255,0.04)" }}>
      <span style={{ fontSize: 11, color: "#71717a", letterSpacing: 0.4 }}>{label}</span>
      <span style={{ fontSize: 12, color: "#e7e7ea", textAlign: "right",
                            whiteSpace: "pre-wrap", flex: 1 }}>{value}</span>
    </div>
  );
}


// ─── Style tokens ─────────────────────────────────────────────────────
const inputStyle = {
  width: "100%", marginTop: 4, padding: "7px 10px",
  background: "#0a0a0c", border: "1px solid rgba(255,255,255,0.10)",
  borderRadius: 5, color: "#e7e7ea", fontSize: 12, outline: "none",
};

const btnPrimaryStyle = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "7px 12px",
  background: "#22d3ee", border: "none", borderRadius: 6,
  color: "#0a0a0c", fontSize: 12, fontWeight: 700,
  cursor: "pointer", letterSpacing: 0.3,
};

const btnSuccessStyle = { ...btnPrimaryStyle, background: "#22c55e" };
const btnDangerStyle = {
  ...btnPrimaryStyle, background: "#ef4444", color: "#fff",
};
const btnGhostStyle = {
  display: "inline-flex", alignItems: "center", gap: 6,
  padding: "6px 10px",
  background: "transparent",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 5, color: "#e7e7ea", fontSize: 12,
  cursor: "pointer",
};
const iconBtnStyle = {
  ...btnGhostStyle, padding: "5px 6px", minWidth: 28,
};

const chipStyle = {
  padding: "5px 12px", borderRadius: 999, border: "1px solid",
  fontSize: 11, fontWeight: 600, cursor: "pointer",
  letterSpacing: 0.4, textTransform: "uppercase",
};

const listRowStyle = {
  display: "flex", alignItems: "center", gap: 8,
  background: "#0c0c10",
  border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: 8, padding: "10px 12px",
  cursor: "default",
  fontFamily: "inherit", textAlign: "left", color: "inherit",
};

const sectionDividerStyle = {
  fontSize: 10, color: "#71717a", letterSpacing: 0.8,
  marginTop: 16, marginBottom: 6, fontWeight: 600,
  display: "flex", alignItems: "center", gap: 4,
  textTransform: "uppercase",
};

const backdropStyle = {
  position: "fixed", inset: 0,
  background: "rgba(0,0,0,0.6)",
  display: "flex", justifyContent: "flex-end",
  zIndex: 50,
};

const drawerStyle = {
  width: "100%", maxWidth: 540,
  background: "#0a0a0c",
  borderLeft: "1px solid rgba(255,255,255,0.08)",
  display: "flex", flexDirection: "column",
  height: "100%",
};

const drawerHeaderStyle = {
  display: "flex", justifyContent: "space-between",
  alignItems: "flex-start", padding: 16,
  borderBottom: "1px solid rgba(255,255,255,0.06)",
  gap: 12,
};

const drawerBodyStyle = {
  flex: 1, overflowY: "auto", padding: 16,
};

const drawerFooterStyle = {
  display: "flex", justifyContent: "flex-end", gap: 8,
  padding: 12,
  borderTop: "1px solid rgba(255,255,255,0.06)",
};

const twoColStyle = {
  display: "grid", gridTemplateColumns: "1fr 1fr",
  gap: 10, marginBottom: 12,
};
