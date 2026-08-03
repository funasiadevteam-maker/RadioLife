// Phase 15c — /about
import React from "react";
import MarketingShell, { SEO } from "./MarketingShell";

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
      <SEO title="About"
              description="BigFM is rebuilding internet radio for the AI era — personalized hosts, live trivia, and a wallet that rewards listening." />
      <section className="max-w-5xl mx-auto px-6 lg:px-10 py-20 space-y-6"
                  data-testid="about-hero">
        <div className="text-[10px] font-mono uppercase tracking-widest
                              text-text-secondary">Our story</div>
        <h1 className="font-display font-extrabold text-5xl lg:text-6xl
                              tracking-display-tight">
          Radio for the way <span className="text-accent-electric">people listen now.</span>
        </h1>
        <p className="text-text-secondary text-lg max-w-2xl">
          Streaming told us what we wanted to hear. Radio told us what we
          didn’t know we wanted yet. BigFM is the second one — rebuilt with
          an AI host that knows your city, your mood, and the café two
          blocks away.
        </p>
      </section>

      <section className="max-w-5xl mx-auto px-6 lg:px-10 py-12 border-t
                                border-white/[0.06]" data-testid="about-team">
        <Eyebrow>Team</Eyebrow>
        <h2 className="font-display font-bold text-3xl mt-2
                              tracking-display-tight">Made by listeners.</h2>
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
