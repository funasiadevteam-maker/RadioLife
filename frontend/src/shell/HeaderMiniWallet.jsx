// Classic-B header mini-wallet: one-tap BigPoints. Shows balance + tier +
// points-to-next, top ways to earn, and quick actions (Earn / Use / Open).
// Reuses the existing earn overview API + PointsPill visual language.
import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Coins, ChevronRight, X, Gift, Wallet as WalletIcon, Sparkles } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { fetchEarnOverview, routeForAction } from "@/rewards/earnApi";
import { EarnIcon } from "@/rewards/EarnIcon";

export default function HeaderMiniWallet() {
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
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    if (open) document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  if (!user) return null;
  const balance = data?.balance ?? 0;
  const topWays = (data?.ways_to_earn || []).filter((w) => w.eligible).slice(0, 3);
  const go = (to) => { setOpen(false); navigate(to); };

  return (
    <div className="relative" ref={ref}>
      <button type="button" data-testid="mini-wallet-pill" onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 h-10 pl-3 pr-3.5 rounded-full bg-accent-gold/10
                          border border-accent-gold/30 hover:bg-accent-gold/15 transition-colors duration-150">
        <Coins size={16} className="text-accent-gold" />
        <span className="font-mono text-sm text-accent-gold font-semibold" data-testid="mini-wallet-balance">
          {balance.toLocaleString()}
        </span>
        <span className="hidden lg:inline text-[10px] font-mono uppercase tracking-widest text-accent-gold/70">BP</span>
      </button>

      {open && (
        <div data-testid="mini-wallet-drawer"
          className="absolute right-0 mt-2 w-80 z-50 rounded-token-card border border-white/[0.08]
                            bg-bg-elevated shadow-2xl p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">Mini wallet</div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Close"
              className="text-text-secondary hover:text-white"><X size={14} /></button>
          </div>

          <div className="rounded-token-md border border-accent-gold/25 bg-accent-gold/[0.06] px-3 py-2.5">
            <div className="flex items-center gap-2">
              <Coins size={18} className="text-accent-gold" />
              <span className="font-mono text-2xl font-black text-accent-gold" data-testid="mini-wallet-balance-big">
                {balance.toLocaleString()}
              </span>
              <span className="text-xs text-text-secondary mt-1.5">BigPoints</span>
            </div>
            {data?.tier && (
              <div className="mt-1.5 text-xs text-text-secondary" data-testid="mini-wallet-tier">
                <span className="text-accent-electric font-semibold">{data.tier.name}</span>
                {data.tier.next && (
                  <> · {data.tier.points_to_next?.toLocaleString?.() ?? data.tier.points_to_next} pts to {data.tier.next.name}</>
                )}
              </div>
            )}
          </div>

          {topWays.length > 0 && (
            <div className="space-y-2">
              <div className="text-[10px] font-mono uppercase tracking-widest text-text-secondary">Earn right now</div>
              {topWays.map((w) => (
                <button key={w.key} type="button" data-testid={`mini-wallet-way-${w.key}`}
                  onClick={() => go(routeForAction(w.action))}
                  className="w-full flex items-center gap-3 rounded-token-md border border-white/[0.06]
                                    px-3 py-2 text-left hover:border-accent-electric/40 hover:bg-white/[0.03] transition-colors duration-150">
                  <EarnIcon name={w.icon} size={16} className="text-accent-electric shrink-0" />
                  <div className="min-w-0 flex-1"><div className="text-sm font-medium truncate">{w.title}</div></div>
                  <span className="font-mono text-xs text-accent-gold whitespace-nowrap">+{w.points}{w.unit ? ` ${w.unit}` : ""}</span>
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-3 gap-2 pt-1">
            <button type="button" data-testid="mini-wallet-earn" onClick={() => go("/earn")}
              className="flex flex-col items-center gap-1 rounded-token-md border border-white/[0.08] py-2.5
                                hover:border-accent-electric/40 transition-colors duration-150">
              <Sparkles size={16} className="text-accent-electric" />
              <span className="text-[11px] font-semibold">Earn more</span>
            </button>
            <button type="button" data-testid="mini-wallet-use" onClick={() => go("/wallet")}
              className="flex flex-col items-center gap-1 rounded-token-md border border-white/[0.08] py-2.5
                                hover:border-accent-gold/40 transition-colors duration-150">
              <Gift size={16} className="text-accent-gold" />
              <span className="text-[11px] font-semibold">Use rewards</span>
            </button>
            <button type="button" data-testid="mini-wallet-open" onClick={() => go("/wallet")}
              className="flex flex-col items-center gap-1 rounded-token-md border border-white/[0.08] py-2.5
                                hover:border-white/25 transition-colors duration-150">
              <WalletIcon size={16} className="text-text-primary" />
              <span className="text-[11px] font-semibold">Open wallet</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
