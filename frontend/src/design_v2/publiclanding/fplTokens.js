// Shared tokens + nav/rail/shortcut config for the FUUSIC public social
// landing. Colors derive from the Social-Feed brand tokens so Light/Dark stay
// identical to the logged-in surface; a few landing-only extras are added.
import { SF_TOKENS } from "../socialfeed/sfTheme";

export function fplTokens(theme) {
  const dark = theme === "dark";
  const sf = SF_TOKENS[dark ? "dark" : "light"];
  return {
    ...sf,
    dark,
    pageBg: dark ? "#070a17" : "#eef1f8",
    navBg: dark ? "rgba(10,13,28,0.82)" : "rgba(255,255,255,0.9)",
    navBorder: dark ? "rgba(139,124,246,0.18)" : "#e3e7f1",
    heroBg: dark
      ? "radial-gradient(120% 130% at 82% 6%, rgba(124,58,237,0.55), transparent 55%), radial-gradient(90% 90% at 98% 90%, rgba(236,72,153,0.35), transparent 60%), linear-gradient(120deg,#0b1030 0%,#180f3a 55%,#2a0f38 100%)"
      : "radial-gradient(120% 130% at 82% 6%, rgba(192,132,252,0.40), transparent 55%), radial-gradient(90% 90% at 98% 90%, rgba(249,168,212,0.45), transparent 60%), linear-gradient(120deg,#efe9ff 0%,#f4ecff 55%,#ffe9f4 100%)",
    railActiveBg: dark ? "rgba(168,85,247,0.22)" : "#efe9ff",
    railActiveText: dark ? "#e9d5ff" : "#7c3aed",
    tag: dark ? "rgba(255,255,255,0.08)" : "#eef0f7",
    tagText: dark ? "#9aa3bf" : "#6b7280",
  };
}

const R = {
  home: "/", social: "/social", listen: "/listen", shop: "/shop",
  play: "/play-and-win", dining: "/dining", bigpoints: "/wallet",
  events: "/social", clubs: "/social", dreams: "/social/dreams",
  tarot: "/social/tarot", explore: "/social", premium: "/pricing",
  business: "/for-business", about: "/about",
};
export const ROUTE_FOR = R;

export const NAV_LINKS = [
  { key: "home", label: "Home", to: R.home },
  { key: "social", label: "Social", to: R.social },
  { key: "listen", label: "Listen", to: R.listen },
  { key: "shop", label: "Shop", to: R.shop },
  { key: "play", label: "Play", to: R.play },
  { key: "dining", label: "Dining", to: R.dining },
];

export const MORE_LINKS = [
  { key: "bigpoints", label: "BigPoints", to: R.bigpoints },
  { key: "events", label: "Events", to: R.events },
  { key: "clubs", label: "Clubs", to: R.clubs },
  { key: "dreams", label: "Dreams", to: R.dreams },
  { key: "tarot", label: "Tarot", to: R.tarot },
  { key: "premium", label: "Premium", to: R.premium },
  { key: "business", label: "For Business", to: R.business },
  { key: "about", label: "About FUUSIC", to: R.about },
];

export const RAIL_PRIMARY = [
  { key: "home", label: "Home", to: R.home },
  { key: "social", label: "Social", to: R.social },
  { key: "listen", label: "Listen", to: R.listen },
  { key: "shop", label: "Shop", to: R.shop },
  { key: "play", label: "Play", to: R.play },
  { key: "dining", label: "Dining Club", to: R.dining },
  { key: "bigpoints", label: "BigPoints", to: R.bigpoints },
];
export const RAIL_SECONDARY = [
  { key: "events", label: "Events", to: R.events },
  { key: "clubs", label: "Clubs", to: R.clubs },
  { key: "dreams", label: "Dreams", to: R.dreams },
  { key: "tarot", label: "Tarot", to: R.tarot },
  { key: "explore", label: "Explore More", to: R.explore },
];

export const TOGETHER = [
  { key: "listen_together", label: "Listen Together", icon: "headphones", to: R.listen, grad: "linear-gradient(135deg,#a855f7,#6d28d9)" },
  { key: "play_together", label: "Play Together", icon: "gamepad", to: R.play, grad: "linear-gradient(135deg,#8b5cf6,#6366f1)" },
  { key: "go_together", label: "Go Together", icon: "pin", to: R.social, grad: "linear-gradient(135deg,#ec4899,#f43f5e)" },
  { key: "shop_together", label: "Shop Together", icon: "bag", to: R.shop, grad: "linear-gradient(135deg,#f472b6,#ec4899)" },
  { key: "share_dream", label: "Share a Dream", icon: "moon", to: R.dreams, grad: "linear-gradient(135deg,#6366f1,#22d3ee)" },
  { key: "tarot", label: "Tarot", icon: "sparkles", to: R.tarot, grad: "linear-gradient(135deg,#a855f7,#ec4899)" },
];
