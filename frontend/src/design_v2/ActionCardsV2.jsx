import React from "react";
import { useNavigate } from "react-router-dom";
import { ShoppingBag, Gamepad2, Users, ChevronRight } from "lucide-react";
import { TILE_IMG } from "./tileArt";

const CARDS = [
  {
    key: "shop", label: "Shop", to: "/shop", icon: ShoppingBag,
    copy: "Discover products, local deals and exclusive offers.",
    glow: "rgba(236,72,153,0.22)", ring: "rgba(236,72,153,0.35)",
    grad: "linear-gradient(135deg,#ec4899,#a855f7)",
    art: TILE_IMG["Featured Businesses"],
  },
  {
    key: "play", label: "Play", to: "/play-and-win", icon: Gamepad2,
    copy: "Games, trivia and win BigPoints while you listen.",
    glow: "rgba(139,92,246,0.22)", ring: "rgba(139,92,246,0.35)",
    grad: "linear-gradient(135deg,#8b5cf6,#6366f1)",
    art: TILE_IMG["Sponsored Games"],
  },
  {
    key: "social", label: "Social", to: "/community", icon: Users,
    copy: "Connect with friends, share music and join the community.",
    glow: "rgba(45,212,191,0.20)", ring: "rgba(45,212,191,0.35)",
    grad: "linear-gradient(135deg,#14b8a6,#22c55e)",
    art: TILE_IMG["Groups & Events"],
  },
];

export default function ActionCardsV2() {
  const navigate = useNavigate();
  return (
    <section data-testid="nlv2-actions">
      <div className="mb-4">
        <h2 className="text-xl font-bold">Do More While You Listen</h2>
        <p className="text-sm text-[#97a3c2] mt-0.5">Turn your listening time into more experiences</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {CARDS.map((c) => {
          const Icon = c.icon;
          return (
            <button type="button" key={c.key} onClick={() => navigate(c.to)}
              data-testid={`nlv2-action-${c.key}`}
              className="group nlv2-glass-strong nlv2-card-hover rounded-3xl p-6 text-left relative overflow-hidden"
              style={{ borderColor: c.ring }}>
              {c.art && (
                <img src={c.art} alt="" aria-hidden="true" loading="lazy"
                  className="absolute right-0 top-0 h-full w-1/2 object-cover opacity-40 z-0 transition-transform duration-500 group-hover:scale-105"
                  onError={(e) => { e.currentTarget.style.display = "none"; }} />
              )}
              <div className="absolute inset-0 z-0" style={{ background: "linear-gradient(90deg, #12172b 0%, rgba(18,23,43,0.92) 40%, rgba(18,23,43,0.25) 100%)" }} />
              <div className="absolute -right-8 -top-8 w-40 h-40 rounded-full z-0" style={{ background: c.glow, filter: "blur(24px)" }} />
              <div className="relative z-10">
                <div className="w-12 h-12 rounded-2xl grid place-items-center mb-4" style={{ background: c.grad }}>
                  <Icon size={22} color="#fff" />
                </div>
                <div className="text-xl font-black">{c.label}</div>
                <div className="text-sm text-[#aab4d0] mt-1.5 max-w-[80%]">{c.copy}</div>
                <div className="mt-4 inline-flex items-center gap-1 text-sm font-bold text-white/90">
                  Explore <ChevronRight size={16} className="transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
