/** Phase 41 Session 4.A — Owner-only announcement manager.
 *
 * Renders inside `StationPage.jsx` for the station owner. Lists
 * existing announcements (active + scheduled + expired) and exposes
 * a create form. Each row supports inline edit and delete.
 *
 * The `?include_expired=true` query is appended so the owner gets
 * full history. Public listeners use the same endpoint without the
 * flag and see only currently-active announcements (which is what
 * the TV display ingests via `/api/tv/{slug}`).
 */
import React, { useCallback, useEffect, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Megaphone, Plus, Trash2, Pencil, Save, X, AlertTriangle, Ticket,
} from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;
const MAX_CHARS = 280;

export default function AnnouncementManager({ slug }) {
  const [items, setItems]  = useState([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editId, setEditId] = useState(null);
  const [draft, setDraft]   = useState({ message: "", priority: 5,
                                          starts_at: "", ends_at: "" });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/announcements`,
        { params: { include_expired: true },
          withCredentials: true });
      setItems(r.data?.items || []);
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      if (code !== "not_found") {
        toast.error("Could not load announcements", { id: "ann-load-err" });
      }
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    let cancelled = false;
    Promise.resolve().then(() => { if (!cancelled) load(); });
    return () => { cancelled = true; };
  }, [load]);

  const startCreate = () => {
    setEditId(null);
    setDraft({ message: "", priority: 5, starts_at: "", ends_at: "" });
    setCreating(true);
  };
  const startEdit = (a) => {
    setCreating(false);
    setEditId(a.id);
    setDraft({ message: a.message || "",
                priority: a.priority ?? 5,
                starts_at: a.starts_at ? toLocalInput(a.starts_at) : "",
                ends_at:   a.ends_at   ? toLocalInput(a.ends_at)   : "" });
  };
  const cancel = () => { setCreating(false); setEditId(null); };

  const submit = async () => {
    const body = buildBody(draft);
    if (!body) return;
    try {
      if (creating) {
        const r = await axios.post(
          `${API}/stations/${encodeURIComponent(slug)}/announcements`,
          body, { withCredentials: true });
        setItems((xs) => [r.data, ...xs]);
        toast.success("Announcement created");
      } else if (editId) {
        const r = await axios.patch(
          `${API}/stations/${encodeURIComponent(slug)}/announcements/${editId}`,
          body, { withCredentials: true });
        setItems((xs) => xs.map((x) => (x.id === editId ? r.data : x)));
        toast.success("Announcement updated");
      }
      cancel();
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      if (code === "active_cap") {
        toast.error("Maximum 10 active announcements at once");
      } else if (code === "validation_error") {
        toast.error(e.response.data.detail.message || "Validation error");
      } else {
        toast.error("Could not save announcement");
      }
    }
  };

  const del = async (a) => {
    if (!window.confirm("Delete this announcement?")) return;
    try {
      await axios.delete(
        `${API}/stations/${encodeURIComponent(slug)}/announcements/${a.id}`,
        { withCredentials: true });
      setItems((xs) => xs.filter((x) => x.id !== a.id));
      toast.success("Deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  const activeCount = items.filter((x) => x.active).length;
  const isEditing = creating || !!editId;

  return (
    <div data-testid="announcement-manager"
         style={{ marginTop: 28, padding: 18, borderRadius: 14,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      <div style={{ display: "flex", alignItems: "center",
                     justifyContent: "space-between", marginBottom: 14 }}>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <Megaphone size={16} color="#00d9ff" />
          <div style={{ fontSize: 14, fontWeight: 700, color: "#fff" }}>
            Announcements
          </div>
          <span data-testid="announcement-active-count"
                style={{ fontSize: 11, color: "#9aa3af" }}>
            {activeCount} active · {items.length} total
          </span>
        </div>
        {!isEditing && (
          <button data-testid="announcement-create-btn"
                  onClick={startCreate}
                  style={{ display: "inline-flex", alignItems: "center", gap: 6,
                            background: "rgba(0,217,255,0.15)", color: "#00d9ff",
                            border: "1px solid rgba(0,217,255,0.4)",
                            padding: "6px 12px", borderRadius: 6,
                            fontSize: 12, fontWeight: 600, cursor: "pointer" }}>
            <Plus size={13} /> New
          </button>
        )}
      </div>

      {isEditing && (
        <DraftForm draft={draft} setDraft={setDraft}
                   onCancel={cancel} onSubmit={submit}
                   editing={!!editId} />
      )}

      {loading && items.length === 0 && (
        <div style={{ color: "#9aa3af", fontSize: 12, padding: 8 }}>
          Loading…
        </div>
      )}

      {!loading && items.length === 0 && !isEditing && (
        <div data-testid="announcement-empty"
             style={{ color: "#9aa3af", fontSize: 12, padding: 8,
                       display: "flex", alignItems: "center", gap: 6 }}>
          No announcements yet — create one to start rotating it on the TV display.
        </div>
      )}

      {items.length > 0 && (
        <div style={{ display: "grid", gap: 8 }}>
          {items.map((a) => (
            <AnnouncementRow key={a.id} a={a}
                              onEdit={() => startEdit(a)}
                              onDelete={() => del(a)}
                              onCouponChange={(coupon, updated_at) => setItems(
                                (xs) => xs.map((x) => x.id === a.id ? {
                                  ...x, coupon,
                                  updated_at: updated_at || x.updated_at,
                                } : x))} />
          ))}
        </div>
      )}
    </div>
  );
}

function DraftForm({ draft, setDraft, onCancel, onSubmit, editing }) {
  const upd = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  const remaining = MAX_CHARS - (draft.message?.length || 0);
  return (
    <div data-testid="announcement-form"
         style={{ marginBottom: 14, padding: 12,
                   background: "rgba(0,0,0,0.25)", borderRadius: 10,
                   border: "1px solid rgba(255,255,255,0.06)" }}>
      <textarea data-testid="announcement-form-message"
                value={draft.message}
                onChange={(e) => upd("message", e.target.value.slice(0, MAX_CHARS))}
                placeholder="What's happening at your business right now?"
                rows={3}
                style={{ width: "100%", padding: 10, fontSize: 13,
                          borderRadius: 6,
                          background: "rgba(255,255,255,0.05)",
                          color: "#fff", resize: "vertical",
                          border: "1px solid rgba(255,255,255,0.08)" }} />
      <div style={{ fontSize: 11, color: remaining < 20 ? "#fb923c" : "#9aa3af",
                     textAlign: "right", marginTop: 4 }}>
        {remaining} chars remaining
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "auto 1fr 1fr",
                     gap: 10, marginTop: 10 }}>
        <label style={{ fontSize: 11, color: "#9aa3af",
                          display: "flex", alignItems: "center", gap: 6 }}>
          Priority
          <select data-testid="announcement-form-priority"
                  value={draft.priority}
                  onChange={(e) => upd("priority", parseInt(e.target.value, 10))}
                  style={{ background: "rgba(255,255,255,0.05)", color: "#fff",
                            border: "1px solid rgba(255,255,255,0.08)",
                            padding: "4px 8px", borderRadius: 4,
                            fontSize: 12 }}>
            {[1,2,3,4,5,6,7,8,9,10].map((n) =>
              <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <label style={{ fontSize: 11, color: "#9aa3af" }}>
          Starts at
          <input data-testid="announcement-form-starts-at"
                 type="datetime-local"
                 value={draft.starts_at}
                 onChange={(e) => upd("starts_at", e.target.value)}
                 style={{ width: "100%", marginTop: 2,
                           background: "rgba(255,255,255,0.05)", color: "#fff",
                           border: "1px solid rgba(255,255,255,0.08)",
                           padding: "4px 8px", borderRadius: 4, fontSize: 12 }} />
        </label>
        <label style={{ fontSize: 11, color: "#9aa3af" }}>
          Ends at
          <input data-testid="announcement-form-ends-at"
                 type="datetime-local"
                 value={draft.ends_at}
                 onChange={(e) => upd("ends_at", e.target.value)}
                 style={{ width: "100%", marginTop: 2,
                           background: "rgba(255,255,255,0.05)", color: "#fff",
                           border: "1px solid rgba(255,255,255,0.08)",
                           padding: "4px 8px", borderRadius: 4, fontSize: 12 }} />
        </label>
      </div>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 8,
                     marginTop: 10 }}>
        <button data-testid="announcement-form-cancel"
                onClick={onCancel}
                style={{ display: "inline-flex", alignItems: "center", gap: 4,
                          background: "rgba(255,255,255,0.04)", color: "#cbd5e1",
                          border: "1px solid rgba(255,255,255,0.08)",
                          padding: "6px 12px", borderRadius: 6,
                          fontSize: 12, cursor: "pointer" }}>
          <X size={12} /> Cancel
        </button>
        <button data-testid="announcement-form-submit"
                onClick={onSubmit}
                disabled={!draft.message.trim()}
                style={{ display: "inline-flex", alignItems: "center", gap: 4,
                          background: "#00d9ff", color: "#0b0b0b",
                          border: "none",
                          padding: "6px 14px", borderRadius: 6,
                          fontSize: 12, fontWeight: 700,
                          opacity: draft.message.trim() ? 1 : 0.4,
                          cursor: draft.message.trim() ? "pointer" : "not-allowed" }}>
          <Save size={12} /> {editing ? "Save changes" : "Create"}
        </button>
      </div>
    </div>
  );
}

function AnnouncementRow({ a, onEdit, onDelete, onCouponChange }) {
  const [couponDraft, setCouponDraft] = useState(null);
  const [couponBusy,  setCouponBusy]  = useState(false);
  const isExpired = !a.active && (a.ends_at || a.starts_at);
  const c = a.coupon || null;

  const slugFromAnn = a.station_slug;

  const saveCoupon = async () => {
    if (!couponDraft) return;
    const body = buildCouponBody(couponDraft);
    if (!body) return;
    setCouponBusy(true);
    try {
      const r = await axios.post(
        `${API}/stations/${encodeURIComponent(slugFromAnn)}/announcements/${a.id}/coupon`,
        body, { withCredentials: true });
      // Lift change up to the parent so React state stays the source of truth.
      onCouponChange?.(
        r.data?.announcement?.coupon || null,
        r.data?.announcement?.updated_at);
      setCouponDraft(null);
      toast.success("Coupon saved");
    } catch (e) {
      const code = e.response?.data?.detail?.code;
      if (code === "validation_error") {
        toast.error(e.response.data.detail.message || "Invalid coupon");
      } else if (code === "permission_denied") {
        toast.error("Only the station owner can edit coupons");
      } else {
        toast.error("Could not save coupon");
      }
    } finally {
      setCouponBusy(false);
    }
  };

  const clearCoupon = async () => {
    if (!window.confirm("Remove this coupon?")) return;
    setCouponBusy(true);
    try {
      await axios.post(
        `${API}/stations/${encodeURIComponent(slugFromAnn)}/announcements/${a.id}/coupon`,
        { clear: true }, { withCredentials: true });
      onCouponChange?.(null);
      setCouponDraft(null);
      toast.success("Coupon cleared");
    } catch {
      toast.error("Could not clear coupon");
    } finally {
      setCouponBusy(false);
    }
  };

  return (
    <div data-testid={`announcement-row-${a.id}`}
         data-active={a.active ? "true" : "false"}
         data-has-coupon={c ? "true" : "false"}
         style={{ display: "grid",
                   gridTemplateColumns: "1fr auto",
                   gap: 12, alignItems: "start", padding: 10,
                   borderRadius: 8,
                   background: a.active
                     ? "rgba(16,185,129,0.06)"
                     : "rgba(255,255,255,0.03)",
                   border: `1px solid ${a.active
                     ? "rgba(16,185,129,0.2)"
                     : "rgba(255,255,255,0.05)"}` }}>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 6,
                       marginBottom: 4, fontSize: 11, flexWrap: "wrap" }}>
          <span style={{ color: a.active ? "#10b981" : "#9aa3af",
                          fontWeight: 700, letterSpacing: "0.06em",
                          textTransform: "uppercase" }}>
            {a.active ? "Active" : (isExpired ? "Expired" : "Scheduled")}
          </span>
          <span style={{ color: "#6b7280" }}>· P{a.priority}</span>
          {c && (
            <span data-testid={`announcement-coupon-chip-${a.id}`}
                  style={{ display: "inline-flex", alignItems: "center", gap: 4,
                            background: "rgba(0,217,255,0.12)",
                            color: "#00d9ff",
                            border: "1px solid rgba(0,217,255,0.4)",
                            padding: "1px 8px", borderRadius: 4,
                            fontSize: 10, fontWeight: 700,
                            letterSpacing: "0.04em" }}>
              <Ticket size={10} /> {c.code}
              {" · "}
              {c.discount_pct
                 ? `${c.discount_pct}%`
                 : (c.discount_amount_cents
                     ? `$${(c.discount_amount_cents/100).toFixed(2)}`
                     : "")}
              {(c.max_redemptions != null) && (
                <span style={{ color: "#9aa3af", fontWeight: 600,
                                marginLeft: 4 }}>
                  · {c.redemptions_count || 0}/{c.max_redemptions}
                </span>
              )}
            </span>
          )}
          {a.starts_at && (
            <span style={{ color: "#6b7280" }}>
              · from {fmtShort(a.starts_at)}
            </span>
          )}
          {a.ends_at && (
            <span style={{ color: "#6b7280" }}>
              · until {fmtShort(a.ends_at)}
            </span>
          )}
        </div>
        <div style={{ fontSize: 13, color: "#fff", whiteSpace: "pre-wrap",
                       wordBreak: "break-word" }}>
          {a.message}
        </div>
        {/* Coupon editor toggle row */}
        {!couponDraft && (
          <div style={{ marginTop: 8 }}>
            <button data-testid={`announcement-coupon-toggle-${a.id}`}
                    onClick={() => setCouponDraft(couponToDraft(c))}
                    style={{ display: "inline-flex", alignItems: "center", gap: 4,
                              background: "rgba(0,217,255,0.08)",
                              color: "#00d9ff",
                              border: "1px solid rgba(0,217,255,0.3)",
                              padding: "4px 10px", borderRadius: 6,
                              fontSize: 11, fontWeight: 600, cursor: "pointer" }}>
              <Ticket size={11} /> {c ? "Edit coupon" : "Add coupon"}
            </button>
            {c && (
              <button data-testid={`announcement-coupon-clear-${a.id}`}
                      onClick={clearCoupon}
                      disabled={couponBusy}
                      style={{ display: "inline-flex", alignItems: "center", gap: 4,
                                background: "rgba(239,68,68,0.08)",
                                color: "#ef4444",
                                border: "1px solid rgba(239,68,68,0.3)",
                                padding: "4px 10px", borderRadius: 6,
                                fontSize: 11, fontWeight: 600, cursor: "pointer",
                                marginLeft: 6 }}>
                Remove coupon
              </button>
            )}
          </div>
        )}
        {couponDraft && (
          <CouponDraftForm draft={couponDraft}
                            setDraft={setCouponDraft}
                            onCancel={() => setCouponDraft(null)}
                            onSubmit={saveCoupon}
                            busy={couponBusy}
                            annId={a.id} />
        )}
      </div>
      <div style={{ display: "inline-flex", gap: 4 }}>
        <button data-testid={`announcement-edit-${a.id}`}
                onClick={onEdit} title="Edit"
                style={{ background: "rgba(255,255,255,0.04)",
                          border: "1px solid rgba(255,255,255,0.08)",
                          color: "#cbd5e1", padding: 6, borderRadius: 6,
                          cursor: "pointer" }}>
          <Pencil size={12} />
        </button>
        <button data-testid={`announcement-delete-${a.id}`}
                onClick={onDelete} title="Delete"
                style={{ background: "rgba(239,68,68,0.1)",
                          border: "1px solid rgba(239,68,68,0.3)",
                          color: "#ef4444", padding: 6, borderRadius: 6,
                          cursor: "pointer" }}>
          <Trash2 size={12} />
        </button>
      </div>
    </div>
  );
}

function CouponDraftForm({ draft, setDraft, onCancel, onSubmit, busy, annId }) {
  const upd = (k, v) => setDraft((d) => ({ ...d, [k]: v }));
  return (
    <div data-testid={`announcement-coupon-form-${annId}`}
         style={{ marginTop: 10, padding: 10,
                   background: "rgba(0,0,0,0.3)",
                   border: "1px solid rgba(0,217,255,0.25)",
                   borderRadius: 8 }}>
      <div style={{ display: "grid",
                     gridTemplateColumns: "1fr 1fr 1fr",
                     gap: 8, marginBottom: 8 }}>
        <label style={{ fontSize: 10, color: "#9aa3af",
                          letterSpacing: 0.04 }}>
          Code (auto if blank)
          <input data-testid={`coupon-form-code-${annId}`}
                 value={draft.code}
                 onChange={(e) => upd("code", e.target.value.toUpperCase().slice(0, 24))}
                 placeholder="KARAK15"
                 style={inputStyle} />
        </label>
        <label style={{ fontSize: 10, color: "#9aa3af" }}>
          Discount %
          <input data-testid={`coupon-form-pct-${annId}`}
                 type="number" min={1} max={100}
                 value={draft.discount_pct}
                 onChange={(e) => upd("discount_pct", e.target.value)}
                 placeholder="15"
                 style={inputStyle} />
        </label>
        <label style={{ fontSize: 10, color: "#9aa3af" }}>
          Max redemptions
          <input data-testid={`coupon-form-max-${annId}`}
                 type="number" min={1}
                 value={draft.max_redemptions}
                 onChange={(e) => upd("max_redemptions", e.target.value)}
                 placeholder="unlimited"
                 style={inputStyle} />
        </label>
      </div>
      <label style={{ fontSize: 10, color: "#9aa3af" }}>
        Expires at (optional)
        <input data-testid={`coupon-form-expires-${annId}`}
               type="datetime-local"
               value={draft.expires_at}
               onChange={(e) => upd("expires_at", e.target.value)}
               style={inputStyle} />
      </label>
      <label style={{ fontSize: 10, color: "#9aa3af", display: "block",
                       marginTop: 8 }}>
        Terms (optional, ≤240 chars)
        <input data-testid={`coupon-form-terms-${annId}`}
               value={draft.terms}
               onChange={(e) => upd("terms", e.target.value.slice(0, 240))}
               placeholder="Dine-in only, expires today."
               style={inputStyle} />
      </label>
      <div style={{ display: "flex", justifyContent: "flex-end", gap: 6,
                     marginTop: 10 }}>
        <button data-testid={`coupon-form-cancel-${annId}`}
                onClick={onCancel}
                disabled={busy}
                style={{ background: "rgba(255,255,255,0.04)", color: "#cbd5e1",
                          border: "1px solid rgba(255,255,255,0.08)",
                          padding: "5px 10px", borderRadius: 6,
                          fontSize: 11, cursor: "pointer" }}>
          Cancel
        </button>
        <button data-testid={`coupon-form-save-${annId}`}
                onClick={onSubmit}
                disabled={busy}
                style={{ background: "#00d9ff", color: "#0b0b0b",
                          border: "none", fontWeight: 700,
                          padding: "5px 14px", borderRadius: 6,
                          fontSize: 11, cursor: "pointer",
                          opacity: busy ? 0.6 : 1 }}>
          Save coupon
        </button>
      </div>
    </div>
  );
}

const inputStyle = {
  width: "100%", marginTop: 2,
  background: "rgba(255,255,255,0.05)", color: "#fff",
  border: "1px solid rgba(255,255,255,0.08)",
  padding: "4px 8px", borderRadius: 4, fontSize: 12,
};

function couponToDraft(c) {
  if (!c) {
    return { code: "", discount_pct: "", max_redemptions: "",
              expires_at: "", terms: "" };
  }
  return {
    code:             c.code || "",
    discount_pct:     c.discount_pct ?? "",
    max_redemptions:  (c.max_redemptions ?? "") + "",
    expires_at:       c.expires_at ? toLocalInput(c.expires_at) : "",
    terms:            c.terms || "",
  };
}

function buildCouponBody(draft) {
  const body = {};
  const code = (draft.code || "").trim().toUpperCase();
  if (code) body.code = code;
  const pct = draft.discount_pct === "" ? null : parseInt(draft.discount_pct, 10);
  if (pct == null || Number.isNaN(pct)) {
    toast.error("Discount % is required (1-100)");
    return null;
  }
  body.discount_pct = pct;
  const mx = draft.max_redemptions === "" ? null : parseInt(draft.max_redemptions, 10);
  if (mx != null && !Number.isNaN(mx)) body.max_redemptions = mx;
  if (draft.expires_at) body.expires_at = fromLocalInput(draft.expires_at);
  if (draft.terms) body.terms = draft.terms;
  return body;
}

// ----- helpers -----
function buildBody(draft) {
  const msg = (draft.message || "").trim();
  if (!msg) return null;
  const body = { message: msg, priority: parseInt(draft.priority, 10) || 5 };
  // datetime-local emits "YYYY-MM-DDTHH:mm" — convert to ISO with TZ offset.
  if (draft.starts_at) body.starts_at = fromLocalInput(draft.starts_at);
  if (draft.ends_at)   body.ends_at   = fromLocalInput(draft.ends_at);
  if (body.starts_at && body.ends_at && body.ends_at <= body.starts_at) {
    toast.error("End time must be after start time",
                 { id: "ann-bad-range", icon: <AlertTriangle size={14} /> });
    return null;
  }
  return body;
}

function toLocalInput(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n) => (n < 10 ? `0${n}` : `${n}`);
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function fromLocalInput(local) {
  return new Date(local).toISOString();
}
function fmtShort(iso) {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined,
      { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  } catch { return iso; }
}
