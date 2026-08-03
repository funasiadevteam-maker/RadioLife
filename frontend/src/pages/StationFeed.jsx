/**
 * Phase 41 Session 2.A — StationFeed component.
 *
 * Renders the social engagement layer (posts + reactions + comments)
 * for a community station. Owner sees a composer at the top with an
 * optional image picker; everyone who can view the station sees the
 * post feed below with a 5-reaction popover.
 *
 * 30-second polling on visible feed; suspended when the tab is hidden.
 * Client-side 5 MB image cap; preview before send.
 *
 * Owner consumes typed error codes (rate_limited / validation_error /
 * not_owner) and surfaces toast-style messages inline — never silent
 * success/failure.
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { Link } from "react-router-dom";
import {
  Heart, Flame, ThumbsUp, MessageCircle, Smile, Sparkles,
  Image as ImageIcon, X, Trash2, MoreHorizontal,
} from "lucide-react";
import { API, useAuth } from "@/AuthContext";

const REACTIONS = [
  { key: "like",  Icon: ThumbsUp,  label: "Like",   color: "#60a5fa" },
  { key: "love",  Icon: Heart,     label: "Love",   color: "#f472b6" },
  { key: "fire",  Icon: Flame,     label: "Fire",   color: "#fb923c" },
  { key: "laugh", Icon: Smile,     label: "Laugh",  color: "#facc15" },
  { key: "wow",   Icon: Sparkles,  label: "Wow",    color: "#a78bfa" },
];
const REACTION_MAP = REACTIONS.reduce((m, r) => { m[r.key] = r; return m; }, {});

const POLL_INTERVAL_MS = 30 * 1000;
const IMAGE_MAX_BYTES  = 5 * 1024 * 1024;

function relTime(iso) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const sec = Math.max(0, (Date.now() - t) / 1000);
  if (sec < 60)    return `${Math.floor(sec)}s ago`;
  if (sec < 3600)  return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function totalCount(counts) {
  if (!counts) return 0;
  return REACTIONS.reduce((s, r) => s + (counts[r.key] || 0), 0);
}

// ─── reaction picker ──────────────────────────────────────────────
function ReactionBar({ counts, myReaction, onReact, testIdPrefix }) {
  const [open, setOpen] = useState(false);
  const total = totalCount(counts);
  const currentR = REACTION_MAP[myReaction];
  const closeTimer = useRef();

  const handleEnter = () => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    setOpen(true);
  };
  const handleLeave = () => {
    closeTimer.current = setTimeout(() => setOpen(false), 240);
  };

  return (
    <div
      style={{ position: "relative", display: "inline-flex" }}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
    >
      <button
        type="button"
        data-testid={`${testIdPrefix}-react-toggle`}
        onClick={() => {
          if (myReaction) onReact(myReaction); // toggle off
          else            setOpen(true);
        }}
        style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "5px 10px", borderRadius: 999,
          background: myReaction ? `${currentR.color}22` : "rgba(255,255,255,0.04)",
          color: myReaction ? currentR.color : "#cbd5e1",
          border: `1px solid ${myReaction ? `${currentR.color}55` : "rgba(255,255,255,0.06)"}`,
          fontSize: 12, cursor: "pointer",
        }}
      >
        {currentR
          ? <currentR.Icon size={14} />
          : <ThumbsUp size={14} />}
        <span>{total > 0 ? total : "React"}</span>
      </button>
      {open && (
        <div
          data-testid={`${testIdPrefix}-react-popover`}
          style={{
            position: "absolute", bottom: "calc(100% + 6px)", left: 0,
            display: "flex", gap: 4,
            padding: "6px 8px", borderRadius: 999,
            background: "rgba(20,22,28,0.95)",
            border: "1px solid rgba(255,255,255,0.08)",
            boxShadow: "0 6px 18px rgba(0,0,0,0.45)",
            zIndex: 20,
          }}
        >
          {REACTIONS.map(({ key, Icon, label, color }) => (
            <button
              key={key}
              type="button"
              data-testid={`${testIdPrefix}-react-${key}`}
              aria-label={label}
              onClick={() => { onReact(key); setOpen(false); }}
              style={{
                background: "transparent", border: "none", cursor: "pointer",
                padding: 6, borderRadius: 999,
                color: myReaction === key ? color : "#9aa3af",
                transition: "transform 120ms ease",
              }}
              onMouseEnter={(e) => e.currentTarget.style.transform = "scale(1.2)"}
              onMouseLeave={(e) => e.currentTarget.style.transform = "scale(1.0)"}
              title={label}
            >
              <Icon size={18} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── composer ─────────────────────────────────────────────────────
function Composer({ slug, onPosted }) {
  const [body, setBody]     = useState("");
  const [file, setFile]     = useState(null);
  const [preview, setPrev]  = useState(null);
  const [err, setErr]       = useState(null);
  const [busy, setBusy]     = useState(false);
  const fileInput = useRef();

  const pickFile = (f) => {
    setErr(null);
    if (!f) { setFile(null); setPrev(null); return; }
    if (f.size > IMAGE_MAX_BYTES) {
      setErr("Image must be ≤ 5 MB.");
      return;
    }
    setFile(f);
    const r = new FileReader();
    r.onload = () => setPrev(r.result);
    r.readAsDataURL(f);
  };

  const submit = async () => {
    if (busy) return;
    const text = body.trim();
    if (!text && !file) {
      setErr("Add text or an image.");
      return;
    }
    setBusy(true); setErr(null);
    try {
      const fd = new FormData();
      if (text) fd.append("body", text);
      if (file) fd.append("image", file);
      const r = await axios.post(
        `${API}/stations/${encodeURIComponent(slug)}/posts`,
        fd, { withCredentials: true,
              headers: { "Content-Type": "multipart/form-data" } });
      setBody(""); setFile(null); setPrev(null);
      if (fileInput.current) fileInput.current.value = "";
      onPosted && onPosted(r.data.post);
    } catch (e) {
      const code = e.response?.data?.detail?.code || "error";
      const msg = e.response?.data?.detail?.message;
      if (code === "rate_limited") {
        const wait = e.response?.data?.detail?.retry_after_sec;
        setErr(`You're posting too fast. Try again in ${wait}s.`);
      } else if (code === "image_too_large") {
        setErr("Image is too large (max 5 MB).");
      } else if (code === "not_owner") {
        setErr("Only the station owner can post here.");
      } else {
        setErr(msg || `Couldn't post (${code}).`);
      }
    }
    setBusy(false);
  };

  return (
    <div data-testid="composer"
         style={{ padding: 14, borderRadius: 12,
                   background: "rgba(255,255,255,0.04)",
                   border: "1px solid rgba(255,255,255,0.06)",
                   marginBottom: 18 }}>
      <textarea
        data-testid="composer-textarea"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Share an update with your listeners…"
        maxLength={2000}
        style={{ width: "100%", minHeight: 72, resize: "vertical",
                 background: "rgba(0,0,0,0.25)", color: "#fff",
                 border: "1px solid rgba(255,255,255,0.08)",
                 borderRadius: 8, padding: 10, fontSize: 14,
                 fontFamily: "inherit", outline: "none" }}
      />
      {preview && (
        <div style={{ marginTop: 8, position: "relative",
                       maxWidth: 360, borderRadius: 10, overflow: "hidden" }}>
          <img src={preview} alt="preview"
               style={{ width: "100%", display: "block" }} />
          <button type="button"
                  data-testid="composer-clear-image"
                  onClick={() => pickFile(null)}
                  style={{ position: "absolute", top: 6, right: 6,
                           background: "rgba(0,0,0,0.6)",
                           color: "#fff", border: "none",
                           borderRadius: 999, padding: 4, cursor: "pointer" }}>
            <X size={14} />
          </button>
        </div>
      )}
      <div style={{ display: "flex", alignItems: "center",
                     justifyContent: "space-between",
                     marginTop: 10 }}>
        <button type="button"
                data-testid="composer-pick-image"
                onClick={() => fileInput.current?.click()}
                style={{ background: "transparent",
                         color: "#9aa3af", border: "none",
                         display: "inline-flex", alignItems: "center",
                         gap: 6, cursor: "pointer", fontSize: 13 }}>
          <ImageIcon size={16} /> Add image
        </button>
        <input ref={fileInput} type="file" accept="image/png,image/jpeg,image/webp"
               style={{ display: "none" }}
               onChange={(e) => pickFile(e.target.files?.[0])} />
        <button type="button"
                data-testid="composer-submit"
                onClick={submit} disabled={busy}
                style={{ background: "#00d9ff", color: "#0b0b0b",
                         border: "none", padding: "8px 16px",
                         borderRadius: 8, fontWeight: 600, fontSize: 13,
                         cursor: busy ? "default" : "pointer",
                         opacity: busy ? 0.6 : 1 }}>
          {busy ? "Posting…" : "Post"}
        </button>
      </div>
      {err && <div data-testid="composer-error"
                   style={{ color: "#f87171", fontSize: 12, marginTop: 6 }}>
                {err}
              </div>}
    </div>
  );
}

// ─── comments (lazy under each post) ─────────────────────────────
function CommentList({ slug, post, onPostUpdate }) {
  const [open, setOpen]     = useState(false);
  const [items, setItems]   = useState([]);
  const [loading, setLoad]  = useState(false);
  const [text, setText]     = useState("");
  const [err, setErr]       = useState(null);
  const [busy, setBusy]     = useState(false);

  const load = useCallback(async () => {
    setLoad(true);
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/posts/${post.post_id}/comments?limit=10`,
        { withCredentials: true });
      setItems(r.data.items || []);
    } catch (_e) { /* */ }
    setLoad(false);
  }, [slug, post.post_id]);

  const toggle = () => {
    setOpen((v) => !v);
    if (!open && items.length === 0) load();
  };

  const submit = async () => {
    const body = text.trim();
    if (!body || busy) return;
    setBusy(true); setErr(null);
    try {
      const r = await axios.post(
        `${API}/stations/${encodeURIComponent(slug)}/posts/${post.post_id}/comments`,
        { body }, { withCredentials: true });
      setItems((arr) => [...arr, r.data.comment]);
      setText("");
      // ── Fix 1 (P41 S2.A verification) ─────────────────────────
      // Propagate the new comment_count up so the parent post-card
      // badge increments visibly in the feed without a re-poll.
      if (onPostUpdate) {
        onPostUpdate({ ...post,
                        comment_count: (post.comment_count || 0) + 1 });
      }
    } catch (e) {
      const code = e.response?.data?.detail?.code || "error";
      const msg = e.response?.data?.detail?.message;
      if (code === "rate_limited") {
        setErr("You're commenting too fast.");
      } else {
        setErr(msg || `Couldn't comment (${code}).`);
      }
    }
    setBusy(false);
  };

  return (
    <div style={{ marginTop: 8 }}>
      <button type="button"
              data-testid={`post-${post.post_id}-toggle-comments`}
              onClick={toggle}
              style={{ background: "transparent", border: "none",
                       color: "#9aa3af", fontSize: 12, cursor: "pointer",
                       display: "inline-flex", alignItems: "center", gap: 4,
                       padding: 0 }}>
        <MessageCircle size={13} />
        {post.comment_count || 0} {open ? "Hide" : "Show"} comments
      </button>
      {open && (
        <div data-testid={`post-${post.post_id}-comments`}
             style={{ marginTop: 8 }}>
          {loading && <div style={{ color: "#9aa3af", fontSize: 12 }}>Loading…</div>}
          {items.map((c) => (
            <div key={c.comment_id}
                 data-testid={`comment-${c.comment_id}`}
                 style={{ padding: "6px 0",
                          borderTop: "1px solid rgba(255,255,255,0.04)",
                          fontSize: 13 }}>
              <span style={{ color: "#cbd5e1", fontWeight: 600 }}>
                {c.author_name}
              </span>
              <span style={{ color: "#6b7280", fontSize: 11, marginLeft: 8 }}>
                {relTime(c.created_at)}
              </span>
              <div style={{ color: c.deleted_at ? "#6b7280" : "#e5e7eb",
                            marginTop: 2 }}>
                {c.body}
              </div>
            </div>
          ))}
          <div style={{ marginTop: 8, display: "flex", gap: 6 }}>
            <input
              data-testid={`post-${post.post_id}-comment-input`}
              value={text}
              onChange={(e) => setText(e.target.value)}
              maxLength={500}
              placeholder="Write a comment…"
              style={{ flex: 1, padding: "6px 10px",
                       background: "rgba(0,0,0,0.25)", color: "#fff",
                       border: "1px solid rgba(255,255,255,0.08)",
                       borderRadius: 8, fontSize: 13, outline: "none" }}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
            />
            <button type="button"
                    data-testid={`post-${post.post_id}-comment-submit`}
                    onClick={submit} disabled={busy}
                    style={{ background: "rgba(0,217,255,0.15)",
                             color: "#00d9ff", border: "1px solid #00d9ff",
                             padding: "6px 12px", borderRadius: 8,
                             fontSize: 12, cursor: "pointer",
                             opacity: busy ? 0.6 : 1 }}>
              Send
            </button>
          </div>
          {err && <div data-testid={`post-${post.post_id}-comment-error`}
                       style={{ color: "#f87171", fontSize: 12, marginTop: 4 }}>
                    {err}
                  </div>}
        </div>
      )}
    </div>
  );
}

// ─── post card ────────────────────────────────────────────────────
function PostCard({ slug, post, onUpdate, onDelete }) {
  const { user } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const myId = user?.user_id;
  const canDelete = !post.deleted_at && (
    post.is_mine || post.author_id === myId  // server returns is_mine
  );

  const react = async (rt) => {
    // ── Fix 2 (P41 S2.A verification) — optimistic update ──────
    // Toggle/upgrade/new the user's reaction LOCALLY first so the
    // pill state + counts move on click, then reconcile with the
    // server response. Same-emoji click on an already-active
    // reaction is the toggle-off semantic — we send the request
    // unconditionally (no early return) and let the server confirm.
    const prev = {
      my_reaction:     post.my_reaction,
      reaction_counts: { ...(post.reaction_counts || {}) },
    };
    const counts = { ...prev.reaction_counts };
    let nextMine;
    if (prev.my_reaction === rt) {
      counts[rt] = Math.max(0, (counts[rt] || 0) - 1);
      nextMine = null;
    } else if (prev.my_reaction) {
      counts[prev.my_reaction] =
        Math.max(0, (counts[prev.my_reaction] || 0) - 1);
      counts[rt] = (counts[rt] || 0) + 1;
      nextMine = rt;
    } else {
      counts[rt] = (counts[rt] || 0) + 1;
      nextMine = rt;
    }
    onUpdate({ ...post, reaction_counts: counts, my_reaction: nextMine });
    // Server reconcile
    try {
      const r = await axios.post(
        `${API}/stations/${encodeURIComponent(slug)}/reactions`,
        { target_type: "post", target_id: post.post_id,
          reaction_type: rt },
        { withCredentials: true });
      onUpdate({ ...post,
                  reaction_counts: r.data.counts,
                  my_reaction: r.data.my_reaction });
    } catch (e) {
      // Roll back the optimistic update on error.
      onUpdate({ ...post, ...prev });
    }
  };

  const del = async () => {
    if (!window.confirm("Delete this post?")) return;
    try {
      await axios.delete(
        `${API}/stations/${encodeURIComponent(slug)}/posts/${post.post_id}`,
        { withCredentials: true });
      onDelete(post.post_id);
    } catch (_e) { /* */ }
  };

  return (
    <article
      data-testid={`post-${post.post_id}`}
      data-deleted={post.deleted_at ? "true" : "false"}
      style={{ padding: 14, borderRadius: 12,
               background: "rgba(255,255,255,0.03)",
               border: "1px solid rgba(255,255,255,0.06)",
               marginBottom: 12 }}
    >
      <header style={{ display: "flex", alignItems: "center",
                        justifyContent: "space-between",
                        marginBottom: 6 }}>
        <div>
          <span style={{ color: "#e5e7eb", fontWeight: 600, fontSize: 13 }}>
            {post.author_name || "Anonymous"}
          </span>
          <span style={{ color: "#6b7280", fontSize: 11, marginLeft: 8 }}>
            {relTime(post.created_at)}
          </span>
          {post.deleted_at && (
            <span data-testid={`post-${post.post_id}-deleted-badge`}
                  style={{ color: "#6b7280", fontSize: 10, marginLeft: 8,
                           padding: "1px 6px", borderRadius: 4,
                           background: "rgba(255,255,255,0.04)" }}>
              deleted
            </span>
          )}
        </div>
        {canDelete && (
          <div style={{ position: "relative" }}>
            <button type="button"
                    data-testid={`post-${post.post_id}-menu`}
                    onClick={() => setMenuOpen((v) => !v)}
                    style={{ background: "transparent", border: "none",
                             color: "#6b7280", cursor: "pointer", padding: 4 }}>
              <MoreHorizontal size={16} />
            </button>
            {menuOpen && (
              <div style={{ position: "absolute", right: 0, top: "100%",
                             background: "rgba(20,22,28,0.97)",
                             border: "1px solid rgba(255,255,255,0.08)",
                             borderRadius: 8, padding: 6, zIndex: 10 }}>
                <button type="button"
                        data-testid={`post-${post.post_id}-delete`}
                        onClick={del}
                        style={{ background: "transparent", border: "none",
                                 color: "#f87171", display: "flex", gap: 6,
                                 alignItems: "center", padding: "6px 10px",
                                 fontSize: 12, cursor: "pointer", width: "100%" }}>
                  <Trash2 size={13} /> Delete
                </button>
              </div>
            )}
          </div>
        )}
      </header>
      {post.body && (
        <div data-testid={`post-${post.post_id}-body`}
             style={{ color: post.deleted_at ? "#6b7280" : "#e5e7eb",
                       fontSize: 14, lineHeight: 1.55, whiteSpace: "pre-wrap" }}>
          {post.body}
        </div>
      )}
      {post.image_url && (
        <img data-testid={`post-${post.post_id}-image`}
             src={post.image_url} alt=""
             style={{ width: "100%", maxHeight: 480, objectFit: "cover",
                       borderRadius: 8, marginTop: 8 }} />
      )}
      <footer style={{ display: "flex", alignItems: "center", gap: 12,
                        marginTop: 10 }}>
        <ReactionBar
          counts={post.reaction_counts}
          myReaction={post.my_reaction}
          onReact={react}
          testIdPrefix={`post-${post.post_id}`}
        />
        <CommentList slug={slug} post={post} onPostUpdate={onUpdate} />
      </footer>
    </article>
  );
}

// ─── main feed wrapper ───────────────────────────────────────────
export default function StationFeed({ slug, station }) {
  const { user } = useAuth();
  const isOwner = !!(user && station &&
                      station.owner_user_id === user.user_id);
  const [posts, setPosts]   = useState(null);
  const [err, setErr]       = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await axios.get(
        `${API}/stations/${encodeURIComponent(slug)}/posts?limit=20`,
        { withCredentials: true });
      setPosts(r.data.items || []);
    } catch (e) {
      setErr(e.response?.data?.detail?.code || "error");
    }
  }, [slug]);

  // Single effect for initial load + visibility-aware polling. setState
  // inside `load` happens only after `await` resolves (microtask, not
  // sync) so this satisfies react-hooks/set-state-in-effect.
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    const tick = () => {
      if (!cancelled && document.visibilityState === "visible") load();
    };
    const startPoll = () => {
      if (!timer) timer = setInterval(tick, POLL_INTERVAL_MS);
    };
    const stopPoll = () => {
      if (timer) { clearInterval(timer); timer = null; }
    };
    const onVis = () => {
      if (document.visibilityState === "visible") {
        load();
        startPoll();
      } else {
        stopPoll();
      }
    };
    // Initial async load + polling kick-off in a microtask, never sync.
    Promise.resolve().then(() => {
      if (cancelled) return;
      load();
      if (document.visibilityState === "visible") startPoll();
    });
    document.addEventListener("visibilitychange", onVis);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVis);
      stopPoll();
    };
  }, [load]);

  // Phase 41 S2.C.1 — anchor-scroll on load: when the URL contains a
  // `#post-<id>` hash, scroll to that post and briefly highlight it.
  // Triggered after `posts` has loaded (so the DOM has the cards).
  useEffect(() => {
    if (!posts || posts.length === 0) return undefined;
    const hash = (window.location.hash || "").replace(/^#/, "");
    if (!hash.startsWith("post-")) return undefined;
    const id = hash.slice("post-".length);
    let cleared = false;
    const t = setTimeout(() => {
      if (cleared) return;
      const el = document.querySelector(`[data-testid="post-${id}"]`);
      if (!el) return;
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.style.transition = "box-shadow 600ms ease";
      el.style.boxShadow =
        "0 0 0 2px rgba(0,217,255,0.55), 0 0 24px rgba(0,217,255,0.25)";
      setTimeout(() => {
        if (el) el.style.boxShadow = "";
      }, 2400);
    }, 300);
    return () => { cleared = true; clearTimeout(t); };
  }, [posts]);

  const onPosted = (newPost) => {
    setPosts((arr) => [newPost, ...(arr || [])]);
  };
  const onUpdate = (updated) => {
    setPosts((arr) => (arr || []).map((p) =>
      p.post_id === updated.post_id ? { ...p, ...updated } : p));
  };
  const onDelete = (post_id) => {
    setPosts((arr) => (arr || []).map((p) =>
      p.post_id === post_id ? { ...p, deleted_at: new Date().toISOString(),
                                  body: "[deleted]", image_url: null } : p));
  };

  const headerCount = useMemo(() => posts ? posts.filter(
    (p) => !p.deleted_at).length : 0, [posts]);

  return (
    <section data-testid="station-feed"
             style={{ marginTop: 26 }}>
      <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12,
                    color: "#fff", display: "flex",
                    alignItems: "center", gap: 8 }}>
        Station feed
        {posts && (
          <span data-testid="station-feed-count"
                style={{ color: "#9aa3af", fontSize: 12, fontWeight: 400 }}>
            {headerCount} post{headerCount === 1 ? "" : "s"}
          </span>
        )}
      </h3>
      {isOwner && <Composer slug={slug} onPosted={onPosted} />}
      {err && (
        <div data-testid="station-feed-error"
             style={{ color: "#f87171", fontSize: 13, padding: 10 }}>
          Couldn&rsquo;t load the feed.
        </div>
      )}
      {!err && posts === null && (
        <div data-testid="station-feed-skeleton">
          {[0, 1, 2].map((i) => (
            <div key={i} style={{ height: 110, marginBottom: 12,
                                    borderRadius: 12,
                                    background: "rgba(255,255,255,0.03)" }} />
          ))}
        </div>
      )}
      {!err && posts && posts.length === 0 && (
        <div data-testid="station-feed-empty"
             style={{ color: "#9aa3af", fontSize: 13, padding: "18px 4px" }}>
          {isOwner
            ? "Share your first post — listeners will see it here."
            : "No posts yet."}
        </div>
      )}
      {!err && posts && posts.map((p) => (
        <PostCard key={p.post_id} slug={slug} post={p}
                  onUpdate={onUpdate} onDelete={onDelete} />
      ))}
    </section>
  );
}
