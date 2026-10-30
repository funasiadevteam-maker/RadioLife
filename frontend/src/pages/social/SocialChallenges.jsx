// FUUSIC Arena — Play-With-Friends challenges + weekly score leaderboard (web).
import { useCallback, useEffect, useRef, useState } from "react";
import axios from "axios";
import { toast } from "sonner";
import {
  Trophy, Swords, Users, Clock, Check, X, Loader2, Crown, Plus,
  ChevronRight, Film, HelpCircle, Zap,
} from "lucide-react";
import { Avatar } from "./SocialV2";

const B = process.env.REACT_APP_BACKEND_URL || "";
const api = axios.create({ baseURL: `${B}/api/arena`, withCredentials: true });
const social = axios.create({ baseURL: `${B}/api/social`, withCredentials: true });

const GAME_ICON = { trivia: HelpCircle, quiz: Film };

function Card({ children, className = "", ...rest }) {
  return (
    <div className={`rounded-3xl bg-white/[0.04] border border-white/10 p-4 ${className}`} {...rest}>
      {children}
    </div>
  );
}

export function ChallengesTab() {
  const [sub, setSub] = useState("challenges");
  return (
    <div data-testid="arena-tab">
      <div className="flex items-center gap-2 mb-5">
        <SubTab active={sub === "challenges"} onClick={() => setSub("challenges")}
                icon={Swords} label="Challenges" testid="arena-subtab-challenges" />
        <SubTab active={sub === "leaderboard"} onClick={() => setSub("leaderboard")}
                icon={Trophy} label="Leaderboard" testid="arena-subtab-leaderboard" />
      </div>
      {sub === "challenges" ? <ChallengesList /> : <ScoreLeaderboard />}
    </div>
  );
}

function SubTab({ active, onClick, icon: Icon, label, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-bold transition-colors ${
        active ? "bg-gradient-to-r from-purple-600 to-pink-600 text-white"
               : "bg-white/[0.05] text-slate-300 hover:bg-white/10"}`}>
      <Icon size={15} /> {label}
    </button>
  );
}

/* ───────────────────────── Challenges list ───────────────────────── */
function ChallengesList() {
  const [data, setData] = useState({ invites: [], active: [], completed: [] });
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [playCid, setPlayCid] = useState(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get("/challenges"); setData(data); }
    catch (_) { /* soft */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (cid, action) => {
    try { await api.post(`/challenges/${cid}/${action}`); load(); }
    catch (_) { toast.error("Could not update challenge"); }
  };

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="animate-spin text-purple-400" /></div>;

  const empty = !data.invites.length && !data.active.length && !data.completed.length;
  return (
    <div className="space-y-5" data-testid="arena-challenges">
      <button onClick={() => setCreateOpen(true)} data-testid="arena-new-challenge-btn"
        className="w-full flex items-center justify-center gap-2 py-3 rounded-2xl font-black text-white bg-gradient-to-r from-purple-600 to-pink-600 hover:opacity-90 transition">
        <Plus size={18} /> Challenge a friend
      </button>

      {empty && (
        <Card className="text-center py-10" data-testid="arena-empty">
          <Swords size={34} className="mx-auto text-purple-400 mb-3" />
          <div className="font-black text-lg">No challenges yet</div>
          <div className="text-sm text-slate-400 mt-1">Challenge a friend to a quiz and climb the leaderboard.</div>
        </Card>
      )}

      {data.invites.length > 0 && (
        <Section title="Invitations" count={data.invites.length}>
          {data.invites.map((c) => (
            <InviteCard key={c.id} c={c}
              onAccept={() => act(c.id, "accept")}
              onDecline={() => act(c.id, "decline")} />
          ))}
        </Section>
      )}

      {data.active.length > 0 && (
        <Section title="Active" count={data.active.length}>
          {data.active.map((c) => (
            <ActiveCard key={c.id} c={c} onPlay={() => setPlayCid(c.id)} />
          ))}
        </Section>
      )}

      {data.completed.length > 0 && (
        <Section title="Results" count={data.completed.length}>
          {data.completed.map((c) => <CompletedCard key={c.id} c={c} />)}
        </Section>
      )}

      {createOpen && (
        <CreateChallengeModal onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); load(); }} />
      )}
      {playCid && (
        <QuizRunner cid={playCid} onClose={() => { setPlayCid(null); load(); }} />
      )}
    </div>
  );
}

function Section({ title, count, children }) {
  return (
    <div>
      <div className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">{title} · {count}</div>
      <div className="space-y-2.5">{children}</div>
    </div>
  );
}

function GameBadge({ gameKey }) {
  const Icon = GAME_ICON[gameKey] || HelpCircle;
  return (
    <span className="w-10 h-10 rounded-xl grid place-items-center bg-gradient-to-br from-purple-600/40 to-pink-600/40 shrink-0">
      <Icon size={18} className="text-purple-200" />
    </span>
  );
}

function InviteCard({ c, onAccept, onDecline }) {
  return (
    <Card className="flex items-center gap-3" data-testid={`arena-invite-${c.id}`}>
      <GameBadge gameKey={c.game_key} />
      <div className="flex-1 min-w-0">
        <div className="font-black truncate">{c.title}</div>
        <div className="text-xs text-slate-400 truncate">
          {c.host?.name} challenged you · {c.prize_points} pts
        </div>
      </div>
      <button onClick={onDecline} data-testid={`arena-decline-${c.id}`}
        className="w-9 h-9 rounded-full grid place-items-center bg-white/[0.06] text-slate-300 hover:text-red-400"><X size={16} /></button>
      <button onClick={onAccept} data-testid={`arena-accept-${c.id}`}
        className="px-4 py-2 rounded-full font-bold text-sm text-white bg-gradient-to-r from-purple-600 to-pink-600">Accept</button>
    </Card>
  );
}

function ActiveCard({ c, onPlay }) {
  const canPlay = c.i_joined && !c.i_submitted;
  const waiting = c.i_submitted;
  return (
    <Card className="flex items-center gap-3" data-testid={`arena-active-${c.id}`}>
      <GameBadge gameKey={c.game_key} />
      <div className="flex-1 min-w-0">
        <div className="font-black truncate">{c.title}</div>
        <div className="text-xs text-slate-400 truncate flex items-center gap-1.5">
          <Users size={12} /> {c.participants.length} playing
          {c.mode === "group" ? " · Group" : " · Head-to-head"} · {c.prize_points} pts
        </div>
      </div>
      {canPlay && (
        <button onClick={onPlay} data-testid={`arena-play-${c.id}`}
          className="flex items-center gap-1.5 px-4 py-2 rounded-full font-black text-sm text-white bg-gradient-to-r from-purple-600 to-pink-600">
          <Zap size={14} /> Play
        </button>
      )}
      {waiting && (
        <span className="flex items-center gap-1.5 text-xs font-bold text-amber-500" data-testid={`arena-waiting-${c.id}`}>
          <Clock size={13} /> Waiting
        </span>
      )}
    </Card>
  );
}

function CompletedCard({ c }) {
  return (
    <Card data-testid={`arena-completed-${c.id}`}>
      <div className="flex items-center gap-3">
        <GameBadge gameKey={c.game_key} />
        <div className="flex-1 min-w-0">
          <div className="font-black truncate">{c.title}</div>
          <div className={`text-xs font-bold ${c.i_won ? "text-emerald-400" : "text-slate-400"}`}>
            {c.i_won ? `You won · +${c.prize_points} pts` : `${c.winner?.name || "Someone"} won`}
          </div>
        </div>
        {c.i_won && <Crown size={20} className="text-amber-400" />}
      </div>
      {Array.isArray(c.scoreboard) && (
        <div className="mt-3 space-y-1.5">
          {c.scoreboard.map((b, i) => (
            <div key={i} className="flex items-center gap-2 text-sm" data-testid={`arena-score-row-${c.id}-${i}`}>
              <span className="w-5 text-slate-500 font-black">{i + 1}</span>
              <Avatar name={b.user?.name} url={b.user?.avatar_url} size={22} />
              <span className="flex-1 truncate">{b.user?.name}</span>
              <span className="font-black tabular-nums">{b.score}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

/* ───────────────────────── Create modal ──────────────────────────── */
function CreateChallengeModal({ onClose, onCreated }) {
  const [games, setGames] = useState([]);
  const [friends, setFriends] = useState([]);
  const [gameKey, setGameKey] = useState("trivia");
  const [mode, setMode] = useState("h2h");
  const [picked, setPicked] = useState([]);
  const [prize, setPrize] = useState(100);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/games").then(({ data }) => setGames(data.games || [])).catch(() => {});
    social.get("/friends").then(({ data }) => setFriends(data.friends || [])).catch(() => {});
  }, []);

  const toggleFriend = (uid) => setPicked((p) => {
    if (p.includes(uid)) return p.filter((x) => x !== uid);
    if (mode === "h2h") return [uid];
    return [...p, uid];
  });

  const create = async () => {
    if (mode === "h2h" && picked.length !== 1) return toast.error("Pick one friend");
    if (mode === "group" && picked.length < 2) return toast.error("Pick at least two friends");
    setSaving(true);
    try {
      await api.post("/challenges", { game_key: gameKey, mode, invitees: picked, prize: Number(prize) });
      toast.success("Challenge sent!");
      onCreated();
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code || "Could not create challenge");
    } finally { setSaving(false); }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4"
         onClick={onClose} data-testid="arena-create-modal">
      <div onClick={(e) => e.stopPropagation()}
        className="w-full sm:max-w-md bg-[#15131f] border border-white/10 rounded-t-3xl sm:rounded-3xl p-5 max-h-[88vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-xl font-black">New challenge</h3>
          <button onClick={onClose} data-testid="arena-create-close" className="text-slate-400 hover:text-white"><X size={20} /></button>
        </div>

        <div className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">Game</div>
        <div className="grid grid-cols-2 gap-2 mb-4">
          {games.map((g) => {
            const Icon = GAME_ICON[g.key] || HelpCircle;
            const on = gameKey === g.key;
            return (
              <button key={g.key} onClick={() => setGameKey(g.key)} data-testid={`arena-create-game-${g.key}`}
                className={`flex items-center gap-2 p-3 rounded-2xl border text-left ${
                  on ? "border-purple-500 bg-purple-500/15" : "border-white/10 bg-white/[0.03]"}`}>
                <Icon size={18} className="text-purple-300 shrink-0" />
                <span className="text-sm font-bold truncate">{g.label}</span>
              </button>
            );
          })}
        </div>

        <div className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">Mode</div>
        <div className="flex gap-2 mb-4">
          {[["h2h", "Head-to-head"], ["group", "Group"]].map(([k, l]) => (
            <button key={k} onClick={() => { setMode(k); setPicked([]); }} data-testid={`arena-create-mode-${k}`}
              className={`flex-1 py-2.5 rounded-2xl text-sm font-bold border ${
                mode === k ? "border-purple-500 bg-purple-500/15 text-white" : "border-white/10 bg-white/[0.03] text-slate-300"}`}>{l}</button>
          ))}
        </div>

        <div className="text-xs font-black uppercase tracking-widest text-slate-400 mb-2">
          {mode === "h2h" ? "Pick a friend" : "Pick friends (2+)"}
        </div>
        <div className="space-y-1.5 mb-4 max-h-52 overflow-y-auto">
          {friends.length === 0 && <div className="text-sm text-slate-500 py-3">Add friends first to challenge them.</div>}
          {friends.map((f) => {
            const on = picked.includes(f.user_id);
            return (
              <button key={f.user_id} onClick={() => toggleFriend(f.user_id)} data-testid={`arena-create-friend-${f.user_id}`}
                className={`w-full flex items-center gap-3 p-2.5 rounded-2xl border ${
                  on ? "border-purple-500 bg-purple-500/15" : "border-white/10 bg-white/[0.03]"}`}>
                <Avatar name={f.name} url={f.avatar_url} size={32} />
                <span className="flex-1 text-left font-bold truncate">{f.name}</span>
                {on && <Check size={18} className="text-purple-300" />}
              </button>
            );
          })}
        </div>

        <div className="flex items-center justify-between mb-4">
          <span className="text-sm font-bold text-slate-300">Prize (BigPoints)</span>
          <input type="number" min={10} max={500} step={10} value={prize}
            onChange={(e) => setPrize(e.target.value)} data-testid="arena-create-prize"
            className="w-24 rounded-xl bg-white/[0.05] border border-white/10 px-3 py-2 text-sm text-right outline-none" />
        </div>

        <button onClick={create} disabled={saving} data-testid="arena-create-submit"
          className="w-full py-3 rounded-2xl font-black text-white bg-gradient-to-r from-purple-600 to-pink-600 disabled:opacity-50">
          {saving ? "Sending…" : "Send challenge"}
        </button>
      </div>
    </div>
  );
}

/* ───────────────────────── Quiz runner ───────────────────────────── */
function QuizRunner({ cid, onClose }) {
  const [q, setQ] = useState(null);
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState([]);
  const [result, setResult] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const startRef = useRef(Date.now());

  useEffect(() => {
    api.get(`/challenges/${cid}/quiz`)
      .then(({ data }) => { setQ(data); startRef.current = Date.now(); })
      .catch((e) => { toast.error("Could not load quiz"); onClose(); });
  }, [cid, onClose]);

  const choose = async (choiceIdx) => {
    const next = [...answers, choiceIdx];
    setAnswers(next);
    if (idx + 1 < q.questions.length) { setIdx(idx + 1); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post(`/challenges/${cid}/submit`,
        { answers: next, time_ms: Date.now() - startRef.current });
      setResult(data);
    } catch (e) { toast.error("Could not submit"); onClose(); }
    finally { setSubmitting(false); }
  };

  return (
    <div className="fixed inset-0 z-[60] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4" data-testid="arena-quiz">
      <div className="w-full max-w-md bg-[#15131f] border border-white/10 rounded-3xl p-5">
        {!q && <div className="py-16 flex justify-center"><Loader2 className="animate-spin text-purple-400" /></div>}

        {q && !result && (
          <>
            <div className="flex items-center justify-between mb-4">
              <span className="text-xs font-black uppercase tracking-widest text-purple-300">{q.game_label}</span>
              <span className="text-xs font-bold text-slate-400">{idx + 1} / {q.questions.length}</span>
            </div>
            <div className="h-1 rounded-full bg-white/10 mb-5 overflow-hidden">
              <div className="h-full bg-gradient-to-r from-purple-500 to-pink-500 transition-all"
                   style={{ width: `${(idx / q.questions.length) * 100}%` }} />
            </div>
            <div className="text-lg font-black mb-5" data-testid="arena-quiz-prompt">{q.questions[idx].prompt}</div>
            <div className="space-y-2.5">
              {q.questions[idx].choices.map((ch, i) => (
                <button key={i} disabled={submitting} onClick={() => choose(i)} data-testid={`arena-quiz-choice-${i}`}
                  className="w-full text-left p-3.5 rounded-2xl border border-white/10 bg-white/[0.03] hover:border-purple-500 hover:bg-purple-500/10 font-bold disabled:opacity-50 transition">
                  {ch}
                </button>
              ))}
            </div>
          </>
        )}

        {result && (
          <div className="text-center py-4" data-testid="arena-quiz-result">
            <Trophy size={40} className="mx-auto text-amber-400 mb-3" />
            <div className="text-3xl font-black tabular-nums">{result.score}</div>
            <div className="text-sm text-slate-400 mb-4">{result.correct} / {result.total} correct</div>
            {result.finalized ? (
              <div className={`text-sm font-black mb-4 ${result.challenge?.i_won ? "text-emerald-400" : "text-slate-300"}`}>
                {result.challenge?.i_won ? `🏆 You won +${result.challenge.prize_points} pts!`
                                         : `${result.challenge?.winner?.name || "Your rival"} took this one.`}
              </div>
            ) : (
              <div className="text-sm text-amber-300 font-bold mb-4">Waiting for your opponent to play…</div>
            )}
            <button onClick={onClose} data-testid="arena-quiz-close"
              className="w-full py-3 rounded-2xl font-black text-white bg-gradient-to-r from-purple-600 to-pink-600">Done</button>
          </div>
        )}
      </div>
    </div>
  );
}

/* ───────────────────────── Leaderboard ───────────────────────────── */
function ScoreLeaderboard() {
  const [scope, setScope] = useState("global");
  const [gameKey, setGameKey] = useState("all");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/leaderboard", { params: { scope, game_key: gameKey } });
      setData(data);
    } catch (_) { /* soft */ } finally { setLoading(false); }
  }, [scope, gameKey]);
  useEffect(() => { load(); }, [load]);

  const GAMES = [["all", "All games"], ["trivia", "Trivia"], ["quiz", "Movie"]];

  return (
    <div className="space-y-4" data-testid="arena-leaderboard">
      <div className="flex gap-2">
        {[["global", "Global"], ["friends", "Friends"]].map(([k, l]) => (
          <button key={k} onClick={() => setScope(k)} data-testid={`arena-lb-scope-${k}`}
            className={`flex-1 py-2 rounded-full text-sm font-bold ${
              scope === k ? "bg-gradient-to-r from-purple-600 to-pink-600 text-white" : "bg-white/[0.05] text-slate-300"}`}>{l}</button>
        ))}
      </div>
      <div className="flex gap-1.5 overflow-x-auto no-scrollbar">
        {GAMES.map(([k, l]) => (
          <button key={k} onClick={() => setGameKey(k)} data-testid={`arena-lb-game-${k}`}
            className={`px-3.5 py-1.5 rounded-full text-xs font-bold whitespace-nowrap shrink-0 ${
              gameKey === k ? "bg-white/15 text-white" : "bg-white/[0.04] text-slate-400"}`}>{l}</button>
        ))}
      </div>

      {loading && <div className="flex justify-center py-12"><Loader2 className="animate-spin text-purple-400" /></div>}

      {!loading && data && (
        <>
          {data.items.length === 0 && (
            <Card className="text-center py-10" data-testid="arena-lb-empty">
              <Trophy size={30} className="mx-auto text-purple-400 mb-2" />
              <div className="font-bold">No scores this week yet</div>
              <div className="text-sm text-slate-400 mt-1">Play a challenge to get on the board.</div>
            </Card>
          )}
          {data.items.length > 0 && (
            <Card className="!p-2">
              {data.items.map((it) => (
                <LbRow key={it.rank} it={it} />
              ))}
            </Card>
          )}
          {data.me && !data.items.some((i) => i.is_me) && (
            <Card className="!p-2" data-testid="arena-lb-me">
              <LbRow it={data.me} />
            </Card>
          )}
          <div className="text-center text-[11px] text-slate-500">Week {data.week} · resets Monday</div>
        </>
      )}
    </div>
  );
}

function LbRow({ it }) {
  const medal = it.rank <= 3;
  return (
    <div className={`flex items-center gap-3 p-2.5 rounded-2xl ${it.is_me ? "bg-purple-500/15" : ""}`}
         data-testid={`arena-lb-row-${it.rank}`}>
      <span className={`w-7 text-center font-black tabular-nums ${medal ? "text-amber-400" : "text-slate-500"}`}>
        {it.rank}
      </span>
      <Avatar name={it.user?.name} url={it.user?.avatar_url} size={34} />
      <div className="flex-1 min-w-0">
        <div className="font-bold truncate">{it.user?.name || "Player"}{it.is_me ? " (You)" : ""}</div>
        <div className="text-[11px] text-slate-500">{it.plays} play{it.plays === 1 ? "" : "s"}</div>
      </div>
      <span className="font-black tabular-nums text-violet-600">{it.score}</span>
    </div>
  );
}

export default ChallengesTab;
