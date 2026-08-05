// Phase LAND.v2 (2026-08-02) — Alternative positioning landing page.
//
// Route:    /l/v2
// Aesthetic: RadioLife light-mode (cream/slate, coral accent, rounded
//              cards, generous whitespace)
// Narrative: LISTEN → EARN → REDEEM
//
// Self-contained: does NOT use MarketingShell (which is dark-mode) so
// the light aesthetic here doesn't leak into any other route.  All
// images use SafeImage for guaranteed non-broken rendering.  All CTAs
// deep-link to REAL existing routes in the app.
//
// Guardrails (per task spec):
//   - Do NOT modify `/` landing or any existing homepage components.
//   - Do NOT touch backend, mobile, sidebar.
//   - Do NOT add new dependencies.
//   - Every <img> uses <SafeImage> with a category+text fallback.
import React, { useCallback } from "react";
import { Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import {
  Radio, Sparkles, Gift, MapPin, Trophy, Users,
  Mic2, Headphones, Coffee, Coins, ArrowRight, Play,
  Newspaper, ChevronRight,
} from "lucide-react";
import SafeImage from "@/components/SafeImage";
import mobileHero from "@/assets/landing/mobile_hero.png";
import couponWallet from "@/assets/landing/coupon_wallet.png";
import liveTrivia from "@/assets/landing/live_trivia.png";
import routeAds from "@/assets/landing/route_based_ads.png";


// ─── palette (scoped to this page via inline styles) ────────────
const PALETTE = {
  base:            "#fff8f2",    // warm cream background
  ink:              "#0f172a",   // near-black text
  inkSoft:      "#475569",   // secondary text
  hairline:    "#e2d9cf",     // divider lines
  coral:          "#ff6b57",     // primary accent
  coralDark: "#e5533f",     // primary accent hover
  gold:            "#f4b41a",   // secondary accent
  card:            "#ffffff",     // card surface
  chip:            "#fef2ec",     // chip background
};


// ─── small building blocks ──────────────────────────────────────

function EyebrowChip({ children, tone = "coral" }) {
  const bg = tone === "gold" ? "#fef3c7" : PALETTE.chip;
  const fg = tone === "gold" ? "#b45309" : PALETTE.coralDark;
  return (
    <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-[11px]
                              font-semibold tracking-widest uppercase"
              style={{ background: bg, color: fg }}>
      {children}
    </div>
  );
}


function PrimaryButton({ to, children, testId, external, onClick }) {
  const cls = "inline-flex items-center gap-2 h-12 px-6 rounded-full " +
                          "text-white font-semibold text-sm shadow-lg " +
                          "transition-all duration-200 hover:shadow-xl " +
                          "hover:translate-y-[-1px]";
  const style = { background: PALETTE.coral,
                                    boxShadow: "0 10px 32px -8px rgba(255,107,87,0.55)" };
  if (external || onClick) {
    return (
      <button type="button" onClick={onClick}
                        className={cls} style={style} data-testid={testId}>
        {children}
      </button>
    );
  }
  return (
    <Link to={to} className={cls} style={style} data-testid={testId}>
      {children}
    </Link>
  );
}


function SecondaryButton({ children, onClick, to, testId }) {
  const cls = "inline-flex items-center gap-2 h-12 px-6 rounded-full " +
                          "font-semibold text-sm border-2 transition-all duration-200 " +
                          "hover:bg-black/[0.03]";
  const style = { color: PALETTE.ink, borderColor: PALETTE.ink };
  if (onClick) {
    return (
      <button type="button" onClick={onClick}
                        className={cls} style={style} data-testid={testId}>
        {children}
      </button>
    );
  }
  return (
    <Link to={to} className={cls} style={style} data-testid={testId}>
      {children}
    </Link>
  );
}


// ─── page ────────────────────────────────────────────────────────

export default function LandingV2() {
  const scrollToStory = useCallback(() => {
    const el = document.getElementById("landing-v2-story");
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  return (
    <div data-testid="landing-v2-root"
              style={{ background: PALETTE.base, color: PALETTE.ink,
                              fontFamily: 'system-ui, -apple-system, "Segoe UI", ' +
                                                    '"Helvetica Neue", sans-serif',
                              // Phase LAND.v2.1 (2026-08-03) — belt-and-braces
                              // guard against any absolutely-positioned decorative
                              // element pushing the doc past viewport width on
                              // narrow mobile.
                              overflowX: "hidden" }}
              className="min-h-screen">
      <Helmet>
        <title>RadioLife — Radio that knows you</title>
        {/* Preview experiment — do not index yet. */}
        <meta name="robots" content="noindex, nofollow" />
        <meta name="description" content="Personal AI radio stations tuned by your mood, city, and time of day. Every song earns coins you can spend on real things." />
      </Helmet>

      <PreviewBanner />

      <TopBar />

      <Hero onSeeHow={scrollToStory} />

      <StorySection />

      <UniqueSection />

      <FlowSection />

      <BusinessSection />

      <FinalCTA />

      <FooterMini />

      {/* Fade-in on scroll — pure CSS, no framer. */}
      <style>{`
        @media (prefers-reduced-motion: no-preference) {
          .lv2-reveal { opacity: 0; transform: translateY(20px);
                                      transition: opacity 700ms ease-out,
                                                          transform 700ms cubic-bezier(.2,.7,.2,1); }
          .lv2-reveal.in { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <RevealOnScroll />
    </div>
  );
}


// ─── preview banner ─────────────────────────────────────────────

function PreviewBanner() {
  return (
    <div data-testid="landing-v2-preview-banner"
              style={{ background: PALETTE.ink, color: "#f3ede5" }}
              className="text-xs sm:text-sm py-2 px-4 text-center flex items-center
                              justify-center gap-2 flex-wrap">
      <span className="inline-flex items-center gap-1.5 opacity-95">
        <Sparkles size={12} />
        <b className="font-semibold">Preview:</b>
        alternative positioning
      </span>
      <span className="opacity-40">·</span>
      <Link to="/" data-testid="landing-v2-view-current"
                  className="underline underline-offset-4 hover:text-white
                                  transition-colors">
        view current site
      </Link>
    </div>
  );
}


// ─── topbar (minimal, on-page — not the marketing shell) ──────────

function TopBar() {
  return (
    <header data-testid="landing-v2-topbar"
                    className="sticky top-0 z-30 backdrop-blur-md"
                    style={{ background: `${PALETTE.base}dd`,
                                      borderBottom: `1px solid ${PALETTE.hairline}` }}>
      <div className="max-w-6xl mx-auto px-5 md:px-8 h-16 flex items-center gap-4">
        <Link to="/l/v2"
                  data-testid="landing-v2-logo"
                  className="flex items-center gap-2 font-black text-lg tracking-tight">
          <span className="inline-block w-9 h-9 rounded-full grid place-items-center"
                        style={{ background: PALETTE.coral, color: "#fff" }}>
            <Radio size={18} strokeWidth={2.4} />
          </span>
          <span>RadioLife<span style={{ color: PALETTE.coral }}>.app</span></span>
        </Link>
        <div className="flex-1" />
        <Link to="/login"
                  data-testid="landing-v2-signin"
                  className="hidden sm:inline-block text-sm font-medium
                                  hover:opacity-70 transition-opacity"
                  style={{ color: PALETTE.inkSoft }}>
          Sign in
        </Link>
        <Link to="/radio"
                  data-testid="landing-v2-topbar-cta"
                  className="inline-flex items-center gap-1.5 h-9 px-4 rounded-full
                                  text-white text-xs font-semibold uppercase
                                  tracking-widest transition-all
                                  hover:opacity-90"
                  style={{ background: PALETTE.ink }}>
          Try it <ChevronRight size={14} />
        </Link>
      </div>
    </header>
  );
}


// ─── HERO ───────────────────────────────────────────────────────

function Hero({ onSeeHow }) {
  return (
    <section data-testid="landing-v2-hero"
                    className="relative overflow-hidden">
      {/* Decorative background — abstract gradient blobs */}
      <div aria-hidden className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-24 -left-24 w-96 h-96 rounded-full opacity-40 blur-3xl"
                    style={{ background: `radial-gradient(circle, ${PALETTE.coral}55, transparent 70%)` }} />
        <div className="absolute -bottom-32 -right-16 w-[500px] h-[500px] rounded-full opacity-30 blur-3xl"
                    style={{ background: `radial-gradient(circle, ${PALETTE.gold}66, transparent 70%)` }} />
      </div>

      <div className="relative max-w-6xl mx-auto px-5 md:px-8 py-14 md:py-24
                                grid md:grid-cols-2 gap-10 md:gap-14 items-center">
        <div className="lv2-reveal in">
          <EyebrowChip>AI Radio · Rewards · Local</EyebrowChip>
          <h1 data-testid="landing-v2-hero-h1"
                    className="mt-5 font-black leading-[0.95] tracking-tight"
                    style={{ fontSize: "clamp(44px, 8vw, 84px)",
                                        letterSpacing: "-0.02em" }}>
            Radio that <span style={{ color: PALETTE.coral,
                                                            display: "inline-block",
                                                            fontStyle: "italic" }}>knows you.</span>
          </h1>
          <p data-testid="landing-v2-hero-sub"
                  className="mt-6 max-w-lg"
                  style={{ color: PALETTE.inkSoft,
                                      fontSize: "clamp(16px, 1.5vw, 20px)",
                                      lineHeight: 1.5 }}>
            Personal AI stations tuned by your mood, city, and time —
            plus <b style={{ color: PALETTE.ink }}>50,000+ live terrestrial
            radio stations</b> from around the world.  Every song earns
            coins you can spend on real things.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <PrimaryButton to="/radio"
                                                testId="landing-v2-hero-cta-play">
              <Play size={16} fill="currentColor" />
              Play Radio
              <ArrowRight size={16} />
            </PrimaryButton>
            <SecondaryButton onClick={onSeeHow}
                                                    testId="landing-v2-hero-cta-see-how">
              See how it works
            </SecondaryButton>
          </div>
          {/* Phase LAND.v2.1 — hero differentiator chips: AI + 50k + Global. */}
          <div data-testid="landing-v2-hero-chips"
                      className="mt-6 flex flex-wrap items-center gap-2 max-w-full">
            {[
              { Icon: Sparkles, label: "AI-personal stations" },
              { Icon: Radio,      label: "50,000+ terrestrial stations" },
              { Icon: MapPin,      label: "Global coverage" },
            ].map((c, i) => (
              <div key={c.label}
                          data-testid={`landing-v2-hero-chip-${i}`}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5
                                                    rounded-full text-xs font-semibold whitespace-nowrap"
                          style={{ background: "#ffffff",
                                                border: `1px solid ${PALETTE.hairline}`,
                                                color: PALETTE.ink }}>
                <c.Icon size={13} style={{ color: PALETTE.coral }} strokeWidth={2.4} />
                {c.label}
              </div>
            ))}
          </div>
          <div className="mt-5 flex items-center gap-4"
                        style={{ color: PALETTE.inkSoft, fontSize: 12 }}>
            <div className="flex -space-x-2">
              {[PALETTE.coral, PALETTE.gold, PALETTE.ink].map((c, i) => (
                <div key={i} className="w-7 h-7 rounded-full border-2 border-white"
                                    style={{ background: c }} />
              ))}
            </div>
            <span>Listeners across Dubai · Mumbai · Dallas · Toronto</span>
          </div>
        </div>

        {/* Right-side hero art */}
        <div className="lv2-reveal in relative">
          <div className="relative aspect-[4/5] max-w-[420px] mx-auto rounded-3xl
                                    overflow-hidden shadow-2xl"
                        style={{ boxShadow: "0 40px 80px -20px rgba(15,23,42,0.35)",
                                              border: `1px solid ${PALETTE.hairline}` }}>
            <SafeImage
              src={mobileHero}
              alt="RadioLife app — a phone streaming personal radio"
              fallbackKind="generic"
              fallbackText="RadioLife Radio"
              className="w-full h-full object-cover" />
          </div>
          {/* Floating station-card mockup */}
          <div className="absolute -bottom-6 -left-4 md:-left-8 bg-white rounded-2xl
                                    p-4 shadow-xl w-[220px]"
                        style={{ border: `1px solid ${PALETTE.hairline}` }}>
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl grid place-items-center flex-shrink-0"
                            style={{ background: `linear-gradient(135deg, ${PALETTE.coral} 0%, ${PALETTE.gold} 100%)` }}>
                <Radio size={18} className="text-white" />
              </div>
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-widest"
                              style={{ color: PALETTE.coral }}>Now playing</div>
                <div className="text-sm font-bold truncate">Bollywood Mehfil</div>
                <div className="text-[11px] truncate" style={{ color: PALETTE.inkSoft }}>
                  DJ Aisha · Live in Dubai
                </div>
              </div>
            </div>
            <div className="mt-3 h-1 rounded-full bg-slate-200 overflow-hidden">
              <div className="h-full w-2/3" style={{ background: PALETTE.coral }} />
            </div>
          </div>
          {/* Floating coin chip */}
          <div className="absolute -top-3 -right-3 md:-right-6 bg-white rounded-full
                                    px-4 py-2 shadow-lg flex items-center gap-2"
                        style={{ border: `1px solid ${PALETTE.hairline}` }}>
            <Coins size={16} style={{ color: PALETTE.gold }} />
            <span className="text-xs font-bold">+ 24 BigCoins</span>
          </div>
        </div>
      </div>
    </section>
  );
}


// ─── SECTION 2 — the 3-layer story ─────────────────────────────

const STORY = [
  { id: "listen",  Icon: Radio,      label: "LISTEN",
      title: "Radio that reads your mind.",
      body:    "AI-personal stations, live hosts, your language. No song " +
                      "picking — the radio picks you.",
      art:      liveTrivia,
      tint:      PALETTE.coral },
  { id: "earn",      Icon: Sparkles, label: "EARN",
      title: "Every song earns you something.",
      body:    "Play trivia, spin the wheel, predict along — collect BigCoins " +
                      "just by listening.",
      art:      null,
      tint:      PALETTE.gold },
  { id: "redeem", Icon: Gift,          label: "REDEEM",
      title: "Trade coins for the good stuff.",
      body:    "Restaurants, movies, concerts, cafés near you. Discover your " +
                      "city while you listen.",
      art:      couponWallet,
      tint:      "#22c55e" },
];


function StorySection() {
  return (
    <section id="landing-v2-story"
                    data-testid="landing-v2-story"
                    className="relative py-20 md:py-28"
                    style={{ borderTop: `1px solid ${PALETTE.hairline}` }}>
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <div className="text-center max-w-2xl mx-auto lv2-reveal">
          <EyebrowChip>The loop</EyebrowChip>
          <h2 className="mt-5 font-black tracking-tight"
                    style={{ fontSize: "clamp(32px, 5vw, 52px)",
                                        letterSpacing: "-0.02em" }}>
            Listen → Earn → Redeem
          </h2>
          <p className="mt-4" style={{ color: PALETTE.inkSoft, fontSize: 17 }}>
            One simple loop. Every layer feeds the next. Every play matters.
          </p>
        </div>

        <div className="mt-14 grid md:grid-cols-3 gap-6 lg:gap-8 relative">
          {STORY.map((s, i) => (
            <StoryCard key={s.id} spec={s} index={i} />
          ))}
        </div>
      </div>
    </section>
  );
}


function StoryCard({ spec, index }) {
  const { Icon } = spec;
  return (
    <div className="lv2-reveal relative flex flex-col rounded-3xl p-6 md:p-8"
              data-testid={`landing-v2-story-card-${spec.id}`}
              style={{ background: PALETTE.card,
                                  border: `1px solid ${PALETTE.hairline}`,
                                  transitionDelay: `${index * 90}ms` }}>
      {/* Flow arrow (desktop only, between cards) */}
      {index < STORY.length - 1 && (
        <div className="hidden md:flex absolute top-1/2 -right-4 lg:-right-5
                                    -translate-y-1/2 z-10 w-8 h-8 rounded-full items-center
                                    justify-center bg-white shadow"
                    style={{ border: `1px solid ${PALETTE.hairline}` }}
                    aria-hidden>
          <ArrowRight size={16} style={{ color: PALETTE.inkSoft }} />
        </div>
      )}
      <div className="w-14 h-14 rounded-2xl grid place-items-center mb-5"
                    style={{ background: `${spec.tint}22`, color: spec.tint }}>
        <Icon size={24} strokeWidth={2.2} />
      </div>
      <div className="text-[11px] font-bold uppercase tracking-widest mb-2"
                    style={{ color: spec.tint }}>
        {spec.label}
      </div>
      <h3 className="font-black tracking-tight leading-tight"
                    style={{ fontSize: "clamp(22px, 2.4vw, 28px)",
                                          letterSpacing: "-0.01em" }}>
        {spec.title}
      </h3>
      <p className="mt-3 flex-1" style={{ color: PALETTE.inkSoft, lineHeight: 1.55 }}>
        {spec.body}
      </p>
      {spec.art && (
        <div className="mt-5 aspect-video rounded-xl overflow-hidden"
                    style={{ background: PALETTE.chip }}>
          <SafeImage src={spec.art}
                                fallbackKind="generic"
                                fallbackText={spec.title}
                                alt={spec.title}
                                className="w-full h-full object-cover" />
        </div>
      )}
    </div>
  );
}


// ─── SECTION 3 — what makes it unique ────────────────────────

const UNIQUE = [
  // Phase LAND.v2.1 — lead with the terrestrial catalog (real DB
  // count 58,558 rows spanning 239 countries) — this is the strongest
  // differentiator vs. any AI-only competitor.
  { Icon: Radio,          title: "50,000+ terrestrial stations, worldwide",
      body: "Live FM, AM, and internet radio from Mumbai to Dallas to " +
                  "Dubai — all searchable, all in one player." },
  { Icon: Mic2,          title: "AI Radio Jockeys that talk to you",
      body: "Personalities in your language, bilingual, contextual." },
  { Icon: Trophy,       title: "Trivia, games, and predictions",
      body: "Play along without leaving the stream." },
  { Icon: MapPin,       title: "Location-aware offers",
      body: "Deals from restaurants near your route or neighborhood." },
  { Icon: Users,        title: "Social listening lobbies",
      body: "Tune in with friends, chat live, react to songs together." },
  { Icon: Gift,          title: "Your Social Passport",
      body: "Badges, stamps, and tiers as you explore your city." },
];


function UniqueSection() {
  return (
    <section data-testid="landing-v2-unique"
                    className="py-20 md:py-28"
                    style={{ background: "#fff",
                                      borderTop: `1px solid ${PALETTE.hairline}`,
                                      borderBottom: `1px solid ${PALETTE.hairline}` }}>
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <div className="text-center max-w-2xl mx-auto lv2-reveal">
          <EyebrowChip tone="gold">What makes it unique</EyebrowChip>
          <h2 className="mt-5 font-black tracking-tight"
                    style={{ fontSize: "clamp(30px, 4.5vw, 48px)",
                                        letterSpacing: "-0.02em" }}>
            Not another music app.
          </h2>
          <p className="mt-4" style={{ color: PALETTE.inkSoft, fontSize: 17 }}>
            A radio, a game, a city guide, and a rewards wallet — one stream.
          </p>
        </div>
        <div className="mt-14 grid sm:grid-cols-2 lg:grid-cols-3 gap-5 lg:gap-6">
          {UNIQUE.map((u, i) => (
            <div key={u.title}
                        className="lv2-reveal rounded-2xl p-6 transition-all
                                        duration-200 hover:shadow-md hover:translate-y-[-2px]"
                        style={{ background: PALETTE.base,
                                              border: `1px solid ${PALETTE.hairline}`,
                                              transitionDelay: `${(i % 3) * 60}ms` }}>
              <div className="w-11 h-11 rounded-xl grid place-items-center mb-4"
                            style={{ background: `${PALETTE.coral}18`, color: PALETTE.coral }}>
                <u.Icon size={20} strokeWidth={2.2} />
              </div>
              <div className="font-bold text-lg leading-snug tracking-tight">
                {u.title}
              </div>
              <p className="mt-2 text-sm" style={{ color: PALETTE.inkSoft, lineHeight: 1.55 }}>
                {u.body}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}


// ─── SECTION 4 — how rewards work (horizontal flow) ─────────

const FLOW = [
  { Icon: Headphones, title: "Listen",    caption: "Tune in" },
  { Icon: Trophy,        title: "Play",      caption: "Trivia, spin, predict" },
  { Icon: Coins,          title: "Earn",      caption: "BigCoins pile up" },
  { Icon: Coffee,        title: "Redeem",  caption: "At real restaurants, cinemas, cafés" },
];


function FlowSection() {
  return (
    <section data-testid="landing-v2-flow"
                    className="py-20 md:py-28">
      <div className="max-w-6xl mx-auto px-5 md:px-8">
        <div className="text-center max-w-2xl mx-auto lv2-reveal">
          <EyebrowChip>How rewards work</EyebrowChip>
          <h2 className="mt-5 font-black tracking-tight"
                    style={{ fontSize: "clamp(30px, 4.5vw, 48px)",
                                        letterSpacing: "-0.02em" }}>
            Four steps.  That&apos;s the whole thing.
          </h2>
        </div>
        <div className="mt-14 grid grid-cols-2 md:grid-cols-4 gap-4 md:gap-3">
          {FLOW.map((f, i) => (
            <div key={f.title} className="lv2-reveal relative"
                        style={{ transitionDelay: `${i * 80}ms` }}
                        data-testid={`landing-v2-flow-step-${f.title.toLowerCase()}`}>
              {/* Arrow between steps (desktop only) */}
              {i < FLOW.length - 1 && (
                <div className="hidden md:block absolute top-6 -right-1
                                            lg:right-0 z-10"
                            aria-hidden>
                  <ChevronRight size={22} style={{ color: PALETTE.hairline }} />
                </div>
              )}
              <div className="flex flex-col items-center text-center">
                <div className="w-14 h-14 rounded-2xl grid place-items-center"
                              style={{ background: `${PALETTE.coral}18`,
                                                    color: PALETTE.coral }}>
                  <f.Icon size={24} strokeWidth={2.2} />
                </div>
                <div className="mt-3 text-xs font-bold uppercase tracking-widest"
                              style={{ color: PALETTE.coral }}>
                  Step {i + 1}
                </div>
                <div className="mt-1 font-black text-xl tracking-tight">
                  {f.title}
                </div>
                <div className="mt-1 text-sm" style={{ color: PALETTE.inkSoft }}>
                  {f.caption}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}


// ─── SECTION 5 — for businesses ─────────────────────────────

function BusinessSection() {
  return (
    <section data-testid="landing-v2-business"
                    className="py-20 md:py-28 relative overflow-hidden"
                    style={{ background: PALETTE.ink, color: "#f3ede5" }}>
      <div aria-hidden className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-32 right-0 w-[520px] h-[520px] rounded-full opacity-25 blur-3xl"
                    style={{ background: `radial-gradient(circle, ${PALETTE.coral}, transparent 70%)` }} />
      </div>
      <div className="relative max-w-6xl mx-auto px-5 md:px-8
                                grid md:grid-cols-5 gap-10 items-center">
        <div className="md:col-span-3 lv2-reveal">
          <EyebrowChip tone="gold">For businesses</EyebrowChip>
          <h2 className="mt-5 font-black tracking-tight"
                    style={{ fontSize: "clamp(34px, 5.5vw, 60px)",
                                        letterSpacing: "-0.02em", color: "#fff" }}>
            Turn listeners into <span style={{ color: PALETTE.coral }}>customers.</span>
          </h2>
          <p className="mt-5 max-w-lg" style={{ opacity: 0.75, fontSize: 18, lineHeight: 1.5 }}>
            Your ad plays.  They earn a coupon.  They walk in.  <b style={{ color: "#fff" }}>
            That&apos;s</b> when you pay.
          </p>
          <div className="mt-8 grid sm:grid-cols-3 gap-4">
            {[
              { Icon: MapPin,  title: "Local reach",
                  body: "Target by city, route, weather, time of day." },
              { Icon: Sparkles, title: "Warm intent",
                  body: "They opted in by earning the coupon." },
              { Icon: Coins,      title: "Pay-per-visit",
                  body: "Attribution to real redemptions, not clicks." },
            ].map((b, i) => (
              <div key={b.title}
                          className="rounded-2xl p-4"
                          style={{ background: "rgba(255,255,255,0.05)",
                                                border: "1px solid rgba(255,255,255,0.08)" }}>
                <div className="w-9 h-9 rounded-xl grid place-items-center mb-3"
                              style={{ background: `${PALETTE.coral}22`, color: PALETTE.coral }}>
                  <b.Icon size={16} strokeWidth={2.4} />
                </div>
                <div className="font-bold" style={{ color: "#fff" }}>{b.title}</div>
                <div className="mt-1 text-xs" style={{ opacity: 0.7, lineHeight: 1.5 }}>
                  {b.body}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-8">
            <PrimaryButton to="/business/register"
                                                testId="landing-v2-business-cta">
              List your business
              <ArrowRight size={16} />
            </PrimaryButton>
          </div>
        </div>

        <div className="md:col-span-2 lv2-reveal">
          <div className="relative aspect-square max-w-[380px] mx-auto rounded-3xl
                                    overflow-hidden">
            <SafeImage src={routeAds}
                                    alt="Location-aware offers on a city map"
                                    fallbackKind="business"
                                    fallbackText="Local reach"
                                    className="w-full h-full object-cover" />
          </div>
        </div>
      </div>
    </section>
  );
}


// ─── SECTION 6 — final CTA ──────────────────────────────────

function FinalCTA() {
  return (
    <section data-testid="landing-v2-final"
                    className="py-20 md:py-28 relative overflow-hidden"
                    style={{ background: PALETTE.base }}>
      <div aria-hidden className="absolute inset-0 pointer-events-none">
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 w-[600px] h-[600px]
                                  rounded-full opacity-30 blur-3xl"
                    style={{ background: `radial-gradient(circle, ${PALETTE.coral}88, transparent 70%)` }} />
      </div>
      <div className="relative max-w-4xl mx-auto px-5 md:px-8 text-center lv2-reveal">
        {/* Phase LAND.v2.1 — stat strip grounded in real DB counts:
                58,558 stations / 14 channels / 239 countries. */}
        <div data-testid="landing-v2-stat-strip"
                    className="mb-10 md:mb-14 grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-6
                                    max-w-3xl mx-auto">
          {[
            { n: "50,000+", label: "STATIONS",       tid: "stations" },
            { n: "14",             label: "AI CHANNELS", tid: "channels" },
            { n: "200+",       label: "COUNTRIES",   tid: "countries" },
            { n: "∞",              label: "REWARDS",       tid: "rewards" },
          ].map((s) => (
            <div key={s.tid}
                        data-testid={`landing-v2-stat-${s.tid}`}
                        className="rounded-2xl px-3 py-4 md:py-5"
                        style={{ background: "#fff",
                                              border: `1px solid ${PALETTE.hairline}` }}>
              <div className="font-black tracking-tight leading-none"
                            style={{ fontSize: "clamp(28px, 4.2vw, 44px)",
                                                  color: PALETTE.ink,
                                                  letterSpacing: "-0.02em" }}>
                {s.n}
              </div>
              <div className="mt-2 text-[10px] md:text-xs font-bold uppercase
                                            tracking-widest"
                            style={{ color: PALETTE.inkSoft }}>
                {s.label}
              </div>
            </div>
          ))}
        </div>
        <h2 className="font-black tracking-tight"
                    style={{ fontSize: "clamp(40px, 6.5vw, 76px)",
                                        letterSpacing: "-0.03em" }}>
          Ready to <span style={{ color: PALETTE.coral, fontStyle: "italic" }}>
          listen?</span>
        </h2>
        <p className="mt-5" style={{ color: PALETTE.inkSoft, fontSize: 18 }}>
          One tap and you&apos;re on-air.  Bring your headphones.
        </p>
        <div className="mt-10 flex flex-wrap justify-center gap-3">
          <PrimaryButton to="/radio"
                                            testId="landing-v2-final-cta-play">
            <Play size={16} fill="currentColor" />
            Play Radio
            <ArrowRight size={16} />
          </PrimaryButton>
          <SecondaryButton to="/business/register"
                                                testId="landing-v2-final-cta-business">
            List a business
            <ArrowRight size={16} />
          </SecondaryButton>
        </div>
      </div>
    </section>
  );
}


// ─── minimal footer ─────────────────────────────────────────

function FooterMini() {
  return (
    <footer data-testid="landing-v2-footer"
                    className="py-10 md:py-14"
                    style={{ borderTop: `1px solid ${PALETTE.hairline}`,
                                        background: "#fff" }}>
      <div className="max-w-6xl mx-auto px-5 md:px-8 flex flex-wrap
                                gap-6 items-center justify-between">
        <div className="flex items-center gap-2 font-black">
          <span className="inline-block w-7 h-7 rounded-full grid place-items-center"
                        style={{ background: PALETTE.coral, color: "#fff" }}>
            <Radio size={14} strokeWidth={2.5} />
          </span>
          RadioLife<span style={{ color: PALETTE.coral }}>.app</span>
        </div>
        <div className="flex flex-wrap gap-5 text-sm"
                    style={{ color: PALETTE.inkSoft }}>
          <Link to="/legal/privacy" className="hover:opacity-70">Privacy</Link>
          <Link to="/legal/terms" className="hover:opacity-70">Terms</Link>
          <Link to="/about" className="hover:opacity-70">About</Link>
          <Link to="/for-business" className="hover:opacity-70">For business</Link>
          <Link to="/" className="hover:opacity-70"
                        data-testid="landing-v2-footer-view-current">
            View current site
          </Link>
        </div>
        <div className="text-xs" style={{ color: PALETTE.inkSoft }}>
          © {new Date().getFullYear()} RadioLife.app · part of{" "}
          <a href="https://funasianetwork.com" target="_blank" rel="noreferrer"
             data-testid="funasia-footer-link"
             className="underline hover:opacity-70" style={{ color: PALETTE.coral }}>
            funasianetwork.com
          </a>
        </div>
      </div>
    </footer>
  );
}


// ─── reveal-on-scroll (pure IntersectionObserver, no deps) ─

function RevealOnScroll() {
  React.useEffect(() => {
    if (typeof window === "undefined" || !("IntersectionObserver" in window)) return;
    const els = document.querySelectorAll(".lv2-reveal");
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -60px 0px" });
    els.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, []);
  return null;
}
