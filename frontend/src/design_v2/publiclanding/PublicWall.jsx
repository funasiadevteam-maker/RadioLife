// Center social wall: composer preview, Together shortcuts, Following/For You
// tabs and the mixed public feed (reuses the shared SocialFeedCard renderer).
import { useState } from "react";
import {
  Image, Music, Mic, MapPin, MoreHorizontal, Headphones, Gamepad2, ShoppingBag,
  Moon, Sparkles, Loader2,
} from "lucide-react";
import SocialFeedCard from "../socialfeed/SocialFeedCard";
import { TOGETHER } from "./fplTokens";

const SHORTCUT_ICON = {
  headphones: Headphones, gamepad: Gamepad2, pin: MapPin, bag: ShoppingBag,
  moon: Moon, sparkles: Sparkles,
};
const COMPOSER_ACTIONS = [
  { key: "photo", label: "Photo/Video", Icon: Image, color: "#22c55e" },
  { key: "music", label: "Music", Icon: Music, color: "#a855f7" },
  { key: "voice", label: "Voice", Icon: Mic, color: "#ec4899" },
  { key: "checkin", label: "Check In", Icon: MapPin, color: "#f43f5e" },
  { key: "more", label: "More", Icon: MoreHorizontal, color: "#60a5fa" },
];

function Composer({ t, onAuth }) {
  return (
    <div data-testid="fpl-composer" style={{ background: t.card, border: `1px solid ${t.border}`,
      borderRadius: 18, boxShadow: t.shadow, padding: 14 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ width: 40, height: 40, borderRadius: 999, flexShrink: 0, display: "grid",
          placeItems: "center", color: "#fff", fontWeight: 900, background: t.accentGrad }}>F</span>
        <button data-testid="fpl-composer-input" onClick={() => onAuth("login")} className="fpl-press"
          style={{ flex: 1, textAlign: "left", padding: "11px 16px", borderRadius: 999,
            background: t.cardAlt, border: `1px solid ${t.border}`, color: t.muted, cursor: "pointer",
            fontSize: 14.5 }}>
          What&apos;s on your mind?
        </button>
      </div>
      <div className="fpl-noscroll" style={{ display: "flex", gap: 4, marginTop: 10, overflowX: "auto" }}>
        {COMPOSER_ACTIONS.map((a) => (
          <button key={a.key} data-testid={`fpl-composer-${a.key}`} onClick={() => onAuth("login")}
            className="fpl-press" style={{ flex: 1, minWidth: 92, display: "inline-flex", alignItems: "center",
              justifyContent: "center", gap: 6, padding: "9px 8px", borderRadius: 10, border: "none",
              background: "transparent", cursor: "pointer", color: t.text2, fontWeight: 700, fontSize: 13 }}>
            <a.Icon size={17} color={a.color} /> {a.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function TogetherShortcuts({ t, onNavigate }) {
  return (
    <div data-testid="fpl-together" style={{ display: "grid",
      gridTemplateColumns: "repeat(6, minmax(0,1fr))", gap: 10 }}>
      {TOGETHER.map((s) => {
        const Icon = SHORTCUT_ICON[s.icon] || Sparkles;
        return (
          <button key={s.key} data-testid={`fpl-together-${s.key}`} onClick={() => onNavigate(s.to)}
            className="fpl-press fpl-lift" style={{ background: t.card, border: `1px solid ${t.border}`,
              borderRadius: 14, boxShadow: t.shadow, cursor: "pointer", padding: "12px 6px",
              display: "flex", flexDirection: "column", alignItems: "center", gap: 7 }}>
            <span style={{ width: 38, height: 38, borderRadius: 12, display: "grid", placeItems: "center",
              background: s.grad }}>
              <Icon size={18} color="#fff" />
            </span>
            <span style={{ fontSize: 11.5, fontWeight: 700, color: t.text, textAlign: "center",
              lineHeight: 1.15 }}>{s.label}</span>
          </button>
        );
      })}
      <style>{`@media (max-width:620px){ [data-testid="fpl-together"]{ grid-template-columns: repeat(3, minmax(0,1fr)) !important; } }`}</style>
    </div>
  );
}

function Tabs({ t, tab, setTab, onAuth }) {
  const Tab = ({ id, label, locked }) => (
    <button data-testid={`fpl-tab-${id}`} onClick={() => (locked ? onAuth("login") : setTab(id))}
      className="fpl-press" style={{ flex: 1, padding: "11px 0", background: "none", border: "none",
        cursor: "pointer", fontWeight: 800, fontSize: 14, color: tab === id ? t.accent : t.text2,
        borderBottom: `2px solid ${tab === id ? t.accent : "transparent"}` }}>
      {label}
    </button>
  );
  return (
    <div style={{ display: "flex", background: t.card, border: `1px solid ${t.border}`,
      borderRadius: 14, overflow: "hidden", boxShadow: t.shadow }}>
      <Tab id="following" label="Following" locked />
      <Tab id="foryou" label="For You" />
    </div>
  );
}

export default function PublicWall({ t, items, loading, hasMore, onLoadMore, onFollow, onAuth, onNavigate }) {
  const [tab, setTab] = useState("foryou");
  return (
    <div data-testid="fpl-wall" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <Composer t={t} onAuth={onAuth} />
      <TogetherShortcuts t={t} onNavigate={onNavigate} />
      <Tabs t={t} tab={tab} setTab={setTab} onAuth={onAuth} />

      <div data-testid="fpl-feed" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        {items.map((item) => (
          <div key={item.id} className="fpl-fade" style={{ position: "relative" }}>
            {item.illustrative && (
              <span data-testid="fpl-illustrative-tag" style={{ position: "absolute", top: 12, right: 12,
                zIndex: 2, fontSize: 9.5, fontWeight: 800, letterSpacing: ".05em", textTransform: "uppercase",
                padding: "3px 8px", borderRadius: 999, background: t.tag, color: t.tagText,
                border: `1px solid ${t.border}` }}>
                Illustrative
              </span>
            )}
            <SocialFeedCard item={item} t={t} onFollow={onFollow} />
          </div>
        ))}
        {loading && (
          <div style={{ display: "grid", placeItems: "center", padding: 24, color: t.muted }}>
            <Loader2 className="animate-spin" size={22} />
          </div>
        )}
        {!loading && hasMore && (
          <button data-testid="fpl-load-more" onClick={onLoadMore} className="fpl-press"
            style={{ padding: "12px", borderRadius: 12, border: `1px solid ${t.border}`, background: t.card,
              color: t.text, fontWeight: 800, fontSize: 14, cursor: "pointer" }}>
            Show more
          </button>
        )}
      </div>
    </div>
  );
}
