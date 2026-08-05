// Phase 16b — Multiplayer trivia: Create / Join / Room (lobby + game).
//
// One page handles all 4 surfaces driven by the URL:
//   /trivia/rooms/create    — host pick category + create
//   /trivia/join             — enter code, redirect to room
//   /trivia/rooms/:code     — lobby + gameplay + final
//
// Single WebSocket per page lifetime via `useTriviaRoom`.
import React, { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import {
  Users, Copy, ChevronRight, Crown, Check, X, Loader2, Trophy, Coins, Share2, Sparkles, Gift,
} from "lucide-react";
import { Card, Button, Chip, LiveDot } from "@/shell/primitives";
import { API } from "@/AuthContext";
import { useTriviaRoom } from "@/store/useTriviaRoom";

// ─── /trivia/rooms/create ────────────────────────────────────────────
export function TriviaRoomCreate() {
  const navigate = useNavigate();
  const [cats, setCats]   = useState([]);
  const [chosen, setChosen] = useState(null);
  const [busy, setBusy]   = useState(false);

  useEffect(() => {
    axios.get(`${API}/trivia/categories`).then((r) =>
      setCats(r.data?.categories || [])
    ).catch(() => {});
  }, []);

  const createRoom = async () => {
    if (!chosen || busy) return;
    setBusy(true);
    try {
      const r = await axios.post(`${API}/trivia/rooms`,
        { category_id: chosen.id, is_private: false });
      navigate(`/trivia/rooms/${r.data.room_code}`, { replace: true });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to create room");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="trivia-room-create" className="max-w-xl mx-auto pb-24 space-y-5">
      <h1 className="font-display font-bold text-3xl tracking-display-tight">
        Host a <span className="text-accent-magenta">live room</span>
      </h1>
      <p className="text-text-secondary text-sm">
        Pick a topic, share the code, beat your friends.  10 questions, 15 seconds each.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {cats.map((c) => (
          <Card key={c.id} hoverable
                  onClick={() => setChosen(c)}
                  data-testid={`trivia-room-cat-${c.id}`}
                  className={`p-4 cursor-pointer ${chosen?.id === c.id
                    ? "border-accent-electric/80 bg-accent-electric/5" : ""}`}>
            <div className="flex items-center gap-3">
              <div className="text-2xl">{c.icon || "🧠"}</div>
              <div className="flex-1">
                <div className="font-display font-bold text-base">{c.name}</div>
                {c.tagline && <div className="text-xs text-text-secondary">{c.tagline}</div>}
              </div>
              {chosen?.id === c.id && <Check size={18} className="text-accent-electric" />}
            </div>
          </Card>
        ))}
      </div>
      <Button variant="primary" disabled={!chosen || busy}
                  onClick={createRoom} data-testid="trivia-room-create-btn">
        {busy ? <Loader2 className="animate-spin" size={14} /> : null}
        Create room <ChevronRight size={14} />
      </Button>
    </div>
  );
}

// Canonical room code: accepts variants like "bfm-xjg979", "BFMXJG979",
// "xjg979", " BFM XJG-979 " → "BFM-XJG979".  Mirrors backend
// `normalize_room_code` so client + server always agree.
function normalizeRoomCode(raw) {
  let s = (raw || "").trim().toUpperCase().replace(/[^A-Z0-9-]/g, "");
  // Strip any leading "BFM-" or "BFM" so we re-attach cleanly.
  s = s.replace(/^BFM-?/, "");
  // Drop any leftover hyphens inside the body — only the prefix hyphen survives.
  s = s.replace(/-/g, "");
  return s ? `BFM-${s}` : "";
}

// ─── /trivia/join ────────────────────────────────────────────────────
export function TriviaJoin() {
  const navigate = useNavigate();
  const [sp]     = useSearchParams();
  const [code, setCode] = useState((sp.get("code") || "").toUpperCase());
  const canon = normalizeRoomCode(code);
  // Valid shape: BFM- followed by 4-12 chars (server enforces 6, but be lenient).
  const looksValid = /^BFM-[A-Z0-9]{4,12}$/.test(canon);

  const go = (e) => {
    e?.preventDefault?.();
    if (!looksValid) {
      toast.error("Enter a code that looks like BFM-XJG979.");
      return;
    }
    navigate(`/trivia/rooms/${canon}`);
  };
  const onPaste = (e) => {
    const pasted = (e.clipboardData || window.clipboardData).getData("text");
    if (pasted) {
      e.preventDefault();
      setCode(pasted);
    }
  };
  return (
    <form onSubmit={go} data-testid="trivia-join"
            className="max-w-md mx-auto pb-24 pt-8 space-y-4">
      <h1 className="font-display font-bold text-3xl tracking-display-tight">
        Join a <span className="text-accent-electric">live room</span>
      </h1>
      <p className="text-text-secondary text-sm">
        Paste or type the 10-char code your host shared (e.g.&nbsp;
        <span className="font-mono text-text-primary">BFM-XJG979</span>).
      </p>
      <input
        type="text"
        value={code}
        onChange={(e) => setCode(e.target.value.toUpperCase())}
        onPaste={onPaste}
        placeholder="BFM-XXXXXX"
        autoFocus
        className="w-full px-4 py-3 rounded-token-card border border-white/[0.10]
                          bg-bg-glass font-mono tracking-widest text-center text-xl
                          focus:border-accent-electric/70 outline-none"
        data-testid="trivia-join-input"
      />
      {code && (
        <div className="font-mono text-[10px] text-text-secondary text-center"
              data-testid="trivia-join-preview">
          Will join: <span className="text-accent-electric">{canon || "—"}</span>
        </div>
      )}
      <Button variant="primary" type="submit" data-testid="trivia-join-btn"
                  disabled={!looksValid}>
        Join room <ChevronRight size={14} />
      </Button>
    </form>
  );
}

// ─── /trivia/rooms/:code ─────────────────────────────────────────────
export function TriviaRoom() {
  const { code }     = useParams();
  const navigate     = useNavigate();
  const connect      = useTriviaRoom((s) => s.connect);
  const disconnect  = useTriviaRoom((s) => s.disconnect);
  const sendAnswer  = useTriviaRoom((s) => s.sendAnswer);
  const ws            = useTriviaRoom((s) => s.ws);
  const room          = useTriviaRoom((s) => s.room);
  const phase         = useTriviaRoom((s) => s.phase);
  const question     = useTriviaRoom((s) => s.question);
  const deadlineMs  = useTriviaRoom((s) => s.deadlineMs);
  const serverSkew  = useTriviaRoom((s) => s.serverSkewMs);
  const you           = useTriviaRoom((s) => s.you);
  const reveal        = useTriviaRoom((s) => s.reveal);
  const leaderboard = useTriviaRoom((s) => s.leaderboard);
  const finalScores = useTriviaRoom((s) => s.finalScores);
  const sponsorPrizes = useTriviaRoom((s) => s.sponsorPrizes) || [];
  const answersIn   = useTriviaRoom((s) => s.answersIn);
  const totalPlayers = useTriviaRoom((s) => s.totalPlayers);
  const connected   = useTriviaRoom((s) => s.connected);
  const kicked       = useTriviaRoom((s) => s.kicked);
  const error         = useTriviaRoom((s) => s.error);
  const announcement = useTriviaRoom((s) => s.announcement);

  const [chosenId, setChosenId] = useState(null);
  const [now, setNow]            = useState(Date.now());

  // Connect once on mount, disconnect on unmount.
  useEffect(() => {
    connect(code);
    return () => disconnect();
  }, [code, connect, disconnect]);

  // Host kicked us — toast + bounce back to the trivia hub.
  useEffect(() => {
    if (!kicked) return;
    toast.error("You've been removed from this room");
    navigate("/trivia", { replace: true });
  }, [kicked, navigate]);

  // Fatal WS error (room_not_found, unauthorized, mid-game lock) →
  // toast + redirect.  Transient errors set `error` too but the close
  // handler short-circuits the reconnect for these codes only.
  useEffect(() => {
    if (!error) return;
    if (error.code === "room_not_found") {
      toast.error(`No room with code ${code}. Double-check or ask the host.`);
      navigate("/trivia/join", { replace: true });
    } else if (error.code === "room_in_progress") {
      toast.error("Room is mid-game — wait for the next round.");
      navigate("/trivia", { replace: true });
    } else if (error.code === "unauthorized") {
      toast.error("Sign in to join a live room.");
      navigate("/login", { replace: true });
    }
  }, [error, code, navigate]);

  // 100ms timer for the countdown bar.
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, []);

  // Reset chosen on new question.
  useEffect(() => { setChosenId(null); }, [question?.id]);

  const isHost = you?.user_id && room?.host_user_id === you.user_id;
  const remainingMs = deadlineMs
    ? Math.max(0, deadlineMs - (now - serverSkew))
    : 0;
  const phaseTotalMs = phase === "question" ? 15000
                          : phase === "reveal" ? 4000
                          : phase === "leaderboard" ? 4000
                          : 0;
  const timerPct = phaseTotalMs > 0
    ? Math.max(0, Math.min(100, (remainingMs / phaseTotalMs) * 100))
    : 0;

  const startGame = async () => {
    try {
      await axios.post(`${API}/trivia/rooms/${code}/start`);
    } catch (e) {
      // FastAPI puts structured payloads under `detail`.  Older
      // string-detail errors still work via the fallback chain.
      const d = e?.response?.data?.detail;
      const msg = (d && typeof d === "object" && d.message)
                ? d.message
                : (typeof d === "string" ? d : "Failed to start the round.");
      toast.error(msg);
    }
  };

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      toast.success("Room code copied");
    } catch {
      toast.error("Couldn't copy — copy by hand");
    }
  };

  const inviteUrl = useMemo(
    () => `${window.location.origin}/trivia/join?code=${code}`,
    [code],
  );
  const shareInvite = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ title: "Join my RadioLife trivia room",
                                       text: `Code: ${code}`, url: inviteUrl });
      } else {
        await navigator.clipboard.writeText(inviteUrl);
        toast.success("Invite link copied");
      }
    } catch { /* user cancelled */ }
  };

  if (!ws || !room) {
    return <div className="max-w-md mx-auto pt-10 text-center text-text-secondary"
                      data-testid="trivia-room-connecting">
        <Loader2 size={18} className="inline animate-spin mr-2" />
        Joining room…
      </div>;
  }

  return (
    <div className="max-w-3xl mx-auto pb-24 space-y-5"
            data-testid="trivia-room" data-phase={phase}>
      {announcement && (
        <div className="rounded-2xl border-2 border-accent-magenta bg-accent-magenta/[0.08]
                                px-5 py-4 flex items-center gap-4 animate-in fade-in"
              data-testid="trivia-room-announcement">
          {announcement.emoji && (
            <div className="text-4xl leading-none">{announcement.emoji}</div>
          )}
          <div className="flex-1 min-w-0">
            <div className="text-[10px] uppercase tracking-[0.3em] text-accent-magenta font-mono">
              From {announcement.venue_name || "the venue"}
            </div>
            <div className="font-display font-bold text-lg tracking-display-tight">
              {announcement.message}
            </div>
          </div>
        </div>
      )}
      {/* ── Top strip: code, players, connection ──────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="font-mono font-bold text-xl tracking-widest
                                  text-accent-electric"
                data-testid="trivia-room-code">{code}</div>
          <button type="button" onClick={copyCode} data-testid="trivia-room-copy"
                      className="p-1.5 rounded-md border border-white/[0.10]
                                          hover:border-accent-electric/40">
            <Copy size={14} />
          </button>
          <button type="button" onClick={shareInvite} data-testid="trivia-room-share"
                      className="p-1.5 rounded-md border border-white/[0.10]
                                          hover:border-accent-electric/40">
            <Share2 size={14} />
          </button>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono
                                  uppercase tracking-widest text-text-secondary">
          <LiveDot color={connected ? "green" : "red"} />
          <Users size={12} /> {room.players.length}/{room.max_players}
        </div>
      </div>

      {/* Phase H — Trivia sponsorship chip (AD.5). */}
      {room.sponsorship && (
        <div className="flex items-center gap-2 rounded-full bg-fuchsia-500/10
                                        border border-fuchsia-500/40 text-fuchsia-300 px-3 py-1.5
                                        text-[11px] font-mono uppercase tracking-widest"
                    data-testid="trivia-room-sponsor-chip">
          <Sparkles size={12} className="text-fuchsia-400" />
          Sponsored by {room.sponsorship.display_name}
          {room.sponsorship.tagline && (
            <span className="text-text-secondary normal-case tracking-normal ml-1">
              · {room.sponsorship.tagline}
            </span>
          )}
        </div>
      )}

      {/* ── Lobby ─────────────────────────────────────────────────── */}
      {phase === "lobby" && (
        <Card className="p-6 space-y-4" data-testid="trivia-room-lobby">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary">Lobby · waiting to start</div>
          <h2 className="font-display font-bold text-2xl tracking-display-tight">
            {room.players.length === 1 ? "Just you for now." : "Players in"}
          </h2>
          <ul className="space-y-2" data-testid="trivia-room-players">
            {room.players.map((p) => (
              <li key={p.user_id}
                    data-testid={`trivia-room-player-${p.user_id}`}
                    className="flex items-center gap-3 px-3 py-2 rounded-token-md
                                            border border-white/[0.06]">
                <div className="w-7 h-7 rounded-full bg-bg-3 grid place-items-center
                                          font-mono text-xs text-text-secondary">
                  {(p.name || "?")[0]}
                </div>
                <span className="font-display text-sm">{p.name}</span>
                {p.user_id === room.host_user_id && (
                  <span className="text-accent-gold flex items-center gap-1
                                            text-[10px] font-mono uppercase tracking-widest">
                    <Crown size={10} /> Host
                  </span>
                )}
                <span className={`ml-auto w-2 h-2 rounded-full ${
                  p.connected ? "bg-accent-mint" : "bg-text-faint"
                }`} />
              </li>
            ))}
          </ul>
          {isHost ? (
            <>
              <Button variant="primary" onClick={startGame}
                          disabled={room.players.length < 2}
                          data-testid="trivia-room-start">
                Start round <ChevronRight size={14} />
              </Button>
              {room.players.length < 2 && (
                <div className="text-xs text-text-secondary"
                      data-testid="trivia-room-start-hint">
                  Need <span className="text-accent-magenta font-mono">1 more player</span> to start.
                  Share the code <span className="font-mono text-accent-electric">{code}</span> with a friend,
                  or <button type="button" onClick={() => navigate("/trivia/play")}
                                  className="underline hover:text-text-primary">
                    practice solo
                  </button>.
                </div>
              )}
            </>
          ) : (
            <div className="text-sm text-text-secondary">
              Waiting for the host to start…
            </div>
          )}
        </Card>
      )}

      {/* ── Active question / reveal ─────────────────────────────── */}
      {(phase === "question" || phase === "reveal") && question && (
        <>
          <div className="h-1 rounded-full overflow-hidden bg-white/[0.06]">
            <div
              data-testid="trivia-room-timer"
              className="h-full bg-accent-electric transition-all duration-100"
              style={{ width: `${timerPct}%` }}
            />
          </div>
          <Card className="p-6 space-y-5" data-testid="trivia-room-question">
            <div className="flex items-center justify-between
                                    text-[10px] font-mono uppercase tracking-widest
                                    text-text-secondary">
              <span>Q {(room.current_index ?? 0) + 1} / {room.total_questions || 10}</span>
              <span>{answersIn}/{totalPlayers || room.players.length} answered</span>
            </div>
            <h2 className="font-display font-bold text-2xl tracking-display-tight"
                  data-testid="trivia-room-prompt">
              {question.prompt}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3"
                    data-testid="trivia-room-choices">
              {question.choices.map((c) => {
                const isChosen = chosenId === c.id;
                const isCorrect = reveal && reveal.correct_choice_id === c.id;
                const isWrongPick = reveal && isChosen && !isCorrect;
                return (
                  <button
                    key={c.id}
                    type="button"
                    disabled={phase !== "question" || !!chosenId}
                    onClick={() => { setChosenId(c.id); sendAnswer(question.id, c.id); }}
                    data-testid={`trivia-room-choice-${c.id}`}
                    className={[
                      "rounded-token-card border px-4 py-3 text-left text-sm",
                      "flex items-center gap-3 disabled:cursor-default",
                      "transition-colors duration-150",
                      phase === "reveal"
                        ? (isCorrect
                              ? "border-accent-mint/70 bg-accent-mint/10"
                              : isWrongPick
                                  ? "border-accent-magenta/70 bg-accent-magenta/10"
                                  : "border-white/[0.05] opacity-60")
                        : (isChosen
                              ? "border-accent-electric/80 bg-accent-electric/10"
                              : "border-white/[0.08] hover:border-accent-electric/40"),
                    ].join(" ")}
                  >
                    <span className="font-mono text-[10px] text-text-faint">
                      {c.id.toUpperCase()}
                    </span>
                    <span className="flex-1">{c.text}</span>
                    {phase === "reveal" && isCorrect &&
                      <Check size={16} className="text-accent-mint" />}
                    {phase === "reveal" && isWrongPick &&
                      <X size={16} className="text-accent-magenta" />}
                  </button>
                );
              })}
            </div>
          </Card>
        </>
      )}

      {/* ── Between-question leaderboard ─────────────────────────── */}
      {phase === "leaderboard" && (
        <Card className="p-6 space-y-4" data-testid="trivia-room-leaderboard">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary">Standings</div>
          <ul className="space-y-2">
            {leaderboard.map((p) => (
              <li key={p.user_id}
                    data-testid={`trivia-room-lb-${p.user_id}`}
                    className="flex items-center gap-3 px-3 py-2 rounded-token-md
                                            border border-white/[0.06]">
                <span className="font-mono text-text-faint w-6">#{p.rank}</span>
                <span className="font-display flex-1">{p.name}</span>
                <span className="font-mono text-accent-electric">{p.score}</span>
              </li>
            ))}
          </ul>
        </Card>
      )}

      {/* ── Final scoreboard ─────────────────────────────────────── */}
      {phase === "done" && (
        <Card className="p-6 space-y-4" data-testid="trivia-room-final">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary flex items-center gap-2">
            <Trophy size={12} /> Final scoreboard
          </div>
          <ul className="space-y-2">
            {finalScores.map((p) => (
              <li key={p.user_id}
                    data-testid={`trivia-room-final-${p.user_id}`}
                    className="flex items-center gap-3 px-3 py-2 rounded-token-md
                                            border border-white/[0.06]">
                <span className="font-mono text-text-faint w-6">#{p.rank}</span>
                <span className="font-display flex-1">{p.name}</span>
                <span className="font-mono text-accent-electric">{p.score}</span>
                <span className="font-mono text-accent-gold text-xs flex items-center gap-1">
                  <Coins size={12} /> +{p.bigcoin_awarded}
                </span>
              </li>
            ))}
          </ul>
          <Button variant="primary"
                      onClick={() => navigate("/trivia")}
                      data-testid="trivia-room-finish-back">
            Back to trivia <ChevronRight size={14} />
          </Button>
        </Card>
      )}

      {/* Phase H — AD.5 sponsor prizes.  Shown when the current user
              won a sponsored prize in this room.  Redirects to the wallet on
              Claim (wallet already has trivia_prize_reward filtering). */}
      {phase === "done" && (sponsorPrizes || []).length > 0 && (
        <MySponsorPrizes prizes={sponsorPrizes} navigate={navigate}
                                          myUserId={you?.user_id} />
      )}
    </div>
  );
}


function MySponsorPrizes({ prizes, navigate, myUserId }) {
  const mine = (prizes || []).filter((p) => p.user_id === myUserId);
  if (mine.length === 0) return null;
  const claim = async (award_id) => {
    try {
      await axios.post(`${API}/user/trivia-prize-awards/${award_id}/claim`,
                                    {}, { withCredentials: true });
      toast.success("Prize claimed! Check your wallet.");
      navigate("/wallet");
    } catch (e) {
      toast.error("Claim failed — try from your wallet page.");
    }
  };
  return (
    <Card className="mt-4"
                data-testid="trivia-room-sponsor-prizes">
      <div className="text-[10px] font-mono uppercase tracking-widest
                                    text-fuchsia-400 mb-2 inline-flex items-center gap-1">
        <Gift size={12} /> Sponsored prizes won
      </div>
      <div className="space-y-2">
        {mine.map((p) => (
          <div key={p.award_id}
                      data-testid={`trivia-room-sponsor-prize-${p.award_id}`}
                      className="flex items-center gap-3 rounded-lg bg-fuchsia-500/10
                                                border border-fuchsia-500/40 p-3">
            <div className="w-9 h-9 rounded-full grid place-items-center
                                        bg-fuchsia-500/25 shrink-0">
              <Sparkles size={16} className="text-fuchsia-300" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-black">
                Rank #{p.rank} — {p.currency === "usd"
                  ? `$${(p.points_awarded / 100).toFixed(2)} voucher`
                  : `+${p.points_awarded} BigCoin`}
              </div>
              <div className="text-[11px] text-text-secondary truncate">
                From {p.sponsor_display_name}
              </div>
            </div>
            <Button variant="secondary" size="sm"
                            onClick={() => claim(p.award_id)}
                            data-testid={`trivia-room-sponsor-claim-${p.award_id}`}>
              Claim
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}
