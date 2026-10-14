// Public footer — brand, promise, link columns and a join CTA.
const COLS = [
  { title: "Explore", links: [["Social", "/social"], ["Listen", "/listen"], ["Shop", "/shop"], ["Play", "/play-and-win"], ["Dining", "/dining"]] },
  { title: "FUUSIC", links: [["BigPoints", "/wallet"], ["Premium", "/pricing"], ["For Business", "/for-business"], ["About", "/about"]] },
  { title: "Legal", links: [["Privacy", "/privacy"], ["Terms", "/terms"]] },
];

export default function PublicFooter({ t, onNavigate, onAuth, signupLabel }) {
  return (
    <footer data-testid="fpl-footer" style={{ borderTop: `1px solid ${t.navBorder}`, background: t.card,
      marginBottom: 64 }}>
      <div className="fpl-shell" style={{ padding: "28px 16px", display: "grid",
        gridTemplateColumns: "1.4fr repeat(3, 1fr)", gap: 20 }}>
        <div>
          <div style={{ fontWeight: 900, fontSize: 22, background: t.accentGrad, WebkitBackgroundClip: "text",
            backgroundClip: "text", WebkitTextFillColor: "transparent" }}>FUUSIC</div>
          <p style={{ marginTop: 6, color: t.text2, fontSize: 13.5, maxWidth: 280 }}>
            Everything You Love, Together. Listen. Connect. Play. Shop. Earn.
          </p>
          <button data-testid="fpl-footer-cta" onClick={() => onAuth("signup")} className="fpl-press"
            style={{ marginTop: 14, border: "none", cursor: "pointer", color: "#fff", fontWeight: 800,
              fontSize: 14, padding: "11px 20px", borderRadius: 999, background: t.accentGrad }}>
            {signupLabel}
          </button>
        </div>
        {COLS.map((c) => (
          <div key={c.title}>
            <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: ".07em", textTransform: "uppercase",
              color: t.muted, marginBottom: 10 }}>{c.title}</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {c.links.map(([label, to]) => (
                <button key={label} onClick={() => onNavigate(to)} className="fpl-press"
                  style={{ background: "none", border: "none", cursor: "pointer", color: t.text2,
                    fontSize: 13.5, fontWeight: 600, textAlign: "left", padding: 0 }}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
      <div style={{ borderTop: `1px solid ${t.border}`, padding: "14px 0" }}>
        <div className="fpl-shell" style={{ color: t.muted, fontSize: 12 }}>
          © {new Date().getFullYear()} FUUSIC · fuusic.com
        </div>
      </div>
      <style>{`@media (max-width:760px){ [data-testid="fpl-footer"] > .fpl-shell { grid-template-columns: 1fr 1fr !important; } }`}</style>
    </footer>
  );
}
