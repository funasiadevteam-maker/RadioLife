// Phase 7 — /lobby/:id room page. Host drives playback via radio API + WS announce.
// Listeners receive segment_changed broadcasts, sync to host's clock with seek
// offset from started_at. Chat + reactions + presence + skip-vote all WS.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Send, ChevronLeft, Crown, Users, X, Volume2, VolumeX, SkipForward, MessageCircle,
  LogOut as LeaveIcon, Loader2, Smile, AlertTriangle, Play, Pause, Music, Award,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import "./Lobbies.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const WS_URL = (() => {
  const u = new URL(BACKEND_URL);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  return u.toString().replace(/\/$/, "");
})();

const REACTION_PALETTE = [
  "❤️", "🔥", "👍", "👏", "🎉", "🎶", "🕺", "💃", "🪩",
  "😍", "😂", "🤩", "😎", "🙏", "💯", "🚀", "✨", "🎵", "🎤", "🎧",
];

export default function Lobby() {
  const { id: lobbyId } = useParams();
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();

  const [lobby, setLobby] = useState(null);
  const [members, setMembers] = useState([]);
  const [messages, setMessages] = useState([]);
  const [reactions, setReactions] = useState([]); // ephemeral floating reactions
  const [skipVotes, setSkipVotes] = useState({ votes: 0, threshold: 1, members: 1 });
  const [wsConnected, setWsConnected] = useState(false);
  const [isHost, setIsHost] = useState(false);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(0.85);
  const [playing, setPlaying] = useState(false);
  const [currentSegment, setCurrentSegment] = useState(null);
  const [chatInput, setChatInput] = useState("");
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);

  // Host-only: radio session + prefetch state
  const [hostSessionId, setHostSessionId] = useState(null);
  const [hostStarting, setHostStarting] = useState(false);
  const [skipBusy, setSkipBusy] = useState(false);

  const audioRef = useRef(null);
  const wsRef = useRef(null);
  const messagesRef = useRef(null);
  const segmentEndedHandledRef = useRef(false);
  const segmentStartedAtRef = useRef(null);
  // Listener clock drift: how many seconds the audio.currentTime should be
  // ahead of the file's natural start to stay in sync with the host.
  const seekOffsetRef = useRef(0);

  // ---- Auth gate
  useEffect(() => {
    if (authLoading) return;
    if (!user) navigate("/login");
  }, [user, authLoading, navigate]);

  // ---- Bootstrap: load detail + join (if not already member)
  useEffect(() => {
    if (!user || !lobbyId) return;
    (async () => {
      try {
        // Try detail first — host or rejoiner doesn't need to call /join
        const d = await axios.get(`${API}/lobbies/${lobbyId}`);
        setLobby(d.data);
        setMembers(d.data.members_preview || []);
        setMessages(d.data.recent_messages || []);
        setIsHost(d.data.i_am_host);
        // If not a member yet, attempt to join
        const isMember = (d.data.members_preview || [])
          .some((m) => m.user_id === user.user_id);
        if (!isMember) {
          const j = await axios.post(`${API}/lobbies/${lobbyId}/join`);
          if (j.data.role === "host") setIsHost(true);
        }
        openWebSocket();
      } catch (err) {
        const code = err?.response?.data?.detail;
        if (code === "free_daily_join_cap_reached") {
          toast.error("Daily join limit reached — go Premium");
          navigate("/pricing");
        } else if (code === "invite_required") {
          toast.error("This lobby is private — you need an invite link");
          navigate("/lobbies");
        } else if (code === "lobby_full") {
          toast.error("Lobby is full");
          navigate("/lobbies");
        } else if (err?.response?.status === 404) {
          toast.error("Lobby not found");
          navigate("/lobbies");
        } else {
          toast.error(code || "Failed to load lobby");
        }
      }
    })();
    return () => { closeWebSocket(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user, lobbyId]);

  // ---- WS connection
  const openWebSocket = useCallback(() => {
    if (wsRef.current) return;
    const ws = new WebSocket(`${WS_URL}/api/lobbies/ws/${lobbyId}`);
    wsRef.current = ws;
    ws.onopen = () => { setWsConnected(true); };
    ws.onclose = () => { setWsConnected(false); wsRef.current = null; };
    ws.onerror = () => { /* keep silent; onclose will retry */ };
    ws.onmessage = (e) => {
      let msg;
      try { msg = JSON.parse(e.data); } catch { return; }
      handleWsMessage(msg);
    };
    // Heartbeat
    const ping = setInterval(() => {
      try { ws.readyState === 1 && ws.send(JSON.stringify({ type: "ping" })); }
      catch (_e) { /* */ }
    }, 25000);
    ws.addEventListener("close", () => clearInterval(ping));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lobbyId]);

  const closeWebSocket = () => {
    if (wsRef.current) {
      try { wsRef.current.close(); } catch (_e) { /* */ }
      wsRef.current = null;
    }
  };

  const handleWsMessage = (msg) => {
    switch (msg.type) {
      case "hello":
        if (msg.you?.role === "host") setIsHost(true);
        if (msg.current_segment?.segment_id) syncToSegment(msg.current_segment);
        break;
      case "chat_message":
        setMessages((m) => [...m, msg].slice(-100));
        break;
      case "reaction":
        const tag = `${msg.ts}-${msg.user_id}-${msg.emoji}-${Math.random()}`;
        setReactions((r) => [...r, { ...msg, _tag: tag }].slice(-20));
        setTimeout(() => {
          setReactions((r) => r.filter((x) => x._tag !== tag));
        }, 3200);
        break;
      case "presence_update":
        setLobby((l) => l
          ? { ...l, current_listener_count: msg.current_listener_count ?? l.current_listener_count }
          : l);
        if (msg.action === "join" && msg.user) {
          setMembers((mm) => mm.some((x) => x.user_id === msg.user.user_id)
            ? mm : [...mm, { ...msg.user, joined_at: new Date().toISOString() }]);
        } else if (msg.action === "leave" || msg.action === "kicked" || msg.action === "ws_disconnect") {
          setMembers((mm) => mm.filter((x) => x.user_id !== msg.user.user_id));
        }
        break;
      case "skip_vote_update":
        setSkipVotes({
          votes: msg.votes, threshold: msg.threshold,
          members: msg.members, triggered: msg.triggered,
        });
        break;
      case "host_skip_now":
        // I'm the host — execute the skip
        if (isHost && hostSessionId) hostSkipNow();
        break;
      case "segment_changed":
        syncToSegment(msg);
        break;
      case "channel_changed":
        setLobby((l) => l
          ? { ...l, channel_slug: msg.channel_slug, channel_name: msg.channel_name }
          : l);
        toast.info(`Channel switched to ${msg.channel_name}`);
        break;
      case "host_changed":
        setLobby((l) => l ? { ...l, host_user_id: msg.new_host_user_id,
                                 host_display_name: msg.new_host_display_name } : l);
        setIsHost(msg.new_host_user_id === user?.user_id);
        toast.message(`Host is now ${msg.new_host_display_name}`);
        break;
      case "kicked":
        toast.error(`You were removed from the lobby`);
        navigate("/lobbies");
        break;
      case "lobby_closed":
        toast.message("Lobby ended");
        navigate("/lobbies");
        break;
      case "error":
        if (msg.code !== "rate_limited") toast.error(msg.code);
        break;
      default: /* ignore */
    }
  };

  // ---- Audio sync
  const syncToSegment = (segMeta) => {
    if (!segMeta || !segMeta.segment_url) return;
    setCurrentSegment(segMeta);
    segmentEndedHandledRef.current = false;
    const startedAt = segMeta.started_at ? new Date(segMeta.started_at).getTime() : Date.now();
    segmentStartedAtRef.current = startedAt;
    const elapsed = Math.max(0, (Date.now() - startedAt) / 1000);
    seekOffsetRef.current = elapsed;
    const a = audioRef.current;
    if (a) {
      a.src = `${BACKEND_URL}${segMeta.segment_url}`;
      a.load();
      const onLoaded = () => {
        if (elapsed > 0 && elapsed < (segMeta.duration_sec || 9999)) {
          try { a.currentTime = elapsed; } catch (_e) { /* */ }
        }
        a.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
        a.removeEventListener("loadedmetadata", onLoaded);
      };
      a.addEventListener("loadedmetadata", onLoaded);
    }
  };

  // ---- Host-only: start radio + announce loop
  const hostStartRadio = async () => {
    if (!isHost || hostSessionId || hostStarting) return;
    setHostStarting(true);
    try {
      const r = await axios.post(`${API}/radio/start`,
        { channel: lobby.channel_slug }, { timeout: 120000 });
      setHostSessionId(r.data.session_id);
      const seg = r.data.segment;
      // Announce to listeners
      await axios.post(`${API}/lobbies/${lobbyId}/announce_segment`, segToPayload(seg));
      // syncToSegment will be triggered by the server's broadcast back to us
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : "Could not start radio");
    } finally { setHostStarting(false); }
  };

  const segToPayload = (seg) => ({
    segment_id: seg.segment_id,
    segment_url: seg.segment_url,
    duration_sec: seg.duration_sec,
    track_title: seg.track_title,
    track_artist: seg.track_artist,
    rj_voice_name: seg.rj_voice_name,
    rj_start_sec: seg.rj_start_sec,
    rj_script: seg.rj_script,
    channel_slug: seg.channel_slug,
    channel_name: seg.channel_name,
  });

  const hostFetchNext = async () => {
    if (!isHost || !hostSessionId) return;
    try {
      const r = await axios.get(`${API}/radio/next`,
        { params: { session_id: hostSessionId }, timeout: 120000 });
      await axios.post(`${API}/lobbies/${lobbyId}/announce_segment`, segToPayload(r.data.segment));
    } catch (err) {
      toast.error("Could not load next segment");
    }
  };

  const hostSkipNow = async () => {
    if (!isHost || !hostSessionId || skipBusy) return;
    setSkipBusy(true);
    try {
      const r = await axios.post(`${API}/radio/skip`, null,
        { params: { session_id: hostSessionId }, timeout: 120000 });
      await axios.post(`${API}/lobbies/${lobbyId}/announce_segment`, segToPayload(r.data.segment));
    } catch (err) {
      toast.error("Skip failed");
    } finally { setSkipBusy(false); }
  };

  // ---- Audio ended → host fetches next
  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onEnded = () => {
      if (segmentEndedHandledRef.current) return;
      segmentEndedHandledRef.current = true;
      if (isHost) hostFetchNext();
    };
    a.addEventListener("ended", onEnded);
    return () => a.removeEventListener("ended", onEnded);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isHost, hostSessionId, lobbyId]);

  useEffect(() => {
    const a = audioRef.current;
    if (a) { a.volume = volume; a.muted = muted; }
  }, [volume, muted]);

  // ---- Auto-scroll chat
  useEffect(() => {
    if (messagesRef.current) {
      messagesRef.current.scrollTop = messagesRef.current.scrollHeight;
    }
  }, [messages]);

  // ---- Sender helpers
  const sendChat = () => {
    const text = chatInput.trim();
    if (!text) return;
    if (!wsRef.current || wsRef.current.readyState !== 1) {
      toast.error("Not connected yet");
      return;
    }
    wsRef.current.send(JSON.stringify({ type: "chat", text }));
    setChatInput("");
  };
  const sendReaction = (emoji) => {
    if (!wsRef.current || wsRef.current.readyState !== 1) return;
    wsRef.current.send(JSON.stringify({ type: "reaction", emoji }));
    setEmojiOpen(false);
  };
  const castSkipVote = async () => {
    try {
      const r = await axios.post(`${API}/lobbies/${lobbyId}/skip_vote`);
      setSkipVotes({
        votes: r.data.votes, threshold: r.data.threshold,
        members: r.data.members, triggered: r.data.triggered,
      });
      if (r.data.triggered) toast.message("Majority reached — skipping…");
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (d === "skip_cap_reached") toast.error("Lobby skip cap reached this hour");
      else toast.error(d || "Vote failed");
    }
  };

  // ---- Leave / close
  const leaveLobby = async () => {
    setLeaving(true);
    try { await axios.post(`${API}/lobbies/${lobbyId}/leave`); }
    catch (_e) { /* */ }
    closeWebSocket();
    navigate("/lobbies");
  };
  const closeLobby = async () => {
    if (!window.confirm("End this lobby for everyone?")) return;
    try {
      await axios.post(`${API}/lobbies/${lobbyId}/close`);
      navigate("/lobbies");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Could not close");
    }
  };
  const kickMember = async (uid) => {
    if (!window.confirm("Remove this listener?")) return;
    try { await axios.post(`${API}/lobbies/${lobbyId}/kick`, { user_id: uid }); }
    catch (err) { toast.error(err?.response?.data?.detail || "Could not kick"); }
  };

  const myAvatar = useMemo(() => {
    const me = members.find((m) => m.user_id === user?.user_id);
    return me?.avatar_color || "#ff2d95";
  }, [members, user]);

  if (authLoading || !user || !lobby) {
    return <div className="lobbies-loading"><Loader2 size={28} className="spin" /></div>;
  }

  const pctFull = (lobby.current_listener_count / lobby.max_listeners) * 100;
  const skipPct = (skipVotes.votes / skipVotes.threshold) * 100;

  return (
    <div className="lobby-room" data-testid="lobby-room">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="lobby-room-header">
        <Link to="/lobbies" className="lobbies-back" data-testid="lobby-back">
          <ChevronLeft size={14} /> back to lobbies
        </Link>
        <div className="lobby-room-title">
          <h1 data-testid="lobby-title">{lobby.name}</h1>
          <div className="mono sub">
            hosted by <b>{lobby.host_display_name}</b>
            {" · "} <Users size={11} /> {lobby.current_listener_count}/{lobby.max_listeners}
            {" · "} {wsConnected
              ? <span className="ws-dot connected" data-testid="ws-status-connected">LIVE</span>
              : <span className="ws-dot" data-testid="ws-status-disconnected">CONNECTING…</span>}
          </div>
        </div>
        <div className="lobby-room-actions">
          {isHost ? (
            <button className="btn-danger" onClick={closeLobby} data-testid="close-lobby-btn">
              <X size={13} /> End lobby
            </button>
          ) : (
            <button className="btn-ghost" onClick={leaveLobby}
                    disabled={leaving} data-testid="leave-lobby-btn">
              {leaving ? <Loader2 size={13} className="spin" /> : <LeaveIcon size={13} />} Leave
            </button>
          )}
        </div>
      </header>

      <div className="lobby-room-body">
        <main className="lobby-stage" data-testid="lobby-stage">
          {!currentSegment ? (
            isHost ? (
              <div className="lobby-empty-stage">
                <Music size={42} />
                <h2>Ready to start the radio?</h2>
                <p>Tap to begin streaming for {lobby.current_listener_count - 1} listener(s).</p>
                <button
                  className="big-go-live"
                  onClick={hostStartRadio} disabled={hostStarting}
                  data-testid="host-start-radio-btn">
                  {hostStarting ? <Loader2 size={16} className="spin" /> : <Play size={16} />}
                  {hostStarting ? "Starting…" : "Go live"}
                </button>
              </div>
            ) : (
              <div className="lobby-empty-stage">
                <Loader2 size={32} className="spin" />
                <h2>Waiting for host…</h2>
                <p>Your host is queueing up the first track.</p>
              </div>
            )
          ) : (
            <div className="lobby-now-playing" data-testid="lobby-now-playing">
              <div className="np-badge mono">
                <span className="np-dot" /> ON AIR · {currentSegment.channel_name || lobby.channel_name}
              </div>
              <div className="np-title">{currentSegment.track_title || "—"}</div>
              <div className="np-artist">{currentSegment.track_artist || ""}</div>
              {currentSegment.rj_script && (
                <div className="np-rj-script" data-testid="lobby-rj-script">
                  <div className="mono rj-tag">RJ {currentSegment.rj_voice_name?.toUpperCase()}</div>
                  <p>{currentSegment.rj_script}</p>
                </div>
              )}
              <div className="np-controls">
                <button
                  className="ctrl-toggle"
                  onClick={() => {
                    const a = audioRef.current;
                    if (!a) return;
                    if (a.paused) a.play().then(() => setPlaying(true)).catch(() => {});
                    else { a.pause(); setPlaying(false); }
                  }}
                  data-testid="lobby-play-btn">
                  {playing ? <Pause size={16} /> : <Play size={16} />}
                </button>
                <button
                  className="ctrl-toggle"
                  onClick={() => setMuted((m) => !m)}
                  data-testid="lobby-mute-btn">
                  {muted ? <VolumeX size={16} /> : <Volume2 size={16} />}
                </button>
                <input className="vol-slider" type="range" min={0} max={1} step={0.01}
                       value={muted ? 0 : volume}
                       onChange={(e) => { setVolume(parseFloat(e.target.value)); setMuted(false); }}
                       data-testid="lobby-volume" />
                <div className="skip-vote-pill" data-testid="skip-vote-pill">
                  <button className="skip-vote-btn" onClick={castSkipVote}
                          data-testid="cast-skip-vote-btn">
                    <SkipForward size={13} /> Vote skip
                  </button>
                  <div className="skip-bar">
                    <div className="skip-fill"
                         style={{ width: `${Math.min(100, skipPct)}%` }} />
                  </div>
                  <span className="mono">{skipVotes.votes}/{skipVotes.threshold}</span>
                </div>
              </div>
              {isHost && hostSessionId && (
                <button className="host-skip-now"
                        onClick={hostSkipNow} disabled={skipBusy}
                        data-testid="host-skip-now-btn">
                  {skipBusy ? <Loader2 size={13} className="spin" /> : <SkipForward size={13} />}
                  Skip now (host)
                </button>
              )}
            </div>
          )}
          {/* Floating reactions overlay */}
          <div className="reactions-overlay" data-testid="reactions-overlay">
            {reactions.map((r) => (
              <span key={r._tag} className="floating-reaction"
                    style={{ left: `${10 + (parseInt((r.user_id || "").slice(-2) || "0", 36) % 80)}%`,
                              color: r.avatar_color }}>
                {r.emoji}
              </span>
            ))}
          </div>
          {/* Emoji palette */}
          <div className="emoji-launcher">
            <button onClick={() => setEmojiOpen((o) => !o)}
                    className="emoji-btn" data-testid="emoji-launcher-btn">
              <Smile size={16} />
            </button>
            {emojiOpen && (
              <div className="emoji-palette" data-testid="emoji-palette">
                {REACTION_PALETTE.map((emoji) => (
                  <button key={emoji} onClick={() => sendReaction(emoji)}
                          data-testid={`react-${emoji}`}>
                    {emoji}
                  </button>
                ))}
              </div>
            )}
          </div>
        </main>

        <aside className="lobby-sidepanel">
          <section className="lobby-members" data-testid="lobby-members-panel">
            <h3 className="mono">
              <Users size={11} /> LISTENERS · {lobby.current_listener_count}
            </h3>
            <ul>
              {members.map((m) => (
                <li key={m.user_id} data-testid={`member-${m.user_id}`}>
                  <span className="member-dot"
                        style={{ background: m.avatar_color || "#888" }} />
                  <span className="member-name">{m.display_name}</span>
                  {/* Phase 10b — host_perks pre-badge chips (annual / L4+) */}
                  {(m.host_perks || []).map((p, i) => (
                    <span key={`perk-${i}`}
                          className={"member-tag perk-tag perk-" + p.kind}
                          title={p.label}
                          data-testid={`member-perk-${m.user_id}-${p.kind}`}>
                      {p.glyph}
                    </span>
                  ))}
                  {/* Phase 10b — top public badges chips (max 3 visible) */}
                  {(m.public_badges || []).slice(0, 3).map((b) => (
                    <span key={b.badge_id}
                          className={"member-tag badge-tag tier-" + (b.tier || "bronze")}
                          title={`${b.name} · ${b.points} pts`}
                          data-testid={`member-badge-${m.user_id}-${b.badge_id}`}>
                      <Award size={9} />
                    </span>
                  ))}
                  {(m.public_badges || []).length > 3 && (
                    <span className="member-tag badge-more"
                          title={`${m.public_badges.length - 3} more`}>
                      +{m.public_badges.length - 3}
                    </span>
                  )}
                  {m.role === "host" && (
                    <span className="member-tag host-tag"><Crown size={9} /> HOST</span>
                  )}
                  {isHost && m.user_id !== user.user_id && m.role !== "host" && (
                    <button className="kick-mini-btn"
                            onClick={() => kickMember(m.user_id)}
                            title="Remove" data-testid={`kick-${m.user_id}`}>
                      <X size={10} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <section className="lobby-chat" data-testid="lobby-chat-panel">
            <h3 className="mono">
              <MessageCircle size={11} /> CHAT
            </h3>
            <div className="chat-list" ref={messagesRef} data-testid="chat-messages">
              {messages.length === 0 && (
                <div className="chat-empty mono">say something nice…</div>
              )}
              {messages.map((m) => (
                <div className="chat-msg" key={m.message_id || m.created_at}
                     data-testid="chat-msg">
                  <span className="chat-avatar"
                        style={{ background: m.avatar_color || "#888" }}>
                    {(m.display_name || "?").slice(0, 1).toUpperCase()}
                  </span>
                  <div className="chat-body">
                    <div className="chat-name">{m.display_name}</div>
                    <div className="chat-text">{m.text}</div>
                  </div>
                </div>
              ))}
            </div>
            <div className="chat-input">
              <span className="my-avatar" style={{ background: myAvatar }}>
                {(user.name || "?").slice(0, 1).toUpperCase()}
              </span>
              <input
                value={chatInput}
                maxLength={240}
                placeholder={wsConnected ? "say something…" : "connecting…"}
                onKeyDown={(e) => { if (e.key === "Enter") sendChat(); }}
                onChange={(e) => setChatInput(e.target.value)}
                disabled={!wsConnected}
                data-testid="chat-input" />
              <button onClick={sendChat} disabled={!chatInput.trim() || !wsConnected}
                      data-testid="chat-send-btn">
                <Send size={14} />
              </button>
            </div>
          </section>
        </aside>
      </div>

      <audio ref={audioRef} preload="auto" data-testid="lobby-audio" />
    </div>
  );
}
