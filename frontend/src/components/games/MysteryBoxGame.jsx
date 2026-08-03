// Phase 23 Session 7 — Mystery Box re-skinned from uploaded box-pick
// pattern, server-resolved.  Server decides what prize lies in the
// picked box; the component just animates the pick.
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";


export default function MysteryBoxGame({
  config, onSubmit, submitting, result, brand, onAnimationComplete,
}) {
  const accent  = brand || "#f59e0b";
  const boxes    = config?.boxes && config.boxes.length
    ? config.boxes : [0, 1, 2];
  const [picked, setPicked] = useState(null);
  const isWin = result && result.result !== "lose";
  const prize = result?.prize;

  // Phase 23 Session 8b — gate the parent ResultModal on the reveal
  // animation completing.  Total = 1200ms reveal + 300ms buffer = 1500ms
  // (≥1200ms acceptance gate).
  useEffect(() => {
    if (!result) return;
    const t = setTimeout(() => onAnimationComplete?.(result), 1500);
    return () => clearTimeout(t);
  }, [result, onAnimationComplete]);

  const onPick = (i) => {
    if (picked !== null || submitting || result) return;
    setPicked(i);
    onSubmit?.({ box_index: i });
  };

  return (
    <div className="mystery-box-game" data-testid="mystery-box-game"
            style={{ display: "flex", flexDirection: "column",
                            alignItems: "center", gap: 16,
                            "--tpl-accent": accent }}>
      <div className="dim" style={{ fontSize: 13, opacity: 0.85,
                                                                  letterSpacing: 0.3 }}>
        Pick a box to reveal your prize
      </div>
      <div style={{ display: "flex", gap: 16 }}>
        {boxes.map((_, i) => {
          const isChosen = picked === i;
          const revealed  = isChosen && !!result;
          return (
            <div key={i}
                    onClick={() => onPick(i)}
                    data-testid={`mystery-box-${i}`}
                    data-picked={isChosen ? "true" : "false"}
                    style={{
                      width: 100, height: 100, borderRadius: 16,
                      cursor: picked === null && !submitting ? "pointer" : "default",
                      display: "flex", flexDirection: "column",
                      alignItems: "center", justifyContent: "center",
                      gap: 4, fontSize: revealed ? 30 : 56,
                      background: revealed
                        ? (isWin
                              ? `linear-gradient(135deg, ${accent}, #b45309)`
                              : "linear-gradient(135deg, #4b5563, #1f2937)")
                        : (isChosen
                              ? `linear-gradient(135deg, ${accent}88, #b4530988)`
                              : "linear-gradient(135deg, #2d1b00, #160c00)"),
                      color: "#fff",
                      boxShadow: isChosen
                        ? `0 12px 28px ${accent}55`
                        : "0 8px 22px rgba(0,0,0,0.4)",
                      opacity: picked !== null && !isChosen ? 0.35 : 1,
                      transition: "transform 200ms, opacity 200ms, background 300ms",
                      transform: isChosen
                        ? "translateY(-6px) scale(1.06)"
                        : "none",
                      border: `2px solid ${isChosen ? accent : "rgba(255,255,255,0.06)"}`,
                    }}>
              {revealed ? (
                <>
                  <div data-testid={`mystery-box-${i}-prize-emoji`}
                          style={{fontSize: 36}}>
                    {isWin ? "🎁" : "😅"}
                  </div>
                  <div data-testid={`mystery-box-${i}-prize-title`}
                          style={{fontSize: 11, fontWeight: 800,
                                          textAlign: "center", padding: "0 4px",
                                          letterSpacing: 0.2}}>
                    {prize?.title || (isWin ? "Prize!" : "Try again")}
                  </div>
                </>
              ) : (
                <span>🎁</span>
              )}
              {isChosen && submitting && (
                <Loader2 size={18} className="spin"
                                style={{position: "absolute"}}/>
              )}
            </div>
          );
        })}
      </div>
      {picked !== null && !result && submitting && (
        <div className="dim mono"
                data-testid="mystery-box-resolving">
          Opening box…
        </div>
      )}
    </div>
  );
}
