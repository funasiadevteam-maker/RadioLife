import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import {
  Users, Headphones, Radio, ShoppingBag, Gamepad2, Utensils, Coins,
  Sparkles, Compass, MapPin, ChevronRight,
} from "lucide-react";
import { fireV2Event } from "./analytics";
import { useFeaturePrefs } from "@/store/useFeaturePrefs";

const ICONS = {
  users: Users, headphones: Headphones, radio: Radio, "shopping-bag": ShoppingBag,
  "gamepad-2": Gamepad2, utensils: Utensils, coins: Coins, sparkles: Sparkles,
  compass: Compass, "map-pin": MapPin,
};

// Fallback pillar set (used only if the backend payload is unavailable).
const FALLBACK = [
  { key: "social", label: "Social", icon: "users", headline: "Do things together", sub: "Friends, Moments, Clubs & shared experiences.", cta: "Explore Social", to: "/social", featured: true, grad: ["#14b8a6", "#22c55e"] },
  { key: "listen", label: "Listen", icon: "headphones", headline: "Your sound. Your way.", sub: "Live radio, AI radio, podcasts and more.", cta: "Start Listening", to: "/listen", grad: ["#a855f7", "#ec4899"] },
  { key: "live", label: "Live", icon: "radio", headline: "Happening right now", sub: "Live audio, business video and events.", cta: "See What's Live", to: "/social?tab=live", grad: ["#f43f5e", "#a855f7"] },
  { key: "shop", label: "Shop", icon: "shopping-bag", headline: "Discover local favorites", sub: "Products, services and offers near you.", cta: "Shop Now", to: "/shop", grad: ["#ec4899", "#f59e0b"] },
  { key: "play", label: "Play", icon: "gamepad-2", headline: "Play. Compete. Win.", sub: "Trivia, Predict & Win and challenges.", cta: "Start Playing", to: "/play-and-win", grad: ["#8b5cf6", "#6366f1"] },
  { key: "dining", label: "Dining", icon: "utensils", headline: "Your next favorite meal", sub: "Restaurants, Dining Club & social dining.", cta: "Explore Dining", to: "/dining", grad: ["#fb923c", "#ec4899"] },
  { key: "earn", label: "Earn", icon: "coins", headline: "Everything counts", sub: "Earn BigPoints as you listen, play & shop.", cta: "View BigPoints", to: "/wallet", grad: ["#f59e0b", "#f5c563"] },
  { key: "explore", label: "Explore", icon: "sparkles", headline: "More to discover", sub: "Moments, Clubs, Local Pulse & Events.", cta: "Explore FUUSIC", to: "/social", grad: ["#06b6d4", "#3b82f6"] },
];

// "Your FUUSIC World" — the whole ecosystem in one glanceable rail so the
// Home answers "what IS FUUSIC?" in seconds. Social gets visual priority.
export default function FuusicWorldGridV2({ title = "Your FUUSIC World", pillars, social }) {
  const navigate = useNavigate();
  const seen = useRef(false);
  const enabledFeatures = useFeaturePrefs((s) => s.enabled);
  const base = (pillars && pillars.length ? pillars : FALLBACK);
  const items = enabledFeatures
    ? enabledFeatures.map((k) => base.find((p) => p.key === k)).filter(Boolean)
    : base;

  useEffect(() => {
    if (seen.current) return;
    seen.current = true;
    fireV2Event("home_fuusic_world_view");
  }, []);

  const friendsActive = Number(social?.friends_online || social?.friends_listening || 0);
  const liveNow = Number(social?.live_experiences || 0);

  const go = (p) => {
    fireV2Event("home_pillar_click", { kind: p.key, meta: p.to });
    fireV2Event(`home_${p.key}_click`);
    navigate(p.to);
  };

  return (
    <section data-testid="nlv2-fuusic-world">
      <div className="mb-4">
        <h2 className="text-xl font-bold">{title}</h2>
        <p className="text-sm text-[#97a3c2] mt-0.5">Everything you love, one connected experience</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {items.map((p) => {
          const Icon = ICONS[p.icon] || Sparkles;
          const grad = `linear-gradient(135deg, ${(p.grad || ["#a855f7", "#ec4899"])[0]}, ${(p.grad || ["#a855f7", "#ec4899"])[1]})`;
          const isSocial = p.key === "social";
          const featured = !!p.featured;
          return (
            <button
              type="button"
              key={p.key}
              onClick={() => go(p)}
              data-testid={`nlv2-pillar-${p.key}`}
              className={`group relative overflow-hidden text-left nlv2-glass-strong nlv2-card-hover rounded-2xl p-4 sm:p-5 ${featured ? "col-span-2 lg:col-span-2" : ""}`}
              style={featured ? { borderColor: "rgba(45,212,191,0.45)" } : undefined}>
              <div className="absolute -right-8 -top-8 w-32 h-32 rounded-full z-0"
                style={{ background: (p.grad || ["#a855f7"])[0], opacity: 0.16, filter: "blur(26px)" }} />
              <div className="relative z-10 flex items-start gap-3">
                <div className="w-11 h-11 rounded-2xl grid place-items-center shrink-0" style={{ background: grad }}>
                  <Icon size={20} color="#fff" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <div className="text-base font-black truncate">{p.label}</div>
                    {isSocial && friendsActive > 0 && (
                      <span data-testid="nlv2-pillar-social-badge"
                        className="inline-flex items-center gap-1 text-[10px] font-black px-2 py-0.5 rounded-full"
                        style={{ background: "rgba(45,212,191,0.18)", color: "#5eead4" }}>
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                        {friendsActive} active
                      </span>
                    )}
                  </div>
                  <div className="text-[13px] font-semibold text-white/90 mt-0.5 truncate">{p.headline}</div>
                  <div className="text-[12px] text-[#97a3c2] mt-1 leading-snug line-clamp-2">
                    {isSocial && friendsActive > 0
                      ? `${friendsActive} friend${friendsActive === 1 ? "" : "s"} doing things right now — join them.`
                      : p.sub}
                  </div>
                  <div className="mt-3 inline-flex items-center gap-1 text-[12px] font-bold text-white/85">
                    {p.cta} <ChevronRight size={14} className="transition-transform group-hover:translate-x-1" />
                  </div>
                </div>
              </div>
              {featured && liveNow > 0 && (
                <div className="relative z-10 mt-3 text-[11px] font-semibold" style={{ color: "#5eead4" }}>
                  ● {liveNow} live experience{liveNow === 1 ? "" : "s"} happening now
                </div>
              )}
            </button>
          );
        })}
      </div>
    </section>
  );
}
