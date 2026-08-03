// Quiz: 1-N questions, timer, submit answers.
import { useEffect, useRef, useState } from "react";
import { Loader2, Clock } from "lucide-react";

export default function Quiz({ config, onSubmit, submitting, result, brand, onAnimationComplete }) {
  const questions = config.questions || [];
  const dynamic = questions.length === 1;
  const timePerQ = config.time_per_question_s || 15;
  const minCorrect = config.min_correct_to_win || 1;
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState([]);
  const [remaining, setRemaining] = useState(timePerQ);
  const tickRef = useRef(null);

  // Phase Stabilization (Mobile games P0) — defensive guard. If the
  // session ever arrives with 0 questions (server-side fix should
  // prevent this, but bail gracefully if it slips through) render an
  // empty state instead of a broken "Q1 / 0" stage with no content.
  if (!questions.length) {
    return (
      <div className="quiz-shell quiz-empty"
            data-testid="quiz-empty-state">
        <h3 style={{ margin: 0, marginBottom: 8, fontSize: "1.05rem" }}>
          Trivia is still being prepared
        </h3>
        <p style={{ margin: 0, fontSize: "0.85rem",
                     color: "var(--paw-text-dim)" }}>
          Questions for this campaign aren&apos;t available yet — please
          check back soon.
        </p>
      </div>
    );
  }

  // Phase 23 Session 8b — gate the parent ResultModal on ≥1000ms
  // after the final question's correct/incorrect highlight displays
  // (the "Grading…" surface already covers that window).
  useEffect(() => {
    if (!result) return;
    const t = setTimeout(() => onAnimationComplete?.(result), 1000);
    return () => clearTimeout(t);
  }, [result, onAnimationComplete]);

  useEffect(() => {
    if (submitting || result || idx >= questions.length) return;
    setRemaining(timePerQ);
    tickRef.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) {
          clearInterval(tickRef.current);
          submitAnswer(-1);     // timeout = wrong
          return 0;
        }
        return r - 1;
      });
    }, 1000);
    return () => clearInterval(tickRef.current);
    // eslint-disable-next-line
  }, [idx, questions.length]);

  const submitAnswer = (chosen) => {
    clearInterval(tickRef.current);
    const newAnswers = [...answers, chosen];
    setAnswers(newAnswers);
    if (idx + 1 >= questions.length) {
      // Submit the whole quiz
      if (dynamic) {
        onSubmit({ answer_idx: chosen });
      } else {
        onSubmit({ answers: newAnswers });
      }
    } else {
      setIdx(idx + 1);
    }
  };

  const q = questions[idx] || {};

  if (submitting || result) {
    return (
      <div className="quiz-shell submitted" data-testid="quiz-submitted">
        <Loader2 size={24} className="spin" />
        <p>Grading…</p>
      </div>
    );
  }

  return (
    <div className="quiz-shell" data-testid="quiz-stage">
      <div className="quiz-progress">
        <div className="mono">Q{idx + 1} / {questions.length}</div>
        <div className="quiz-timer mono" data-testid="quiz-timer">
          <Clock size={11} /> {remaining}s
        </div>
      </div>
      <div className="quiz-bar">
        <div className="quiz-bar-fill"
                style={{ width: `${(remaining / timePerQ) * 100}%`,
                        background: brand || "#ff2d95" }} />
      </div>
      <h2 className="quiz-prompt" data-testid="quiz-prompt">{q.prompt}</h2>
      {(q.track || q.song) && (
        <div className="quiz-subtitle mono">
          {q.song
            ? <>From <i>"{q.song}"</i>{q.artist ? ` — ${q.artist}` : ""}</>
            : <>About <i>{q.track?.title}</i>{q.track?.artist ? ` by ${q.track.artist}` : ""}</>}
        </div>
      )}
      <div className="quiz-options">
        {(q.options || []).map((opt, i) => (
          <button key={i}
                    className="quiz-option"
                    onClick={() => submitAnswer(i)}
                    data-testid={`quiz-option-${i}`}>
            <span className="quiz-option-letter">{String.fromCharCode(65 + i)}</span>
            <span>{opt}</span>
          </button>
        ))}
      </div>
      <p className="quiz-rule mono">
        Need <b>{minCorrect}</b> correct out of <b>{questions.length}</b> to win.
      </p>
    </div>
  );
}
