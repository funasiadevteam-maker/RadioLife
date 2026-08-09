// Phase RWD.1 — "Ways to Earn Today" home card + a contextual Premium teaser.
import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { ChevronRight, Sparkles } from "lucide-react";
import { Card } from "@/shell/primitives";
import { useEarnOverview, routeForAction } from "@/rewards/earnApi";
import { EarnIcon } from "@/rewards/EarnIcon";

export default function WaysToEarnCard() {
  const { data, loading, error } = useEarnOverview();
  const navigate = useNavigate();

  if (error === "unauth") return null;

  const ways = (data?.ways_to_earn || []).slice(0, 5);
  const goal = data?.daily_goal;
  const bonuses = data?.active_bonuses || [];

  return (
    <section data-testid="home-ways-to-earn" className="space-y-3">
      {bonuses.map((b) => (
        <div key={b.window_id} data-testid={`home-bonus-${b.window_id}`}
                  className="flex items-center gap-3 rounded-token-card border
                                    border-accent-gold/30 bg-accent-gold/[0.08] px-4 py-3">
          <Sparkles size={16} className="text-accent-gold shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-semibold">{b.title}</div>
            {b.sponsor_name && (
              <div className="text-xs text-text-secondary truncate">
                Sponsored by {b.sponsor_name}
              </div>
            )}
          </div>
          <span className="font-mono text-xs text-accent-gold">{b.multiplier}×</span>
        </div>
      ))}
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="flex items-center gap-2">
              <Sparkles size={16} className="text-accent-gold" />
              <h2 className="font-display font-bold text-lg tracking-display-tight">
                Ways to Earn Today
              </h2>
            </div>
            {goal && (
              <div className="text-xs text-text-secondary mt-1"
                        data-testid="ways-daily-goal">
                Daily goal · {goal.earned}/{goal.target} pts
                {goal.bonus_points ? ` — hit it for +${goal.bonus_points} bonus` : ""}
              </div>
            )}
          </div>
          <Link to="/earn" data-testid="ways-see-all"
                    className="text-xs font-semibold text-accent-electric hover:underline
                                      flex items-center gap-1 whitespace-nowrap">
            See all <ChevronRight size={13} />
          </Link>
        </div>

        {goal && (
          <div className="h-1.5 rounded-full overflow-hidden bg-white/[0.06]">
            <div className="h-full bg-accent-gold transition-all duration-300"
                      style={{ width: `${goal.pct}%` }} />
          </div>
        )}

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {loading && [0, 1, 2, 3].map((i) => (
            <div key={i} className="h-14 rounded-token-md bg-white/[0.04] animate-pulse" />
          ))}
          {!loading && ways.map((w) => (
            <button
              key={w.key}
              type="button"
              data-testid={`ways-item-${w.key}`}
              onClick={() => navigate(routeForAction(w.action))}
              className="flex items-center gap-3 rounded-token-md border
                                border-white/[0.06] px-3 py-3 text-left
                                hover:border-accent-electric/40 hover:bg-white/[0.03]
                                transition-colors duration-150"
            >
              <div className="w-9 h-9 rounded-full grid place-items-center
                                    bg-accent-electric/10 shrink-0">
                <EarnIcon name={w.icon} size={16} className="text-accent-electric" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium truncate">{w.title}</div>
                <div className="text-xs text-text-secondary truncate">{w.subtitle}</div>
              </div>
              <span className="font-mono text-xs text-accent-gold whitespace-nowrap">
                +{w.points}{w.unit ? ` ${w.unit}` : ""}
              </span>
            </button>
          ))}
        </div>
      </Card>

      {/* Contextual Premium teaser — full Premium cue system lands in a later phase. */}
      <Link
        to="/premium"
        data-testid="home-premium-teaser"
        className="flex items-center gap-3 rounded-token-card border
                          border-accent-magenta/20 bg-accent-magenta/[0.06]
                          px-4 py-3 hover:bg-accent-magenta/[0.1]
                          transition-colors duration-150"
      >
        <Sparkles size={16} className="text-accent-magenta shrink-0" />
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">Get more with Premium</div>
          <div className="text-xs text-text-secondary">
            Fewer platform interruptions · more AI features · extra reward opportunities
          </div>
        </div>
        <ChevronRight size={14} className="text-accent-magenta shrink-0" />
      </Link>
    </section>
  );
}
