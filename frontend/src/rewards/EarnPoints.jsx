// Phase RWD.1 — full "Earn Points" screen (/earn).
import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coins, Flame, ChevronRight, Check, Gift, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { Card, Button, LiveDot } from "@/shell/primitives";
import { useEarnOverview, routeForAction, claimMission } from "@/rewards/earnApi";
import { EarnIcon } from "@/rewards/EarnIcon";
import { useReward } from "@/rewards/RewardOverlay";
import PremiumCue from "@/rewards/PremiumCue";

function MissionRow({ m, onClaim, claiming }) {
  const pct = Math.min(100, Math.round((m.progress / m.target) * 100));
  return (
    <div data-testid={`mission-${m.mission_id}`}
              className="rounded-token-md border border-white/[0.06] p-4 space-y-3">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-full grid place-items-center
                              bg-accent-electric/10 shrink-0">
          <EarnIcon name={m.icon} size={16} className="text-accent-electric" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium truncate">{m.title}</div>
          <div className="text-xs text-text-secondary">
            {m.progress}/{m.target} · reward +{m.reward_points} pts
          </div>
        </div>
        {m.claimed ? (
          <span className="flex items-center gap-1 text-xs text-accent-mint font-mono"
                      data-testid={`mission-claimed-${m.mission_id}`}>
            <Check size={13} /> Claimed
          </span>
        ) : m.claimable ? (
          <Button variant="primary" size="sm"
                      data-testid={`mission-claim-${m.mission_id}`}
                      disabled={claiming === m.mission_id}
                      onClick={() => onClaim(m.mission_id)}>
            {claiming === m.mission_id
              ? <Loader2 size={13} className="animate-spin" />
              : <><Gift size={13} /> Claim</>}
          </Button>
        ) : (
          <span className="font-mono text-xs text-text-faint">{pct}%</span>
        )}
      </div>
      <div className="h-1.5 rounded-full overflow-hidden bg-white/[0.06]">
        <div className={`h-full transition-all duration-300 ${
          m.claimed ? "bg-accent-mint" : "bg-accent-electric"
        }`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function EarnPoints() {
  const { data, loading, error, reload } = useEarnOverview();
  const navigate = useNavigate();
  const [claiming, setClaiming] = useState(null);
  const { celebrate } = useReward();

  const onClaim = async (id) => {
    setClaiming(id);
    try {
      const r = await claimMission(id);
      await reload();
      celebrate({ points: r.awarded, title: "Mission complete" });
    } catch (e) {
      toast.error(e?.response?.data?.detail?.code === "already_claimed"
        ? "Already claimed." : "Couldn't claim — try again.");
    } finally {
      setClaiming(null);
    }
  };

  if (error === "unauth") {
    return (
      <div className="max-w-xl mx-auto pt-20 text-center text-text-secondary"
                data-testid="earn-unauth">
        Sign in to start earning points.
      </div>
    );
  }
  if (loading || !data) {
    return (
      <div className="max-w-2xl mx-auto pt-20 text-center text-text-secondary"
                data-testid="earn-loading">
        <Loader2 className="animate-spin inline-block mr-2" size={18} /> Loading rewards…
      </div>
    );
  }

  const ways = data.ways_to_earn || [];
  const daily = (data.missions || []).filter((m) => m.scope === "daily");
  const weekly = (data.missions || []).filter((m) => m.scope === "weekly");
  const goal = data.daily_goal;

  return (
    <div data-testid="earn-root" className="max-w-2xl mx-auto space-y-8 pb-24">
      {/* Balance + tier header */}
      <Card className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
              Your points
            </div>
            <div className="flex items-center gap-2 mt-1">
              <Coins size={26} className="text-accent-gold" />
              <span className="font-display font-bold text-4xl tracking-display-tight
                                      text-accent-gold" data-testid="earn-balance">
                {data.balance.toLocaleString()}
              </span>
            </div>
          </div>
          {data.streak?.current > 0 && (
            <div className="flex items-center gap-1 text-accent-magenta font-mono text-sm"
                      data-testid="earn-streak">
              <Flame size={16} /> {data.streak.current}-day streak
            </div>
          )}
        </div>

        {data.tier && (
          <div data-testid="earn-tier">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-accent-electric font-semibold">{data.tier.name}</span>
              {data.tier.next && (
                <span className="text-text-secondary">
                  {data.tier.points_to_next.toLocaleString()} pts to {data.tier.next.name}
                </span>
              )}
            </div>
            {data.tier.next && (
              <div className="h-1.5 rounded-full overflow-hidden bg-white/[0.06]">
                <div className="h-full bg-accent-electric transition-all duration-300"
                          style={{
                            width: `${Math.min(100, Math.round(
                              (data.tier.lifetime_points /
                                (data.tier.next.min_points || 1)) * 100))}%`,
                          }} />
              </div>
            )}
          </div>
        )}

        {goal && (
          <div data-testid="earn-daily-goal">
            <div className="flex items-center justify-between text-xs mb-1">
              <span className="text-text-secondary">Today&apos;s goal</span>
              <span className="text-text-secondary">{goal.earned}/{goal.target} pts</span>
            </div>
            <div className="h-1.5 rounded-full overflow-hidden bg-white/[0.06]">
              <div className="h-full bg-accent-gold transition-all duration-300"
                        style={{ width: `${goal.pct}%` }} />
            </div>
            {goal.bonus_points > 0 && !goal.complete && (
              <div className="text-[11px] text-text-secondary mt-1">
                Finish for a +{goal.bonus_points} bonus.
              </div>
            )}
          </div>
        )}
      </Card>

      {/* Available now */}
      <PremiumCue context="rewards" />
      <section className="space-y-3" data-testid="earn-available">
        <h2 className="font-display font-bold text-lg tracking-display-tight
                              flex items-center gap-2">
          <LiveDot /> Available now
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {ways.map((w) => (
            <button
              key={w.key}
              type="button"
              data-testid={`earn-way-${w.key}`}
              onClick={() => navigate(routeForAction(w.action))}
              className={`flex items-center gap-3 rounded-token-md border px-3 py-3
                                text-left transition-colors duration-150 ${
                                  w.eligible
                                    ? "border-white/[0.06] hover:border-accent-electric/40 hover:bg-white/[0.03]"
                                    : "border-white/[0.04] opacity-50"
                                }`}
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
      </section>

      {/* Daily missions */}
      {daily.length > 0 && (
        <section className="space-y-3" data-testid="earn-daily-missions">
          <h2 className="font-display font-bold text-lg tracking-display-tight">
            Daily missions
          </h2>
          <div className="space-y-2">
            {daily.map((m) => (
              <MissionRow key={m.mission_id} m={m} onClaim={onClaim} claiming={claiming} />
            ))}
          </div>
        </section>
      )}

      {/* Weekly challenges */}
      {weekly.length > 0 && (
        <section className="space-y-3" data-testid="earn-weekly-missions">
          <h2 className="font-display font-bold text-lg tracking-display-tight">
            Weekly challenges
          </h2>
          <div className="space-y-2">
            {weekly.map((m) => (
              <MissionRow key={m.mission_id} m={m} onClaim={onClaim} claiming={claiming} />
            ))}
          </div>
        </section>
      )}

      <button type="button" data-testid="earn-view-history"
                  onClick={() => navigate("/wallet")}
                  className="flex items-center justify-center gap-1 w-full text-xs
                                    font-semibold text-accent-electric hover:underline">
        View wallet &amp; history <ChevronRight size={13} />
      </button>
    </div>
  );
}
