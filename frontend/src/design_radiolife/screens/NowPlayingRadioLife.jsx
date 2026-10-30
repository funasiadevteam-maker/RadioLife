// Phase R.1 — Now Playing.  Consumes the existing PlayerStore state
// (channel, playing, artwork) and RJ segment info.  No new player logic —
// this is purely presentation.
import React, { useEffect, useRef, useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import axios from "axios";
import { ArrowLeft, Play, Pause, SkipForward, SkipBack, Sparkles,
              MapPin, Ticket, Zap, Mic, Heart, Scissors, X, Loader2,
              Check, Globe, Users } from "lucide-react";
import { API } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { RLBadge } from "../DesignSystem";
import TalkToFunAI from "@/FunAI/TalkToFunAI";
import RjPersonalityPicker from "@/FunAI/RjPersonalityPicker";
import FunAiMemory from "@/FunAI/FunAiMemory";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

// Clip the last 30s of FUUSIC's own AI-radio audio and share it to the wall.
function ClipMoment({ channelSlug, channelName, channelLogo, audioUrl, onClose }) {
  const [comment, setComment] = useState("");
  const [visibility, setVisibility] = useState("public");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState(null);
  const idemRef = useRef(`segclip_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  const audioSrc = !audioUrl ? null
    : (audioUrl.startsWith("http") ? audioUrl : `${BACKEND_URL}${audioUrl}`);

  const share = async () => {
    setBusy(true); setErr(null);
    try {
      await axios.post(`${API}/radio/clips/share-segment`, {
        channel_slug: channelSlug, channel_name: channelName, channel_logo: channelLogo,
        segment_audio_url: audioUrl, comment: comment.trim(), visibility,
        duration_seconds: 30, idempotency_key: idemRef.current,
      });
      setDone(true);
      setTimeout(onClose, 1100);
    } catch (e) {
      setErr(e?.response?.data?.detail?.message || "Couldn't share your clip — try again.");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="rl-clip-modal" onClick={onClose}
      className="fixed inset-0 z-[120] flex items-end sm:items-center justify-center p-0 sm:p-4"
      style={{ background: "rgba(10,8,20,.6)", backdropFilter: "blur(4px)" }}>
      <div onClick={(e) => e.stopPropagation()}
        className="w-full sm:max-w-md bg-white rounded-t-3xl sm:rounded-3xl p-5 shadow-2xl">
        <div className="flex items-center justify-between mb-3">
          <div className="font-black text-lg text-slate-900 flex items-center gap-2">
            <Scissors size={18} className="text-purple-600" /> Clip a Moment
          </div>
          <button onClick={onClose} data-testid="rl-clip-close"
            className="w-9 h-9 rounded-full bg-slate-100 text-slate-500 flex items-center justify-center">
            <X size={18} />
          </button>
        </div>
        {done ? (
          <div className="py-10 text-center" data-testid="rl-clip-done">
            <div className="w-14 h-14 rounded-full bg-purple-100 text-purple-600 mx-auto flex items-center justify-center mb-3">
              <Check size={28} />
            </div>
            <div className="font-black text-slate-900">Clip shared to your wall!</div>
          </div>
        ) : (
          <>
            <div className="flex items-center gap-3 mb-3">
              {channelLogo
                ? <img src={channelLogo} alt="" className="w-11 h-11 rounded-xl object-cover" />
                : <div className="w-11 h-11 rounded-xl bg-purple-100 flex items-center justify-center text-purple-600"><Sparkles size={20} /></div>}
              <div className="min-w-0">
                <div className="font-black text-slate-900 truncate">{channelName || "FUUSIC Radio"}</div>
                <div className="text-xs text-slate-500">The last 30 seconds you just heard</div>
              </div>
            </div>
            {audioSrc && <audio src={audioSrc} controls preload="none" className="w-full mb-3" data-testid="rl-clip-audio" />}
            <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={3}
              data-testid="rl-clip-comment" placeholder="Say something about this moment…"
              className="w-full rounded-xl border border-slate-200 p-3 text-sm text-slate-900 outline-none mb-3 resize-none" />
            <div className="flex gap-2 mb-3">
              {[{ k: "public", I: Globe, l: "Public" }, { k: "friends", I: Users, l: "Friends" }].map(({ k, I, l }) => (
                <button key={k} onClick={() => setVisibility(k)} data-testid={`rl-clip-vis-${k}`}
                  className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-bold border ${visibility === k ? "bg-purple-600 text-white border-purple-600" : "bg-white text-slate-600 border-slate-200"}`}>
                  <I size={14} /> {l}
                </button>
              ))}
            </div>
            {err && <div data-testid="rl-clip-error" className="text-sm text-red-600 mb-2">{err}</div>}
            <button onClick={share} disabled={busy || !audioUrl} data-testid="rl-clip-submit"
              className="w-full rounded-full py-3 font-black text-white flex items-center justify-center gap-2 disabled:opacity-60"
              style={{ background: "linear-gradient(90deg,#A020F0,#EC4899)" }}>
              {busy ? <><Loader2 size={16} className="animate-spin" /> Sharing…</> : <><Scissors size={16} /> Share to My Wall</>}
            </button>
          </>
        )}
      </div>
    </div>
  );
}

export default function NowPlayingRadioLife() {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  // Overlay is outside <Routes>; parse slug from pathname or ?ch= fallback.
  let urlSlug = "";
  if (pathname.startsWith("/radio/station/")) {
    urlSlug = decodeURIComponent(pathname.slice("/radio/station/".length)
                                                .split("/")[0]);
  } else {
    const params = new URLSearchParams(search);
    urlSlug = params.get("ch") || "";
  }
  const [channel, setChannel] = useState(null);
  const [persona, setPersona] = useState(null);
  const playing = usePlayerStore((s) => s.playing);
  const setPlaying = usePlayerStore((s) => s.setPlaying);
  const currentSeg = usePlayerStore((s) => s.currentSeg);
  const advancing = usePlayerStore((s) => s.advancing);
  const skipUsed = usePlayerStore((s) => s.skipUsed);
  const skipLimit = usePlayerStore((s) => s.skipLimit);
  const sessionId = usePlayerStore((s) => s.sessionId);
  const activeChannelSlug = usePlayerStore((s) => s.activeChannel);
  const activeChannelName = usePlayerStore((s) => s.activeChannelName);
  const activeChannelThumb = usePlayerStore((s) => s.activeChannelThumb);
  const chSlug = urlSlug || activeChannelSlug || "";

  const [following, setFollowing] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);
  const [clipOpen, setClipOpen] = useState(false);
  const [talkOpen, setTalkOpen] = useState(false);
  const [radioMsg, setRadioMsg] = useState(null);

  useEffect(() => {
    if (!chSlug) { setFollowing(false); return; }
    let on = true;
    axios.get(`${API}/radio/channels/${encodeURIComponent(chSlug)}/follow-status`)
      .then((r) => { if (on) setFollowing(!!r.data?.following); })
      .catch(() => { if (on) setFollowing(false); });
    return () => { on = false; };
  }, [chSlug]);

  const toggleFollow = async () => {
    if (!chSlug || followBusy) return;
    setFollowBusy(true);
    const next = !following;
    setFollowing(next);
    try {
      await axios.post(
        `${API}/radio/channels/${encodeURIComponent(chSlug)}/${next ? "follow" : "unfollow"}`,
        { channel_name: channel?.name, channel_logo: artUrl });
    } catch (_e) {
      setFollowing(!next);
    } finally {
      setFollowBusy(false);
    }
  };

  useEffect(() => {
    if (!chSlug) return;
    axios.get(`${API}/channels`).then((r) => {
      const c = (r.data?.channels || []).find((x) => x.slug === chSlug);
      setChannel(c || null);
    }).catch(() => setChannel(null));
  }, [chSlug]);

  // Phase D — resolve station's assigned host persona.
  useEffect(() => {
    if (!chSlug) { setPersona(null); return; }
    let cancelled = false;
    axios.get(`${API}/rj/stations/${encodeURIComponent(chSlug)}/personas`)
      .then((r) => { if (!cancelled)
        setPersona((r.data?.items || [])[0] || null); })
      .catch(() => { if (!cancelled) setPersona(null); });
    return () => { cancelled = true; };
  }, [chSlug]);

  const rawThumb = channel?.thumbnail_url || activeChannelThumb;
  const artUrl = rawThumb
    ? (rawThumb.startsWith("http") ? rawThumb : `${BACKEND_URL}${rawThumb}`) : null;

  return (
    <div className="min-h-screen relative overflow-hidden" data-testid="rl-now-playing">
      {/* Gradient background */}
      <div className="absolute inset-0 pointer-events-none"
                style={{ background: "linear-gradient(180deg, #A020F0 0%, #EC4899 45%, #FAF7FE 100%)" }} />
      <div className="relative px-5 pt-4 pb-24">
        {/* Header */}
        <div className="flex items-center justify-between">
          <button
            type="button"
            onClick={() => navigate(-1)}
            data-testid="rl-back-btn"
            className="w-10 h-10 rounded-full bg-white/25 backdrop-blur
                                text-white flex items-center justify-center
                                hover:bg-white/40 transition-colors">
            <ArrowLeft size={18} />
          </button>
          <div className="text-white/85 text-[11px] font-semibold uppercase tracking-widest">
            Now Playing
          </div>
          <button
            type="button"
            onClick={toggleFollow}
            disabled={followBusy || !chSlug}
            data-testid="rl-follow-show-btn"
            aria-pressed={following}
            className={`h-10 px-3 rounded-full flex items-center gap-1.5 text-xs font-black
                        backdrop-blur transition-colors disabled:opacity-60 ${following
                          ? "bg-white text-purple-700"
                          : "bg-white/25 text-white hover:bg-white/40"}`}>
            <Heart size={15} fill={following ? "currentColor" : "none"} />
            {following ? "Following" : "Follow"}
          </button>
        </div>

        {/* Artwork */}
        <div className="mt-6 mx-auto w-64 h-64 rounded-3xl overflow-hidden
                                shadow-2xl shadow-black/30 bg-white/10 backdrop-blur
                                flex items-center justify-center relative">
          {artUrl ? (
            <img src={artUrl} alt={channel?.name}
                    className="absolute inset-0 w-full h-full object-cover"
                    onError={(e)=>{e.currentTarget.style.display="none";}} />
          ) : (
            <Sparkles size={64} className="text-white/60" />
          )}
        </div>

        {/* Title */}
        <div className="mt-6 text-center">
          <div className="text-white font-black text-2xl tracking-tight">
            {channel?.name || activeChannelName || "Now Playing"}
          </div>
          <div className="text-white/70 text-sm mt-1">
            {channel?.tagline || "Personalised for you"}
          </div>
        </div>

        {/* Earning-active chip */}
        <div className="mt-4 flex justify-center">
          <RLBadge tone="amber" className="bg-white/25 text-white border border-white/25
                                                              backdrop-blur"
                          data-testid="rl-earning-chip">
            <Zap size={11} /> Earning +5 pts/min
          </RLBadge>
        </div>

        {/* Phase D — Hosted-by persona chip. */}
        {persona && (
          <div className="mt-3 flex justify-center">
            <div
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full
                                          bg-white/25 border border-white/30 text-white
                                          text-[11px] font-semibold backdrop-blur"
              title={persona.tagline || persona.description
                                || `Hosted by ${persona.name}`}
              data-testid="rl-now-playing-persona-chip"
              data-persona-id={persona.id}>
              <Mic size={11} />
              Hosted by {persona.name}
            </div>
          </div>
        )}

        {/* Controls */}
        <div className="mt-8 flex items-center justify-center gap-8">
          <button
            type="button"
            disabled
            title="Radio plays forward only"
            className="w-12 h-12 rounded-full bg-white/20 text-white
                                flex items-center justify-center backdrop-blur
                                opacity-40 cursor-not-allowed"
            data-testid="rl-prev-btn"
            aria-label="Previous (unavailable on radio)">
            <SkipBack size={20} />
          </button>
          <button
            type="button"
            onClick={() => setPlaying(!playing)}
            data-testid="rl-playpause-btn"
            aria-label={playing ? "Pause" : "Play"}
            className="w-16 h-16 rounded-full bg-white text-purple-700
                                flex items-center justify-center shadow-xl
                                hover:scale-105 active:scale-95 transition-transform">
            {playing
              ? <Pause size={26} strokeWidth={2.5} fill="currentColor" />
              : <Play size={26} strokeWidth={2.5} fill="currentColor" />}
          </button>
          <button
            type="button"
            onClick={() => {
              if (advancing || !sessionId) return;
              window.dispatchEvent(new CustomEvent("bigfm:player:skip"));
            }}
            disabled={advancing || !sessionId || (skipLimit > 0 && skipUsed >= skipLimit)}
            data-testid="rl-next-btn"
            aria-label="Next"
            title={skipLimit > 0 && skipUsed >= skipLimit ? "Skip limit reached" : "Next"}
            className="w-12 h-12 rounded-full bg-white/20 text-white
                                flex items-center justify-center hover:bg-white/30
                                transition-colors backdrop-blur disabled:opacity-50">
            {advancing
              ? <Loader2 size={20} className="animate-spin" />
              : <SkipForward size={20} />}
          </button>
        </div>

        {/* Clip & Share the live moment (FUUSIC-owned audio) */}
        <div className="mt-8 flex justify-center">
          <button
            type="button"
            onClick={() => setClipOpen(true)}
            disabled={!currentSeg?.audio_url}
            data-testid="rl-clip-btn"
            title={currentSeg?.audio_url ? "Clip the last 30 seconds" : "Start the station to clip"}
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full
                        bg-white/95 text-purple-700 font-black shadow-md
                        hover:shadow-lg active:scale-95 transition-all
                        disabled:opacity-50">
            <Scissors size={16} /> Clip last 30s
          </button>
        </div>

        {/* Talk to Fun AI — voice RJ on the player (Phase 2) */}
        <div className="mt-4 max-w-sm mx-auto w-full">
          <FunAiMemory dark accent="#22d3ee" testIdPrefix="rl-memory" />
          <RjPersonalityPicker dark accent="#22d3ee" testIdPrefix="rl-rj-personality" />
        </div>
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => setTalkOpen(true)}
            data-testid="rl-talk-funai-btn"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-full
                        bg-gradient-to-r from-cyan-500 to-fuchsia-500 text-white
                        font-black shadow-md hover:shadow-lg active:scale-95 transition-all">
            <Mic size={16} /> Talk to Fun AI
          </button>
        </div>

        {/* Secondary CTAs */}
        <div className="mt-8 space-y-3">
          <Link
            to="/pay?intent=daily_code"
            data-testid="rl-claim-daily-code"
            className="flex items-center gap-3 p-4 bg-white/95 rounded-2xl
                                shadow-md hover:shadow-lg transition-all">
            <div className="w-10 h-10 rounded-xl bg-amber-100 flex items-center
                                    justify-center text-amber-700">
              <Ticket size={18} />
            </div>
            <div className="flex-1">
              <div className="font-bold text-slate-900">Claim daily code</div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider">
                Ships in R.2 — coming soon
              </div>
            </div>
            <span className="text-[11px] font-semibold text-purple-700">→</span>
          </Link>
          <Link
            to="/commute"
            data-testid="rl-nearby-deals-cta"
            className="flex items-center gap-3 p-4 bg-white/95 rounded-2xl
                                shadow-md hover:shadow-lg transition-all">
            <div className="w-10 h-10 rounded-xl bg-purple-100 flex items-center
                                    justify-center text-purple-700">
              <MapPin size={18} />
            </div>
            <div className="flex-1">
              <div className="font-bold text-slate-900">Nearby deals</div>
              <div className="text-[11px] text-slate-500 uppercase tracking-wider">
                Offers along your route
              </div>
            </div>
            <span className="text-[11px] font-semibold text-purple-700">→</span>
          </Link>
        </div>

        {clipOpen && (
          <ClipMoment
            channelSlug={chSlug}
            channelName={channel?.name}
            channelLogo={artUrl}
            audioUrl={currentSeg?.audio_url}
            onClose={() => setClipOpen(false)}
          />
        )}

        {talkOpen && (
          <TalkToFunAI
            dark
            surface="player"
            station={{ slug: chSlug,
                       name: channel?.name || activeChannelName || "FUUSIC Radio",
                       type: "managed" }}
            modeLabel={channel?.name || activeChannelName || "FUUSIC Radio"}
            onRadioAction={(out) => {
              const showMsg = (text, onUndo) => {
                setRadioMsg({ text, onUndo });
                setTimeout(() => setRadioMsg(null), 9000);
              };
              if (!out?.allowed) {
                showMsg(out?.reason || "That change isn't available on radio.");
                return;
              }
              if (out.target) {
                const prev = chSlug;
                navigate(`/radio/station/${encodeURIComponent(out.target)}`);
                showMsg("Fun AI switched your station.", () => {
                  if (prev) navigate(`/now-playing?ch=${encodeURIComponent(prev)}`);
                  else navigate(-1);
                  setRadioMsg(null);
                });
              } else if (out.applied && Object.keys(out.applied).length) {
                const fields = Object.keys(out.applied).filter((k) => out.applied[k]);
                const desc = fields.map((k) => `${k.replace(/_/g, " ")} → ${out.applied[k]}`).join(", ");
                showMsg(`Fun AI set ${desc}.`, async () => {
                  try {
                    await axios.post(`${BACKEND_URL}/api/fun-ai/radio/undo`,
                      { fields }, { withCredentials: true });
                  } catch (_e) { /* noop */ }
                  setRadioMsg(null);
                });
              } else {
                showMsg("Done.");
              }
            }}
            onClose={() => setTalkOpen(false)}
            onStatusChange={() => {}}
          />
        )}

        {radioMsg && (
          <div data-testid="rl-radio-action-msg"
               className="fixed left-1/2 -translate-x-1/2 bottom-24 z-[1100] max-w-[92vw]
                          flex items-center gap-3 px-4 py-2.5 rounded-xl bg-slate-900 text-white text-sm shadow-xl">
            <span>{radioMsg.text}</span>
            {radioMsg.onUndo && (
              <button data-testid="rl-radio-undo" onClick={radioMsg.onUndo}
                      className="underline font-bold text-cyan-300 shrink-0">
                Undo
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
