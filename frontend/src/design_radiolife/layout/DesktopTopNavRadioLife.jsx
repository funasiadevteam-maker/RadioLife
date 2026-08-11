// Desktop-only top nav for RadioLife Shop — turns the app-style surface into
// a real desktop website on laptops (hidden below lg, where the bottom nav rules).
import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Radio, Store, Gift, User as UserIcon, CreditCard, Sparkles } from "lucide-react";
import { useDesignVariantStore } from "@/hooks/useDesignVariant";
import { cn } from "@/lib/utils";

const ITEMS = [
  { label: "Listen", Icon: Radio, to: "/radio" },
  { label: "Shop", Icon: Store, to: "/shop" },
  { label: "Pay", Icon: CreditCard, to: "/pay" },
  { label: "Rewards", Icon: Gift, to: "/wallet" },
  { label: "Profile", Icon: UserIcon, to: "/profile" },
];

const isActive = (p, to) => p === to || p.startsWith(to + "/");

export default function DesktopTopNavRadioLife() {
  const { pathname } = useLocation();
  const setVariant = useDesignVariantStore((s) => s.setVariant);
  return (
    <div
      data-testid="rl-desktop-topnav"
      className="hidden lg:block sticky top-0 z-40 bg-[#0b0b0d]/95 backdrop-blur border-b border-white/10">
      <div className="mx-auto max-w-6xl h-16 px-6 flex items-center gap-6">
        <Link to="/shop" className="flex items-center gap-2 font-black text-lg tracking-tight text-white">
          <span className="w-8 h-8 rounded-xl bg-orange-600 text-white flex items-center justify-center">R</span>
          RadioLife
        </Link>
        <nav className="flex items-center gap-1 flex-1">
          {ITEMS.map((it) => (
            <Link
              key={it.to}
              to={it.to}
              data-testid={`rl-desktopnav-${it.label.toLowerCase()}`}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-full text-sm font-bold transition-colors",
                isActive(pathname, it.to) ? "bg-orange-600 text-white" : "text-zinc-400 hover:bg-white/5 hover:text-white"
              )}>
              <it.Icon size={16} />
              {it.label}
            </Link>
          ))}
        </nav>
        <button
          type="button"
          onClick={() => setVariant("legacy")}
          data-testid="rl-desktop-legacy"
          className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider
                     text-orange-400 hover:bg-white/5 rounded-full px-3 h-8 border border-white/10">
          <Sparkles size={12} /> Legacy
        </button>
      </div>
    </div>
  );
}
