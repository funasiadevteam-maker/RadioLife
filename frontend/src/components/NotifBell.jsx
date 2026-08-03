/** Phase 41 Session 2 — Notification bell (drop-in top-nav widget). */
import React, { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import { Bell } from "lucide-react";
import { API } from "@/AuthContext";

export default function NotifBell() {
  const [unread, setUnread] = useState(0);
  const [open, setOpen]     = useState(false);
  const [items, setItems]   = useState([]);
  const timerRef            = useRef(null);

  const poll = async () => {
    try {
      const r = await axios.get(`${API}/social/notifications`,
        { params: { limit: 10 }, withCredentials: true });
      setUnread(r.data?.unread_total || 0);
      setItems(r.data?.items || []);
    } catch (e) { /* silent */ }
  };

  useEffect(() => {
    poll();
    timerRef.current = setInterval(poll, 45000);
    return () => clearInterval(timerRef.current);
  }, []);

  const markAllRead = async () => {
    try {
      await axios.post(`${API}/social/notifications/mark_read`, {},
                              { withCredentials: true });
      setUnread(0);
      setItems(prev => prev.map(n => ({ ...n, read: true })));
    } catch (e) { /* silent */ }
  };

  return (
    <div style={{ position: "relative" }} data-testid="notif-bell">
      <button data-testid="notif-bell-button"
              onClick={() => { setOpen(v => !v); if (!open && unread > 0) markAllRead(); }}
              style={{ background: "none", border: "none", color: "#fff",
                       cursor: "pointer", position: "relative", padding: 4 }}>
        <Bell size={18} />
        {unread > 0 && (
          <span data-testid="notif-bell-badge"
                style={{ position: "absolute", top: -2, right: -2,
                          background: "#ef4444", color: "#fff",
                          fontSize: 9, fontWeight: 700,
                          width: 16, height: 16, borderRadius: "50%",
                          display: "flex", alignItems: "center",
                          justifyContent: "center" }}>
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>
      {open && (
        <div data-testid="notif-bell-dropdown"
             style={{ position: "absolute", top: 30, right: 0,
                      width: 320, maxHeight: 420, overflowY: "auto",
                      background: "#1f2937", borderRadius: 10,
                      border: "1px solid rgba(255,255,255,0.08)",
                      boxShadow: "0 8px 20px rgba(0,0,0,0.4)", zIndex: 1000 }}>
          <div style={{ padding: 12, borderBottom: "1px solid rgba(255,255,255,0.08)",
                          fontSize: 13, fontWeight: 600, color: "#fff" }}>
            Notifications
          </div>
          {items.length === 0 ? (
            <div style={{ padding: 18, color: "#9aa3af", fontSize: 12,
                            textAlign: "center" }}>
              You're all caught up.
            </div>
          ) : items.map(n => (
            <div key={n.notification_id} data-testid={`notif-row-${n.notification_id}`}
                 style={{ padding: 10, borderBottom: "1px solid rgba(255,255,255,0.04)",
                          background: n.read ? "transparent" : "rgba(0,217,255,0.05)" }}>
              <div style={{ fontSize: 12, color: "#fff", marginBottom: 3 }}>
                {n.message}
              </div>
              <div style={{ fontSize: 10, color: "#9aa3af", fontFamily: "monospace" }}>
                {n.notif_type} · {n.created_at?.slice(0, 19)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
