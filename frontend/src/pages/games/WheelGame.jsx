import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import axios from "axios";
import confetti from "canvas-confetti";
import { API } from "@/AuthContext";
import { ArrowLeft, Volume2, VolumeX, Loader2, Gift, Sparkles } from "lucide-react";

const CX = 160, CY = 160, R = 150, LABEL_R = 100;

function polar(cx, cy, r, degFromTop) {
  const t = ((degFromTop - 90) * Math.PI) / 180;
  return [cx + r * Math.cos(t), cy + r * Math.sin(t)];
}

function slicePath(i, seg) {
  const a0 = i * seg, a1 = (i + 1) * seg;
  const [x0, y0] = polar(CX, CY, R, a0);
  const [x1, y1] = polar(CX, CY, R, a1);
  const large = seg > 180 ? 1 : 0;
  return `M ${CX} ${CY} L ${x0.toFixed(2)} ${y0.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
}

function shorten(label) {
  const m = /^(\d+)\s*pts$/i.exec(label);
  if (m) return [m[1], "pts"];
  if (/jackpot/i.test(label)) return ["5000", "JACKPOT"];
  const parts = label.split(" ");
  if (parts.length > 1) return [parts[0], parts.slice(1).join(" ")];
  return [label, ""];
}

export default function WheelGame() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const gameId = params.get("game_id") || "wheel_house";

  const [cfg, setCfg] = useState(null);
  const [rotation, setRotation] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [prize, setPrize] = useState(null);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState(null);
  const audioRef = useRef(null);
  const rotRef = useRef(0);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/games/wheel/config`, {
        params: { game_id: gameId }, withCredentials: true });
      setCfg(data);
    } catch (e) { setError("Couldn’t load the wheel."); }
  }, [gameId]);
  useEffect(() => { load(); }, [load]);

  const fireConfetti = () => {
    const end = Date.now() + 900;
    const colors = ["#a855f7", "#ec4899", "#fbbf24", "#22d3ee", "#10b981"];
    (function frame() {
      confetti({ particleCount: 5, angle: 60, spread: 60, origin: { x: 0 }, colors });
      confetti({ particleCount: 5, angle: 120, spread: 60, origin: { x: 1 }, colors });
      if (Date.now() < end) requestAnimationFrame(frame);
    })();
  };

  const spin = async () => {
    if (spinning || !cfg || cfg.spins_left <= 0) return;
    setSpinning(true); setPrize(null);
    // start BGM on the user gesture
    if (audioRef.current && !muted) { audioRef.current.volume = 0.35; audioRef.current.play().catch(() => {}); }
    try {
      const { data } = await axios.post(`${API}/games/wheel/spin`,
        { game_id: gameId }, { withCredentials: true });
      const n = cfg.segments.length;
      const seg = 360 / n;
      const ci = data.segment_index * seg + seg / 2;
      const next = Math.ceil((rotRef.current + 1) / 360) * 360 + 6 * 360 + ((360 - ci) % 360);
      rotRef.current = next;
      setRotation(next);
      setTimeout(() => {
        setSpinning(false);
        setCfg((c) => ({ ...c, spins_left: data.spins_left }));
        setPrize(data.prize);
        if (data.prize.kind !== "none") fireConfetti();
      }, 4300);
    } catch (e) {
      setSpinning(false);
      if (e?.response?.status === 429) setCfg((c) => ({ ...c, spins_left: 0 }));
      else setError("Spin failed — try again.");
    }
  };

  const toggleMute = () => {
    setMuted((m) => {
      const nm = !m;
      if (audioRef.current) { if (nm) audioRef.current.pause(); else audioRef.current.play().catch(() => {}); }
      return nm;
    });
  };

  if (error && !cfg) return (
    <div className="min-h-screen grid place-items-center bg-[#0b0c16] text-white" data-testid="wheel-error">
      <div className="text-center"><p className="mb-4">{error}</p>
        <button onClick={() => navigate(-1)} className="px-4 h-10 rounded-full bg-white/10">Go back</button></div>
    </div>
  );
  if (!cfg) return (
    <div className="min-h-screen grid place-items-center bg-[#0b0c16] text-white"><Loader2 className="animate-spin" /></div>
  );

  const n = cfg.segments.length;
  const seg = 360 / n;
  const out = cfg.spins_left <= 0;

  return (
    <div className="min-h-screen bg-[#0b0c16] text-white relative overflow-hidden"
         style={{ backgroundImage: "radial-gradient(1200px 600px at 50% -10%, rgba(168,85,247,0.22), transparent), radial-gradient(900px 500px at 50% 110%, rgba(236,72,153,0.18), transparent)" }}
         data-testid="wheel-game">
      {cfg.bgm_url && <audio ref={audioRef} src={cfg.bgm_url} loop preload="auto" />}

      <div className="flex items-center justify-between p-4 max-w-lg mx-auto">
        <button onClick={() => navigate(-1)} data-testid="wheel-back" className="w-10 h-10 grid place-items-center rounded-full bg-white/10 hover:bg-white/20 transition"><ArrowLeft size={18} /></button>
        <div className="text-sm font-black tracking-wide">Wheel of Fortune</div>
        <button onClick={toggleMute} data-testid="wheel-mute" className="w-10 h-10 grid place-items-center rounded-full bg-white/10 hover:bg-white/20 transition">{muted ? <VolumeX size={18} /> : <Volume2 size={18} />}</button>
      </div>

      {(cfg.logo_url || cfg.sponsor_name) && (
        <div className="flex items-center justify-center gap-2 mb-1" data-testid="wheel-sponsor">
          {cfg.logo_url && <img src={cfg.logo_url} alt={cfg.sponsor_name} className="w-9 h-9 rounded-full object-cover ring-2 ring-white/20" />}
          <span className="text-xs text-slate-300">Sponsored by <b className="text-white">{cfg.sponsor_name}</b></span>
        </div>
      )}

      <div className="relative mx-auto mt-3" style={{ width: 340, height: 360 }}>
        {/* pointer */}
        <div className="absolute left-1/2 -translate-x-1/2 z-20" style={{ top: 2 }}>
          <div style={{ width: 0, height: 0, borderLeft: "16px solid transparent", borderRight: "16px solid transparent", borderTop: "28px solid #fbbf24", filter: "drop-shadow(0 3px 4px rgba(0,0,0,0.5))" }} />
        </div>
        <svg viewBox="0 0 320 320" width="320" height="320" className="mx-auto block"
             style={{ transform: `rotate(${rotation}deg)`, transition: spinning ? "transform 4.2s cubic-bezier(0.16,1,0.3,1)" : "none", filter: "drop-shadow(0 18px 40px rgba(0,0,0,0.55))" }}>
          <defs>
            <radialGradient id="gloss" cx="50%" cy="38%" r="65%">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
              <stop offset="45%" stopColor="#ffffff" stopOpacity="0.06" />
              <stop offset="100%" stopColor="#000000" stopOpacity="0.28" />
            </radialGradient>
          </defs>
          <circle cx={CX} cy={CY} r={R + 6} fill="#1e1030" stroke="#fbbf24" strokeWidth="4" />
          {cfg.segments.map((s, i) => (
            <path key={i} d={slicePath(i, seg)} fill={s.color} stroke="rgba(0,0,0,0.25)" strokeWidth="1.5" data-testid={`wheel-seg-${i}`} />
          ))}
          {cfg.segments.map((s, i) => {
            const am = i * seg + seg / 2;
            const [lx, ly] = polar(CX, CY, LABEL_R, am);
            const [big, small] = shorten(s.label);
            return (
              <g key={`l${i}`} transform={`rotate(${am} ${lx} ${ly})`}>
                <text x={lx} y={ly - 4} textAnchor="middle" fontSize="15" fontWeight="900" fill="#fff" style={{ textShadow: "0 1px 2px rgba(0,0,0,0.6)" }}>{big}</text>
                <text x={lx} y={ly + 11} textAnchor="middle" fontSize="8" fontWeight="700" fill="rgba(255,255,255,0.85)">{small}</text>
              </g>
            );
          })}
          <circle cx={CX} cy={CY} r={R} fill="url(#gloss)" pointerEvents="none" />
        </svg>
        {/* center hub / spin button */}
        <button onClick={spin} disabled={spinning || out} data-testid="wheel-spin"
                className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 w-20 h-20 rounded-full grid place-items-center font-black text-black disabled:opacity-70 active:scale-95 transition"
                style={{ background: "radial-gradient(circle at 35% 30%, #fff, #fbbf24 60%, #f59e0b)", boxShadow: "0 6px 16px rgba(0,0,0,0.5), inset 0 2px 6px rgba(255,255,255,0.7)" }}>
          {spinning ? <Loader2 className="animate-spin" size={22} /> : <span className="text-sm tracking-wider">SPIN</span>}
        </button>
      </div>

      <div className="text-center mt-4">
        {out ? (
          <div className="text-sm text-amber-300 font-bold" data-testid="wheel-no-spins">Out of spins — come back tomorrow! 🎡</div>
        ) : (
          <div className="text-sm text-slate-300" data-testid="wheel-spins-left"><b className="text-white">{cfg.spins_left}</b> spin{cfg.spins_left === 1 ? "" : "s"} left today</div>
        )}
      </div>

      {prize && (
        <div className="fixed inset-0 z-40 grid place-items-center bg-black/70 p-6" data-testid="wheel-prize-modal" onClick={() => setPrize(null)}>
          <div className="rounded-3xl p-6 max-w-xs w-full text-center border border-white/15" style={{ background: "linear-gradient(160deg,#241436,#0b0c16)" }} onClick={(e) => e.stopPropagation()}>
            <div className="w-16 h-16 rounded-full grid place-items-center mx-auto mb-3" style={{ background: prize.kind === "none" ? "rgba(255,255,255,0.08)" : "linear-gradient(135deg,#fbbf24,#f59e0b)" }}>
              {prize.kind === "coupon" ? <Gift className="text-black" size={30} /> : prize.kind === "none" ? <Sparkles className="text-slate-300" size={28} /> : <Sparkles className="text-black" size={30} />}
            </div>
            <div className="text-lg font-black mb-1">{prize.kind === "none" ? "So close!" : "You won! 🎉"}</div>
            <div className="text-2xl font-black mb-2" style={{ color: prize.kind === "none" ? "#94a3b8" : "#fbbf24" }}>{prize.label}</div>
            {prize.kind === "coupon" && <div className="text-xs text-slate-300 mb-2">Saved to your wallet{prize.sponsor ? ` · ${prize.sponsor}` : ""}</div>}
            {prize.kind === "points" && <div className="text-xs text-slate-300 mb-2">Added to your balance</div>}
            <button onClick={() => setPrize(null)} data-testid="wheel-prize-close" className="mt-2 w-full h-11 rounded-full font-black text-white" style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
              {out ? "Done" : "Spin again"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
