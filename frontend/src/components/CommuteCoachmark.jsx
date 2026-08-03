/**
 * Phase 18b — Commute 3-step coachmark tour.
 *
 * Renders into a React portal targeting `document.body` so it isn't
 * captured by transformed ancestors (which is what broke our initial
 * `position:fixed` attempt — the shell wrapper has a `transform` from
 * the slide-in animation, which re-roots fixed positioning).
 *
 * 3 steps with Next / Got it.  Setting `localStorage.commute_intro_seen`
 * to `"true"` permanently dismisses it.
 */
import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronRight, X, MapPin, Clock, Sparkles } from "lucide-react";

const STEPS = [
  {
    icon: MapPin,
    title:  "Tell us where you're headed",
    body:    "Drop a destination into the input below and we'll route you " +
                "through deals along the way.",
  },
  {
    icon: Clock,
    title:  "Pick when",
    body:    "Right now or schedule for later — we match offers to time of " +
                "day, so lunch deals show up at noon and not at midnight.",
  },
  {
    icon: Sparkles,
    title:  "Lunch deals, comfort food, Friday events",
    body:    "We surface 3 picks along your route. Save them to your wallet " +
                "or start driving in audio-first mode.",
  },
];


export default function CommuteCoachmark({ open, onDismiss }) {
  const [step, setStep] = useState(0);
  // When the host re-opens this (e.g. parent clears localStorage), reset.
  useEffect(() => { if (open) setStep(0); }, [open]);

  if (!open) return null;
  if (typeof document === "undefined") return null;     // SSR guard

  const cur  = STEPS[step];
  const last = step === STEPS.length - 1;
  const Icon = cur.icon;

  const node = (
    <div
      data-testid="commute-coachmark"
      role="dialog"
      aria-label="Commute tour"
      style={{
        position: "fixed",
        inset:     0,
        zIndex:    9999,
        display:   "flex",
        alignItems:     "center",
        justifyContent: "center",
        padding:        "1rem",
        background:    "rgba(0,0,0,0.55)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
      }}
      onClick={onDismiss}>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width:           "min(420px, 100%)",
          background:    "var(--bg-base, #0a0a0c)",
          border:           "1px solid rgba(0, 240, 255, 0.45)",
          borderRadius: "20px",
          padding:         "1.5rem",
          boxShadow:    "0 20px 60px rgba(0,0,0,0.65), 0 0 40px rgba(0,240,255,0.15)",
          color:             "#e8e8ec",
        }}>
        {/* Close (×) */}
        <button
          type="button"
          onClick={onDismiss}
          aria-label="Skip tour"
          data-testid="commute-coachmark-skip"
          style={{
            position: "absolute",
            top:        "calc(50% - 200px)",
            right:     "calc(50% - 200px)",
            border:    "none", background: "transparent",
            color:      "#9aa0a6", cursor: "pointer",
          }}>
          <X size={18} />
        </button>

        <div style={{ display: "flex", gap: "0.5rem", alignItems: "center",
                              fontFamily: "monospace", fontSize: 10,
                              letterSpacing: "0.3em", color: "#9aa0a6",
                              textTransform: "uppercase" }}>
          BIG&shy;FM TOUR · STEP {step + 1} OF {STEPS.length}
        </div>

        <div style={{ display: "flex", gap: "0.75rem", alignItems: "flex-start",
                              marginTop: "0.75rem" }}>
          <div style={{ flex: "0 0 auto",
                              width: 40, height: 40, borderRadius: 12,
                              background: "rgba(0,240,255,0.10)",
                              border: "1px solid rgba(0,240,255,0.30)",
                              display: "flex", alignItems: "center", justifyContent: "center",
                              color: "var(--accent-electric, #00f0ff)" }}>
            <Icon size={18} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontFamily: "var(--font-display, serif)",
                                  fontWeight: 700, fontSize: "1.125rem",
                                  letterSpacing: "-0.01em" }}
                  data-testid={`commute-coachmark-title-${step}`}>
              {cur.title}
            </div>
            <p style={{ fontSize: "0.8125rem", color: "#9aa0a6",
                              marginTop: "0.35rem", lineHeight: 1.5 }}>
              {cur.body}
            </p>
          </div>
        </div>

        {/* Step dots */}
        <div style={{ display: "flex", gap: 6, justifyContent: "center",
                              marginTop: "1.25rem" }}
              data-testid="commute-coachmark-dots">
          {STEPS.map((_, i) => (
            <span key={i}
                      style={{
                        width: i === step ? 22 : 6, height: 6, borderRadius: 999,
                        background: i === step
                          ? "var(--accent-electric, #00f0ff)" : "rgba(255,255,255,0.18)",
                        transition: "all 0.2s ease",
                      }} />
          ))}
        </div>

        <div style={{ display: "flex", justifyContent: "space-between",
                              alignItems: "center", marginTop: "1rem" }}>
          <button
            type="button"
            onClick={onDismiss}
            data-testid="commute-coachmark-dismiss"
            style={{
              background: "transparent", border: "none",
              color: "#9aa0a6", fontSize: 12, cursor: "pointer",
              padding: "6px 8px",
            }}>
            Skip
          </button>
          {last ? (
            <button
              type="button"
              onClick={onDismiss}
              data-testid="commute-coachmark-got-it"
              style={{
                background: "var(--accent-electric, #00f0ff)",
                color: "#000", border: "none", borderRadius: 999,
                fontWeight: 700, fontSize: 12, padding: "8px 16px",
                cursor: "pointer",
              }}>
              Got it
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setStep((s) => Math.min(s + 1, STEPS.length - 1))}
              data-testid="commute-coachmark-next"
              style={{
                background: "var(--accent-electric, #00f0ff)",
                color: "#000", border: "none", borderRadius: 999,
                fontWeight: 700, fontSize: 12, padding: "8px 16px",
                cursor: "pointer", display: "inline-flex",
                alignItems: "center", gap: 4,
              }}>
              Next <ChevronRight size={12} />
            </button>
          )}
        </div>
      </div>
    </div>
  );

  return createPortal(node, document.body);
}
