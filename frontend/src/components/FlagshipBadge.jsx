// Phase FUN.1 — Small FLAGSHIP pill badge, used in MiniPlayer + FlagshipStrip cards.
// Phase FUN.1-v2 — added compact "PRIORITY" variant for non-flagship Dubai stations.
import { Star, Zap } from "lucide-react";

export default function FlagshipBadge({ compact = false, variant = "flagship", className = "" }) {
  const isPriority = variant === "priority";
  // Compact = tiny pill (mini-player, card corner).
  if (compact) {
    if (isPriority) {
      return (
        <span
          className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full
                                      text-[9px] font-black uppercase tracking-widest
                                      bg-gradient-to-r from-cyan-500 to-blue-500 text-white ${className}`}
          data-testid="priority-badge">
          <Zap className="w-2.5 h-2.5 fill-current" /> PRIO
        </span>
      );
    }
    return (
      <span
        className={`inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded-full
                                    text-[9px] font-black uppercase tracking-widest
                                    bg-gradient-to-r from-purple-500 to-pink-500 text-white ${className}`}
        data-testid="flagship-badge">
        <Star className="w-2.5 h-2.5 fill-current" /> FLAG
      </span>
    );
  }
  if (isPriority) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                                    text-[10px] font-black uppercase tracking-widest
                                    bg-gradient-to-r from-cyan-500 to-blue-500 text-white ${className}`}
        data-testid="priority-badge">
        <Zap className="w-3 h-3 fill-current" /> PRIORITY
      </span>
    );
  }
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full
                                text-[10px] font-black uppercase tracking-widest
                                bg-gradient-to-r from-purple-500 to-pink-500 text-white ${className}`}
      data-testid="flagship-badge">
      <Star className="w-3 h-3 fill-current" /> ★ FLAGSHIP
    </span>
  );
}
