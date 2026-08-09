// Phase RWD.3 — Premium client helpers (mobile).
import api from './client';

export interface PremiumBenefit { key: string; title: string; category: string; enabled: boolean }
export interface PremiumStatus {
  is_premium: boolean;
  points_multiplier: number;
  trial_days: number;
  monthly_price: number | null;
  annual_price: number | null;
  currency: string;
  benefits: PremiumBenefit[];
  value: { month_points_earned: number; premium_bonus_points_estimate: number; multiplier_active: boolean };
}

export async function fetchPremiumStatus(): Promise<PremiumStatus> {
  const r = await api.get('/me/premium/status');
  return r.data;
}
