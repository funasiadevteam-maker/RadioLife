// Dining Club — consumer home + enrollment (web).
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { toast } from "sonner";
import {
  UtensilsCrossed, Sparkles, Ticket, Clock, ChevronLeft, Crown,
  Minus, Plus, Store, Loader2, Leaf, Drumstick, Dices,
} from "lucide-react";
import { diningApi, DINE, money, errCode } from "./diningApi";

const Label = ({ children }) => (
  <span style={{ color: DINE.muted, letterSpacing: "0.14em" }}
    className="text-[11px] font-mono uppercase">{children}</span>
);

export default function DiningHome() {
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [meals, setMeals] = useState(5);
  const [veg, setVeg] = useState("VEG");
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { setData(await diningApi.home()); }
    catch (e) { toast.error(errCode(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    (async () => {
      const params = new URLSearchParams(window.location.search);
      const sid = params.get("session_id");
      if (sid && window.location.pathname.includes("enrolled")) {
        try { await diningApi.subscribeStatus(sid); toast.success("Membership active!"); } catch { /* keep going */ }
      }
      await load();
    })();
  }, []);

  const enroll = async () => {
    setBusy(true);
    try {
      const r = await diningApi.subscribe({ meals_per_week: meals, veg_default: veg });
      if (r.requires_payment && r.checkout_url) { window.location.href = r.checkout_url; return; }
      toast.success("Welcome to the Dining Club!");
      await load();
    } catch (e) { toast.error(errCode(e)); }
    finally { setBusy(false); }
  };

  if (loading) return <Shell><div className="flex justify-center py-24"><Loader2 className="animate-spin" color={DINE.pink} /></div></Shell>;

  const m = data?.membership;
  const active = m && m.status === "active";
  const c = data?.credits || {};
  const min = data?.program?.min_meals_week || 3;
  const max = data?.program?.max_meals_week || 14;
  const clamp = (v) => Math.max(min, Math.min(max, v));

  return (
    <Shell testid="dining-home">
      <button onClick={() => nav(-1)} data-testid="dining-back"
        className="flex items-center gap-1 mb-6 text-sm" style={{ color: DINE.muted }}>
        <ChevronLeft size={16} /> Back
      </button>

      {/* Hero */}
      <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
        className="rounded-3xl p-8 mb-8 relative overflow-hidden"
        style={{ background: `linear-gradient(135deg, ${DINE.pink}22, ${DINE.cyan}18)`, border: `1px solid ${DINE.border}` }}>
        <div className="flex items-center gap-2 mb-3"><UtensilsCrossed color={DINE.pink} /><Label>FUUSIC Dining Club</Label></div>
        <h1 className="text-4xl sm:text-5xl font-black leading-none mb-3" style={{ color: DINE.text }}>
          Stop deciding<br />where to eat.
        </h1>
        <p className="text-base max-w-lg" style={{ color: DINE.muted }}>
          Choose <b style={{ color: DINE.cyan }}>Veg</b> or <b style={{ color: DINE.gold }}>Non-Veg</b> — we spin you a
          surprise restaurant. Every meal a flat <b style={{ color: DINE.gold }}>{money(data?.meal_price_cents)}</b>.
        </p>
      </motion.div>

      {active ? (
        <div className="grid sm:grid-cols-3 gap-4 mb-8">
          <Stat testid="dining-meals-available" icon={<Ticket color={DINE.cyan} />} value={c.available ?? 0} label="Meals available" />
          <Stat testid="dining-expiring" icon={<Clock color={DINE.gold} />} value={c.expiring_soon ?? 0} label="Expiring soon" />
          <Stat testid="dining-days-left" icon={<Crown color={DINE.pink} />} value={data?.days_remaining ?? "—"} label="Days remaining" />
        </div>
      ) : null}

      <button onClick={() => nav("/dining/dice")} data-testid="dining-dice-cta"
        className="w-full flex items-center justify-between gap-2 rounded-2xl px-5 py-4 mb-5 font-black transition"
        style={{ background: `${DINE.gold}12`, color: DINE.text, border: `1px solid ${DINE.gold}55` }}>
        <span className="flex items-center gap-2"><Dices size={18} style={{ color: DINE.gold }} /> Roll the dice — win a free meal for 8</span>
        <span className="text-xs font-mono uppercase tracking-wider" style={{ color: DINE.gold }}>1 in 12 →</span>
      </button>

      {active ? (
        <div className="flex flex-col sm:flex-row gap-3">
          <NeonBtn testid="dining-use-meal-btn" onClick={() => nav("/dining/play")}
            disabled={(c.available ?? 0) < 1} color={DINE.pink}>
            <Sparkles size={18} /> Use a Meal
          </NeonBtn>
          <GhostBtn testid="dining-merchant-link" onClick={() => nav("/dining/merchant")}>
            <Store size={16} /> Restaurant portal
          </GhostBtn>
        </div>
      ) : (
        <div className="rounded-3xl p-6" style={{ background: DINE.card, border: `1px solid ${DINE.border}` }}>
          <Label>Join the club · 30 days</Label>
          {!data?.is_premium && (
            <div className="mt-3 mb-4 rounded-2xl p-4 flex items-start gap-3"
              style={{ background: `${DINE.gold}14`, border: `1px solid ${DINE.gold}44` }} data-testid="dining-premium-bundle">
              <Crown color={DINE.gold} className="shrink-0 mt-0.5" size={18} />
              <p className="text-sm" style={{ color: DINE.text }}>
                Dining Club is a <b>Premium</b> benefit. Joining bundles <b>FUUSIC Annual Premium</b>
                {data?.premium_price?.amount_cents ? <> ({money(data.premium_price.amount_cents)}/yr)</> : null} with your Dining Club membership.
              </p>
            </div>
          )}
          <h3 className="text-2xl font-black mt-4 mb-1" style={{ color: DINE.text }}>How many meals each week?</h3>
          <p className="text-sm mb-5" style={{ color: DINE.muted }}>{min}–{max} meals/week · issued weekly, each credit valid 30 days.</p>

          <div className="flex items-center gap-5 mb-6">
            <IconBtn testid="dining-meals-dec" onClick={() => setMeals((v) => clamp(v - 1))}><Minus size={20} /></IconBtn>
            <div className="text-center w-24">
              <div className="text-5xl font-black" style={{ color: DINE.cyan }} data-testid="dining-meals-value">{meals}</div>
              <Label>meals / week</Label>
            </div>
            <IconBtn testid="dining-meals-inc" onClick={() => setMeals((v) => clamp(v + 1))}><Plus size={20} /></IconBtn>
          </div>

          <Label>Default preference</Label>
          <div className="grid grid-cols-2 gap-3 mt-2 mb-6">
            <VegToggle active={veg === "VEG"} onClick={() => setVeg("VEG")} testid="dining-veg" color={DINE.cyan} icon={<Leaf size={18} />} text="Veg" />
            <VegToggle active={veg === "NON_VEG"} onClick={() => setVeg("NON_VEG")} testid="dining-nonveg" color={DINE.pink} icon={<Drumstick size={18} />} text="Non-Veg" />
          </div>

          <NeonBtn testid="dining-join" onClick={enroll} disabled={busy} color={DINE.pink} full>
            {busy ? <Loader2 size={18} className="animate-spin" /> : <UtensilsCrossed size={18} />}
            Join Dining Club — {meals} meals/week
          </NeonBtn>
          <p className="text-center text-xs mt-3" style={{ color: DINE.muted }}>
            {money(data?.meal_price_cents)} per redeemed meal. Restaurant assigned at random. Cancel anytime.
          </p>
        </div>
      )}
    </Shell>
  );
}

// ── shared primitives ──────────────────────────────────────────────
export function Shell({ children, testid }) {
  return (
    <div style={{ background: DINE.bg, minHeight: "100vh", color: DINE.text }} data-testid={testid}>
      <div className="max-w-3xl mx-auto px-5 py-8">{children}</div>
    </div>
  );
}
function Stat({ icon, value, label, testid }) {
  return (
    <div className="rounded-2xl p-5" style={{ background: DINE.card, border: `1px solid ${DINE.border}` }} data-testid={testid}>
      <div className="mb-2">{icon}</div>
      <div className="text-3xl font-black">{value}</div>
      <Label>{label}</Label>
    </div>
  );
}
export function NeonBtn({ children, onClick, color, disabled, full, testid }) {
  return (
    <button onClick={onClick} disabled={disabled} data-testid={testid}
      className={`flex items-center justify-center gap-2 font-bold rounded-full px-6 py-3.5 transition ${full ? "w-full" : ""}`}
      style={{ background: color, color: "#0a0c18", opacity: disabled ? 0.45 : 1, boxShadow: `0 8px 30px ${color}55` }}>
      {children}
    </button>
  );
}
export function GhostBtn({ children, onClick, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className="flex items-center justify-center gap-2 font-semibold rounded-full px-6 py-3.5"
      style={{ background: "transparent", color: DINE.text, border: `1px solid ${DINE.border}` }}>
      {children}
    </button>
  );
}
function IconBtn({ children, onClick, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className="rounded-full w-12 h-12 flex items-center justify-center"
      style={{ background: DINE.panel, border: `1px solid ${DINE.border}`, color: DINE.text }}>
      {children}
    </button>
  );
}
function VegToggle({ active, onClick, color, icon, text, testid }) {
  return (
    <button onClick={onClick} data-testid={testid}
      className="flex items-center justify-center gap-2 rounded-2xl py-4 font-bold transition"
      style={{ background: active ? `${color}22` : DINE.panel, color: active ? color : DINE.muted, border: `1px solid ${active ? color : DINE.border}` }}>
      {icon} {text}
    </button>
  );
}
