import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import confetti from "canvas-confetti";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Volume2, VolumeX, Ticket, Coins } from "lucide-react";
import { API } from "@/AuthContext";
import { GAME_ART } from "@/assets/gameArt";

function ScratchTile({ label, color, onDone, revealAll }) {
  const cvs = useRef(null);
  const drawing = useRef(false);
  const [revealed, setRevealed] = useState(false);

  useEffect(() => {
    const c = cvs.current; if (!c) return;
    const ctx = c.getContext("2d");
    const g = ctx.createLinearGradient(0, 0, c.width, c.height);
    g.addColorStop(0, "#c0c6d0"); g.addColorStop(0.5, "#8b93a4"); g.addColorStop(1, "#aeb6c4");
    ctx.fillStyle = g; ctx.fillRect(0, 0, c.width, c.height);
    ctx.fillStyle = "rgba(255,255,255,0.5)"; ctx.font = "bold 12px sans-serif";
    ctx.textAlign = "center"; ctx.fillText("SCRATCH", c.width / 2, c.height / 2 + 4);
  }, []);

  useEffect(() => { if (revealAll && !revealed) reveal(); }, [revealAll]); // eslint-disable-line

  const pct = () => {
    const c = cvs.current; const ctx = c.getContext("2d");
    const d = ctx.getImageData(0, 0, c.width, c.height).data;
    let clear = 0; for (let i = 3; i < d.length; i += 40) if (d[i] === 0) clear++;
    return clear / (d.length / 40);
  };
  const reveal = () => {
    const c = cvs.current; if (!c) return;
    c.getContext("2d").clearRect(0, 0, c.width, c.height);
    if (!revealed) { setRevealed(true); onDone?.(); }
  };
  const scratch = (e) => {
    if (!drawing.current || revealed) return;
    const c = cvs.current; const r = c.getBoundingClientRect();
    const x = (e.clientX ?? e.touches?.[0]?.clientX) - r.left;
    const y = (e.clientY ?? e.touches?.[0]?.clientY) - r.top;
    const ctx = c.getContext("2d");
    ctx.globalCompositeOperation = "destination-out";
    ctx.beginPath(); ctx.arc(x * (c.width / r.width), y * (c.height / r.height), 16, 0, 7); ctx.fill();
    if (pct() > 0.5) reveal();
  };

  return (
    <div className="relative w-full aspect-square rounded-2xl overflow-hidden select-none"
      style={{ background: color || "linear-gradient(145deg,#2a1b4e,#140d2a)",
        border: "1px solid rgba(251,191,36,0.25)",
        boxShadow: "inset 0 2px 10px rgba(0,0,0,0.4)" }} data-testid="scratch-tile">
      <div className="absolute inset-0 grid place-items-center text-center px-1">
        <span className="text-sm font-black text-white leading-tight"
          style={{ textShadow: "0 2px 6px rgba(0,0,0,0.6)" }}>{label}</span>
      </div>
      <canvas ref={cvs} width={120} height={120} data-testid="scratch-canvas"
        className="absolute inset-0 w-full h-full cursor-pointer touch-none"
        onPointerDown={(e) => { drawing.current = true; scratch(e); }}
        onPointerUp={() => { drawing.current = false; }}
        onPointerLeave={() => { drawing.current = false; }}
        onPointerMove={scratch} />
    </div>
  );
}

export default function ScratchGame() {
  const navigate = useNavigate();
  const [sp] = useSearchParams();
  const gameId = sp.get("game_id") || "scratch_house";
  const [cfg, setCfg] = useState(null);
  const [card, setCard] = useState(null);   // {tiles, win, prize, spins_left}
  const [revealed, setRevealed] = useState(0);
  const [revealAll, setRevealAll] = useState(false);
  const [done, setDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [muted, setMuted] = useState(false);
  const audio = useRef(null);

  useEffect(() => {
    axios.get(`${API}/games/wheel/config`, { params: { game_id: gameId }, withCredentials: true })
      .then(({ data }) => setCfg(data)).catch(() => setCfg({ error: true }));
  }, [gameId]);

  useEffect(() => {
    if (!cfg?.bgm_url) return;
    const a = new Audio(cfg.bgm_url); a.loop = true; a.volume = 0.32; audio.current = a;
    return () => { a.pause(); };
  }, [cfg?.bgm_url]);
  useEffect(() => { if (audio.current) audio.current.muted = muted; }, [muted]);

  const spinsLeft = card ? card.spins_left : (cfg?.spins_left ?? 0);

  const newCard = useCallback(async () => {
    if (loading) return;
    setLoading(true); setDone(false); setRevealed(0); setRevealAll(false); setCard(null);
    try {
      if (audio.current && !muted) audio.current.play().catch(() => {});
      const { data } = await axios.post(`${API}/games/scratch/play`, { game_id: gameId }, { withCredentials: true });
      setCard(data);
    } catch (e) {
      if (e?.response?.status === 429) toast.info("You're out of cards today — come back tomorrow!");
      else toast.error("Couldn't deal a card. Try again.");
    } finally { setLoading(false); }
  }, [gameId, loading, muted]);

  const onTileDone = () => setRevealed((n) => {
    const next = n + 1;
    if (next >= 3 && !done) {
      setDone(true);
      if (card?.win) {
        confetti({ particleCount: 130, spread: 75, origin: { y: 0.6 } });
        toast.success(card.prize?.kind === "coupon" ? `You won: ${card.prize.label}! 🎟️` : `You won ${card.prize?.points || 0} points! 🎉`);
      }
    }
    return next;
  });

  if (!cfg) return <div className="min-h-screen grid place-items-center bg-[#0b0c16]"><Loader2 className="animate-spin text-white" /></div>;

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#161327] via-[#0f0d1c] to-[#0b0c16] text-white" data-testid="scratch-game">
      <div className="max-w-md mx-auto px-4 py-4">
        <div className="flex items-center justify-between mb-4">
          <button onClick={() => navigate(-1)} data-testid="scratch-back" className="w-9 h-9 grid place-items-center rounded-full bg-white/10"><ArrowLeft size={18} /></button>
          <div className="flex items-center gap-1.5 text-sm font-black"><Ticket size={16} className="text-amber-300" /> Scratch Card</div>
          <button onClick={() => setMuted((m) => !m)} data-testid="scratch-mute" className="w-9 h-9 grid place-items-center rounded-full bg-white/10">{muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</button>
        </div>

        {cfg.logo_url && (
          <div className="flex items-center justify-center gap-2 mb-3" data-testid="scratch-sponsor">
            <img src={cfg.logo_url} alt={cfg.sponsor_name} className="w-8 h-8 rounded-full object-cover" />
            <span className="text-xs text-slate-300">Sponsored by <b className="text-white">{cfg.sponsor_name}</b></span>
          </div>
        )}

        {/* Premium AI-art hero */}
        <div className="relative rounded-3xl overflow-hidden mb-4" data-testid="scratch-hero"
          style={{ minHeight: 128,
            backgroundImage: `linear-gradient(90deg, rgba(14,8,34,0.92) 0%, rgba(14,8,34,0.4) 60%, rgba(14,8,34,0.15) 100%), url(${GAME_ART.scratch_win})`,
            backgroundSize: "cover", backgroundPosition: "center",
            boxShadow: "0 16px 40px rgba(0,0,0,0.5)" }}>
          <div className="p-4">
            <div className="inline-block text-[10px] font-black tracking-[0.14em] px-2.5 py-1 rounded-full"
              style={{ color: "#fff", background: "linear-gradient(135deg,#fbbf24,#f59e0b)" }}>
              DAILY SCRATCH
            </div>
            <div className="text-xl font-black mt-2 text-white">Scratch, match &amp; win instantly</div>
            <div className="text-xs mt-1" style={{ color: "#e3d9fb" }}>
              Reveal all three panels — match 3 to win BigPoints or coupons.
            </div>
          </div>
        </div>

        <div className="rounded-3xl p-5" data-testid="scratch-card-frame"
          style={{ border: "1px solid rgba(251,191,36,0.25)",
            background: "linear-gradient(160deg, rgba(36,20,54,0.92), rgba(11,12,22,0.96))",
            boxShadow: "0 18px 50px rgba(0,0,0,0.5)" }}>
          <div className="text-center text-[11px] text-slate-400 mb-3">Match 3 to win — scratch each panel</div>
          <div className="grid grid-cols-3 gap-3">
            {(card?.tiles || cfg.segments?.slice(0, 3).map((s) => s.label) || ["?", "?", "?"]).map((lbl, i) => (
              <ScratchTile key={`${card ? "c" : "e"}-${i}`} label={lbl}
                color={card ? undefined : "#1c1830"}
                revealAll={revealAll} onDone={card ? onTileDone : undefined} />
            ))}
          </div>

          {done && (
            <div className="mt-4 text-center" data-testid="scratch-result">
              {card?.win
                ? <div className="text-lg font-black text-amber-300 flex items-center justify-center gap-2"><Coins size={18} /> {card.prize?.kind === "coupon" ? card.prize.label : `+${card.prize?.points || 0} points`}</div>
                : <div className="text-sm font-bold text-slate-300">No match this time — try again!</div>}
              {typeof card?.balance === "number" && <div className="text-[11px] text-slate-400 mt-1">Balance: {card.balance} pts</div>}
            </div>
          )}

          <div className="mt-4 flex items-center justify-between">
            <span className="text-[11px] text-slate-400" data-testid="scratch-spins-left">{spinsLeft} card{spinsLeft === 1 ? "" : "s"} left today</span>
            {(!card || done) ? (
              spinsLeft <= 0 && done ? (
                <span className="text-xs font-bold text-slate-400" data-testid="scratch-no-cards">Out of cards — back tomorrow</span>
              ) : (
                <button onClick={newCard} disabled={loading || (spinsLeft <= 0 && !card)} data-testid="scratch-new-card"
                  className="inline-flex items-center gap-2 h-10 px-5 rounded-full font-black text-black disabled:opacity-40" style={{ background: "linear-gradient(135deg,#fbbf24,#f59e0b)" }}>
                  {loading ? <Loader2 size={16} className="animate-spin" /> : <Ticket size={16} />} {card ? "New card" : "Get a card"}
                </button>
              )
            ) : (
              <button onClick={() => setRevealAll(true)} data-testid="scratch-reveal-all"
                className="inline-flex items-center gap-2 h-10 px-5 rounded-full font-bold border border-white/15 text-white">
                Reveal all
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
