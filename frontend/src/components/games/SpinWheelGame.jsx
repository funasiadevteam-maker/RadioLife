// Phase 23 Session 7 — Spin Wheel re-skinned from the uploaded
// PlayAndWin.jsx canvas idiom but server-resolved.  Outcome comes
// from the parent via the `result` prop; the animation only THEATRES
// what the backend already decided.
//
// Canvas hardening (lessons from 4.5c/d):
//   * `useLayoutEffect` for the initial DPR scale + draw so a React
//     18 StrictMode double-mount doesn't race the canvas attribute
//     reassertion.
//   * Imperative `canvas.width`/`canvas.height` reassertion in every
//     paint so attribute re-application by HMR can't blank the
//     buffer.
//   * `globalCompositeOperation="source-over"` reset at the start of
//     `draw()` so any future "erase" mode added downstream stays
//     idempotent.
//   * `cancelAnimationFrame` cleanup on unmount + on result reset.
import {
  useCallback, useEffect, useLayoutEffect, useRef, useState,
} from "react";
import { Loader2 } from "lucide-react";

const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
const FONT = "'Geist Mono', 'Trebuchet MS', system-ui, sans-serif";


function defaultSegments(brand) {
  // Built-in fallback so any spin_wheel campaign without a config
  // still renders.  Server prize selection still drives the result.
  return [
    { label: "Free Coffee",  color: brand || "#a855f7" },
    { label: "Try Again",      color: "#231044" },
    { label: "Merch",                color: "#7c3aed" },
    { label: "Try Again",      color: "#3b0764" },
    { label: "Concert Tix",  color: "#c084fc" },
    { label: "Try Again",      color: "#231044" },
  ];
}


export default function SpinWheelGame({
  config, onSubmit, submitting, result, brand, onAnimationComplete,
}) {
  const SIZE = 320;
  const segments = (config?.segments && config.segments.length)
    ? config.segments : (config?.prizes && config.prizes.length
        ? config.prizes : defaultSegments(brand));
  const N      = segments.length;
  const ARC    = (2 * Math.PI) / N;
  const accent = brand || "#a855f7";  // template_theme.spin_wheel.accent

  const canvasRef    = useRef(null);
  const ctxRef          = useRef(null);
  const rafRef          = useRef(null);
  const angleRef      = useRef(0);
  const animatingRef = useRef(false);
  const [spinning, setSpinning] = useState(false);

  const draw = useCallback((rot) => {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = ctxRef.current || c.getContext("2d");
    if (!ctx) return;
    ctx.globalCompositeOperation = "source-over";
    const cx = SIZE / 2, cy = SIZE / 2, r = SIZE / 2 - 8;
    ctx.clearRect(0, 0, SIZE, SIZE);
    for (let i = 0; i < N; i++) {
      const start = rot + i * ARC;
      const seg    = segments[i];
      const color = seg.color || seg.accent_color
                              || (i % 2 ? "#3b0764" : "#7c3aed");
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, r, start, start + ARC);
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.65)";
      ctx.lineWidth    = 2;
      ctx.stroke();
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(start + ARC / 2);
      ctx.fillStyle    = "#fff";
      ctx.font              = `bold 13px ${FONT}`;
      ctx.textAlign    = "right";
      ctx.textBaseline = "middle";
      const label = (seg.label || seg.display_label
                                  || seg.title || "—").slice(0, 14);
      ctx.fillText(label, r - 12, 0);
      ctx.restore();
    }
    // Center hub.
    ctx.beginPath();
    ctx.arc(cx, cy, 22, 0, 2 * Math.PI);
    ctx.fillStyle = "#fff";
    ctx.fill();
    ctx.strokeStyle = accent;
    ctx.lineWidth    = 3;
    ctx.stroke();
  }, [ARC, N, accent, segments]);

  // DPR-aware initial mount.  useLayoutEffect runs synchronously
  // after DOM mutation but before paint — closes the StrictMode race.
  useLayoutEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    c.width  = SIZE * dpr;
    c.height = SIZE * dpr;
    c.style.width    = SIZE + "px";
    c.style.height = SIZE + "px";
    const ctx = c.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.scale(dpr, dpr);
    ctxRef.current = ctx;
    draw(angleRef.current);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [draw]);

  // Phase 23 S9-hotfix — OPTIMISTIC spin. The wheel begins rotating
  // immediately on click (free-spin loop at constant velocity) so the
  // user gets instant visual feedback, even before /api/play/resolve
  // returns. When the server response arrives, the landing-animation
  // effect below takes over and decelerates onto the picked segment.
  const optimisticAfRef = useRef(null);
  const startOptimisticSpin = useCallback(() => {
    if (optimisticAfRef.current || animatingRef.current) return;
    setSpinning(true);
    const FREE_RPS = 2.2;           // 2.2 revolutions per second
    let last = performance.now();
    const frame = (now) => {
      if (animatingRef.current) {
        // Landing animation took over — stop the free-spin loop.
        optimisticAfRef.current = null;
        return;
      }
      const dt = (now - last) / 1000; last = now;
      angleRef.current = (angleRef.current + FREE_RPS * 2 * Math.PI * dt) % (2 * Math.PI);
      draw(angleRef.current);
      optimisticAfRef.current = requestAnimationFrame(frame);
    };
    optimisticAfRef.current = requestAnimationFrame(frame);
  }, [draw]);

  // Server result arrived → animate to the picked segment.
  useEffect(() => {
    if (!result || animatingRef.current) return;
    animatingRef.current = true;
    // Stop the free-spin loop so the landing animation owns the canvas.
    if (optimisticAfRef.current) {
      cancelAnimationFrame(optimisticAfRef.current);
      optimisticAfRef.current = null;
    }
    setSpinning(true);
    // Server may provide `segment_index`.  When absent (legacy
    // backend), fall back to a random index — theatre still works,
    // but the wedge under the pointer won't match the modal text.
    const target = (typeof result.segment_index === "number"
                                  && result.segment_index >= 0
                                  && result.segment_index < N)
        ? result.segment_index
        : Math.floor(Math.random() * N);
    // Land target's CENTER under the top pointer (angle = -PI/2).
    const desired = -Math.PI / 2 - (target * ARC + ARC / 2);
    let final = desired;
    while (final < angleRef.current + 5 * 2 * Math.PI) final += 2 * Math.PI;
    const startRot  = angleRef.current;
    const startTime = performance.now();
    const DUR              = 4200;
    const frame = (now) => {
      const t    = Math.min(1, (now - startTime) / DUR);
      const rot = startRot + (final - startRot) * easeOutCubic(t);
      draw(rot);
      if (t < 1) {
        rafRef.current = requestAnimationFrame(frame);
      } else {
        angleRef.current = final % (2 * Math.PI);
        setSpinning(false);
        // Phase 23 Session 8b — gate the parent ResultModal on the
        // animation's onComplete handler (NOT on result-prop receipt).
        // Min total duration = 4200ms (≥3500ms acceptance gate).
        onAnimationComplete?.(result);
      }
    };
    rafRef.current = requestAnimationFrame(frame);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [result, ARC, N, draw]);

  const onSpin = () => {
    if (spinning || submitting || result) return;
    // Phase 23 S9-hotfix — fire optimistic spin BEFORE awaiting server,
    // so the user sees motion within ~16ms of click.
    startOptimisticSpin();
    onSubmit?.({ action: "spin" });
  };

  return (
    <div className="spin-wheel-game" data-testid="spin-wheel-game"
            style={{ display: "flex", flexDirection: "column",
                            alignItems: "center", gap: 14,
                            "--tpl-accent": accent }}>
      <div style={{ position: "relative", width: SIZE, height: SIZE,
                                    filter: "drop-shadow(0 16px 40px rgba(0,0,0,0.45))" }}>
        {/* Top pointer */}
        <div data-testid="spin-wheel-pointer"
                style={{ position: "absolute", top: -4, left: "50%",
                                transform: "translateX(-50%)", width: 0, height: 0,
                                borderLeft: "12px solid transparent",
                                borderRight: "12px solid transparent",
                                borderTop: `18px solid ${accent}`,
                                zIndex: 2, filter: "drop-shadow(0 2px 4px rgba(0,0,0,0.6))" }}/>
        <canvas ref={canvasRef}
                        data-testid="spin-wheel-canvas"
                        width={SIZE} height={SIZE}
                        style={{ borderRadius: "50%",
                                        background: "#15151a",
                                        border: `3px solid ${accent}` }}/>
      </div>
      <button onClick={onSpin}
                  disabled={spinning || submitting || !!result}
                  data-testid="spin-wheel-spin-btn"
                  style={{ border: "none", cursor: "pointer",
                                  padding: "13px 36px", borderRadius: 999,
                                  fontSize: 15, fontWeight: 800, letterSpacing: 0.6,
                                  color: "#fff",
                                  background: `linear-gradient(135deg, ${accent}, #6d28d9)`,
                                  boxShadow: `0 10px 24px ${accent}55`,
                                  opacity: spinning || submitting ? 0.6 : 1 }}>
        {submitting
          ? <><Loader2 size={14} className="spin"/> Loading…</>
          : spinning ? "Spinning…" : "SPIN"}
      </button>
    </div>
  );
}
