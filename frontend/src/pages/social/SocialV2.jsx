// RadioLife Social V2 — Phase 1 web shell.
// "Do things together": Together (default) · Live · Moments · Clubs · Friends.
// Design-independent functionality; premium New Look V2 presentation.
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Radio, Users, Gamepad2, MapPin, ShoppingBag, Sparkles, Loader2,
  UserPlus, Check, X, Search, Headphones, Video, Camera, Users2,
  Play, Dot, ChevronRight, Clock, Moon,
} from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { MomentsTab, PulseTab, GoTogetherModal, PlayTogetherModal, ShopTogetherModal, DiscoverSection } from "./SocialTogether";
import { LiveTab } from "./SocialLive";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api/social`,
  withCredentials: true,
});

const TABS = [
  { key: "together", label: "Together", icon: Sparkles },
  { key: "live", label: "Live", icon: Video },
  { key: "moments", label: "Moments", icon: Camera },
  { key: "pulse", label: "Pulse", icon: MapPin },
  { key: "friends", label: "Friends", icon: Users },
];

export default function SocialV2() {
  const [tab, setTab] = useState("together");
  const [home, setHome] = useState(null);
  const [loading, setLoading] = useState(true);

  const loadHome = useCallback(async () => {
    try {
      const { data } = await api.get("/home");
      setHome(data);
    } catch (_) { /* soft */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadHome(); }, [loadHome]);

  return (
    <div className="min-h-screen text-white"
              style={{ background: "linear-gradient(180deg,#080a16 0%,#0b0f1e 40%,#0a0a14 100%)" }}
              data-testid="social-v2">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 pt-8 pb-32">
        <Header home={home} />
        <TabBar tab={tab} setTab={setTab} counts={home?.counts} />
        <div className="mt-6">
          {loading && (
            <div className="flex justify-center py-20" data-testid="social-loading">
              <Loader2 className="animate-spin text-purple-400" />
            </div>
          )}
          {!loading && tab === "together" && (
            <TogetherTab home={home} reload={loadHome} />
          )}
          {!loading && tab === "friends" && <FriendsTab />}
          {!loading && tab === "live" && <LiveTab />}
          {!loading && tab === "moments" && <MomentsTab />}
          {!loading && tab === "pulse" && <PulseTab />}
        </div>
      </div>
    </div>
  );
}

function Header({ home }) {
  const h = home?.happening_now || {};
  const stats = [
    { icon: Radio, n: h.live_experiences || 0, label: "Live now", tone: "#f472b6" },
    { icon: Headphones, n: h.friends_listening || 0, label: "Friends listening", tone: "#22d3ee" },
    { icon: Users, n: home?.counts?.friends || 0, label: "Friends", tone: "#a855f7" },
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
        {stats.map((s) => (
          <div key={s.label}
                    className="flex items-center gap-2.5 rounded-2xl px-4 py-2.5 bg-white/[0.04] border border-white/10 backdrop-blur">
            <span className="grid place-items-center w-9 h-9 rounded-xl"
                      style={{ background: `${s.tone}22`, color: s.tone }}>
              <s.icon size={16} />
            </span>
            <div className="leading-none">
              <div className="text-lg font-black tabular-nums">{s.n}</div>
              <div className="text-[10px] text-slate-400 uppercase tracking-wider">{s.label}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TabBar({ tab, setTab, counts }) {
  return (
    <div className="mt-7 flex gap-1.5 overflow-x-auto no-scrollbar" data-testid="social-tabs">
      {TABS.map((t) => {
        const active = tab === t.key;
        const badge = t.key === "friends" ? (counts?.friend_requests || 0) : 0;
        return (
          <button key={t.key} type="button" onClick={() => setTab(t.key)}
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

// ───────────────────────── Together ────────────────────────────────
function TogetherTab({ home, reload }) {
  const navigate = useNavigate();
  const importedStation = usePlayerStore((s) => s.importedStation);
  const podcastEpisode = usePlayerStore((s) => s.podcastEpisode);
  const [starting, setStarting] = useState(false);
  const [goOpen, setGoOpen] = useState(false);
  const [playOpen, setPlayOpen] = useState(false);
  const [shopOpen, setShopOpen] = useState(false);

  const nowPlaying = importedStation
    ? { type: "live", name: importedStation.name, art: importedStation.favicon }
    : podcastEpisode
      ? { type: "podcast", name: podcastEpisode.title, art: podcastEpisode.cover_image_url }
      : null;

  const startRoom = async () => {
    if (!nowPlaying) {
      toast.info("Start playing a station or podcast first, then invite friends.");
      return;
    }
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

  const doTogether = [
    { key: "listen", label: "Listen Together", icon: Headphones, on: startRoom },
    { key: "play", label: "Play Together", icon: Gamepad2, on: () => setPlayOpen(true) },
    { key: "go", label: "Go Together", icon: MapPin, on: () => setGoOpen(true) },
    { key: "shop", label: "Shop Together", icon: ShoppingBag, on: () => setShopOpen(true) },
  ];

  const rooms = home?.suggested_rooms || [];
  const friendsNow = home?.friends_now || [];

  return (
    <div className="space-y-8" data-testid="social-together">
      {/* Start / continue a listening room */}
      <button type="button" onClick={startRoom} disabled={starting}
                    data-testid="social-start-room"
                    className="w-full text-left rounded-3xl p-5 flex items-center gap-4 border border-white/10 disabled:opacity-70"
                    style={{ background: "linear-gradient(120deg,#1a1038,#2a1148 60%,#3a0f52)" }}>
        <span className="grid place-items-center w-14 h-14 rounded-2xl text-white shrink-0"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
          {starting ? <Loader2 className="animate-spin" /> : <Headphones size={24} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-lg font-black">Listen Together</div>
          <div className="text-sm text-slate-300 truncate">
            {nowPlaying ? `Invite friends to "${nowPlaying.name}"` : "Play a station, then invite friends to tune in with you"}
          </div>
        </div>
        <ChevronRight className="text-slate-400" />
      </button>

      {/* Dreams & Guidance */}
      <button type="button" onClick={() => navigate("/social/dreams")}
                    data-testid="social-open-dreams"
                    className="w-full text-left rounded-3xl p-5 flex items-center gap-4 border border-violet-500/25"
                    style={{ background: "linear-gradient(120deg,#1e1b4b,#4c1d95 65%,#6d28d9)" }}>
        <span className="grid place-items-center w-14 h-14 rounded-2xl text-white shrink-0"
                  style={{ background: "linear-gradient(135deg,#7c3aed,#c026d3)" }}>
          <Moon size={24} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-lg font-black">Dreams & Guidance</div>
          <div className="text-sm text-violet-200/80 truncate">
            Share a dream, get an AI reflection, and connect with verified advisors
          </div>
        </div>
        <ChevronRight className="text-slate-400" />
      </button>
      <div>
        <SectionTitle>Do something together</SectionTitle>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {doTogether.map((d) => (
            <button key={d.key} type="button" onClick={d.on}
                          data-testid={`social-do-${d.key}`}
                          className="rounded-2xl p-4 bg-white/[0.04] border border-white/10 hover:bg-white/[0.07] transition flex flex-col items-center gap-2 text-center">
              <span className="grid place-items-center w-11 h-11 rounded-xl bg-purple-500/15 text-purple-300">
                <d.icon size={20} />
              </span>
              <span className="text-xs font-bold">{d.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Friends right now */}
      {friendsNow.length > 0 && (
        <div>
          <SectionTitle>Friends right now</SectionTitle>
          <div className="flex gap-3 overflow-x-auto no-scrollbar pb-1" data-testid="social-friends-now">
            {friendsNow.map((f) => (
              <button key={f.user_id} type="button" onClick={() => navigate(`/social/room/${f.room_id}`)}
                            className="flex-shrink-0 w-40 rounded-2xl p-3 bg-white/[0.04] border border-white/10 text-left hover:bg-white/[0.07]">
                <Avatar name={f.name} url={f.avatar_url} size={40} />
                <div className="mt-2 text-sm font-bold truncate">{f.name}</div>
                <div className="text-[11px] text-cyan-300 flex items-center gap-1 truncate">
                  <Dot className="animate-pulse" size={16} /> {f.context || "Listening"}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Live now — listening rooms */}
      <div>
        <SectionTitle>Live listening rooms</SectionTitle>
        {rooms.length === 0 ? (
          <EmptyCard>No rooms live right now — start one above and invite your friends. 🎧</EmptyCard>
        ) : (
          <div className="grid sm:grid-cols-2 gap-3" data-testid="social-rooms">
            {rooms.map((r) => (
              <RoomCard key={r.room_id} room={r} onJoin={() => navigate(`/social/room/${r.room_id}`)} />
            ))}
          </div>
        )}
      </div>
      {goOpen && <GoTogetherModal onClose={() => setGoOpen(false)} />}
      {playOpen && <PlayTogetherModal onClose={() => setPlayOpen(false)} />}
      {shopOpen && <ShopTogetherModal onClose={() => setShopOpen(false)} />}
    </div>
  );
}

function RoomCard({ room, onJoin }) {
  return (
    <button type="button" onClick={onJoin}
                  data-testid={`social-room-${room.room_id}`}
                  className="text-left rounded-2xl overflow-hidden bg-white/[0.04] border border-white/10 hover:bg-white/[0.07] transition">
      <div className="flex items-center gap-3 p-3">
        <span className="grid place-items-center w-14 h-14 rounded-xl shrink-0 overflow-hidden bg-purple-500/20 text-purple-200">
          {(room.content?.favicon) ? (
            <img src={room.content.favicon} alt="" className="w-full h-full object-cover" />
          ) : <Radio size={22} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 inline-flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" /> Live
            </span>
            {room.has_friend && (
              <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300">
                Friend here
              </span>
            )}
          </div>
          <div className="text-sm font-black truncate mt-1">{room.content?.name || room.title}</div>
          <div className="text-[11px] text-slate-400">
            {room.participant_count} listening · hosted by {room.host_name}
          </div>
        </div>
        <Play className="text-white/70" size={18} />
      </div>
    </button>
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
function ComingSoon({ icon: Icon, title, blurb }) {
  return (
    <div className="rounded-3xl border border-white/10 bg-white/[0.03] p-10 text-center" data-testid="social-coming-soon">
      <span className="inline-grid place-items-center w-16 h-16 rounded-2xl mb-4"
                style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
        <Icon size={28} className="text-white" />
      </span>
      <h3 className="text-2xl font-black">{title}</h3>
      <p className="text-slate-400 mt-2 max-w-sm mx-auto text-sm">{blurb}</p>
      <span className="inline-flex items-center gap-1.5 mt-4 text-[11px] font-black uppercase tracking-widest px-3 py-1.5 rounded-full bg-purple-500/20 text-purple-200">
        <Clock size={12} /> Coming soon
      </span>
    </div>
  );
}
