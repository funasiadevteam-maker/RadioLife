import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { Link, useNavigate } from "react-router-dom";
import {
  Radio as RadioIcon, Play, Pause, SkipForward, Volume2, VolumeX, MapPin, Loader2,
  LogOut, User as UserIcon, Shield, Users, Share2, Clock, Crown, Lock, Coins, Sparkles, Award,
  ThumbsUp, ThumbsDown, RefreshCw,
} from "lucide-react";
import { Toaster, toast } from "sonner";
import { useAuth, API } from "@/AuthContext";
import ChannelSwitcher from "@/ChannelSwitcher";
import ChannelGateModal from "@/ChannelGateModal";
// Phase 41 P1-interrupt — Community Radio strip on the /radio tab.
import CommunityRadioStrip from "@/components/CommunityRadioStrip";
import ShareBreakModal from "@/ShareBreakModal";
import ActionCard from "@/ActionCard";
import RjActionCard from "@/RjActionCard";
import ReactivationBanner from "@/ReactivationBanner";
import { useAudioBus, bumpVolume } from "@/shell/useAudioBus";
import RadioRail from "@/RadioRail";
import { useViewport } from "@/shell/useViewport";
// Phase 15d — dynamic city/market for the /radio brand header.
import { useGeoStore } from "@/store/useGeoStore";
import BigFmBrand from "@/components/BigFmBrand";
// Phase 15d.3 — global audio mount lives in GlobalAudio.  Radio.js no
// longer owns the <audio> nodes or the ended/timeupdate handlers; it
// drives the singleton audio elements + mirrors session/transport state
// to `usePlayerStore` so playback survives route changes.
import { audioElements } from "@/store/audioElements";
import { usePlayerStore } from "@/store/usePlayerStore";
import "@/radio-page-v2.css";
import BannerAdSlot from "@/components/BannerAdSlot";
// Phase 41 S2.B — community-station listener-session tracker. Fires
// join/ping/leave for community channels; admin channels are 404'd by
// the backend and silently no-op'd by the hook.
import useStationListenerSession from "@/hooks/useStationListenerSession";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const PREFETCH_LEAD_SEC = 8;

const fmt = (s) => {
  if (!isFinite(s) || s < 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
};
const fmtCountdown = (s) => {
  if (!isFinite(s) || s <= 0) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
};

export default function Radio() {
  const { user, loading: authLoading, logout } = useAuth();
  // Phase 15d — read resolved market for brand header. Component is opt-in to
  // re-render when the city label changes, NOT on every store update.
  const geoCity = useGeoStore((s) => s.city);
  const navigate = useNavigate();
  // Phase 15c — viewport hook at top of component so the conditional rail
  // mount below the early returns doesn't violate rules-of-hooks.
  const vp = useViewport();
  const showRail = vp.layout === "desktop";

  const [channels, setChannelsLocal] = useState([]);
  // Phase 15d.3 — sessionId, currentSeg, nextSeg, playing, activeIdx,
  // history, activeChannel, volume, muted, skip state all live in
  // usePlayerStore so they survive Radio.js unmount when the listener
  // navigates to /home, /wallet, etc.  Local `useState` becomes a
  // thin selector + setter alias so the rest of this file diffs cleanly.
  const sessionId          = usePlayerStore((s) => s.sessionId);
  const setSessionId       = usePlayerStore((s) => s.setSession);
  const currentSeg         = usePlayerStore((s) => s.currentSeg);
  const setCurrentSeg      = usePlayerStore((s) => s.setCurrentSeg);
  const nextSeg            = usePlayerStore((s) => s.nextSeg);
  const setNextSeg         = usePlayerStore((s) => s.setNextSeg);
  const activeIdx          = usePlayerStore((s) => s.activeIdx);
  const setActiveIdx       = usePlayerStore((s) => s.setActiveIdx);
  const playing            = usePlayerStore((s) => s.playing);
  const setPlaying         = usePlayerStore((s) => s.setPlaying);
  const currentTime        = usePlayerStore((s) => s.currentTime);
  const setCurrentTime     = usePlayerStore((s) => s.setCurrentTime);
  const duration           = usePlayerStore((s) => s.duration);
  const setDuration        = usePlayerStore((s) => s.setDuration);
  const volume             = usePlayerStore((s) => s.volume);
  const setVolume          = usePlayerStore((s) => s.setVolume);
  const muted              = usePlayerStore((s) => s.muted);
  const setMuted           = usePlayerStore((s) => s.setMuted);
  const history            = usePlayerStore((s) => s.history);
  const setHistory         = usePlayerStore((s) => s.setHistory);
  const activeChannelStore = usePlayerStore((s) => s.activeChannel);
  const setActiveChannelStore = usePlayerStore((s) => s.setActiveChannel);
  const skipUsed           = usePlayerStore((s) => s.skipUsed);
  const skipLimit          = usePlayerStore((s) => s.skipLimit);
  const skipResetIn        = usePlayerStore((s) => s.skipResetIn);
  const setStoreSkip       = usePlayerStore((s) => s.setSkipState);
  // The setters below are aliases that match the old setX(value) shape
  // (the store's setSkipState is a 3-arg setter).
  const setSkipUsed   = (v) => setStoreSkip(v, null, null);
  const setSkipLimit  = (v) => setStoreSkip(null, v, null);
  const setSkipResetIn = (v) => setStoreSkip(null, null, v);
  const activeChannel    = activeChannelStore;
  const setActiveChannel = (slug) => setActiveChannelStore(slug);
  const setChannels = (list) => {
    setChannelsLocal(list);
    usePlayerStore.getState().setChannels(list);
  };

  const [starting, setStarting] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  // Audio-engine warm-up banner — set when /radio/start returns 503
  // `audio_engine_unavailable` so listeners see a friendly notice + Retry
  // instead of a dead player.
  const [audioWarming, setAudioWarming] = useState(false);  const [switching, setSwitching] = useState(null);
  const [skipCountdown, setSkipCountdown] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);

  const [shareModal, setShareModal] = useState(null);
  const [creatingShare, setCreatingShare] = useState(false);
  // My Radio signals — which feedback the listener gave on the current track.
  const [fbSent, setFbSent] = useState(null); // "like" | "less" | null
  // Phase 10c — channel access gating modal state
  const [gate, setGate] = useState(null); // { access, channel }

  // Phase 15d.3 — Audio elements live in the singleton mounted by
  // <GlobalAudio /> at AppShell root.  We KEEP the `audioRefs` shape so
  // every existing `audioRefs[i].current` reference below still works.
  const audioRefs = [audioElements.a, audioElements.b];
  const prefetchTriggered = useRef(false);
  const autoStarted = useRef(false);
  const sessionRef = useRef(null);
  useEffect(() => { sessionRef.current = sessionId; }, [sessionId]);

  // Phase 41 S2.B — listener-session tracker for the current channel.
  // Hook auto-no-ops for admin channels (backend returns 404
  // `not_community_station`); only community stations get tracked.
  useStationListenerSession(
    currentSeg?.channel_slug || activeChannel || null,
    !!playing,
  );

  // Auth gate
  useEffect(() => {
    if (authLoading) return;
    if (!user) { navigate("/login", { replace: true }); return; }
    if (!user.onboarding_complete) { navigate("/onboarding", { replace: true }); return; }
  }, [user, authLoading, navigate]);

  // Load channels list
  useEffect(() => {
    (async () => {
      try {
        const r = await axios.get(`${API}/channels`);
        setChannels(r.data.channels || []);
        // Phase 41 S1.6 — honor `?channel=` URL param so deep-links from
        // `/r/{slug}` (community Listen CTA) actually tune to the
        // requested station instead of silently falling back to the
        // user's default channel.  If radio_start then fails for that
        // station (e.g. empty_playable_pool / channel_empty), the
        // catch-handler renders a toast — we do NOT auto-tune to a
        // retry_channel.
        const params = new URLSearchParams(window.location.search);
        const requested = params.get("channel");
        setActiveChannel(requested || r.data.default);
      } catch (_e) { /* */ }
    })();
  }, []);

  // Avatar menu outside click
  useEffect(() => {
    if (!menuOpen) return;
    const onClick = (e) => {
      if (!e.target.closest?.(".radio-avatar-wrap")) setMenuOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [menuOpen]);

  // Phase 5 — BigPoints heartbeat: server-side 1 BC/min while playing
  const lastTrackId = useRef(null);
  useEffect(() => {
    if (!user) return;
    const sendBeat = async (trackChanged) => {
      try {
        const sid = sessionRef.current;
        if (!sid) return;
        const a = audioRefs[0].current;
        const b = audioRefs[1].current;
        const playing = (a && !a.paused) || (b && !b.paused);
        if (!playing) return;
        await axios.post(`${API}/bigcoin/heartbeat`,
          { session_id: sid, track_changed: !!trackChanged });
      } catch (_e) { /* ignore */ }
    };
    const id = setInterval(() => sendBeat(false), 60000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);

  // Skip countdown ticker
  useEffect(() => {
    if (skipResetIn <= 0) { setSkipCountdown(0); return; }
    setSkipCountdown(skipResetIn);
    const t0 = Date.now();
    const id = setInterval(() => {
      const elapsed = Math.floor((Date.now() - t0) / 1000);
      const left = Math.max(0, skipResetIn - elapsed);      setSkipCountdown(left);
      if (left <= 0) {
        clearInterval(id);
        refreshSkipState();
      }
    }, 1000);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [skipResetIn]);

  const refreshSkipState = async () => {
    try {
      const r = await axios.get(`${API}/radio/skip_state`);
      setSkipUsed(r.data.used); setSkipLimit(r.data.limit); setSkipResetIn(r.data.reset_in_sec || 0);
    } catch (_e) { /* */ }
  };

  useEffect(() => {
    audioRefs.forEach((r) => {
      if (r.current) { r.current.volume = volume; r.current.muted = muted; }
    });
  }, [volume, muted, currentSeg, nextSeg]); // eslint-disable-line react-hooks/exhaustive-deps

  const applySkipState = (ss) => {
    if (!ss) return;
    setSkipUsed(ss.used); setSkipLimit(ss.limit); setSkipResetIn(ss.reset_in_sec || 0);
  };

  const fetchNext = useCallback(async () => {
    const sid = sessionRef.current;
    if (!sid) return null;
    try {
      const r = await axios.get(`${API}/radio/next`, { params: { session_id: sid }, timeout: 120000 });
      applySkipState(r.data.skip_state);
      return r.data.segment;
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not fetch next segment");
      return null;
    }
  }, []);

  const startRadio = useCallback(async (channelSlug = null) => {
    if (starting || sessionId) return;
    setStarting(true);
    // Mutual exclusivity — stop any live-flagship / podcast stream the
    // instant the user goes ON AIR, BEFORE /radio/start resolves (which
    // can take seconds).  Otherwise the previous stream keeps playing
    // over the tuning sequence ("two stations at once").
    usePlayerStore.getState().clearImported();
    usePlayerStore.getState().clearPodcast();
    // Phase 15d.3 fix — push channel name + thumb to the store
    // optimistically (synchronously, before /radio/start resolves) so
    // Media Session + MiniPlayer reflect the chosen channel within
    // milliseconds instead of waiting for the 5-15s API round-trip.
    const targetSlug = channelSlug || activeChannel;
    if (targetSlug) {
      const ch = channels.find((c) => c.slug === targetSlug);
      if (ch) {
        setActiveChannelStore(
          targetSlug,
          ch.name || targetSlug,
          ch.thumbnail_url || null,
        );
      }
    }
    try {
      const body = channelSlug ? { channel: channelSlug } : { channel: activeChannel };
      const r = await axios.post(`${API}/radio/start`, body, { timeout: 120000 });
      setAudioWarming(false);
      setSessionId(r.data.session_id);
      sessionRef.current = r.data.session_id;
      applySkipState(r.data.skip_state);
      const seg = r.data.segment;
      setCurrentSeg(seg); setHistory([seg]); setActiveIdx(0);
      if (seg.channel_slug) {
        // Phase 15d.3 — also push channel name/thumb to the player store
        // so Media Session + MiniPlayer render the right metadata.
        const ch = channels.find((c) => c.slug === seg.channel_slug);
        setActiveChannelStore(
          seg.channel_slug,
          seg.channel_name || ch?.name || null,
          ch?.thumbnail_url || null,
        );
      }
      setTimeout(() => {
        const a = audioRefs[0].current;
        if (a) {
          a.src = `${BACKEND_URL}${seg.segment_url}`;
          a.load();
          a.play().then(() => setPlaying(true)).catch(() => {
            toast.warning("Autoplay blocked — tap Play");
            setPlaying(false);
          });
        }
      }, 50);
      setTimeout(async () => {
        const next = await fetchNext();
        if (next) {
          setNextSeg(next);
          const a2 = audioRefs[1].current;
          if (a2) { a2.src = `${BACKEND_URL}${next.segment_url}`; a2.load(); }
        }
      }, 200);
      toast.success(`ON AIR — ${seg.channel_name || "FUUSIC"}, dil se`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      // Phase 41 S1.6 — backend returns either `code` (newer endpoints)
      // or legacy `error` (radio engine pre-existing 503 shape). Honor
      // both so the toast branch fires regardless.
      const code = detail?.code || detail?.error;
      if (e?.response?.status === 403 && (
            code === "premium_required"
            || code === "ambassador_level_required"
            || code === "exclusive_unlock_required"
            || code === "access_denied"
          )) {
        // Phase 10c — open the gating modal instead of redirecting
        setGate({
          access: detail,
          channel: { slug: detail.channel, name: detail.channel_name },
        });
      } else if (code === "empty_playable_pool" || code === "channel_empty") {
        // Phase 41 S1.5/S1.6 — clear user-facing message instead of
        // generic "Could not start radio". We INTENTIONALLY ignore
        // `detail.retry_channel` here — backend may return it as a hint
        // but the player must NEVER auto-tune (would feel like a silent
        // swap). The user can click another channel chip if they want.
        toast.error(detail?.message
                    || "This station has no playable tracks right now. Try a different station.");
      } else if (code === "audio_engine_unavailable" || e?.response?.status === 503) {
        // Audio engine warming up — show a persistent, friendly banner
        // (not just a fleeting toast) so it never looks broken.
        setAudioWarming(true);
      } else {
        toast.error(typeof detail === "string"
                    ? detail
                    : (detail?.message || "Could not start radio"));
      }
    } finally {
      setStarting(false);
    }
  }, [starting, sessionId, activeChannel, fetchNext, navigate]); // eslint-disable-line react-hooks/exhaustive-deps

  // My Radio one-tap — auto-start when arriving via `?autoplay=1`
  // (e.g. from the Listen Hub "Start My Radio" card). Fires once, after
  // channels resolve `activeChannel` and only if no session is running.
  useEffect(() => {
    if (autoStarted.current) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get("autoplay") !== "1") return;
    if (!activeChannel || sessionId || starting) return;
    autoStarted.current = true;
    startRadio(activeChannel);
  }, [activeChannel, sessionId, starting, startRadio]);

  // Reset the like/less signal when the track changes.
  useEffect(() => { setFbSent(null); }, [currentSeg?.segment_id]);

  const sendFeedback = async (action) => {
    if (!currentSeg) return;
    try {
      await axios.post(`${API}/radio/feedback`, {
        action,
        segment_id: currentSeg.segment_id,
        track_id: currentSeg.track_id,
        track_title: currentSeg.track_title,
        track_artist: currentSeg.track_artist,
        genre: currentSeg.genre,
        channel_slug: currentSeg.channel_slug || activeChannel,
      });
      setFbSent(action);
      toast.success(action === "like"
        ? "Nice — we'll play more like this"
        : "Got it — you'll hear this less");
    } catch (_e) {
      toast.error("Could not save your preference");
    }
  };

  const switchChannel = async (slug) => {
    if (!sessionId) { setActiveChannel(slug); return; }
    if (switching || slug === activeChannel) return;
    setSwitching(slug);
    // Phase 15d.3 fix — push the new channel name + thumb to the player
    // store OPTIMISTICALLY (synchronously, before the /switch_channel API
    // call resolves) so Media Session + MiniPlayer album / artwork
    // refresh within milliseconds of the click, not after the 5-15s
    // round-trip.  If the server later rejects (e.g. 403 locked), the
    // 403 handler below reverts via setActiveChannel(prev).
    const targetCh = channels.find((c) => c.slug === slug);
    if (targetCh) {
      setActiveChannelStore(
        slug,
        targetCh.name || slug,
        targetCh.thumbnail_url || null,
      );
    }
    const a = audioRefs[activeIdx].current;
    if (a) { try { a.pause(); } catch (_e) { /* */ } }
    try {
      const r = await axios.post(`${API}/radio/switch_channel`,
        { session_id: sessionId, channel: slug }, { timeout: 15000 });
      applySkipState(r.data.skip_state);
      setActiveChannel(r.data.channel_slug || slug);
      setNextSeg(null);
      prefetchTriggered.current = false;
      // Play the short tuning SFX immediately while the new channel's first
      // segment is built in the background. ~3-5s perceived latency.
      const tuningAudio = audioRefs[activeIdx].current;
      if (tuningAudio) {
        tuningAudio.src = `${BACKEND_URL}${r.data.tuning_sfx_url}`;
        tuningAudio.load();
        try { await tuningAudio.play(); setPlaying(true); } catch (_e) { /* */ }
      }
      toast.success(`Tuning to ${r.data.channel_name || slug}…`);
      // Poll until the real first segment is ready
      const start = Date.now();
      const maxWait = 60000;
      const interval = setInterval(async () => {
        if (Date.now() - start > maxWait) { clearInterval(interval); setSwitching(null); return; }
        try {
          const rr = await axios.get(`${API}/radio/ready`, { params: { session_id: sessionId }, timeout: 5000 });
          if (rr.data.ready && rr.data.segment) {
            clearInterval(interval);
            const seg = rr.data.segment;
            applySkipState(rr.data.skip_state);
            setCurrentSeg(seg);
            setHistory((h) => [...h, seg].slice(-6));
            const newAudio = audioRefs[activeIdx].current;
            if (newAudio) {
              newAudio.src = `${BACKEND_URL}${seg.segment_url}`;
              newAudio.load();
              try { await newAudio.play(); setPlaying(true); } catch (_e) { /* */ }
            }
            // Trigger background prefetch of segment 2 on new channel
            setTimeout(async () => {
              const next = await fetchNext();
              if (next) {
                setNextSeg(next);
                const inactive = audioRefs[1 - activeIdx].current;
                if (inactive) { inactive.src = `${BACKEND_URL}${next.segment_url}`; inactive.load(); }
              }
            }, 200);
            toast.success(`Tuned to ${seg.channel_name || slug}`);
            setSwitching(null);
          }
        } catch (_e) { /* keep polling */ }
      }, 1000);
    } catch (e) {
      const status = e?.response?.status;
      const detail = e?.response?.data?.detail;
      const code = detail?.code;
      if (status === 403 && (
            code === "premium_required"
            || code === "ambassador_level_required"
            || code === "exclusive_unlock_required"
            || code === "access_denied"
          )) {
        // Phase 10c — present gate UI; user stays on prior channel
        setGate({
          access: detail,
          channel: { slug: detail.channel, name: detail.channel_name },
        });
      } else if (code === "audio_engine_unavailable" || status === 503) {
        setAudioWarming(true);
      } else {
        toast.error(detail || "Could not switch channel");
      }
      setSwitching(null);
    }
  };

  // Phase 15d.3 — timeupdate / ended / loadedmetadata listeners now live
  // exclusively in <GlobalAudio /> (mounted at AppShell root) so playback
  // advances even when the user has navigated away from /radio.  Radio.js
  // intentionally does NOT re-attach those listeners — doing so would
  // cause duplicate `fetchNext` calls and a double `setCurrentSeg`.

  const togglePlay = () => {
    const a = audioRefs[activeIdx].current;
    if (!a) return;
    if (a.paused) { a.play().then(() => setPlaying(true)).catch(() => {}); }
    else { a.pause(); setPlaying(false); }
  };

  // Phase 15b — wire `bigfm:player:*` events (dispatched by the
  // 15a keyboard shortcuts) into the real audio element.
  useAudioBus({
    onToggle: useCallback(() => togglePlay(), [activeIdx]),  // eslint-disable-line react-hooks/exhaustive-deps
    onVolUp:  useCallback(() => {
      const a = audioRefs[activeIdx].current;
      const v = bumpVolume(a, +0.1);
      if (typeof v === "number") { setVolume(v); setMuted(v === 0); }
    }, [activeIdx]),
    onVolDown: useCallback(() => {
      const a = audioRefs[activeIdx].current;
      const v = bumpVolume(a, -0.1);
      if (typeof v === "number") { setVolume(v); setMuted(v === 0); }
    }, [activeIdx]),
  });

  const skip = async () => {
    if (advancing) return;
    // Try the skip; backend returns 429 if exhausted
    setAdvancing(true);
    const a = audioRefs[activeIdx].current;
    if (a) a.pause();
    try {
      const r = await axios.post(`${API}/radio/skip`,
        null, { params: { session_id: sessionId }, timeout: 120000 });
      applySkipState(r.data.skip_state);
      const seg = r.data.segment;
      const newActive = nextSeg ? (1 - activeIdx) : activeIdx;
      const newAudio = audioRefs[newActive].current;
      if (newAudio) {
        if (newAudio.src !== `${BACKEND_URL}${seg.segment_url}`) {
          newAudio.src = `${BACKEND_URL}${seg.segment_url}`; newAudio.load();
        }
        try { await newAudio.play(); setPlaying(true); setActiveIdx(newActive); } catch (_e) { /* */ }
      }
      setCurrentSeg(seg);
      setHistory((h) => [...h, seg].slice(-6));
      setNextSeg(null);
      prefetchTriggered.current = false;
      setTimeout(async () => {
        const nseg = await fetchNext();
        if (nseg) {
          setNextSeg(nseg);
          const inactive = audioRefs[1 - newActive].current;
          if (inactive) { inactive.src = `${BACKEND_URL}${nseg.segment_url}`; inactive.load(); }
        }
      }, 100);
    } catch (e) {
      if (e?.response?.status === 429) {
        const d = e.response.data || {};
        if (d.skip_state) applySkipState(d.skip_state);
        else { setSkipResetIn(d.retry_after_sec || 0); setSkipUsed(d.used || skipLimit); }
        const retry = d.reset_in_sec || d.retry_after_sec || 0;
        toast.error(
          <span>
            {user.is_premium
              ? <>All {d.limit || skipLimit} skips used — next skip in {fmtCountdown(retry)}.</>
              : <>You've used your free skip — next skip in {fmtCountdown(retry)}.{" "}
                  <Link to="/pricing" style={{ color: "#ffd700", textDecoration: "underline" }}>
                    View Premium →
                  </Link></>}
          </span>,
          { duration: 6000 },
        );
        if (a) { try { await a.play(); setPlaying(true); } catch (_e) { /* */ } }
      } else {
        toast.error(e?.response?.data?.detail || "Could not skip");
      }
    } finally {
      setAdvancing(false);
    }
  };

  const doLogout = async () => {
    // Phase 15d.3 — hard-stop audio + clear store on logout.
    try {
      const { teardownAllAudio } = await import("@/store/audioElements");
      teardownAllAudio();
    } catch (_e) { /* */ }
    try { usePlayerStore.getState().reset(); } catch (_e) { /* */ }
    await logout();
    navigate("/login", { replace: true });
  };

  const handleShareBreak = async () => {
    if (creatingShare || !currentSeg) return;
    setCreatingShare(true);
    try {
      const r = await axios.post(`${API}/share/break`, { segment_id: currentSeg.segment_id });
      setShareModal(r.data);
      toast.success("Share link ready");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not create share");
    } finally {
      setCreatingShare(false);
    }
  };

  const inRJ = currentSeg && currentTime >= currentSeg.rj_start_sec;
  const isDuo = currentSeg?.rj_format === "duo";
  const duoLabel = isDuo && currentSeg?.rj_hosts?.length >= 2
    ? `${currentSeg.rj_hosts[0].name} × ${currentSeg.rj_hosts[1].name}`
    : null;
  const canShare = !!currentSeg && currentTime >= (currentSeg.rj_start_sec + 2);
  const skipExhausted = skipUsed >= skipLimit;
  const skipRemaining = Math.max(0, skipLimit - skipUsed);

  if (authLoading || !user) {
    return <div className="auth-loading"><Loader2 className="spin" size={28} /></div>;
  }

  // Phase 15c — only mount the right rail when the viewport is genuinely
  // desktop. CSS `hidden lg:flex` was hiding visually but kept the rail in
  // the DOM (screen readers and tests still saw it). Gating the mount on
  // viewport keeps it out of the DOM at <1024px entirely.
  // (vp + showRail are computed at the top of the component.)
  return (
    <div className="radio-page-v2"
              data-testid="radio-split-root">
      <div className="radio-shell">
      <Toaster theme="dark" position="bottom-right" richColors />
      <ReactivationBanner />
      <RjActionCard user={user} />

      {audioWarming && (
        <div className="audio-warming-banner" data-testid="audio-warming-banner"
                  role="status"
                  style={{
                    display: "flex", alignItems: "center", gap: 12,
                    margin: "0 0 14px", padding: "12px 16px", borderRadius: 14,
                    background: "linear-gradient(90deg, rgba(245,158,11,0.16), rgba(245,158,11,0.05))",
                    border: "1px solid rgba(245,158,11,0.35)",
                  }}>
          <Loader2 size={18} className="spin" color="#f59e0b" style={{ flexShrink: 0 }} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, color: "#f7c948", fontSize: 14 }}>
              Audio engine warming up
            </div>
            <div style={{ color: "#cbb48a", fontSize: 12, marginTop: 2 }}>
              We're getting your station ready — this only takes a moment. Your music starts right after.
            </div>
          </div>
          <button type="button"
                        data-testid="audio-warming-retry"
                        onClick={() => { setAudioWarming(false); startRadio(); }}
                        disabled={starting}
                        style={{
                          display: "inline-flex", alignItems: "center", gap: 6,
                          padding: "8px 14px", borderRadius: 999, border: "none",
                          background: "#f59e0b", color: "#1a1205",
                          fontWeight: 700, fontSize: 13, flexShrink: 0,
                          cursor: starting ? "default" : "pointer",
                          opacity: starting ? 0.6 : 1,
                        }}>
            <RefreshCw size={14} className={starting ? "spin" : ""} /> Retry
          </button>
        </div>
      )}

      <header className="radio-header" data-testid="radio-header">
        <div className="radio-brand">
          <span className="dot" />
          {user.market === "dfw" ? (
            <h1 data-testid="brand-funasia">FunAsia <span className="dxb">AI Radio</span></h1>
          ) : (
            <BigFmBrand variant="lockup" testId="brand-bigfm" />
          )}
        </div>
        <div className="radio-meta">
          <span className="chip mono" data-testid="location-chip">
            <MapPin size={11} /> {user.market === "dfw" ? "NOW IN DFW" : `NOW IN ${(geoCity || "Global").toUpperCase()}`}
          </span>
          {user.role === "admin" && (
            <Link to="/admin" className="back-link mono" data-testid="admin-link">ADMIN →</Link>
          )}
          <div className="radio-avatar-wrap">
            <button type="button" className={`radio-avatar-btn ${user.is_premium ? "is-premium" : ""}`}
                    onClick={() => setMenuOpen((o) => !o)}
                    aria-label="Account menu" data-testid="avatar-menu-btn">
              {user.picture
                ? <img src={user.picture} alt={user.name} />
                : <span>{(user.name || user.email).slice(0, 1).toUpperCase()}</span>}
              {user.is_premium && (
                <span className="avatar-vip-ring" aria-hidden="true">
                  <Crown size={10} />
                </span>
              )}
            </button>
            {menuOpen && (
              <div className="avatar-menu" data-testid="avatar-menu">
                <div className="menu-head">
                  <div className="name">
                    {user.name}
                    {user.is_premium && (
                      <span className="menu-vip-tag mono" data-testid="menu-vip-tag">
                        <Crown size={9} /> VIP
                      </span>
                    )}
                  </div>
                  <div className="email">{user.email}</div>
                </div>
                <Link to="/profile" className="menu-item" data-testid="menu-profile-link"
                      onClick={() => setMenuOpen(false)}>
                  <UserIcon size={14} /> Profile &amp; preferences
                </Link>
                <Link to="/wallet" className="menu-item" data-testid="menu-wallet-link"
                      onClick={() => setMenuOpen(false)}>
                  <Coins size={14} /> BigPoints wallet
                </Link>
                <Link to="/passport" className="menu-item" data-testid="menu-passport-link"
                      onClick={() => setMenuOpen(false)}>
                  <Award size={14} /> Social Passport
                </Link>
                <Link to="/lobbies" className="menu-item" data-testid="menu-lobbies-link"
                      onClick={() => setMenuOpen(false)}>
                  <Users size={14} /> Lobbies · listen together
                </Link>
                <Link to="/play-and-win" className="menu-item" data-testid="menu-paw-link"
                      onClick={() => setMenuOpen(false)}>
                  <Sparkles size={14} /> Play &amp; Win</Link>
                <Link to="/billing" className="menu-item" data-testid="menu-billing-link"
                      onClick={() => setMenuOpen(false)}>
                  <Crown size={14} /> Billing &amp; plans
                </Link>
                {user.is_premium ? (
                  <Link to="/profile#billing" className="menu-item" data-testid="menu-manage-billing"
                        onClick={() => setMenuOpen(false)}>
                    <Crown size={14} /> Manage subscription
                  </Link>
                ) : (
                  <Link to="/pricing" className="menu-item is-premium-cta" data-testid="menu-go-premium"
                        onClick={() => setMenuOpen(false)}>
                    <Crown size={14} /> Go Premium · $12/yr
                  </Link>
                )}
                {user.role === "admin" && (
                  <Link to="/admin" className="menu-item" data-testid="menu-admin-link"
                        onClick={() => setMenuOpen(false)}>
                    <Shield size={14} /> Admin catalog
                  </Link>
                )}
                <div className="menu-divider" />
                <button type="button" className="menu-item danger" onClick={doLogout}
                        data-testid="menu-logout-btn">
                  <LogOut size={14} /> Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      <div className="radio-tag mono" data-testid="radio-tag">DIL SE · {(geoCity || "GLOBAL").toUpperCase()} SE</div>

      {channels.length > 0 && (
        <ChannelSwitcher
          channels={channels}
          activeSlug={activeChannel}
          switching={switching}
          isPremium={!!user.is_premium}
          onLocked={(ch) => {
            // Phase 10c — show gating modal with the channel's access detail
            setGate({ access: ch.access, channel: ch });
          }}
          onSwitch={(slug, ch) => {
            // Free channels — go directly; backend access check is still
            // the source of truth (handled in switchChannel 403 path).
            sessionId ? switchChannel(slug) : setActiveChannel(slug);
          }}
        />
      )}

      {!sessionId ? (
        <div className="radio-launch" data-testid="radio-launch">
          <button
            className={`onair-button ${starting ? "is-loading" : ""}`}
            onClick={() => startRadio()} disabled={starting}
            data-testid="on-air-button" aria-label="Go on air"
          >
            <div className="onair-inner">
              {starting ? <Loader2 className="spin" size={48} strokeWidth={1.5} />
                        : <RadioIcon size={56} strokeWidth={1.3} />}
              <div className="onair-label">
                <div className="big">{starting ? "TUNING IN…" : "ON AIR"}</div>
                <div className="small mono">
                  {starting ? "PHIR MILTE HAIN" :
                   activeChannel ? `TAP TO START · ${(channels.find(c => c.slug === activeChannel)?.name || "").toUpperCase()}` :
                   "TAP TO START · NON-STOP RADIO"}
                </div>
              </div>
            </div>
            <div className="ring r1" /><div className="ring r2" /><div className="ring r3" />
          </button>
          <p className="launch-sub" data-testid="launch-sub">
            Welcome back, {user.name.split(" ")[0]}. Pick a channel above, then tap ON AIR.
          </p>
        </div>
      ) : (
        <div className="radio-deck" data-testid="radio-deck">
          <div className="np-card">
            <div className="np-status" data-testid="np-status">
              <span className={`np-pulse ${inRJ ? "is-rj" : ""}`} />
              {inRJ ? (
                <span>
                  <span className="mono on-air-tag">
                    {isDuo ? "BANTER" : `RJ ${currentSeg?.rj_voice_name?.toUpperCase()}`}
                  </span> · LIVE BREAK
                  {isDuo && (
                    <span className="duo-badge mono" data-testid="duo-badge">
                      <Users size={11} /> DUO
                    </span>
                  )}
                </span>
              ) : (
                <span>
                  <span className="mono on-air-tag">ON AIR</span> · NOW PLAYING
                  {currentSeg?.channel_name && (
                    <span className="np-channel-tag mono" data-testid="np-channel-tag">
                      {currentSeg.channel_name.toUpperCase()}
                    </span>
                  )}
                </span>
              )}
            </div>
            {duoLabel && (
              <div className="duo-hosts mono" data-testid="duo-hosts">
                Hosts on this break: <b>{duoLabel}</b>
              </div>
            )}
            <div className="np-track" data-testid="np-track">
              <div className="np-title">{currentSeg?.track_title || "—"}</div>
              <div className="np-artist">{currentSeg?.track_artist || ""}</div>
            </div>

            <div className="seg-bar" data-testid="seg-bar">
              <div className="seg-track-area" style={{ width: `${(currentSeg?.rj_start_sec || 0) / (currentSeg?.duration_sec || 1) * 100}%` }} />
              <div className="seg-rj-area" style={{
                left: `${(currentSeg?.rj_start_sec || 0) / (currentSeg?.duration_sec || 1) * 100}%`,
                width: `${100 - (currentSeg?.rj_start_sec || 0) / (currentSeg?.duration_sec || 1) * 100}%`
              }} />
              <div className="seg-head" style={{ left: `${(currentTime / (duration || 1)) * 100}%` }} />
            </div>
            <div className="seg-times mono" data-testid="seg-times">
              <span>{fmt(currentTime)}</span><span>{fmt(duration)}</span>
            </div>

            <div className="controls-row">
              <button className="ctrl-btn primary" onClick={togglePlay}
                      data-testid="play-pause-btn" aria-label={playing ? "Pause" : "Play"}>
                {playing ? <Pause size={22} fill="white" /> : <Play size={22} fill="white" style={{ marginLeft: 3 }} />}
              </button>
              <button className="ctrl-btn ghost"
                      onClick={skip}
                      disabled={advancing || skipExhausted}
                      data-testid="skip-btn"
                      title={skipExhausted ? `Next skip in ${fmtCountdown(skipCountdown)}` : "Skip"}
                      aria-label="Skip">
                {advancing ? <Loader2 size={18} className="spin" /> : <SkipForward size={18} />}
                <span className="lbl">
                  {advancing ? "Switching…" :
                   skipExhausted ? `Next skip ${fmtCountdown(skipCountdown)}` :
                   `Skip · ${skipRemaining} left`}
                </span>
              </button>
              <button
                className="ctrl-btn ghost share"
                onClick={handleShareBreak}
                disabled={!canShare || creatingShare}
                data-testid="share-break-btn"
                title={!canShare ? "Available after the break starts" : "Share this break"}
                aria-label="Share break"
              >
                {creatingShare ? <Loader2 size={16} className="spin" /> : <Share2 size={16} />}
                <span className="lbl">Share break</span>
              </button>
              <button
                className={`ctrl-btn ghost icon-only ${fbSent === "like" ? "is-active" : ""}`}
                onClick={() => sendFeedback("like")}
                disabled={!currentSeg}
                data-testid="radio-like-btn"
                title="Like this — play more like it"
                aria-label="Like this track">
                <ThumbsUp size={16} fill={fbSent === "like" ? "currentColor" : "none"} />
              </button>
              <button
                className={`ctrl-btn ghost icon-only ${fbSent === "less" ? "is-active" : ""}`}
                onClick={() => sendFeedback("less")}
                disabled={!currentSeg}
                data-testid="radio-less-btn"
                title="Less like this"
                aria-label="Less like this track">
                <ThumbsDown size={16} fill={fbSent === "less" ? "currentColor" : "none"} />
              </button>
              <div className="vol-wrap">
                <button className="ctrl-btn ghost icon-only" onClick={() => setMuted((m) => !m)}
                        data-testid="mute-btn" aria-label="Mute">
                  {muted || volume === 0 ? <VolumeX size={16} /> : <Volume2 size={16} />}
                </button>
                <input className="vol-slider" type="range" min={0} max={1} step={0.01}
                       value={muted ? 0 : volume}
                       onChange={(e) => { setVolume(parseFloat(e.target.value)); setMuted(false); }}
                       data-testid="volume-slider" />
              </div>
            </div>

            <div className="skip-meta mono" data-testid="skip-meta">
              <Clock size={11} />
              {skipExhausted
                ? <>{user.is_premium ? `ALL ${skipLimit} SKIPS USED` : "FREE SKIP USED"} · NEXT IN <b>{fmtCountdown(skipCountdown)}</b></>
                : <>{skipUsed}/{skipLimit} SKIPS USED · 1H ROLLING{user.is_premium ? <> · <Crown size={11} /> PREMIUM</> : null}</>
              }
            </div>

            {!user.is_premium && skipExhausted && (
              <Link to="/pricing" data-testid="skip-upsell-cue"
                    style={{
                      display: "flex", alignItems: "center", gap: 8,
                      marginTop: 10, padding: "10px 12px", borderRadius: 12,
                      background: "rgba(160,32,240,0.10)", border: "1px solid rgba(160,32,240,0.35)",
                      textDecoration: "none", color: "inherit",
                    }}>
                <Crown size={15} color="#ffd700" />
                <span style={{ fontSize: 12.5, lineHeight: 1.3 }}>
                  <b>6 skips an hour with Premium.</b> You're on {skipLimit} — next in {fmtCountdown(skipCountdown)}.
                </span>
                <span style={{ marginLeft: "auto", color: "#ffd700", fontWeight: 700, fontSize: 12.5, whiteSpace: "nowrap" }}>
                  View Premium →
                </span>
              </Link>
            )}

            {currentSeg?.rj_script && (
              <div className={`rj-bubble ${inRJ ? "active" : "dim"}`} data-testid="rj-bubble">
                <div className="rj-tag mono">
                  {isDuo
                    ? <>DUO BANTER · {duoLabel?.toUpperCase()}</>
                    : <>RJ {currentSeg.rj_voice_name?.toUpperCase()} · HINGLISH BREAK</>}
                </div>
                <p style={{ whiteSpace: isDuo ? "pre-line" : "normal" }}>
                  {currentSeg.rj_script}
                </p>
              </div>
            )}
          </div>

          {history.length > 1 && (
            <div className="history" data-testid="history-ticker">
              <div className="history-title mono">JUST PLAYED</div>
              <div className="history-list">
                {history.slice(0, -1).slice(-4).map((s, i) => (
                  <div className="history-row" key={s.segment_id} data-testid={`history-row-${i}`}>
                    <span className="title">{s.track_title}</span>
                    <span className="dim">— {s.track_artist}</span>
                    {s.rj_format === "duo" && (
                      <span className="duo-badge mono"><Users size={9} /> DUO</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Phase 15d.3 — <audio> elements removed from Radio.js.  They now
            live in <GlobalAudio /> (mounted at AppShell root) so the stream
            survives route navigation. */}

      {shareModal && (
        <ShareBreakModal share={shareModal} onClose={() => setShareModal(null)} />
      )}
      {sessionId && (
        <ActionCard sessionId={sessionId} currentSegmentId={currentSeg?.segment_id} isPremium={!!user?.is_premium} />
      )}

      {/* Phase 41 P1-interrupt — Community Radio strip below admin
            channels. Sources up to 10 community stations via the
            3-tier fallback endpoint (`/api/community/top_listened`).
            Each card routes to the full `/r/{slug}` StationPage. */}
      <CommunityRadioStrip limit={10} />

      <footer className="radio-foot">
        <span>FUUSIC · PHASE 3 · PREMIUM + BILLING</span>
        <span>Made for the Indian community in the UAE.</span>
      </footer>

      {gate && (
        <ChannelGateModal
          access={gate.access}
          channel={gate.channel}
          onClose={() => setGate(null)}
          onCta={(access) => {
            setGate(null);
            if (access?.upgrade_path === "premium") {
              navigate("/pricing");
            } else if (access?.upgrade_path === "earn_badges") {
              navigate("/passport");
            } else if (access?.cta?.href) {
              navigate(access.cta.href);
            }
          }}
        />
      )}
      </div>
      {/* Phase 15c — rail rendered only on desktop viewports. CSS in
            radio-page-v2.css plus useViewport here keep it out of the DOM
            below 1024px (mobile vertical player from 15b is unchanged). */}
      {showRail && (
        <div className="radio-rail-col" data-testid="radio-rail-col">
          <RadioRail
            user={user}
            currentChannel={channels.find((c) => c.slug === activeChannel) || null}
          />
        </div>
      )}
    </div>
  );
}
