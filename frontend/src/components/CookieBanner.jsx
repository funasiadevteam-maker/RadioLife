// Phase Π.3 — GDPR + CCPA basic consent banner.  Persists choice in
// `bigfm_consent` cookie with `essential|analytics|advertising` flags.
// Phase AD.11 — suppressed on /admin/* (ops staff consent via a
// separate flow).
import React, { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Cookie, X } from "lucide-react";
import { Button, Chip } from "@/shell/primitives";
import { useAuth } from "@/AuthContext";

const COOKIE_KEY  = "bigfm_consent";
const COOKIE_DAYS = 180;

function readConsent() {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp(`${COOKIE_KEY}=([^;]+)`));
  if (!m) return null;
  try { return JSON.parse(decodeURIComponent(m[1])); } catch { return null; }
}
function writeConsent(obj) {
  const v = encodeURIComponent(JSON.stringify(obj));
  const exp = new Date(Date.now() + COOKIE_DAYS * 86400_000).toUTCString();
  const secure = window.location.protocol === "https:" ? "; Secure" : "";
  document.cookie = `${COOKIE_KEY}=${v}; expires=${exp}; path=/; SameSite=Lax${secure}`;
}

export default function CookieBanner() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const [open, setOpen]            = useState(false);
  const [customMode, setCustom] = useState(false);
  const [choices, setChoices]    = useState({
    essential: true, analytics: false, advertising: false,
  });

  useEffect(() => {
    const c = readConsent();
    if (!c) setOpen(true);
    else setChoices({ essential: true, ...c });
  }, []);

  // Phase AD.11 — suppress on admin routes (ops staff consent
  // separately via internal onboarding).  Rendered as null so the
  // banner never obscures admin tables / actions.  Also suppressed on
  // FUUSIC Shop/Sell surfaces where a fixed bottom CTA would clash.
  if (pathname.startsWith("/admin")) return null;
  if (pathname === "/shop" || pathname.startsWith("/shop/") || pathname === "/sell") return null;

  const acceptAll = () => {
    const v = { essential: true, analytics: true, advertising: true,
                          accepted_at: new Date().toISOString() };
    writeConsent(v); setChoices(v); setOpen(false);
  };
  const acceptEssentialOnly = () => {
    const v = { essential: true, analytics: false, advertising: false,
                          accepted_at: new Date().toISOString() };
    writeConsent(v); setChoices(v); setOpen(false);
  };
  const saveCustom = () => {
    const v = { ...choices, accepted_at: new Date().toISOString() };
    writeConsent(v); setOpen(false);
  };
  if (!open) return null;

  return (
    <div data-testid="cookie-banner"
            className={`fixed ${user ? "bottom-44" : "bottom-4"} left-3 right-3 lg:left-auto lg:right-4
                              lg:bottom-4 lg:max-w-md z-[80] rounded-token-md
                              bg-bg-elevated/95 backdrop-blur-md
                              border border-white/[0.10] shadow-2xl
                              p-4 space-y-3 text-sm`}>
      <header className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2 text-accent-gold
                                font-display font-bold tracking-display-tight">
          <Cookie size={16} /> Cookies on FUUSIC
        </div>
        <button onClick={acceptEssentialOnly}
                        aria-label="Dismiss with essential cookies only"
                        data-testid="cookie-banner-close"
                        className="text-text-secondary hover:text-white">
          <X size={14} />
        </button>
      </header>
      <p className="text-text-secondary text-xs leading-relaxed">
        We use essential cookies to keep FUUSIC working. With your permission,
        we&apos;ll also use analytics + advertising cookies to make the
        experience smarter and partly fund free radio.{" "}
        <Link to="/cookies" className="underline text-accent-electric">
          Cookie Policy
        </Link>.
      </p>

      {customMode && (
        <div className="space-y-2" data-testid="cookie-banner-custom">
          {[
            { key: "essential",      label: "Essential",      locked: true,
                blurb: "Auth, session, security." },
            { key: "analytics",      label: "Analytics",      locked: false,
                blurb: "Usage stats so we know what to improve." },
            { key: "advertising", label: "Advertising", locked: false,
                blurb: "Personalised ad recommendations." },
          ].map(({ key, label, locked, blurb }) => (
            <label key={key}
                          className="flex items-start gap-2 cursor-pointer"
                          data-testid={`cookie-banner-${key}`}>
              <input type="checkbox" checked={choices[key]}
                              disabled={locked}
                              onChange={(e) => setChoices((c) => ({
                                ...c, [key]: e.target.checked,
                              }))}
                              className="mt-0.5 accent-accent-gold" />
              <div>
                <div className="text-text-primary font-semibold text-xs">
                  {label}{locked && (
                    <Chip tone="neutral" className="ml-2">Always on</Chip>
                  )}
                </div>
                <div className="text-text-secondary text-[10px]">{blurb}</div>
              </div>
            </label>
          ))}
        </div>
      )}

      <div className="flex gap-2 flex-wrap">
        {!customMode && (
          <>
            <Button variant="gold" size="sm" onClick={acceptAll}
                            data-testid="cookie-banner-accept-all">
              Accept all
            </Button>
            <Button variant="outline" size="sm" onClick={acceptEssentialOnly}
                            data-testid="cookie-banner-essential">
              Essential only
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setCustom(true)}
                            data-testid="cookie-banner-customise">
              Customise
            </Button>
          </>
        )}
        {customMode && (
          <>
            <Button variant="gold" size="sm" onClick={saveCustom}
                            data-testid="cookie-banner-save-custom">
              Save preferences
            </Button>
            <Button variant="ghost" size="sm" onClick={() => setCustom(false)}
                            data-testid="cookie-banner-back">
              Back
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
