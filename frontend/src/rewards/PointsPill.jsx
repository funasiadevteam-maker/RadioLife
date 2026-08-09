// Phase RWD.1 — persistent points pill in the top bar.
// Shows the live balance; tapping opens a mini drawer with the top
// "ways to earn right now" + a link to the full Earn screen.
import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Coins, ChevronRight, X } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { fetchEarnOverview, routeForAction } from "@/rewards/earnApi";
import { EarnIcon } from "@/rewards/EarnIcon";

export default function PointsPill() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!user) return;
    let cancel = false;
    fetchEarnOverview().then((d) => { if (!cancel) setData(d); }).catch(() => {});
    return () => { cancel = true; };
  }, [user]);

  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    if (open) document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  if (!user) return null;
  const balance = data?.balance ?? 0;
  const topWays = (data?.ways_to_earn || []).filter((w) => w.eligible).slice(0, 3);

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        data-testid="points-pill"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 h-10 pl-3 pr-3 rounded-full
                          bg-accent-gold/10 border border-accent-gold/30
                          hover:bg-accent-gold/15 transition-colors duration-150"
      >
        <Coins size={16} className="text-accent-gold" />
        <span className="font-mono text-sm text-accent-gold font-semibold"
                    data-testid="points-pill-balance">
          {balance.toLocaleString()}
        </span>
      </button>

      {open && (
        <div
          data-testid="points-pill-drawer"
          className="absolute right-0 mt-2 w-80 z-50 rounded-token-card
                            border border-white/[0.08] bg-bg-elevated shadow-2xl
                            p-4 space-y-3"
        >
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">
              Ways to earn right now
            </div>
            <button type="button" onClick={() => setOpen(false)}
                        aria-label="Close" className="text-text-secondary hover:text-white">
              <X size={14} />
            </button>
          </div>

          {data?.tier && (
            <div className="text-xs text-text-secondary" data-testid="points-pill-tier">
              <span className="text-accent-electric font-semibold">{data.tier.name}</span>
              {data.tier.next && (
                <> · {data.tier.points_to_next.toLocaleString()} pts to {data.tier.next.name}</>
              )}
            </div>
          )}

          <div className="space-y-2">
            {topWays.length === 0 && (
              <div className="text-xs text-text-secondary">You&apos;re all caught up today 🎉</div>
            )}
            {topWays.map((w) => (
              <button
                key={w.key}
                type="button"
                data-testid={`pill-way-${w.key}`}
                onClick={() => { setOpen(false); navigate(routeForAction(w.action)); }}
                className="w-full flex items-center gap-3 rounded-token-md
                                  border border-white/[0.06] px-3 py-2 text-left
                                  hover:border-accent-electric/40 hover:bg-white/[0.03]
                                  transition-colors duration-150"
              >
                <EarnIcon name={w.icon} size={16} className="text-accent-electric shrink-0" />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium truncate">{w.title}</div>
                </div>
                <span className="font-mono text-xs text-accent-gold whitespace-nowrap">
                  +{w.points}{w.unit ? ` ${w.unit}` : ""}
                </span>
                <ChevronRight size={14} className="text-text-faint shrink-0" />
              </button>
            ))}
          </div>

          <Link
            to="/earn"
            data-testid="pill-see-all"
            onClick={() => setOpen(false)}
            className="flex items-center justify-center gap-1 text-xs font-semibold
                              text-accent-electric hover:underline pt-1"
          >
            See all ways to earn <ChevronRight size={13} />
          </Link>
        </div>
      )}
    </div>
  );
}
