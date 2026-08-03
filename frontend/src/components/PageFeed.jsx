/** Phase 41 Session 2 — Post composer + feed list (shared). */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Send, Heart } from "lucide-react";
import { API } from "@/AuthContext";

const REACTIONS = [
  { id: "like",      label: "👍" },
  { id: "love",      label: "❤️" },
  { id: "wow",       label: "😮" },
  { id: "fire",      label: "🔥" },
  { id: "celebrate", label: "🎉" },
];

export function PostComposer({ pageId, onPosted }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg,  setMsg]  = useState(null);

  const submit = async () => {
    if (!text.trim() || busy) return;
    setBusy(true); setMsg(null);
    try {
      const r = await axios.post(`${API}/social/pages/${pageId}/posts`,
                                          { text }, { withCredentials: true });
      setText("");
      setMsg(r.data?.approved ? "Posted!" : "Posted — pending review.");
      onPosted?.(r.data);
    } catch (e) {
      setMsg(e.response?.data?.detail?.code || "Could not post.");
    }
    setBusy(false);
  };

  return (
    <div data-testid="post-composer"
         style={{ padding: 14, background: "rgba(255,255,255,0.04)",
                  borderRadius: 12, marginBottom: 16 }}>
      <textarea data-testid="post-composer-text" value={text} rows={2}
                 onChange={e => setText(e.target.value)}
                 placeholder="Say something to your followers…"
                 style={{ width: "100%", background: "transparent", color: "#fff",
                          border: "none", outline: "none", fontSize: 14,
                          fontFamily: "inherit", resize: "vertical" }} />
      <div style={{ display: "flex", justifyContent: "space-between",
                     alignItems: "center", marginTop: 8 }}>
        <span style={{ fontSize: 11, color: "#9aa3af" }}>{msg || `${text.length}/2000`}</span>
        <button data-testid="post-composer-submit" disabled={busy || !text.trim()}
                onClick={submit}
                style={{ background: "#00d9ff", color: "#0b0b0b", border: "none",
                         padding: "7px 14px", borderRadius: 6, fontSize: 12,
                         fontWeight: 600, cursor: "pointer", opacity: busy ? 0.6 : 1,
                         display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Send size={12} /> Post
        </button>
      </div>
    </div>
  );
}

export function PostCard({ post, onReact }) {
  const [counts, setCounts] = useState(post.reaction_counts || {});
  const [my, setMy] = useState(null);

  const react = async (rt) => {
    try {
      const r = await axios.post(`${API}/social/posts/${post.post_id}/react`,
                                          { reaction_type: rt }, { withCredentials: true });
      setCounts(r.data?.counts || {});
      setMy(r.data?.my_reaction);
      onReact?.(post.post_id, r.data);
    } catch (e) { /* silent */ }
  };

  return (
    <div data-testid={`post-card-${post.post_id}`}
         style={{ padding: 14, background: "rgba(255,255,255,0.04)",
                  borderRadius: 12, marginBottom: 12 }}>
      <div style={{ fontSize: 11, color: "#9aa3af", marginBottom: 6, fontFamily: "monospace" }}>
        {post.author_user_id?.slice(0, 12)}… · {post.created_at?.slice(0, 19)}
      </div>
      <div style={{ color: "#fff", fontSize: 14, lineHeight: 1.55,
                     marginBottom: 10, whiteSpace: "pre-wrap" }}>
        {post.text}
      </div>
      {post.approval_status === "pending_moderation" && (
        <div style={{ fontSize: 10, color: "#f59e0b", fontFamily: "monospace",
                       letterSpacing: 1, marginBottom: 8 }}>
          PENDING REVIEW
        </div>
      )}
      <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
        {REACTIONS.map(r => {
          const n = counts[r.id] || 0;
          const on = my === r.id;
          return (
            <button key={r.id} data-testid={`post-react-${post.post_id}-${r.id}`}
                    onClick={() => react(r.id)}
                    style={{ background: on ? "rgba(0,217,255,0.2)" : "rgba(255,255,255,0.04)",
                             border: `1px solid ${on ? "#00d9ff" : "rgba(255,255,255,0.08)"}`,
                             padding: "4px 10px", borderRadius: 12, fontSize: 12,
                             cursor: "pointer", color: "#fff",
                             display: "inline-flex", alignItems: "center", gap: 4 }}>
              {r.label} {n > 0 && <span style={{ fontSize: 11, color: "#cbd5e1" }}>{n}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default function PageFeed({ pageId, isOwner }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/social/pages/${pageId}/posts`,
        { params: { limit: 20 }, withCredentials: true });
      setItems(r.data?.items || []);
    } catch (e) { setItems([]); }
    setLoading(false);
  };

  useEffect(() => { load(); }, [pageId]);

  return (
    <div data-testid="page-feed">
      {isOwner && <PostComposer pageId={pageId} onPosted={load} />}
      {loading ? (
        <div style={{ color: "#9aa3af", padding: 20 }}>Loading…</div>
      ) : items.length === 0 ? (
        <div data-testid="page-feed-empty"
             style={{ color: "#9aa3af", padding: 20, textAlign: "center" }}>
          No posts yet.
        </div>
      ) : items.map(p => (
        <PostCard key={p.post_id} post={p} />
      ))}
    </div>
  );
}
