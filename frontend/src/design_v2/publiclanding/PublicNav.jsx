// Sticky global navigation for the public landing: logo, center links, a More
// menu, search, appearance switcher and auth CTAs. Fully Light/Dark aware.
import { useState } from "react";
import { Search, ChevronDown, Sun, Moon, Monitor, Menu, X } from "lucide-react";
import { NAV_LINKS, MORE_LINKS } from "./fplTokens";

function AppearanceSwitcher({ t, mode, setMode, enabled }) {
  if (!enabled) return null;
  const opts = [
    { k: "light", Icon: Sun }, { k: "dark", Icon: Moon }, { k: "system", Icon: Monitor },
  ];
  return (
    <div data-testid="fpl-appearance" style={{ display: "inline-flex", gap: 2, padding: 3,
      borderRadius: 999, background: t.tag, border: `1px solid ${t.navBorder}` }}>
      {opts.map(({ k, Icon }) => (
        <button key={k} data-testid={`fpl-appearance-${k}`} onClick={() => setMode(k)}
          aria-label={`${k} theme`} className="fpl-press"
          style={{ width: 30, height: 28, borderRadius: 999, border: "none", cursor: "pointer",
            display: "grid", placeItems: "center",
            background: mode === k ? t.accentGrad : "transparent",
            color: mode === k ? "#fff" : t.text2 }}>
          <Icon size={14} />
        </button>
      ))}
    </div>
  );
}

export default function PublicNav({ t, mode, setMode, allowThemeSwitch, comingSoon,
  onNavigate, onAuth, signupLabel }) {
  const [moreOpen, setMoreOpen] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <header data-testid="fpl-nav" style={{ position: "sticky", top: 0, zIndex: 40,
      background: t.navBg, borderBottom: `1px solid ${t.navBorder}`,
      backdropFilter: "blur(16px)", WebkitBackdropFilter: "blur(16px)" }}>
      <div className="fpl-shell" style={{ height: 60, display: "flex", alignItems: "center", gap: 18 }}>
        <button data-testid="fpl-logo" onClick={() => onNavigate("/")} className="fpl-press"
          style={{ background: "none", border: "none", cursor: "pointer", fontWeight: 900,
            fontSize: 22, letterSpacing: "-0.03em",
            background: t.accentGrad, WebkitBackgroundClip: "text", backgroundClip: "text",
            WebkitTextFillColor: "transparent" }}>
          FUUSIC
        </button>

        {/* center links (desktop) */}
        <nav style={{ display: "none", gap: 4, flex: 1 }} className="fpl-navlinks">
          {NAV_LINKS.map((l) => (
            <button key={l.key} data-testid={`fpl-nav-${l.key}`} onClick={() => onNavigate(l.to)}
              className="fpl-press" style={{ background: "none", border: "none", cursor: "pointer",
                color: l.key === "home" ? t.accent : t.text, fontWeight: 700, fontSize: 14,
                padding: "8px 11px", borderRadius: 10 }}>
              {l.label}
            </button>
          ))}
          <div style={{ position: "relative" }} onMouseLeave={() => setMoreOpen(false)}>
            <button data-testid="fpl-nav-more" onClick={() => setMoreOpen((v) => !v)}
              className="fpl-press" style={{ background: "none", border: "none", cursor: "pointer",
                color: t.text, fontWeight: 700, fontSize: 14, padding: "8px 11px", borderRadius: 10,
                display: "inline-flex", alignItems: "center", gap: 3 }}>
              More <ChevronDown size={14} />
            </button>
            {moreOpen && (
              <div style={{ position: "absolute", top: "100%", left: 0, marginTop: 6, width: 190,
                background: t.card, border: `1px solid ${t.border}`, borderRadius: 14,
                boxShadow: t.shadow, padding: 6, zIndex: 50 }}>
                {MORE_LINKS.map((m) => (
                  <button key={m.key} data-testid={`fpl-more-${m.key}`}
                    onClick={() => { setMoreOpen(false); onNavigate(m.to); }} className="fpl-press"
                    style={{ display: "block", width: "100%", textAlign: "left", background: "none",
                      border: "none", cursor: "pointer", color: t.text, fontWeight: 600, fontSize: 13.5,
                      padding: "9px 10px", borderRadius: 9 }}>
                    {m.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </nav>

        <div style={{ flex: 1 }} className="fpl-navspacer" />

        {/* right cluster */}
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <button data-testid="fpl-search" onClick={() => onAuth("login")} aria-label="Search FUUSIC"
            className="fpl-press" style={{ width: 34, height: 34, borderRadius: 999, cursor: "pointer",
              border: `1px solid ${t.navBorder}`, background: t.tag, color: t.text2,
              display: "grid", placeItems: "center" }}>
            <Search size={16} />
          </button>
          <AppearanceSwitcher t={t} mode={mode} setMode={setMode} enabled={allowThemeSwitch} />
          <button data-testid="fpl-login" onClick={() => onAuth("login")} className="fpl-press fpl-login-btn"
            style={{ cursor: "pointer", color: t.accent, fontWeight: 800, fontSize: 14,
              padding: "8px 18px", borderRadius: 999, background: "transparent",
              border: `1.5px solid ${t.accent}`, display: "none" }}>
            Log In
          </button>
          <button data-testid="fpl-signup" onClick={() => onAuth(comingSoon ? "waitlist" : "signup")}
            className="fpl-press" style={{ border: "none", cursor: "pointer", color: "#fff",
              fontWeight: 800, fontSize: 13.5, padding: "9px 16px", borderRadius: 999,
              background: t.accentGrad, boxShadow: "0 8px 22px rgba(168,85,247,.32)" }}>
            {signupLabel}
          </button>
          <button data-testid="fpl-mobile-toggle" onClick={() => setMobileOpen((v) => !v)}
            className="fpl-press fpl-hamburger" aria-label="Menu"
            style={{ width: 34, height: 34, borderRadius: 10, cursor: "pointer",
              border: `1px solid ${t.navBorder}`, background: t.tag, color: t.text,
              display: "none", placeItems: "center" }}>
            {mobileOpen ? <X size={18} /> : <Menu size={18} />}
          </button>
        </div>
      </div>

      {/* mobile drawer */}
      {mobileOpen && (
        <div data-testid="fpl-mobile-menu" style={{ borderTop: `1px solid ${t.navBorder}`,
          background: t.card, padding: 10 }}>
          {[...NAV_LINKS, ...MORE_LINKS].map((l) => (
            <button key={l.key} onClick={() => { setMobileOpen(false); onNavigate(l.to); }}
              className="fpl-press" style={{ display: "block", width: "100%", textAlign: "left",
                background: "none", border: "none", cursor: "pointer", color: t.text, fontWeight: 600,
                fontSize: 15, padding: "11px 10px", borderRadius: 10 }}>
              {l.label}
            </button>
          ))}
          {/* Auth actions — always reachable from the mobile menu. */}
          <div style={{ borderTop: `1px solid ${t.navBorder}`, marginTop: 8, paddingTop: 10,
            display: "flex", flexDirection: "column", gap: 8 }}>
            <button data-testid="fpl-mobile-signup" onClick={() => { setMobileOpen(false); onAuth(comingSoon ? "waitlist" : "signup"); }}
              className="fpl-press" style={{ width: "100%", cursor: "pointer", color: "#fff",
                fontWeight: 800, fontSize: 15, padding: "12px 10px", borderRadius: 12, border: "none",
                background: t.accentGrad }}>
              {signupLabel}
            </button>
            <button data-testid="fpl-mobile-login" onClick={() => { setMobileOpen(false); onAuth("login"); }}
              className="fpl-press" style={{ width: "100%", cursor: "pointer", color: t.accent,
                fontWeight: 800, fontSize: 15, padding: "12px 10px", borderRadius: 12,
                background: "transparent", border: `1.5px solid ${t.accent}` }}>
              Log In
            </button>
            <div style={{ display: "flex", gap: 8 }}>
              <button data-testid="fpl-mobile-business" onClick={() => { setMobileOpen(false); onAuth("business"); }}
                className="fpl-press" style={{ flex: 1, cursor: "pointer", color: t.text,
                  fontWeight: 700, fontSize: 13, padding: "10px 8px", borderRadius: 11,
                  background: t.tag, border: `1px solid ${t.navBorder}` }}>
                Business Sign In
              </button>
              <button data-testid="fpl-mobile-staff" onClick={() => { setMobileOpen(false); onAuth("staff"); }}
                className="fpl-press" style={{ flex: 1, cursor: "pointer", color: t.text,
                  fontWeight: 700, fontSize: 13, padding: "10px 8px", borderRadius: 11,
                  background: t.tag, border: `1px solid ${t.navBorder}` }}>
                Staff / Admin
              </button>
            </div>
          </div>
        </div>
      )}

      <style>{`
        @media (min-width: 640px) {
          [data-testid="fpl-login"].fpl-login-btn { display: inline-block !important; }
        }
        @media (min-width: 1024px) {
          .fpl-navlinks { display: flex !important; }
          .fpl-navspacer { display: none; }
        }
        @media (max-width: 1023px) { .fpl-hamburger { display: grid !important; } }
      `}</style>
    </header>
  );
}
