// Phase R.1 — Bottom nav for RadioLife.  5 items, center Pay button is
// larger and gradient-filled.  Hidden on scroll if the parent applies a
// scroll listener; parent controls visibility.
import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Radio, Compass, Gift, User as UserIcon, CreditCard } from "lucide-react";
import { RL_COLORS } from "../DesignSystem";
import { cn } from "@/lib/utils";

const ITEMS = [
  { key: "listen",    label: "Listen",   Icon: Radio,       to: "/radio" },
  { key: "discover",  label: "Discover", Icon: Compass,     to: "/discover" },
  { key: "pay",        label: "Pay",       Icon: CreditCard, to: "/pay",     center: true },
  { key: "rewards",  label: "Rewards", Icon: Gift,          to: "/wallet" },
  { key: "profile",  label: "Profile",  Icon: UserIcon,   to: "/profile" },
];

export default function BottomNavRadioLife() {
  const { pathname } = useLocation();
  return (
    <nav
      data-testid="rl-bottom-nav"
      className="fixed bottom-0 inset-x-0 z-40 bg-white border-t border-slate-100
                          shadow-[0_-4px_20px_rgba(160,32,240,0.06)]">
      <div className="mx-auto max-w-md h-[72px] grid grid-cols-5 items-center px-2">
        {ITEMS.map((it) => (
          <Item key={it.key} {...it} active={isActive(pathname, it.to)} />
        ))}
      </div>
    </nav>
  );
}

function isActive(pathname, to) {
  if (to === "/") return pathname === "/";
  return pathname === to || pathname.startsWith(to + "/");
}

function Item({ Icon, label, to, active, center }) {
  if (center) {
    return (
      <Link
        to={to}
        data-testid={`rl-nav-pay`}
        aria-label={label}
        className="flex flex-col items-center justify-center">
        <span
          className={cn(
            "w-14 h-14 rounded-full flex items-center justify-center",
            "text-white shadow-lg -mt-6 transition-transform duration-150",
            "hover:scale-105 active:scale-95")}
          style={{ background: RL_COLORS.gradient,
                     boxShadow: "0 10px 24px -6px rgba(236,72,153,0.5)" }}>
          <Icon size={22} />
        </span>
        <span className={cn(
          "text-[10px] mt-1 font-semibold uppercase tracking-wider",
          active ? "text-purple-700" : "text-slate-500"
        )}>{label}</span>
      </Link>
    );
  }
  return (
    <Link
      to={to}
      data-testid={`rl-nav-${label.toLowerCase()}`}
      className={cn(
        "flex flex-col items-center justify-center gap-1 h-full",
        "transition-colors duration-150",
        active ? "text-purple-700" : "text-slate-400 hover:text-purple-500"
      )}>
      <Icon size={22} strokeWidth={active ? 2.2 : 1.75} />
      <span className="text-[10px] font-semibold uppercase tracking-wider">
        {label}
      </span>
    </Link>
  );
}
