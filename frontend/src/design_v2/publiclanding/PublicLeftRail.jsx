// Left category rail — clean vertical navigation (primary + secondary groups).
import {
  Home, Users, Headphones, ShoppingBag, Gamepad2, Utensils, Coins,
  Calendar, Users2, Moon, Sparkles, Compass,
} from "lucide-react";
import { RAIL_PRIMARY, RAIL_SECONDARY } from "./fplTokens";

const ICON = {
  home: Home, social: Users, listen: Headphones, shop: ShoppingBag, play: Gamepad2,
  dining: Utensils, bigpoints: Coins, events: Calendar, clubs: Users2, dreams: Moon,
  tarot: Sparkles, explore: Compass,
};

function Item({ t, item, active, onNavigate }) {
  const Icon = ICON[item.key] || Compass;
  return (
    <button data-testid={`fpl-rail-${item.key}`} onClick={() => onNavigate(item.to)} className="fpl-press"
      style={{ display: "flex", alignItems: "center", gap: 12, width: "100%", textAlign: "left",
        background: active ? t.railActiveBg : "transparent", border: "none", cursor: "pointer",
        color: active ? t.railActiveText : t.text, fontWeight: active ? 800 : 600, fontSize: 14,
        padding: "10px 12px", borderRadius: 12 }}>
      <Icon size={19} color={active ? t.accent : t.text2} />
      {item.label}
    </button>
  );
}

export default function PublicLeftRail({ t, onNavigate }) {
  return (
    <aside data-testid="fpl-left-rail" className="fpl-left">
      <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {RAIL_PRIMARY.map((i) => (
          <Item key={i.key} t={t} item={i} active={i.key === "home"} onNavigate={onNavigate} />
        ))}
      </nav>
      <div style={{ height: 1, background: t.border, margin: "12px 8px" }} />
      <nav style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        {RAIL_SECONDARY.map((i) => (
          <Item key={i.key} t={t} item={i} active={false} onNavigate={onNavigate} />
        ))}
      </nav>
    </aside>
  );
}
