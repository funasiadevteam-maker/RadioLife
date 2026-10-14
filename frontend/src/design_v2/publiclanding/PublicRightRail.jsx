// Right sidebar — People You May Know, Live Now, Sponsored & Discover.
import {
  BadgeCheck, Crown, Store, Coins, Utensils, Users, ChevronRight,
} from "lucide-react";
import { initials } from "../socialfeed/sfTheme";

const PROMO_ICON = { crown: Crown, store: Store, coins: Coins, utensils: Utensils, users: Users };

function Section({ t, title, onSeeAll, children, testid }) {
  return (
    <div data-testid={testid} style={{ background: t.card, border: `1px solid ${t.border}`,
      borderRadius: 16, boxShadow: t.shadow, padding: 14, marginBottom: 16 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 10 }}>
        <span style={{ fontSize: 11, fontWeight: 900, letterSpacing: ".07em", textTransform: "uppercase",
          color: t.muted }}>{title}</span>
        {onSeeAll && (
          <button onClick={onSeeAll} className="fpl-press" style={{ background: "none", border: "none",
            cursor: "pointer", color: t.accent, fontWeight: 700, fontSize: 12 }}>See All</button>
        )}
      </div>
      {children}
    </div>
  );
}

function Ava({ t, url, name, size = 38 }) {
  if (url) return <img src={url} alt="" loading="lazy" style={{ width: size, height: size, borderRadius: 999, objectFit: "cover", flexShrink: 0 }} />;
  return (
    <span style={{ width: size, height: size, borderRadius: 999, flexShrink: 0, display: "grid",
      placeItems: "center", color: "#fff", fontWeight: 800, background: t.accentGrad }}>{initials(name)}</span>
  );
}

export default function PublicRightRail({ t, people, live, discover, promos, onAuth, onNavigate }) {
  return (
    <aside data-testid="fpl-right-rail" className="fpl-right">
      {/* People You May Know */}
      <Section t={t} title="People You May Know" testid="fpl-people" onSeeAll={() => onAuth("login")}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {people.map((p, i) => (
            <div key={i} style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Ava t={t} url={p.avatar_url} name={p.name} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <span style={{ fontWeight: 800, fontSize: 13.5, color: t.text, whiteSpace: "nowrap",
                    overflow: "hidden", textOverflow: "ellipsis" }}>{p.name}</span>
                  {(p.kind === "business" || p.verified) && <BadgeCheck size={13} color={t.accent} />}
                </div>
                <div style={{ fontSize: 11.5, color: t.muted }}>{p.descriptor}</div>
              </div>
              <button data-testid="fpl-person-follow" onClick={() => onAuth("login")} className="fpl-press"
                style={{ fontSize: 12, fontWeight: 800, color: t.accent, background: t.accentSoft,
                  border: "none", borderRadius: 999, padding: "6px 14px", cursor: "pointer" }}>Follow</button>
            </div>
          ))}
        </div>
      </Section>

      {/* Live Now — genuinely live first, then an illustrative discover set */}
      <Section t={t} title="Live Now" testid="fpl-live-now" onSeeAll={() => onNavigate("/social")}>
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {live.map((l) => (
            <LiveRow key={l.id} t={t} l={{ ...l, live: true }} onClick={() => onNavigate("/social")} />
          ))}
          {live.length === 0 && (
            <div style={{ fontSize: 11, color: t.muted, marginBottom: 2 }}>
              Nothing live right now — discover what&apos;s happening:
            </div>
          )}
          {(live.length === 0 ? discover : []).map((l) => (
            <LiveRow key={l.id} t={t} l={{ ...l, live: false }} illustrative onClick={() => onAuth("login")} />
          ))}
        </div>
      </Section>

      {/* Sponsored & Discover */}
      <Section t={t} title="Sponsored &amp; Discover" testid="fpl-promos">
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {promos.map((p) => {
            const Icon = PROMO_ICON[p.icon] || Store;
            return (
              <div key={p.id} data-testid={`fpl-promo-${p.id}`} className="fpl-lift"
                style={{ display: "flex", alignItems: "center", gap: 10, padding: 8, borderRadius: 12,
                  border: `1px solid ${t.border}`, background: t.cardAlt }}>
                {p.image_url ? (
                  <img src={p.image_url} alt="" loading="lazy" style={{ width: 42, height: 42, borderRadius: 10, objectFit: "cover", flexShrink: 0 }} />
                ) : (
                  <span style={{ width: 42, height: 42, borderRadius: 10, flexShrink: 0, display: "grid",
                    placeItems: "center", background: `${p.accent || t.accent}22` }}>
                    <Icon size={20} color={p.accent || t.accent} />
                  </span>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <span style={{ fontWeight: 800, fontSize: 12.5, color: t.text, whiteSpace: "nowrap",
                      overflow: "hidden", textOverflow: "ellipsis" }}>{p.name}</span>
                  </div>
                  <div style={{ fontSize: 11, color: t.muted, whiteSpace: "nowrap", overflow: "hidden",
                    textOverflow: "ellipsis" }}>{p.text}</div>
                  {p.sponsored && (
                    <span style={{ fontSize: 9, fontWeight: 700, color: t.tagText }}>Sponsored</span>
                  )}
                </div>
                <button onClick={() => onNavigate(p.cta_to || "/login")} className="fpl-press"
                  style={{ fontSize: 11.5, fontWeight: 800, color: "#fff", background: t.accentGrad,
                    border: "none", borderRadius: 999, padding: "6px 12px", cursor: "pointer",
                    whiteSpace: "nowrap", flexShrink: 0 }}>{p.cta_label}</button>
              </div>
            );
          })}
        </div>
      </Section>
    </aside>
  );
}

function LiveRow({ t, l, onClick, illustrative }) {
  return (
    <button onClick={onClick} className="fpl-press" style={{ display: "flex", alignItems: "center", gap: 10,
      width: "100%", textAlign: "left", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
      <div style={{ position: "relative", flexShrink: 0 }}>
        <img src={l.thumb} alt="" loading="lazy" style={{ width: 52, height: 52, borderRadius: 12, objectFit: "cover" }} />
        {l.live && (
          <span style={{ position: "absolute", top: 4, left: 4, fontSize: 8, fontWeight: 900, color: "#fff",
            background: t.live, padding: "1px 5px", borderRadius: 999 }}>LIVE</span>
        )}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 800, fontSize: 13, color: t.text, whiteSpace: "nowrap", overflow: "hidden",
          textOverflow: "ellipsis" }}>{l.name}</div>
        <div style={{ fontSize: 11.5, color: t.muted }}>{l.desc}{illustrative ? " · preview" : ""}</div>
      </div>
      <ChevronRight size={16} color={t.muted} />
    </button>
  );
}
