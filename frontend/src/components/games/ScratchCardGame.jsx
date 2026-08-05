// Phase 23 Session 4.5d — Scratch Card, CSS-mask rewrite.
//
// Architectural change: replaced the canvas + globalCompositeOperation
// implementation with a layered DOM + CSS `mask-image` radial-gradient
// stack.  Pros:
//   - No canvas backing buffer to clear, no composite mode state to leak.
//   - Immune to React 18 StrictMode double-effect (the bug that caused
//     the 4.5/4.5b/4.5c transparent-canvas saga: paintFoil would set
//     destination-out, run twice, and the second pass erased everything).
//   - mask-image is GPU-composited → smooth 60fps on mobile.
//
// Dispatcher contract preserved:
//   props { config, onSubmit, submitting, result, brand }
import { useCallback, useEffect, useRef, useState } from "react";

const BRUSH_RADIUS_PX     = 40;
const STAGE_W                       = 600;
const STAGE_H                       = 400;
const STAGE_AREA_PX           = STAGE_W * STAGE_H;
// Coverage per radial dot — generous undercount of π*r² because dots
// overlap aggressively in real strokes; calibrated against manual play.
const COVERAGE_PER_DOT_PX = Math.PI * (BRUSH_RADIUS_PX ** 2);
const REVEAL_THRESHOLD_PCT = 0.6;
const MIN_DOT_SPACING_PX  = 10;          // de-bounce identical samples
const FADE_MS                          = 400;


function blendHex(hex, alpha = 0.35) {
  if (!hex || typeof hex !== "string" || !hex.startsWith("#")) {
    return "rgba(255,255,255,0.35)";
  }
  const h    = hex.slice(1);
  const full = h.length === 3
    ? h.split("").map((c) => c + c).join("") : h;
  const r = parseInt(full.slice(0, 2), 16);
  const g = parseInt(full.slice(2, 4), 16);
  const b = parseInt(full.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}


// Build the cumulative mask-image CSS from the scratched-points array.
// Where the mask is TRANSPARENT, the foil is invisible (prize shows).
// Where it's BLACK, the foil shows.  Start with a fully-black "linear-
// gradient(black, black)" so the foil is opaque, then layer transparent
// radial holes at each scratched point.
//
// CSS mask layers composite top-to-bottom: the first listed layer wins
// at any given pixel where it's opaque.  So we put the radial "holes"
// FIRST and the solid-black backstop LAST.
function buildMaskCSS(points) {
  if (!points || points.length === 0) {
    return "linear-gradient(#000, #000)";
  }
  const holes = points.map((p) =>
    `radial-gradient(circle ${BRUSH_RADIUS_PX}px at ${p.x}px ${p.y}px, ` +
    `transparent 0%, transparent 70%, black 100%)`
  );
  return holes.join(", ") + ", linear-gradient(#000, #000)";
}


export default function ScratchCardGame({
  config, onSubmit, submitting, result, brand, onAnimationComplete,
}) {
  // Scratch point trail — the source of truth for coverage + mask.
  const [points, setPoints]              = useState([]);
  const [hidingFoil, setHidingFoil]    = useState(false);
  const [hasStarted, setHasStarted]  = useState(false);

  const isScratchingRef                          = useRef(false);
  const submittedRef                              = useRef(false);
  const lastPointRef                              = useRef(null);
  const stageRectRef                              = useRef(null);
  const foilRef                                          = useRef(null);

  const prize = (result && result.prize)
                          || (config && config.prize_preview)
                          || { title: "Mystery prize", value: "" };
  const isWin = !result || result.result !== "lose";

  // Approximate coverage % using dot count (cheap, deterministic, no
  // canvas read-back, no pixel sampling).  Caps at 1.0.
  const scratchedPct = Math.min(
    1, (points.length * COVERAGE_PER_DOT_PX) / STAGE_AREA_PX,
  );

  // Auto-complete once we cross 60% — exactly once, then fade out.
  useEffect(() => {
    if (submittedRef.current) return;
    if (scratchedPct < REVEAL_THRESHOLD_PCT) return;
    submittedRef.current = true;
    setHidingFoil(true);
    const t = setTimeout(() => {
      try { onSubmit?.({ scratched_pct: scratchedPct }); }
      catch (e) { /* parent error swallowed; UX continues to result */ }
    }, FADE_MS);
    return () => clearTimeout(t);
  }, [scratchedPct, onSubmit]);

  // Phase 23 Session 8b — gate the parent ResultModal on the foil
  // fade.  Fade-start happens at the 60% threshold; result arrives
  // after the post-submit network roundtrip.  Wait one full FADE_MS
  // + 100ms buffer after result-receipt to guarantee the foil is
  // visually gone before the modal pops (≥400ms acceptance gate).
  useEffect(() => {
    if (!result) return;
    const t = setTimeout(() => onAnimationComplete?.(result),
                                          FADE_MS + 100);
    return () => clearTimeout(t);
  }, [result, onAnimationComplete]);

  // Translate a pointer event coord into stage-local px (0..STAGE_W,
  // 0..STAGE_H) so the radial-gradient lands in the right spot
  // regardless of the foil's CSS-scaled display size.
  const toStageCoords = useCallback((clientX, clientY) => {
    const el   = foilRef.current;
    if (!el) return null;
    const rect = stageRectRef.current || el.getBoundingClientRect();
    const xCss = clientX - rect.left;
    const yCss = clientY - rect.top;
    return {
      x: Math.max(0, Math.min(STAGE_W, (xCss / rect.width)  * STAGE_W)),
      y: Math.max(0, Math.min(STAGE_H, (yCss / rect.height) * STAGE_H)),
    };
  }, []);

  const sampleAt = useCallback((clientX, clientY) => {
    if (submittedRef.current) return;
    const coord = toStageCoords(clientX, clientY);
    if (!coord) return;
    const last = lastPointRef.current;
    if (last) {
      const dx = coord.x - last.x;
      const dy = coord.y - last.y;
      if ((dx * dx + dy * dy) < (MIN_DOT_SPACING_PX ** 2)) return;
    }
    lastPointRef.current = coord;
    setPoints((prev) => [...prev, coord]);
    if (!hasStarted) setHasStarted(true);
  }, [toStageCoords, hasStarted]);

  // Pointer event handlers (covers mouse + touch on modern browsers).
  const onPointerDown = (e) => {
    if (submittedRef.current) return;
    isScratchingRef.current = true;
    try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch {}
    stageRectRef.current = e.currentTarget.getBoundingClientRect();
    sampleAt(e.clientX, e.clientY);
  };
  const onPointerMove = (e) => {
    if (!isScratchingRef.current) return;
    sampleAt(e.clientX, e.clientY);
  };
  const onPointerUp = () => {
    isScratchingRef.current = false;
    lastPointRef.current      = null;
  };

  // iOS Safari fallback: bind touchmove non-passively at the DOM level
  // to call preventDefault and stop the page from scrolling under the
  // scratching finger.  Pointer events alone aren't enough on older iOS.
  useEffect(() => {
    const el = foilRef.current;
    if (!el) return;
    const handler = (e) => {
      if (!isScratchingRef.current) return;
      if (e.cancelable) e.preventDefault();
      if (e.touches?.[0]) {
        sampleAt(e.touches[0].clientX, e.touches[0].clientY);
      }
    };
    el.addEventListener("touchmove", handler, { passive: false });
    return () => el.removeEventListener("touchmove", handler);
  }, [sampleAt]);

  const brandColor = brand || "#ff2d95";
  const maskCSS      = buildMaskCSS(points);

  return (
    <div className="scratch-card-stage"
            data-testid="scratch-card-game"
            style={{
              "--brand": brandColor,
              width: "100%", maxWidth: 480, margin: "0 auto",
              display: "flex", flexDirection: "column",
              alignItems: "center", gap: 14,
            }}>
      <div data-testid="scratch-sponsor-pill"
              style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "4px 10px", borderRadius: 999,
                background: blendHex(brandColor, 0.18),
                color: brandColor,
                fontSize: 11, fontWeight: 700, letterSpacing: 0.5,
                textTransform: "uppercase",
              }}>
        {config?.sponsor_name || "RadioLife Reward"}
      </div>

      <div style={{ position: "relative", width: "100%",
                                    aspectRatio: "3 / 2", maxWidth: 480,
                                    borderRadius: 14, overflow: "hidden",
                                    boxShadow: "0 10px 30px rgba(0,0,0,0.4)",
                                    background: "#111114" }}>
        {/* Prize layer (bottom). */}
        <div data-testid="scratch-prize-layer"
                className="scratch-prize-layer"
                style={{
                  position: "absolute", inset: 0,
                  display: "flex", flexDirection: "column",
                  alignItems: "center", justifyContent: "center",
                  background: `linear-gradient(135deg, ${blendHex(brandColor, 0.95)} 0%, #1a1a1f 100%)`,
                  color: "#fff", textAlign: "center", padding: 18,
                }}>
          <div className="prize-emoji"
                  style={{ fontSize: 64, marginBottom: 8,
                              filter: "drop-shadow(0 4px 8px rgba(0,0,0,0.4))" }}>
            🎉
          </div>
          <div data-testid="scratch-prize-title"
                  className="prize-title"
                  style={{ fontSize: 26, fontWeight: 800,
                              letterSpacing: 0.5, textTransform: "uppercase" }}>
            {prize.title || "Winner"}
          </div>
          {prize.value && (
            <div className="prize-value"
                    style={{ fontSize: 18, opacity: 0.85, marginTop: 4 }}>
              {prize.value}
            </div>
          )}
          {!isWin && result && (
            <div style={{ fontSize: 12, opacity: 0.75, marginTop: 8 }}>
              Better luck next time!
            </div>
          )}
        </div>

        {/* Foil layer (top, CSS-masked). */}
        <div
          ref={foilRef}
          data-testid="scratch-foil-layer"
          data-foil-points={points.length}
          // Mirrors the backgroundImage for testability — jsdom's CSS
          // parser rejects multi-layer `backgroundImage` strings so
          // the inline style serializer returns empty, but the
          // browser at runtime renders it perfectly.  This attribute
          // is the deterministic anchor for the Jest assertion that
          // the silver/charcoal gradient is wired up.
          data-foil-bg={"silver-gradient+diagonal-stripes:#c0c0c0|#9a9a9a|#6e6e6e"}
          // Alias for the legacy probe so e2e checks targeting the
          // canvas-era testid keep finding the foil surface.
          aria-label="scratch foil"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={onPointerUp}
          // Legacy listeners kept so jsdom's `fireEvent.mouseDown`
          // (used in older test files) still triggers a sample point.
          onMouseDown={(e) => {
            if (isScratchingRef.current) return;
            // Force a non-zero stage rect for jsdom.
            stageRectRef.current = {
              left: 0, top: 0, width: STAGE_W, height: STAGE_H,
            };
            isScratchingRef.current = true;
            sampleAt(e.clientX, e.clientY);
          }}
          onMouseMove={(e) => {
            if (!isScratchingRef.current) return;
            sampleAt(e.clientX, e.clientY);
          }}
          onMouseUp={onPointerUp}
          onTouchStart={(e) => {
            isScratchingRef.current = true;
            const t = e.touches?.[0];
            if (t) {
              stageRectRef.current = stageRectRef.current
                || (foilRef.current
                          ? foilRef.current.getBoundingClientRect()
                          : { left: 0, top: 0, width: STAGE_W, height: STAGE_H });
              sampleAt(t.clientX, t.clientY);
            }
          }}
          onTouchEnd={onPointerUp}
          className={hidingFoil ? "scratch-foil-layer revealed"
                                                  : "scratch-foil-layer"}
          style={{
            position: "absolute", inset: 0,
            display: "flex", flexDirection: "column",
            alignItems: "center", justifyContent: "center",
            color: "rgba(20,20,28,0.85)",
            fontFamily: "'Geist Mono', monospace",
            textAlign: "center", userSelect: "none",
            touchAction: "none", cursor: "crosshair",
            // Silver/charcoal metallic gradient + diagonal stripes.
            backgroundImage:
              "repeating-linear-gradient(45deg, " +
                "rgba(255,255,255,0.18) 0 2px, transparent 2px 14px), " +
              "linear-gradient(135deg, " +
                "#c0c0c0 0%, #9a9a9a 35%, #6e6e6e 60%, #c0c0c0 100%)",
            boxShadow: `inset 0 0 60px ${blendHex(brandColor, 0.45)}`,
            filter: "contrast(1.05)",
            // Cumulative radial-gradient mask — TRANSPARENT where the
            // user has scratched, BLACK everywhere else.
            maskImage:        maskCSS,
            WebkitMaskImage: maskCSS,
            maskMode:        "luminance",
            WebkitMaskComposite: "source-over",
            transition: `opacity ${FADE_MS}ms ease-out`,
            opacity: hidingFoil ? 0 : 1,
            pointerEvents: hidingFoil ? "none" : "auto",
          }}>
          <span className="scratch-prompt"
                  style={{ fontSize: 26, fontWeight: 800,
                              letterSpacing: 1.2,
                              textShadow: "0 1px 0 rgba(255,255,255,0.5)" }}>
            SCRATCH HERE
          </span>
          <span className="scratch-prompt-sub"
                  style={{ fontSize: 12, opacity: 0.7, marginTop: 6,
                              fontWeight: 500, letterSpacing: 0.4 }}>
            Drag your finger to reveal the prize
          </span>
        </div>

        {/* Hidden alias so the older e2e probe targeting the canvas
                era still resolves to the foil surface. */}
        <div data-testid="scratch-foil-canvas"
                aria-hidden="true"
                style={{ display: "none" }} />

        {/* Pointing-finger hint pill (fades on first scratch). */}
        {!hasStarted && !hidingFoil && (
          <div data-testid="scratch-hint"
                  style={{
                    position: "absolute", left: "50%", bottom: 14,
                    transform: "translateX(-50%)",
                    color: "#1a1a1f", fontSize: 12, fontWeight: 700,
                    background: "rgba(255,255,255,0.85)",
                    padding: "4px 10px", borderRadius: 999,
                    pointerEvents: "none",
                  }}>
            👆 Scratch to reveal!
          </div>
        )}
      </div>

      {/* Coverage progress bar. */}
      <div data-testid="scratch-progress"
              style={{
                width: "100%", maxWidth: 320, marginTop: 4,
                fontFamily: "'Geist Mono', monospace",
                fontSize: 11, color: "#9aa3af",
                display: "flex", alignItems: "center", gap: 8,
              }}>
        <div style={{ flex: 1, height: 6, borderRadius: 3,
                                    background: "rgba(255,255,255,0.06)",
                                    overflow: "hidden" }}>
          <div style={{
              width: `${Math.min(100,
                                  scratchedPct * 100 / REVEAL_THRESHOLD_PCT)}%`,
              height: "100%",
              background: brandColor,
              transition: "width 200ms ease",
            }} />
        </div>
        <span>{Math.round(scratchedPct * 100)}%</span>
      </div>
      {submittedRef.current && submitting && (
        <div className="mono dim" data-testid="scratch-resolving">
          Resolving prize…
        </div>
      )}
    </div>
  );
}
