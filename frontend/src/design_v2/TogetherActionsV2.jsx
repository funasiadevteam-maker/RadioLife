import React from "react";
import { useNavigate } from "react-router-dom";
import { Headphones, Gamepad2, ShoppingBag, MapPin, ChevronRight } from "lucide-react";
import { fireV2Event } from "./analytics";

const ICONS = {
  headphones: Headphones, "gamepad-2": Gamepad2, "shopping-bag": ShoppingBag, "map-pin": MapPin,
};

const FALLBACK = [
  { key: "listen", label: "Listen Together", sub: "Sync a station with friends", to: "/social?action=listen", icon: "headphones" },
  { key: "play", label: "Play Together", sub: "Team up on games & trivia", to: "/social?action=play", icon: "gamepad-2" },
  { key: "shop", label: "Shop Together", sub: "Share a group cart", to: "/social?action=shop", icon: "shopping-bag" },
  { key: "go", label: "Go Together", sub: "Plan a night out", to: "/social?action=go", icon: "map-pin" },
];

// One of FUUSIC's clearest differentiators — do things WITH people.
export default function TogetherActionsV2({ title = "Do Something Together", actions }) {
  const navigate = useNavigate();
  const items = (actions && actions.length ? actions : FALLBACK);

  const go = (a) => {
    fireV2Event("home_together_action_click", { kind: a.key, meta: a.to });
    navigate(a.to || "/social");
  };

  return (
    <section data-testid="nlv2-together">
      <div className="mb-4">
        <h2 className="text-xl font-bold">{title}</h2>
        <p className="text-sm text-[#97a3c2] mt-0.5">Listen, play, shop and go out — with your friends</p>
      </div>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        {items.map((a) => {
          const Icon = ICONS[a.icon] || Headphones;
          return (
            <button type="button" key={a.key} onClick={() => go(a)}
              data-testid={`nlv2-together-${a.key}`}
              className="group text-left nlv2-glass nlv2-card-hover rounded-2xl p-5 relative overflow-hidden">
              <div className="absolute -right-6 -bottom-6 w-24 h-24 rounded-full"
                style={{ background: "rgba(168,85,247,0.16)", filter: "blur(20px)" }} />
              <div className="relative z-10">
                <div className="w-11 h-11 rounded-2xl grid place-items-center mb-3"
                  style={{ background: "linear-gradient(135deg,#a855f7,#ec4899)" }}>
                  <Icon size={20} color="#fff" />
                </div>
                <div className="text-base font-black">{a.label}</div>
                <div className="text-[12px] text-[#97a3c2] mt-1">{a.sub}</div>
                <div className="mt-3 inline-flex items-center gap-1 text-[12px] font-bold text-white/85">
                  Start <ChevronRight size={14} className="transition-transform group-hover:translate-x-1" />
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}
