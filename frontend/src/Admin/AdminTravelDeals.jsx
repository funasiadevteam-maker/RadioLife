/** Admin — Travel Deals manager.
 *  Route: /admin/travel-deals  (requireAdmin)
 *  CRUD over the curated travel catalogue surfaced in Shop → Travel and in the
 *  social wall for members who follow the Travel topic.
 */
import React, { useEffect, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import { Plane, Plus, Pencil, Trash2, X, Star, Coins } from "lucide-react";
import { API } from "@/AuthContext";

const TYPES = ["flight", "hotel", "package", "experience", "cruise"];
const money = (c) => `$${Math.round((c || 0) / 100)}`;
const BG = "#070710", CARD = "#0f0f17", BORDER = "#24242f", ACCENT = "#a855f7";
const TXT = "#f4f4f6", MUT = "#8b8b99";

const EMPTY = {
  title: "", deal_type: "package", destination: "", origin: "",
  price: "", strike: "", bigpoints: 0, image_url: "", blurb: "",
  duration: "", rating: "", tags: "", promoted: false, active: true,
};

function toForm(d) {
  return {
    title: d.title || "", deal_type: d.deal_type || "package",
    destination: d.destination || "", origin: d.origin || "",
    price: d.price_cents ? String(d.price_cents / 100) : "",
    strike: d.strike_cents ? String(d.strike_cents / 100) : "",
    bigpoints: d.bigpoints || 0, image_url: d.image_url || "",
    blurb: d.blurb || "", duration: d.duration || "",
    rating: d.rating != null ? String(d.rating) : "",
    tags: (d.tags || []).join(", "), promoted: !!d.promoted,
    active: d.active !== false,
  };
}

function toPayload(f) {
  return {
    title: f.title.trim(), deal_type: f.deal_type,
    destination: f.destination.trim(), origin: f.origin.trim() || null,
    price_cents: Math.round((parseFloat(f.price) || 0) * 100),
    strike_cents: f.strike ? Math.round((parseFloat(f.strike) || 0) * 100) : null,
    bigpoints: parseInt(f.bigpoints, 10) || 0,
    image_url: f.image_url.trim() || null, blurb: f.blurb.trim() || null,
    duration: f.duration.trim() || null,
    rating: f.rating ? parseFloat(f.rating) : null,
    tags: f.tags.split(",").map((t) => t.trim()).filter(Boolean),
    promoted: !!f.promoted, active: !!f.active,
  };
}

export default function AdminTravelDeals() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null); // deal object or {} for new
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/travel/admin/deals`, { withCredentials: true });
      setItems(r.data?.items || []);
    } catch (_e) { toast.error("Couldn't load travel deals"); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openNew = () => { setForm(EMPTY); setEditing({}); };
  const openEdit = (d) => { setForm(toForm(d)); setEditing(d); };
  const close = () => setEditing(null);
  const set = (k) => (e) => {
    const v = e?.target?.type === "checkbox" ? e.target.checked : e.target.value;
    setForm((f) => ({ ...f, [k]: v }));
  };

  const save = async () => {
    if (!form.title.trim() || !form.destination.trim()) { toast.error("Title and destination are required"); return; }
    setSaving(true);
    try {
      const payload = toPayload(form);
      if (editing?.deal_id) await axios.put(`${API}/travel/admin/deals/${editing.deal_id}`, payload, { withCredentials: true });
      else await axios.post(`${API}/travel/admin/deals`, payload, { withCredentials: true });
      toast.success(editing?.deal_id ? "Deal updated" : "Deal created");
      close(); load();
    } catch (_e) { toast.error("Save failed — check the fields"); }
    finally { setSaving(false); }
  };

  const remove = async (d) => {
    if (!window.confirm(`Delete "${d.title}"?`)) return;
    try {
      await axios.delete(`${API}/travel/admin/deals/${d.deal_id}`, { withCredentials: true });
      toast.success("Deal deleted"); load();
    } catch (_e) { toast.error("Delete failed"); }
  };

  const field = { background: "#15151f", border: `1px solid ${BORDER}`, borderRadius: 10, color: TXT, padding: "10px 12px", fontSize: 14, width: "100%", outline: "none" };
  const lbl = { fontSize: 12, fontWeight: 700, color: MUT, marginBottom: 4, display: "block" };

  return (
    <div style={{ minHeight: "100vh", background: BG, color: TXT }}>
      <main style={{ maxWidth: 1000, margin: "0 auto", padding: "24px 18px 80px" }} data-testid="admin-travel-page">
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <span style={{ width: 44, height: 44, borderRadius: 12, display: "grid", placeItems: "center", background: `linear-gradient(135deg,#a855f7,#ec4899)` }}>
            <Plane size={22} color="#fff" />
          </span>
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 22, fontWeight: 900, margin: 0 }}>Travel Deals</h1>
            <p style={{ color: MUT, fontSize: 13, margin: "2px 0 0" }}>Curated deals for Shop → Travel &amp; the wall.</p>
          </div>
          <button onClick={openNew} data-testid="admin-travel-new"
            style={{ display: "inline-flex", alignItems: "center", gap: 7, background: ACCENT, color: "#fff", border: "none", borderRadius: 999, padding: "10px 16px", fontWeight: 800, cursor: "pointer" }}>
            <Plus size={16} /> New deal
          </button>
        </div>

        {loading ? (
          <div style={{ color: MUT, textAlign: "center", padding: 40 }} data-testid="admin-travel-loading">Loading…</div>
        ) : items.length === 0 ? (
          <div style={{ color: MUT, textAlign: "center", padding: 40 }}>No deals yet. Create your first one.</div>
        ) : (
          <div style={{ display: "grid", gap: 10 }}>
            {items.map((d) => (
              <div key={d.deal_id} data-testid={`admin-travel-row-${d.deal_id}`}
                style={{ display: "flex", alignItems: "center", gap: 12, background: CARD, border: `1px solid ${BORDER}`, borderRadius: 14, padding: 12 }}>
                <div style={{ width: 72, height: 54, borderRadius: 10, overflow: "hidden", background: "#15151f", flexShrink: 0 }}>
                  {d.image_url && <img src={d.image_url} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} />}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ fontWeight: 800, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{d.title}</span>
                    <span style={{ fontSize: 10.5, fontWeight: 800, color: ACCENT, background: "rgba(168,85,247,.15)", borderRadius: 999, padding: "2px 8px", textTransform: "capitalize" }}>{d.deal_type}</span>
                    {d.promoted && <span style={{ fontSize: 10.5, fontWeight: 800, color: "#fff", background: "#ef4444", borderRadius: 999, padding: "2px 8px" }}>DEAL</span>}
                    {!d.active && <span style={{ fontSize: 10.5, fontWeight: 800, color: MUT, border: `1px solid ${BORDER}`, borderRadius: 999, padding: "2px 8px" }}>hidden</span>}
                  </div>
                  <div style={{ color: MUT, fontSize: 12.5, marginTop: 2, display: "flex", gap: 12, flexWrap: "wrap" }}>
                    <span>{d.destination}</span>
                    <span style={{ fontWeight: 700, color: TXT }}>{money(d.price_cents)}</span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><Coins size={12} /> +{d.bigpoints}</span>
                    {d.rating ? <span style={{ display: "inline-flex", alignItems: "center", gap: 3 }}><Star size={12} /> {d.rating}</span> : null}
                  </div>
                </div>
                <button onClick={() => openEdit(d)} data-testid={`admin-travel-edit-${d.deal_id}`}
                  style={{ width: 36, height: 36, borderRadius: 10, border: `1px solid ${BORDER}`, background: "transparent", color: TXT, cursor: "pointer", display: "grid", placeItems: "center" }}><Pencil size={15} /></button>
                <button onClick={() => remove(d)} data-testid={`admin-travel-delete-${d.deal_id}`}
                  style={{ width: 36, height: 36, borderRadius: 10, border: `1px solid ${BORDER}`, background: "transparent", color: "#ef4444", cursor: "pointer", display: "grid", placeItems: "center" }}><Trash2 size={15} /></button>
              </div>
            ))}
          </div>
        )}

        {editing && (
          <div onClick={close} style={{ position: "fixed", inset: 0, zIndex: 100, background: "rgba(0,0,0,.6)", display: "grid", placeItems: "center", padding: 16 }}>
            <div onClick={(e) => e.stopPropagation()} data-testid="admin-travel-form"
              style={{ width: "100%", maxWidth: 560, maxHeight: "88vh", overflowY: "auto", background: CARD, border: `1px solid ${BORDER}`, borderRadius: 18, padding: 18 }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 14 }}>
                <h2 style={{ fontSize: 17, fontWeight: 900, margin: 0 }}>{editing.deal_id ? "Edit deal" : "New deal"}</h2>
                <button onClick={close} style={{ width: 32, height: 32, borderRadius: 999, border: "none", background: "#15151f", color: TXT, cursor: "pointer" }}><X size={16} /></button>
              </div>
              <div style={{ display: "grid", gap: 12 }}>
                <div><label style={lbl}>Title</label><input value={form.title} onChange={set("title")} data-testid="admin-travel-f-title" style={field} /></div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div><label style={lbl}>Type</label>
                    <select value={form.deal_type} onChange={set("deal_type")} data-testid="admin-travel-f-type" style={field}>
                      {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div><label style={lbl}>Destination</label><input value={form.destination} onChange={set("destination")} data-testid="admin-travel-f-destination" style={field} /></div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
                  <div><label style={lbl}>Price ($)</label><input value={form.price} onChange={set("price")} data-testid="admin-travel-f-price" inputMode="decimal" style={field} /></div>
                  <div><label style={lbl}>Was ($)</label><input value={form.strike} onChange={set("strike")} inputMode="decimal" style={field} /></div>
                  <div><label style={lbl}>BigPoints</label><input value={form.bigpoints} onChange={set("bigpoints")} inputMode="numeric" style={field} /></div>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                  <div><label style={lbl}>Duration</label><input value={form.duration} onChange={set("duration")} placeholder="e.g. 5 nights" style={field} /></div>
                  <div><label style={lbl}>Rating</label><input value={form.rating} onChange={set("rating")} inputMode="decimal" placeholder="4.8" style={field} /></div>
                </div>
                <div><label style={lbl}>Image URL</label><input value={form.image_url} onChange={set("image_url")} data-testid="admin-travel-f-image" style={field} /></div>
                <div><label style={lbl}>Blurb</label><textarea value={form.blurb} onChange={set("blurb")} rows={2} style={{ ...field, resize: "vertical" }} /></div>
                <div><label style={lbl}>Tags (comma separated)</label><input value={form.tags} onChange={set("tags")} placeholder="beach, villa" style={field} /></div>
                <div style={{ display: "flex", gap: 20 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, cursor: "pointer" }}>
                    <input type="checkbox" checked={form.promoted} onChange={set("promoted")} data-testid="admin-travel-f-promoted" /> Promoted
                  </label>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, cursor: "pointer" }}>
                    <input type="checkbox" checked={form.active} onChange={set("active")} data-testid="admin-travel-f-active" /> Active
                  </label>
                </div>
                <button onClick={save} disabled={saving} data-testid="admin-travel-save"
                  style={{ background: ACCENT, color: "#fff", border: "none", borderRadius: 12, padding: "12px", fontWeight: 800, cursor: "pointer", opacity: saving ? 0.6 : 1 }}>
                  {saving ? "Saving…" : editing.deal_id ? "Save changes" : "Create deal"}
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
