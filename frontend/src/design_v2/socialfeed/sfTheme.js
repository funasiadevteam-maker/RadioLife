// Scoped design tokens for the FUUSIC Social Feed view (V2 light / V3 dark).
// NOT a color-inversion filter — each theme is authored independently.
export const SF_TOKENS = {
  light: {
    canvas: "#edf0f6", card: "#ffffff", cardAlt: "#f6f7fb",
    border: "#e4e7f0", text: "#101830", text2: "#5c6880", muted: "#8b93a9",
    accent: "#7c3aed", accentText: "#ffffff", accentSoft: "#efe9ff",
    accentGrad: "linear-gradient(135deg,#7c3aed,#ec4899)",
    gold: "#c98a00", goldBg: "linear-gradient(135deg,rgba(245,197,99,.25),rgba(245,158,11,.14))",
    header: "rgba(255,255,255,.92)", chip: "#eef0f7",
    shadow: "0 1px 2px rgba(16,24,48,.06), 0 6px 18px rgba(16,24,48,.05)",
    live: "#e11d6b",
  },
  dark: {
    canvas: "#090b16", card: "#121628", cardAlt: "#0e1221",
    border: "rgba(139,124,246,.16)", text: "#f4f6ff", text2: "#9aa3bf", muted: "#6b7490",
    accent: "#a855f7", accentText: "#ffffff", accentSoft: "rgba(168,85,247,.16)",
    accentGrad: "linear-gradient(135deg,#a855f7,#ec4899)",
    gold: "#ffd700", goldBg: "linear-gradient(135deg,rgba(245,197,99,.18),rgba(245,158,11,.10))",
    header: "rgba(9,11,22,.9)", chip: "rgba(255,255,255,.06)",
    shadow: "0 2px 16px rgba(0,0,0,.45)",
    live: "#ff2d6b",
  },
};

export const sfTokens = (appearance) => SF_TOKENS[appearance === "dark" ? "dark" : "light"];

export function timeAgo(iso) {
  if (!iso) return "";
  try {
    const s = (Date.now() - new Date(iso).getTime()) / 1000;
    if (s < 60) return "now";
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    if (s < 86400) return `${Math.floor(s / 3600)}h`;
    return `${Math.floor(s / 86400)}d`;
  } catch (_e) { return ""; }
}

// Map a feed CTA action to a safe existing route (deep-linking is a later phase).
export function ctaTo(cta) {
  const a = cta?.action, t = cta?.target;
  switch (a) {
    case "open_station": return t ? `/radio?ch=${t}&autoplay=1` : "/listen";
    case "open_live":
    case "open_room": return "/listen";
    case "open_dream": return "/social/dreams";
    case "open_tarot": return "/social/tarot";
    case "open_moment": return "/social";
    case "view_offer": return "/shop";
    case "open_travel": return t ? `/shop/travel/${t}` : "/shop/travel";
    case "open_game": return "/play-and-win";
    case "open_event": return "/social";
    default: return "/social";
  }
}

export const initials = (name) => (name || "?").trim().slice(0, 1).toUpperCase();

export const pillStyle = (t) => ({
  display: "block", width: "100%", textAlign: "center", padding: "10px 14px",
  borderRadius: 999, fontWeight: 800, fontSize: 13, cursor: "pointer",
  color: t.accentText, background: t.accentGrad, border: "none",
});
