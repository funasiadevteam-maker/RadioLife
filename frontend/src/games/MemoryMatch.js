// Phase 8b — Memory Match. Server pre-shuffles the deck and we just play it
// back. Player clicks cards; we track flips and matches client-side, then
// submit `pairs_found` + `time_spent_sec` for the server to validate.
import { useEffect, useState, useRef } from "react";
import { Loader2, Timer, CheckCircle2 } from "lucide-react";

export default function MemoryMatch({ config, onSubmit, submitting, result, brand }) {
  const deck = config.deck || [];
  const grid = config.grid_size || 4;
  const timeLimit = config.time_limit_sec || 90;
  const [revealed, setRevealed] = useState(() => deck.map(() => false));
  const [matched, setMatched] = useState(() => deck.map(() => false));
  const [busy, setBusy] = useState(false);
  const [pairsFound, setPairsFound] = useState(0);
  const [timeLeft, setTimeLeft] = useState(timeLimit);
  const [started, setStarted] = useState(false);
  const startedRef = useRef(null);

  useEffect(() => {
    if (!started || result) return;
    const t = setInterval(() => {
      setTimeLeft((l) => Math.max(0, l - 1));
    }, 1000);
    return () => clearInterval(t);
  }, [started, result]);

  useEffect(() => {
    if (started && timeLeft === 0 && !result) {
      finalize();
    }
  }, [timeLeft, started, result]);

  const finalize = () => {
    if (!startedRef.current) return;
    const spent = (Date.now() - startedRef.current) / 1000;
    onSubmit({ pairs_found: pairsFound, time_spent_sec: spent });
  };

  const clickCard = (idx) => {
    if (busy || revealed[idx] || matched[idx] || result) return;
    if (!started) {
      setStarted(true);
      startedRef.current = Date.now();
    }
    const newRevealed = [...revealed];
    newRevealed[idx] = true;
    setRevealed(newRevealed);
    const flipped = newRevealed
      .map((v, i) => (v && !matched[i] ? i : -1))
      .filter((i) => i >= 0);
    if (flipped.length === 2) {
      setBusy(true);
      const [a, b] = flipped;
      if (deck[a].pair_idx === deck[b].pair_idx) {
        // match!
        setTimeout(() => {
          setMatched((m) => {
            const c = [...m]; c[a] = true; c[b] = true; return c;
          });
          setPairsFound((p) => {
            const np = p + 1;
            // auto-finalize when ALL pairs found
            if (np === deck.length / 2) {
              setTimeout(() => {
                const spent = (Date.now() - startedRef.current) / 1000;
                onSubmit({ pairs_found: np, time_spent_sec: spent });
              }, 400);
            }
            return np;
          });
          setBusy(false);
        }, 400);
      } else {
        setTimeout(() => {
          setRevealed((r) => {
            const c = [...r]; c[a] = false; c[b] = false; return c;
          });
          setBusy(false);
        }, 900);
      }
    }
  };

  return (
    <div className="memory-shell" data-testid="memory-match"
            style={{ "--brand": brand, "--grid": grid }}>
      <div className="memory-hud">
        <div className="hud-pill mono">
          <Timer size={12} /> {timeLeft}s
        </div>
        <div className="hud-pill mono">
          <CheckCircle2 size={12} /> {pairsFound}/{deck.length / 2}
        </div>
      </div>
      <div className="memory-grid"
              style={{ gridTemplateColumns: `repeat(${grid}, 1fr)` }}>
        {deck.map((card, i) => (
          <button key={i} type="button" className="memory-card"
                      data-testid={`memory-card-${i}`}
                      data-flipped={revealed[i] || matched[i]}
                      data-matched={matched[i]}
                      onClick={() => clickCard(i)}
                      disabled={busy || !!result}>
            <div className="memory-card-inner">
              <div className="memory-card-face memory-card-back">
                <span className="mono">BFM</span>
              </div>
              <div className="memory-card-face memory-card-front">
                <span>{card.label}</span>
              </div>
            </div>
          </button>
        ))}
      </div>
      <button className="memory-finalize-btn"
                onClick={finalize}
                disabled={!started || submitting || !!result}
                data-testid="memory-finalize-btn">
        {submitting
          ? <><Loader2 size={14} className="spin" /> CHECKING…</>
          : <>END GAME</>}
      </button>
    </div>
  );
}
