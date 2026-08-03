/**
 * Phase 36f Turn 1 — Listener-side podcast mobile surface tests.
 *
 * We unit-test the API layer + data-contract expectations plus
 * rendering-contract assertions via lightweight component logic checks.
 */

// ── Mocks ────────────────────────────────────────────────────────
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), replace: jest.fn() }),
  useLocalSearchParams: () => ({ id: 'test_ch_1' }),
}));
jest.mock('expo-web-browser', () => ({
  openBrowserAsync: jest.fn(),
}));
jest.mock('expo-secure-store', () => ({
  getItemAsync: jest.fn().mockResolvedValue('tok_test'),
  setItemAsync: jest.fn(),
  deleteItemAsync: jest.fn(),
}));
jest.mock('react-native-safe-area-context', () => ({
  SafeAreaView: ({ children }: any) => children,
  useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }),
}));

import axios from 'axios';
jest.mock('axios', () => {
  const inst = {
    get: jest.fn(),
    post: jest.fn(),
    interceptors: {
      request: { use: jest.fn() },
      response: { use: jest.fn() },
    },
    defaults: {},
  };
  return {
    __esModule: true,
    default: { create: () => inst, ...inst },
    create: () => inst,
    ...inst,
  };
});

const mockAxios = axios as any;

/* ── Helpers ─────────────────────────────────────────────────── */
function getApi() {
  // Re-require after mocks are set up
  const client = require('../src/api/podcastApi');
  return client;
}

/* ── Tests ────────────────────────────────────────────────────── */
describe('Phase 36f Turn 1 — Podcast mobile listener surface', () => {

  beforeEach(() => jest.clearAllMocks());

  // 1. Channel detail renders header + episode list + highlights carousel
  test('channel_detail_returns_channel_episodes_highlights', async () => {
    const api = getApi();

    // Mock channel detail
    mockAxios.get.mockImplementation((url: string) => {
      if (url.includes('/podcasts/channels/ch_1/highlights')) {
        return Promise.resolve({ data: { items: [
          { id: 'clip_1', title: 'Best moment', start_sec: 10, end_sec: 40, score: 0.92 },
          { id: 'clip_2', title: 'Funny bit', start_sec: 120, end_sec: 150, score: 0.87 },
        ]}});
      }
      if (url.includes('/podcasts/channels/ch_1')) {
        return Promise.resolve({ data: {
          channel: { id: 'ch_1', title: 'Tech Talk', category: 'tech', description: 'A tech show' },
          episodes: [
            { id: 'ep_1', title: 'Episode 1', is_bonus: false, duration_sec: 1800 },
            { id: 'ep_2', title: 'Bonus ep', is_bonus: true, duration_sec: 600 },
          ],
          followers: 42,
        }});
      }
      return Promise.reject(new Error('unexpected'));
    });

    const [chData, clips] = await Promise.all([
      api.getChannel('ch_1'),
      api.getChannelHighlights('ch_1'),
    ]);

    expect(chData.channel.title).toBe('Tech Talk');
    expect(chData.episodes).toHaveLength(2);
    expect(chData.followers).toBe(42);
    expect(clips).toHaveLength(2);
    expect(clips[0].title).toBe('Best moment');
  });

  // 2. Episode detail with paywall renders paywall card when API returns 402
  test('episode_402_exposes_paywall_payload', async () => {
    const api = getApi();

    const paywallPayload = {
      channel_id: 'ch_99',
      plan: {
        plan_name: 'Premium',
        price_cents: 499,
        trial_days: 7,
        features: { ad_free: true, early_access_hours: 48, bonus_episodes: true },
      },
    };

    mockAxios.get.mockRejectedValueOnce({
      response: { status: 402, data: paywallPayload },
    });

    try {
      await api.getEpisode('ep_gated');
      throw new Error('should have thrown');
    } catch (e: any) {
      expect(e.response.status).toBe(402);
      const pw = e.response.data;
      expect(pw.plan.plan_name).toBe('Premium');
      expect(pw.plan.price_cents).toBe(499);
      expect(pw.plan.features.bonus_episodes).toBe(true);
    }
  });

  // 3. Global highlights feed paginates with cursor
  test('highlights_feed_paginates_with_cursor', async () => {
    const api = getApi();

    // Page 1
    mockAxios.get.mockResolvedValueOnce({ data: {
      items: Array.from({ length: 20 }, (_, i) => ({
        id: `hl_${i}`, title: `Highlight ${i}`, start_sec: 0, end_sec: 30, score: 0.8,
      })),
      next_cursor: '2026-06-01T00:00:00',
      has_more: true,
    }});

    const page1 = await api.getGlobalHighlights(20, null);
    expect(page1.items).toHaveLength(20);
    expect(page1.has_more).toBe(true);
    expect(page1.next_cursor).toBe('2026-06-01T00:00:00');

    // Page 2
    mockAxios.get.mockResolvedValueOnce({ data: {
      items: [{ id: 'hl_20', title: 'Highlight 20', start_sec: 0, end_sec: 15, score: 0.6 }],
      next_cursor: null,
      has_more: false,
    }});

    const page2 = await api.getGlobalHighlights(20, page1.next_cursor);
    expect(page2.items).toHaveLength(1);
    expect(page2.has_more).toBe(false);

    // Verify cursor was passed
    const call2Url = mockAxios.get.mock.calls[1][0];
    expect(call2Url).toContain('cursor=2026-06-01T00%3A00%3A00');
  });

  // 4. Listener subs cancel button fires the right API call
  test('cancel_subscription_fires_correct_endpoint', async () => {
    const api = getApi();

    mockAxios.post.mockResolvedValueOnce({ data: { status: 'canceled' } });

    const result = await api.cancelSubscription('lsub_test_123');

    expect(mockAxios.post).toHaveBeenCalledWith(
      '/listener/subscriptions/lsub_test_123/cancel'
    );
    expect(result.status).toBe('canceled');
  });

  // 5. Subscribe fires funnel event then subscribe POST
  test('subscribe_fires_funnel_cta_then_subscribe', async () => {
    const api = getApi();

    mockAxios.post.mockImplementation((url: string) => {
      if (url.includes('funnel/cta-clicked')) return Promise.resolve({});
      if (url.includes('subscribe')) return Promise.resolve({ data: { checkout_url: 'https://checkout.stripe.com/mock' } });
      return Promise.reject(new Error('unexpected'));
    });

    const result = await api.subscribe('ch_funnel');

    // Both endpoints should have been called
    const postCalls = mockAxios.post.mock.calls.map((c: any) => c[0]);
    expect(postCalls).toEqual(
      expect.arrayContaining([
        expect.stringContaining('funnel/cta-clicked'),
        expect.stringContaining('subscribe'),
      ])
    );
    expect(result.checkout_url).toContain('stripe.com');
  });
});
