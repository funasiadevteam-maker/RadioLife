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
import { WHEEL_BACKDROP } from "../../assets/gameArt";

const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
const FONT = "'Geist Mono', 'Trebuchet MS', system-ui, sans-serif";
const PALETTE = ["#7c3aed", "#ec4899", "#f59e0b", "#06b6d4", "#3b82f6", "#a855f7",
                 "#d946ef", "#f43f5e"];

function _lighten(hex, amt) {
  try {
    const h = hex.replace("#", "");
    const n = h.length === 3 ? h.split("").map((c) => c + c).join("") : h;
    const r = Math.min(255, Math.round(parseInt(n.slice(0, 2), 16) + 255 * amt));
    const g = Math.min(255, Math.round(parseInt(n.slice(2, 4), 16) + 255 * amt));
    const b = Math.min(255, Math.round(parseInt(n.slice(4, 6), 16) + 255 * amt));
    return `rgb(${r},${g},${b})`;
  } catch (_e) { return hex; }
}


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
    const cx = SIZE / 2, cy = SIZE / 2;
    const rimOuter = SIZE / 2 - 4;
    const rimInner = rimOuter - 16;      // gold rim band
    const r = rimInner - 3;              // segment radius
    ctx.clearRect(0, 0, SIZE, SIZE);

    // ── rotating colored segments (glossy) ──
    for (let i = 0; i < N; i++) {
      const start = rot + i * ARC;
      const seg = segments[i];
      const base = seg.color || seg.accent_color || PALETTE[i % PALETTE.length];
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, r, start, start + ARC);
      ctx.closePath();
      const g = ctx.createRadialGradient(cx, cy, r * 0.18, cx, cy, r);
      g.addColorStop(0, _lighten(base, 0.28));
      g.addColorStop(1, base);
      ctx.fillStyle = g;
      ctx.fill();
      ctx.strokeStyle = "rgba(255,255,255,0.85)";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(start + ARC / 2);
      ctx.fillStyle = "#fff";
      ctx.font = `800 13px ${FONT}`;
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      ctx.shadowColor = "rgba(0,0,0,.45)";
      ctx.shadowBlur = 3;
      const label = (seg.label || seg.display_label || seg.title || "—").slice(0, 13);
      ctx.fillText(label, r - 14, 0);
      ctx.restore();
    }
    ctx.shadowBlur = 0;

    // ── fixed gold rim band ──
    const rim = ctx.createLinearGradient(0, 0, SIZE, SIZE);
    rim.addColorStop(0, "#fde68a"); rim.addColorStop(0.5, "#d4a017");
    rim.addColorStop(1, "#b8860b");
    ctx.beginPath();
    ctx.arc(cx, cy, (rimOuter + rimInner) / 2, 0, 2 * Math.PI);
    ctx.strokeStyle = rim;
    ctx.lineWidth = rimOuter - rimInner;
    ctx.stroke();

    // ── glowing rim bulbs ──
    const bulbR = (rimOuter + rimInner) / 2;
    const BULBS = Math.max(12, N * 2);
    for (let b = 0; b < BULBS; b++) {
      const a = (b / BULBS) * 2 * Math.PI;
      const bx = cx + Math.cos(a) * bulbR;
      const by = cy + Math.sin(a) * bulbR;
      ctx.beginPath();
      ctx.arc(bx, by, 2.6, 0, 2 * Math.PI);
      ctx.fillStyle = b % 2 ? "#fffbe6" : "#fff2a8";
      ctx.shadowColor = "#ffe9a8"; ctx.shadowBlur = 6;
      ctx.fill();
    }
    ctx.shadowBlur = 0;

    // ── center gold hub with crown ──
    const hubR = 26;
    const hg = ctx.createRadialGradient(cx - 6, cy - 8, 4, cx, cy, hubR);
    hg.addColorStop(0, "#fff6cf"); hg.addColorStop(0.55, "#e9b949");
    hg.addColorStop(1, "#b8860b");
    ctx.beginPath(); ctx.arc(cx, cy, hubR, 0, 2 * Math.PI);
    ctx.fillStyle = hg; ctx.fill();
    ctx.strokeStyle = "#fff"; ctx.lineWidth = 3; ctx.stroke();
    ctx.fillStyle = "#7c3aed";
    ctx.font = "16px system-ui";
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.fillText("\u265B", cx, cy + 1);   // crown glyph
  }, [ARC, N, segments]);

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
      <div style={{ position: "relative", width: SIZE + 44, height: SIZE + 44,
                    display: "grid", placeItems: "center", borderRadius: 28,
                    overflow: "hidden",
                    backgroundImage: `linear-gradient(rgba(10,6,28,.35),rgba(10,6,28,.55)), url(${WHEEL_BACKDROP})`,
                    backgroundSize: "cover", backgroundPosition: "center",
                    boxShadow: "0 20px 60px rgba(0,0,0,0.5)" }}>
        {/* Premium top pointer */}
        <div data-testid="spin-wheel-pointer"
                style={{ position: "absolute", top: 10, left: "50%",
                                transform: "translateX(-50%)", width: 0, height: 0,
                                borderLeft: "15px solid transparent",
                                borderRight: "15px solid transparent",
                                borderTop: "26px solid #fde68a",
                                zIndex: 3, filter: "drop-shadow(0 3px 5px rgba(0,0,0,0.7))" }}/>
        <canvas ref={canvasRef}
                        data-testid="spin-wheel-canvas"
                        width={SIZE} height={SIZE}
                        style={{ borderRadius: "50%", background: "transparent",
                                        filter: "drop-shadow(0 10px 28px rgba(0,0,0,0.45))" }}/>
      </div>
      <button onClick={onSpin}
                  disabled={spinning || submitting || !!result}
                  data-testid="spin-wheel-spin-btn"
                  style={{ border: "none", cursor: "pointer",
                                  padding: "14px 44px", borderRadius: 999,
                                  fontSize: 16, fontWeight: 900, letterSpacing: 0.8,
                                  color: "#fff",
                                  background: "linear-gradient(135deg,#a855f7,#ec4899)",
                                  boxShadow: "0 12px 28px rgba(168,85,247,.5)",
                                  opacity: spinning || submitting ? 0.6 : 1 }}>
        {submitting
          ? <><Loader2 size={14} className="spin"/> Loading…</>
          : spinning ? "Spinning…" : "SPIN NOW"}
      </button>
    </div>
  );
}
