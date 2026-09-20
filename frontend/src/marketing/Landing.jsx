// Phase 15c — public landing page. Rendered at `/` for logged-out users.
// Phase B — hero "Live in <cities>" strip is now driven by
// useCityTags() instead of a hardcoded "Dubai · Mumbai · Dallas".
// Phase Π+3 (2026-07-24) — for-business / for-advertisers feature tiles
// on the landing now render the AI-generated marketing hero images.
// AppDownload section renders `mobile_hero.png` as its background.
import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Radio, Gamepad2, Wallet, Brain, MapPin, Sparkles,
  Megaphone, Building2, ChevronRight, Star,
} from "lucide-react";
import MarketingShell, { SEO } from "./MarketingShell";
import { useCityTags } from "@/hooks/useCityTags";
import { useMarketingAssets } from "@/hooks/useMarketingAssets";
// Phase FUN.1-v2 — flagship strip in the marketing hero.
import FlagshipStrip from "@/components/FlagshipStrip";

export default function Landing() {
  const { urlFor } = useMarketingAssets();
  return (
    <MarketingShell>
      <SEO title="AI Radio · Live Trivia · Real Rewards"
              description="FUUSIC is a non-interactive personalized radio with an AI RJ, live trivia in your neighborhood, BigPoints rewards, and a wallet of real coupons." />
      <Hero />
      {/* Phase FUN.1-v2 — Flagship strip on the landing hero for cross-promo. */}
      <section className="max-w-6xl mx-auto px-4 sm:px-6 py-8"
                        data-testid="landing-flagship-section">
        <FlagshipStrip
          title="Featured on our flagship stations"
          testId="landing-flagship-strip"
          limit={6} />
      </section>
      <StationStrip />
      <ForListeners />
      <ForBusinessCTA urlFor={urlFor} />
      <ForAdvertisersCTA urlFor={urlFor} />
      <AppDownload urlFor={urlFor} />
      <Testimonials />
    </MarketingShell>
  );
}

function Hero() {
  // Phase B — hero "Live in <city>, <city>, <city>" strip is now driven
  // by useCityTags() instead of the hardcoded "Dubai · Mumbai · Dallas".
  // Bug B1 fix — render the API's `tag.label` per pill rather than
  // hardcoding a single "Live in" prefix for the whole string. The API
  // is authoritative about each tag's relationship (Home/Visiting/Live/
  // Live in for the heat fill), so we surface that verbatim and preserve
  // the API-supplied order without any client-side sort.
  const { tags, isLoading } = useCityTags();
  return (
    <section className="relative overflow-hidden" data-testid="landing-hero">
      <motion.div
        aria-hidden="true"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 1.2 }}
        className="absolute inset-0 pointer-events-none"
      >
        <div className="absolute top-[-12rem] left-[-8rem] w-[42rem] h-[42rem]
                                rounded-full opacity-30"
                  style={{ background: "radial-gradient(closest-side, var(--accent-electric), transparent)" }} />
        <div className="absolute top-[10rem] right-[-10rem] w-[36rem] h-[36rem]
                                rounded-full opacity-25"
                  style={{ background: "radial-gradient(closest-side, var(--accent-magenta), transparent)" }} />
        <div className="absolute bottom-[-10rem] left-[20%] w-[28rem] h-[28rem]
                                rounded-full opacity-20"
                  style={{ background: "radial-gradient(closest-side, var(--accent-gold), transparent)" }} />
      </motion.div>
      <div className="relative max-w-7xl mx-auto px-6 lg:px-10 py-20 lg:py-32">
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="max-w-3xl space-y-6"
        >
          <div className="text-[10px] font-mono uppercase tracking-widest
                                text-text-secondary flex items-center gap-2 flex-wrap"
                    data-testid="landing-live-strip">
            <span className="w-1.5 h-1.5 rounded-full bg-accent-live live-dot" />
            {isLoading || tags.length === 0
              ? <span>Live everywhere</span>
              : tags.map((t, i) => (
                  <React.Fragment key={`${t.source}-${t.city}`}>
                    {i > 0 && <span className="text-text-secondary/40">·</span>}
                    <span data-testid={`landing-live-tag-${t.source}`}>
                      <span className="text-text-secondary/70">{t.label}</span>
                      {" "}
                      <span className="text-white">{t.city}</span>
                    </span>
                  </React.Fragment>
                ))}
          </div>
          <h1 className="font-display font-extrabold text-5xl sm:text-6xl
                                lg:text-7xl xl:text-8xl leading-[0.95]
                                tracking-display-tight">
            Radio that <span className="text-accent-electric">knows</span>
            <br /> what you want
            <br /> before <span className="text-accent-magenta">you do.</span>
          </h1>
          <p className="text-text-secondary text-lg max-w-xl">
            Press play and an AI host builds a station around you — drawing from
            50,000+ live stations, podcasts and news. A wallet that pays you to
            listen, local deals and live trivia come along for the ride.
          </p>
          <div className="flex flex-wrap gap-3 pt-2">
            <Link to="/login" data-testid="landing-cta-signup"
                      className="px-6 h-12 inline-flex items-center gap-2
                                      rounded-full bg-accent-electric text-bg-base
                                      font-mono text-xs uppercase tracking-widest
                                      hover:bg-white transition-colors duration-150">
              Start listening free <ChevronRight size={14} />
            </Link>
            <Link to="/login?demo=1" data-testid="landing-cta-demo"
                      className="px-6 h-12 inline-flex items-center gap-2
                                      rounded-full border border-white/[0.12]
                                      text-white font-mono text-xs uppercase
                                      tracking-widest hover:bg-white/5
                                      transition-colors duration-150">
              <Sparkles size={14} /> Try the demo
            </Link>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

// P1 (Slice 3) — consumer-first feature section. Leads with the listening
// proposition (AI host + free radio) and surfaces Play & Earn as the
// contextual next step, BEFORE the B2B / advertiser sections below.
function ForListeners() {
  const ITEMS = [
    { icon: Radio, title: "An AI host who knows you",
      body: "A live radio host that reads the room — your mood, your city, your commute — and never plays the same hour twice." },
    { icon: Gamepad2, title: "Play & win real coupons",
      body: "Spin, scratch and quiz your way to discounts from brands near you. Every play is a shot at a real reward." },
    { icon: Wallet, title: "A wallet that pays you to listen",
      body: "Earn BigPoints just for tuning in, then stack coupons and perks in a wallet that's always in your pocket." },
  ];
  return (
    <section data-testid="landing-for-listeners"
                  className="relative py-20 border-t border-white/[0.06]">
      <div className="max-w-7xl mx-auto px-6 lg:px-10">
        <SectionEyebrow>For listeners</SectionEyebrow>
        <SectionTitle>Free to listen. Built to reward you.</SectionTitle>
        <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-5">
          {ITEMS.map(({ icon: Icon, title, body }) => (
            <div key={title}
                      data-testid={`listener-card-${title.toLowerCase().replace(/\s+/g, "-").slice(0, 20)}`}
                      className="rounded-token-card border border-white/[0.06]
                                      bg-bg-elevated p-6">
              <div className="w-10 h-10 rounded-token-md grid place-items-center
                                      bg-accent-electric/25 text-accent-electric">
                <Icon size={18} />
              </div>
              <div className="mt-4 font-display font-bold text-lg
                                      tracking-display-tight">{title}</div>
              <div className="mt-1 text-sm text-text-secondary">{body}</div>
            </div>
          ))}
        </div>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/login" data-testid="listener-cta-listen"
                    className="px-6 h-12 inline-flex items-center gap-2
                                    rounded-full bg-accent-electric text-bg-base
                                    font-mono text-xs uppercase tracking-widest
                                    hover:bg-white transition-colors duration-150">
            <Radio size={14} /> Start listening free
          </Link>
          <Link to="/login?demo=1" data-testid="listener-cta-play"
                    className="px-6 h-12 inline-flex items-center gap-2
                                    rounded-full border border-white/[0.12] text-white
                                    font-mono text-xs uppercase tracking-widest
                                    hover:bg-white/5 transition-colors duration-150">
            <Gamepad2 size={14} /> Play &amp; earn
          </Link>
        </div>
      </div>
    </section>
  );
}


function StationStrip() {
  // Phase 42-D1 — wire the Phase-C AI-generated channel artwork instead of
  // gradient placeholders.  Each entry maps to a real channel slug whose
  // .webp poster lives under /api/static/channel_thumbnails/<slug>.webp
  // (idempotent backfill at boot).
  const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
  const STATIONS = [
    { name: "Bollywood Mehfil", dj: "Aanya",       slug: "bollywood_mehfil" },
    { name: "Lounge UAE",         dj: "DJ Ravi",     slug: "vip_lounge" },
    { name: "Party Mix",            dj: "DJ Charlie", slug: "party_dubai" },
    { name: "Late Night Sufi",    dj: "Karan",       slug: "late_night_drive" },
  ];
  return (
    <section className="relative py-16 border-t border-white/[0.06]"
                  data-testid="landing-stations">
      <div className="max-w-7xl mx-auto px-6 lg:px-10">
        <SectionEyebrow>Stations</SectionEyebrow>
        <SectionTitle>Tune in. Or let the AI host pick.</SectionTitle>
        <div className="mt-10 grid grid-cols-2 lg:grid-cols-4 gap-5">
          {STATIONS.map((s) => (
            <motion.div
              key={s.name} whileHover={{ y: -4 }}
              transition={{ duration: 0.18 }}
              data-testid={`landing-station-${s.slug}`}
              className="group relative rounded-token-card overflow-hidden
                              bg-bg-elevated border border-white/[0.06]"
            >
              <div className="aspect-square relative bg-bg-elevated">
                <img
                  src={`${BACKEND_URL}/api/static/channel_thumbnails/${s.slug}.webp`}
                  alt={s.name}
                  loading="lazy"
                  className="w-full h-full object-cover"
                  onError={(e) => {
                    // Neutral SVG placeholder when artwork missing.  No gradient.
                    e.currentTarget.style.display = "none";
                    e.currentTarget.parentNode.classList.add(
                      "flex", "items-center", "justify-center");
                    const ph = document.createElement("div");
                    ph.className = "text-text-secondary text-4xl";
                    ph.textContent = "♪";
                    e.currentTarget.parentNode.appendChild(ph);
                  }}
                />
              </div>
              <div className="p-4">
                <div className="font-display font-bold tracking-display-tight">
                  {s.name}
                </div>
                <div className="text-xs text-text-secondary mt-1">
                  with {s.dj}
                </div>
              </div>
              <div className="absolute inset-0 grid place-items-center
                                    bg-bg-base/70 opacity-0 group-hover:opacity-100
                                    transition-opacity duration-200">
                <Link to="/login"
                          className="px-4 h-10 inline-flex items-center rounded-full
                                          bg-accent-electric text-bg-base font-mono
                                          text-[11px] uppercase tracking-widest"
                          title="Sign up to listen">
                  Sign up to listen
                </Link>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function ForBusinessCTA({ urlFor }) {
  return (
    <PartnerSection
      eyebrow="For business"
      title="Bring the neighborhood through your door."
      testId="landing-for-business"
      cta={{ to: "/for-business", label: "Open a business account" }}
      items={[
        { icon: Brain,      title: "Live trivia",           imageKey: "live_trivia",
              body: "Host a quiz night that fills the room and the till." },
        { icon: Gamepad2, title: "Game campaigns",   imageKey: "game_campaigns",
              body: "Spin-the-wheel, lucky draws, lyric hunts — branded, measured." },
        { icon: Wallet,      title: "Coupon wallet",      imageKey: "coupon_wallet",
              body: "Drop offers into BigPoints wallets near you. Redeem in-store via QR." },
      ]}
      urlFor={urlFor}
    />
  );
}

function ForAdvertisersCTA({ urlFor }) {
  return (
    <PartnerSection
      eyebrow="For advertisers"
      title="Audio that buys back its airtime."
      testId="landing-for-advertisers"
      cta={{ to: "/for-advertisers", label: "Become an advertiser" }}
      items={[
        { icon: Radio,        title: "Audio ads",                  imageKey: "audio_ads",
              body: "AI host reads your spot, in-character, with the song before it." },
        { icon: Gamepad2,  title: "Sponsored games",       imageKey: "sponsored_games",
              body: "Branded games unlock during your daypart. Track engagement live." },
        { icon: MapPin,      title: "Route-based ads",         imageKey: "route_based_ads",
              body: "Hit listeners on their commute, near your nearest store." },
      ]}
      urlFor={urlFor}
    />
  );
}

function PartnerSection({ eyebrow, title, items, cta, testId, urlFor }) {
  const resolve = urlFor || (() => "");
  return (
    <section data-testid={testId}
                  className="relative py-20 border-t border-white/[0.06]">
      <div className="max-w-7xl mx-auto px-6 lg:px-10">
        <SectionEyebrow>{eyebrow}</SectionEyebrow>
        <SectionTitle>{title}</SectionTitle>
        <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-5">
          {items.map(({ icon: Icon, title: t, body, imageKey }) => {
            const imgUrl = imageKey ? resolve(imageKey) : "";
            return (
              <div key={t}
                        data-testid={`partner-card-${(imageKey || t)
                                                .toLowerCase().replace(/\s+/g, "-")}`}
                        className="relative overflow-hidden rounded-token-card
                                        border border-white/[0.06] bg-bg-elevated
                                        min-h-[240px] flex flex-col justify-end">
                {imgUrl ? (
                  <>
                    <img
                      src={imgUrl}
                      alt={t}
                      loading="lazy"
                      onError={(e) => { e.currentTarget.style.display = "none"; }}
                      className="absolute inset-0 w-full h-full object-cover
                                          opacity-90"
                      data-testid={`partner-card-img-${imageKey}`} />
                    <div className="absolute inset-0
                                                bg-gradient-to-t
                                                from-bg-elevated via-bg-elevated/70
                                                to-bg-elevated/10" />
                  </>
                ) : null}
                <div className="relative p-6">
                  <div className="w-10 h-10 rounded-token-md grid place-items-center
                                          bg-accent-electric/25 text-accent-electric
                                          backdrop-blur-sm">
                    <Icon size={18} />
                  </div>
                  <div className="mt-4 font-display font-bold text-lg
                                          tracking-display-tight">{t}</div>
                  <div className="mt-1 text-sm text-text-secondary">{body}</div>
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-8">
          <Link to={cta.to}
                    className="px-6 h-12 inline-flex items-center gap-2
                                    rounded-full bg-white text-bg-base font-mono
                                    text-xs uppercase tracking-widest
                                    hover:bg-accent-electric transition-colors
                                    duration-150">
            {cta.label} <ChevronRight size={14} />
          </Link>
        </div>
      </div>
    </section>
  );
}

function AppDownload({ urlFor }) {
  const mobileHero = (urlFor && urlFor("mobile_hero")) || "";
  return (
    <section className="relative py-20 border-t border-white/[0.06]"
                  data-testid="landing-app-download">
      <div className="max-w-7xl mx-auto px-6 lg:px-10
                            grid grid-cols-1 lg:grid-cols-2 gap-10 items-center">
        <div>
          <SectionEyebrow>Mobile</SectionEyebrow>
          <SectionTitle>One tap, one stream, one home.</SectionTitle>
          <p className="mt-4 text-text-secondary max-w-md">
            The FUUSIC app picks up where the web left off. Tap into your
            station while you walk, drive, or wait in line.
          </p>
          <div className="mt-6 flex flex-wrap gap-3">
            <a href="#" data-testid="landing-appstore"
                  className="h-12 px-5 inline-flex items-center gap-2 rounded-full
                                  bg-white text-bg-base font-mono text-xs uppercase
                                  tracking-widest">
              <span aria-hidden="true">⌘</span> App Store
            </a>
            <a href="#" data-testid="landing-playstore"
                  className="h-12 px-5 inline-flex items-center gap-2 rounded-full
                                  border border-white/[0.12] text-white font-mono
                                  text-xs uppercase tracking-widest">
              <Megaphone size={14} /> Google Play
            </a>
          </div>
        </div>
        <div className="relative h-80 rounded-token-card overflow-hidden
                              border border-white/[0.06] bg-bg-elevated"
                data-testid="landing-mobile-preview">
          {mobileHero ? (
            <>
              <img
                src={mobileHero}
                alt="FUUSIC mobile preview"
                loading="lazy"
                onError={(e) => { e.currentTarget.style.display = "none"; }}
                className="absolute inset-0 w-full h-full object-cover"
                data-testid="landing-mobile-preview-img" />
              <div className="absolute inset-0
                                          bg-gradient-to-tr from-bg-base/70
                                          via-transparent to-bg-base/30" />
            </>
          ) : (
            <div className="absolute inset-0"
                    style={{
                      background: "radial-gradient(ellipse at 30% 20%, rgba(0,212,255,0.25), transparent 50%)," +
                                                "radial-gradient(ellipse at 80% 80%, rgba(255,46,142,0.25), transparent 50%)",
                    }} />
          )}
        </div>
      </div>
    </section>
  );
}

function Testimonials() {
  const QUOTES = [
    { who: "Nikita R.", role: "Listener · Mumbai",
          q: "The AI host actually knows my mood. It plays Sufi at midnight without me asking." },
    { who: "Café Bateel",  role: "Business partner · Dubai",
          q: "Trivia nights brought 40 new faces in two weeks. The leaderboard does the marketing for us." },
    { who: "Lulu Hypermart", role: "Advertiser · UAE",
          q: "Route-based offers turned into actual footfalls. Numbers we can defend in a board meeting." },
  ];
  return (
    <section data-testid="landing-testimonials"
                  className="relative py-20 border-t border-white/[0.06]">
      <div className="max-w-7xl mx-auto px-6 lg:px-10">
        <SectionEyebrow>Reviews</SectionEyebrow>
        <SectionTitle>Heard around the block.</SectionTitle>
        <div className="mt-10 grid grid-cols-1 md:grid-cols-3 gap-5">
          {QUOTES.map((q) => (
            <figure key={q.who}
                          data-placeholder="true"
                          className="rounded-token-card border border-white/[0.06]
                                          bg-bg-elevated p-6">
              <div className="flex gap-1 text-accent-gold">
                {[0,1,2,3,4].map((i) => <Star key={i} size={14} fill="currentColor" />)}
              </div>
              <blockquote className="mt-4 text-sm">“{q.q}”</blockquote>
              <figcaption className="mt-4 text-xs text-text-secondary font-mono">
                <span className="text-white">{q.who}</span> · {q.role}
              </figcaption>
            </figure>
          ))}
        </div>
      </div>
    </section>
  );
}

function SectionEyebrow({ children }) {
  return (
    <div className="text-[10px] font-mono uppercase tracking-widest
                          text-text-secondary">{children}</div>
  );
}

function SectionTitle({ children }) {
  return (
    <h2 className="font-display font-bold text-4xl sm:text-5xl
                          tracking-display-tight mt-2 max-w-3xl">
      {children}
    </h2>
  );
}
