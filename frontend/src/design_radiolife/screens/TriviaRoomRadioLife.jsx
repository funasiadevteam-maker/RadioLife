/** Phase C — RadioLife (light) variant of /trivia/rooms/:code.
 *
 *  Uses the same `useTriviaRoom` zustand store as the Legacy page, so
 *  the WebSocket / state machine / scoring is shared.  Only the visual
 *  shell + palette differ.
 *
 *  Overlay is mounted outside `<Routes>`; parse the code from pathname.
 */
import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { Loader2, Users, Copy, Share2, Crown, Trophy, Coins,
                  Check, X, ChevronRight } from "lucide-react";
import { API } from "@/AuthContext";
import { useTriviaRoom } from "@/store/useTriviaRoom";

export default function TriviaRoomRadioLife() {
  const { pathname } = useLocation();
  const code = pathname.startsWith("/trivia/rooms/")
    ? decodeURIComponent(
          pathname.slice("/trivia/rooms/".length).split("/")[0])
    : "";
  const navigate = useNavigate();
  const connect              = useTriviaRoom((s) => s.connect);
  const disconnect          = useTriviaRoom((s) => s.disconnect);
  const sendAnswer          = useTriviaRoom((s) => s.sendAnswer);
  const ws                        = useTriviaRoom((s) => s.ws);
  const room                    = useTriviaRoom((s) => s.room);
  const phase                  = useTriviaRoom((s) => s.phase);
  const question              = useTriviaRoom((s) => s.question);
  const deadlineMs          = useTriviaRoom((s) => s.deadlineMs);
  const serverSkewMs      = useTriviaRoom((s) => s.serverSkewMs);
  const you                      = useTriviaRoom((s) => s.you);
  const reveal                  = useTriviaRoom((s) => s.reveal);
  const leaderboard        = useTriviaRoom((s) => s.leaderboard);
  const finalScores        = useTriviaRoom((s) => s.finalScores);
  const sponsorPrizes    = useTriviaRoom((s) => s.sponsorPrizes) || [];
  const answersIn            = useTriviaRoom((s) => s.answersIn);
  const totalPlayers      = useTriviaRoom((s) => s.totalPlayers);
  const connected            = useTriviaRoom((s) => s.connected);

  const [chosenId, setChosenId] = useState(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => { connect(code); return () => disconnect(); },
                    [code, connect, disconnect]);
  useEffect(() => { setChosenId(null); }, [question?.id]);
  useEffect(() => {
    if (phase !== "question") return;
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, [phase]);

  const isHost = room?.host_user_id === you?.user_id;
  const remainingMs = deadlineMs
    ? Math.max(0, deadlineMs - (now - serverSkewMs)) : 0;
  const phaseTotalMs = phase === "question" ? 15000
                                          : phase === "reveal" ? 4000
                                          : phase === "leaderboard" ? 4000
                                          : 0;
  const timerPct = phaseTotalMs > 0
    ? Math.max(0, Math.min(100, (remainingMs / phaseTotalMs) * 100))
    : 0;

  const startGame = async () => {
    try {
      await axios.post(`${API}/trivia/rooms/${code}/start`, {},
        { withCredentials: true });
    } catch (e) {
      const d = e?.response?.data?.detail;
      const msg = (d && typeof d === "object" && d.message) ? d.message
                        : (typeof d === "string" ? d : "Failed to start.");
      toast.error(msg);
    }
  };
  const copyCode = async () => {
    try { await navigator.clipboard.writeText(code);
          toast.success("Code copied"); }
    catch { /* silent */ }
  };
  const inviteUrl = useMemo(
    () => `${window.location.origin}/trivia/join?code=${code}`, [code]);
  const shareInvite = async () => {
    try {
      if (navigator.share)
        await navigator.share({ title: "Join my RadioLife trivia room",
                                                        text: `Code: ${code}`, url: inviteUrl });
      else {
        await navigator.clipboard.writeText(inviteUrl);
        toast.success("Invite link copied");
      }
    } catch { /* user cancelled */ }
  };

  if (!ws || !room) {
    return (
      <div className="p-8 text-center text-slate-500"
                data-testid="rl-trivia-room-connecting">
        <Loader2 size={18} className="inline animate-spin mr-2 text-violet-500" />
        Joining room…
      </div>
    );
  }

  return (
    <div className="px-4 pt-4 pb-6 space-y-4"
              data-testid="rl-trivia-room" data-phase={phase}>
      {/* Header strip */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="font-mono font-bold text-lg tracking-widest
                                          text-violet-600"
                      data-testid="rl-trivia-room-code">{code}</div>
          <button type="button" onClick={copyCode}
                      data-testid="rl-trivia-room-copy"
                      className="p-1.5 rounded-md border border-slate-200
                                                hover:border-violet-500">
            <Copy size={12} className="text-slate-600" />
          </button>
          <button type="button" onClick={shareInvite}
                      data-testid="rl-trivia-room-share"
                      className="p-1.5 rounded-md border border-slate-200
                                                hover:border-violet-500">
            <Share2 size={12} className="text-slate-600" />
          </button>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono
                                        uppercase tracking-widest text-slate-500">
          <span className={`w-2 h-2 rounded-full ${
            connected ? "bg-emerald-500" : "bg-red-500"}`} />
          <Users size={11} /> {room.players.length}/{room.max_players}
        </div>
      </div>

      {/* Phase H — Trivia sponsorship chip (AD.5). */}
      {room.sponsorship && (
        <div className="flex items-center gap-2 rounded-full bg-fuchsia-100
                                        border border-fuchsia-300 text-fuchsia-700 px-3 py-1.5
                                        text-[11px] font-mono uppercase tracking-widest"
                    data-testid="rl-trivia-room-sponsor-chip">
          <span className="w-1.5 h-1.5 rounded-full bg-fuchsia-500" />
          Sponsored by {room.sponsorship.display_name}
          {room.sponsorship.tagline && (
            <span className="text-slate-500 normal-case tracking-normal ml-1">
              · {room.sponsorship.tagline}
            </span>
          )}
        </div>
      )}

      {/* Lobby */}
      {phase === "lobby" && (
        <div className="rounded-2xl bg-white border border-slate-200 p-5
                                        space-y-4"
                    data-testid="rl-trivia-room-lobby">
          <div>
            <div className="text-[10px] uppercase tracking-widest font-mono
                                            text-slate-400">Lobby · waiting to start</div>
            <h2 className="text-xl font-black text-slate-900 mt-1">
              {room.players.length === 1
                ? "Just you for now."
                : "Players in"}
            </h2>
          </div>
          <ul className="space-y-2" data-testid="rl-trivia-room-players">
            {room.players.map((p) => (
              <li key={p.user_id}
                      data-testid={`rl-trivia-room-player-${p.user_id}`}
                      className="flex items-center gap-3 px-3 py-2
                                                  rounded-lg border border-slate-100
                                                  bg-slate-50">
                <div className="w-7 h-7 rounded-full bg-violet-100
                                                grid place-items-center font-mono
                                                text-xs text-violet-700">
                  {(p.name || "?")[0]}
                </div>
                <span className="text-sm text-slate-900">{p.name}</span>
                {p.user_id === room.host_user_id && (
                  <span className="text-amber-600 flex items-center gap-1
                                                  text-[10px] font-mono uppercase tracking-widest">
                    <Crown size={10} /> Host
                  </span>
                )}
                <span className={`ml-auto w-2 h-2 rounded-full ${
                  p.connected ? "bg-emerald-500" : "bg-slate-300"}`} />
              </li>
            ))}
          </ul>
          {isHost ? (
            <button
              type="button"
              onClick={startGame}
              disabled={room.players.length < 2}
              data-testid="rl-trivia-room-start"
              className="w-full h-11 rounded-full bg-violet-500 text-white
                                          font-semibold disabled:opacity-50
                                          disabled:cursor-not-allowed inline-flex
                                          items-center justify-center gap-1 text-sm">
              Start round <ChevronRight size={14} />
            </button>
          ) : (
            <div className="text-sm text-slate-500">
              Waiting for the host to start…
            </div>
          )}
          {isHost && room.players.length < 2 && (
            <div className="text-xs text-slate-500"
                        data-testid="rl-trivia-room-start-hint">
              Need 1 more player.  Share code&nbsp;
              <span className="font-mono text-violet-600">{code}</span>.
            </div>
          )}
        </div>
      )}

      {/* Question / reveal */}
      {(phase === "question" || phase === "reveal") && question && (
        <>
          <div className="h-1 rounded-full overflow-hidden bg-slate-200">
            <div
              data-testid="rl-trivia-room-timer"
              className="h-full bg-violet-500 transition-all duration-100"
              style={{ width: `${timerPct}%` }} />
          </div>
          <div className="rounded-2xl bg-white border border-slate-200
                                          p-5 space-y-4"
                      data-testid="rl-trivia-room-question">
            <div className="flex items-center justify-between text-[10px]
                                            uppercase tracking-widest font-mono
                                            text-slate-500">
              <span>Q {(room.current_index ?? 0) + 1} / {room.total_questions || 10}</span>
              <span>{answersIn}/{totalPlayers || room.players.length}
                          {" "}answered</span>
            </div>
            <h2 className="text-xl font-black text-slate-900"
                        data-testid="rl-trivia-room-prompt">
              {question.prompt}
            </h2>
            <div className="grid grid-cols-1 gap-2"
                        data-testid="rl-trivia-room-choices">
              {question.choices.map((c) => {
                const isChosen = chosenId === c.id;
                const isCorrect = reveal
                        && reveal.correct_choice_id === c.id;
                const isWrongPick = reveal && isChosen && !isCorrect;
                return (
                  <button
                    key={c.id}
                    type="button"
                    disabled={phase !== "question" || !!chosenId}
                    onClick={() => { setChosenId(c.id);
                                                        sendAnswer(question.id, c.id); }}
                    data-testid={`rl-trivia-room-choice-${c.id}`}
                    className={[
                      "rounded-xl border px-4 py-3 text-left text-sm",
                      "flex items-center gap-3 transition",
                      "disabled:cursor-default",
                      phase === "reveal"
                        ? (isCorrect
                              ? "border-emerald-500 bg-emerald-50 text-emerald-900"
                              : isWrongPick
                                  ? "border-red-500 bg-red-50 text-red-900"
                                  : "border-slate-200 opacity-60 bg-white")
                        : (isChosen
                              ? "border-violet-500 bg-violet-50 text-violet-900"
                              : "border-slate-200 bg-white "
                                    + "hover:border-violet-400"),
                    ].join(" ")}>
                    <span className="font-mono text-[10px] text-slate-400">
                      {c.id.toUpperCase()}
                    </span>
                    <span className="flex-1">{c.text}</span>
                    {phase === "reveal" && isCorrect &&
                      <Check size={14} className="text-emerald-600" />}
                    {phase === "reveal" && isWrongPick &&
                      <X size={14} className="text-red-600" />}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* Between-question leaderboard */}
      {phase === "leaderboard" && (
        <div className="rounded-2xl bg-white border border-slate-200 p-5"
                    data-testid="rl-trivia-room-leaderboard">
          <div className="text-[10px] uppercase tracking-widest font-mono
                                          text-slate-400 mb-3">Standings</div>
          <ul className="space-y-2">
            {leaderboard.map((p) => (
              <li key={p.user_id}
                      data-testid={`rl-trivia-room-lb-${p.user_id}`}
                      className="flex items-center gap-3 px-3 py-2
                                                  rounded-lg bg-slate-50 border border-slate-100">
                <span className="font-mono text-slate-400 w-6">#{p.rank}</span>
                <span className="flex-1 text-slate-900">{p.name}</span>
                <span className="font-mono text-violet-600">{p.score}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Final */}
      {phase === "done" && (
        <div className="rounded-2xl bg-white border border-slate-200 p-5
                                        space-y-3"
                    data-testid="rl-trivia-room-final">
          <div className="text-[10px] uppercase tracking-widest font-mono
                                          text-slate-400 flex items-center gap-2">
            <Trophy size={12} /> Final scoreboard
          </div>
          <ul className="space-y-2">
            {finalScores.map((p) => (
              <li key={p.user_id}
                      data-testid={`rl-trivia-room-final-${p.user_id}`}
                      className="flex items-center gap-3 px-3 py-2
                                                  rounded-lg bg-slate-50 border border-slate-100">
                <span className="font-mono text-slate-400 w-6">#{p.rank}</span>
                <span className="flex-1 text-slate-900">{p.name}</span>
                <span className="font-mono text-violet-600">{p.score}</span>
                <span className="font-mono text-amber-600 text-xs
                                                flex items-center gap-1">
                  <Coins size={11} /> +{p.bigcoin_awarded}
                </span>
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={() => navigate("/trivia")}
            data-testid="rl-trivia-room-finish-back"
            className="w-full h-11 rounded-full bg-violet-500 text-white
                                        font-semibold text-sm inline-flex items-center
                                        justify-center gap-1">
            Back to trivia <ChevronRight size={14} />
          </button>
        </div>
      )}

      {/* Phase H — sponsor prizes on the RadioLife done screen. */}
      {phase === "done" && sponsorPrizes.filter((p) => p.user_id === you?.user_id).length > 0 && (
        <div className="rounded-2xl bg-white border border-fuchsia-200 p-5"
                    data-testid="rl-trivia-room-sponsor-prizes">
          <div className="text-[10px] font-mono uppercase tracking-widest
                                          text-fuchsia-600 mb-3 inline-flex items-center gap-1">
            Sponsored prizes won
          </div>
          <div className="space-y-2">
            {sponsorPrizes.filter((p) => p.user_id === you?.user_id).map((p) => (
              <div key={p.award_id}
                          data-testid={`rl-trivia-room-sponsor-prize-${p.award_id}`}
                          className="flex items-center gap-3 rounded-xl bg-fuchsia-50
                                                    border border-fuchsia-200 p-3">
                <div className="w-9 h-9 rounded-full grid place-items-center
                                            bg-fuchsia-500/15 shrink-0">
                  <Trophy size={16} className="text-fuchsia-600" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-black text-slate-900">
                    Rank #{p.rank} — {p.currency === "usd"
                      ? `$${(p.points_awarded / 100).toFixed(2)} voucher`
                      : `+${p.points_awarded} BigPoints`}
                  </div>
                  <div className="text-[11px] text-slate-500 truncate">
                    From {p.sponsor_display_name}
                  </div>
                </div>
                <button onClick={() => {
                                    fetch(`${process.env.REACT_APP_BACKEND_URL}/api/user/trivia-prize-awards/${p.award_id}/claim`,
                                                {method:"POST",credentials:"include"});
                                    navigate("/wallet");
                                }}
                                data-testid={`rl-trivia-room-sponsor-claim-${p.award_id}`}
                                className="text-[11px] font-black px-3 py-1.5 rounded-full
                                                        bg-fuchsia-500 text-white hover:bg-fuchsia-400">
                  Claim
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
