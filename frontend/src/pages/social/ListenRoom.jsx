// Listen Together room (web) — poll-based sync on top of the shared social
// API. Live rooms share the station context; podcast rooms timestamp-sync
// from the host. The persistent RadioLife player keeps playing.
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  ArrowLeft, Send, Users, Radio, Loader2, Share2, LogOut, Trophy,
} from "lucide-react";
import { usePlayerStore } from "@/store/usePlayerStore";
import { Avatar } from "@/pages/social/SocialV2";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL || ""}/api/social`,
  withCredentials: true,
});

const REACTIONS = ["❤️", "🔥", "😂", "👏", "🎉"];

export default function ListenRoom() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [room, setRoom] = useState(null);
  const [messages, setMessages] = useState([]);
  const [participants, setParticipants] = useState([]);
  const [challenge, setChallenge] = useState(null);
  const [floaters, setFloaters] = useState([]);
  const [text, setText] = useState("");
  const [error, setError] = useState(false);
  const sinceRef = useRef(null);
  const chatRef = useRef(null);
  const setImportedStation = usePlayerStore((s) => s.setImportedStation);
  const setImportedPlaying = usePlayerStore((s) => s.setImportedPlaying);

  // Join once, then sync the persistent player to the room's station.
  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await api.post(`/rooms/${id}/join`);
        if (!alive) return;
        setRoom(data);
        setMessages(data.messages || []);
        setParticipants(data.participants || []);
        if (data.content_type === "live" && data.content?.stream_url) {
          setImportedStation(data.content);
          setImportedPlaying(true);
        }
      } catch (_) { if (alive) setError(true); }
    })();
    return () => {
      alive = false;
      api.post(`/rooms/${id}/leave`).catch(() => {});
    };
  }, [id, setImportedStation, setImportedPlaying]);

  // Poll heartbeat for chat/reactions/presence/challenge.
  const beat = useCallback(async () => {
    try {
      const url = sinceRef.current
        ? `/rooms/${id}/heartbeat?since=${encodeURIComponent(sinceRef.current)}`
        : `/rooms/${id}/heartbeat`;
      const { data } = await api.post(url);
      sinceRef.current = data.server_time;
      setParticipants(data.participants || []);
      if (data.challenge) setChallenge(data.challenge);
      if (data.messages?.length) {
        setMessages((prev) => {
          const seen = new Set(prev.map((m) => m.id));
          return [...prev, ...data.messages.filter((m) => !seen.has(m.id))];
        });
      }
      if (data.reactions?.length) {
        const add = data.reactions.map((r, i) => ({
          key: `${r.created_at}-${i}-${Math.random()}`, emoji: r.emoji,
          left: 8 + Math.random() * 78,
        }));
        setFloaters((f) => [...f, ...add]);
        setTimeout(() => setFloaters((f) => f.slice(add.length)), 2600);
      }
      if (data.active === false) { toast.info("This room has ended."); navigate("/social"); }
    } catch (_) { /* transient */ }
  }, [id, navigate]);

  useEffect(() => {
    const t = setInterval(beat, 2500);
    beat();
    return () => clearInterval(t);
  }, [beat]);

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight;
  }, [messages]);

  const send = async () => {
    const t = text.trim();
    if (!t) return;
    setText("");
    try {
      const { data } = await api.post(`/rooms/${id}/messages`, { text: t });
      setMessages((prev) => prev.some((m) => m.id === data.id) ? prev : [...prev, data]);
    } catch (_) { toast.error("Message failed"); }
  };

  const react = async (emoji) => {
    try { await api.post(`/rooms/${id}/reactions`, { emoji }); } catch (_) {}
  };

  const invite = async () => {
    const link = `${window.location.origin}/social/room/${id}`;
    try { await navigator.clipboard.writeText(link); toast.success("Invite link copied"); }
    catch (_) { toast.info(link); }
  };

  const leave = () => { navigate("/social"); };

  if (error) {
    return (
      <div className="min-h-screen grid place-items-center text-white" style={{ background: "#0b0f1e" }}>
        <div className="text-center">
          <p className="text-slate-300">This room isn't available.</p>
          <button onClick={() => navigate("/social")} className="mt-4 px-4 py-2 rounded-full bg-white/10 text-sm font-bold">
            Back to Social
          </button>
        </div>
      </div>
    );
  }
  if (!room) {
    return <div className="min-h-screen grid place-items-center" style={{ background: "#0b0f1e" }}>
      <Loader2 className="animate-spin text-purple-400" /></div>;
  }

  return (
    <div className="min-h-screen text-white flex flex-col"
              style={{ background: "linear-gradient(180deg,#0b0f1e,#150a26 60%,#0a0a14)" }}
              data-testid="listen-room">
      {/* Header */}
      <div className="sticky top-0 z-10 backdrop-blur-xl bg-black/30 border-b border-white/10">
        <div className="max-w-3xl mx-auto px-4 py-3 flex items-center gap-3">
          <button onClick={leave} data-testid="listen-room-back" className="p-2 -ml-2 text-slate-300 hover:text-white">
            <ArrowLeft />
          </button>
          <span className="grid place-items-center w-11 h-11 rounded-xl overflow-hidden bg-purple-500/20 text-purple-200 shrink-0">
            {room.content?.favicon ? <img src={room.content.favicon} alt="" className="w-full h-full object-cover" /> : <Radio />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-full bg-red-500/20 text-red-300 inline-flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" /> Live
              </span>
              <span className="text-[11px] text-slate-400 inline-flex items-center gap-1">
                <Users size={12} /> <span data-testid="listen-room-count">{participants.length}</span>
              </span>
            </div>
            <div className="text-sm font-black truncate">{room.content?.name || room.title}</div>
          </div>
          <button onClick={invite} data-testid="listen-room-invite" className="p-2 rounded-full bg-white/10 hover:bg-white/15" title="Invite">
            <Share2 size={16} />
          </button>
          <button onClick={leave} data-testid="listen-room-leave" className="p-2 rounded-full bg-white/10 hover:bg-white/15" title="Leave">
            <LogOut size={16} />
          </button>
        </div>
      </div>

      <div className="max-w-3xl mx-auto w-full px-4 flex-1 flex flex-col">
        {/* Participants + challenge */}
        <div className="py-3 flex items-center gap-2 overflow-x-auto no-scrollbar" data-testid="listen-room-participants">
          {participants.map((p) => (
            <div key={p.user_id} className="flex-shrink-0 flex flex-col items-center gap-1 w-14">
              <Avatar name={p.name} url={p.avatar_url} size={44} />
              <span className="text-[10px] text-slate-400 truncate max-w-[54px]">
                {p.role === "host" ? "🎙 " : ""}{(p.name || "").split(" ")[0]}
              </span>
            </div>
          ))}
        </div>
        {challenge && (
          <div className="mb-2 rounded-2xl p-3 bg-amber-400/10 border border-amber-400/20 flex items-center gap-3"
                    data-testid="listen-room-challenge">
            <Trophy size={16} className="text-amber-300 shrink-0" />
            <div className="flex-1">
              <div className="text-[11px] font-bold text-amber-200">
                {challenge.awarded ? "Challenge complete — BigPoints earned! 🎉"
                  : `Listen with a friend: ${challenge.minutes}/${challenge.target} min`}
              </div>
              <div className="mt-1 h-1.5 rounded-full bg-white/10 overflow-hidden">
                <div className="h-full rounded-full bg-amber-400"
                          style={{ width: `${Math.min(100, (challenge.minutes / challenge.target) * 100)}%` }} />
              </div>
            </div>
            {challenge.awarded && <span className="text-amber-300 font-black text-sm">+{challenge.reward_points}</span>}
          </div>
        )}

        {/* Chat */}
        <div ref={chatRef} className="flex-1 overflow-y-auto space-y-2 py-2 relative" data-testid="listen-room-chat"
                  style={{ minHeight: 200 }}>
          {messages.length === 0 && (
            <div className="text-center text-slate-500 text-sm py-10">Say hi 👋 and vibe together.</div>
          )}
          {messages.map((m) => (
            <div key={m.id} className="flex items-start gap-2.5">
              <Avatar name={m.name} url={m.avatar_url} size={30} />
              <div className="min-w-0">
                <div className="text-[11px] text-slate-400 font-semibold">{m.name}</div>
                <div className="text-sm text-slate-100 break-words">{m.text}</div>
              </div>
            </div>
          ))}
          {/* floating reactions */}
          <div className="pointer-events-none absolute inset-0 overflow-hidden">
            {floaters.map((f) => (
              <span key={f.key} className="absolute bottom-0 text-2xl animate-[floatUp_2.5s_ease-out_forwards]"
                        style={{ left: `${f.left}%` }}>{f.emoji}</span>
            ))}
          </div>
        </div>

        {/* Reactions + composer */}
        <div className="py-3 sticky bottom-0 bg-gradient-to-t from-[#0a0a14] to-transparent">
          <div className="flex gap-1.5 mb-2" data-testid="listen-room-reactions">
            {REACTIONS.map((e) => (
              <button key={e} onClick={() => react(e)} data-testid={`listen-room-react-${e}`}
                            className="w-10 h-10 rounded-full bg-white/[0.06] hover:bg-white/[0.12] text-lg active:scale-90 transition">
                {e}
              </button>
            ))}
          </div>
          <div className="flex gap-2 items-center">
            <input value={text} onChange={(e) => setText(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && send()}
                        data-testid="listen-room-input"
                        placeholder="Message the room…"
                        className="flex-1 rounded-full bg-white/[0.06] border border-white/10 px-4 py-3 text-sm outline-none focus:border-purple-400/60" />
            <button onClick={send} data-testid="listen-room-send"
                          className="w-12 h-12 rounded-full grid place-items-center text-white shrink-0"
                          style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              <Send size={18} />
            </button>
          </div>
        </div>
      </div>

      <style>{`@keyframes floatUp{0%{transform:translateY(0);opacity:1}100%{transform:translateY(-220px);opacity:0}}`}</style>
    </div>
  );
}
