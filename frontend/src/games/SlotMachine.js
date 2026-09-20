// Phase 8b — Slot Machine. Server pre-decides reel positions; we animate
// each reel to a long random scroll that lands on the server's pick. The
// "win" decision is made server-side on submit based on the symbol match.
import { useEffect, useRef, useState } from "react";
import { Loader2, Zap } from "lucide-react";

export default function SlotMachine({ config, onSubmit, submitting, result, brand }) {
  const reels = config.reels || [];
  const positions = config.positions || [];
  const spinMs = config.spin_duration_ms || 3200;
  const [phase, setPhase] = useState("idle"); // idle | spinning | done
  const [reelStops, setReelStops] = useState(reels.map(() => 0));
  const reelRefs = useRef(reels.map(() => null));

  const startSpin = () => {
    if (phase !== "idle" || submitting) return;
    setPhase("spinning");
    // Stagger reel stop timings (left → right)
    reels.forEach((_, i) => {
      const delay = i * 450;
      setTimeout(() => {
        setReelStops((s) => {
          const c = [...s];
          c[i] = positions[i] || 0;
          return c;
        });
        if (i === reels.length - 1) {
          setTimeout(() => {
            setPhase("done");
            onSubmit({});
          }, spinMs + 200);
        }
      }, delay);
    });
  };

  const symbolHeight = 80;

  return (
    <div className="slot-shell" data-testid="slot-machine"
            style={{ "--brand": brand }}>
      <div className="slot-marquee mono">
        <Zap size={12} /> FUUSIC SLOTS · MATCH 3 TO WIN
      </div>
      <div className="slot-cabinet">
        {reels.map((reel, ri) => {
          // Build a long virtual strip — repeat the symbols 8x then land on target
          const repeats = 8;
          const fullStrip = [];
          for (let k = 0; k < repeats; k++)
            fullStrip.push(...reel);
          const targetIdx = (reels.length - 1 === ri && phase === "done")
            ? positions[ri]
            : reelStops[ri];
          // Distance: end-of-strip + final position
          const stopAt = (repeats - 1) * reel.length + targetIdx;
          const translateY = -(stopAt * symbolHeight);
          return (
            <div className="slot-reel" key={ri} data-testid={`slot-reel-${ri}`}>
              <div className="slot-reel-window">
                <div className="slot-reel-strip"
                       ref={(el) => (reelRefs.current[ri] = el)}
                       style={{
                         transform: `translateY(${translateY}px)`,
                         transition: phase === "spinning"
                           ? `transform ${spinMs}ms cubic-bezier(.2,.7,.25,1)`
                           : phase === "done"
                           ? `transform 0s`
                           : `transform 0s`,
                       }}>
                  {fullStrip.map((s, k) => (
                    <div className="slot-symbol" key={k}>
                      <span>{s.label}</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="slot-paylines" />
            </div>
          );
        })}
      </div>
      <button className="slot-lever-btn"
                onClick={startSpin}
                disabled={phase !== "idle" || submitting || !!result}
                data-testid="slot-spin-btn">
        {phase === "spinning" || submitting
          ? <><Loader2 size={14} className="spin" /> SPINNING…</>
          : <>PULL THE LEVER</>}
      </button>
      <p className="slot-help mono">Match 3 symbols on the centre row to win</p>
    </div>
  );
}
