// FUUSIC Social V2 — Phase 2 web surfaces: Moments, Local Pulse,
// Go Together (plans) and Play Together (game sessions).
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Loader2, Camera, Image as ImageIcon, Mic, Video, Send, Heart,
  MessageCircle, X, MapPin, Gamepad2, Users, Globe, Radio, Play,
  Music, Utensils, Sparkles, Trash2, ChevronRight,
} from "lucide-react";
import { Avatar } from "./SocialV2";

const B = process.env.REACT_APP_BACKEND_URL || "";
const api = axios.create({ baseURL: `${B}/api/social`, withCredentials: true });

const grad = { background: "linear-gradient(135deg,#a855f7,#ec4899)" };
const CTX_KINDS = [
  { key: "listening", label: "Listening", icon: Music },
  { key: "eating", label: "Eating", icon: Utensils },
  { key: "playing", label: "Playing", icon: Gamepad2 },
  { key: "place", label: "At a place", icon: MapPin },
  { key: "custom", label: "Just vibing", icon: Sparkles },
];
const CTX_ICON = Object.fromEntries(CTX_KINDS.map((c) => [c.key, c.icon]));

function timeAgo(iso) {
  if (!iso) return "";
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

// ═══════════════════════════ Moments ═══════════════════════════════
export function MomentsTab() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try { const { data } = await api.get("/moments"); setItems(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <div className="space-y-5" data-testid="social-moments">
      <MomentComposer onPosted={load} />
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="animate-spin text-purple-400" /></div>
      ) : items.length === 0 ? (
        <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-8 text-center text-slate-400">
          No moments yet — share what you’re listening to or up to. 📸
        </div>
      ) : (
        <div className="space-y-4">
          {items.map((m) => <MomentCard key={m.moment_id} m={m} onChange={load} />)}
        </div>
      )}
    </div>
  );
}

function MomentComposer({ onPosted }) {
  const fileRef = useRef(null);
  const [caption, setCaption] = useState("");
  const [media, setMedia] = useState(null);      // {url, media_type}
  const [uploading, setUploading] = useState(false);
  const [posting, setPosting] = useState(false);
  const [ctxKind, setCtxKind] = useState("custom");
  const [ctxLabel, setCtxLabel] = useState("");
  const [vis, setVis] = useState("friends");

  const pick = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setUploading(true);
    try {
      const fd = new FormData(); fd.append("file", f);
      const { data } = await api.post("/media/upload", fd);
      setMedia({ url: data.url, media_type: data.media_type });
    } catch (_) { toast.error("Couldn’t upload that file."); } finally { setUploading(false); }
  };

  const post = async () => {
    if (!media && !caption.trim()) { toast.info("Add a photo or a caption first."); return; }
    setPosting(true);
    try {
      const body = {
        caption, visibility: vis,
        media_url: media?.url, media_type: media?.media_type,
        context: ctxLabel.trim() ? { kind: ctxKind, label: ctxLabel.trim() } : { kind: ctxKind, label: CTX_KINDS.find((c) => c.key === ctxKind)?.label || "" },
      };
      const { data } = await api.post("/moments", body);
      toast.success(data?.points_awarded ? "Moment shared 💫  +1 point" : "Moment shared 💫");
      setCaption(""); setMedia(null); setCtxLabel(""); setCtxKind("custom");
      window.dispatchEvent(new Event("dreams-streak-refresh"));
      onPosted?.();
    } catch (_) { toast.error("Couldn’t share that moment."); } finally { setPosting(false); }
  };

  return (
    <div className="rounded-3xl bg-white/[0.04] border border-white/10 p-4" data-testid="moment-composer">
      <textarea value={caption} onChange={(e) => setCaption(e.target.value)} rows={2}
                placeholder="What’s the moment? What are you listening to right now?"
                data-testid="moment-caption"
                className="w-full bg-transparent resize-none outline-none text-sm placeholder:text-slate-500" />
      {media && (
        <div className="relative mt-2 rounded-2xl overflow-hidden border border-white/10">
          {media.media_type === "photo" && <img src={media.url} alt="" className="w-full max-h-72 object-cover" />}
          {media.media_type === "video" && <video src={media.url} controls className="w-full max-h-72" />}
          {media.media_type === "voice" && <audio src={media.url} controls className="w-full" />}
          <button onClick={() => setMedia(null)} data-testid="moment-media-remove"
                  className="absolute top-2 right-2 w-8 h-8 grid place-items-center rounded-full bg-black/60"><X size={15} /></button>
        </div>
      )}
      {/* context chips */}
      <div className="flex gap-1.5 mt-3 flex-wrap">
        {CTX_KINDS.map((c) => (
          <button key={c.key} onClick={() => setCtxKind(c.key)} data-testid={`moment-ctx-${c.key}`}
                  className={`inline-flex items-center gap-1.5 px-3 h-8 rounded-full text-xs font-bold ${ctxKind === c.key ? "text-white" : "bg-white/[0.05] text-slate-400"}`}
                  style={ctxKind === c.key ? grad : undefined}>
            <c.icon size={13} /> {c.label}
          </button>
        ))}
      </div>
      {ctxKind !== "custom" && (
        <input value={ctxLabel} onChange={(e) => setCtxLabel(e.target.value)} data-testid="moment-ctx-label"
               placeholder={ctxKind === "listening" ? "Track or station…" : ctxKind === "eating" ? "What / where…" : ctxKind === "playing" ? "Game…" : "Place…"}
               className="mt-2 w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2 text-sm outline-none" />
      )}
      <div className="flex items-center gap-2 mt-3">
        <input ref={fileRef} type="file" accept="image/*,video/*,audio/*" hidden onChange={pick} data-testid="moment-file-input" />
        <button onClick={() => fileRef.current?.click()} disabled={uploading} data-testid="moment-attach"
                className="inline-flex items-center gap-2 h-10 px-3 rounded-full bg-white/[0.05] text-slate-300 text-sm font-bold">
          {uploading ? <Loader2 size={16} className="animate-spin" /> : <ImageIcon size={16} />} Media
        </button>
        <button onClick={() => setVis(vis === "friends" ? "public" : "friends")} data-testid="moment-visibility"
                className="inline-flex items-center gap-2 h-10 px-3 rounded-full bg-white/[0.05] text-slate-300 text-sm font-bold">
          {vis === "public" ? <Globe size={16} /> : <Users size={16} />} {vis === "public" ? "Public" : "Friends"}
        </button>
        <button onClick={post} disabled={posting} data-testid="moment-post"
                className="ml-auto inline-flex items-center gap-2 h-10 px-5 rounded-full text-white text-sm font-black" style={grad}>
          {posting ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />} Share
        </button>
      </div>
    </div>
  );
}

function MomentCard({ m, onChange }) {
  const [liked, setLiked] = useState(m.liked_by_me);
  const [likes, setLikes] = useState(m.like_count);
  const [showC, setShowC] = useState(false);
  const [comments, setComments] = useState(null);
  const [ctext, setCtext] = useState("");
  const [trLang, setTrLang] = useState("hi");
  const [trText, setTrText] = useState(null);
  const [trBusy, setTrBusy] = useState(false);
  const Ctx = CTX_ICON[m.context?.kind] || Sparkles;

  const translate = async () => {
    if (trText) { setTrText(null); return; }
    setTrBusy(true);
    try { const { data } = await api.post(`/translate`, { text: m.caption, target_lang: trLang }); setTrText(data.translated); }
    catch (_) { toast.error("Couldn’t translate."); } finally { setTrBusy(false); }
  };

  const toggleLike = async () => {
    setLiked((v) => !v); setLikes((n) => n + (liked ? -1 : 1));
    try { const { data } = await api.post(`/moments/${m.moment_id}/like`); setLiked(data.liked_by_me); setLikes(data.like_count); }
    catch (_) {}
  };
  const openComments = async () => {
    setShowC((v) => !v);
    if (comments === null) {
      try { const { data } = await api.get(`/moments/${m.moment_id}/comments`); setComments(data.items || []); } catch (_) { setComments([]); }
    }
  };
  const addComment = async () => {
    if (!ctext.trim()) return;
    try {
      const { data } = await api.post(`/moments/${m.moment_id}/comments`, { text: ctext.trim() });
      setComments((c) => [...(c || []), data]); setCtext("");
    } catch (_) {}
  };
  const del = async () => {
    try { await api.delete(`/moments/${m.moment_id}`); toast.success("Moment removed"); onChange?.(); } catch (_) {}
  };

  return (
    <div className="rounded-3xl bg-white/[0.04] border border-white/10 overflow-hidden" data-testid={`moment-${m.moment_id}`}>
      <div className="flex items-center gap-3 p-4 pb-3">
        <Avatar name={m.author?.name} url={m.author?.avatar_url} size={38} />
        <div className="min-w-0 flex-1">
          <div className="font-bold text-sm truncate">{m.author?.name || "Listener"}</div>
          <div className="text-[11px] text-slate-400 flex items-center gap-1">
            {timeAgo(m.created_at)} ago{m.city ? ` · ${m.city}` : ""}
          </div>
        </div>
        {m.is_mine && <button onClick={del} data-testid={`moment-delete-${m.moment_id}`} className="text-slate-500 hover:text-red-400"><Trash2 size={16} /></button>}
      </div>
      {m.context?.label && (
        <div className="mx-4 mb-3 inline-flex items-center gap-1.5 px-3 h-7 rounded-full bg-purple-500/15 text-purple-200 text-xs font-bold">
          <Ctx size={13} /> {m.context.label}{m.context.sub ? ` · ${m.context.sub}` : ""}
        </div>
      )}
      {m.caption && <p className="px-4 pb-2 text-sm text-slate-200">{trText || m.caption}</p>}
      {m.caption && (
        <div className="px-4 pb-3 flex items-center gap-2">
          <select value={trLang} onChange={(e) => { setTrLang(e.target.value); setTrText(null); }} data-testid={`moment-tr-lang-${m.moment_id}`}
                  className="bg-white/[0.05] border border-white/10 rounded-full text-[11px] text-slate-300 h-7 px-2 outline-none">
            {["hi","ar","es","fr","en"].map((l) => <option key={l} value={l} className="bg-[#1a1030]">{l.toUpperCase()}</option>)}
          </select>
          <button onClick={translate} disabled={trBusy} data-testid={`moment-translate-${m.moment_id}`}
                  className="inline-flex items-center gap-1 text-[11px] font-bold text-purple-300">
            {trBusy ? <Loader2 size={12} className="animate-spin" /> : <Globe size={12} />} {trText ? "Show original" : "Translate"}
          </button>
        </div>
      )}
      {m.media_url && (
        <div className="bg-black/30">
          {m.media_type === "photo" && <img src={m.media_url} alt="" className="w-full max-h-[520px] object-cover" />}
          {m.media_type === "video" && <video src={m.media_url} controls className="w-full max-h-[520px]" />}
          {m.media_type === "voice" && <div className="p-4"><audio src={m.media_url} controls className="w-full" /></div>}
        </div>
      )}
      <div className="flex items-center gap-4 p-4">
        <button onClick={toggleLike} data-testid={`moment-like-${m.moment_id}`}
                className={`inline-flex items-center gap-1.5 text-sm font-bold ${liked ? "text-rose-400" : "text-slate-400"}`}>
          <Heart size={17} className={liked ? "fill-rose-500" : ""} /> {likes}
        </button>
        <button onClick={openComments} data-testid={`moment-comment-${m.moment_id}`}
                className="inline-flex items-center gap-1.5 text-sm font-bold text-slate-400">
          <MessageCircle size={17} /> {m.comment_count}
        </button>
      </div>
      {showC && (
        <div className="px-4 pb-4 space-y-2" data-testid={`moment-comments-${m.moment_id}`}>
          {(comments || []).map((c) => (
            <div key={c.id} className="flex items-start gap-2">
              <Avatar name={c.author?.name} url={c.author?.avatar_url} size={26} />
              <div className="bg-white/[0.05] rounded-2xl px-3 py-2 flex-1">
                <span className="text-[11px] font-bold text-slate-300">{c.author?.name}</span>
                <p className="text-sm">{c.text}</p>
              </div>
            </div>
          ))}
          <div className="flex items-center gap-2 pt-1">
            <input value={ctext} onChange={(e) => setCtext(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addComment()}
                   placeholder="Add a comment…" data-testid={`moment-comment-input-${m.moment_id}`}
                   className="flex-1 rounded-full bg-white/[0.05] border border-white/10 px-4 h-10 text-sm outline-none" />
            <button onClick={addComment} className="w-10 h-10 grid place-items-center rounded-full text-white" style={grad}><Send size={15} /></button>
          </div>
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════ Local Pulse ═══════════════════════════
export function PulseTab() {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/pulse").then(({ data }) => setData(data)).catch(() => setData({})); }, []);
  if (!data) return <div className="flex justify-center py-16"><Loader2 className="animate-spin text-purple-400" /></div>;
  const empty = !(data.moments?.length || data.outings?.length || data.play_sessions?.length);
  return (
    <div className="space-y-6" data-testid="social-pulse">
      <div className="flex items-center gap-2 text-sm text-slate-300">
        <MapPin size={16} className="text-cyan-300" />
        <span className="font-bold">{data.city ? `What’s happening in ${data.city}` : "What’s happening near you"}</span>
      </div>
      {empty && <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-8 text-center text-slate-400">It’s quiet right now — be the first to post a public Moment or plan. 🌆</div>}
      {data.outings?.length > 0 && (
        <div>
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Plans near you</div>
          <div className="space-y-2">{data.outings.map((o) => <PulseOuting key={o.outing_id} o={o} />)}</div>
        </div>
      )}
      {data.play_sessions?.length > 0 && (
        <div>
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Playing now</div>
          <div className="space-y-2">{data.play_sessions.map((p) => <PulsePlay key={p.session_id} p={p} />)}</div>
        </div>
      )}
      {data.moments?.length > 0 && (
        <div>
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wide mb-2">Public moments</div>
          <div className="grid sm:grid-cols-2 gap-3">
            {data.moments.map((m) => (
              <div key={m.moment_id} className="rounded-2xl bg-white/[0.04] border border-white/10 p-3">
                <div className="flex items-center gap-2"><Avatar name={m.author?.name} url={m.author?.avatar_url} size={30} />
                  <span className="text-sm font-bold truncate">{m.author?.name}</span>
                  <span className="text-[11px] text-slate-500 ml-auto">{timeAgo(m.created_at)}</span></div>
                {m.context?.label && <div className="mt-2 text-xs text-purple-200">{m.context.label}</div>}
                {m.caption && <p className="text-sm text-slate-300 mt-1 line-clamp-2">{m.caption}</p>}
                {m.media_url && m.media_type === "photo" && <img src={m.media_url} alt="" className="mt-2 rounded-xl w-full h-32 object-cover" />}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function PulseOuting({ o }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3 flex items-center gap-3" data-testid={`pulse-outing-${o.outing_id}`}>
      <span className="grid place-items-center w-11 h-11 rounded-xl bg-cyan-500/15 text-cyan-300"><MapPin size={18} /></span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-black truncate">{o.title}</div>
        <div className="text-[11px] text-slate-400">{[o.place, o.when_text].filter(Boolean).join(" · ")} · {o.going_count} going</div>
      </div>
    </div>
  );
}
function PulsePlay({ p }) {
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3 flex items-center gap-3" data-testid={`pulse-play-${p.session_id}`}>
      <span className="grid place-items-center w-11 h-11 rounded-xl bg-pink-500/15 text-pink-300"><Gamepad2 size={18} /></span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-black truncate">{p.title}</div>
        <div className="text-[11px] text-slate-400">{p.game_label} · {p.player_count} playing · {p.host?.name}</div>
      </div>
    </div>
  );
}

// ═══════════════════════════ Go Together ═══════════════════════════
const ACTIVITIES = [["food", "Food"], ["coffee", "Coffee"], ["cinema", "Cinema"], ["sports", "Sports"], ["music", "Live music"], ["hangout", "Hangout"]];

export function GoTogetherModal({ onClose }) {
  const [outings, setOutings] = useState([]);
  const [friends, setFriends] = useState([]);
  const [title, setTitle] = useState("");
  const [activity, setActivity] = useState("hangout");
  const [place, setPlace] = useState("");
  const [when, setWhen] = useState("");
  const [invitees, setInvitees] = useState([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/outings"); setOutings(data.items || []); } catch (_) {}
    try { const { data } = await api.get("/friends"); setFriends(data.friends || []); } catch (_) {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    if (title.trim().length < 2) { toast.info("Give your plan a title."); return; }
    setSaving(true);
    try {
      await api.post("/outings", { title, activity, place, when_text: when, invitees, visibility: "friends" });
      toast.success("Plan created — friends invited 🎉");
      setTitle(""); setPlace(""); setWhen(""); setInvitees([]); load();
    } catch (_) { toast.error("Couldn’t create the plan."); } finally { setSaving(false); }
  };

  return (
    <ModalShell title="Go Together" onClose={onClose} testid="go-together-modal">
      <div className="space-y-3">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="What’s the plan? e.g. Friday chai & cricket"
               data-testid="outing-title" className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <div className="flex gap-1.5 flex-wrap">
          {ACTIVITIES.map(([k, l]) => (
            <button key={k} onClick={() => setActivity(k)} data-testid={`outing-act-${k}`}
                    className={`px-3 h-8 rounded-full text-xs font-bold ${activity === k ? "text-white" : "bg-white/[0.05] text-slate-400"}`}
                    style={activity === k ? grad : undefined}>{l}</button>
          ))}
        </div>
        <input value={place} onChange={(e) => setPlace(e.target.value)} placeholder="Where? (place / area)" data-testid="outing-place"
               className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <input value={when} onChange={(e) => setWhen(e.target.value)} placeholder="When? e.g. Fri 8pm" data-testid="outing-when"
               className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        {friends.length > 0 && (
          <div>
            <div className="text-[11px] text-slate-400 mb-1.5">Invite friends</div>
            <div className="flex gap-2 flex-wrap">
              {friends.map((f) => {
                const on = invitees.includes(f.user_id);
                return <button key={f.user_id} onClick={() => setInvitees((s) => on ? s.filter((x) => x !== f.user_id) : [...s, f.user_id])}
                               data-testid={`outing-invite-${f.user_id}`}
                               className={`px-3 h-8 rounded-full text-xs font-bold ${on ? "text-white" : "bg-white/[0.05] text-slate-400"}`} style={on ? grad : undefined}>{f.name}</button>;
              })}
            </div>
          </div>
        )}
        <button onClick={create} disabled={saving} data-testid="outing-create"
                className="w-full h-11 rounded-full text-white font-black inline-flex items-center justify-center gap-2" style={grad}>
          {saving ? <Loader2 size={16} className="animate-spin" /> : <MapPin size={16} />} Create plan
        </button>
      </div>
      {outings.length > 0 && (
        <div className="mt-5 space-y-2">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wide">Your plans</div>
          {outings.map((o) => <OutingRow key={o.outing_id} o={o} onChange={load} />)}
        </div>
      )}
    </ModalShell>
  );
}

function OutingRow({ o, onChange }) {
  const [rsvp, setRsvp] = useState(o.my_rsvp);
  const [going, setGoing] = useState(o.going_count);
  const setStatus = async (s) => {
    try { const { data } = await api.post(`/outings/${o.outing_id}/rsvp`, { status: s }); setRsvp(data.my_rsvp); setGoing(data.going_count); } catch (_) {}
  };
  return (
    <div className="rounded-2xl bg-white/[0.04] border border-white/10 p-3" data-testid={`outing-${o.outing_id}`}>
      <div className="text-sm font-black">{o.title}</div>
      <div className="text-[11px] text-slate-400">{[o.place, o.when_text].filter(Boolean).join(" · ")} · {going} going</div>
      <div className="flex gap-1.5 mt-2">
        {[["going", "Going"], ["maybe", "Maybe"], ["no", "Can’t"]].map(([k, l]) => (
          <button key={k} onClick={() => setStatus(k)} data-testid={`outing-rsvp-${o.outing_id}-${k}`}
                  className={`px-3 h-8 rounded-full text-xs font-bold ${rsvp === k ? "text-white" : "bg-white/[0.05] text-slate-400"}`} style={rsvp === k ? grad : undefined}>{l}</button>
        ))}
      </div>
    </div>
  );
}

// ═══════════════════════════ Play Together ═════════════════════════
export function PlayTogetherModal({ onClose }) {
  const navigate = useNavigate();
  const [games, setGames] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [game, setGame] = useState("trivia");
  const [title, setTitle] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/play/games"); setGames(data.games || []); } catch (_) {}
    try { const { data } = await api.get("/play/sessions"); setSessions(data.items || []); } catch (_) {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setSaving(true);
    try { await api.post("/play/sessions", { game_key: game, title }); toast.success("Session started — invite your friends! 🎮"); setTitle(""); load(); }
    catch (_) { toast.error("Couldn’t start the session."); } finally { setSaving(false); }
  };
  const join = async (sid) => { try { await api.post(`/play/sessions/${sid}/join`); toast.success("Joined!"); load(); } catch (_) {} };

  return (
    <ModalShell title="Play Together" onClose={onClose} testid="play-together-modal">
      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-2">
          {games.map((g) => (
            <button key={g.key} onClick={() => setGame(g.key)} data-testid={`play-game-${g.key}`}
                    className={`rounded-2xl p-3 border text-left ${game === g.key ? "border-purple-400 bg-purple-500/15" : "border-white/10 bg-white/[0.04]"}`}>
              <Gamepad2 size={18} className="text-purple-300 mb-1" />
              <div className="text-sm font-bold">{g.label}</div>
            </button>
          ))}
        </div>
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Session title (optional)" data-testid="play-title"
               className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
        <button onClick={create} disabled={saving} data-testid="play-create"
                className="w-full h-11 rounded-full text-white font-black inline-flex items-center justify-center gap-2" style={grad}>
          {saving ? <Loader2 size={16} className="animate-spin" /> : <Gamepad2 size={16} />} Start session
        </button>
      </div>
      {sessions.length > 0 && (
        <div className="mt-5 space-y-2">
          <div className="text-xs font-bold text-slate-400 uppercase tracking-wide">Open sessions</div>
          {sessions.map((p) => (
            <div key={p.session_id} className="rounded-2xl bg-white/[0.04] border border-white/10 p-3 flex items-center gap-3" data-testid={`play-session-${p.session_id}`}>
              <span className="grid place-items-center w-10 h-10 rounded-xl bg-pink-500/15 text-pink-300"><Gamepad2 size={18} /></span>
              <div className="min-w-0 flex-1"><div className="text-sm font-black truncate">{p.title}</div>
                <div className="text-[11px] text-slate-400">{p.game_label} · {p.player_count} playing</div></div>
              {p.joined ? <span className="text-[11px] text-green-300 font-bold">Joined</span>
                : <button onClick={() => join(p.session_id)} data-testid={`play-join-${p.session_id}`} className="px-4 h-9 rounded-full text-white text-xs font-black" style={grad}>Join</button>}
            </div>
          ))}
        </div>
      )}
    </ModalShell>
  );
}

// ═══════════════════════ Shop Together (group cart) ════════════════
export function ShopTogetherModal({ onClose }) {
  const [carts, setCarts] = useState([]);
  const [friends, setFriends] = useState([]);
  const [active, setActive] = useState(null);
  const [name, setName] = useState("");
  const [members, setMembers] = useState([]);
  const [itTitle, setItTitle] = useState("");
  const [itPrice, setItPrice] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/carts"); setCarts(data.items || []); if (active) setActive(data.items.find((c) => c.cart_id === active.cart_id) || null); } catch (_) {}
    try { const { data } = await axios.get(`${B}/api/social/friends`, { withCredentials: true }); setFriends(data.friends || []); } catch (_) {}
  }, [active]);
  useEffect(() => { load(); /* eslint-disable-next-line */ }, []);

  const create = async () => {
    setBusy(true);
    try { const { data } = await api.post("/carts", { name: name || "Group cart", members }); setActive(data); setName(""); setMembers([]); load(); }
    catch (_) { toast.error("Couldn’t create the cart."); } finally { setBusy(false); }
  };
  const addItem = async () => {
    if (!itTitle.trim()) return;
    try { const { data } = await api.post(`/carts/${active.cart_id}/items`, { title: itTitle.trim(), price_cents: Math.round(parseFloat(itPrice || "0") * 100), qty: 1 }); setActive(data); setItTitle(""); setItPrice(""); load(); } catch (_) {}
  };
  const removeItem = async (id) => { try { const { data } = await api.delete(`/carts/${active.cart_id}/items/${id}`); setActive(data); load(); } catch (_) {} };
  const checkout = async () => {
    try { const { data } = await api.post(`/carts/${active.cart_id}/checkout`, { origin_url: window.location.origin }); if (data.checkout_url) window.location.href = data.checkout_url; }
    catch (e) { toast.error(e?.response?.data?.detail?.code === "empty_cart" ? "Add an item first." : "Couldn’t checkout."); }
  };

  return (
    <ModalShell title="Shop Together" onClose={onClose} testid="shop-together-modal">
      {!active ? (
        <div className="space-y-3">
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Cart name (e.g. Iftar groceries)" data-testid="cart-name"
                 className="w-full rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2.5 text-sm outline-none" />
          {friends.length > 0 && (
            <div>
              <div className="text-[11px] text-slate-400 mb-1.5">Invite friends</div>
              <div className="flex flex-wrap gap-2">
                {friends.map((f) => {
                  const on = members.includes(f.user_id);
                  return <button key={f.user_id} onClick={() => setMembers((m) => on ? m.filter((x) => x !== f.user_id) : [...m, f.user_id])}
                                 data-testid={`cart-invite-${f.user_id}`} className={`px-3 h-8 rounded-full text-xs font-bold ${on ? "text-white" : "bg-white/[0.05] text-slate-400"}`} style={on ? grad : undefined}>{f.name}</button>;
                })}
              </div>
            </div>
          )}
          <button onClick={create} disabled={busy} data-testid="cart-create" className="w-full h-11 rounded-full text-white font-black inline-flex items-center justify-center gap-2" style={grad}>{busy ? <Loader2 size={16} className="animate-spin" /> : <Users size={16} />} Create cart</button>
          {carts.length > 0 && (
            <div className="pt-2 space-y-2">
              <div className="text-xs font-bold text-slate-400 uppercase tracking-wide">Your carts</div>
              {carts.map((c) => (
                <button key={c.cart_id} onClick={() => setActive(c)} data-testid={`cart-open-${c.cart_id}`} className="w-full flex items-center gap-3 rounded-2xl bg-white/[0.04] border border-white/10 px-3 py-2.5 text-left">
                  <span className="grid place-items-center w-10 h-10 rounded-xl bg-purple-500/15 text-purple-300"><Users size={16} /></span>
                  <span className="flex-1 min-w-0"><span className="block text-sm font-black truncate">{c.name}</span><span className="block text-[11px] text-slate-400">{c.item_count} items · {c.members.length} people</span></span>
                  <ChevronRight size={16} className="text-slate-500" />
                </button>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-3" data-testid="cart-detail">
          <button onClick={() => setActive(null)} className="text-xs text-slate-400 inline-flex items-center gap-1"><X size={13} /> All carts</button>
          <div className="text-lg font-black">{active.name}</div>
          <div className="flex -space-x-2">{active.members.map((m) => <span key={m.user_id} className="ring-2 ring-[#12131f] rounded-full"><Avatar name={m.name} url={m.avatar_url} size={28} /></span>)}</div>
          <div className="space-y-2">
            {active.items.length === 0 && <div className="text-sm text-slate-500">No items yet — add the first one.</div>}
            {active.items.map((it) => (
              <div key={it.item_id} className="flex items-center gap-2 rounded-2xl bg-white/[0.04] border border-white/10 px-3 py-2" data-testid={`cart-item-${it.item_id}`}>
                <div className="flex-1 min-w-0"><div className="text-sm font-bold truncate">{it.title}</div><div className="text-[11px] text-slate-400">added by {it.added_by_name}</div></div>
                <div className="text-sm font-black">${((it.price_cents || 0) / 100).toFixed(2)}</div>
                <button onClick={() => removeItem(it.item_id)} className="text-slate-500 hover:text-red-400"><Trash2 size={14} /></button>
              </div>
            ))}
          </div>
          <div className="flex items-center gap-2">
            <input value={itTitle} onChange={(e) => setItTitle(e.target.value)} placeholder="Item" data-testid="cart-item-title" className="flex-1 rounded-xl bg-white/[0.05] border border-white/10 px-3 h-10 text-sm outline-none" />
            <input value={itPrice} onChange={(e) => setItPrice(e.target.value)} placeholder="$" type="number" data-testid="cart-item-price" className="w-20 rounded-xl bg-white/[0.05] border border-white/10 px-3 h-10 text-sm outline-none" />
            <button onClick={addItem} data-testid="cart-item-add" className="w-10 h-10 grid place-items-center rounded-full text-white" style={grad}><Send size={15} /></button>
          </div>
          <div className="flex items-center justify-between pt-1">
            <div className="text-sm font-black">Total ${((active.total_cents || 0) / 100).toFixed(2)}</div>
            <button onClick={checkout} data-testid="cart-checkout" className="px-5 h-11 rounded-full text-white font-black inline-flex items-center gap-2" style={grad}>Checkout</button>
          </div>
        </div>
      )}
    </ModalShell>
  );
}

// ═══════════════════════════ AI Discovery ══════════════════════════
export function DiscoverSection() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/discover").then(({ data }) => setData(data)).catch(() => {}); }, []);
  const follow = async (uid) => {
    try { await axios.post(`${B}/api/social/friends/request`, { user_id: uid }, { withCredentials: true }); toast.success("Friend request sent"); setData((d) => ({ ...d, people: d.people.filter((p) => p.user_id !== uid) })); }
    catch (_) { toast.error("Couldn’t send request."); }
  };
  if (!data || (!data.people?.length && !data.shows?.length)) return null;
  return (
    <div className="mb-5" data-testid="discover-section">
      <div className="flex items-center gap-2 mb-2"><Sparkles size={15} className="text-purple-300" /><span className="text-sm font-black">Discover</span></div>
      {data.headline && <p className="text-[12px] text-slate-400 mb-3">{data.headline}</p>}
      {data.people?.length > 0 && (
        <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1">
          {data.people.map((p) => (
            <div key={p.user_id} className="flex-shrink-0 w-40 rounded-2xl bg-white/[0.04] border border-white/10 p-3 text-center" data-testid={`discover-person-${p.user_id}`}>
              <div className="flex justify-center"><Avatar name={p.name} url={p.avatar_url} size={48} /></div>
              <div className="text-sm font-black truncate mt-2">{p.name}</div>
              <div className="text-[10px] text-slate-400 truncate">{p.reason}</div>
              <button onClick={() => follow(p.user_id)} data-testid={`discover-follow-${p.user_id}`} className="mt-2 w-full h-8 rounded-full text-white text-[11px] font-black" style={grad}>Add friend</button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ModalShell({ title, onClose, children, testid }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-black/70 p-0 sm:p-5" onClick={onClose} data-testid={testid}>
      <div onClick={(e) => e.stopPropagation()}
           className="w-full sm:max-w-lg max-h-[90vh] overflow-y-auto rounded-t-3xl sm:rounded-3xl border border-white/10 p-5"
           style={{ background: "linear-gradient(180deg,#12131f,#0b0c16)" }}>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-black text-white">{title}</h3>
          <button onClick={onClose} className="w-9 h-9 grid place-items-center rounded-full bg-white/[0.06]"><X size={18} /></button>
        </div>
        {children}
      </div>
    </div>
  );
}
