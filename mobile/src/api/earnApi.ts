// Phase RWD.1 — Earn Loop client helpers (mobile).
import api from './client';

// Semantic action → expo-router route. Backend stays platform-agnostic.
export const ACTION_ROUTE: Record<string, string> = {
  listen: '/(tabs)/listen',
  daily_code: '/(tabs)/listen',
  trivia: '/(tabs)/trivia',
  predict: '/games/predict',
  game: '/(tabs)/games',
  discover: '/coupons',
  share: '/(tabs)/profile',
  refer: '/(tabs)/profile',
};

export function routeForAction(action?: string): string {
  return (action && ACTION_ROUTE[action]) || '/earn';
}

// Ionicons name for a backend icon key.
export const ICON_MAP: Record<string, string> = {
  radio: 'radio',
  key: 'key',
  brain: 'bulb',
  target: 'locate',
  gamepad: 'game-controller',
  'map-pin': 'location',
  'credit-card': 'card',
  share: 'share-social',
  'user-plus': 'person-add',
  compass: 'compass',
  coins: 'cash',
};

export function ionIcon(key?: string): any {
  return (key && ICON_MAP[key]) || 'sparkles';
}

export interface EarnWay {
  key: string; title: string; subtitle?: string; icon?: string;
  points: number; unit?: string | null; action?: string;
  category?: string; eligible: boolean;
}
export interface EarnMission {
  mission_id: string; title: string; scope: string; icon?: string;
  target: number; progress: number; reward_points: number;
  complete: boolean; claimed: boolean; claimable: boolean;
}
export interface EarnOverview {
  balance: number;
  tier: { name: string; next?: { name: string; min_points: number } | null;
          points_to_next: number; lifetime_points: number };
  daily_goal: { target: number; earned: number; bonus_points: number;
                pct: number; complete: boolean };
  streak: { current: number };
  ways_to_earn: EarnWay[];
  missions: EarnMission[];
}

export async function fetchEarnOverview(): Promise<EarnOverview> {
  const r = await api.get('/me/earn/overview');
  return r.data;
}

export async function claimMission(missionId: string) {
  const r = await api.post(`/me/earn/missions/${missionId}/claim`);
  return r.data;
}
