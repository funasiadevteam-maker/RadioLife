import api from './client';

/* ── games_v2 API layer (Phase 39M.3) ──

   IMPORTANT — the legacy Phase 5 endpoints (`/api/games/spin/play`,
   `/api/games/trivia/*`, `/api/games/lyric/*`) were retired in Phase 8a
   and now return HTTP 410 Gone.  The live framework is `/api/games_v2/*`
   with a 3-step flow:

     POST /api/games_v2/campaigns/{campaign_id}/start
       -> { session_id, render_config, ... }
     POST /api/games_v2/sessions/{session_id}/submit
       -> { result: 'win'|'lose', prize, bigcoin_earned, quiz_meta, share_text }
     POST /api/games_v2/sessions/{session_id}/claim_to_wallet
       -> { wallet_item } | { bigcoin_credited }

   BigCoin prizes are auto-credited on submit; `claim_to_wallet` is only
   needed for non-BigCoin prizes (e.g. coupons).                        */

export const HOUSE_CAMPAIGNS = {
  spin: 'cmp_house_spin',
  trivia: 'cmp_house_trivia',
  lyric: 'cmp_house_lyric',
} as const;

export type GamePrize = {
  prize_id: string;
  title: string;
  description?: string | null;
  prize_type: string;
  value_amount?: number | null;
  value_currency?: string | null;
  redemption_method?: string | null;
};

export type SubmitResult = {
  session_id: string;
  result: 'win' | 'lose';
  prize: GamePrize | null;
  bigcoin_earned: number;
  quiz_meta?: Record<string, any>;
  share_text?: string;
};

export type WheelSegment = { label: string; color: string; idx: number };

/** GET /api/games_v2/play_and_win — hub feed. */
export async function fetchPlayAndWin() {
  const r = await api.get('/games_v2/play_and_win');
  const d = r.data || {};
  return {
    unlockedForYou: d.unlocked_for_you || [],
    expiringSoon: d.expiring_soon || [],
    playedHistory: d.played_history || [],
  };
}

/** GET /api/games_v2/campaigns/{id} — title, prizes, compliance, branding. */
export async function fetchCampaign(campaignId: string) {
  const r = await api.get(`/games_v2/campaigns/${campaignId}`);
  return r.data;
}

/** POST /api/games_v2/campaigns/{id}/start — creates a session. */
export async function startSession(campaignId: string, extra: Record<string, any> = {}) {
  const r = await api.post(`/games_v2/campaigns/${campaignId}/start`, {
    client_seed: `c_${Math.random().toString(36).slice(2, 12)}`,
    source_context: { surface: 'mobile_games' },
    ...extra,
  });
  return r.data;
}

/** POST /api/games_v2/sessions/{id}/submit — server resolves the prize. */
export async function submitSession(
  sessionId: string,
  payload: Record<string, any> = {},
): Promise<SubmitResult> {
  const r = await api.post(`/games_v2/sessions/${sessionId}/submit`, payload);
  return r.data;
}

/** POST /api/games_v2/sessions/{id}/claim_to_wallet — non-BigCoin prizes. */
export async function claimToWallet(sessionId: string) {
  const r = await api.post(`/games_v2/sessions/${sessionId}/claim_to_wallet`);
  return r.data;
}

/* ── Error normalisation ──
   FastAPI `detail` is sometimes a plain string and sometimes an object
   (`{code, message}` for 503, `{error, commute_id}` for 423).  Collapse
   both shapes into a listener-friendly title/message pair. */

export type GameError = {
  code: string;
  title: string;
  message: string;
  /** true when retrying later could plausibly succeed */
  retryable: boolean;
};

export function normalizeGameError(e: any): GameError {
  const status = e?.response?.status;
  const detail = e?.response?.data?.detail;
  const code: string =
    (typeof detail === 'string' && detail) ||
    detail?.code ||
    detail?.error ||
    `http_${status || 'unknown'}`;
  const serverMsg = typeof detail === 'object' ? detail?.message : undefined;

  const map: Record<string, { title: string; message: string; retryable: boolean }> = {
    driving_mode_active: {
      title: 'Driving mode is on',
      message: 'For your safety, games are paused while you are driving. Turn driving mode off to play.',
      retryable: true,
    },
    no_questions_available: {
      title: 'Getting questions ready',
      message: serverMsg || 'Questions are still being prepared for this game — please check back soon.',
      retryable: true,
    },
    max_per_user_reached: {
      title: 'You have played this one',
      message: 'You have used all your plays for this game. Try another game or come back later.',
      retryable: false,
    },
    rate_limited: {
      title: 'Slow down a moment',
      message: 'That is a lot of plays in one go. Take a short break and try again.',
      retryable: true,
    },
    campaign_ended: {
      title: 'This game has ended',
      message: 'This game is no longer running. Check the Games hub for what is live now.',
      retryable: false,
    },
    campaign_not_started: {
      title: 'Not started yet',
      message: 'This game has not opened yet. Check back a little later.',
      retryable: true,
    },
    campaign_not_found: {
      title: 'Game unavailable',
      message: 'We could not find this game. It may have been removed.',
      retryable: false,
    },
    not_unlocked: {
      title: 'Locked',
      message: 'You need to unlock this game before you can play it.',
      retryable: false,
    },
    geo_not_eligible: {
      title: 'Not available here',
      message: 'This game is not available in your region.',
      retryable: false,
    },
    age_not_confirmed: {
      title: 'Confirm your age',
      message: 'Please confirm your age to play this game.',
      retryable: false,
    },
    age_below_minimum: {
      title: 'Not eligible',
      message: 'You do not meet the minimum age for this game.',
      retryable: false,
    },
    lead_form_required: {
      title: 'One quick step',
      message: 'This sponsor needs a few details before you can play.',
      retryable: false,
    },
  };

  if (map[code]) return { code, ...map[code] };

  // Retired Phase 5 endpoints answer 410 with a `moved_to` hint.
  if (status === 410) {
    return {
      code: 'endpoint_retired',
      title: 'Game moved',
      message: 'This game has moved to a new version. Please update the app.',
      retryable: false,
    };
  }
  if (status === 401) {
    return {
      code: 'unauthorized',
      title: 'Please sign in',
      message: 'Sign in to play and collect BigCoin.',
      retryable: false,
    };
  }
  return {
    code,
    title: 'Something went wrong',
    message: serverMsg || (typeof detail === 'string' ? detail : 'Could not load this game. Please try again.'),
    retryable: true,
  };
}

/** Map a won prize back onto a visual wheel segment index.
 *  The server never tells us which wedge to land on (the wheel is purely
 *  cosmetic), so we match on the prize title, then fall back to a
 *  type-based match (coupon -> the wedge whose label mentions a coupon). */
export function resolveWheelIndex(
  segments: WheelSegment[],
  prize: GamePrize | null,
): number {
  if (!segments.length) return 0;
  if (!prize) {
    const miss = segments.findIndex((s) => /no luck|try again|nothing|better luck/i.test(s.label || ''));
    return miss >= 0 ? miss : 0;
  }
  const title = (prize.title || '').trim().toLowerCase();

  const exact = segments.findIndex((s) => (s.label || '').trim().toLowerCase() === title);
  if (exact >= 0) return exact;

  // "5 BigCoin" wedge vs "5 BigCoin (correct)" prize, etc.
  const amount = Number(prize.value_amount) || 0;
  if (prize.prize_type === 'bigcoin' && amount > 0) {
    const byAmount = segments.findIndex((s) => {
      const m = (s.label || '').match(/\d+/);
      return !!m && Number(m[0]) === amount && /coin|bc/i.test(s.label || '');
    });
    if (byAmount >= 0) return byAmount;
  }
  if (prize.prize_type === 'coupon' || prize.prize_type === 'offer') {
    const byCoupon = segments.findIndex((s) => /coupon|offer|voucher|sponsor/i.test(s.label || ''));
    if (byCoupon >= 0) return byCoupon;
  }
  const partial = segments.findIndex((s) => {
    const l = (s.label || '').trim().toLowerCase();
    return !!l && (title.includes(l) || l.includes(title));
  });
  return partial >= 0 ? partial : 0;
}
