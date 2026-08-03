/** Phase 41M.B — Inline fan badge chip.
 *
 * Tiny rounded pill rendered next to a user handle on station feed
 * posts/comments. Hover/tap reveals the badge label + criteria.
 *
 * Usage: <BadgeChip badge={badgeObj} compact /> or <BadgeChip ...
 * variant="full" /> for the My-Badges grid.
 */
import React from "react";
import {
  Headphones, Flame, MessageCircle, Star, Crown,
} from "lucide-react";

const ICONS = {
  headphones:     Headphones,
  flame:          Flame,
  "message-circle": MessageCircle,
  star:           Star,
  crown:          Crown,
};

const TINTS = {
  loyal_listener:   "#22d3ee",
  top_reactor:      "#f59e0b",
  comment_champion: "#a78bfa",
  first_follower:   "#34d399",
  vip:              "#fbbf24",
};

export default function BadgeChip({ badge, variant = "compact" }) {
  if (!badge) return null;
  const Icon = ICONS[badge.icon] || Star;
  const tint = TINTS[badge.badge_type] || "#cbd5e1";

  if (variant === "full") {
    return (
      <div data-testid={`badge-chip-full-${badge.badge_type}`}
           title={badge.criteria_text}
           style={{ display: "flex", alignItems: "center", gap: 10,
                     padding: "8px 12px", borderRadius: 10,
                     background: "rgba(255,255,255,0.04)",
                     border: `1px solid ${tint}33` }}>
        <div style={{ width: 32, height: 32, borderRadius: 8,
                       background: `${tint}22`, color: tint,
                       display: "flex", alignItems: "center",
                       justifyContent: "center" }}>
          <Icon size={16} />
        </div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <span style={{ fontSize: 12, color: "#fff", fontWeight: 600 }}>
            {badge.label}
          </span>
          <span style={{ fontSize: 10, color: "#9aa3af" }}>
            {badge.criteria_text}
          </span>
        </div>
      </div>
    );
  }

  return (
    <span data-testid={`badge-chip-${badge.badge_type}`}
          title={`${badge.label} — ${badge.criteria_text}`}
          style={{ display: "inline-flex", alignItems: "center", gap: 3,
                    padding: "1px 6px", borderRadius: 999,
                    background: `${tint}22`, color: tint,
                    fontSize: 9.5, fontWeight: 600,
                    border: `1px solid ${tint}44`,
                    verticalAlign: "middle",
                    lineHeight: 1.2,
                    marginLeft: 4 }}>
      <Icon size={9} />
      <span>{badge.label}</span>
    </span>
  );
}

export { TINTS as BADGE_TINTS };
