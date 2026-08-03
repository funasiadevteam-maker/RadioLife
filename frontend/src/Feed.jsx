/** Phase 41 Session 2 — Home feed (`/feed`). */
import React, { useEffect, useState } from "react";
import axios from "axios";
import { Rss } from "lucide-react";
import { PostCard } from "@/components/PageFeed";
import { API } from "@/AuthContext";

export default function Feed() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/social/feed`,
          { params: { limit: 20 }, withCredentials: true });
        setItems(r.data?.items || []);
      } catch (e) { setItems([]); }
      setLoading(false);
    })();
  }, []);

  return (
    <div data-testid="feed-page"
         style={{ maxWidth: 720, margin: "0 auto", padding: 24, color: "#fff" }}>
      <h1 style={{ display: "flex", alignItems: "center", gap: 10,
                   fontSize: 26, fontWeight: 700, margin: "0 0 18px" }}>
        <Rss size={22} color="#00d9ff" /> Your Feed
      </h1>
      {loading ? (
        <div style={{ color: "#9aa3af", padding: 30 }}>Loading…</div>
      ) : items.length === 0 ? (
        <div data-testid="feed-empty"
             style={{ color: "#9aa3af", padding: 30, textAlign: "center",
                      background: "rgba(255,255,255,0.03)", borderRadius: 10,
                      border: "1px dashed rgba(255,255,255,0.08)" }}>
          Follow stations to see their posts here.
        </div>
      ) : items.map(p => <PostCard key={p.post_id} post={p} />)}
    </div>
  );
}
