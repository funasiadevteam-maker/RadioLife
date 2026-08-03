// Phase R.1 — Now Playing.  Consumes the existing PlayerStore state
// (channel, playing, artwork) and RJ segment info.  No new player logic —
// this is purely presentation.
import React, { useEffect, useState } from "react";
import { useNavigate, useLocation, Link } from "react-router-dom";
import axios from "axios";
import { ArrowLeft, Play, Pause, SkipForward, SkipBack, Sparkles,
              MapPin, Ticket, Zap, Mic } from "lucide-react";
import { API } from "@/AuthContext";
import { usePlayerStore } from "@/store/usePlayerStore";
import { RLCard, RLBadge } from "../DesignSystem";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";

export default function NowPlayingRadioLife() {
  const navigate = useNavigate();
  const { pathname, search } = useLocation();
  // Overlay is outside <Routes>; parse slug from pathname or ?ch= fallback.
  let chSlug = "";
  if (pathname.startsWith("/radio/station/")) {
    chSlug = decodeURIComponent(pathname.slice("/radio/station/".length)
                                                .split("/")[0]);
  } else {
    const params = new URLSearchParams(search);
    chSlug = params.get("ch") || "";
  }
  const [channel, setChannel] = useState(null);
  const [persona, setPersona] = useState(null);
  const playing = usePlayerStore((s) => s.playing);
  const setPlaying = usePlayerStore((s) => s.setPlaying);

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

  const artUrl = channel?.thumbnail_url
    ? `${BACKEND_URL}${channel.thumbnail_url}` : null;

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
          <div className="w-10 h-10" />
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
            {channel?.name || "Loading…"}
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
            className="w-12 h-12 rounded-full bg-white/20 text-white
                                flex items-center justify-center hover:bg-white/30
                                transition-colors backdrop-blur"
            data-testid="rl-prev-btn"
            aria-label="Previous">
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
            className="w-12 h-12 rounded-full bg-white/20 text-white
                                flex items-center justify-center hover:bg-white/30
                                transition-colors backdrop-blur"
            data-testid="rl-next-btn"
            aria-label="Next">
            <SkipForward size={20} />
          </button>
        </div>

        {/* Secondary CTAs */}
        <div className="mt-10 space-y-3">
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
      </div>
    </div>
  );
}
