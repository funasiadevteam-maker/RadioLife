// Phase 15c — /about (FUUSIC brand story)
import React from "react";
import MarketingShell, { SEO } from "./MarketingShell";
import { BRAND } from "@/config/brand";

const TEAM = [
  { name: "A. Director",  role: "Head of Programming" },
  { name: "B. Mehta",     role: "AI / Audio" },
  { name: "C. Khan",      role: "Partnerships" },
  { name: "D. Iyer",      role: "Design" },
];
const PRESS = ["The Hindu", "Gulf News", "Mint", "Khaleej Times"];

export default function About() {
  return (
    <MarketingShell>
      <SEO title="About FUUSIC"
              description="FUUSIC brings audio, social experiences, local businesses, live commerce, games and rewards together in one connected experience." />
      <section className="max-w-5xl mx-auto px-6 lg:px-10 py-20 space-y-6"
                  data-testid="about-hero">
        <div className="text-[10px] font-mono uppercase tracking-widest
                              text-text-secondary">Our story</div>
        <h1 className="font-display font-extrabold text-5xl lg:text-6xl
                              tracking-display-tight">
          Everything you love, <span className="text-accent-electric">together.</span>
        </h1>
        <p className="text-text-secondary text-lg max-w-2xl">
          FUUSIC was created around a simple idea: the things we love are better
          when they’re connected. Your music. Your friends. Your favourite places.
          Your games. Your rewards. Your local businesses. Your experiences.
          One place — {BRAND.name}.
        </p>
        <p className="text-sm font-mono uppercase tracking-[0.2em] text-accent-electric">
          {BRAND.descriptor}
        </p>
      </section>

      <section className="max-w-5xl mx-auto px-6 lg:px-10 py-12 border-t
                                border-white/[0.06]" data-testid="about-meaning">
        <Eyebrow>What does FUUSIC mean?</Eyebrow>
        <div className="mt-8 grid grid-cols-2 md:grid-cols-3 gap-5">
          {BRAND.meaning.map(([letter, word], i) => (
            <div key={i}
                 className="rounded-token-card border border-white/[0.06] bg-bg-elevated p-5">
              <div className="text-4xl font-display font-extrabold
                              bg-gradient-to-br from-accent-electric to-accent-magenta
                              bg-clip-text text-transparent">{letter}</div>
              <div className="mt-2 font-display font-bold tracking-display-tight">{word}</div>
            </div>
          ))}
        </div>
        <p className="mt-6 text-text-secondary max-w-2xl">
          {BRAND.meaningLine}. FUUSIC connects media attention to real-world
          experiences and commerce — the things people already love doing together.
        </p>
      </section>

      <section className="max-w-5xl mx-auto px-6 lg:px-10 py-12 border-t
                                border-white/[0.06]" data-testid="about-team">
        <Eyebrow>Team</Eyebrow>
        <h2 className="font-display font-bold text-3xl mt-2
                              tracking-display-tight">Made by people who love this stuff.</h2>
        <div className="mt-8 grid grid-cols-2 md:grid-cols-4 gap-5">
          {TEAM.map((t) => (
            <div key={t.name} data-placeholder="true"
                      className="rounded-token-card border border-white/[0.06]
                                      bg-bg-elevated p-5 text-center">
              <div className="w-16 h-16 mx-auto rounded-full
                                    bg-gradient-to-br from-accent-electric
                                    to-accent-magenta" />
              <div className="mt-3 font-display font-bold tracking-display-tight">
                {t.name}</div>
              <div className="text-xs text-text-secondary mt-1">{t.role}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-6 lg:px-10 py-12 border-t
                                border-white/[0.06]" data-testid="about-press">
        <Eyebrow>Press</Eyebrow>
        <div className="mt-6 flex flex-wrap gap-8 items-center
                              text-text-secondary font-display text-xl
                              tracking-display-tight">
          {PRESS.map((p) => (
            <span key={p} data-placeholder="true">{p}</span>
          ))}
        </div>
      </section>
    </MarketingShell>
  );
}

function Eyebrow({ children }) {
  return <div className="text-[10px] font-mono uppercase tracking-widest
                                      text-text-secondary">{children}</div>;
}
