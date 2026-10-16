// Dining Club — Roll-a-Dice promo: roll two dice, land a double six (12) and
// win a free meal for 8. Win chance is exactly 1/12 (server-weighted RNG).
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import { ChevronLeft, Loader2, Dices, Trophy, Ticket } from "lucide-react";
import { diningApi, DINE, errCode } from "./diningApi";
import { Shell, NeonBtn } from "./DiningHome";
import { DICE_STAGE } from "../../assets/gameArt";
import { playFx, vibrate } from "../../utils/gameFX";

// 3x3 pip layout per face (grid cells 0..8 that are filled).
const PIPS = {
  1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8],
};

function Die({ value, rolling }) {
  const on = new Set(PIPS[value] || [4]);
  return (
    <motion.div
      animate={rolling
        ? { rotate: [0, -24, 22, -14, 10, 0], y: [0, -10, 0, -6, 0], scale: [1, 1.06, 1] }
        : { rotate: 0, y: 0, scale: 1 }}
      transition={{ duration: 0.55, repeat: rolling ? Infinity : 0, ease: "easeInOut" }}
      data-testid="dice-die"
      style={{ width: 90, height: 90, borderRadius: 20, padding: 12,
        display: "grid", gridTemplateColumns: "repeat(3,1fr)", gridTemplateRows: "repeat(3,1fr)",
        background: "radial-gradient(circle at 32% 28%, #ffffff, #efe8ff 70%, #e3d6ff)",
        boxShadow: `0 14px 30px rgba(124,58,237,.35), inset 0 -6px 12px rgba(124,58,237,.18), inset 0 4px 8px #fff`,
        border: `3px solid ${DINE.gold}` }}>
      {Array.from({ length: 9 }).map((_, i) => (
        <span key={i} style={{ display: "grid", placeItems: "center" }}>
          {on.has(i) && (
            <span style={{ width: 15, height: 15, borderRadius: 999,
              background: "radial-gradient(circle at 35% 30%, #a855f7, #6d28d9)",
              boxShadow: "inset 0 -2px 3px rgba(0,0,0,.35), 0 1px 2px rgba(0,0,0,.25)" }} />
          )}
        </span>
      ))}
    </motion.div>
  );
}

export default function DiningDice() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [rolling, setRolling] = useState(false);
  const [d1, setD1] = useState(1);
  const [d2, setD2] = useState(1);
  const [result, setResult] = useState(null);
  const [streak, setStreak] = useState(null);

  const load = () => diningApi.diceStatus().then((r) => {
    setData(r);
    if (r.last_result) { setResult(r.last_result); setD1(r.last_result.die1); setD2(r.last_result.die2); }
  }).catch(() => {});
  useEffect(() => { load(); }, []);

  const roll = async () => {
    if (rolling) return;
    setRolling(true); setResult(null);
    playFx("dice"); vibrate(30);
    const spin = setInterval(() => {
      setD1(1 + Math.floor(Math.random() * 6));
      setD2(1 + Math.floor(Math.random() * 6));
    }, 90);
    try {
      const r = await diningApi.diceRoll();
      setTimeout(() => {
        clearInterval(spin);
        setD1(r.die1); setD2(r.die2); setResult(r); setStreak(r.streak || null); setRolling(false);
        load();
        if (r.win) { toast.success("You won a free meal for 8!"); playFx("win"); vibrate([0, 40, 30, 40]); }
        else { playFx("lose"); vibrate(25); }
      }, 1400);
    } catch (e) {
      clearInterval(spin); setRolling(false);
      const code = errCode(e);
      if (code === "already_rolled_today") {
        const res = e?.response?.data?.detail?.result;
        if (res) { setResult(res); setD1(res.die1); setD2(res.die2); }
        toast.info("You've already rolled today — come back tomorrow!");
        load();
      } else toast.error(code);
    }
  };

  const cfg = data?.config || {};
  const canRoll = data?.can_roll && !rolling;

  return (
    <Shell testid="dining-dice">
      <button onClick={() => nav("/dining")} className="flex items-center gap-1 mb-6 text-sm"
        style={{ color: DINE.muted }} data-testid="dining-dice-back">
        <ChevronLeft size={16} /> Dining Club
      </button>
      <div className="text-center">
        <span className="inline-flex items-center gap-2 text-[11px] font-mono uppercase"
          style={{ color: DINE.gold, letterSpacing: "0.16em" }}>
          <Dices size={14} /> Roll &amp; win
        </span>
        <h1 className="text-3xl font-black mt-1" style={{ color: DINE.text }}>Roll two dice — win a free meal for 8</h1>
        <p className="text-sm mt-2" style={{ color: DINE.muted }}>
          {cfg.how_it_works || "Land a double six and your whole table eats free."}
        </p>
        <div className="inline-flex items-center gap-2 mt-3 rounded-full px-3 py-1 text-xs font-bold"
          style={{ background: `${DINE.cyan}18`, color: DINE.cyan, border: `1px solid ${DINE.cyan}44` }}>
          Winning odds: {cfg.win_chance || "1 in 12"}
        </div>

        <div className="flex items-center justify-center gap-5 my-8 mx-auto"
          style={{ maxWidth: 360, borderRadius: 28, padding: "34px 20px",
            backgroundImage: `linear-gradient(rgba(10,6,28,.45),rgba(10,6,28,.65)), url(${DICE_STAGE})`,
            backgroundSize: "cover", backgroundPosition: "center",
            boxShadow: "0 18px 50px rgba(0,0,0,.5)" }}>
          <Die value={d1} rolling={rolling} />
          <span className="text-2xl font-black" style={{ color: "#fff" }}>+</span>
          <Die value={d2} rolling={rolling} />
        </div>

        {result && !rolling && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
            className="rounded-3xl p-6 mb-6" data-testid="dice-result"
            style={{ background: result.win ? `${DINE.gold}14` : DINE.card,
              border: `1px solid ${result.win ? DINE.gold : DINE.border}` }}>
            {result.win ? (
              <>
                <Trophy size={30} style={{ color: DINE.gold }} className="mx-auto mb-2" />
                <div className="text-2xl font-black" style={{ color: DINE.text }}>You won!</div>
                <div className="text-sm mt-1" style={{ color: DINE.muted }}>{result.prize}</div>
                <div className="inline-flex items-center gap-2 mt-3 rounded-xl px-4 py-2 font-mono font-black"
                  style={{ background: DINE.panel, color: DINE.gold, border: `1px dashed ${DINE.gold}` }} data-testid="dice-win-code">
                  <Ticket size={16} /> {result.code}
                </div>
                <p className="text-[11px] mt-3" style={{ color: DINE.muted }}>Show this code at a participating restaurant to redeem your free meal for 8.</p>
              </>
            ) : (
              <>
                <div className="text-xl font-black" style={{ color: DINE.text }}>You rolled {result.total}. So close!</div>
                <div className="text-sm mt-1" style={{ color: DINE.muted }}>Only a double six (12) wins. Come back tomorrow for another roll.</div>
              </>
            )}
            {streak?.bonus?.awarded && (
              <div className="text-sm font-bold mt-3" style={{ color: "#fb923c" }} data-testid="dice-streak-bonus">
                🔥 Day {streak.bonus.streak_day} streak · +{streak.bonus.points} pts{streak.bonus.bonus_spin ? " · +1 bonus spin!" : ""}
              </div>
            )}
          </motion.div>
        )}

        {canRoll ? (
          <NeonBtn testid="dice-roll-btn" onClick={roll} disabled={rolling} color={DINE.pink} full>
            {rolling ? <Loader2 size={18} className="animate-spin" /> : <Dices size={18} />} {rolling ? "Rolling…" : "Roll the dice"}
          </NeonBtn>
        ) : (
          !rolling && <p className="text-sm" style={{ color: DINE.muted }} data-testid="dice-used">You've used today's roll. Come back tomorrow!</p>
        )}
      </div>
    </Shell>
  );
}
