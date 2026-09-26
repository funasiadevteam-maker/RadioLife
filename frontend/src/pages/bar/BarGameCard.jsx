// Phase 5 — Gamified Bar Purchase. Drink-themed spin wheel on the bar's page.
// Renders NOTHING unless the business is a bar/club. Spins come from paid orders
// PLUS one free spin per day. Bars can theme the wheel (colours, logo, prizes).
// Wheel has spin sound + win chime + haptics; owners can customise; wins go to
// the "My drink perks" wallet (/drink-perks).
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import axios from "axios";
import { toast } from "sonner";
import { motion } from "framer-motion";
import { Loader2, Wine, Ticket, RefreshCw, Sparkles, Gift, Clock, Palette, Wallet, Radio, ScanLine } from "lucide-react";
import BarSkinEditor from "./BarSkinEditor";
import BarOwnerScheduler from "./BarOwnerScheduler";
import BarStaffScan from "./BarStaffScan";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const WHEEL = ["#a855f7", "#ec4899", "#f59e0b", "#22d3ee", "#34d399", "#f472b6", "#8b5cf6"];

function resetIn(iso) {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  if (diff <= 0) return "soon";
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  return h >= 1 ? `${h}h ${m}m` : `${m}m`;
}

// ── Sound (WebAudio, no assets) + haptics ─────────────────────────
function playSpinSound(ctxRef) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = ctxRef.current || (ctxRef.current = new Ctx());
    if (ctx.state === "suspended") ctx.resume();
    const now = ctx.currentTime;
    // Descending "whir" that slows down like a real wheel.
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sawtooth";
    osc.frequency.setValueAtTime(620, now);
    osc.frequency.exponentialRampToValueAtTime(90, now + 3.2);
    gain.gain.setValueAtTime(0.06, now);
    gain.gain.exponentialRampToValueAtTime(0.001, now + 3.3);
    osc.connect(gain).connect(ctx.destination);
    osc.start(now); osc.stop(now + 3.35);
  } catch (_) {}
}
function playWinSound(ctxRef) {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = ctxRef.current || (ctxRef.current = new Ctx());
    if (ctx.state === "suspended") ctx.resume();
    const now = ctx.currentTime;
    [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "triangle";
      osc.frequency.value = f;
      const t = now + i * 0.11;
      gain.gain.setValueAtTime(0.0001, t);
      gain.gain.exponentialRampToValueAtTime(0.15, t + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, t + 0.35);
      osc.connect(gain).connect(ctx.destination);
      osc.start(t); osc.stop(t + 0.4);
    });
  } catch (_) {}
}
const vibrate = (p) => { try { navigator.vibrate && navigator.vibrate(p); } catch (_) {} };

export default function BarGameCard({ businessId }) {
  const navigate = useNavigate();
  const [data, setData] = useState(null);
  const [spinning, setSpinning] = useState(false);
  const [rot, setRot] = useState(0);
  const [result, setResult] = useState(null);
  const [editing, setEditing] = useState(false);
  const [scheduling, setScheduling] = useState(false);
  const [scanning, setScanning] = useState(false);
  const audioRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await axios.get(`${API}/bar-games/${businessId}`, { withCredentials: true });
      setData(data);
      if (data?.last_result) setResult(data.last_result);
    } catch (_) { setData({ eligible: false }); }
  }, [businessId]);
  useEffect(() => { load(); }, [load]);

  const claim = async () => {
    try {
      const { data } = await axios.post(`${API}/bar-games/${businessId}/claim`, {}, { withCredentials: true });
      setData(data);
      if (data.granted > 0) toast.success(`${data.granted} spin unlocked 🎉`);
      else toast.info("Buy a round at this bar to unlock a spin.");
    } catch (_) { toast.error("Couldn’t refresh."); }
  };

  const spin = async () => {
    if (spinning) return;
    setSpinning(true); setResult(null);
    playSpinSound(audioRef); vibrate(20);
    try {
      const { data: res } = await axios.post(`${API}/bar-games/${businessId}/spin`, {}, { withCredentials: true });
      const n = res.segments?.length || data?.config?.segments?.length || 1;
      const seg = 360 / n;
      const target = 360 * 5 + (360 - (res.segment_index + 0.5) * seg);
      setRot((r) => r - (r % 360) + target);
      setTimeout(() => {
        setSpinning(false);
        setResult(res);
        setData((d) => ({ ...d, spins_available: res.spins_available,
          free_spin_available: res.free_spin_available,
          total_playable: (res.spins_available || 0) + (res.free_spin_available ? 1 : 0) }));
        if (res.win) { playWinSound(audioRef); vibrate([0, 60, 40, 120]); toast.success(`You won: ${res.prize}! 🍸 Saved to My Perks`); }
        else vibrate(40);
      }, 3400);
    } catch (e) {
      setSpinning(false);
      const code = e?.response?.data?.detail?.code;
      if (code === "no_spin_unlocked") toast.info(e?.response?.data?.detail?.message || "No spins left today.");
      else toast.error("Couldn’t spin. Try again.");
      load();
    }
  };

  if (!data || !data.eligible) return null;

  const theme = data.config?.theme || {};
  const accent = theme.accent || "#a855f7";
  const accent2 = theme.accent2 || "#ec4899";
  const logo = theme.logo_url;
  const segments = data.config?.segments || [];
  const n = segments.length || 1;
  const seg = 360 / n;
  const purchaseSpins = data.spins_available || 0;
  const freeReady = !!data.free_spin_available;
  const playable = (data.total_playable ?? (purchaseSpins + (freeReady ? 1 : 0))) > 0;
  const gradient = `conic-gradient(${segments.map((s, i) => `${WHEEL[i % WHEEL.length]} ${i * seg}deg ${(i + 1) * seg}deg`).join(",")})`;
  const btnGrad = `linear-gradient(135deg,${accent},${accent2})`;

  return (
    <div className="mt-4 rounded-3xl p-5 border"
         style={{ background: "linear-gradient(135deg,#160f2e,#241041)", borderColor: `${accent}55` }}
         data-testid="bar-game-card">
      <div className="flex items-center gap-2 mb-1">
        <span className="grid place-items-center w-9 h-9 rounded-xl text-white overflow-hidden"
              style={{ background: btnGrad }}>
          {logo ? <img src={logo} alt="" className="w-full h-full object-cover" /> : <Wine size={18} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-white font-black text-base">Spin the Bar Wheel</div>
          <div className="text-[11px] truncate" style={{ color: `${accent}` }}>{data.config?.how_it_works}</div>
        </div>
      </div>

      {/* actions: perks wallet + owner customise */}
      <div className="flex items-center gap-2 flex-wrap mt-2">
        <button onClick={() => navigate("/drink-perks")} data-testid="bar-game-perks-link"
                className="inline-flex items-center gap-1.5 text-[11px] font-bold rounded-full px-3 py-1.5 bg-white/10 text-white">
          <Wallet size={12} /> My drink perks
        </button>
        {data.is_owner && (
          <button onClick={() => setEditing(true)} data-testid="bar-game-customize"
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold rounded-full px-3 py-1.5"
                  style={{ background: `${accent}22`, color: accent }}>
            <Palette size={12} /> Customize wheel
          </button>
        )}
        {data.is_owner && (
          <button onClick={() => setScheduling(true)} data-testid="bar-game-schedule-live"
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold rounded-full px-3 py-1.5"
                  style={{ background: "rgba(236,72,153,0.18)", color: "#f9a8d4" }}>
            <Radio size={12} /> Schedule Live event
          </button>
        )}
        {data.is_owner && (
          <button onClick={() => setScanning(true)} data-testid="bar-game-scan"
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold rounded-full px-3 py-1.5"
                  style={{ background: "rgba(52,211,153,0.16)", color: "#34d399" }}>
            <ScanLine size={12} /> Redeem a perk
          </button>
        )}
      </div>

      {/* spin sources */}
      <div className="flex items-center gap-2 flex-wrap mt-2" data-testid="bar-game-sources">
        {purchaseSpins > 0 && (
          <span className="inline-flex items-center gap-1 text-[11px] font-bold rounded-full px-2.5 py-1"
                style={{ background: `${accent}22`, color: accent }}>
            <Ticket size={11} /> {purchaseSpins} unlocked
          </span>
        )}
        <span className="inline-flex items-center gap-1 text-[11px] font-bold rounded-full px-2.5 py-1"
              data-testid="bar-game-free-chip"
              style={{ background: freeReady ? "rgba(52,211,153,0.16)" : "rgba(255,255,255,0.06)",
                       color: freeReady ? "#34d399" : "#94a3b8" }}>
          {freeReady ? <><Gift size={11} /> Free daily spin ready</>
                     : <><Clock size={11} /> Free spin in {resetIn(data.next_free_reset)}</>}
        </span>
      </div>

      <div className="flex flex-col items-center mt-4">
        <div className="relative" style={{ width: 240, height: 240 }}>
          <div className="absolute left-1/2 -translate-x-1/2 -top-1 z-10"
               style={{ width: 0, height: 0, borderLeft: "12px solid transparent", borderRight: "12px solid transparent", borderTop: "20px solid #fff" }} />
          <motion.div animate={{ rotate: rot }}
            transition={{ duration: 3.2, ease: [0.16, 1, 0.3, 1] }}
            className="rounded-full border-4 border-white/80 grid place-items-center"
            style={{ width: 240, height: 240, background: gradient, boxShadow: `0 0 40px ${accent}55` }}>
            {segments.map((s, i) => (
              <div key={i} className="absolute text-center"
                   style={{ transform: `rotate(${(i + 0.5) * seg}deg) translateY(-92px) rotate(-${(i + 0.5) * seg}deg)`, width: 70 }}>
                <div style={{ fontSize: 22 }}>{s.emoji}</div>
                <div className="text-[9px] font-black text-white leading-tight">{s.label}</div>
              </div>
            ))}
            <div className="w-12 h-12 rounded-full bg-white/90 grid place-items-center overflow-hidden">
              {logo ? <img src={logo} alt="" className="w-full h-full object-cover" /> : <Sparkles size={18} style={{ color: accent }} />}
            </div>
          </motion.div>
        </div>

        {result && !spinning && (
          <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
            className="mt-4 w-full rounded-2xl p-4 text-center" data-testid="bar-game-result"
            style={{ background: result.win ? "rgba(52,211,153,0.12)" : "rgba(255,255,255,0.05)",
                     border: `1px solid ${result.win ? "#34d399" : "rgba(255,255,255,0.12)"}` }}>
            {result.win ? (
              <>
                <div className="text-white font-black text-lg">🍸 {result.label}</div>
                <div className="inline-flex items-center gap-2 mt-2 rounded-xl px-4 py-2 font-mono font-black text-emerald-300"
                     style={{ background: "rgba(0,0,0,0.3)", border: "1px dashed #34d399" }} data-testid="bar-game-code">
                  <Ticket size={15} /> {result.code}
                </div>
                <p className="text-[11px] text-slate-300/70 mt-2">Saved to My Perks — show this code at the bar to redeem.</p>
              </>
            ) : (
              <div className="text-white font-bold">{result.emoji} {result.label} — no win this time.</div>
            )}
          </motion.div>
        )}

        <div className="mt-4 w-full">
          {playable ? (
            <button onClick={spin} disabled={spinning} data-testid="bar-game-spin"
              className="w-full h-12 rounded-full text-white font-black inline-flex items-center justify-center gap-2"
              style={{ background: btnGrad }}>
              {spinning ? <Loader2 size={18} className="animate-spin" /> : <Wine size={18} />}
              {spinning ? "Spinning…" : purchaseSpins > 0 ? `Spin now · ${purchaseSpins} left` : "Free daily spin"}
            </button>
          ) : (
            <div className="text-center">
              <p className="text-sm text-slate-300/80" data-testid="bar-game-locked">
                All done for today — your free spin resets in {resetIn(data.next_free_reset)}. Buy a round to unlock more.
              </p>
              <button onClick={claim} data-testid="bar-game-claim"
                className="mt-2 inline-flex items-center gap-1.5 text-xs font-bold text-white h-9 px-4 rounded-full bg-white/10">
                <RefreshCw size={13} /> I just bought — unlock my spin
              </button>
            </div>
          )}
        </div>
      </div>

      {editing && (
        <BarSkinEditor businessId={businessId} config={data.config}
          onClose={() => setEditing(false)}
          onSaved={(cfg) => { setEditing(false); setData((d) => ({ ...d, config: cfg })); toast.success("Wheel updated 🎨"); }} />
      )}
      {scheduling && (
        <BarOwnerScheduler businessId={businessId} businessName={data.business_name}
          onClose={() => setScheduling(false)}
          onScheduled={() => setScheduling(false)} />
      )}
      {scanning && (
        <BarStaffScan businessId={businessId} onClose={() => setScanning(false)} />
      )}
    </div>
  );
}
