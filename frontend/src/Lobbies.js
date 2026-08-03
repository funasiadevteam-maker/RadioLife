// Phase 7 — /lobbies list page. Browse + join + host a new lobby.
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import {
  Users, Radio as RadioIcon, ChevronLeft, Plus, Loader2, Lock, Crown, MapPin,
  Music, Zap,
} from "lucide-react";
import { useAuth, API } from "@/AuthContext";
import "./Lobbies.css";

export default function Lobbies() {
  const { user, loading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [channels, setChannels] = useState([]);
  const [filterChannel, setFilterChannel] = useState("");
  const [filterMood, setFilterMood] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [caps, setCaps] = useState(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login"); return; }
  }, [user, authLoading, navigate]);

  useEffect(() => { reload(); }, [filterChannel, filterMood]); // eslint-disable-line
  useEffect(() => {
    (async () => {
      try {
        const [c, h] = await Promise.all([
          axios.get(`${API}/channels`),
          axios.get(`${API}/lobbies/host_caps`),
        ]);
        setChannels(c.data.channels || []);
        setCaps(h.data);
      } catch (_e) { /* ignore */ }
    })();
  }, []);
  useEffect(() => {
    const id = setInterval(reload, 15000); // refresh listing every 15s
    return () => clearInterval(id);
  }, [filterChannel, filterMood]); // eslint-disable-line

  const reload = async () => {
    setLoading(true);
    try {
      const params = {};
      if (filterChannel) params.channel = filterChannel;
      if (filterMood) params.mood = filterMood;
      const r = await axios.get(`${API}/lobbies/list`, { params });
      setItems(r.data.items || []);
    } catch (_e) {
      toast.error("Failed to load lobbies");
    } finally { setLoading(false); }
  };

  if (authLoading || !user) {
    return <div className="lobbies-loading"><Loader2 size={28} className="spin" /></div>;
  }

  return (
    <div className="lobbies-wrap" data-testid="lobbies-page">
      <Toaster theme="dark" position="bottom-right" richColors />

      <header className="lobbies-header">
        <div>
          <Link to="/" className="lobbies-back" data-testid="back-to-radio">
            <ChevronLeft size={14} /> back to radio
          </Link>
          <h1>Lobbies</h1>
          <p className="sub">
            Listen with friends. Synced playback · live chat · majority skip-vote.
          </p>
        </div>
        <button
          className="lobbies-host-btn"
          onClick={() => setShowCreate(true)}
          data-testid="host-lobby-btn">
          <Plus size={14} /> Host a lobby
        </button>
      </header>

      <div className="lobbies-filters" data-testid="lobbies-filters">
        <select
          value={filterChannel}
          onChange={(e) => setFilterChannel(e.target.value)}
          data-testid="filter-channel">
          <option value="">All channels</option>
          {channels.map((c) => (
            <option key={c.slug} value={c.slug}>{c.name}</option>
          ))}
        </select>
        <select
          value={filterMood}
          onChange={(e) => setFilterMood(e.target.value)}
          data-testid="filter-mood">
          <option value="">All moods</option>
          {["chill", "party", "romantic", "uplifting", "groove", "intense"].map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
        <div className="lobbies-count mono" data-testid="lobbies-count">
          {items.length} LIVE · {items.reduce((s, l) => s + (l.current_listener_count || 0), 0)} LISTENING
        </div>
      </div>

      {loading && items.length === 0 ? (
        <div className="lobbies-empty"><Loader2 size={28} className="spin" /></div>
      ) : items.length === 0 ? (
        <div className="lobbies-empty" data-testid="lobbies-empty">
          <Users size={36} />
          <h3>No live lobbies yet</h3>
          <p>Be the first to host one — your friends can drop in with a single tap.</p>
          <button
            className="lobbies-host-btn"
            onClick={() => setShowCreate(true)}
            data-testid="empty-host-btn">
            <Plus size={14} /> Host a lobby
          </button>
        </div>
      ) : (
        <div className="lobbies-grid" data-testid="lobbies-grid">
          {items.map((lobby) => (
            <LobbyCard key={lobby.lobby_id} lobby={lobby} />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateLobbyModal
          channels={channels}
          caps={caps}
          isPremium={user.is_premium}
          onClose={() => setShowCreate(false)}
          onCreated={(lobbyId) => navigate(`/lobby/${lobbyId}`)}
        />
      )}
    </div>
  );
}

function LobbyCard({ lobby }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const onJoin = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await axios.post(`${API}/lobbies/${lobby.lobby_id}/join`);
      navigate(`/lobby/${lobby.lobby_id}`);
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (d === "free_daily_join_cap_reached") {
        toast.error("Daily join limit reached — go Premium for unlimited lobbies");
        navigate("/pricing");
      } else if (d === "lobby_full") {
        toast.error("This lobby is full");
      } else {
        toast.error(d || "Could not join");
      }
    } finally { setBusy(false); }
  };
  const pct = Math.min(100,
    (lobby.current_listener_count / lobby.max_listeners) * 100);
  return (
    <div className="lobby-card" data-testid={`lobby-card-${lobby.lobby_id}`}>
      <div className="lobby-card-top">
        <div
          className="lobby-card-avatar"
          style={{ background: lobby.host_avatar_color || "#ff2d95" }}>
          {(lobby.host_display_name || "?").slice(0, 1).toUpperCase()}
        </div>
        <div className="lobby-card-meta">
          <div className="lobby-card-name" data-testid="lobby-card-name">
            {lobby.name}
          </div>
          <div className="lobby-card-host mono">
            hosted by <b>{lobby.host_display_name}</b>
            {lobby.city ? <> · <MapPin size={9} /> {lobby.city}</> : null}
          </div>
        </div>
      </div>
      {lobby.description && (
        <p className="lobby-card-desc">{lobby.description}</p>
      )}
      <div className="lobby-card-tags">
        <span className="lobby-tag channel-tag">
          <Music size={10} /> {lobby.channel_name || lobby.channel_slug}
        </span>
        {lobby.mood && (
          <span className="lobby-tag mood-tag">{lobby.mood}</span>
        )}
        {lobby.is_event && (
          <span className="lobby-tag event-tag">
            <Zap size={10} /> EVENT
          </span>
        )}
      </div>
      <div className="lobby-card-progress" data-testid="lobby-card-progress">
        <div className="bar"><div className="fill" style={{ width: `${pct}%` }} /></div>
        <div className="mono">
          <Users size={10} /> {lobby.current_listener_count}/{lobby.max_listeners}
        </div>
      </div>
      <button
        className="lobby-join-btn"
        onClick={onJoin} disabled={busy}
        data-testid={`join-${lobby.lobby_id}`}>
        {busy ? <Loader2 size={14} className="spin" /> : <><RadioIcon size={14} /> Join lobby</>}
      </button>
    </div>
  );
}

function CreateLobbyModal({ channels, caps, isPremium, onClose, onCreated }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [channelSlug, setChannelSlug] = useState(channels[0]?.slug || "");
  const [mood, setMood] = useState("");
  const [isPublic, setIsPublic] = useState(true);
  const [maxListeners, setMaxListeners] = useState(caps?.max_listeners || 50);
  const [busy, setBusy] = useState(false);
  const channelObj = useMemo(
    () => channels.find((c) => c.slug === channelSlug), [channelSlug, channels],
  );
  const channelLocked = channelObj?.premium_only && !isPremium;

  const submit = async (e) => {
    e?.preventDefault();
    if (!name.trim()) return toast.error("Lobby name required");
    if (channelLocked) return toast.error("This channel needs Premium");
    setBusy(true);
    try {
      const r = await axios.post(`${API}/lobbies/create`, {
        name, description, channel_slug: channelSlug,
        mood: mood || null,
        is_public: isPublic, max_listeners: Number(maxListeners),
      });
      toast.success(`Lobby live — ${r.data.name}`);
      onCreated(r.data.lobby_id);
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (typeof d === "string" && d.startsWith("already_hosting:")) {
        const lid = d.split(":")[1];
        toast.message("You already host a live lobby — jumping back in.");
        onCreated(lid);
        return;
      }
      toast.error(d || "Could not create lobby");
    } finally { setBusy(false); }
  };

  return (
    <div className="lobby-modal-backdrop" onClick={onClose} data-testid="create-modal">
      <div className="lobby-modal" onClick={(e) => e.stopPropagation()}>
        <h2>Host a lobby</h2>
        <p className="sub">
          {isPremium
            ? <>You're Premium — up to <b>{caps?.premium_host_max_listeners ?? 200}</b> listeners.</>
            : <>Free hosts cap at <b>{caps?.free_host_max_listeners ?? 50}</b> listeners. Upgrade for more.</>}
        </p>
        <form onSubmit={submit}>
          <label>Name
            <input
              value={name}
              maxLength={60}
              onChange={(e) => setName(e.target.value)}
              placeholder="Friday night vibes"
              data-testid="lobby-name-input" />
          </label>
          <label>Description (optional)
            <input
              value={description}
              maxLength={200}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="bring your karak chai"
              data-testid="lobby-desc-input" />
          </label>
          <div className="row">
            <label style={{ flex: 1 }}>Channel
              <select
                value={channelSlug}
                onChange={(e) => setChannelSlug(e.target.value)}
                data-testid="lobby-channel-select">
                {channels.map((c) => (
                  <option key={c.slug} value={c.slug}>
                    {c.name}{c.premium_only ? " · VIP" : ""}
                  </option>
                ))}
              </select>
              {channelLocked && (
                <span className="lock mono"><Lock size={9} /> Premium only</span>
              )}
            </label>
            <label style={{ flex: 1 }}>Mood
              <select
                value={mood}
                onChange={(e) => setMood(e.target.value)}
                data-testid="lobby-mood-select">
                <option value="">Pick a vibe</option>
                {["chill", "party", "romantic", "uplifting", "groove", "intense"].map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            </label>
          </div>
          <div className="row">
            <label style={{ flex: 1 }}>Max listeners
              <input
                type="number" min={2}
                max={caps?.max_listeners ?? 50}
                value={maxListeners}
                onChange={(e) => setMaxListeners(e.target.value)}
                data-testid="lobby-max-listeners" />
            </label>
            <label style={{ flex: 1, display: "flex", alignItems: "center", gap: 10 }}>
              <input
                type="checkbox" checked={isPublic}
                onChange={(e) => setIsPublic(e.target.checked)}
                data-testid="lobby-public-toggle" />
              <span style={{ fontSize: 12 }}>Public · listed in the directory</span>
            </label>
          </div>
          <div className="modal-actions">
            <button type="button" onClick={onClose} data-testid="cancel-create-btn">Cancel</button>
            <button
              type="submit" className="primary"
              disabled={busy || channelLocked || !name.trim()}
              data-testid="submit-create-btn">
              {busy ? <Loader2 size={14} className="spin" /> : <>Go live <RadioIcon size={13} /></>}
            </button>
          </div>
          {!isPremium && (
            <div className="upsell-strip mono">
              <Crown size={11} /> Premium hosts: 200 listeners, unlimited joins, VIP channels
              <Link to="/pricing">See plans →</Link>
            </div>
          )}
        </form>
      </div>
    </div>
  );
}
