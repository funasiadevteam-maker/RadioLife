# Phase 36f Turn 1 — Listener-Side Podcast Mobile Mirror

**Date**: 2026-06-05
**Commit**: 9f62da4 (base) → Phase 36f Turn 1
**Scope**: Listener-side podcast surface ONLY. Creator-side deferred to Turn 2.

## Screens Added (5 new + 1 tab)

| # | Mobile route | Web equivalent | File |
|---|---|---|---|
| 1 | `(tabs)/podcasts` | `/podcasts` (Podcasts.jsx) | `app/(tabs)/podcasts.tsx` |
| 2 | `podcast/channel/[id]` | `/podcasts/:cid` (Podcasts.jsx::ChannelDetail) | `app/podcast/channel/[id].tsx` |
| 3 | `podcast/episode/[id]` | Episode page (Podcasts.jsx) | `app/podcast/episode/[id].tsx` |
| 4 | `podcast/highlights` | `/highlights` (MagicClipsTab.jsx) | `app/podcast/highlights.tsx` |
| 5 | `podcast/subscriptions` | `/profile` sub list (ListenerSubscriptions.jsx) | `app/podcast/subscriptions.tsx` |

## API Layer

New file: `src/api/podcastApi.ts` — thin wrapper around existing `src/api/client.ts` axios instance.

| Function | Endpoint | Method |
|---|---|---|
| `discoverChannels` | `/api/podcasts/discover` | GET |
| `getChannel` | `/api/podcasts/channels/{cid}` | GET |
| `getChannelHighlights` | `/api/podcasts/channels/{cid}/highlights` | GET |
| `getEpisode` | `/api/podcasts/episodes/{eid}` | GET |
| `getEpisodeMagicClips` | `/api/podcasts/episodes/{eid}/magic-clips` | GET |
| `getEpisodeShoppableCards` | `/api/podcasts/episodes/{eid}/shoppable-cards` | GET |
| `shoppableClickUrl` | `/api/podcasts/shoppable-cards/{cid}/click` | (URL for Linking.openURL) |
| `getGlobalHighlights` | `/api/podcasts/highlights?limit=&cursor=` | GET |
| `subscribe` | `/api/podcasts/channels/{cid}/subscribe` | POST |
| `getListenerSubscriptions` | `/api/listener/subscriptions` | GET |
| `cancelSubscription` | `/api/listener/subscriptions/{id}/cancel` | POST |
| `resumeSubscription` | `/api/listener/subscriptions/{id}/resume` | POST |
| `episodeAudioUrl` | `/api/podcasts/episodes/{eid}/audio.mp3` | (URL for expo-audio) |

Subscribe also fires `POST /api/podcasts/channels/{cid}/funnel/cta-clicked` (best-effort, pre-subscribe).

## Navigation Changes

- `(tabs)/_layout.tsx`: Added "Podcasts" tab with `mic` icon between Wallet and Trivia
- `_layout.tsx`: Registered 4 Stack.Screen routes (`podcast/channel/[id]`, `podcast/episode/[id]`, `podcast/highlights`, `podcast/subscriptions`)

## Key Features per Screen

### Podcasts tab
- Search bar + 15 category filter pills (matching web's category taxonomy)
- 2-column channel grid with cover images, name, category, follower count
- "Browse Highlights" + "My Subscriptions" ghost buttons at bottom

### Channel detail
- Cover image + title + follower count + category
- Subscribe button (opens Stripe Checkout via expo-web-browser)
- "Recent clips" horizontal carousel (from channel highlights endpoint)
- Episode list with BONUS / EARLY badges + duration + play icon

### Episode detail
- Big play button (80×80) centered, pink gradient
- Title + time scrubber (pos/dur)
- Shoppable cards horizontal carousel (image + title + price + Shop CTA → Linking.openURL)
- Magic clips / highlights section
- **Paywall card**: When API returns 402, renders a full-screen paywall overlay with plan name, price, features checklist, "Start 7-day free trial" CTA → opens checkout

### Highlights feed
- FlatList with cursor-based pagination (next_cursor)
- Each card: title, duration, score, channel, summary
- "Load more" footer + auto-load on scroll

### Subscriptions
- List of active/trialing subs with status pills (color-coded: orange=trialing, green=active, red=past_due)
- Cancel / Resume buttons per row
- Empty state with "Browse Podcasts" CTA

## Tests

File: `__tests__/podcast_mobile.test.ts` — 5 tests:
1. `channel_detail_returns_channel_episodes_highlights` — API contract
2. `episode_402_exposes_paywall_payload` — Paywall 402 handling
3. `highlights_feed_paginates_with_cursor` — Cursor pagination
4. `cancel_subscription_fires_correct_endpoint` — Cancel API contract
5. `subscribe_fires_funnel_cta_then_subscribe` — Funnel + subscribe flow

## Test Results

```
PASS __tests__/advertiser_mobile.test.ts (4 tests)
PASS __tests__/podcast_mobile.test.ts (5 tests)
PASS __tests__/audio_background.test.ts (3 tests)
PASS __tests__/trivia_mobile.test.ts (5 tests)
Test Suites: 4 passed, 4 total
Tests:       17 passed, 17 total
```

## Screenshot Evidence

1. **Radio home** — "Podcasts" tab visible in bottom tab bar ✅
2. **Podcasts tab** — Search + category pills + channel grid (2 channels from DB) ✅
3. **Channel detail** — "E2E Show" header + Subscribe btn + 1 episode ✅
4. **Episode detail** — Play button + "E2E Ep1" title ✅
5. **Highlights feed** — 4 real magic clips (Phase36d Test Clip, etc.) with scores ✅
6. **Subscriptions** — Empty state with "Browse Podcasts" CTA ✅

## What Was NOT Touched

- ✅ No changes to `/app/frontend/` (web)
- ✅ No changes to `/app/backend/` (shared backend)
- ✅ No changes to advertiser screens (Phase 18)
- ✅ No changes to trivia, audio service, social passport, commute, channels, lobbies
- ✅ Background audio session unaffected (audio_background tests pass)

## Deferred to Turn 2 (Creator-Side)

- Studio recording screen
- Magic Clips review/edit screen
- Channel Settings screen
- Creator Funnel Dashboard
- Transcript editor
- Lightning Splits management

---

## 2026-06-05 Audit & Verification

Phase 36f Turn 1 initial build + verification.

### Gap Report
- Channel covers render as placeholder icons when no `cover_image_url` exists (expected behavior — matches web fallback)
- Shoppable cards only visible when episode has cards (E2E test episode has none; verified via code path)
- Paywall card verified via unit test (402 contract test passes); not visually testable without a gated episode in demo data

### Existing Flows Verified
- Radio: ✅ renders, channel cards visible
- Trivia: ✅ 5 tests pass
- Audio: ✅ 3 tests pass, background mode configured
- Advertiser: ✅ 4 tests pass
