// FUUSIC Social V2 — web shell.
// Social HOME wall (what people & things you follow are doing) + Live · Moments ·
// Nearby · Friends · Dreams · Tarot. Design-independent; premium New Look V2.
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Radio, Users, Gamepad2, MapPin, ShoppingBag, Sparkles, Loader2,
  UserPlus, Check, X, Search, Headphones, Video, Camera,
  Play, Moon, UserCheck,
} from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { PulseTab, GoTogetherModal, PlayTogetherModal, ShopTogetherModal, DiscoverSection } from "./SocialTogether";
import { MomentsTab } from "./SocialTogether";
import { LiveTab } from "./SocialLive";
import SocialWall from "./SocialWall";
import { FollowingPanel } from "./FollowingPanel";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api/social`,
  withCredentials: true,
});
const RADIO_API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

const TABS = [
  { key: "together", label: "Home", icon: Sparkles },
  { key: "live", label: "Live", icon: Video },
  { key: "moments", label: "Moments", icon: Camera },
  { key: "pulse", label: "Nearby", icon: MapPin },
  { key: "friends", label: "Friends", icon: Users },
  { key: "dreams", label: "Dreams", icon: Moon },
  { key: "tarot", label: "Tarot", icon: Sparkles },
];

export default function SocialV2() {
  const [params] = useSearchParams();
  const qTab = params.get("tab");
  const qAction = params.get("action");
  const qSession = params.get("session");
  const qRef = params.get("ref");
  const validTab = TABS.some((t) => t.key === qTab) ? qTab : null;
  const [tab, setTab] = useState(qAction ? "together" : (validTab || "together"));
  const navigate = useNavigate();
  const [home, setHome] = useState(null);
  const [loading, setLoading] = useState(true);
  const [followingOpen, setFollowingOpen] = useState(false);

  const loadHome = useCallback(async () => {
    try {
      const { data } = await api.get("/home");
      setHome(data);
    } catch (_) { /* soft */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadHome(); }, [loadHome]);

  const onSelectTab = (k) => {
    if (k === "dreams") navigate("/social/dreams");
    else if (k === "tarot") navigate("/social/tarot");
    else setTab(k);
  };

  return (
    <div className="min-h-screen fz-social-page fz-text"
              style={{ background: "var(--app-bg)" }}
              data-testid="social-v2">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 pt-8 pb-32">
        <Header home={home} onOpenFollowing={() => setFollowingOpen(true)} />
        <TabBar tab={tab} counts={home?.counts} onSelect={onSelectTab} />
        <div className="mt-6">
          {loading && (
            <div className="flex justify-center py-20" data-testid="social-loading">
              <Loader2 className="animate-spin text-purple-400" />
            </div>
          )}
          {!loading && tab === "together" && (
            <HomeTab initialAction={qAction} playSession={qSession} playRef={qRef}
                     onOpenFollowing={() => setFollowingOpen(true)} />
          )}
          {!loading && tab === "friends" && <FriendsTab />}
          {!loading && tab === "live" && <LiveTab />}
          {!loading && tab === "moments" && <MomentsTab />}
          {!loading && tab === "pulse" && <PulseTab />}
        </div>
      </div>
      {followingOpen && <FollowingPanel onClose={() => setFollowingOpen(false)} />}
    </div>
  );
}

function Header({ home, onOpenFollowing }) {
  const h = home?.happening_now || {};
  const stats = [
    { icon: Radio, n: h.live_experiences || 0, label: "Live now", tone: "#f472b6" },
    { icon: Headphones, n: h.friends_listening || 0, label: "Friends listening", tone: "#22d3ee" },
    { icon: Users, n: home?.counts?.friends || 0, label: "Friends", tone: "#a855f7" },
    { icon: UserCheck, n: home?.counts?.following || 0, label: "Following", tone: "#38bdf8",
      onClick: onOpenFollowing, tid: "social-stat-following" },
  ];
  return (
    <div>
      <div className="flex items-end justify-between gap-3">
        <div>
          <h1 className="text-4xl sm:text-5xl font-black tracking-tight">Social</h1>
          <p className="text-slate-400 mt-1 text-sm font-semibold uppercase tracking-widest">
            Do things together
          </p>
        </div>
      </div>
      <div className="mt-5 flex gap-3 flex-wrap" data-testid="social-happening-now">
        {stats.map((s) => {
          const Tag = s.onClick ? "button" : "div";
          return (
            <Tag key={s.label} type={s.onClick ? "button" : undefined} onClick={s.onClick}
                 data-testid={s.tid}
                 className={`flex items-center gap-2.5 rounded-2xl px-4 py-2.5 bg-white/[0.04] border border-white/10 backdrop-blur ${s.onClick ? "hover:bg-white/[0.08] transition cursor-pointer" : ""}`}>
              <span className="grid place-items-center w-9 h-9 rounded-xl"
                        style={{ background: `${s.tone}22`, color: s.tone }}>
                <s.icon size={16} />
              </span>
              <div className="leading-none text-left">
                <div className="text-lg font-black tabular-nums">{s.n}</div>
                <div className="text-[10px] text-slate-400 uppercase tracking-wider">{s.label}</div>
              </div>
            </Tag>
          );
        })}
      </div>
    </div>
  );
}

function TabBar({ tab, counts, onSelect }) {
  return (
    <div className="mt-7 flex gap-1.5 overflow-x-auto no-scrollbar" data-testid="social-tabs">
      {TABS.map((t) => {
        const active = tab === t.key;
        const badge = t.key === "friends" ? (counts?.friend_requests || 0) : 0;
        return (
          <button key={t.key} type="button" onClick={() => onSelect(t.key)}
                        data-testid={`social-tab-${t.key}`}
                        className={`relative flex-shrink-0 inline-flex items-center gap-2 px-4 h-11 rounded-full text-sm font-bold transition
                          ${active ? "text-white" : "text-slate-400 hover:text-slate-200 bg-white/[0.03]"}`}
                        style={active ? { background: "linear-gradient(135deg,#a855f7,#ec4899)" } : undefined}>
            <t.icon size={16} /> {t.label}
            {badge > 0 && (
              <span className="ml-0.5 min-w-[18px] h-[18px] px-1 grid place-items-center rounded-full bg-cyan-400 text-slate-950 text-[10px] font-black">
                {badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ───────────────────────── Home (combined wall) ────────────────────
function HomeTab({ initialAction, playSession, playRef, onOpenFollowing }) {
  const navigate = useNavigate();
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  const [starting, setStarting] = useState(false);
  const [pickOpen, setPickOpen] = useState(false);
  const [goOpen, setGoOpen] = useState(false);
  const [playOpen, setPlayOpen] = useState(false);
  const [shopOpen, setShopOpen] = useState(false);
  const didAction = useRef(false);

  const nowPlaying = importedStation
    ? { type: "live", name: importedStation.name, art: importedStation.favicon }
    : podcastEpisode
      ? { type: "podcast", name: podcastEpisode.title, art: podcastEpisode.cover_image_url }
      : null;

  const createRoomForStation = async (station) => {
    setStarting(true);
    try {
      const content = { id: station.id, name: station.name, favicon: station.favicon,
        stream_url: station.stream_url, country: station.country, language: station.language, source: "imported" };
      const { data } = await api.post("/rooms", { visibility: "public", content_type: "live", content });
      navigate(`/social/room/${data.room_id}`);
    } catch (_) { toast.error("Couldn't start the room. Please try again."); }
    finally { setStarting(false); }
  };

  const pickAndStart = async (s) => {
    try {
      const r = await axios.post(`${RADIO_API}/radio/play/${s.id}`, {}, { withCredentials: true });
      const station = { id: s.id, name: r.data?.name || s.name, stream_url: r.data?.stream_url,
        favicon: r.data?.favicon || s.favicon, country: r.data?.country, language: r.data?.language };
      setImportedStation({ ...station, source: "imported" });
      setPickOpen(false);
      await createRoomForStation(station);
    } catch (_) { toast.error("Couldn't play that station."); }
  };

  const startRoom = async () => {
    if (!nowPlaying) { setPickOpen(true); return; }
    setStarting(true);
    try {
      const content = importedStation
        ? { ...importedStation }
        : { id: podcastEpisode.episode_id, name: podcastEpisode.title,
                favicon: podcastEpisode.cover_image_url, podcast_id: podcastEpisode.podcast_id };
      const { data } = await api.post("/rooms", {
        visibility: "public",
        content_type: nowPlaying.type,
        content,
        playback: nowPlaying.type === "podcast" ? { position_sec: 0, is_playing: true } : undefined,
      });
      navigate(`/social/room/${data.room_id}`);
    } catch (_) {
      toast.error("Couldn't start the room. Please try again.");
    } finally { setStarting(false); }
  };

  const actions = [
    { key: "listen", label: "Listen Together", blurb: "Tune in with friends",
      icon: Headphones, grad: "linear-gradient(135deg,#a855f7,#ec4899)", on: startRoom },
    { key: "dreams", label: "Dreams", blurb: "Share or explore dreams",
      icon: Moon, grad: "linear-gradient(135deg,#7c3aed,#c026d3)", on: () => navigate("/social/dreams") },
    { key: "tarot", label: "Tarot", blurb: "Draw a card", emoji: "🃏",
      grad: "linear-gradient(135deg,#6d28d9,#db2777)", on: () => navigate("/social/tarot") },
    { key: "play", label: "Play Together", blurb: "Games with friends",
      icon: Gamepad2, grad: "linear-gradient(135deg,#2563eb,#7c3aed)", on: () => setPlayOpen(true) },
    { key: "go", label: "Go Together", blurb: "Plan an outing",
      icon: MapPin, grad: "linear-gradient(135deg,#0891b2,#2563eb)", on: () => setGoOpen(true) },
    { key: "shop", label: "Shop Together", blurb: "Share a cart",
      icon: ShoppingBag, grad: "linear-gradient(135deg,#db2777,#f59e0b)", on: () => setShopOpen(true) },
  ];

  useEffect(() => {
    if (didAction.current || !initialAction) return;
    didAction.current = true;
    if (initialAction === "play") setPlayOpen(true);
    else if (initialAction === "shop") setShopOpen(true);
    else if (initialAction === "go") setGoOpen(true);
    else if (initialAction === "listen") startRoom();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialAction]);

  return (
    <div data-testid="social-home">
      <SocialWall actions={actions} onOpenFollowing={onOpenFollowing} />
      {pickOpen && <StationPickModal onClose={() => setPickOpen(false)} onPick={pickAndStart} />}
      {goOpen && <GoTogetherModal onClose={() => setGoOpen(false)} />}
      {playOpen && <PlayTogetherModal onClose={() => setPlayOpen(false)} sessionId={playSession} refId={playRef} />}
      {shopOpen && <ShopTogetherModal onClose={() => setShopOpen(false)} />}
      {starting && (
        <div className="fixed bottom-24 left-1/2 -translate-x-1/2 z-50 rounded-full px-4 py-2 bg-black/80 border border-white/10 text-sm flex items-center gap-2">
          <Loader2 className="animate-spin" size={15} /> Starting room…
        </div>
      )}
    </div>
  );
}

// ───────────────────────── Listen Together station picker ──────────
function StationPickModal({ onClose, onPick }) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState(null);
  useEffect(() => {
    let alive = true; setLoading(true);
    const t = setTimeout(async () => {
      try {
        const r = await axios.get(`${RADIO_API}/radio/browse`, { params: { q: q || undefined, source: "all", limit: 24 }, withCredentials: true });
        if (alive) setItems(r.data?.items || []);
      } catch (_) {} finally { if (alive) setLoading(false); }
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [q]);
  const pick = async (s) => { setBusyId(s.id); await onPick(s); setBusyId(null); };
  return (
    <div className="fixed inset-0 z-[60] flex items-end sm:items-center justify-center bg-black/70 backdrop-blur-sm" onClick={onClose} data-testid="listen-station-pick">
      <div className="w-full sm:max-w-lg max-h-[85vh] overflow-hidden flex flex-col rounded-t-3xl sm:rounded-3xl border border-white/10" style={{ background: "linear-gradient(180deg,#12102b,#0b0918)" }} onClick={(e) => e.stopPropagation()}>
        <div className="p-5 pb-3">
          <div className="flex items-center gap-2 mb-1"><Headphones size={18} className="text-purple-300" /><h3 className="text-lg font-black">Pick a station to listen together</h3></div>
          <p className="text-xs text-slate-400 mb-3">Choose a station — we'll start playing it and open a room you can share with friends.</p>
          <div className="flex items-center gap-2 rounded-full bg-white/[0.05] border border-white/10 px-3">
            <Search size={15} className="text-slate-400" />
            <input value={q} onChange={(e) => setQ(e.target.value)} data-testid="listen-station-search" placeholder="Search stations…" className="flex-1 bg-transparent py-2.5 text-sm outline-none" />
          </div>
        </div>
        <div className="px-3 pb-4 overflow-y-auto no-scrollbar" data-testid="listen-station-list">
          {loading ? <div className="flex justify-center py-10"><Loader2 className="animate-spin text-purple-400" /></div>
            : items.length === 0 ? <div className="text-center text-sm text-slate-400 py-10">No stations found.</div>
            : items.map((s) => (
              <button key={s.id} type="button" onClick={() => pick(s)} disabled={!!busyId} data-testid={`listen-station-${s.id}`}
                      className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 hover:bg-white/[0.06] text-left disabled:opacity-60">
                <span className="grid place-items-center w-11 h-11 rounded-xl overflow-hidden bg-purple-500/20 text-purple-200 shrink-0">
                  {s.favicon ? <img src={s.favicon} alt="" className="w-full h-full object-cover" /> : <Radio size={18} />}
                </span>
                <span className="min-w-0 flex-1"><span className="block text-sm font-bold truncate">{s.name}</span>
                  <span className="block text-[11px] text-slate-400 truncate">{[s.country, s.language].filter(Boolean).join(" · ") || s.source}</span></span>
                {busyId === s.id ? <Loader2 size={16} className="animate-spin text-purple-300" /> : <Play size={16} className="text-white/70" />}
              </button>
            ))}
        </div>
      </div>
    </div>
  );
}

// ───────────────────────── Friends ─────────────────────────────────
function FriendsTab() {
  const [q, setQ] = useState("");
  const [results, setResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [data, setData] = useState(null);
  const tRef = useRef(null);

  const load = useCallback(async () => {
    try { const r = await api.get("/friends"); setData(r.data); } catch (_) {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const runSearch = (val) => {
    setQ(val);
    if (tRef.current) clearTimeout(tRef.current);
    if (val.trim().length < 2) { setResults([]); return; }
    setSearching(true);
    tRef.current = setTimeout(async () => {
      try { const r = await api.get(`/users/search?q=${encodeURIComponent(val.trim())}`); setResults(r.data.items || []); }
      catch (_) {} finally { setSearching(false); }
    }, 350);
  };

  const act = async (fn, ok) => { try { await fn(); toast.success(ok); await load(); if (q) runSearch(q); } catch (e) { toast.error(e?.response?.data?.detail || "Action failed"); } };

  return (
    <div className="space-y-7" data-testid="social-friends">
      <DiscoverSection />
      <div className="relative">
        <Search size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
        <input value={q} onChange={(e) => runSearch(e.target.value)}
                    data-testid="social-friend-search"
                    placeholder="Find people by name or email"
                    className="w-full rounded-2xl bg-white/[0.05] border border-white/10 pl-11 pr-4 py-3 text-sm outline-none focus:border-purple-400/60" />
        {searching && <Loader2 size={15} className="absolute right-4 top-1/2 -translate-y-1/2 animate-spin text-slate-400" />}
      </div>

      {results.length > 0 && (
        <div className="space-y-2" data-testid="social-search-results">
          <SectionTitle>Search results</SectionTitle>
          {results.map((u) => (
            <PersonRow key={u.user_id} u={u}
              right={u.relationship === "friend" ? <Tag>Friend</Tag>
                : u.relationship === "pending" ? <Tag>Requested</Tag>
                : <IconBtn tid={`social-add-${u.user_id}`} icon={UserPlus} label="Add"
                          onClick={() => act(() => api.post("/friends/request", { user_id: u.user_id }), "Request sent")} />} />
          ))}
        </div>
      )}

      {(data?.incoming?.length > 0) && (
        <div className="space-y-2" data-testid="social-incoming">
          <SectionTitle>Friend requests</SectionTitle>
          {data.incoming.map((u) => (
            <PersonRow key={u.user_id} u={u} right={
              <div className="flex gap-2">
                <IconBtn tid={`social-accept-${u.user_id}`} icon={Check} label="Accept" tone="cyan"
                              onClick={() => act(() => api.post(`/friends/${u.user_id}/accept`), "You're now friends")} />
                <IconBtn tid={`social-decline-${u.user_id}`} icon={X}
                              onClick={() => act(() => api.post(`/friends/${u.user_id}/decline`), "Declined")} />
              </div>} />
          ))}
        </div>
      )}

      <div className="space-y-2">
        <SectionTitle>Your friends {data?.counts?.friends ? `(${data.counts.friends})` : ""}</SectionTitle>
        {(!data?.friends || data.friends.length === 0) ? (
          <EmptyCard>No friends yet — search above to connect and listen together.</EmptyCard>
        ) : data.friends.map((u) => (
          <PersonRow key={u.user_id} u={u} right={
            <IconBtn tid={`social-remove-${u.user_id}`} icon={X}
                          onClick={() => act(() => api.delete(`/friends/${u.user_id}`), "Removed")} />} />
        ))}
      </div>
    </div>
  );
}

function PersonRow({ u, right }) {
  return (
    <div className="flex items-center gap-3 rounded-2xl p-3 bg-white/[0.04] border border-white/10">
      <Avatar name={u.name} url={u.avatar_url} size={40} />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-bold truncate">{u.name}</div>
        {u.city && <div className="text-[11px] text-slate-400">{u.city}</div>}
      </div>
      {right}
    </div>
  );
}

// ───────────────────────── Shared bits ─────────────────────────────
function SectionTitle({ children }) {
  return <div className="text-xs font-black uppercase tracking-[0.18em] text-slate-400 mb-3">{children}</div>;
}
function EmptyCard({ children }) {
  return <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-6 text-center text-sm text-slate-400">{children}</div>;
}
function Tag({ children }) {
  return <span className="text-[11px] font-bold px-3 py-1.5 rounded-full bg-white/10 text-slate-300">{children}</span>;
}
function IconBtn({ icon: Icon, label, onClick, tone, tid }) {
  return (
    <button type="button" onClick={onClick} data-testid={tid}
                  className="inline-flex items-center gap-1.5 h-9 px-3 rounded-full text-xs font-bold text-white"
                  style={{ background: tone === "cyan" ? "linear-gradient(135deg,#06b6d4,#3b82f6)" : "rgba(255,255,255,0.1)" }}>
      <Icon size={14} /> {label}
    </button>
  );
}
export function Avatar({ name, url, size = 40 }) {
  const initials = (name || "?").split(" ").map((s) => s[0]).slice(0, 2).join("").toUpperCase();
  return url ? (
    <img src={url} alt={name} width={size} height={size}
              className="rounded-full object-cover shrink-0" style={{ width: size, height: size }} />
  ) : (
    <span className="rounded-full grid place-items-center shrink-0 font-black text-white"
              style={{ width: size, height: size, fontSize: size * 0.36,
                            background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
      {initials}
    </span>
  );
}
