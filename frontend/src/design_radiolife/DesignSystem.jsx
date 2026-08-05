// Phase R.1 — RadioLife design tokens + primitives.  LIGHT MODE by design.
// Every RadioLife screen wraps its outer container in `.rl-root` so tailwind
// utility classes resolve against light-mode colours instead of RadioLife's
// dark-mode CSS variables.
import React from "react";
import { cn } from "@/lib/utils";

// ─── Colour tokens ────────────────────────────────────────────────────
export const RL_COLORS = {
  purple: "#A020F0",
  pink: "#EC4899",
  ink: "#1F1730",         // near-black with purple undertone
  slate: "#4B4257",
  muted: "#8B8397",
  border: "#EFE9F5",
  surface: "#FFFFFF",
  surfaceMuted: "#FAF7FE",
  gradient: "linear-gradient(135deg, #A020F0 0%, #EC4899 100%)",
};

// ─── Primitives ──────────────────────────────────────────────────────
export function RLButton({ variant = "primary", size = "md", className = "",
                                          children, ...props }) {
  const base = "inline-flex items-center justify-center gap-2 font-semibold " +
                    "rounded-full transition-all duration-150 " +
                    "focus:outline-none focus:ring-2 focus:ring-purple-400/40 " +
                    "disabled:opacity-50 disabled:pointer-events-none";
  const sizes = {
    sm: "h-9 px-4 text-sm",
    md: "h-11 px-6 text-sm",
    lg: "h-13 px-7 text-base",
  };
  const variants = {
    primary: "text-white shadow-lg shadow-purple-500/25 " +
                  "hover:shadow-xl hover:shadow-purple-500/30 " +
                  "active:scale-[0.98]",
    ghost: "bg-white/60 text-purple-700 border border-purple-200 " +
                "hover:bg-purple-50 hover:border-purple-300",
    outline: "bg-transparent text-purple-700 border-2 border-purple-500 " +
                  "hover:bg-purple-500 hover:text-white",
  };
  const style = variant === "primary" ? { background: RL_COLORS.gradient } : undefined;
  return (
    <button
      className={cn(base, sizes[size], variants[variant], className)}
      style={style}
      {...props}>
      {children}
    </button>
  );
}

export function RLCard({ className = "", gradient = false, children, ...props }) {
  return (
    <div
      className={cn(
        "rounded-3xl transition-all duration-200",
        gradient ? "text-white shadow-xl shadow-purple-500/20"
                    : "bg-white border border-slate-100 shadow-sm",
        className)}
      style={gradient ? { background: RL_COLORS.gradient } : undefined}
      {...props}>
      {children}
    </div>
  );
}

export function RLChip({ active = false, className = "", children, ...props }) {
  return (
    <button
      type="button"
      className={cn(
        "inline-flex items-center gap-1.5 px-4 py-2 rounded-full text-sm",
        "font-medium transition-all duration-150 whitespace-nowrap",
        active
          ? "text-white shadow-md shadow-purple-500/25"
          : "bg-white text-slate-600 border border-slate-200 hover:border-purple-300 hover:text-purple-700",
        className)}
      style={active ? { background: RL_COLORS.gradient } : undefined}
      {...props}>
      {children}
    </button>
  );
}

export function RLBadge({ children, tone = "purple", className = "", ...props }) {
  const tones = {
    purple: "bg-purple-100 text-purple-800",
    pink:    "bg-pink-100 text-pink-800",
    amber:   "bg-amber-100 text-amber-800",
    emerald: "bg-emerald-100 text-emerald-800",
    slate:   "bg-slate-100 text-slate-700",
  };
  return (
    <span
      className={cn("inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold",
                                    tones[tone] || tones.purple, className)}
      {...props}>
      {children}
    </span>
  );
}

// Utility — safe read of the passport tier for a user (returns name + progress).
export function extractTier(passport) {
  const amb = passport?.ambassador || {};
  return {
    name: amb.level_name || "Listener",
    nextName: amb.next_level_name || "Regular",
    progress: typeof amb.progress_to_next_pct === "number"
                    ? Math.max(0, Math.min(100, amb.progress_to_next_pct))
                    : 0,
    threshold: amb.next_level_threshold || 100,
    points: amb.points || 0,
  };
}
