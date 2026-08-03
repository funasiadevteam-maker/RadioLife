// Phase R.1 — Points balance card.  Gradient purple→pink surface, big
// tabular-nums number, tier badge, tier progress bar, "View Wallet" link.
import React from "react";
import { Link } from "react-router-dom";
import { Sparkles, ArrowUpRight, ChevronRight } from "lucide-react";
import { RLCard, RLBadge } from "../DesignSystem";

export default function PointsBalanceCard({ balance, tier, showViewWallet = true,
                                                            className = "" }) {
  const tierName = tier?.name || "Listener";
  const nextName = tier?.nextName || "Regular";
  const progress = typeof tier?.progress === "number" ? tier.progress : 0;
  const threshold = tier?.threshold || 100;
  const ptsToNext = Math.max(0, threshold - (tier?.points || 0));
  return (
    <RLCard gradient className={"p-6 relative overflow-hidden " + className}
                data-testid="rl-points-card">
      {/* Decorative sparkles */}
      <div className="absolute -top-6 -right-6 opacity-20 pointer-events-none">
        <Sparkles size={110} strokeWidth={1.25} />
      </div>
      <div className="relative">
        <div className="flex items-center gap-1.5 text-white/85 text-[11px]
                                font-semibold uppercase tracking-widest">
          <Sparkles size={13} />
          <span>Your points</span>
        </div>
        <div className="mt-2 flex items-end gap-3">
          <span className="text-5xl font-black tabular-nums leading-none"
                    data-testid="rl-points-balance">
            {(balance || 0).toLocaleString()}
          </span>
          <span className="text-white/70 text-sm pb-1.5">pts</span>
        </div>
        <div className="mt-3 flex items-center gap-2">
          <RLBadge tone="amber" className="bg-white/25 text-white border border-white/25"
                          data-testid="rl-tier-badge">
            {tierName} Tier
          </RLBadge>
          {showViewWallet && (
            <Link
              to="/wallet"
              data-testid="rl-view-wallet-link"
              className="text-[11px] uppercase tracking-widest font-semibold
                                text-white/90 hover:text-white flex items-center gap-1
                                ml-auto">
              View wallet
              <ArrowUpRight size={12} />
            </Link>
          )}
        </div>
        {/* Progress bar */}
        <div className="mt-4">
          <div className="flex justify-between text-[10px] uppercase tracking-widest
                                    text-white/70 font-semibold mb-1.5">
            <span>{ptsToNext} pts to {nextName}</span>
            <span>{Math.round(progress)}%</span>
          </div>
          <div className="h-2 rounded-full bg-white/20 overflow-hidden">
            <div className="h-full bg-white transition-all duration-500"
                    style={{ width: `${Math.round(progress)}%` }}
                    data-testid="rl-tier-progress" />
          </div>
        </div>
      </div>
    </RLCard>
  );
}
