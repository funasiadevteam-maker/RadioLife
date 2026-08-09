// Phase R.1 — RadioLife design tokens + primitives.  LIGHT MODE by design.
// Every RadioLife screen wraps its outer container in `.rl-root` so tailwind
// utility classes resolve against light-mode colours instead of RadioLife's
// dark-mode CSS variables.
import React from "react";
import { cn } from "@/lib/utils";

// ─── Colour tokens ────────────────────────────────────────────────────
export const RL_COLORS = {
  purple: "#F26B2A",      // brand coral-orange (kept key name for compatibility)
  pink: "#F59E0B",        // amber accent
  ink: "#1C1917",         // warm near-black
  slate: "#57534E",
  muted: "#A8A29E",
  border: "#EFE6DA",
  surface: "#FFFFFF",
  surfaceMuted: "#FBF5EC",
  gradient: "linear-gradient(135deg, #F26B2A 0%, #F59E0B 100%)",
};

// ─── Primitives ──────────────────────────────────────────────────────
export function RLButton({ variant = "primary", size = "md", className = "",
                                          children, ...props }) {
  const base = "inline-flex items-center justify-center gap-2 font-semibold " +
                    "rounded-full transition-all duration-150 " +
                    "focus:outline-none focus:ring-2 focus:ring-orange-400/40 " +
                    "disabled:opacity-50 disabled:pointer-events-none";
  const sizes = {
    sm: "h-9 px-4 text-sm",
    md: "h-11 px-6 text-sm",
    lg: "h-13 px-7 text-base",
  };
  const variants = {
    primary: "text-white shadow-lg shadow-orange-500/25 " +
                  "hover:shadow-xl hover:shadow-orange-500/30 " +
                  "active:scale-[0.98]",
    ghost: "bg-white/60 text-orange-700 border border-orange-200 " +
                "hover:bg-orange-50 hover:border-orange-300",
    outline: "bg-transparent text-orange-700 border-2 border-orange-500 " +
                  "hover:bg-orange-500 hover:text-white",
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
          ? "text-white shadow-md shadow-orange-500/25"
          : "bg-white text-slate-600 border border-slate-200 hover:border-orange-300 hover:text-orange-700",
        className)}
      style={active ? { background: RL_COLORS.gradient } : undefined}
      {...props}>
      {children}
    </button>
  );
}

export function RLBadge({ children, tone = "purple", className = "", ...props }) {
  const tones = {
    purple: "bg-orange-100 text-orange-800",
    pink:    "bg-amber-100 text-amber-800",
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
