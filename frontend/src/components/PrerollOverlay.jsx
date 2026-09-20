/** Phase 42-B — Pre-roll ad overlay.
 *
 *  Modal that plays the pre-roll audio + shows companion creative
 *  before the imported live stream begins.  Self-contained: owns its
 *  own <audio> element, fires lifecycle events to the impression API,
 *  and signals the parent via `onComplete` / `onSkip` callbacks.
 *
 *  Skip button is hidden for the first 5 seconds (standard pre-roll UX).
 */
import React, { useEffect, useRef, useState, useCallback } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Play, SkipForward, ExternalLink, ShoppingBag, Volume2, Sparkles,
} from "lucide-react";
import { API } from "@/AuthContext";

export default function PrerollOverlay({
  impressionId, ad, onComplete, onSkip,
  chainPosition, chainCount,
}) {
  const audioRef = useRef(null);
  const [elapsed, setElapsed] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [walletSaving, setWalletSaving] = useState(false);
  const [walletSaved, setWalletSaved] = useState(false);
  // Phase 42-B2 hotfix — when the browser blocks autoplay (Chrome /
  // Safari / Firefox NotAllowedError), drop into a tap-to-start state
  // so the user can resume with a single gesture.
  const [needsGesture, setNeedsGesture] = useState(false);
  const startedRef = useRef(false);
  const terminalFiredRef = useRef(false);
  // Sub-Phase 42-B2 — companion creative renders ONLY when the ad has
  // an attached offer.  Audio-only ads (FUUSIC house spots + SSP fill)
  // show just sponsor + progress + skip.
  const hasOffer = !!ad?.attached_offer_id;

  // Fire impression events.  Sync variant is for unload — uses
  // navigator.sendBeacon so the event survives page-teardown.
  const fireEvent = useCallback(async (event_type, metadata) => {
    try {
      await axios.post(
        `${API}/live-radio/preroll/${impressionId}/event`,
        { event_type, metadata });
    } catch (_e) { /* swallow */ }
  }, [impressionId]);

  const fireEventBeacon = useCallback((event_type) => {
    try {
      const blob = new Blob(
        [JSON.stringify({ event_type })],
        { type: "application/json" });
      navigator.sendBeacon?.(
        // Phase 42-F.1 — `API` already includes `/api` (from AuthContext);
        // previous value produced `/api/api/...` and silently 404'd, so
        // pre-roll impression telemetry was being dropped.
        `${API}/live-radio/preroll/${impressionId}/event`, blob);
    } catch (_e) { /* swallow */ }
  }, [impressionId]);

  // ─── Autoplay on mount.  We invoke `play()` from JS so we can
  //      catch the browser's autoplay-policy rejection and surface a
  //      tap-to-start CTA when needed (Phase 42-B2 hotfix).
  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const p = el.play();
    if (p && typeof p.then === "function") {
      p.then(() => {
        setPlaying(true);
        setNeedsGesture(false);
        if (!startedRef.current) {
          startedRef.current = true;
          fireEvent("start");
        }
      }).catch((err) => {
        // NotAllowedError, NotSupportedError, AbortError — all map to
        // "user must gesture to start playback".  We don't silently
        // skip the ad — instead we render a CTA so the listener can
        // continue.  The skip button stays available either way.
        if (err && (err.name === "NotAllowedError"
                                  || err.name === "NotSupportedError"
                                  || err.name === "AbortError")) {
          setNeedsGesture(true);
        } else {
          setNeedsGesture(true);
        }
      });
    } else {
      // Synchronous play (old browsers) — assume it worked.
      setPlaying(true);
    }
  }, [fireEvent]);

  // ─── User-gesture fallback: explicit tap to start the ad audio.
  //      Because this is invoked inside a click handler, `play()` is
  //      now a direct user gesture and the browser must honor it.
  const handleTapToStart = useCallback(() => {
    const el = audioRef.current;
    if (!el) return;
    const p = el.play();
    if (p && typeof p.then === "function") {
      p.then(() => {
        setPlaying(true);
        setNeedsGesture(false);
        if (!startedRef.current) {
          startedRef.current = true;
          fireEvent("start");
        }
      }).catch(() => {
        // Even with a gesture, playback failed — keep the CTA so the
        // user can try again (or hit Skip).
        setNeedsGesture(true);
      });
    }
  }, [fireEvent]);

  // ─── Track elapsed time (used for progress bar only — no skip-gate).
  //      Only runs once playback has actually begun (`hasStarted`); this
  //      keeps the countdown silent while the tap-to-start CTA is up.
  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      const el = audioRef.current;
      if (el) setElapsed(Math.floor(el.currentTime));
    }, 250);
    return () => clearInterval(t);
  }, [playing]);

  const handleEnded = () => {
    if (terminalFiredRef.current) return;
    terminalFiredRef.current = true;
    fireEvent("complete");
    onComplete?.();
  };

  const handleSkip = useCallback(() => {
    if (terminalFiredRef.current) return;
    terminalFiredRef.current = true;
    fireEvent("skip");
    onSkip?.();
  }, [fireEvent, onSkip]);

  // ─── ESC key + page-unload skip.  Sub-Phase 42-B2 requirement: skip
  //      should always be one keystroke / one click away, and a
  //      navigated-away impression should still receive a terminal
  //      event so analytics aren't littered with `started` orphans.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape" || e.key === "Esc") {
        e.preventDefault();
        handleSkip();
      }
    };
    const onUnload = () => {
      if (terminalFiredRef.current) return;
      terminalFiredRef.current = true;
      fireEventBeacon("skip");
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("beforeunload", onUnload);
    window.addEventListener("pagehide", onUnload);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("beforeunload", onUnload);
      window.removeEventListener("pagehide", onUnload);
    };
  }, [handleSkip, fireEventBeacon]);

  const handleCompanionClick = () => {
    fireEvent("companion_click",
                          { cta_url: ad?.companion_cta_url });
    if (ad?.companion_cta_url) {
      window.open(ad.companion_cta_url, "_blank", "noopener");
    }
  };

  const handleWalletSave = async () => {
    setWalletSaving(true);
    try {
      const r = await axios.post(
        `${API}/live-radio/preroll/${impressionId}/save-to-wallet`,
        {}, { withCredentials: true });
      setWalletSaved(true);
      toast.success("Saved to your wallet", {
        description: r.data.idempotent
          ? "Already saved earlier — no duplicates created."
          : "Find it under Wallet → Coupons.",
      });
    } catch (e) {
      const code = e?.response?.data?.detail?.code;
      if (code === "no_offer_attached") {
        toast.error("This ad has nothing to save.");
      } else {
        toast.error("Sign in to save offers to your wallet.");
      }
    } finally { setWalletSaving(false); }
  };

  const duration = ad?.duration_sec || 15;
  const remaining = Math.max(0, duration - elapsed);
  // Sub-Phase 42-B2 — companion image renders ONLY when the ad has an
  // attached offer.  This is the consumer-facing rule: "popup is for
  // saving coupons; audio-only ads don't get visual real estate."
  const showCompanionImage = hasOffer && !!ad?.companion_image_url;

  return (
    <div
      data-testid="preroll-overlay"
      data-impression-id={impressionId}
      data-has-offer={hasOffer}
      data-ad-source={ad?.source || "local"}
      data-needs-gesture={needsGesture}
      data-has-started={playing}
      className="fixed inset-0 z-[120] flex items-center justify-center
                          bg-black/70 backdrop-blur-sm p-4"
    >
      <div className={`w-full ${hasOffer ? "max-w-md" : "max-w-sm"}
                                        rounded-2xl bg-slate-900
                                        border border-white/10 shadow-2xl overflow-hidden`}>
        {/* Sponsor strip — no skip countdown copy (42-B2 rule). */}
        <div className="px-4 py-2 flex items-center justify-between
                                bg-white/[0.03] border-b border-white/[0.06]">
          <span className="text-[10px] font-mono uppercase tracking-widest
                                          text-white/40 inline-flex items-center gap-1">
            <Sparkles size={10} className="text-amber-400" /> Sponsored
          </span>
          {/* Phase 42-F.4 — chain progress indicator (Ad X of N). */}
          {chainCount && chainCount > 1 && (
            <span
              data-testid="preroll-chain-progress"
              data-chain-position={chainPosition}
              data-chain-count={chainCount}
              className="text-[10px] font-mono uppercase tracking-widest
                                          text-amber-300/80">
              Ad {chainPosition} of {chainCount}
            </span>
          )}
          <span className="text-[10px] font-mono text-white/40"
                          data-testid="preroll-source-label">
            {ad?.source === "ssp_mocked" ? "SSP" : "Audio Ad"}
          </span>
        </div>

        {/* Tap-to-start CTA — Phase 42-B2 hotfix for autoplay-blocked
             browsers.  Shows when JS .play() rejected with
             NotAllowedError.  Click is a real user gesture so the
             retry succeeds. */}
        {needsGesture && !playing && (
          <button
            type="button"
            onClick={handleTapToStart}
            data-testid="preroll-tap-to-start"
            className="w-full px-4 py-3 flex items-center justify-center
                                gap-2 bg-cyan-400/15 hover:bg-cyan-400/25
                                border-b border-cyan-400/30 text-cyan-100
                                text-sm font-semibold transition-colors">
            <Play size={14} /> Tap to Play Ad &amp; Start Station
          </button>
        )}

        {/* Companion image — offer-gated. */}
        {showCompanionImage && (
          <button
            type="button"
            onClick={handleCompanionClick}
            data-testid="preroll-companion-image"
            className="block w-full aspect-video relative overflow-hidden
                                bg-slate-800 group">
            <img
              src={ad.companion_image_url}
              alt={ad.companion_cta_text || "Sponsored"}
              onError={(e) => { e.currentTarget.style.display = "none"; }}
              className="w-full h-full object-cover transition-transform
                                  duration-300 group-hover:scale-105" />
            <div className="absolute inset-0 bg-gradient-to-t
                                          from-slate-900/80 to-transparent" />
            {ad.companion_cta_text && (
              <div className="absolute bottom-3 left-4 right-4 text-left">
                <div className="text-sm font-semibold text-white drop-shadow">
                  {ad.companion_cta_text}
                </div>
                <div className="text-[11px] text-white/70 inline-flex
                                                items-center gap-1 mt-0.5">
                  <ExternalLink size={10} /> Tap to learn more
                </div>
              </div>
            )}
          </button>
        )}

        {/* Audio player */}
        <div className="p-4 space-y-3">
          <div className="flex items-center gap-3">
            <div data-testid="preroll-status-pill"
                          className={`w-12 h-12 rounded-full grid place-items-center
                                                  ${playing
                                                    ? "bg-cyan-400/20 text-cyan-300"
                                                    : "bg-cyan-400 text-slate-900"}`}>
              {playing ? <Volume2 size={18} /> : <Play size={18} />}
            </div>
            <div className="flex-grow min-w-0">
              <div className="text-sm font-semibold text-white truncate"
                                  data-testid="preroll-ad-name">
                {ad?.name || "Sponsored message"}
              </div>
              <div className="text-xs text-white/50 truncate">
                {ad?.advertiser_name || "FUUSIC Advertiser"}
              </div>
              {/* Progress bar */}
              <div className="mt-1.5 h-1 rounded-full bg-white/[0.06]
                                          overflow-hidden">
                <div
                  data-testid="preroll-progress"
                  className="h-full bg-cyan-400 transition-all duration-200"
                  style={{ width: `${Math.min(100, (elapsed / duration) * 100)}%` }} />
              </div>
              <div className="text-[10px] text-white/40 mt-0.5">
                Ad · {remaining}s remaining
              </div>
            </div>
          </div>

          {/* Action row */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            {hasOffer && (
              <button
                type="button"
                onClick={handleWalletSave}
                disabled={walletSaving || walletSaved}
                data-testid="preroll-wallet-save"
                data-saved={walletSaved}
                className="inline-flex items-center gap-1.5 px-3 h-8
                                    rounded-full text-xs font-medium
                                    bg-amber-400/15 text-amber-200 border
                                    border-amber-400/30 hover:bg-amber-400/25
                                    disabled:opacity-50 transition-colors">
                <ShoppingBag size={12} />
                {walletSaved ? "Saved to wallet ✓"
                                            : walletSaving ? "Saving…"
                                            : "Save offer to wallet"}
              </button>
            )}
            {hasOffer && ad?.companion_cta_url && (
              <button
                type="button"
                onClick={handleCompanionClick}
                data-testid="preroll-cta-btn"
                className="inline-flex items-center gap-1.5 px-3 h-8
                                    rounded-full text-xs text-white/70
                                    hover:text-white bg-white/[0.05]
                                    hover:bg-white/[0.10] border
                                    border-white/[0.08] transition-colors">
                Visit site <ExternalLink size={10} />
              </button>
            )}
            <div className="flex-grow" />
            <button
              type="button"
              onClick={handleSkip}
              data-testid="preroll-skip-btn"
              aria-label="Skip ad (Esc)"
              className="inline-flex items-center gap-1.5 px-3 h-8
                                  rounded-full text-xs font-medium
                                  text-white hover:bg-white/[0.10]
                                  bg-white/[0.06]
                                  border border-white/[0.10]
                                  transition-colors">
              <SkipForward size={12} />
              Skip Ad
            </button>
          </div>
        </div>

        <audio
          ref={audioRef}
          src={ad?.audio_url}
          preload="auto"
          data-testid="preroll-audio"
          onEnded={handleEnded}
          onError={() => {
            // Phase 42-B-redux.2 (2026-07-31) — auto-skip after 2 s
            // when the ad audio truly can't be loaded/decoded (e.g.
            // upstream creative URL rot: HTML placeholder returned
            // in place of the MP3).  Previously we did nothing here,
            // stranding every imported-station listener on the
            // overlay whenever the served ad had a broken audio_url.
            // We still fire a terminal "skip" impression event so
            // analytics see the failure and the ad-serving layer
            // can rotate the creative out.  Users who want the
            // companion CTA / wallet-save still have the manual
            // Skip button before the 2 s auto-skip fires.
            if (terminalFiredRef.current) return;
            setTimeout(() => {
              if (terminalFiredRef.current) return;
              terminalFiredRef.current = true;
              fireEvent("skip", { reason: "audio_load_error" });
              onSkip?.();
            }, 2000);
          }}
          onPlay={() => {
            setPlaying(true);
            setNeedsGesture(false);
            if (!startedRef.current) {
              startedRef.current = true;
              fireEvent("start");
            }
          }}
          onPause={() => setPlaying(false)} />
      </div>
    </div>
  );
}
