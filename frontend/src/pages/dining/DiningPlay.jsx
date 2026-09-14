// Dining Club — Use-a-Meal: pick preference → spin wheel / surprise → reveal → reroll → accept → pay.
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  ChevronLeft, Leaf, Drumstick, Sun, Moon, Sparkles, Dices, MapPin,
  Loader2, RefreshCw, Check, UtensilsCrossed,
} from "lucide-react";
import { diningApi, DINE, money, errCode } from "./diningApi";
import { Shell, NeonBtn, GhostBtn } from "./DiningHome";

const seg = (n) => 360 / Math.max(1, n);

export default function DiningPlay() {
  const nav = useNavigate();
  const [phase, setPhase] = useState("choose"); // choose | wheel | reveal
  const [veg, setVeg] = useState("VEG");
  const [period, setPeriod] = useState("LUNCH");
  const [session, setSession] = useState(null);
  const [segments, setSegments] = useState(10);
  const [winner, setWinner] = useState(null);
  const [canReroll, setCanReroll] = useState(false);
  const [rotation, setRotation] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [busy, setBusy] = useState(false);
  const revealTimer = useRef(null);

  useEffect(() => () => clearTimeout(revealTimer.current), []);

  const beginWith = (s) => {
    setSession(s);
    const n = s?.pre_spin?.restaurants_available || 10;
    setSegments(n);
    if (s.status === "STARTED") setPhase("wheel");
  };

  const start = async () => {
    setBusy(true);
    try {
      const r = await diningApi.start({ veg_preference: veg, meal_period: period });
      const s = r.session;
      if (r.resumed && ["FIRST_RESULT", "FINAL_RESULT"].includes(s.status)) {
        const v = await diningApi.view(s.session_id);
        setSession(s); setSegments(s?.pre_spin?.restaurants_available || 10);
        setWinner(v.winner); setCanReroll(v.can_reroll); setPhase("reveal");
      } else if (r.resumed && s.status === "ACCEPTED") {
        const v = await diningApi.view(s.session_id);
        if (v.order_id) return nav(`/dining/pass?order_id=${v.order_id}`);
        beginWith(s);
      } else beginWith(s);
    } catch (e) {
      const code = errCode(e);
      if (code === "no_available_credits") toast.error("No meals available — grab more next issuance.");
      else if (code === "not_enough_options") toast.error("Not enough restaurants right now. Try another time or preference.");
      else if (code === "cooldown_active") toast.error("Hang on a moment before starting a new spin.");
      else toast.error(code);
    } finally { setBusy(false); }
  };

  const doSpin = async (method) => {
    if (spinning) return;
    setSpinning(true);
    try {
      const r = method === "wheel" ? await diningApi.spin(session.session_id)
        : await diningApi.surprise(session.session_id);
      setCanReroll(r.can_reroll);
      const n = r.segments || segments;
      setSegments(n);
      if (method === "wheel") {
        const target = 360 * 5 + (360 - ((r.winner_index + 0.5) * seg(n)));
        setRotation(target);
        revealTimer.current = setTimeout(() => { setWinner(r.winner); setPhase("reveal"); setSpinning(false); }, 2900);
      } else {
        setWinner(r.winner); setPhase("reveal"); setSpinning(false);
      }
    } catch (e) { toast.error(errCode(e)); setSpinning(false); }
  };

  const reroll = async () => {
    setBusy(true);
    try {
      await diningApi.reroll(session.session_id);
      setWinner(null); setRotation(0); setPhase("wheel");
      toast("One more spin — this one's final.");
    } catch (e) { toast.error(errCode(e)); }
    finally { setBusy(false); }
  };

  const accept = async () => {
    setBusy(true);
    try {
      const a = await diningApi.accept(session.session_id);
      const co = await diningApi.checkout(a.order_id);
      if (co.requires_payment && co.checkout_url) { window.location.href = co.checkout_url; return; }
      nav(`/dining/pass?order_id=${a.order_id}`);
    } catch (e) {
      const code = errCode(e);
      if (code === "availability_changed") { toast.error("That spot just sold out — spinning again, free."); setWinner(null); setRotation(0); setPhase("wheel"); }
      else toast.error(code);
    } finally { setBusy(false); }
  };

  return (
    <Shell testid="dining-play">
      <button onClick={() => nav("/dining")} className="flex items-center gap-1 mb-6 text-sm" style={{ color: DINE.muted }} data-testid="dining-play-back">
        <ChevronLeft size={16} /> Dining Club
      </button>

      {phase === "choose" && (
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
          <h1 className="text-3xl font-black mb-1" style={{ color: DINE.text }}>Where are you eating today?</h1>
          <p className="text-sm mb-7" style={{ color: DINE.muted }}>Pick a preference — 10 restaurants are waiting behind the wheel.</p>
          <span className="text-[11px] font-mono uppercase" style={{ color: DINE.muted, letterSpacing: "0.14em" }}>Preference</span>
          <div className="grid grid-cols-2 gap-3 mt-2 mb-6">
            <Choice active={veg === "VEG"} onClick={() => setVeg("VEG")} color={DINE.cyan} icon={<Leaf size={20} />} text="Veg" testid="dining-pref-veg" />
            <Choice active={veg === "NON_VEG"} onClick={() => setVeg("NON_VEG")} color={DINE.pink} icon={<Drumstick size={20} />} text="Non-Veg" testid="dining-pref-nonveg" />
          </div>
          <span className="text-[11px] font-mono uppercase" style={{ color: DINE.muted, letterSpacing: "0.14em" }}>Meal</span>
          <div className="grid grid-cols-2 gap-3 mt-2 mb-8">
            <Choice active={period === "LUNCH"} onClick={() => setPeriod("LUNCH")} color={DINE.gold} icon={<Sun size={20} />} text="Lunch" testid="dining-period-lunch" />
            <Choice active={period === "DINNER"} onClick={() => setPeriod("DINNER")} color={DINE.gold} icon={<Moon size={20} />} text="Dinner" testid="dining-period-dinner" />
          </div>
          <NeonBtn testid="play-find" onClick={start} disabled={busy} color={DINE.pink} full>
            {busy ? <Loader2 size={18} className="animate-spin" /> : <Sparkles size={18} />} Find my restaurants
          </NeonBtn>
        </motion.div>
      )}

      {phase === "wheel" && (
        <div className="text-center">
          <h2 className="text-3xl font-black" style={{ color: DINE.text }}>10 restaurants. One surprise.</h2>
          <p className="text-sm mt-1 mb-2" style={{ color: DINE.muted }} data-testid="play-prespin">
            {session?.pre_spin?.restaurants_available} available within ~{session?.pre_spin?.within_miles} mi
            {session?.pre_spin?.cuisine_mix?.length ? ` · ${session.pre_spin.cuisine_mix.slice(0, 4).join(", ")}` : ""}
          </p>
          <Wheel n={segments} rotation={rotation} spinning={spinning} />
          <div className="flex flex-col sm:flex-row gap-3 justify-center mt-8">
            <NeonBtn testid="dining-spin-btn" onClick={() => doSpin("wheel")} disabled={spinning} color={DINE.pink}>
              <Sparkles size={18} /> {spinning ? "Spinning…" : "Spin for my restaurant"}
            </NeonBtn>
            <GhostBtn testid="dining-surprise-btn" onClick={() => doSpin("random")}>
              <Dices size={16} /> Surprise me
            </GhostBtn>
          </div>
        </div>
      )}

      {phase === "reveal" && winner && (
        <motion.div initial={{ opacity: 0, scale: 0.94 }} animate={{ opacity: 1, scale: 1 }} data-testid="play-reveal">
          <div className="text-center mb-4">
            <span className="text-[11px] font-mono uppercase" style={{ color: DINE.gold, letterSpacing: "0.16em" }}>Tonight's destination</span>
            <h1 className="text-4xl font-black mt-1" style={{ color: DINE.text }} data-testid="play-winner-name">{winner.name}</h1>
          </div>
          <div className="rounded-3xl p-6 mb-6" style={{ background: DINE.card, border: `1px solid ${DINE.border}` }}>
            <div className="flex flex-wrap gap-2 mb-4">
              <Pill>{winner.restaurant_class?.replace("_", " ")}</Pill>
              <Pill>{winner.cuisine}</Pill>
              <Pill><MapPin size={12} /> {winner.distance_miles} mi</Pill>
            </div>
            <p className="text-sm mb-1" style={{ color: DINE.muted }}>{winner.address}</p>
            <div className="rounded-2xl p-4 mt-4" style={{ background: `${DINE.pink}12`, border: `1px solid ${DINE.pink}33` }}>
              <span className="text-[11px] font-mono uppercase" style={{ color: DINE.pink, letterSpacing: "0.14em" }}>
                Today's {veg === "VEG" ? "Veg" : "Non-Veg"} Dining Club meal
              </span>
              <div className="flex items-baseline justify-between mt-1">
                <span className="font-bold text-lg" style={{ color: DINE.text }}>{winner.todays_meal?.title || "Chef's selected meal"}</span>
                <span className="font-black text-2xl" style={{ color: DINE.gold }}>{money(winner.meal_price_cents || 999)}</span>
              </div>
            </div>
          </div>
          <div className="flex flex-col sm:flex-row gap-3">
            <NeonBtn testid="dining-accept-btn" onClick={accept} disabled={busy} color={DINE.cyan} full>
              {busy ? <Loader2 size={18} className="animate-spin" /> : <Check size={18} />} Accept &amp; pay {money(winner.meal_price_cents || 999)}
            </NeonBtn>
            {canReroll && (
              <GhostBtn testid="dining-reroll-btn" onClick={reroll}>
                <RefreshCw size={16} /> Not feeling it — one more spin
              </GhostBtn>
            )}
          </div>
          {!canReroll && <p className="text-center text-xs mt-3" style={{ color: DINE.muted }}>This is your final spin for this meal.</p>}
        </motion.div>
      )}
    </Shell>
  );
}

function Choice({ active, onClick, color, icon, text, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className="flex items-center justify-center gap-2 rounded-2xl py-5 font-bold transition"
      style={{ background: active ? `${color}22` : DINE.panel, color: active ? color : DINE.muted, border: `1px solid ${active ? color : DINE.border}` }}>
      {icon} {text}
    </button>
  );
}
function Pill({ children }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full px-3 py-1 text-xs font-semibold capitalize"
      style={{ background: DINE.panel, color: DINE.text, border: `1px solid ${DINE.border}` }}>{children}</span>
  );
}

function Wheel({ n, rotation, spinning }) {
  const colors = [DINE.pink, DINE.cyan];
  const step = seg(n);
  const stops = Array.from({ length: n }, (_, i) =>
    `${colors[i % 2]} ${i * step}deg ${(i + 1) * step}deg`).join(", ");
  return (
    <div className="relative mx-auto my-6" style={{ width: 300, height: 300 }} data-testid="dining-wheel">
      <div style={{
        position: "absolute", top: -6, left: "50%", transform: "translateX(-50%)",
        width: 0, height: 0, borderLeft: "12px solid transparent", borderRight: "12px solid transparent",
        borderTop: `22px solid ${DINE.gold}`, zIndex: 3, filter: `drop-shadow(0 2px 6px ${DINE.gold}88)`,
      }} />
      <motion.div animate={{ rotate: rotation }} transition={{ duration: spinning ? 2.8 : 0, ease: [0.16, 1, 0.3, 1] }}
        style={{
          width: 300, height: 300, borderRadius: "50%",
          background: `conic-gradient(${stops})`,
          border: `6px solid ${DINE.gold}`, boxShadow: `0 0 60px ${DINE.pink}44, inset 0 0 40px #00000066`,
        }}>
        {Array.from({ length: n }, (_, i) => (
          <span key={i} style={{
            position: "absolute", top: "50%", left: "50%", color: "#0a0c18", fontWeight: 900, fontSize: 14,
            transform: `rotate(${i * step + step / 2}deg) translateY(-120px) rotate(${-(i * step + step / 2)}deg)`,
            transformOrigin: "0 0",
          }}>{i + 1}</span>
        ))}
      </motion.div>
      <div style={{
        position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)",
        width: 60, height: 60, borderRadius: "50%", background: DINE.bg, border: `4px solid ${DINE.gold}`,
        display: "flex", alignItems: "center", justifyContent: "center", zIndex: 2,
      }}><UtensilsCrossed color={DINE.gold} size={24} /></div>
    </div>
  );
}
