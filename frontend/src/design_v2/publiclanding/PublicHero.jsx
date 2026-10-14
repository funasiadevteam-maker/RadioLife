// Public hero — compact, social/lifestyle-first. Two variants: the open-launch
// hero (Join free / Explore) and the Business-Setup-Mode "coming soon" hero
// with an inline waitlist. Lifestyle image carries floating avatar bubbles.
import { useState } from "react";
import axios from "axios";
import { Users, ShoppingBag, Gamepad2, Radio, Coins, Check, Star } from "lucide-react";

const API = `${process.env.REACT_APP_BACKEND_URL || ""}/api`;

function WaitlistInline({ t }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    const v = email.trim().toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v)) { setErr("Enter a valid email"); return; }
    setErr(""); setBusy(true);
    try { const r = await axios.post(`${API}/waitlist`, { email: v, interests: ["consumer"] }); setRes(r.data || {}); }
    catch (_e) { setErr("Could not join right now. Please try again."); }
    finally { setBusy(false); }
  };
  if (res) {
    return (
      <div data-testid="fpl-waitlist-success" style={{ background: t.card, border: `1px solid ${t.border}`,
        borderRadius: 16, padding: 16, maxWidth: 420, boxShadow: t.shadow }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, color: t.text, fontWeight: 800 }}>
          <Check size={18} color="#22c55e" /> You&apos;re in! Position
          <span style={{ background: t.accentGrad, WebkitBackgroundClip: "text", backgroundClip: "text",
            WebkitTextFillColor: "transparent" }}> #{res.position}</span> of {res.total}
        </div>
        {res.tier && (
          <div style={{ marginTop: 8, display: "inline-flex", alignItems: "center", gap: 5, fontSize: 11,
            fontWeight: 800, padding: "4px 10px", borderRadius: 999, background: t.goldBg, color: t.gold }}>
            <Star size={11} /> {res.tier}
          </div>
        )}
      </div>
    );
  }
  return (
    <form onSubmit={submit} data-testid="fpl-waitlist-form"
      style={{ display: "flex", gap: 8, flexWrap: "wrap", maxWidth: 440 }}>
      <input data-testid="fpl-waitlist-email" type="email" value={email} placeholder="your@email.com"
        onChange={(e) => setEmail(e.target.value)}
        style={{ flex: "1 1 200px", minWidth: 180, padding: "12px 14px", borderRadius: 999,
          border: `1px solid ${t.border}`, background: t.card, color: t.text, fontSize: 14, outline: "none" }} />
      <button type="submit" disabled={busy} data-testid="fpl-waitlist-submit" className="fpl-press"
        style={{ border: "none", cursor: "pointer", color: "#fff", fontWeight: 800, fontSize: 14,
          padding: "12px 22px", borderRadius: 999, background: t.accentGrad }}>
        {busy ? "Joining…" : "Join the Waitlist"}
      </button>
      {err && <div style={{ flexBasis: "100%", color: "#f43f5e", fontSize: 12.5 }}>{err}</div>}
    </form>
  );
}

const BUBBLES = [
  { top: "12%", right: "40%", Icon: Users, bg: "#a855f7", delay: "0s" },
  { top: "30%", right: "8%", Icon: ShoppingBag, bg: "#ec4899", delay: "0.6s" },
  { top: "58%", right: "30%", Icon: Gamepad2, bg: "#6366f1", delay: "1.2s" },
  { top: "70%", right: "6%", Icon: Radio, bg: "#f43f5e", delay: "1.8s" },
  { top: "44%", right: "48%", Icon: Coins, bg: "#f59e0b", delay: "2.4s" },
];

export default function PublicHero({ t, hero, comingSoon, offerMonths, waitlistEnabled,
  onAuth, onExplore, stationCopy }) {
  const headline = comingSoon ? "FUUSIC is Coming." : hero.headline;
  const words = headline.split(" ");
  const tail = words.slice(-2).join(" ");
  const head = words.slice(0, -2).join(" ");

  return (
    <section data-testid="fpl-hero" style={{ background: t.heroBg, borderRadius: 22, overflow: "hidden",
      border: `1px solid ${t.navBorder}`, margin: "18px 0 4px" }}>
      <div className="fpl-hero-grid" style={{ padding: "26px clamp(20px,4vw,44px)" }}>
        {/* copy */}
        <div className="fpl-fade">
          <h1 data-testid="fpl-hero-headline" style={{ fontWeight: 900, letterSpacing: "-0.02em",
            lineHeight: 1.02, color: t.text, fontSize: "clamp(34px,4.4vw,54px)", margin: 0 }}>
            {head}{head ? " " : ""}
            <span style={{ background: "linear-gradient(100deg,#c084fc,#ec4899 50%,#60a5fa)",
              WebkitBackgroundClip: "text", backgroundClip: "text", WebkitTextFillColor: "transparent" }}>
              {tail}
            </span>
          </h1>
          <p style={{ marginTop: 10, color: t.text2, fontWeight: 800, fontSize: "clamp(16px,2vw,20px)" }}>
            {hero.subheadline}
          </p>
          <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: "4px 10px",
            color: t.muted, fontSize: 13, fontWeight: 600 }}>
            {(hero.chips || []).map((c, i) => (
              <span key={c} style={{ display: "inline-flex", alignItems: "center", gap: 10 }}>
                {i > 0 && <span style={{ opacity: 0.4 }}>·</span>}{c}
              </span>
            ))}
          </div>
          <p style={{ marginTop: 14, color: t.text2, fontSize: 14.5, lineHeight: 1.55, maxWidth: 520 }}>
            {comingSoon
              ? `Be first in when we open. Members get ${offerMonths || 6} months of perks. ${stationCopy}`
              : hero.supporting}
          </p>

          <div style={{ marginTop: 20 }}>
            {comingSoon ? (
              waitlistEnabled !== false ? <WaitlistInline t={t} /> : null
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
                <button data-testid="fpl-hero-primary" onClick={() => onAuth("signup")} className="fpl-press"
                  style={{ border: "none", cursor: "pointer", color: "#fff", fontWeight: 800, fontSize: 15,
                    padding: "13px 26px", borderRadius: 999, background: t.accentGrad,
                    boxShadow: "0 12px 30px rgba(168,85,247,.35)" }}>
                  {hero.primary_cta_label}
                </button>
                <button data-testid="fpl-hero-secondary" onClick={onExplore} className="fpl-press"
                  style={{ cursor: "pointer", color: t.text, fontWeight: 800, fontSize: 15,
                    padding: "13px 24px", borderRadius: 999, background: "transparent",
                    border: `1.5px solid ${t.border}` }}>
                  {hero.secondary_cta_label}
                </button>
              </div>
            )}
            <button data-testid="fpl-hero-business" onClick={() => onAuth("business")} className="fpl-press"
              style={{ marginTop: 14, background: "none", border: "none", cursor: "pointer",
                color: t.accent, fontWeight: 800, fontSize: 13.5 }}>
              Own a business? Join early →
            </button>
          </div>
        </div>

        {/* lifestyle image + floating bubbles */}
        <div className="fpl-hero-img" style={{ position: "relative", minHeight: 300, borderRadius: 18,
          overflow: "hidden" }}>
          <img src={hero.image_url} alt="People enjoying FUUSIC" loading="eager"
            style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "cover" }} />
          <div style={{ position: "absolute", inset: 0, pointerEvents: "none",
            background: "linear-gradient(180deg, rgba(10,8,25,0.05), rgba(10,8,25,0.35))" }} />
          {BUBBLES.map((b, i) => (
            <span key={i} className="fpl-bubble" style={{ position: "absolute", top: b.top, right: b.right,
              width: 40, height: 40, borderRadius: 999, background: b.bg, display: "grid",
              placeItems: "center", boxShadow: "0 8px 20px rgba(0,0,0,.3)", animationDelay: b.delay }}>
              <b.Icon size={18} color="#fff" />
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
