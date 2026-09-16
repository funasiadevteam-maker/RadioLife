// New Look V2 — PUBLIC / logged-out landing. Same premium design language as
// the logged-in V2 home so login simply unlocks the personalized version of
// the SAME product. Self-contained (own header + footer); rendered bare by
// AppShellV2 for anonymous `/`.
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";
import {
  Radio, Sparkles, Play, Pause, Coins, Utensils, ShoppingBag, Gamepad2, Users,
  Crown, ArrowRight, Globe, Trophy, Store, Megaphone, Smartphone, Headphones,
  Check, ChevronRight, Star, X,
} from "lucide-react";
import { HERO_IMG } from "./analytics";
import { setIntent } from "@/utils/intent";
import { toPlayableStreamUrl } from "@/utils/streamUrl";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;
const CONTAINER = "max-w-[1240px] mx-auto w-full px-4 sm:px-6 lg:px-8";

const NAV_LINKS = [
  { label: "Listen", to: "/listen" },
  { label: "Shop", to: "/shop" },
  { label: "Play", to: "/play-and-win" },
  { label: "Dining Club", to: "/dining" },
  { label: "For Business", to: "/for-business" },
];

const STATION_FALLBACK = [
  { name: "Big FM Live", music_genre: "Bollywood", country: "UAE" },
  { name: "Bollywood Live", music_genre: "Bollywood", country: "India" },
  { name: "Dallas Radio", music_genre: "Top 40", country: "USA" },
  { name: "Punjabi Hits", music_genre: "Punjabi", country: "India" },
  { name: "Latin Hits", music_genre: "Latin", country: "Global" },
  { name: "K-Pop", music_genre: "K-Pop", country: "Korea" },
  { name: "Arabic Vibes", music_genre: "Arabic", country: "UAE" },
  { name: "World Radio", music_genre: "World", country: "Global" },
];

const GRADS = [
  "linear-gradient(135deg,#a855f7,#ec4899)",
  "linear-gradient(135deg,#3b82f6,#8b5cf6)",
  "linear-gradient(135deg,#ec4899,#f59e0b)",
  "linear-gradient(135deg,#06b6d4,#3b82f6)",
  "linear-gradient(135deg,#8b5cf6,#22d3ee)",
  "linear-gradient(135deg,#f43f5e,#a855f7)",
  "linear-gradient(135deg,#f59e0b,#ec4899)",
  "linear-gradient(135deg,#22c55e,#06b6d4)",
];

function fmtCount(n) {
  if (!n || n < 1000) return "50,000+";
  if (n >= 1000) return `${Math.floor(n / 1000)}k+`;
  return `${n}+`;
}

// Soft-launch — Coming-Soon waitlist capture (posts to /api/waitlist).
function WaitlistForm({ enabled = true }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    const v = email.trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) { setErr("Enter a valid email"); return; }
    setBusy(true);
    try {
      await axios.post(`${API}/waitlist`, { email: v, interests: ["consumer"] });
      setDone(true);
    } catch (_e) {
      setErr("Could not join right now. Please try again.");
    } finally { setBusy(false); }
  };
  if (!enabled) return null;
  if (done) {
    return (
      <div data-testid="waitlist-success" className="nlv2-glass rounded-2xl px-5 py-4 inline-flex items-center gap-2 text-white">
        <Check size={18} className="text-emerald-400" />
        <span className="text-sm font-semibold">You&apos;re on the list — we&apos;ll email you the moment we open.</span>
      </div>
    );
  }
  return (
    <form onSubmit={submit} data-testid="waitlist-form" className="flex flex-col sm:flex-row gap-3 w-full max-w-md">
      <input type="email" value={email} onChange={(e) => setEmail(e.target.value)}
        placeholder="you@email.com" data-testid="waitlist-email"
        className="flex-1 h-12 rounded-full px-5 text-sm bg-white/10 border border-white/15 text-white placeholder:text-white/40 outline-none focus:border-violet-400" />
      <button type="submit" disabled={busy} data-testid="waitlist-submit"
        className="h-12 px-6 rounded-full font-bold text-sm text-white disabled:opacity-60"
        style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
        {busy ? "Joining…" : "Join the waitlist"}
      </button>
      {err && <div data-testid="waitlist-error" className="text-xs text-rose-400 self-center">{err}</div>}
    </form>
  );
}

function ComingSoonHero({ offerMonths = 6, waitlistEnabled = true, onBusiness }) {
  return (
    <section className={`${CONTAINER} pt-12 lg:pt-20 pb-8`} data-testid="coming-soon-hero">
      <div className="max-w-3xl">
        <div className="inline-flex items-center gap-2 text-[11px] font-mono uppercase tracking-widest px-3 py-1 rounded-full nlv2-chip" style={{ color: "#c4b5fd" }}>
          <Sparkles size={13} /> Launching soon
        </div>
        <h1 className="mt-5 font-black leading-[0.98] tracking-tight text-white text-4xl sm:text-5xl lg:text-6xl" data-testid="coming-soon-h1">
          Radio that rewards you.<br />
          <span className="nlv2-grad">Almost here.</span>
        </h1>
        <p className="mt-5 text-base sm:text-lg leading-relaxed" style={{ color: "#a8b0cc" }}>
          We&apos;re building the business network first — great local shops, restaurants and brands are
          setting up now. Join the waitlist and be first in line when RadioLife opens to listeners.
        </p>
        {waitlistEnabled && (
          <div className="mt-7">
            <WaitlistForm enabled={waitlistEnabled} />
          </div>
        )}
        <div className="mt-8 nlv2-glass rounded-2xl p-5 sm:p-6 flex flex-col sm:flex-row sm:items-center gap-4" data-testid="coming-soon-business">
          <div className="flex-1">
            <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#f5c563" }}>
              <Store size={13} className="inline mr-1" /> For Business
            </div>
            <div className="mt-1 font-black text-white text-lg">Get {offerMonths} months free</div>
            <div className="mt-1 text-[13px]" style={{ color: "#97a3c2" }}>
              Set up your storefront now. No monthly fee for {offerMonths} months — you only pay a small commission when you sell.
            </div>
          </div>
          <button onClick={onBusiness} data-testid="coming-soon-business-cta"
            className="shrink-0 h-12 px-6 rounded-full font-bold text-sm text-black inline-flex items-center gap-2"
            style={{ background: "linear-gradient(135deg,#f59e0b,#f5c563)" }}>
            Claim {offerMonths} months free <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </section>
  );
}

export default function PublicHomeNewLookV2({ comingSoon = false, offerMonths = 6, waitlistEnabled = true }) {
  const navigate = useNavigate();
  const [stations, setStations] = useState(STATION_FALLBACK);
  const [count, setCount] = useState(0);
  const howRef = useRef(null);
  const audioRef = useRef(null);
  const timerRef = useRef(null);
  const [previewId, setPreviewId] = useState(null);
  const [previewStation, setPreviewStation] = useState(null);
  const [previewEnded, setPreviewEnded] = useState(false);

  const sessionId = useMemo(() => {
    try {
      let s = localStorage.getItem("rl_land_sid");
      if (!s) { s = Math.random().toString(36).slice(2) + Date.now().toString(36); localStorage.setItem("rl_land_sid", s); }
      return s;
    } catch { return "anon"; }
  }, []);

  // Fire-and-forget landing analytics (CTA clicks, section views, previews).
  const track = useCallback((event, extra = {}) => {
    try { axios.post(`${API}/shell/landing-event`, { event, session_id: sessionId, ...extra }).catch(() => {}); }
    catch (_e) { /* ignore */ }
  }, [sessionId]);

  // Preserve-intent CTA: remember where they wanted to go, then to /login.
  const ctaTo = useCallback((label, intentPath) => () => {
    track("cta", { cta: label });
    if (intentPath) setIntent(intentPath);
    navigate("/login");
  }, [track, navigate]);
  const toLogin = useCallback(() => { track("cta", { cta: "signin" }); navigate("/login"); }, [track, navigate]);

  const stopPreview = useCallback(() => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null; }
    if (audioRef.current) { try { audioRef.current.pause(); } catch (_e) { /* */ } }
    setPreviewId(null);
    setPreviewEnded(false);
    setPreviewStation(null);
  }, []);

  // Let logged-out visitors hear a 30s sample before signing up.
  const playPreview = useCallback((station) => {
    const id = station.id || station.name;
    if (previewId === id) { stopPreview(); return; }
    const src = toPlayableStreamUrl(station.stream_url);
    setPreviewStation(station);
    setPreviewEnded(false);
    if (!src) { setPreviewId(null); setPreviewEnded(true); return; }
    if (!audioRef.current) audioRef.current = new Audio();
    const a = audioRef.current;
    if (timerRef.current) clearTimeout(timerRef.current);
    a.onerror = () => { setPreviewId(null); setPreviewEnded(true); };
    try {
      a.src = src;
      a.volume = 0.9;
      a.play().then(() => {
        setPreviewId(id);
        track("preview_play", { cta: station.name });
        timerRef.current = setTimeout(() => {
          try { a.pause(); } catch (_e) { /* */ }
          setPreviewId(null); setPreviewEnded(true);
        }, 30000);
      }).catch(() => { setPreviewId(null); setPreviewEnded(true); });
    } catch (_e) { setPreviewId(null); setPreviewEnded(true); }
  }, [previewId, stopPreview, track]);

  useEffect(() => () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    if (audioRef.current) { try { audioRef.current.pause(); } catch (_e) { /* */ } }
  }, []);

  useEffect(() => {
    document.title = "RadioLife — Radio that rewards you · Live + AI Radio";
    let meta = document.querySelector('meta[name="description"]');
    if (!meta) { meta = document.createElement("meta"); meta.name = "description"; document.head.appendChild(meta); }
    meta.content = "RadioLife is a better way to listen. Live stations from around the world + AI radio built around you — and your listening earns BigPoints you spend on rewards, dining and local deals.";
  }, []);

  useEffect(() => {
    let alive = true;
    axios.get(`${API}/live-radio/stations?limit=40`)
      .then((r) => {
        if (!alive) return;
        const items = r?.data?.items || [];
        // Prefer https streams — they preview reliably for logged-out
        // visitors (no mixed-content block / proxy allowlist gap).
        const isHttps = (s) => String(s.stream_url || "").startsWith("https://");
        const ordered = [...items.filter(isHttps), ...items.filter((s) => !isHttps(s))];
        if (ordered.length) setStations(ordered.slice(0, 8));
        setCount(r?.data?.total || 0);
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  // Section-view analytics — observe existing section test-ids (no markup change).
  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    const NAMES = ["public-live-header", "public-airadio", "public-how-header",
      "public-bigpoints", "public-dining", "public-shop", "public-play",
      "public-social", "public-premium", "public-appcta"];
    const seen = new Set();
    const obs = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (!e.isIntersecting) return;
        const name = e.target.getAttribute("data-testid");
        if (name && !seen.has(name)) { seen.add(name); track("section_view", { section: name }); }
      });
    }, { threshold: 0.4 });
    NAMES.forEach((n) => { const el = document.querySelector(`[data-testid="${n}"]`); if (el) obs.observe(el); });
    return () => obs.disconnect();
  }, [track]);

  const stationCount = useMemo(() => fmtCount(count), [count]);

  return (
    <div className="nlv2" data-testid="public-home-v2">
      <PublicNav onSignIn={toLogin} onStart={ctaTo("nav_getstarted", "/listen")} />

      <main className="relative z-10">
        {comingSoon && (
          <ComingSoonHero offerMonths={offerMonths} waitlistEnabled={waitlistEnabled}
            onBusiness={() => { track("cta", { cta: "coming_soon_business" }); navigate("/for-business"); }} />
        )}
        {/* ─── HERO ─────────────────────────────────────────────── */}
        <section className={`${CONTAINER} pt-10 lg:pt-16 pb-10`}>
          <div className="nlv2-hero-grid grid grid-cols-1 lg:grid-cols-[1.05fr_0.95fr] gap-8 lg:gap-10 items-center">
            <div>
              <div className="inline-flex items-center gap-2 text-[11px] font-mono uppercase tracking-widest px-3 py-1 rounded-full nlv2-chip" style={{ color: "#c4b5fd" }}>
                <span className="w-1.5 h-1.5 rounded-full" style={{ background: "#f472b6" }} /> Live · Personalized · Rewarded
              </div>
              <h1 className="mt-4 font-black leading-[0.98] tracking-tight text-white text-4xl sm:text-5xl lg:text-6xl" data-testid="public-hero-h1">
                LIVE RADIO.<br />AI RADIO.<br /><span className="nlv2-grad">MORE THAN RADIO.</span>
              </h1>
              <p className="mt-5 text-[15px] leading-relaxed max-w-xl" style={{ color: "#a8b0cc" }}>
                Listen to live stations from around the world, or let AI build a radio experience around what you love. Earn BigPoints while you listen — then play, shop, discover restaurants and connect with friends.
              </p>
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <button onClick={ctaTo("hero_start", "/listen")} data-testid="public-cta-start"
                  className="nlv2-btn inline-flex items-center gap-2 font-black text-sm px-6 py-3 rounded-full">
                  <Play size={16} fill="currentColor" /> START LISTENING
                </button>
                <button onClick={ctaTo("hero_explore", "/listen")} data-testid="public-cta-explore"
                  className="nlv2-btn-ghost inline-flex items-center gap-2 font-bold text-sm px-6 py-3 rounded-full">
                  <Radio size={16} /> EXPLORE LIVE RADIO
                </button>
                <button onClick={() => howRef.current?.scrollIntoView({ behavior: "smooth" })}
                  data-testid="public-cta-how"
                  className="inline-flex items-center gap-1 font-semibold text-sm px-2 py-3" style={{ color: "#8b96b8" }}>
                  See how RadioLife works <ChevronRight size={15} />
                </button>
              </div>
              <div className="mt-8 flex flex-wrap gap-x-7 gap-y-3">
                {[
                  [stationCount, "Stations"], ["Global", "Radio"], ["AI", "Radio"],
                  ["BigPoints", "Rewards"], ["Premium", "Ad-free"],
                ].map(([a, b]) => (
                  <div key={b} className="flex items-center gap-2">
                    <span className="font-black text-white text-base">{a}</span>
                    <span className="text-[11px] uppercase tracking-widest" style={{ color: "#6b7392" }}>{b}</span>
                  </div>
                ))}
              </div>
            </div>

            <div className="relative rounded-3xl overflow-hidden nlv2-glass" style={{ minHeight: 380 }} data-testid="public-hero-image">
              <img src={HERO_IMG} alt="A listener enjoying RadioLife" loading="eager"
                className="absolute inset-0 w-full h-full object-cover" style={{ opacity: 0.92 }} />
              <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(7,10,23,0.15) 0%, rgba(7,10,23,0.35) 55%, rgba(7,10,23,0.85) 100%)" }} />
              <div className="absolute top-5 right-5 text-right">
                <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#e9d5ff" }}>Today's vibe</div>
                <div className="mt-1 text-white text-sm font-medium leading-snug" style={{ maxWidth: 210 }}>Your music. Your mood. A better you.</div>
              </div>
              <div className="absolute bottom-6 left-6">
                <div className="text-3xl sm:text-4xl font-black text-white" style={{ fontFamily: "'Space Grotesk',sans-serif" }}>Music<br />Connects Us</div>
                <div className="mt-3 flex gap-2">
                  {["Live.", "Personalized.", "Rewarded."].map((t) => (
                    <span key={t} className="text-[11px] font-bold px-2.5 py-1 rounded-full nlv2-chip text-white">{t}</span>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── LIVE RIGHT NOW ───────────────────────────────────── */}
        <section className={`${CONTAINER} py-8`}>
          <SectionHeader eyebrow="Live right now" title="Tune in this second" cta="Explore all radio" onCta={ctaTo("explore_all", "/listen")} testid="public-live" />
          <div className="grid grid-flow-col auto-cols-[46%] sm:auto-cols-[30%] lg:grid-flow-row lg:grid-cols-4 gap-4 overflow-x-auto nlv2-scroll pb-2 -mx-1 px-1">
            {stations.slice(0, 8).map((s, i) => (
              <StationCard key={s.id || s.name} station={s} grad={GRADS[i % GRADS.length]}
                onPreview={playPreview} previewing={previewId === (s.id || s.name)} testid={`public-station-${i}`} />
            ))}
          </div>
        </section>

        {/* ─── AI RADIO ─────────────────────────────────────────── */}
        <section className={`${CONTAINER} py-10`}>
          <div className="rounded-3xl overflow-hidden nlv2-glass p-6 sm:p-10 grid grid-cols-1 lg:grid-cols-2 gap-8 items-center relative" data-testid="public-airadio">
            <div className="absolute -top-24 -right-24 w-72 h-72 rounded-full" style={{ background: "radial-gradient(circle, rgba(168,85,247,0.35), transparent 70%)" }} />
            <div className="relative">
              <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#c4b5fd" }}>Radio made for you</div>
              <h2 className="mt-2 text-3xl sm:text-4xl font-black text-white leading-tight">Your station changes<br /><span className="nlv2-grad">with you.</span></h2>
              <p className="mt-4 text-[15px] max-w-md" style={{ color: "#a8b0cc" }}>
                Tell us what you like — or just start listening. RadioLife learns from your listening, skips and preferences and rebuilds your radio in real time.
              </p>
              <button onClick={ctaTo("create_radio", "/radio/create")} data-testid="public-cta-createradio"
                className="nlv2-btn inline-flex items-center gap-2 font-black text-sm px-6 py-3 rounded-full mt-6">
                <Sparkles size={16} /> CREATE MY RADIO
              </button>
            </div>
            <div className="relative grid place-items-center">
              <div className="w-40 h-40 sm:w-52 sm:h-52 rounded-full grid place-items-center relative"
                style={{ background: "conic-gradient(from 0deg, #a855f7, #ec4899, #3b82f6, #a855f7)" }}>
                <div className="w-[86%] h-[86%] rounded-full grid place-items-center" style={{ background: "#0b0f24" }}>
                  <Sparkles size={44} className="text-white" />
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── MORE THAN RADIO ──────────────────────────────────── */}
        <section ref={howRef} className={`${CONTAINER} py-10`}>
          <SectionHeader eyebrow="More than radio" title="One app, your whole vibe" center testid="public-how" />
          <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
            {[
              { Icon: Headphones, t: "Listen", d: "Live + AI Radio", g: GRADS[0] },
              { Icon: Coins, t: "Earn", d: "BigPoints as you engage", g: GRADS[6] },
              { Icon: Gamepad2, t: "Play", d: "Games · Trivia · Predict & Win", g: GRADS[1] },
              { Icon: ShoppingBag, t: "Discover", d: "Shop · Dining · Local deals", g: GRADS[2] },
              { Icon: Users, t: "Social", d: "Listen & play together", g: GRADS[4] },
            ].map(({ Icon, t, d, g }) => (
              <div key={t} className="nlv2-glass nlv2-card-hover rounded-2xl p-5 text-center" data-testid={`public-concept-${t.toLowerCase()}`}>
                <div className="w-12 h-12 rounded-2xl grid place-items-center mx-auto" style={{ background: g }}>
                  <Icon size={22} className="text-white" />
                </div>
                <div className="mt-3 font-black text-white">{t}</div>
                <div className="mt-1 text-[12px]" style={{ color: "#97a3c2" }}>{d}</div>
              </div>
            ))}
          </div>
        </section>

        {/* ─── BIGPOINTS ────────────────────────────────────────── */}
        <section className={`${CONTAINER} py-10`}>
          <div className="rounded-3xl p-6 sm:p-10 grid grid-cols-1 lg:grid-cols-2 gap-8 items-center"
            style={{ background: "linear-gradient(120deg, rgba(245,197,99,0.10), rgba(236,72,153,0.06))", border: "1px solid rgba(245,197,99,0.28)" }}
            data-testid="public-bigpoints">
            <div>
              <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#f5c563" }}>BigPoints</div>
              <h2 className="mt-2 text-3xl sm:text-4xl font-black text-white leading-tight">Listen. Play. <span style={{ color: "#f5c563" }}>Earn.</span></h2>
              <p className="mt-4 text-[15px] max-w-md" style={{ color: "#c9cfe6" }}>
                Earn BigPoints when you listen, play and engage. Spend them across RadioLife rewards, offers and participating businesses.
              </p>
              <button onClick={ctaTo("start_earning", "/wallet")} data-testid="public-cta-earn"
                className="mt-6 inline-flex items-center gap-2 font-black text-sm px-6 py-3 rounded-full"
                style={{ background: "linear-gradient(135deg,#f59e0b,#f5c563)", color: "#1a1305" }}>
                <Coins size={16} /> START EARNING
              </button>
            </div>
            <div className="flex items-center justify-center gap-6">
              <div className="w-28 h-28 rounded-full grid place-items-center shrink-0"
                style={{ background: "radial-gradient(circle at 35% 30%, #ffe9ad, #f59e0b 70%)", boxShadow: "0 12px 40px rgba(245,158,11,0.45)" }}>
                <Coins size={48} style={{ color: "#7a5200" }} />
              </div>
              <div className="nlv2-glass rounded-2xl p-4 min-w-[160px]">
                <div className="text-[10px] font-mono uppercase tracking-widest" style={{ color: "#8b96b8" }}>Example balance</div>
                <div className="text-3xl font-black" style={{ color: "#f5c563" }}>1,250</div>
                <div className="mt-2 h-1.5 rounded-full bg-white/10 overflow-hidden">
                  <div className="h-full" style={{ width: "72%", background: "linear-gradient(90deg,#f59e0b,#f5c563)" }} />
                </div>
                <div className="mt-1.5 text-[11px]" style={{ color: "#97a3c2" }}>Next reward at 1,500</div>
              </div>
            </div>
          </div>
        </section>

        {/* ─── DINING CLUB ──────────────────────────────────────── */}
        <section className={`${CONTAINER} py-10`}>
          <div className="rounded-3xl overflow-hidden nlv2-glass p-6 sm:p-10 grid grid-cols-1 lg:grid-cols-2 gap-8 items-center" data-testid="public-dining">
            <div>
              <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#fca5a5" }}>RadioLife Dining Club</div>
              <h2 className="mt-2 text-3xl sm:text-4xl font-black text-white leading-tight">Spin for your next <span className="nlv2-grad">$9.99 meal.</span></h2>
              <p className="mt-4 text-[15px] max-w-md" style={{ color: "#a8b0cc" }}>
                Choose Veg or Non-Veg, spin (or hit Surprise Me) and RadioLife reveals a participating restaurant. A Premium perk that goes way beyond audio.
              </p>
              <button onClick={ctaTo("dining", "/dining")} data-testid="public-cta-dining"
                className="nlv2-btn inline-flex items-center gap-2 font-black text-sm px-6 py-3 rounded-full mt-6">
                <Utensils size={16} /> DISCOVER DINING CLUB
              </button>
            </div>
            <div className="grid place-items-center relative">
              <div className="w-44 h-44 sm:w-56 sm:h-56 rounded-full relative"
                style={{ background: "conic-gradient(#a855f7 0 45deg,#ec4899 45deg 90deg,#f59e0b 90deg 135deg,#3b82f6 135deg 180deg,#a855f7 180deg 225deg,#ec4899 225deg 270deg,#f59e0b 270deg 315deg,#3b82f6 315deg 360deg)", boxShadow: "0 16px 48px rgba(0,0,0,0.5)" }}>
                <div className="absolute inset-[18%] rounded-full grid place-items-center" style={{ background: "#0b0f24", border: "2px solid rgba(255,255,255,0.12)" }}>
                  <Utensils size={40} className="text-white" />
                </div>
                <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-0 h-0" style={{ borderLeft: "9px solid transparent", borderRight: "9px solid transparent", borderTop: "16px solid #fff" }} />
              </div>
            </div>
          </div>
        </section>

        {/* ─── SHOP / PLAY / SOCIAL previews ────────────────────── */}
        <PreviewSection testid="public-shop" eyebrow="Discover what's around you" title="Shop RadioLife"
          items={[["Local Deals", GRADS[2]], ["Restaurant Pickup", GRADS[0]], ["Services", GRADS[3]], ["Memberships", GRADS[6]], ["Featured Businesses", GRADS[4]]]}
          cta="Explore Shop" onCta={ctaTo("shop", "/shop")} />
        <PreviewSection testid="public-play" eyebrow="Play & win" title="Games, trivia & prizes"
          items={[["Spin & Win", GRADS[6]], ["Trivia", GRADS[1]], ["Predict & Win", GRADS[0]], ["Giveaways", GRADS[2]], ["Sponsored Games", GRADS[4]]]}
          cta="Explore Play" onCta={ctaTo("play", "/play-and-win")} />
        <PreviewSection testid="public-social" eyebrow="Do it together" title="Listen. Play. Go out. Earn — together."
          items={[["Listen Together", GRADS[4]], ["Trivia Teams", GRADS[1]], ["Prediction Groups", GRADS[0]], ["Challenges", GRADS[6]], ["Groups & Events", GRADS[3]]]}
          cta="Join RadioLife" onCta={ctaTo("social", "/community")} />

        {/* ─── PREMIUM ──────────────────────────────────────────── */}
        <section className={`${CONTAINER} py-10`}>
          <div className="rounded-3xl p-6 sm:p-10"
            style={{ background: "linear-gradient(135deg, rgba(20,14,4,0.9), rgba(15,12,30,0.9))", border: "1px solid rgba(245,197,99,0.30)" }}
            data-testid="public-premium">
            <div className="flex items-center gap-2">
              <Crown size={18} style={{ color: "#f5c563" }} />
              <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#f5c563" }}>Premium</div>
            </div>
            <h2 className="mt-2 text-3xl sm:text-4xl font-black text-white">Get more from RadioLife</h2>
            <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="nlv2-glass rounded-2xl p-5">
                <div className="text-sm font-black text-white">Free</div>
                <ul className="mt-3 space-y-2 text-[13px]" style={{ color: "#a8b0cc" }}>
                  {["1 skip per rolling hour", "Live + AI radio", "Earn BigPoints", "Occasional RadioLife ads"].map((t) => (
                    <li key={t} className="flex items-center gap-2"><Check size={14} style={{ color: "#6ea8fe" }} /> {t}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-2xl p-5" style={{ background: "linear-gradient(135deg, rgba(245,197,99,0.12), rgba(236,72,153,0.08))", border: "1px solid rgba(245,197,99,0.45)" }}>
                <div className="text-sm font-black flex items-center gap-1.5" style={{ color: "#f5c563" }}><Star size={14} fill="currentColor" /> Premium</div>
                <ul className="mt-3 space-y-2 text-[13px] text-white">
                  {["6 skips per rolling hour", "Fewer / no RadioLife ads", "Dining Club eligibility", "Premium rewards & perks"].map((t) => (
                    <li key={t} className="flex items-center gap-2"><Check size={14} style={{ color: "#f5c563" }} /> {t}</li>
                  ))}
                </ul>
              </div>
            </div>
            <button onClick={ctaTo("premium", "/premium")} data-testid="public-cta-premium"
              className="mt-6 inline-flex items-center gap-2 font-black text-sm px-6 py-3 rounded-full"
              style={{ background: "linear-gradient(135deg,#f59e0b,#f5c563)", color: "#1a1305" }}>
              <Crown size={16} /> GO PREMIUM
            </button>
          </div>
        </section>

        {/* ─── SPONSORED ────────────────────────────────────────── */}
        <section className={`${CONTAINER} py-6`}>
          <div className="text-[10px] font-mono uppercase tracking-widest mb-2" style={{ color: "#6b7392" }}>Sponsored</div>
          <a href="/for-advertisers" data-testid="public-sponsored"
            className="block rounded-2xl overflow-hidden nlv2-glass nlv2-card-hover p-5 sm:p-6 flex items-center gap-5"
            style={{ background: "linear-gradient(120deg, rgba(59,130,246,0.14), rgba(168,85,247,0.10))" }}>
            <div className="w-14 h-14 rounded-2xl grid place-items-center shrink-0" style={{ background: GRADS[3] }}>
              <Megaphone size={26} className="text-white" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-white font-black">Your brand, on every listen</div>
              <div className="text-[13px]" style={{ color: "#a8b0cc" }}>Audio, display, sponsored games & local commerce — reach engaged listeners on RadioLife.</div>
            </div>
            <ArrowRight size={18} className="text-white shrink-0" />
          </a>
        </section>

        {/* ─── B2B ──────────────────────────────────────────────── */}
        <section className={`${CONTAINER} py-10 grid grid-cols-1 md:grid-cols-2 gap-4`}>
          <B2BCard Icon={Store} title="For Businesses" desc="Reach local customers through RadioLife — offers, pickup and memberships." cta="Join as a business" to="/for-business" testid="public-b2b-business" />
          <B2BCard Icon={Megaphone} title="For Advertisers" desc="Audio, display, sponsored games and local commerce campaigns." cta="Advertise on RadioLife" to="/for-advertisers" testid="public-b2b-advertiser" />
        </section>

        {/* ─── APP CTA ──────────────────────────────────────────── */}
        <section className={`${CONTAINER} py-10`}>
          <div className="rounded-3xl overflow-hidden nlv2-glass p-6 sm:p-10 grid grid-cols-1 lg:grid-cols-2 gap-8 items-center" data-testid="public-appcta">
            <div>
              <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#c4b5fd" }}>Take it with you</div>
              <h2 className="mt-2 text-3xl sm:text-4xl font-black text-white leading-tight">Take RadioLife<br />with you.</h2>
              <p className="mt-4 text-[15px] max-w-md" style={{ color: "#a8b0cc" }}>Your radio. Your rewards. Your local life — anywhere you go.</p>
              <button onClick={ctaTo("app", "/listen")} data-testid="public-cta-app"
                className="nlv2-btn inline-flex items-center gap-2 font-black text-sm px-6 py-3 rounded-full mt-6">
                <Smartphone size={16} /> GET STARTED
              </button>
            </div>
            <div className="grid place-items-center">
              <div className="w-44 rounded-[28px] p-2 nlv2-glass" style={{ border: "1px solid rgba(255,255,255,0.14)" }}>
                <div className="rounded-[22px] overflow-hidden relative" style={{ aspectRatio: "9/19" }}>
                  <img src={HERO_IMG} alt="RadioLife app" className="absolute inset-0 w-full h-full object-cover" />
                  <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(7,10,23,0.1), rgba(7,10,23,0.8))" }} />
                  <div className="absolute bottom-4 left-0 right-0 text-center">
                    <div className="inline-flex items-center gap-1.5 text-white font-black text-sm"><Radio size={14} /> RadioLife</div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {previewStation && (previewId || previewEnded) && (
        <div className="fixed bottom-0 inset-x-0 z-40 nlv2-glass-strong border-t border-white/10" data-testid="public-preview-bar">
          <div className={`${CONTAINER} py-3 flex items-center gap-3`}>
            <button onClick={() => playPreview(previewStation)} data-testid="public-preview-toggle"
              className="nlv2-btn w-10 h-10 rounded-full grid place-items-center shrink-0">
              {previewId ? <Pause size={18} /> : <Play size={18} fill="currentColor" />}
            </button>
            <div className="min-w-0 flex-1">
              <div className="text-white font-bold text-sm truncate">{previewStation.name}</div>
              <div className="text-[11px]" style={{ color: "#8b96b8" }}>{previewId ? "Previewing · 30-second sample" : "Preview ended — sign in to keep listening"}</div>
            </div>
            <button onClick={ctaTo("preview_signup", "/listen")} data-testid="public-preview-signup"
              className="nlv2-btn font-black text-xs px-4 py-2 rounded-full shrink-0">Keep listening</button>
            <button onClick={stopPreview} data-testid="public-preview-close"
              className="w-8 h-8 grid place-items-center shrink-0" style={{ color: "#8b96b8" }}><X size={16} /></button>
          </div>
        </div>
      )}

      <PublicFooter />
    </div>
  );
}

// ─── sub-components ────────────────────────────────────────────────────
function PublicNav({ onSignIn, onStart }) {
  return (
    <header className="nlv2-glass-strong sticky top-0 z-40">
      <div className={`${CONTAINER} h-[64px] flex items-center gap-4`}>
        <Link to="/" className="flex flex-col leading-none shrink-0" data-testid="public-nav-logo">
          <span className="font-black text-lg text-white">Radio<span className="nlv2-grad">Life</span></span>
          <span className="text-[9px] font-mono uppercase tracking-[0.2em] hidden sm:block" style={{ color: "#6b7392" }}>Listen · Earn · Shop · Play · Social</span>
        </Link>
        <nav className="hidden lg:flex items-center gap-1 mx-auto">
          {NAV_LINKS.map((l) => (
            <Link key={l.label} to={l.to} data-testid={`public-nav-${l.label.toLowerCase().replace(/ /g, "-")}`}
              className="px-3 py-2 rounded-full text-sm font-semibold transition-colors hover:text-white" style={{ color: "#97a3c2" }}>
              {l.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-2 sm:gap-3 ml-auto lg:ml-0">
          <button onClick={onSignIn} data-testid="public-nav-signin"
            className="text-sm font-semibold px-3 py-2 rounded-full hover:text-white" style={{ color: "#c9cfe6" }}>
            Sign In
          </button>
          <button onClick={onStart} data-testid="public-nav-getstarted"
            className="nlv2-btn inline-flex items-center gap-1.5 font-black text-xs sm:text-sm px-4 sm:px-5 py-2.5 rounded-full">
            <Play size={14} fill="currentColor" /> START LISTENING
          </button>
        </div>
      </div>
    </header>
  );
}

function SectionHeader({ eyebrow, title, cta, onCta, center, testid }) {
  return (
    <div className={`flex items-end justify-between gap-4 mb-5 ${center ? "flex-col items-center text-center" : ""}`} data-testid={`${testid}-header`}>
      <div>
        <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#c4b5fd" }}>{eyebrow}</div>
        <h2 className="mt-1 text-2xl sm:text-3xl font-black text-white">{title}</h2>
      </div>
      {cta && !center && (
        <button onClick={onCta} className="inline-flex items-center gap-1 text-sm font-bold shrink-0 hover:text-white" style={{ color: "#8b96b8" }}>
          {cta} <ArrowRight size={15} />
        </button>
      )}
    </div>
  );
}

function StationCard({ station, grad, onPreview, previewing, testid }) {
  const art = station.logo_url || station.art || station.favicon || "";
  return (
    <button onClick={() => onPreview(station)} data-testid={testid}
      className="nlv2-glass nlv2-card-hover rounded-2xl p-3 text-left w-full">
      <div className="aspect-square rounded-xl overflow-hidden relative grid place-items-center" style={{ background: grad }}>
        {art
          ? <img src={art} alt={station.name} className="absolute inset-0 w-full h-full object-cover" onError={(e) => { e.currentTarget.style.display = "none"; }} />
          : null}
        <div className="absolute inset-0" style={{ background: "linear-gradient(180deg, rgba(0,0,0,0.04), rgba(0,0,0,0.45))" }} />
        <span className="w-11 h-11 rounded-full grid place-items-center relative nlv2-glass-strong" data-testid={`${testid}-play`}>
          {previewing ? <Pause size={18} className="text-white" /> : <Play size={18} className="text-white" fill="currentColor" />}
        </span>
        <span className="absolute top-2 left-2 text-[9px] font-mono uppercase tracking-widest px-1.5 py-0.5 rounded-full" style={{ background: "rgba(0,0,0,0.5)", color: previewing ? "#86efac" : "#fca5a5" }}>{previewing ? "● Playing" : "● Live"}</span>
      </div>
      <div className="mt-2.5 font-bold text-sm text-white truncate">{station.name}</div>
      <div className="text-[11px] truncate" style={{ color: "#8b96b8" }}>{(station.music_genre || "Radio")}{station.country ? ` · ${station.country}` : ""}</div>
    </button>
  );
}

function PreviewSection({ eyebrow, title, items, cta, onCta, testid }) {
  return (
    <section className={`${CONTAINER} py-8`} data-testid={testid}>
      <SectionHeader eyebrow={eyebrow} title={title} cta={cta} onCta={onCta} testid={testid} />
      <div className="grid grid-flow-col auto-cols-[60%] sm:auto-cols-[38%] lg:grid-flow-row lg:grid-cols-5 gap-4 overflow-x-auto nlv2-scroll pb-2 -mx-1 px-1">
        {items.map(([label, g]) => (
          <div key={label} className="nlv2-glass nlv2-card-hover rounded-2xl overflow-hidden">
            <div className="h-24 grid place-items-center" style={{ background: g }}>
              <span className="text-white/90 font-black text-lg">{label.split(" ").map((w) => w[0]).join("").slice(0, 2)}</span>
            </div>
            <div className="p-3 font-bold text-sm text-white">{label}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

function B2BCard({ Icon, title, desc, cta, to, testid }) {
  return (
    <Link to={to} data-testid={testid} className="nlv2-glass nlv2-card-hover rounded-2xl p-6 flex items-start gap-4">
      <div className="w-11 h-11 rounded-xl grid place-items-center shrink-0" style={{ background: "rgba(255,255,255,0.08)" }}>
        <Icon size={20} className="text-white" />
      </div>
      <div>
        <div className="font-black text-white">{title}</div>
        <div className="mt-1 text-[13px]" style={{ color: "#97a3c2" }}>{desc}</div>
        <div className="mt-3 inline-flex items-center gap-1 text-sm font-bold nlv2-grad">{cta} <ArrowRight size={14} /></div>
      </div>
    </Link>
  );
}

function PublicFooter() {
  const cols = [
    { h: "Listen", links: [["AI Radio", "/listen"], ["Live Radio", "/listen"], ["Podcasts", "/listen"]] },
    { h: "Discover", links: [["Shop", "/shop"], ["Dining Club", "/dining"], ["Play", "/play-and-win"], ["Social", "/community"]] },
    { h: "Business", links: [["For Business", "/for-business"], ["For Advertisers", "/for-advertisers"], ["Pricing", "/pricing"]] },
    { h: "Company", links: [["About", "/about"], ["Terms", "/legal/terms"], ["Privacy", "/legal/privacy"]] },
  ];
  return (
    <footer className="relative z-10 border-t" style={{ borderColor: "rgba(255,255,255,0.08)" }} data-testid="public-footer">
      <div className={`${CONTAINER} py-12 grid grid-cols-2 lg:grid-cols-5 gap-8`}>
        <div className="col-span-2 lg:col-span-1">
          <div className="font-black text-lg text-white">Radio<span className="nlv2-grad">Life</span></div>
          <p className="mt-2 text-[12px]" style={{ color: "#6b7392" }}>A better way to listen — and your listening unlocks more.</p>
        </div>
        {cols.map((c) => (
          <div key={c.h}>
            <div className="text-[11px] font-mono uppercase tracking-widest" style={{ color: "#8b96b8" }}>{c.h}</div>
            <ul className="mt-3 space-y-2">
              {c.links.map(([label, to]) => (
                <li key={label}>
                  <Link to={to} className="text-[13px] hover:text-white transition-colors" style={{ color: "#97a3c2" }}>{label}</Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className={`${CONTAINER} pb-8 text-[11px]`} style={{ color: "#5a6280" }}>© {new Date().getFullYear()} RadioLife. All rights reserved.</div>
    </footer>
  );
}
