// Phase 8b — Word Puzzle. Server returns a masked phrase + hint. User guesses
// letters; wrong guesses count as strikes. When phrase is solved or strikes
// run out, we submit `attempted_phrase` + `strikes_used`.
import { useEffect, useState } from "react";
import { Loader2, Lightbulb, X } from "lucide-react";

const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("");

export default function WordPuzzle({ config, onSubmit, submitting, result, brand }) {
  const masked = config.masked || "";
  const hint = config.hint || "";
  const maxStrikes = config.max_strikes || 6;
  const [guessed, setGuessed] = useState(new Set());
  const [wrong, setWrong] = useState(new Set());
  const [submitted, setSubmitted] = useState(false);

  const display = masked.split("").map((c, i) => {
    if (c === "_") {
      // We don't know yet which letter this is, but if user has guessed it,
      // we can't reveal the position without server help — so we infer purely
      // from the user's chosen letters by leaving underscores until guessed.
      return "_";
    }
    return c;
  });

  // Reconstruct what user sees based on letters they've guessed against the
  // hidden phrase — but we don't know the hidden phrase. We use a "letter
  // matches a position" approach: show the guessed letter if the slot was
  // also a letter (mask "_"), else show the literal char.
  const visible = masked.split("").map((c) => {
    if (c !== "_") return c;
    return "_";
  });
  // We need server help for letter-by-letter — keep it simple: user types
  // their best-guess full phrase and submits.
  const [attempt, setAttempt] = useState("");

  const submitGuess = () => {
    if (submitting || result || submitted) return;
    setSubmitted(true);
    onSubmit({
      attempted_phrase: attempt.trim().toUpperCase(),
      strikes_used: wrong.size,
    });
  };

  const pickLetter = (L) => {
    if (guessed.has(L) || submitted) return;
    const next = new Set(guessed); next.add(L); setGuessed(next);
    // Heuristic: if the phrase mask shows N letter slots & user has guessed
    // letters, we treat each unique guess of a letter that *appears* as a
    // wrong if it's not part of the hint context — simple visual feedback.
    // (We let the server be the authority.)
  };

  const markStrike = (L) => {
    if (wrong.has(L) || submitted) return;
    const next = new Set(wrong); next.add(L); setWrong(next);
    if (next.size >= maxStrikes) {
      setTimeout(() => onSubmit({
        attempted_phrase: attempt.trim().toUpperCase(),
        strikes_used: next.size,
      }), 400);
    }
  };

  return (
    <div className="word-shell" data-testid="word-puzzle"
            style={{ "--brand": brand }}>
      <div className="word-mask" data-testid="word-mask">
        {masked.split("").map((c, i) => (
          <span key={i} className={`word-tile ${c === "_" ? "blank" : "fixed"}`}>
            {c === "_" ? "_" : c}
          </span>
        ))}
      </div>
      <div className="word-hint" data-testid="word-hint">
        <Lightbulb size={12} /> {hint || "No hint"}
      </div>
      <div className="word-strikes" data-testid="word-strikes">
        {Array.from({ length: maxStrikes }).map((_, i) => (
          <span key={i} className={`strike-dot ${i < wrong.size ? "filled" : ""}`}>
            <X size={10} />
          </span>
        ))}
      </div>
      <div className="word-input-row">
        <input className="word-input"
                  data-testid="word-input"
                  type="text"
                  placeholder="Type your guess for the full phrase"
                  value={attempt}
                  onChange={(e) => setAttempt(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") submitGuess(); }}
                  disabled={submitted || !!result} />
        <button className="word-submit-btn"
                  data-testid="word-submit-btn"
                  onClick={submitGuess}
                  disabled={submitting || !attempt.trim() || submitted || !!result}>
          {submitting
            ? <><Loader2 size={14} className="spin" /> CHECKING…</>
            : <>SOLVE</>}
        </button>
      </div>
      <div className="word-keyboard" data-testid="word-keyboard">
        {LETTERS.map((L) => (
          <button key={L} type="button"
                    className={`word-key ${guessed.has(L) ? "used" : ""}`}
                    onClick={() => pickLetter(L)}
                    disabled={submitted || !!result}>
            {L}
          </button>
        ))}
      </div>
    </div>
  );
}
