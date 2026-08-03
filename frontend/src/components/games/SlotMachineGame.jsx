// Phase 23 Session 7 — Slot Machine re-skinned from uploaded reel
// pattern, server-resolved.  Outcome (symbols + win/lose) comes from
// the parent via the `result` prop.  Cleanup discipline matches the
// 4.5c/d lessons.
import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);
const CELL    = 90;
const DEFAULT_SYMBOLS = ["🎵","🎤","📻","🎧","⭐","💎"];


export default function SlotMachineGame({
  config, onSubmit, submitting, result, brand, onAnimationComplete,
}) {
  const accent  = brand || "#f59e0b";
  const symbols = config?.symbols && config.symbols.length
    ? config.symbols : DEFAULT_SYMBOLS;
  // Long strip used for the rolling animation; loops through symbols.
  const STRIP = Array.from({ length: 80 },
                                                  (_, j) => symbols[j % symbols.length]);

  const reelRefs    = [useRef(null), useRef(null), useRef(null)];
  const rafRef        = useRef(null);
  const animatedRef = useRef(false);
  const [rolling, setRolling] = useState(false);

  // Cleanup any in-flight animation on unmount.
  useEffect(() => () => {
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
  }, []);

  // Server result arrived → roll reels to result.symbols.
  useEffect(() => {
    if (!result || animatedRef.current) return;
    animatedRef.current = true;
    setRolling(true);
    // Predetermined symbols from server.  Fallback: random 3.
    const target = (Array.isArray(result.symbols)
                                  && result.symbols.length === 3
                                  && result.symbols.every((s) => symbols.includes(s)))
        ? result.symbols
        : (() => {
            const idx = symbols.indexOf(
                result.prize?.title?.slice(0, 1) || symbols[0]);
            const s    = idx >= 0 ? idx : 0;
            return result.result === "win"
                ? [symbols[s], symbols[s], symbols[s]]
                : [symbols[0], symbols[1], symbols[2]];
        })();
    const finals = target.map((sym, i) => 48 + i * 6 + symbols.indexOf(sym));
    const durs    = [2200, 2700, 3200];
    const startTime = performance.now();
    const frame = (now) => {
      let allDone = true;
      finals.forEach((fin, i) => {
        const t      = Math.min(1, (now - startTime) / durs[i]);
        const off  = easeOutCubic(t) * fin * CELL;
        const el    = reelRefs[i].current;
        if (el) el.style.transform = `translateY(${-off}px)`;
        if (t < 1) allDone = false;
      });
      if (!allDone) {
        rafRef.current = requestAnimationFrame(frame);
      } else {
        setRolling(false);
        // Phase 23 Session 8b — gate the parent ResultModal on the
        // 3rd reel + 200ms buffer.  Min total = 3200ms + 200ms = 3400ms
        // (≥3200ms acceptance gate).
        setTimeout(() => onAnimationComplete?.(result), 200);
      }
    };
    rafRef.current = requestAnimationFrame(frame);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, [result, symbols]);

  const onPull = () => {
    if (rolling || submitting || result) return;
    onSubmit?.({ action: "pull" });
  };

  return (
    <div className="slot-machine-game" data-testid="slot-machine-game"
            style={{ display: "flex", flexDirection: "column",
                            alignItems: "center", gap: 16,
                            "--tpl-accent": accent }}>
      <div style={{ display: "flex", gap: 10, padding: 14,
                                    borderRadius: 16,
                                    background: "linear-gradient(135deg, #2d1b00, #1a1100)",
                                    border: `3px solid ${accent}`,
                                    boxShadow: `0 14px 40px ${accent}33` }}>
        {reelRefs.map((ref, i) => (
          <div key={i} data-testid={`slot-reel-${i}`}
                  style={{ width: CELL, height: CELL,
                                  borderRadius: 10, overflow: "hidden",
                                  background: "#0a0a0c",
                                  boxShadow: "inset 0 0 20px rgba(0,0,0,0.8)" }}>
            <div ref={ref}
                    style={{ transition: "none", willChange: "transform" }}>
              {STRIP.map((sym, j) => (
                <div key={j}
                        style={{ width: CELL, height: CELL,
                                        display: "flex", alignItems: "center",
                                        justifyContent: "center", fontSize: 48 }}>
                  {sym}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
      <button onClick={onPull}
                  disabled={rolling || submitting || !!result}
                  data-testid="slot-machine-pull-btn"
                  style={{ border: "none", cursor: "pointer",
                                  padding: "13px 36px", borderRadius: 999,
                                  fontSize: 15, fontWeight: 800, letterSpacing: 0.6,
                                  color: "#fff",
                                  background: `linear-gradient(135deg, ${accent}, #b45309)`,
                                  boxShadow: `0 10px 24px ${accent}55`,
                                  opacity: rolling || submitting ? 0.6 : 1 }}>
        {submitting
          ? <><Loader2 size={14} className="spin"/> Loading…</>
          : rolling ? "Rolling…" : "PULL"}
      </button>
    </div>
  );
}
