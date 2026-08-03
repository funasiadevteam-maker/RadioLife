/** Phase 19 Part B — Unified moderation queue (admin). */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Shield, Check, X, RefreshCw } from "lucide-react";
import { API } from "@/AuthContext";

const TYPES = [
  { id: "all",                   label: "All" },
  { id: "game_campaigns",        label: "Games" },
  { id: "podcast_applications",  label: "Podcasts" },
  { id: "social_posts",          label: "Social posts" },
  { id: "business_reviews",      label: "Reviews" },
];

export default function AdminModerationQueue() {
  const [type, setType] = useState("all");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/admin/moderation/queue`,
        { params: { content_type: type }, withCredentials: true });
      setItems(r.data?.items || []);
    } catch (e) { setItems([]); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [type]);

  const decide = async (item, action) => {
    try {
      await axios.post(`${API}/admin/moderation/${item.type}/${item.item_id}/decide`,
        { action, reason: "" }, { withCredentials: true });
      setItems(prev => prev.filter(x => x.item_id !== item.item_id));
    } catch (e) { /* silent */ }
  };

  return (
    <div data-testid="admin-moderation-page"
         style={{ maxWidth: 1000, margin: "0 auto", padding: 24, color: "#fff" }}>
      <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                   fontSize: 26, fontWeight: 700, margin: "0 0 8px" }}>
        <Shield size={22} color="#00d9ff" /> Moderation Queue
      </h1>
      <p style={{ color: "#9aa3af", fontSize: 13, marginBottom: 18 }}>
        Unified review across games, podcasts, social posts, and business
        reviews. Approve or reject — both log to <code>social_moderation_logs</code>.
      </p>

      <div style={{ display: "flex", gap: 8, marginBottom: 18, flexWrap: "wrap" }}>
        {TYPES.map(t => (
          <button key={t.id} data-testid={`mod-filter-${t.id}`}
                  onClick={() => setType(t.id)}
                  style={{ background: type === t.id ? "#00d9ff" : "rgba(255,255,255,0.05)",
                           color: type === t.id ? "#0b0b0b" : "#cbd5e1",
                           border: "1px solid rgba(255,255,255,0.08)",
                           padding: "6px 12px", borderRadius: 16,
                           fontSize: 12, fontWeight: type === t.id ? 600 : 400,
                           cursor: "pointer" }}>
            {t.label}
          </button>
        ))}
        <button onClick={load} data-testid="mod-refresh"
                style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6,
                         background: "rgba(255,255,255,0.05)", color: "#9aa3af",
                         border: "1px solid rgba(255,255,255,0.08)",
                         padding: "6px 12px", borderRadius: 16, fontSize: 12,
                         cursor: "pointer" }}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {loading ? (
        <div style={{ color: "#9aa3af", padding: 30 }}>Loading…</div>
      ) : items.length === 0 ? (
        <div data-testid="mod-empty"
             style={{ color: "#9aa3af", padding: 30, textAlign: "center",
                      background: "rgba(255,255,255,0.03)",
                      borderRadius: 10, border: "1px dashed rgba(255,255,255,0.08)" }}>
          Nothing pending review.
        </div>
      ) : (
        <div data-testid="mod-list" style={{ display: "grid", gap: 12 }}>
          {items.map(it => (
            <div key={it.item_id} data-testid={`mod-item-${it.item_id}`}
                 style={{ padding: 14, borderRadius: 10,
                          background: "rgba(255,255,255,0.04)",
                          border: "1px solid rgba(255,255,255,0.05)",
                          display: "flex", gap: 12, alignItems: "center" }}>
              <span style={{ fontSize: 10, padding: "3px 8px",
                              background: "rgba(0,217,255,0.15)", color: "#00d9ff",
                              borderRadius: 12, fontFamily: "monospace",
                              letterSpacing: 1 }}>
                {it.type.toUpperCase().replace(/_/g, " ")}
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontWeight: 600, fontSize: 14,
                                overflow: "hidden", textOverflow: "ellipsis",
                                whiteSpace: "nowrap" }}>
                  {it.summary || "(no summary)"}
                </div>
                <div style={{ fontSize: 11, color: "#9aa3af",
                                fontFamily: "monospace", marginTop: 3 }}>
                  {it.actor_user_id} · {it.created_at?.slice(0, 19)}
                </div>
              </div>
              <button data-testid={`mod-approve-${it.item_id}`}
                      onClick={() => decide(it, "approve")}
                      style={{ background: "rgba(34,197,94,0.15)", color: "#22c55e",
                               border: "1px solid #22c55e", padding: "6px 12px",
                               borderRadius: 6, fontSize: 12, cursor: "pointer",
                               display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Check size={12} /> Approve
              </button>
              <button data-testid={`mod-reject-${it.item_id}`}
                      onClick={() => decide(it, "reject")}
                      style={{ background: "rgba(239,68,68,0.15)", color: "#ef4444",
                               border: "1px solid #ef4444", padding: "6px 12px",
                               borderRadius: 6, fontSize: 12, cursor: "pointer",
                               display: "inline-flex", alignItems: "center", gap: 4 }}>
                <X size={12} /> Reject
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
