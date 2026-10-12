// FUUSIC Social-Feed Home — the center activity wall rendered at "/" when a
// Social Feed view (V2 light / V3 dark) is active. The surrounding chrome
// (header, sidebars, rail, dock, bottom nav) is provided by SocialFeedShell;
// this component owns ONLY the center column: Moments, composer, Together
// quick actions, Following/For-You tabs, an auto-refresh "N new posts" banner,
// and an infinite-scroll stream of mixed feed cards from GET /social/feed-v2.
import { useState, useEffect, useCallback, useRef } from "react";
import axios from "axios";
import { ArrowUp } from "lucide-react";
import { sfTokens } from "./sfTheme";
import { useHomeView } from "@/store/useHomeView";
import SocialFeedCard from "./SocialFeedCard";
import {
  MomentsRow, Composer, TogetherRow, ModeTabs, FeedSkeleton, EmptyState,
} from "./socialFeedParts";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

export default function SocialFeedHomeV2() {
  const appearance = useHomeView((s) => s.appearance());
  const t = sfTokens(appearance);
  const [mode, setMode] = useState("following");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moments, setMoments] = useState([]);
  const [newCount, setNewCount] = useState(0);
  const latestRef = useRef(null);
  const sentinelRef = useRef(null);

  const logEvent = (event) =>
    axios.post(`${API}/social/feed-events`, { event }, { withCredentials: true }).catch(() => {});

  const loadFeed = useCallback(async (m) => {
    setLoading(true);
    try {
      const r = await axios.get(`${API}/social/feed-v2`,
        { params: { mode: m, limit: 20 }, withCredentials: true });
      const list = r.data?.items || [];
      setItems(list);
      setCursor(r.data?.next_cursor || null);
      setHasMore(!!r.data?.has_more);
      latestRef.current = list[0]?.created_at || null;
      setNewCount(0);
    } catch (_e) { setItems([]); setHasMore(false); setCursor(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { loadFeed(mode); logEvent("social_feed_view"); }, [mode, loadFeed]);

  useEffect(() => {
    axios.get(`${API}/social/moments`, { params: { scope: "feed" }, withCredentials: true })
      .then((r) => setMoments(r.data?.items || [])).catch(() => {});
  }, []);

  const loadMore = useCallback(async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await axios.get(`${API}/social/feed-v2`,
        { params: { mode, cursor, limit: 20 }, withCredentials: true });
      setItems((prev) => [...prev, ...(r.data?.items || [])]);
      setCursor(r.data?.next_cursor || null);
      setHasMore(!!r.data?.has_more);
    } catch (_e) { setHasMore(false); }
    finally { setLoadingMore(false); }
  }, [cursor, mode, loadingMore]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const io = new IntersectionObserver((e) => {
      if (e[0].isIntersecting && hasMore && !loadingMore) loadMore();
    }, { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, loadingMore, loadMore]);

  // Auto-refresh — poll for newer activity without disturbing the scroll.
  useEffect(() => {
    const poll = () => {
      if (!latestRef.current) return;
      axios.get(`${API}/social/feed-v2/new-count`,
        { params: { since: latestRef.current, mode }, withCredentials: true })
        .then((r) => setNewCount(r.data?.new_count || 0)).catch(() => {});
    };
    const id = setInterval(poll, 45000);
    return () => clearInterval(id);
  }, [mode]);

  const onFollow = useCallback((id) => {
    if (!id) return;
    axios.post(`${API}/social/follow/${id}`, {}, { withCredentials: true }).catch(() => {});
  }, []);

  const refreshTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
    loadFeed(mode);
  };

  const switchMode = (m) => {
    if (m === mode) return;
    setMode(m);
    logEvent(m === "for_you" ? "social_feed_mode_for_you" : "social_feed_mode_following");
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }} data-testid="social-feed-home">
      <MomentsRow t={t} moments={moments} />
      <Composer t={t} onPosted={() => loadFeed(mode)} />
      <TogetherRow t={t} />
      <ModeTabs t={t} mode={mode} setMode={switchMode} />

      {newCount > 0 && (
        <button onClick={refreshTop} data-testid="sf-new-posts" className="sf-press sf-fade-in"
          style={{ alignSelf: "center", display: "inline-flex", alignItems: "center", gap: 6,
                   padding: "8px 18px", borderRadius: 999, border: "none", cursor: "pointer",
                   color: "#fff", background: t.accentGrad, fontWeight: 800, fontSize: 13,
                   boxShadow: t.shadow, position: "sticky", top: 70, zIndex: 20 }}>
          <ArrowUp size={15} /> {newCount} new {newCount === 1 ? "post" : "posts"}
        </button>
      )}

      {loading ? (
        <FeedSkeleton t={t} />
      ) : items.length === 0 ? (
        <EmptyState t={t} mode={mode} onDiscover={() => switchMode("for_you")} />
      ) : (
        <>
          {items.map((it) => (
            <SocialFeedCard key={it.id} item={it} t={t} onFollow={onFollow} />
          ))}
          <div ref={sentinelRef} style={{ height: 1 }} />
          {loadingMore && <FeedSkeleton t={t} />}
          {!hasMore && (
            <div style={{ textAlign: "center", padding: 20, fontSize: 13, color: t.muted }}>
              You're all caught up ✨
            </div>
          )}
        </>
      )}
    </div>
  );
}
