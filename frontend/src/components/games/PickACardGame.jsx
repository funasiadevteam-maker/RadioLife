// Phase 23 Session 4 — Pick-a-Card game (genuinely new).
//
// Listener sees 3 face-down cards, taps one, the chosen card flips with
// a CSS keyframe + scale bump; the other two reveal as "lost" outcomes.
// The component is purely presentational — it calls `onSubmit({choice})`
// and the parent (`GamePlayer.js`) handles the server-side weighted
// prize selection via the same `record_winner` flow every other game
// uses.  Brand color is applied via the `--brand` CSS custom property
// so the campaign's primary color tints the card backs + win burst.
//
// Prop contract (mirrors SpinWheel / ScratchCard / etc.):
//   config:       { type:"pick_a_card", num_cards?: 3 }
//   onSubmit:    (clientPayload) => void   // called with {choice: idx}
//   submitting: bool
//   result:        null | { result:"win"|"lose", prize?:{...} }
//   brand:          "#rrggbb"
import { useEffect, useState } from "react";

const DEFAULT_NUM_CARDS = 3;

export default function PickACardGame({
  config, onSubmit, submitting, result, brand, onAnimationComplete,
}) {
  const num = Math.max(2,
    Math.min(6, parseInt((config || {}).num_cards) || DEFAULT_NUM_CARDS));
  const [pickedIdx, setPickedIdx] = useState(null);
  const isWin = result?.result === "win";

  // Reset internal state when the parent clears the result (e.g. user
  // restarted a session).  Prevents stale flipped card carrying over.
  useEffect(() => {
    if (result === null) setPickedIdx(null);
  }, [result]);

  // Phase 23 Session 8b — gate the parent ResultModal on the flip
  // animation completing.  Total = 1000ms flip + 300ms buffer = 1300ms
  // (≥1300ms acceptance gate).
  useEffect(() => {
    if (!result) return;
    const t = setTimeout(() => onAnimationComplete?.(result), 1300);
    return () => clearTimeout(t);
  }, [result, onAnimationComplete]);

  const pick = (i) => {
    if (submitting || pickedIdx !== null) return;
    setPickedIdx(i);
    onSubmit({ choice: i });
  };

  return (
    <div className="pick-a-card-stage" data-testid="pick-a-card-game"
            style={{ "--brand": brand || "#ff2d95",
                        display: "flex", flexDirection: "column",
                        alignItems: "center", gap: 18 }}>
      {!result && (
        <div className="mono dim" data-testid="pick-a-card-prompt">
          Pick a card, any card
        </div>
      )}
      <div className="pick-a-card-row"
              style={{ display: "flex", gap: 16, perspective: 1200 }}>
        {Array.from({ length: num }).map((_, i) => {
          const revealed = pickedIdx === i || result !== null;
          const chosen    = pickedIdx === i;
          const showWin  = chosen && isWin;
          const showLose = !chosen && result !== null;
          return (
            <button
              key={i}
              onClick={() => pick(i)}
              disabled={submitting || pickedIdx !== null}
              data-testid={`pick-card-${i}`}
              aria-label={`Pick card ${i + 1}`}
              style={{
                width: 110, height: 160, borderRadius: 12,
                border: "none", padding: 0, cursor: pickedIdx !== null
                  ? "default" : "pointer",
                transformStyle: "preserve-3d",
                transform: revealed ? "rotateY(180deg)" : "rotateY(0)",
                // Phase 23 Session 8b — flip duration bumped 0.55s → 1.0s
                // to satisfy the ≥1.0s flip acceptance gate.
                transition: "transform 1s cubic-bezier(.4,1.4,.6,1)",
                background: "transparent",
              }}>
              <span data-testid={`pick-card-${i}-back`}
                      style={{
                          position: "absolute", inset: 0, borderRadius: 12,
                          backfaceVisibility: "hidden",
                          background: `linear-gradient(135deg, ${brand || "#ff2d95"} 0%, #16161a 100%)`,
                          display: "flex", alignItems: "center",
                          justifyContent: "center", color: "#fff",
                          fontSize: 32, fontWeight: 700,
                          boxShadow: "0 6px 18px rgba(0,0,0,0.45)",
                      }}>?</span>
              <span data-testid={`pick-card-${i}-face`}
                      style={{
                          position: "absolute", inset: 0, borderRadius: 12,
                          backfaceVisibility: "hidden",
                          transform: "rotateY(180deg)",
                          background: showWin
                              ? "linear-gradient(135deg, #14e29a 0%, #0a7a52 100%)"
                              : "#16161a",
                          border: showLose ? "1px solid rgba(255,255,255,0.06)"
                                                  : "none",
                          display: "flex", alignItems: "center",
                          justifyContent: "center",
                          color: showWin ? "#0a0a0c" : "#9aa3af",
                          fontSize: showWin ? 18 : 14,
                          fontWeight: showWin ? 700 : 400,
                          padding: 8, textAlign: "center",
                      }}>
                {showWin && (result?.prize?.title || "Winner")}
                {showLose && "—"}
                {chosen && !result && submitting && "…"}
              </span>
            </button>
          );
        })}
      </div>
      {submitting && (
        <div className="mono dim" data-testid="pick-a-card-revealing">
          Revealing…
        </div>
      )}
    </div>
  );
}
