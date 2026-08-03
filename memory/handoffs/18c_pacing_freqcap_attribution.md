# Phase 18c — Pacing + Frequency Capping + Attribution + Engagement Push (2026-06-02)

## Highlights
- `services/pacing.py` — date-progress-aware bid weight: ahead (>20%) → ×0.30 throttle, behind (>20%) → ×1.50 boost, on-pace → ×1.00. Takeover campaigns bypass entirely.
- `services/freq_caps.py` — 5-dimension caps (`min_seconds_between` / hourly / daily / per-advertiser-per-week / channel cadence) with stable `reason` strings: `min_interval`, `hourly`, `daily`, `lifetime_weekly`, `channel_cadence`. `ad_serve_events` is the new counter collection mirrored from every `ad_serves` insert.
- Attribution chain — `ad_serve_events.id` flows through to `coupons.attribution_serve_id` / `attribution_campaign_id`. New endpoint `GET /advertiser/{aid}/campaigns/{cid}/attribution` returns `{impressions, coupon_saves, redemptions, checkins, save_rate, redeem_rate, cost_per_save, cost_per_redeem}`.
- `services/engagement_push.py` — 5-min-before-bucket-flip detector with quiet hours (22→07), per-user caps (3/day, ≥90 min between), demo/admin emails excluded by default. Web-push (VAPID) delivery; FCM/APNs **MOCKED**. Admin trigger `POST /api/admin/push/tick-now`.
- `services/hygiene18c.py` — daily disk prune of `storage/streams|segments|tracks` + `static/ad_creatives` older than `HYGIENE_TTL_HOURS` (default 24). Whitelist exception for active `ad_creatives` and any `news_radio_segments` scheduled within next 7 days. Logged to `hygiene_runs`. Admin endpoints `GET /admin/hygiene/last-run` + `POST /admin/hygiene/run-now`.
- Pacing health panel — `GET /admin/advertiser/pacing-health` returns `{ahead, behind}` arrays with spend/time progress + projected end-of-budget. Frontend at `/admin/advertiser/analytics` shows `<PacingHealthPanel />`.
- `pick-debug` now returns `meta.freq_cap_reason` so operators see which cap fired.

## New tests
- Backend `tests/test_phase18c.py` (11 tests): pacing math (ahead / behind / takeover bypass / n_a), freq cap (min_interval / hourly / ok), attribution chain, hygiene prune + whitelist, push exclusion + bucket-flip math.
- Frontend `__tests__/Phase18c.test.jsx` (3 tests): Conversions tab funnel render, Pacing health panel ahead+behind rows, Freq-cap editor 5-field form.

## Live verification
- `GET /admin/advertiser/pacing-health` returned synthetic `BBQ Pit Mega Push` (ahead, spend 65% vs time 20%) and `Karak Slow Burn` (behind, spend 10% vs time 40%).
- `POST /admin/hygiene/run-now?ttl_hours=1&dry_run=true` → would delete 12 files (1.2 MB), 0 errors. After live (`dry_run=false`) run, disk usage on `/app/backend/storage` dropped to ~3 MB and `/app/backend/static/ad_creatives` stayed within whitelist.
- `pick-debug` after a single serve to `heavy_user` returned `meta.freq_cap_reason: "min_interval"` on the immediate follow-up call.
- `POST /admin/push/tick-now` returned `{candidates: 0, sent: 0}` — no opted-in non-demo users in DB yet, which is the correct zero-spam outcome for the QA env.

## Out of scope (deferred)
- GAM/OpenRTB live (18d).
- Apple APNs (MOCKED).
- Stripe Connect transfers (parked).
- Mobile (Expo) mirror — `e1_expo_frontend_dev` handles separately after Phase 18 closes.
- After 18c/18d → Phase 22 Podcast Creator Network (re-prioritized; 19/20/21 deferred; 40 still parked).

## 2026-06-02 — Attribution chain writer fix (POST-VERIFY)
**Defect**: `routes/phase18c.py` `/attribution` reads `coupons.attribution_campaign_id`, but the upstream coupon writers (`routes/ads_public.py` `action_save_coupon` + `routes/local_commerce.py` `commerce_claim_offer`) never persisted `attribution_*` fields → funnel always reported 0 saves.

**Fix**: Both writers now accept `attribution_serve_id` from either
- request body field `attribution_serve_id`, or
- HTTP header `X-Attribution-Serve-Id`

…look up the matching `ad_serve_events` row (queried by either `id` or `serve_id`), and persist `attribution_serve_id` + `attribution_campaign_id` + `attribution_advertiser_id` on the new coupon doc. Missing or unknown serve_ids are a silent no-op (do NOT 4xx) so legacy non-ad coupon flows keep working.

**Live verification (real HTTP, real Mongo, no mocks)**:
```
POST /api/ads/action/save_coupon
  Header: X-Attribution-Serve-Id: serve_curl_test_001
  Body:   {"ad_pod_id":"pod_curl_001","offer_id":"ofr_curl_attr"}
→ {"ok":true,"coupon_id":"cp_3fc656a45b7c4a", ...}

Mongo coupon doc:
  attribution_serve_id      = serve_curl_test_001
  attribution_campaign_id  = cmp_curl_attr
  attribution_advertiser_id = adv_curl_attr

Funnel after one impression + one save:
  impressions = 1
  coupon_saves = 1
```

**New tests** (extend, not duplicate, `tests/test_phase18c.py`):
1. `test_attribution_chain_e2e_save_coupon_persists_campaign_and_advertiser` — body-field path.
2. `test_attribution_chain_e2e_redemption_status_flip_counts_in_funnel` — header path + redemption flip.
3. `test_attribution_chain_save_coupon_without_serve_id_is_silent_noop` — missing serve_id must not 4xx.

**Final counts**: 14/14 in test_phase18c.py, 75/75 across all phase 18 backend tests, 3/3 Phase18c FE tests. No regressions.
