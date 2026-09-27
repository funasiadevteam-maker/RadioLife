// FUUSIC Social V2 — Social Home wall.
// The combined "what people & things I care about are doing right now" feed:
// compact quick actions + composer + FOLLOWING/FOR YOU toggle + a diversity-
// balanced, AI-ranked wall of real activity. Extends the shared social backend
// (GET /api/social/feed-v2). No duplicate feed/social systems.
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Headphones, Moon, Gamepad2, MapPin, Loader2, Heart, MessageCircle, Share2,
  ChevronRight, Radio, Video, Sparkles, Store, Users, Play, ArrowUp, Image as ImageIcon,
  X, SlidersHorizontal, Check,
} from "lucide-react";
import { Avatar } from "./SocialV2";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const social = axios.create({ baseURL: `${BACKEND}/api/social`, withCredentials: true });

const fireEvent = (event, extra = {}) =>
  social.post("/feed-events", { event, ...extra }).catch(() => {});

const TAROT_ICON = "🃏";

// ───────────────────────── Quick actions ───────────────────────────
function QuickActions({ actions }) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5" data-testid="social-quick-actions">
      {actions.map((a) => (
        <button key={a.key} type="button" onClick={a.on} data-testid={`social-quick-${a.key}`}
                className="group text-left rounded-2xl px-3.5 py-3 border border-white/10 bg-white/[0.04] hover:bg-white/[0.07] transition flex items-center gap-3"
                style={{ minHeight: 84 }}>
          <span className="grid place-items-center w-10 h-10 rounded-xl shrink-0 text-white"
                style={{ background: a.grad }}>
            {a.emoji ? <span className="text-lg leading-none">{a.emoji}</span> : <a.icon size={18} />}
          </span>
          <span className="min-w-0">
            <span className="block text-sm font-black truncate">{a.label}</span>
            <span className="block text-[11px] text-slate-400 truncate">{a.blurb}</span>
          </span>
        </button>
      ))}
    </div>
  );
}

// ───────────────────────── Composer ────────────────────────────────
function Composer({ onOpenMoment, onDream }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 flex items-center gap-3"
         data-testid="social-composer">
      <button type="button" onClick={onOpenMoment} data-testid="composer-open"
              className="flex-1 text-left text-sm text-slate-400 rounded-full bg-white/[0.05] border border-white/10 px-4 py-2.5">
        Share something with your friends…
      </button>
      <button type="button" onClick={onOpenMoment} data-testid="composer-photo"
              className="w-10 h-10 grid place-items-center rounded-full bg-white/10 hover:bg-white/20">
        <ImageIcon size={17} className="text-pink-300" />
      </button>
      <button type="button" onClick={onDream} data-testid="composer-dream"
              className="w-10 h-10 grid place-items-center rounded-full bg-white/10 hover:bg-white/20">
        <Moon size={17} className="text-violet-300" />
      </button>
    </div>
  );
}

function MomentComposerModal({ onClose, onPosted }) {
  const [caption, setCaption] = useState("");
  const [media, setMedia] = useState("");
  const [busy, setBusy] = useState(false);
  const post = async () => {
    if (!caption.trim() && !media.trim()) { toast.error("Add a caption or an image URL"); return; }
    setBusy(true);
    try {
      await social.post("/moments", {
        caption: caption.trim(), media_url: media.trim() || null,
        media_type: media.trim() ? "photo" : null, visibility: "friends",
      });
      toast.success("Shared to your friends");
      onPosted?.();
      onClose();
    } catch (_) { toast.error("Couldn't post that moment"); }
    finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm"
         onClick={onClose} data-testid="moment-composer">
      <div className="w-full sm:max-w-lg rounded-t-3xl sm:rounded-3xl border border-white/10 p-5"
           style={{ background: "linear-gradient(180deg,#12102b,#0b0918)" }}
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-black">Share a moment</h3>
          <button type="button" onClick={onClose} className="w-9 h-9 grid place-items-center rounded-full bg-white/10">
            <X size={18} />
          </button>
        </div>
        <textarea value={caption} onChange={(e) => setCaption(e.target.value)} rows={3}
                  data-testid="moment-caption" placeholder="What's happening?"
                  className="w-full rounded-2xl bg-white/[0.05] border border-white/10 p-3 text-sm outline-none focus:border-purple-400/60 resize-none" />
        <input value={media} onChange={(e) => setMedia(e.target.value)} data-testid="moment-media"
               placeholder="Image URL (optional)"
               className="mt-2 w-full rounded-2xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <button type="button" onClick={post} disabled={busy} data-testid="moment-post"
                className="mt-3 w-full h-11 rounded-full font-bold text-white disabled:opacity-60"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {busy ? <Loader2 className="animate-spin mx-auto" size={18} /> : "Share moment"}
        </button>
      </div>
    </div>
  );
}

// ───────────────────────── Wall card ───────────────────────────────
const TYPE_META = {
  MOMENT: { verb: "shared a moment", icon: ImageIcon, tone: "#f472b6" },
  LIVE_VIDEO: { verb: "went live", icon: Video, tone: "#ef4444" },
  BUSINESS_LIVE: { verb: "is live shopping", icon: Video, tone: "#ef4444" },
  EVENT: { verb: "has an upcoming event", icon: Sparkles, tone: "#22d3ee" },
  LISTEN_ROOM: { verb: "is listening together", icon: Headphones, tone: "#22d3ee" },
  DREAM: { verb: "shared a dream", icon: Moon, tone: "#a855f7" },
  CLUB_POST: { verb: "posted in a club", icon: Users, tone: "#a855f7" },
  TAROT_SHARE: { verb: "shared a Tarot card", icon: null, emoji: TAROT_ICON, tone: "#c084fc" },
  STATION_ACTIVITY: { verb: "posted", icon: Radio, tone: "#38bdf8" },
};

function RelChip({ rel }) {
  const map = {
    friend_following: ["Friend · Following", "#22d3ee"],
    friend: ["Friend", "#22d3ee"],
    following: ["Following", "#a855f7"],
  };
  const m = map[rel];
  if (!m) return null;
  return (
    <span className="text-[9px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full"
          style={{ background: `${m[1]}22`, color: m[1] }}>{m[0]}</span>
  );
}

function WallCard({ item, mode, onFollow }) {
  const navigate = useNavigate();
  const meta = TYPE_META[item.type] || { verb: "", icon: Sparkles, tone: "#a855f7" };
  const actor = item.actor || {};
  const [liked, setLiked] = useState(false);
  const [likeCount, setLikeCount] = useState(item.meta?.like_count || 0);
  const [followed, setFollowed] = useState(false);

  const cardRef = useRef(null);
  useEffect(() => {
    const el = cardRef.current;
    if (!el) return;
    const ob = new IntersectionObserver((es) => {
      es.forEach((e) => {
        if (e.isIntersecting) {
          fireEvent("feed_item_impression", { item_id: item.id, item_type: item.type, mode });
          ob.disconnect();
        }
      });
    }, { threshold: 0.5 });
    ob.observe(el);
    return () => ob.disconnect();
  }, [item.id, item.type, mode]);

  const openCta = () => {
    fireEvent("feed_item_open", { item_id: item.id, item_type: item.type, mode });
    const t = item.cta?.target;
    switch (item.cta?.action) {
      case "open_room": fireEvent("feed_join_room", { item_id: item.id }); navigate(`/social/room/${t}`); break;
      case "open_live": fireEvent("feed_watch_live", { item_id: item.id }); navigate(`/social?tab=live`); break;
      case "open_dream": fireEvent("feed_dream_similar", { item_id: item.id }); navigate(`/social/dreams`); break;
      case "open_tarot": fireEvent("feed_tarot_open", { item_id: item.id }); navigate(`/social/tarot`); break;
      case "open_station": navigate(`/r/${t}`); break;
      case "open_moment": default: navigate(`/social?tab=moments`); break;
    }
  };

  const like = async () => {
    if (item.type !== "MOMENT") return;
    const id = item.id.split(":")[1];
    setLiked((v) => !v); setLikeCount((c) => c + (liked ? -1 : 1));
    try { const r = await social.post(`/moments/${id}/like`); setLiked(r.data.liked_by_me); setLikeCount(r.data.like_count); }
    catch (_) { setLiked((v) => !v); }
  };

  const follow = async () => {
    if (!actor.id) return;
    setFollowed(true);
    try { await social.post(`/follow/${actor.id}`); fireEvent("feed_follow_click", { item_id: item.id }); onFollow?.(); toast.success(`Following ${actor.name}`); }
    catch (_) { setFollowed(false); toast.error("Couldn't follow"); }
  };

  const showFollow = mode === "for_you" && item.follow_relationship === "discovery"
    && actor.kind === "user" && actor.id && !actor.anonymous;

  return (
    <div ref={cardRef} data-testid={`wall-card-${item.type}`}
         className="rounded-2xl border border-white/10 bg-white/[0.035] overflow-hidden">
      <div className="flex items-center gap-3 p-3.5">
        <Avatar name={actor.name} url={actor.avatar_url} size={40} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-black truncate">{actor.name || "FUUSIC"}</span>
            <span className="text-xs text-slate-400 truncate">{meta.verb}</span>
            <RelChip rel={item.follow_relationship} />
          </div>
          {item.context_label && (
            <div className="text-[10px] text-slate-500">{item.context_label}</div>
          )}
        </div>
        <span className="grid place-items-center w-8 h-8 rounded-lg shrink-0"
              style={{ background: `${meta.tone}22`, color: meta.tone }}>
          {meta.emoji ? <span>{meta.emoji}</span> : <meta.icon size={15} />}
        </span>
      </div>

      {(item.title || item.text) && (
        <div className="px-3.5 pb-2">
          {item.title && <div className="text-[15px] font-bold leading-snug">{item.title}</div>}
          {item.text && <div className="text-sm text-slate-300 leading-snug mt-0.5">{item.text}</div>}
          {item.meta?.tags?.length > 0 && (
            <div className="mt-1.5 flex gap-1.5 flex-wrap">
              {item.meta.tags.map((t) => (
                <span key={t} className="text-[10px] text-violet-300">#{t}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {item.media_url && (
        <button type="button" onClick={openCta} className="block w-full">
          <div className="relative w-full aspect-video bg-black/30">
            <img src={item.media_url} alt="" className="w-full h-full object-cover" />
            {(item.type === "LIVE_VIDEO" || item.type === "BUSINESS_LIVE") && (
              <span className="absolute top-3 left-3 inline-flex items-center gap-1 text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-full bg-red-500/90 text-white">
                <span className="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> Live
              </span>
            )}
            {item.type === "EVENT" && (
              <span className="absolute top-3 left-3 text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded-full bg-cyan-500/90 text-slate-950">
                Upcoming
              </span>
            )}
          </div>
        </button>
      )}

      {item.meta?.products?.length > 0 && (
        <div className="px-3.5 pt-2 flex gap-2 overflow-x-auto no-scrollbar">
          {item.meta.products.map((p, i) => (
            <span key={i} className="flex-shrink-0 text-[11px] font-bold px-2.5 py-1 rounded-full bg-white/10">
              {p.title} · ${((p.price_cents || 0) / 100).toFixed(0)}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 p-3">
        {item.type === "MOMENT" && (
          <>
            <button type="button" onClick={like} data-testid={`wall-like-${item.id}`}
                    className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-300 hover:text-pink-300">
              <Heart size={17} fill={liked ? "#f472b6" : "none"} color={liked ? "#f472b6" : "currentColor"} /> {likeCount}
            </button>
            <button type="button" onClick={openCta}
                    className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-300 hover:text-slate-100">
              <MessageCircle size={17} /> {item.meta?.comment_count || 0}
            </button>
          </>
        )}
        <div className="flex-1" />
        {showFollow ? (
          <button type="button" onClick={follow} disabled={followed} data-testid={`wall-follow-${item.id}`}
                  className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-sm font-bold text-white disabled:opacity-60"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            {followed ? "Following" : "Follow"}
          </button>
        ) : (
          <button type="button" onClick={openCta} data-testid={`wall-cta-${item.id}`}
                  className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-sm font-bold text-white"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
            {item.cta?.label || "Open"} <ChevronRight size={15} />
          </button>
        )}
      </div>
    </div>
  );
}

// ───────────────────────── Interest picker ─────────────────────────
function InterestPickerModal({ onClose, onSaved }) {
  const [topics, setTopics] = useState([]);
  const [sel, setSel] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    social.get("/interests")
      .then((r) => { setTopics(r.data?.topics || []); setSel(r.data?.selected || []); })
      .catch(() => {});
  }, []);
  const toggle = (id) =>
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
  const save = async () => {
    setBusy(true);
    try {
      await social.put("/interests", { interests: sel });
      toast.success("Suggestions tuned to your interests");
      onSaved?.(); onClose();
    } catch (_) { toast.error("Couldn't save interests"); }
    finally { setBusy(false); }
  };
  return (
    <div className="fixed inset-0 z-[70] flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm"
         onClick={onClose} data-testid="interest-picker">
      <div className="w-full sm:max-w-lg rounded-t-3xl sm:rounded-3xl border border-white/10 p-5"
           style={{ background: "linear-gradient(180deg,#12102b,#0b0918)" }}
           onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2 text-purple-300 text-[10px] font-black uppercase tracking-widest">
            <SlidersHorizontal size={13} /> Tune your suggestions
          </div>
          <button type="button" onClick={onClose} data-testid="interest-close"
                  className="w-9 h-9 grid place-items-center rounded-full bg-white/10"><X size={18} /></button>
        </div>
        <p className="text-sm text-slate-400 mb-4">
          Pick a few topics you love — we'll surface creators who match, on top of your mutual friends.
        </p>
        <div className="flex flex-wrap gap-2">
          {topics.map((t) => {
            const on = sel.includes(t.id);
            return (
              <button key={t.id} type="button" onClick={() => toggle(t.id)}
                      data-testid={`interest-chip-${t.id}`}
                      className={`inline-flex items-center gap-1.5 h-9 px-4 rounded-full text-sm font-bold border transition ${
                        on ? "text-white border-transparent" : "text-slate-300 border-white/15 bg-white/[0.04]"}`}
                      style={on ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" } : undefined}>
                {on && <Check size={14} />} {t.label}
              </button>
            );
          })}
        </div>
        <button type="button" onClick={save} disabled={busy} data-testid="interest-save"
                className="mt-5 w-full h-11 rounded-full font-bold text-white disabled:opacity-60"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {busy ? <Loader2 className="animate-spin mx-auto" size={18} /> : "Save interests"}
        </button>
      </div>
    </div>
  );
}

// ───────────────────────── Wall ────────────────────────────────────
export default function SocialWall({ actions, onOpenFollowing }) {
  const navigate = useNavigate();
  const [mode, setMode] = useState("following");
  const [items, setItems] = useState([]);
  const [cursor, setCursor] = useState(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [composerOpen, setComposerOpen] = useState(false);
  const [interestsOpen, setInterestsOpen] = useState(false);
  const [newCount, setNewCount] = useState(0);
  const latestRef = useRef(null);

  const fetchFeed = useCallback(async (m, reset = true) => {
    if (reset) setLoading(true);
    try {
      const r = await social.get("/feed-v2", { params: { mode: m, limit: 20 } });
      setItems(r.data.items || []);
      setCursor(r.data.next_cursor || null);
      setHasMore(!!r.data.has_more);
      latestRef.current = (r.data.items || [])[0]?.created_at || null;
      setNewCount(0);
      fireEvent("social_feed_view", { mode: m });
      fireEvent(m === "following" ? "social_feed_mode_following" : "social_feed_mode_for_you", { mode: m });
    } catch (_) { /* soft */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { fetchFeed(mode, true); }, [mode, fetchFeed]);

  // Dynamic refresh — poll new-count every 60s; auto-refresh only when at top.
  useEffect(() => {
    const tick = async () => {
      if (document.hidden || !latestRef.current) return;
      try {
        const r = await social.get("/feed-v2/new-count", { params: { since: latestRef.current, mode } });
        const n = r.data.new_count || 0;
        if (n > 0) {
          if (window.scrollY < 240) fetchFeed(mode, false);
          else setNewCount(n);
        }
      } catch (_) {}
    };
    const id = setInterval(tick, 60000);
    const onFocus = () => tick();
    window.addEventListener("focus", onFocus);
    return () => { clearInterval(id); window.removeEventListener("focus", onFocus); };
  }, [mode, fetchFeed]);

  const loadMore = async () => {
    if (!cursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const r = await social.get("/feed-v2", { params: { mode, cursor, limit: 20 } });
      setItems((prev) => [...prev, ...(r.data.items || [])]);
      setCursor(r.data.next_cursor || null);
      setHasMore(!!r.data.has_more);
    } catch (_) {} finally { setLoadingMore(false); }
  };

  const showNew = () => { window.scrollTo({ top: 0, behavior: "smooth" }); fetchFeed(mode, false); };

  return (
    <div className="space-y-5" data-testid="social-wall">
      <QuickActions actions={actions} />
      <Composer onOpenMoment={() => setComposerOpen(true)} onDream={() => navigate("/social/dreams")} />

      {/* FOLLOWING / FOR YOU toggle */}
      <div className="flex items-center gap-2" data-testid="wall-mode-toggle">
        {[["following", "Following"], ["for_you", "For You"]].map(([k, label]) => {
          const active = mode === k;
          return (
            <button key={k} type="button" onClick={() => setMode(k)} data-testid={`wall-mode-${k}`}
                    className={`h-9 px-5 rounded-full text-sm font-black transition ${active ? "text-white" : "text-slate-400 bg-white/[0.04]"}`}
                    style={active ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" } : undefined}>
              {label}
            </button>
          );
        })}
        <div className="flex-1" />
        <button type="button" onClick={() => setInterestsOpen(true)} data-testid="wall-tune-suggestions"
                className="inline-flex items-center gap-1.5 text-xs font-bold text-slate-400 hover:text-white">
          <SlidersHorizontal size={13} /> Tune suggestions
        </button>
        <button type="button" onClick={onOpenFollowing} data-testid="wall-open-following"
                className="text-xs font-bold text-slate-400 hover:text-white">Manage following</button>
      </div>

      {newCount > 0 && (
        <button type="button" onClick={showNew} data-testid="wall-new-posts"
                className="w-full h-11 rounded-full text-sm font-black text-white flex items-center justify-center gap-2"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          <ArrowUp size={16} /> {newCount} new post{newCount > 1 ? "s" : ""}
        </button>
      )}

      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="rounded-2xl border border-white/10 bg-white/[0.03] h-40 animate-pulse" />
          ))}
        </div>
      ) : items.length === 0 ? (
        <WallEmpty mode={mode} onOpenFollowing={onOpenFollowing} switchForYou={() => setMode("for_you")} />
      ) : (
        <div className="space-y-3" data-testid="wall-items">
          {items.map((it) => (
            <WallCard key={it.id} item={it} mode={mode} onFollow={() => fetchFeed(mode, false)} />
          ))}
          {hasMore && (
            <button type="button" onClick={loadMore} disabled={loadingMore} data-testid="wall-load-more"
                    className="w-full h-11 rounded-full font-bold bg-white/[0.06] border border-white/10">
              {loadingMore ? <Loader2 className="animate-spin mx-auto" size={18} /> : "Load more"}
            </button>
          )}
        </div>
      )}

      {composerOpen && (
        <MomentComposerModal onClose={() => setComposerOpen(false)}
                             onPosted={() => fetchFeed(mode, false)} />
      )}
      {interestsOpen && (
        <InterestPickerModal onClose={() => setInterestsOpen(false)}
                             onSaved={() => fetchFeed(mode, false)} />
      )}
    </div>
  );
}

function WallEmpty({ mode, onOpenFollowing, switchForYou }) {
  if (mode === "for_you") {
    return (
      <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-10 text-center" data-testid="wall-empty">
        <Sparkles className="mx-auto text-purple-300 mb-3" size={28} />
        <h3 className="text-xl font-black">You're all caught up</h3>
        <p className="text-slate-400 mt-2 text-sm">Check back soon for fresh activity near you.</p>
      </div>
    );
  }
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-10 text-center" data-testid="wall-empty">
      <Users className="mx-auto text-purple-300 mb-3" size={28} />
      <h3 className="text-xl font-black">Build your FUUSIC feed</h3>
      <p className="text-slate-400 mt-2 text-sm max-w-sm mx-auto">
        Follow people, businesses, creators and clubs you care about — their moments,
        live shows and dreams will show up here.
      </p>
      <div className="mt-4 flex flex-col sm:flex-row gap-2 justify-center">
        <button type="button" onClick={onOpenFollowing} data-testid="wall-empty-follow"
                className="h-11 px-5 rounded-full font-bold text-white"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>Find people to follow</button>
        <button type="button" onClick={switchForYou}
                className="h-11 px-5 rounded-full font-bold bg-white/10">Explore For You</button>
      </div>
    </div>
  );
}
