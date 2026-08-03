// Phase 15c — Legal page scaffolds. Real copy goes in alongside Phase 2
// compliance review. These render under /legal/terms and /legal/privacy
// inside the MarketingShell with proper SEO meta.
import React from "react";
import MarketingShell, { SEO } from "./MarketingShell";

const SECTIONS_TERMS = [
  ["Acceptance",           "By accessing or using BigFM you agree to these Terms. If you do not agree, do not use the service."],
  ["The service",           "BigFM provides a non-interactive personalized internet radio service, AI-hosted segments, games, and a rewards wallet."],
  ["Eligibility",           "You must be at least 13 years old, or the minimum age required in your country, to use BigFM. Some features require 18+."],
  ["Content & licenses",   "Music is licensed for non-interactive streaming via partnered rights bodies. You may not download, copy, or rebroadcast without permission."],
  ["Wallet & rewards",     "BigCoin is a non-transferable in-product reward unit. It has no cash value, cannot be sold, and may expire per the Wallet Terms."],
  ["Termination",           "We may suspend or terminate accounts that violate these Terms or applicable law."],
  ["Disclaimers",           "The service is provided on an as-is basis without warranties of any kind, express or implied."],
  ["Contact",                "Questions? Reach us at legal@bigfm.example."],
];

const SECTIONS_PRIVACY = [
  ["What we collect",      "Account email, listening telemetry, market/city, opt-in location data, in-app behavior for personalization."],
  ["How we use it",         "To deliver radio recommendations, run games and rewards, measure ad effectiveness, and improve the service."],
  ["Who we share with",    "Authorized service providers (hosting, audio synthesis, analytics) under contract. We do not sell your data."],
  ["Your choices",          "You can edit your profile, opt out of location-based offers, and request export/deletion at any time."],
  ["Children",                "BigFM is not designed for children under 13. We do not knowingly collect data from anyone under 13."],
  ["International transfers", "Data may be processed in the US, EU, or UAE depending on your market. We use appropriate safeguards."],
  ["Retention",               "We retain account data for as long as your account is active and for a limited period after closure for legal/operational needs."],
  ["Contact",                "Privacy questions? Reach us at privacy@bigfm.example."],
];

function LegalScaffold({ title, eyebrow, sections, testId }) {
  const updated = new Date().toISOString().slice(0, 10);
  return (
    <div data-testid={testId}
              className="max-w-3xl mx-auto px-6 lg:px-10 py-20 space-y-8">
      <div>
        <div className="text-[10px] font-mono uppercase tracking-widest
                              text-text-secondary">{eyebrow}</div>
        <h1 className="font-display font-extrabold text-5xl
                              tracking-display-tight mt-2">{title}</h1>
        <div className="mt-2 text-xs font-mono text-text-secondary">
          Last updated · {updated}
        </div>
        <div className="mt-3 text-xs font-mono uppercase tracking-widest
                              text-accent-gold">
          Draft for review — final version under legal review
        </div>
      </div>
      <div className="space-y-6">
        {sections.map(([h, body]) => (
          <section key={h}>
            <h2 className="font-display font-bold text-xl
                                  tracking-display-tight">{h}</h2>
            <p className="mt-2 text-text-secondary text-sm leading-relaxed">
              {body}
            </p>
          </section>
        ))}
      </div>
    </div>
  );
}

export function LegalTerms() {
  return (
    <MarketingShell>
      <SEO title="Terms of Service"
              description="The terms that govern your use of BigFM — radio, wallet, games, and rewards." />
      <LegalScaffold testId="legal-terms" eyebrow="Legal"
                              title="Terms of Service" sections={SECTIONS_TERMS} />
    </MarketingShell>
  );
}

export function LegalPrivacy() {
  return (
    <MarketingShell>
      <SEO title="Privacy Policy"
              description="What BigFM collects, how it's used, and the choices you control." />
      <LegalScaffold testId="legal-privacy" eyebrow="Legal"
                              title="Privacy Policy" sections={SECTIONS_PRIVACY} />
    </MarketingShell>
  );
}
