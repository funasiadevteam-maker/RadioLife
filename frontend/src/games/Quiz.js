// Quiz: 1-N questions, timer, submit answers.
import { useEffect, useRef, useState } from "react";
import { Loader2, Clock } from "lucide-react";
import { GAME_ART } from "../assets/gameArt";
import { playFx, vibrate } from "../utils/gameFX";

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
    const won = result.result === "win" || result.won === true;
    if (won) { playFx("win"); vibrate([0, 40, 30, 40]); }
    else { playFx("lose"); vibrate(20); }
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
    if (chosen >= 0) { playFx("reveal"); vibrate(12); }
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
      <div className="quiz-shell submitted" data-testid="quiz-submitted"
        style={{ display: "flex", flexDirection: "column", alignItems: "center",
          gap: 12, padding: 44, borderRadius: 24, color: "#fff",
          background: "linear-gradient(165deg, rgba(30,18,58,.96), rgba(11,12,22,.98))",
          border: "1px solid rgba(59,130,246,.3)",
          boxShadow: "0 20px 60px rgba(0,0,0,.5)" }}>
        <Loader2 size={28} className="spin" />
        <p style={{ margin: 0, fontWeight: 800 }}>Grading your answers…</p>
      </div>
    );
  }

  const lowTime = remaining <= 5;
  return (
    <div className="quiz-shell" data-testid="quiz-stage"
      style={{ display: "flex", flexDirection: "column", gap: 16, padding: 18,
        borderRadius: 24,
        background: "linear-gradient(165deg, rgba(30,18,58,.96), rgba(11,12,22,.98))",
        border: "1px solid rgba(59,130,246,.3)",
        boxShadow: "0 20px 60px rgba(0,0,0,.5)" }}>
      {/* AI-art header band */}
      <div style={{ position: "relative", borderRadius: 16, overflow: "hidden",
        minHeight: 96, display: "flex", alignItems: "flex-end", padding: 14,
        backgroundImage: `linear-gradient(90deg, rgba(14,8,34,.92), rgba(14,8,34,.3)), url(${GAME_ART.trivia})`,
        backgroundSize: "cover", backgroundPosition: "center" }}>
        <div>
          <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: ".12em", color: "#93c5fd" }}>
            MUSIC TRIVIA
          </div>
          <div style={{ fontSize: 16, fontWeight: 900, color: "#fff", marginTop: 2 }}>
            Answer fast — win bigger
          </div>
        </div>
        <div data-testid="quiz-timer"
          style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6,
            background: "rgba(0,0,0,.5)", backdropFilter: "blur(4px)",
            padding: "7px 13px", borderRadius: 999, fontWeight: 900, fontSize: 15,
            color: lowTime ? "#f87171" : "#fff",
            border: `1px solid ${lowTime ? "rgba(248,113,113,.6)" : "rgba(255,255,255,.2)"}` }}>
          <Clock size={13} /> {remaining}s
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
        fontSize: 12, fontWeight: 800, color: "#c4b5fd" }}>
        <span>Question {idx + 1} of {questions.length}</span>
        <span>Need {minCorrect} correct to win</span>
      </div>

      {/* Timer bar */}
      <div style={{ height: 8, borderRadius: 999, background: "rgba(255,255,255,.08)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${(remaining / timePerQ) * 100}%`,
          background: lowTime
            ? "linear-gradient(90deg,#f87171,#ef4444)"
            : "linear-gradient(90deg,#60a5fa,#a855f7)",
          transition: "width 1s linear" }} />
      </div>

      <h2 data-testid="quiz-prompt"
        style={{ fontSize: 20, fontWeight: 900, color: "#fff", margin: 0, lineHeight: 1.25 }}>
        {q.prompt}
      </h2>
      {(q.track || q.song) && (
        <div style={{ fontSize: 12.5, color: "#a5b4fc" }}>
          {q.song
            ? <>From <i>"{q.song}"</i>{q.artist ? ` — ${q.artist}` : ""}</>
            : <>About <i>{q.track?.title}</i>{q.track?.artist ? ` by ${q.track.artist}` : ""}</>}
        </div>
      )}

      <div style={{ display: "grid", gap: 10 }}>
        {(q.options || []).map((opt, i) => (
          <button key={i} onClick={() => submitAnswer(i)} data-testid={`quiz-option-${i}`}
            style={{ display: "flex", alignItems: "center", gap: 12, textAlign: "left",
              cursor: "pointer", padding: "14px 16px", borderRadius: 14, color: "#fff",
              background: "rgba(255,255,255,.05)", border: "1px solid rgba(255,255,255,.12)",
              fontSize: 15, fontWeight: 700,
              transition: "transform .12s ease, background .12s ease, border-color .12s ease" }}
            onMouseEnter={(e) => { e.currentTarget.style.background = "rgba(59,130,246,.18)"; e.currentTarget.style.borderColor = "#3b82f6"; e.currentTarget.style.transform = "translateY(-2px)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = "rgba(255,255,255,.05)"; e.currentTarget.style.borderColor = "rgba(255,255,255,.12)"; e.currentTarget.style.transform = "none"; }}>
            <span style={{ display: "grid", placeItems: "center", width: 30, height: 30,
              flexShrink: 0, borderRadius: 9, fontSize: 14, fontWeight: 900, color: "#fff",
              background: "linear-gradient(135deg,#3b82f6,#a855f7)" }}>
              {String.fromCharCode(65 + i)}
            </span>
            <span>{opt}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
