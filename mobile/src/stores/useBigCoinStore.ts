import { create } from 'zustand';
import api from '../api/client';

/* ── BigCoin balance store (Phase 39M.3) ──
   Single source of truth for the listener's BigCoin balance so the Games
   hub chip, the reward modals and the Wallet tab all agree.

   Backend contract: GET /api/bigcoin/me
     -> { balance, lifetime_earned, tier, tier_label, streak_days, ... }

   `addOptimistic` bumps the balance the instant a game reports
   `bigcoin_earned` (the backend already credited it inside
   games_v2 submit_session), then `refresh()` reconciles with the ledger. */

type BigCoinState = {
  balance: number;
  lifetime: number;
  tier: string | null;
  tierLabel: string | null;
  streakDays: number;
  loading: boolean;
  loaded: boolean;
  refresh: () => Promise<number>;
  addOptimistic: (amount: number) => void;
  reset: () => void;
};

export const useBigCoinStore = create<BigCoinState>((set, get) => ({
  balance: 0,
  lifetime: 0,
  tier: null,
  tierLabel: null,
  streakDays: 0,
  loading: false,
  loaded: false,

  addOptimistic: (amount: number) => {
    const n = Number(amount) || 0;
    if (n === 0) return;
    set((s) => ({ balance: s.balance + n, lifetime: s.lifetime + n }));
  },

  refresh: async () => {
    set({ loading: true });
    try {
      const r = await api.get('/bigcoin/me');
      const d = r.data || {};
      const balance = Number(d.balance) || 0;
      set({
        balance,
        lifetime: Number(d.lifetime_earned) || 0,
        tier: d.tier ?? null,
        tierLabel: d.tier_label ?? null,
        streakDays: Number(d.streak_days) || 0,
        loaded: true,
      });
      return balance;
    } catch {
      // Keep whatever we had; never blank the chip on a transient error.
      set({ loaded: true });
      return get().balance;
    } finally {
      set({ loading: false });
    }
  },

  reset: () => set({
    balance: 0, lifetime: 0, tier: null, tierLabel: null,
    streakDays: 0, loaded: false, loading: false,
  }),
}));

export default useBigCoinStore;
