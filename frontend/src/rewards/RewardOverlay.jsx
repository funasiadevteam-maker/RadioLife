// Phase RWD.2 — global post-action reward celebration overlay (web).
// Provides useReward().celebrate({ points, title }) — shows the points
// earned, the fresh balance, and 2 "keep earning" next actions.
import React, { createContext, useContext, useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coins, X, ChevronRight, PartyPopper } from "lucide-react";
import { fetchEarnOverview, routeForAction } from "@/rewards/earnApi";
import { EarnIcon } from "@/rewards/EarnIcon";

const RewardCtx = createContext({ celebrate: () => {} });
export const useReward = () => useContext(RewardCtx);

export function RewardProvider({ children }) {
  const [state, setState] = useState(null); // { points, title, balance, ways }
  const navigate = useNavigate();

  const celebrate = useCallback(async ({ points, title }) => {
    setState({ points, title: title || "Points earned", balance: null, ways: [] });
    try {
      const d = await fetchEarnOverview();
      const ways = (d.ways_to_earn || []).filter((w) => w.eligible).slice(0, 2);
      setState({ points, title: title || "Points earned", balance: d.balance, ways });
    } catch { /* keep the basic celebration even if overview fails */ }
  }, []);

  const close = () => setState(null);

  return (
    <RewardCtx.Provider value={{ celebrate }}>
      {children}
      {state && (
        <div data-testid="reward-overlay"
                  className="fixed inset-0 z-[100] grid place-items-center
                                  bg-black/60 backdrop-blur-sm px-6"
                  onClick={close}>
          <div className="w-full max-w-sm rounded-token-card border border-white/[0.1]
                                  bg-bg-elevated p-6 space-y-5 text-center relative
                                  animate-[rewardpop_.25s_ease-out]"
                    onClick={(e) => e.stopPropagation()}>
            <button type="button" onClick={close} aria-label="Close"
                        data-testid="reward-close"
                        className="absolute right-3 top-3 text-text-secondary hover:text-white">
              <X size={16} />
            </button>

            <div className="flex flex-col items-center gap-2">
              <div className="w-14 h-14 rounded-full grid place-items-center
                                    bg-accent-gold/15">
                <PartyPopper size={26} className="text-accent-gold" />
              </div>
              <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
                {state.title}
              </div>
              <div className="flex items-center gap-2 text-accent-gold"
                        data-testid="reward-points">
                <Coins size={24} />
                <span className="font-display font-bold text-4xl tracking-display-tight">
                  +{state.points}
                </span>
              </div>
              {state.balance != null && (
                <div className="text-sm text-text-secondary" data-testid="reward-balance">
                  New balance · <span className="text-white font-semibold">
                    {state.balance.toLocaleString()}
                  </span>
                </div>
              )}
            </div>

            {state.ways.length > 0 && (
              <div className="space-y-2 text-left">
                <div className="text-[10px] font-mono uppercase tracking-widest
                                      text-text-secondary">Keep earning</div>
                {state.ways.map((w) => (
                  <button key={w.key} type="button"
                              data-testid={`reward-keep-${w.key}`}
                              onClick={() => { close(); navigate(routeForAction(w.action)); }}
                              className="w-full flex items-center gap-3 rounded-token-md
                                              border border-white/[0.06] px-3 py-2
                                              hover:border-accent-electric/40 hover:bg-white/[0.03]
                                              transition-colors duration-150">
                    <EarnIcon name={w.icon} size={15} className="text-accent-electric shrink-0" />
                    <span className="flex-1 text-sm truncate">{w.title}</span>
                    <span className="font-mono text-xs text-accent-gold whitespace-nowrap">
                      +{w.points}{w.unit ? ` ${w.unit}` : ""}
                    </span>
                    <ChevronRight size={13} className="text-text-faint shrink-0" />
                  </button>
                ))}
              </div>
            )}

            <button type="button" onClick={close} data-testid="reward-done"
                        className="w-full rounded-full bg-accent-electric text-bg-base
                                        font-semibold text-sm py-2.5 hover:opacity-90
                                        transition-opacity duration-150">
              Nice!
            </button>
          </div>
        </div>
      )}
    </RewardCtx.Provider>
  );
}
