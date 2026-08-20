// Phase 16a — Single-player trivia gameplay.
//   Start ⇒ /api/trivia/sessions/start with category_id query param.
//   Loops through 10 questions, posts /answer per click, shows reveal,
//   then /finish on the last one + animates BigPoints reward.
import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams, useLocation } from "react-router-dom";
import axios from "axios";
import { Brain, Check, X, Sparkles, Coins, ChevronRight, Loader2, RotateCcw, Share2 } from "lucide-react";
import { toast } from "sonner";
import { Card, Button, Chip, LiveDot } from "@/shell/primitives";
import { API } from "@/AuthContext";

const PER_Q_TIMEOUT_SEC = 30;

export default function TriviaPlay() {
  const navigate     = useNavigate();
  const location     = useLocation();
  const [sp]         = useSearchParams();
  const categoryId   = sp.get("cat") || "";

  const [session, setSession]     = useState(null);
  const [qIndex, setQIndex]       = useState(0);
  const [reveal, setReveal]       = useState(null); // { correct, points, correct_choice_id }
  const [chosen, setChosen]       = useState(null);
  const [score, setScore]         = useState(0);
  const [loading, setLoading]     = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [finished, setFinished]   = useState(null);
  const [now, setNow]             = useState(Date.now());

  const qStartRef = useRef(Date.now()); // local timer for the per-Q UI bar

  // ─── Boot: start the session ──────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    if (!categoryId) { navigate("/trivia", { replace: true }); return; }
    (async () => {
      try {
        const r = await axios.post(`${API}/trivia/sessions/start`, {
          category_id: categoryId, difficulty: 2,
        });
        if (cancelled) return;
        setSession(r.data);
        qStartRef.current = Date.now();
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Failed to start trivia.");
        navigate("/trivia", { replace: true });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [categoryId, navigate]);

  // ─── Local 30-s countdown for the question bar ────────────────────────
  useEffect(() => {
    if (!session || reveal || finished) return;
    const t = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(t);
  }, [session, reveal, finished, qIndex]);

  const currentQ = useMemo(() => {
    if (!session) return null;
    return session.questions[qIndex] || null;
  }, [session, qIndex]);

  const elapsedSec  = (now - qStartRef.current) / 1000;
  const remainingSec = Math.max(0, PER_Q_TIMEOUT_SEC - elapsedSec);
  const timeoutPct  = Math.min(100, (elapsedSec / PER_Q_TIMEOUT_SEC) * 100);

  const onChoose = async (choiceId) => {
    if (!currentQ || reveal || submitting) return;
    setSubmitting(true);
    setChosen(choiceId);
    try {
      const r = await axios.post(
        `${API}/trivia/sessions/${session.session_id}/answer`,
        { question_id: currentQ.id, choice_id: choiceId },
      );
      setReveal(r.data);
      setScore(r.data.running_score);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 408) {
        setReveal({ correct: false, correct_choice_id: null, points_awarded: 0,
                      running_score: score, timed_out: true });
        toast.error("Out of time.");
      } else {
        toast.error(typeof detail === "string" ? detail : "Failed to submit.");
        setChosen(null);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onNext = async () => {
    if (!session) return;
    const nextIdx = qIndex + 1;
    if (nextIdx >= session.questions.length) {
      // Finish the session.
      try {
        const r = await axios.post(`${API}/trivia/sessions/${session.session_id}/finish`);
        setFinished(r.data);
      } catch (_e) {
        toast.error("Failed to finalise score.");
      }
      return;
    }
    setQIndex(nextIdx);
    setChosen(null);
    setReveal(null);
    qStartRef.current = Date.now();
  };

  // ─── Final screen ─────────────────────────────────────────────────────
  if (finished) {
    return (
      <div data-testid="trivia-final" className="max-w-xl mx-auto space-y-6 pb-24">
        <Card className="p-8 text-center space-y-4">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                text-text-secondary flex items-center gap-2 justify-center">
            <LiveDot /> Session complete
          </div>
          <h1 className="font-display font-bold text-5xl
                                tracking-display-tight text-accent-electric"
                data-testid="trivia-final-score">
            {finished.final_score}
          </h1>
          <div className="text-text-secondary text-sm">
            {finished.correct} / {finished.total} correct
          </div>
          <div className="flex items-center justify-center gap-2 text-accent-gold
                                  font-mono text-lg"
                data-testid="trivia-final-bc">
            <Coins size={18} />
            +{finished.bigcoin_awarded} BigPoints awarded
          </div>
          <div className="flex gap-3 justify-center pt-4">
            <Button variant="primary" onClick={() => navigate("/trivia")}
                        data-testid="trivia-final-again">
              <RotateCcw size={14} /> Play again
            </Button>
            <Button variant="ghost" onClick={async () => {
              const url = window.location.origin + "/trivia";
              try {
                if (navigator.share) await navigator.share({
                  title: "RadioLife Trivia", text: `I scored ${finished.final_score} on RadioLife Trivia.`, url,
                });
                else {
                  await navigator.clipboard.writeText(url);
                  toast.success("Trivia link copied — share away.");
                }
              } catch (_) { /* user cancelled */ }
            }} data-testid="trivia-final-share">
              <Share2 size={14} /> Share
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (loading || !session || !currentQ) {
    // Phase UX.1 — show the topic name in the loading state so it
    // feels like the click was acknowledged rather than a generic
    // "warming up".
    const topicName = location.state?.categoryName;
    const topicIcon = location.state?.categoryIcon;
    return (
      <div className="max-w-xl mx-auto pt-20 text-center text-text-secondary"
              data-testid="trivia-loading">
        {topicIcon && (
          <div className="text-5xl mb-4 select-none" aria-hidden>
            {topicIcon}
          </div>
        )}
        <Loader2 className="animate-spin inline-block mr-2" size={18} />
        {topicName
          ? <>Generating your <span className="text-accent-magenta font-semibold">{topicName}</span> trivia…</>
          : "Warming up the question bank…"}
        <div className="text-xs text-text-secondary/70 mt-2">
          10 questions, server-timed.  Hang tight — usually 5-15 s.
        </div>
      </div>
    );
  }

  return (
    <div data-testid="trivia-play" className="max-w-xl mx-auto space-y-5 pb-24">
      {/* Top bar — Q-of-N, score, timer */}
      <div className="flex items-center justify-between text-[10px]
                              font-mono uppercase tracking-widest
                              text-text-secondary">
        <span data-testid="trivia-progress">
          Q {qIndex + 1} / {session.questions.length}
        </span>
        <span data-testid="trivia-score" className="text-accent-electric">
          Score · {score}
        </span>
      </div>

      <div className="h-1 rounded-full overflow-hidden bg-white/[0.06]">
        <div
          data-testid="trivia-timer-bar"
          className={`h-full transition-all duration-100 ${
            remainingSec < 5 ? "bg-accent-magenta" : "bg-accent-electric"
          }`}
          style={{ width: `${100 - timeoutPct}%` }}
        />
      </div>

      <Card className="p-6 space-y-5">
        <div className="flex items-center gap-2 text-[10px] font-mono
                                uppercase tracking-widest text-text-secondary">
          <Brain size={12} /> {currentQ.category || "trivia"} · diff {currentQ.difficulty}
        </div>
        <h2 className="font-display font-bold text-2xl
                              tracking-display-tight"
              data-testid="trivia-prompt">
          {currentQ.prompt}
        </h2>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                data-testid="trivia-choices">
          {currentQ.choices.map((c) => {
            const isChosen     = chosen === c.id;
            const isCorrect    = reveal?.correct_choice_id === c.id;
            const isWrongPick = reveal && isChosen && !reveal.correct;
            return (
              <button
                key={c.id}
                type="button"
                disabled={!!reveal || submitting}
                onClick={() => onChoose(c.id)}
                data-testid={`trivia-choice-${c.id}`}
                className={[
                  "rounded-token-card border px-4 py-3 text-left text-sm",
                  "transition-colors duration-150 ease-out150",
                  "flex items-center gap-3 disabled:cursor-default",
                  reveal
                    ? (isCorrect
                          ? "border-accent-mint/70 bg-accent-mint/10"
                          : isWrongPick
                              ? "border-accent-magenta/70 bg-accent-magenta/10"
                              : "border-white/[0.05] opacity-60")
                    : (isChosen
                          ? "border-accent-electric/80 bg-accent-electric/10"
                          : "border-white/[0.08] hover:border-accent-electric/40 hover:bg-white/[0.03]"),
                ].join(" ")}
              >
                <span className="font-mono text-[10px] text-text-faint">
                  {c.id.toUpperCase()}
                </span>
                <span className="flex-1">{c.text}</span>
                {reveal && isCorrect &&    <Check size={16} className="text-accent-mint" />}
                {reveal && isWrongPick && <X size={16} className="text-accent-magenta" />}
              </button>
            );
          })}
        </div>

        {reveal && (
          <div className="rounded-token-md border border-white/[0.08]
                                p-4 flex items-center justify-between"
                data-testid="trivia-reveal">
            <div>
              {reveal.timed_out ? (
                <div className="text-accent-magenta font-display font-bold">
                  Time up — no points awarded.
                </div>
              ) : reveal.correct ? (
                <div className="text-accent-mint font-display font-bold">
                  Correct! +{reveal.points_awarded} points
                  {reveal.points_awarded > 100 && (
                    <span className="ml-2 text-[10px] font-mono
                                              uppercase tracking-widest text-accent-gold">
                      <Sparkles size={10} className="inline" /> speed bonus
                    </span>
                  )}
                </div>
              ) : (
                <div className="text-accent-magenta font-display font-bold">
                  Not quite — answer was {reveal.correct_choice_id?.toUpperCase()}.
                </div>
              )}
            </div>
            <Button variant="primary" size="sm" onClick={onNext}
                        data-testid="trivia-next">
              {qIndex + 1 >= session.questions.length ? "Finish" : "Next"}
              <ChevronRight size={14} />
            </Button>
          </div>
        )}
      </Card>
    </div>
  );
}
