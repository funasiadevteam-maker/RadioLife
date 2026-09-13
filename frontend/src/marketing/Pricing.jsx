// Phase 15c — /pricing
import React from "react";
import { Link } from "react-router-dom";
import { Check, X } from "lucide-react";
import MarketingShell, { SEO } from "./MarketingShell";

const TIERS = [
  {
    name: "Free", price: "$0",       cadence: "forever",
    accent: "border-white/[0.06]",
    cta: { to: "/login", label: "Start listening" },
    bullets: [
      ["Personalized AI radio",     true],
      ["1 skip per hour",             true],
      ["Wallet + rewards",            true],
      ["Live trivia",                  true],
      ["VIP channels",                 false],
      ["Ad-free listening",            false],
      ["Early access to features",    false],
    ],
  },
  {
    name: "Premium",     price: "$12", cadence: "per year",
    accent: "border-accent-electric ring-1 ring-accent-electric/30",
    badge: "Most popular",
    cta: { to: "/login?upgrade=premium", label: "Go Premium" },
    bullets: [
      ["Personalized AI radio",     true],
      ["6 skips every hour",         true],
      ["Wallet + rewards",            true],
      ["Live trivia",                  true],
      ["VIP channels",                 true],
      ["Ad-free listening",            true],
      ["Early access to features",    false],
    ],
  },
  {
    name: "Premium+",  price: "$24", cadence: "per year",
    accent: "border-accent-magenta/40",
    cta: { to: "/login?upgrade=plus", label: "Go Premium+" },
    bullets: [
      ["Personalized AI radio",     true],
      ["6 skips every hour",         true],
      ["Wallet + rewards",            true],
      ["Live trivia",                  true],
      ["VIP channels",                 true],
      ["Ad-free listening",            true],
      ["Early access to features",    true],
    ],
  },
];

export default function Pricing() {
  return (
    <MarketingShell>
      <SEO title="Pricing · Free, Premium, Premium+"
              description="Listen free with 1 skip an hour, or go Premium for 6 skips an hour, VIP channels and early access to features." />
      <section className="max-w-6xl mx-auto px-6 lg:px-10 py-20 space-y-3"
                  data-testid="pricing-hero">
        <div className="text-[10px] font-mono uppercase tracking-widest
                              text-text-secondary">Pricing</div>
        <h1 className="font-display font-extrabold text-5xl lg:text-6xl
                              tracking-display-tight">Listen free.
          <span className="text-accent-electric"> Or get more.</span></h1>
        <p className="text-text-secondary text-lg max-w-2xl">
          One subscription, no surprises. Prices in USD; local pricing
          shows at checkout.
        </p>
      </section>
      <section className="max-w-6xl mx-auto px-6 lg:px-10 pb-20
                                grid grid-cols-1 lg:grid-cols-3 gap-5"
                    data-testid="pricing-tiers">
        {TIERS.map((t) => (
          <div key={t.name}
                    data-testid={`pricing-${t.name.toLowerCase().replace("+","plus")}`}
                    className={`relative rounded-token-card border bg-bg-elevated
                                          p-6 flex flex-col ${t.accent}`}>
            {t.badge && (
              <span className="absolute -top-3 left-6 px-2 py-1 rounded-full
                                            bg-accent-electric text-bg-base font-mono
                                            text-[10px] uppercase tracking-widest">
                {t.badge}
              </span>
            )}
            <div className="font-display font-bold text-2xl tracking-display-tight">
              {t.name}
            </div>
            <div className="mt-2 flex items-baseline gap-1">
              <span className="font-display font-extrabold text-5xl
                                            tracking-display-tight">{t.price}</span>
              <span className="text-text-secondary text-sm font-mono">
                / {t.cadence}
              </span>
            </div>
            <ul className="mt-6 space-y-3 text-sm flex-1">
              {t.bullets.map(([label, ok]) => (
                <li key={label} className="flex items-center gap-2">
                  {ok
                    ? <Check size={14} className="text-accent-success" />
                    : <X size={14} className="text-text-secondary" />}
                  <span className={ok ? "" : "text-text-secondary"}>{label}</span>
                </li>
              ))}
            </ul>
            <Link to={t.cta.to}
                      data-testid={`pricing-cta-${t.name.toLowerCase().replace("+","plus")}`}
                      className="mt-6 h-11 inline-flex items-center
                                      justify-center rounded-full bg-white
                                      text-bg-base font-mono text-xs uppercase
                                      tracking-widest hover:bg-accent-electric
                                      transition-colors duration-150">
              {t.cta.label}
            </Link>
          </div>
        ))}
      </section>
    </MarketingShell>
  );
}
