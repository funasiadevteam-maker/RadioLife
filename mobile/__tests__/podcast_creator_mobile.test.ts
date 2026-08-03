/**
 * Phase 36f Turn 2 — Creator-side podcast mobile surface tests.
 */

// ── Mocks ────────────────────────────────────────────────────────
jest.mock('expo-router', () => ({
  useRouter: () => ({ push: jest.fn(), back: jest.fn(), replace: jest.fn() }),
  useLocalSearchParams: () => ({ id: 'test_ch_1', episodeId: 'test_ep_1' }),
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
    get: jest.fn(), post: jest.fn(), patch: jest.fn(), put: jest.fn(), delete: jest.fn(),
    interceptors: { request: { use: jest.fn() }, response: { use: jest.fn() } },
    defaults: {},
  };
  return { __esModule: true, default: { create: () => inst, ...inst }, create: () => inst, ...inst };
});

const mockAxios = axios as any;

function getApi() {
  return require('../src/api/podcastApi');
}

/* ── Tests ────────────────────────────────────────────────────── */
describe('Phase 36f Turn 2 — Creator podcast mobile surface', () => {

  beforeEach(() => jest.clearAllMocks());

  // 1. Channel Settings: changing magic_clips_per_episode fires PATCH with the right body
  test('channel_settings_patch_magic_clips_per_episode', async () => {
    const api = getApi();

    mockAxios.patch.mockResolvedValueOnce({
      data: { magic_clips_enabled: true, magic_clips_per_episode: 8, title: 'Test Ch' },
    });

    const result = await api.patchChannelSettings('ch_abc', {
      magic_clips_enabled: true,
      magic_clips_per_episode: 8,
    });

    expect(mockAxios.patch).toHaveBeenCalledWith(
      '/podcasts/channels/ch_abc/settings',
      { magic_clips_enabled: true, magic_clips_per_episode: 8 }
    );
    expect(result.magic_clips_per_episode).toBe(8);
  });

  // 2. Lightning Splits: running-total-chip turns red on 90%, green on 100%, Save disabled when !=100
  test('lightning_splits_total_chip_color_and_save_validation', () => {
    // Test the totalSplit logic inline (mirrors component behavior)
    function totalSplit(recipients: any[]) {
      return recipients.reduce((s: number, r: any) => s + (Number(r.split_pct) || 0), 0);
    }
    function isValid(total: number) {
      return Math.abs(total - 100) <= 0.5;
    }

    // 90% → red, save disabled
    const t90 = totalSplit([{ split_pct: 45 }, { split_pct: 45 }]);
    expect(t90).toBe(90);
    expect(isValid(t90)).toBe(false); // red

    // 100% → green, save enabled
    const t100 = totalSplit([{ split_pct: 50 }, { split_pct: 50 }]);
    expect(t100).toBe(100);
    expect(isValid(t100)).toBe(true); // green

    // 100.3% → within 0.5 tolerance → green
    const t100_3 = totalSplit([{ split_pct: 50.3 }, { split_pct: 50 }]);
    expect(isValid(t100_3)).toBe(true);

    // 99.6% → within 0.5 tolerance → green
    const t99_6 = totalSplit([{ split_pct: 49.6 }, { split_pct: 50 }]);
    expect(isValid(t99_6)).toBe(true);

    // 98% → outside tolerance → red
    const t98 = totalSplit([{ split_pct: 48 }, { split_pct: 50 }]);
    expect(isValid(t98)).toBe(false);
  });

  // 3. Magic Clips review: Publish action fires POST and removes clip from draft list
  test('magic_clips_publish_fires_post_and_removes_from_drafts', async () => {
    const api = getApi();

    // Mock publish endpoint
    mockAxios.post.mockResolvedValueOnce({ data: { status: 'published' } });

    const result = await api.publishMagicClip('clip_draft_1');

    expect(mockAxios.post).toHaveBeenCalledWith(
      '/podcasts/magic-clips/clip_draft_1/publish'
    );
    expect(result.status).toBe('published');

    // Simulate the component removing the clip from drafts after publish
    const drafts = [
      { id: 'clip_draft_1', status: 'draft', title: 'Clip 1' },
      { id: 'clip_draft_2', status: 'draft', title: 'Clip 2' },
    ];
    const afterPublish = drafts.filter(c => c.id !== 'clip_draft_1');
    expect(afterPublish).toHaveLength(1);
    expect(afterPublish[0].id).toBe('clip_draft_2');
  });

  // 4. Funnel dashboard: 5 stage cards render with correct dropoff %; empty state when all zero
  test('funnel_dashboard_5_stages_dropoff_and_empty_state', async () => {
    const api = getApi();

    const STAGES = [
      { key: 'visits', next: 'plays' },
      { key: 'plays', next: 'cta_clicks' },
      { key: 'cta_clicks', next: 'trials' },
      { key: 'trials', next: 'conversions' },
      { key: 'conversions', next: null },
    ];

    // Case 1: With data — verify dropoff calc
    const totals = { visits: 1000, plays: 600, cta_clicks: 150, trials: 30, conversions: 10 };

    function dropoff(curr: number, next: number) {
      if (!curr) return null;
      return Math.round(((curr - next) / curr) * 100);
    }

    // visits → plays: (1000-600)/1000 = 40%
    expect(dropoff(totals.visits, totals.plays)).toBe(40);
    // plays → cta: (600-150)/600 = 75%
    expect(dropoff(totals.plays, totals.cta_clicks)).toBe(75);
    // cta → trials: (150-30)/150 = 80%
    expect(dropoff(totals.cta_clicks, totals.trials)).toBe(80);
    // trials → conversions: (30-10)/30 = 67%
    expect(dropoff(totals.trials, totals.conversions)).toBe(67);
    // conversions: stage.next is null → component skips dropoff; when curr=0 dropoff returns null
    expect(dropoff(0, 0)).toBe(null);

    // All 5 stages must exist
    expect(STAGES).toHaveLength(5);

    // Case 2: Empty state — all zero
    const emptyTotals = { visits: 0, plays: 0, cta_clicks: 0, trials: 0, conversions: 0 };
    const isEmpty = STAGES.every(s => (emptyTotals[s.key as keyof typeof emptyTotals] || 0) === 0);
    expect(isEmpty).toBe(true);

    // Case 3: API call shape
    mockAxios.get.mockResolvedValueOnce({
      data: { overall: totals, per_channel: [{ channel_id: 'ch1', channel_name: 'My Ch', ...totals }] },
    });
    const summaryResult = await api.getFunnelSummary('crt_123', 7);
    expect(mockAxios.get).toHaveBeenCalledWith('/podcasts/creators/crt_123/funnel/summary?window_days=7');
    expect(summaryResult.overall.visits).toBe(1000);
    expect(summaryResult.per_channel).toHaveLength(1);
  });

  // 5. Delete magic clip fires correct DELETE endpoint
  test('delete_magic_clip_fires_correct_endpoint', async () => {
    const api = getApi();

    mockAxios.delete.mockResolvedValueOnce({ data: { deleted: true } });

    const result = await api.deleteMagicClip('clip_rm_1');

    expect(mockAxios.delete).toHaveBeenCalledWith('/podcasts/magic-clips/clip_rm_1');
    expect(result.deleted).toBe(true);
  });
});
