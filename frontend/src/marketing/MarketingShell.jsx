// Phase 15c — public marketing shell. Routes mounted under MarketingShell
// are explicitly excluded from the listener AppShell via the
// MARKETING_ROUTES regex in /app/frontend/src/shell/AppShell.jsx.
import React, { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Menu, X } from "lucide-react";
import { Helmet } from "react-helmet-async";

const NAV = [
  { to: "/about",            label: "About" },
  { to: "/for-business",      label: "For Business" },
  { to: "/for-advertisers",  label: "For Advertisers" },
  { to: "/pricing",          label: "Pricing" },
];

export function SEO({ title, description, image }) {
  const fullTitle = title ? `${title} · BigFM` : "BigFM · AI Radio · Rewards · Local Commerce";
  const desc = description || "Non-interactive personalized radio with an AI RJ, live trivia in your neighborhood, BigCoin rewards, and a wallet of real coupons.";
  return (
    <Helmet>
      <title>{fullTitle}</title>
      <meta name="description" content={desc} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={desc} />
      <meta property="og:type" content="website" />
      {image && <meta property="og:image" content={image} />}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={desc} />
    </Helmet>
  );
}

export default function MarketingShell({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="marketing-shell"
              className="min-h-screen bg-bg-base text-text-primary
                              flex flex-col selection:bg-accent-electric/30">
      <TopNav open={open} setOpen={setOpen} />
      <main className="flex-1">{children}</main>
      <Footer />
    </div>
  );
}

function TopNav({ open, setOpen }) {
  return (
    <header
      data-testid="marketing-topnav"
      className="sticky top-0 z-40 backdrop-blur-xl
                        border-b border-white/[0.06] bg-bg-base/85"
    >
      <div className="max-w-7xl mx-auto px-6 lg:px-10 h-16 flex items-center gap-6">
        <Link to="/" data-testid="marketing-logo"
                  className="font-display font-extrabold text-xl
                                  tracking-display-tight">
          BigFM<span className="text-accent-electric">.AI</span>
        </Link>
        <nav className="hidden md:flex items-center gap-6 text-sm">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to}
                          data-testid={`mnav-${n.to.replace(/\W/g, "-")}`}
                          className={({ isActive }) =>
                            `transition-colors duration-150 hover:text-white ${
                              isActive ? "text-white" : "text-text-secondary"
                            }`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="flex-1" />
        <Link to="/login" data-testid="marketing-signin"
                  className="hidden sm:inline-block text-sm text-text-secondary
                                  hover:text-white transition-colors duration-150">
          Sign in
        </Link>
        <Link to="/login?demo=1" data-testid="marketing-demo-cta"
                  className="px-4 h-10 inline-flex items-center rounded-full
                                  bg-accent-electric text-bg-base font-mono text-xs
                                  uppercase tracking-widest hover:bg-white
                                  transition-colors duration-150">
          Try the demo
        </Link>
        <button
          type="button" data-testid="marketing-menu-toggle"
          className="md:hidden w-10 h-10 grid place-items-center
                          rounded-full hover:bg-white/5 transition-colors"
          onClick={() => setOpen((v) => !v)} aria-label="Toggle menu">
          {open ? <X size={18} /> : <Menu size={18} />}
        </button>
      </div>
      {open && (
        <div className="md:hidden border-t border-white/[0.06]
                              bg-bg-base px-6 py-3 space-y-2 text-sm"
                  data-testid="marketing-mobile-menu">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} onClick={() => setOpen(false)}
                          className="block py-2 text-text-secondary hover:text-white">
              {n.label}
            </NavLink>
          ))}
          <Link to="/login" onClick={() => setOpen(false)}
                    className="block py-2 text-text-secondary hover:text-white">
            Sign in
          </Link>
        </div>
      )}
    </header>
  );
}

function Footer() {
  const COLS = [
    {
      title: "Product",
      links: [
        ["Stations",         "/about"],
        ["Live trivia",      "/about"],
        ["BigCoin wallet",   "/about"],
        ["Mobile app",       "/about"],
      ],
    },
    {
      title: "For partners",
      links: [
        ["Open a business account", "/for-business"],
        ["Become an advertiser",     "/for-advertisers"],
        ["Press kit",                "/about"],
      ],
    },
    {
      title: "Company",
      links: [
        ["About BigFM",   "/about"],
        ["Pricing",       "/pricing"],
        ["Contact",       "/about"],
      ],
    },
    {
      title: "Legal",
      links: [
        ["Terms",         "/legal/terms"],
        ["Privacy",       "/legal/privacy"],
        ["Cookies",       "/legal/privacy"],
      ],
    },
  ];
  return (
    <footer data-testid="marketing-footer"
                className="border-t border-white/[0.06] mt-24 bg-bg-elevated/40">
      <div className="max-w-7xl mx-auto px-6 lg:px-10 py-12
                            grid grid-cols-2 md:grid-cols-5 gap-8">
        <div className="col-span-2 md:col-span-1">
          <div className="font-display font-extrabold text-lg
                                tracking-display-tight">
            BigFM<span className="text-accent-electric">.AI</span>
          </div>
          <p className="mt-3 text-sm text-text-secondary max-w-xs">
            Internet radio, reimagined. AI hosts, live trivia in your
            neighborhood, and a wallet full of real-world rewards.
          </p>
        </div>
        {COLS.map((c) => (
          <div key={c.title}>
            <div className="text-[10px] font-mono uppercase tracking-widest
                                  text-text-secondary mb-3">{c.title}</div>
            <ul className="space-y-2 text-sm">
              {c.links.map(([label, to]) => (
                <li key={label}>
                  <Link to={to} className="hover:text-white text-text-secondary
                                                          transition-colors duration-150">
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
      <div className="border-t border-white/[0.06]">
        <div className="max-w-7xl mx-auto px-6 lg:px-10 py-5
                              flex flex-wrap items-center gap-3
                              justify-between text-xs text-text-secondary
                              font-mono">
          <div>© {new Date().getFullYear()} BigFM AI Radio</div>
          <select aria-label="Language"
                        data-testid="marketing-lang-switcher"
                        className="bg-bg-elevated border border-white/[0.06]
                                        rounded-token-md px-2 py-1">
            <option>English</option>
            <option disabled>हिन्दी (soon)</option>
            <option disabled>العربية (soon)</option>
          </select>
        </div>
      </div>
    </footer>
  );
}
