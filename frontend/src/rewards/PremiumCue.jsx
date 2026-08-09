// Phase RWD.3 — reusable contextual Premium cue (web).
// Hidden for premium users. `context` tailors the benefit-led message.
import React from "react";
import { Link } from "react-router-dom";
import { Sparkles, ChevronRight } from "lucide-react";
import { usePremiumStatus } from "@/rewards/premiumApi";

const MESSAGES = {
  listen: "Enjoy this station without RadioLife platform audio ads.",
  rewards: "Premium members earn boosted reward points.",
  games: "Premium unlocks extra daily game entries.",
  podcast: "Premium unlocks exclusive & early podcast episodes.",
  ai: "Unlock advanced AI personalization with Premium.",
  default: "Fewer platform interruptions · more AI features · extra rewards",
};

export default function PremiumCue({ context = "default", className = "" }) {
  const { data } = usePremiumStatus();
  if (!data || data.is_premium) return null;

  let msg = MESSAGES[context] || MESSAGES.default;
  if (context === "rewards" && data.points_multiplier > 1) {
    msg = `Premium members earn ${data.points_multiplier}× reward points.`;
  }

  return (
    <Link to="/premium" data-testid={`premium-cue-${context}`}
              className={`flex items-center gap-3 rounded-token-card border
                                border-accent-magenta/20 bg-accent-magenta/[0.06]
                                px-4 py-3 hover:bg-accent-magenta/[0.1]
                                transition-colors duration-150 ${className}`}>
      <Sparkles size={16} className="text-accent-magenta shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold">Get more with Premium</div>
        <div className="text-xs text-text-secondary truncate">{msg}</div>
      </div>
      <ChevronRight size={14} className="text-accent-magenta shrink-0" />
    </Link>
  );
}
