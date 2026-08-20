// Phase Π.3 — Legal pages (Privacy, Terms, Cookies, DMCA).  Boilerplate
// covering RadioLife's feature set.  Plain text, no design subagent needed
// for legal pages — clarity beats aesthetics here.
import React from "react";
import { Link } from "react-router-dom";

const Shell = ({ title, lastUpdated, children, testid }) => (
  <div data-testid={testid}
          className="min-h-screen bg-bg-base text-text-primary
                            px-4 sm:px-8 py-12 max-w-3xl mx-auto">
    <Link to="/" className="text-xs text-accent-electric hover:underline">
      ← RadioLife home
    </Link>
    <h1 className="font-display font-bold text-4xl sm:text-5xl
                            tracking-display-tight mt-4 mb-2">{title}</h1>
    <p className="text-xs text-text-secondary mb-8">
      Last updated · {lastUpdated}
    </p>
    <div className="prose prose-invert max-w-none text-sm leading-relaxed
                            text-text-primary space-y-4
                            [&_h2]:font-display [&_h2]:font-bold [&_h2]:text-lg
                            [&_h2]:tracking-display-tight [&_h2]:mt-8 [&_h2]:mb-2
                            [&_h2]:text-accent-gold
                            [&_p]:text-text-secondary
                            [&_li]:text-text-secondary [&_li]:my-1
                            [&_a]:text-accent-electric [&_a]:underline">
      {children}
    </div>
    <footer className="mt-12 pt-6 border-t border-white/[0.08]
                              text-xs text-text-secondary">
      Questions? Email{" "}
      <a href="mailto:legal@bigfantv.com">legal@bigfantv.com</a>.
    </footer>
  </div>
);

export function PrivacyPolicy() {
  return (
    <Shell title="Privacy Policy" lastUpdated="2026-06-19" testid="page-privacy">
      <p>This Privacy Policy describes how RadioLife ("RadioLife", "we", "us") collects, uses, and shares personal information when you use bigfantv.com, app.bigfantv.com, our mobile apps, or any RadioLife-branded service (collectively, the "Service").</p>
      <h2>1. Information we collect</h2>
      <ul>
        <li><strong>Account info</strong> — email, display name, password hash, optional profile picture.</li>
        <li><strong>Usage</strong> — listen history, station favourites, trivia answers, predict-and-win selections, share events.</li>
        <li><strong>Location</strong> — approximate location (city/market) derived from IP, plus precise GPS only when you grant it for commute features.</li>
        <li><strong>Device</strong> — browser/app type, OS, IP address, language.</li>
        <li><strong>Payments</strong> — handled by Stripe; we store the Stripe customer ID and the last four digits of the card you used.</li>
        <li><strong>Communications</strong> — emails we send and opens/clicks captured via Mailgun webhooks.</li>
      </ul>
      <h2>2. How we use it</h2>
      <ul>
        <li>Personalise station picks, trivia topics, predict-and-win events, and local offers.</li>
        <li>Run rewards (BigPoints balance, badges, city stamps, leaderboards).</li>
        <li>Process payments for Premium subscriptions, ad campaigns, and Predict & Win entries.</li>
        <li>Send transactional emails (welcome, invite, receipts) and, with consent, promotional emails.</li>
        <li>Detect and prevent fraud, abuse, and policy violations.</li>
      </ul>
      <h2>3. Sharing</h2>
      <p>We share data with: Stripe (payments), Mailgun (transactional email), OpenAI (script generation), ElevenLabs (voice synthesis), NewsAPI (headlines), and Tigris (object storage). We never sell your personal information.</p>
      <h2>4. Retention</h2>
      <p>Account data is retained for the life of your account. Listen history older than 24 months is anonymised. Payment records are retained for 7 years per US tax law.</p>
      <h2>5. Your rights</h2>
      <p>You can access, correct, export, or delete your data by emailing <a href="mailto:privacy@bigfantv.com">privacy@bigfantv.com</a>. California and EU residents have additional rights under CCPA / GDPR — we'll honour them within 30 days.</p>
      <h2>6. Children</h2>
      <p>RadioLife is not directed at children under 13. We do not knowingly collect data from anyone under 13. If you believe we have, email <a href="mailto:legal@bigfantv.com">legal@bigfantv.com</a>.</p>
      <h2>7. Changes</h2>
      <p>We'll update this page when we materially change how we handle data, and notify active users by email at least 14 days in advance.</p>
    </Shell>
  );
}

export function TermsOfService() {
  return (
    <Shell title="Terms of Service" lastUpdated="2026-06-19" testid="page-terms">
      <p>By accessing RadioLife you agree to these Terms.  If you don&apos;t agree, please don&apos;t use the Service.</p>
      <h2>1. Your account</h2>
      <p>You must be 13+ to create an account. You're responsible for safeguarding your password and for activity under your account.</p>
      <h2>2. Acceptable use</h2>
      <p>You may not (a) re-broadcast or commercially exploit RadioLife-licensed music outside the Service; (b) impersonate another person; (c) upload content you don&apos;t have rights to; (d) scrape or systematically copy our content; (e) abuse the Predict & Win or rewards systems.</p>
      <h2>3. Music + content</h2>
      <p>RadioLife streams (a) licensed music via direct partnerships and DMCA-compliant performance rights; (b) community-uploaded tracks under the RadioLife Community Upload License (the uploader represents they have rights to the audio); (c) third-party radio streams via public Radio Browser indexes.</p>
      <h2>4. Voice cloning</h2>
      <p>AI host voices on RadioLife are derived from voice talent who consented in writing. You may not request voice clones of any third party without their written consent.</p>
      <h2>5. Rewards + BigPoints</h2>
      <p>BigPoints is a closed-loop loyalty unit, not currency. It has no cash value and cannot be sold or transferred outside the Service. Voucher coupons are issued by participating businesses and honoured at their discretion.</p>
      <h2>6. Payments</h2>
      <p>Premium subscriptions and ad campaign purchases are processed by Stripe. Refunds: subscription cancellations take effect at the end of the current billing period; ad campaign refunds are available only for unspent budget within 7 days of purchase.</p>
      <h2>7. Termination</h2>
      <p>We may suspend or terminate accounts for violations.  You may delete your account at any time from Settings.</p>
      <h2>8. Liability</h2>
      <p>RadioLife is provided "as is".  To the maximum extent permitted by law, RadioLife's aggregate liability is limited to the amount you paid us in the 12 months before the claim.</p>
      <h2>9. Governing law</h2>
      <p>These Terms are governed by the laws of the State of Texas, USA.  Disputes go to the state or federal courts in Dallas County, Texas.</p>
    </Shell>
  );
}

export function CookiePolicy() {
  return (
    <Shell title="Cookie Policy" lastUpdated="2026-06-19" testid="page-cookies">
      <h2>What cookies we use</h2>
      <ul>
        <li><strong>Essential</strong> — session, CSRF, security. Always on.</li>
        <li><strong>Analytics</strong> — anonymised usage metrics so we can improve the product.</li>
        <li><strong>Advertising</strong> — frequency capping + personalised ad placements.</li>
      </ul>
      <h2>Your control</h2>
      <p>You can change your preferences any time from the cookie banner, or by clearing the <code>bigfm_consent</code> cookie in your browser. Essential cookies cannot be disabled because the Service won&apos;t work without them.</p>
      <h2>Third-party cookies</h2>
      <p>Stripe sets a cookie on its Checkout page (not ours) for fraud detection.  Google Maps (when commute features are enabled) sets cookies on its tile servers.</p>
    </Shell>
  );
}

export function DmcaPolicy() {
  return (
    <Shell title="DMCA Takedown Procedure" lastUpdated="2026-06-19" testid="page-dmca">
      <p>RadioLife honours the Digital Millennium Copyright Act ("DMCA").  If you believe content on RadioLife infringes your copyright, follow these steps.</p>
      <h2>1. Send a takedown notice</h2>
      <p>Email <a href="mailto:dmca@bigfantv.com">dmca@bigfantv.com</a> with the following.  Notices missing any required item will be returned.</p>
      <ul>
        <li>Your physical or electronic signature.</li>
        <li>Identification of the copyrighted work claimed to be infringed.</li>
        <li>Identification of the RadioLife URL(s) hosting the allegedly infringing material.</li>
        <li>Your contact information (name, address, phone, email).</li>
        <li>A statement that you have a good-faith belief that the disputed use is not authorised.</li>
        <li>A statement that the information in the notice is accurate and, under penalty of perjury, that you are the copyright owner or authorised to act on their behalf.</li>
      </ul>
      <h2>2. Our response</h2>
      <p>Within 5 business days we&apos;ll review and, where required, remove the content and notify the uploader.</p>
      <h2>3. Counter-notice</h2>
      <p>If you uploaded content that was removed in error, you may file a counter-notice to the same email.</p>
      <h2>4. Repeat infringers</h2>
      <p>We terminate accounts that receive three or more valid DMCA notices.</p>
    </Shell>
  );
}
