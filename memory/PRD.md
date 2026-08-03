# BigFM — PRD (Phase H v1 · Commute Mode MVP · 2026-07-24)

## Original problem statement (this dispatch)
Phase H v1 (Commute Mode MVP): a logged-in listener enters a destination,
sees a real Google Map with route polyline, ETA, traffic, and gets a
list of route-relevant offers/coupons matched from existing collections.
Backed by real Google Maps Platform APIs (Routes, Places New, Geocoding,
Weather) — no mocks.

## Prior dispatch (kept for context)
Combined Dispatch (UX.1 · Phase I · Phase F-2 · Mailgun Webhook) — shipped
2026-06-19.  Followed by Phase Π (production readiness), Phase Ω (K8s
deploy hardening), Phase Π+2/+3/+3.1/+4/+4.1 (asset migration, marketing
image wiring, ffmpeg pipeline + LiveRadioStation player unification).

## Original problem statement (Combined Dispatch)
Ship Combined Dispatch — UX.1 (AI Trivia topic auto-start), Phase I (Business
Redemption Portal + Ad Buying), Phase F-2 (Ledger Reader Flip), and Mailgun
Webhook Handler. Phase H (Commute Mode Deep Features) is BLOCKED pending
Google API keys.

## Product summary
BigFM is a mature AI-powered radio + rewards + local-commerce platform (FastAPI
+ React + MongoDB). Combined Dispatch lands four parallel work items that
sharpen monetisation (business portal + ad buys), unify accounting (ledger
reader flip), close the loop on transactional email (Mailgun webhook), and
remove friction in the trivia funnel (one-click topic start).

## User personas
- **Listener** — discovers radio + trivia + local offers, earns points.
- **Business owner** — registers storefront, redeems coupons at counter, buys
  banner inventory.
- **Advertiser** — runs self-serve banner / Predict & Win campaigns.
- **Admin** — full visibility on points ledger parity, mail funnel, mod queue.

## Core requirements satisfied this dispatch
1. **UX.1 Trivia auto-start** — clicking a topic card navigates immediately
   to `/trivia/play?cat=<id>` with router-state passthrough of topic name +
   icon; no interstitial confirmation step.
2. **Phase I Business Redemption Portal**
   - 9 new backend endpoints under `/api/business/*`.
   - 6 new frontend pages under `/business/{login,register,redeem,campaigns,ads/buy}`
     plus the index dashboard at `/business`.
   - 4-digit PIN (bcrypt-hashed) gates redemption.  Successful redemption
     awards customer +20 BC via `PointsService.award(source="coupon_redeemed",
     idempotency_key=...)`.
3. **Phase F-2 Ledger Reader Flip**
   - `PointsService.award` no longer back-writes to `users.bigcoin_balance`
     by default; gated behind `BIGCOIN_LEGACY_DUAL_WRITE=1` for rollback.
   - All readers (`/api/bigcoin/me`, admin analytics liability aggregate,
     referral-completion idempotent path) flipped to PointsService.get_balance.
   - New admin endpoint `GET /api/admin/points/parity-check` reports drift.
   - Reconcile script froze legacy field — last run: scanned=1277 matched=1276
     drift=0.
4. **Mailgun Webhook Handler**
   - Public `POST /api/webhooks/mailgun/events` with HMAC-SHA256(timestamp +
     token) verify (DEV escape hatch via `MAILGUN_WEBHOOK_VERIFY_SIGNATURE=0`).
   - Persists `mail_events`, cross-links `referral_invites` by message_id,
     auto-suppresses bounces/complaints/unsubs.
   - Admin endpoints: `/api/admin/mail/events`, `/api/admin/mail/funnel`.

## Architecture tasks completed
- Backend routers mounted: `business_portal`, `f2_mailgun_webhook`.
- Frontend routing: 6 static `/business/*` routes inserted before dynamic
  `/business/:slug` so the existing PublicBusiness page still handles
  arbitrary public slugs.
- Reconcile script + parity-check endpoint surface drift continuously.
- Memory: `/app/memory/CURRENT_STATE.md` and `test_credentials.md` updated.

## What's been implemented (historical)
- **2026-06-19 — Combined Dispatch (UX.1 / Phase I / Phase F-2 / Mailgun
  Webhook)** — this turn.
- 2026-06-18 — Phase H'.5 player glue + admin AI-RJ cache stats.
- 2026-06-18 — Phase H' ElevenLabs TTS live (persona samples, news radio,
  AI-RJ segment cache).
- 2026-06-18 — Phase 42-E2.5 Mailgun LIVE for invite-a-friend.
- 2026-06-18 — Phase 42-E2 home redesign + universal share + MediaSession.
- 2026-06-18 — Phase 42-E1 banner ads + Predict & Win self-serve.
- 2026-06-18 — Phase F-1 unified points engine (ledger + dual-write).
- Previous phases — see `/app/memory/CURRENT_STATE.md` historical sections.

## Prioritized backlog
**P0 (blocked, waiting on user)**
- **Phase H** Commute Mode Deep Features — awaiting `GOOGLE_ROUTES_API_KEY`,
  `GOOGLE_PLACES_API_KEY`, `GOOGLE_WEATHER_API_KEY`, and frontend
  `REACT_APP_GOOGLE_MAPS_API_KEY`.  DO NOT START until keys land.
- **Mailgun webhook signing key** — flip `MAILGUN_WEBHOOK_VERIFY_SIGNATURE=1`
  once `MAILGUN_WEBHOOK_SIGNING_KEY` is provided.

**P1 (next dispatch candidates)**
- Real Stripe Checkout for Phase I `/business/ads/buy` + Predict & Win
  self-serve.
- Business profile verification flow (admin one-click verify + email).
- Bulk coupon-issuance UI for business owners.
- Cosmetic: fix React `key prop spread` warning + nested button hydration
  warning on `/business/login`.

**P2 (deferred)**
- Phase G OpenRTB (real SSP fill beyond mocked house creatives).
- Voice cloning per business owner.
- Mobile/Expo mirror of business portal.

## Next tasks (immediate)
1. User unblocks Phase H by providing Google API keys → kick off H.1-H.4.
2. User provides Mailgun signing key → flip env flag + rerun webhook smoke.
3. (Optional) Wire real Stripe Checkout for ads buy + Predict & Win.

## Test fixtures
- `admin@bigfm.dubai` / `AdminPass123!` — admin role
- `test@bigfm.dubai` / `TestUser123!` — creator + advertiser + **business
  (Karak Cafe QA fixture, biz_qa_e3_karak, PIN 4242)**
- `demo@bigfm.dubai` / `DemoPass123!` — consumer, free tier
- `predictest@bigfm.dubai` / `PredictTest123!` — Predict & Win E2 fixture
- `freetest@bigfm.dubai` / `FreeTest123!` — pristine free tier
- `advertest@bigfm.dubai` / `AdvTest123!` — advertiser premium
- `premiumtest@bigfm.dubai` / `PremiumTest123!` — premium consumer

## Health
- Backend booted clean; all routes 200.
- Frontend webpack compiled with 6 new pages, no lint errors.
- Parity check: 0 drift across 1277 users.
- Mailgun webhook DEV signature-skip is loud (warning log fires on every hit).
- 14/14 backend tests pass (iteration_10.json).

## Phase FLAGADMIN.1 — Flagship CRUD + Pre-roll Parity (2026-07-27) — SHIPPED
- Added POST/PATCH/DELETE + validate-stream + audit endpoints in
  `/app/backend/routes/flagship_stations.py`. All admin-only.
- Added `preroll_enabled` gate to `/api/live-radio/preroll/request`
  (default `true`; only explicit `false` disables). Confirmed NO
  `is_flagship` bypass anywhere in the preroll pipeline.
- New `station_admin_audit` Mongo collection captures create/update/
  soft_delete/hard_delete rows with before-snapshots.
- Rewrote `/app/frontend/src/pages/admin/AdminFlagshipStations.jsx`
  with FlagshipFormModal + FlagshipDeleteModal + PrerollToggle.
  Type-slug-to-confirm gate on hard delete.
- Backend: 17/17 tests PASS (iteration_17.json). Frontend Playwright
  95%. Zero critical issues.


## Phase AD.11 — Banner Ad Buying + 7-Zone Placement (2026-07-27) — SHIPPED
- Backend: `banner_campaigns` + `banner_impressions` + `banner_clicks` collections; auction (priority + CPM) at `GET /api/banner/serve?zone=…`. Impressions billed via `POST /api/banner/impression` with (session, banner, zone) 5-min dedup, wallet debit + AD.2-style split via `payment_transactions_v2`, and NEW session-per-zone frequency cap of 3.
- Fix during hardening: `stripe_payment_intent_id=tx_id` sentinel on AD.11 ledger rows to sidestep the pre-existing unique-index null collision on `payment_transactions_v2`.
- Frontend: `<BannerZoneSlot zone="…" />` mounted in ALL 7 zones —
  landing_hero (RadioHome), browse_row (RadioBrowse), station_detail (LiveRadioStation), now_playing (LiveRadioStation footer), wallet (Wallet.js + WalletV2), games (PredictWin), bottom_bar (MiniPlayer). Null-render when auction empty; `data-ad-slot="ad11-{zone}"` attribute for analytics; impression + click POSTs wrapped in `.catch()` for ad-block resilience.
- New advertiser dashboard: `/advertiser/dashboard/banner-campaigns` with 5-step wizard (identity → zones+creative → targeting → budget+CPM → review). Nav testid `advertiser-nav-banner-campaigns`.
- Bundled: Admin nav badge counts poll `/api/admin/nav-counts` every 60s with visibility-hidden pause. Cookie banner suppressed on `/admin/*`.
- Tests: 8/8 backend (iteration_25.json). Frontend UI verified (iteration_24.json).

## Phase AD.12a — In-App Notification Ads + Weekly Digest (2026-07-27) — SHIPPED
- Backend: `notification_campaigns` + `notification_deliveries` collections; 9 endpoints (create/patch/upload/publish/list/analytics + inbox/open/click/dismiss). Idempotent per-user-per-campaign billing via AD.2 rails; wallet-drain auto-pause. ADMOD.1 approval reusing `ad_type='notification'`.
- **Push channel deferred permanently** per user decision — enum value kept in model; `publish` returns `push_channel_not_enabled` for `channel='push'|'both'`. Wizard visibly disables the push option.
- **CPD by category hints** in `/api/ad-pricing-hints` — F&B 8¢, Retail 12¢, Entertainment/Nightlife 15¢, Health/Fitness 10¢, Services 10¢, Default 10¢. Shown as tooltip only; no auto-fill (mirrors AD.4 CPS pattern).
- Frontend: 5-step wizard at `/advertiser/dashboard/notification-campaigns`; enhanced `<NotificationBell />` merges legacy station notifications + AD.12 sponsored deliveries with "Sponsored" chips; full-page `/notifications` feed.
- **Bundled — Weekly Advertiser Performance Digest**: Monday 09:00 UTC scheduler aggregates last 7 days across AD.1/AD.4/AD.11/AD.12/PG.1 (spend, impressions, CTR, top creatives, zone perf, rule-based recommendations). HTML template at `/app/backend/templates/advertiser_weekly_digest.html`. Admin manual trigger + advertiser opt-out (default ON via `email_weekly_digest` field). Mailgun live-verified during smoke.
- Tests: 25/25 backend PASS + frontend fully verified (iteration_26.json). Zero regressions to AD.4, ADMOD.1, AD.11, ADMIN.NAV.1.

## Phase AD.7 — Scan-to-Pay at Partner Merchants (2026-07-27) — SHIPPED
- Backend: `scan_to_pay_transactions` + `scan_to_pay_qr_tokens` collections; 12 endpoints (merchant QR generate, QR resolve, quote, authorize, capture, refund, user history, merchant transactions, merchant settings GET+PATCH, admin analytics). Ephemeral 60s QR tokens; Stripe Connect destination charge with `application_fee_amount` from SC.3 commission engine; points debit/earn via F-1 unified points ledger. Refund reverses BOTH card (with `reverse_transfer=true`) and points (both redeemed AND earned). Idempotent capture + refund.
- Points math: 1 pt == 1¢ on redemption; earn = `int(card_cents / 100 * points_per_dollar)`. Redemption capped at merchant's `max_points_redemption_pct` (default 50%). Verified: 800 pts requested → 500 pts clamped for $10 bill @ 50% cap.
- Frontend: `/scan` camera scanner + manual token entry, `/scan-to-pay/:token` checkout with points slider + tip picker + Stripe test card, `/merchant/:merchantId/scan-to-pay` cashier terminal + settings + transactions table.
- **Bundled — Notification Trigger Recipes**: `GET /api/notification-trigger-recipes` returns 10 pre-baked recipes (coupon_saved, coupon_expiring_24h, podcast_completed, station_played_5x, wallet_top_up, first_login, flagship_played_first_time, predict_win_correct, merchant_visit_nearby, game_win_high_value). Wizard step 3 dropdown replaces free-text `trigger_type` (custom escape hatch remains). `dispatch_event()` wired into `/api/ads/action/save_coupon` — silent-on-error so upstream flows never break.
- Tests: 16/16 backend PASS + full frontend live-verified (iteration_27.json). Zero regressions across AD.4/AD.11/AD.12a/ADMOD.1/SC.x/MER.x/ADMIN.NAV.1. POC uses hard-coded `pm_card_visa` in checkout — full Stripe Elements integration is a follow-up.

## Phase AD.3 — Advertiser Predict & Win Sponsorship (2026-07-27) — SHIPPED
- Backend: `predict_win_sponsorships` + `predict_win_sponsorship_events` collections; 10 endpoints (available-parents, CRUD, brand-asset upload, publish, ADMOD.1 mint, admin set_status, auction endpoint, impression billing, analytics). Auction picks 1 sponsor per view weighted by advertiser priority_score_boost DESC, CPE/CPI DESC, random tiebreaker. Per-user idempotent billing (unique index on user_id+sponsorship_id+event_type); wallet-drain auto-pause; race-safe compensation on duplicate insert.
- Pricing: default CPE 20¢, CPI 5¢; high-volume 35¢ CPE / 10¢ CPI; niche 10¢ / 3¢. Exposed via `pw_sponsorship_tiers` in `/api/ad-pricing-hints`.
- ADMOD.1: new `ad_type='advertiser_pw_sponsorship'` wired to `predict_win_sponsorships` target table + snapshot builder (distinct from PW-M's `sponsored_predict_win` for merchant-branded activations).
- Frontend: 5-step wizard at `/advertiser/dashboard/predict-win-sponsorships` (pick parent → brand identity + asset → pricing model + CPE/CPI → budget + targeting → preview + submit). New `<PredictWinSponsorBadge>` component with 3 variants (card corner chip / detail brand block / win-screen powered-by strip) — mounted in PredictWin.jsx ActiveCard + EnterModal.
- **Bundled — Trigger recipe upstream wiring**: `coupon_saved` (in `ads_public.action_save_coupon`) and `predict_win_correct` (in `predict_win_award_pipeline._deliver_prize`) are LIVE. Remaining 8 recipes documented as TODO in `notification_trigger_dispatcher.py` docstring per user directive (don't build missing infra).
- Tests: 27/27 backend PASS (`test_ad3_pw_sponsorships.py`), advertiser dashboard + wizard step 1 + card badge + detail modal all live-verified in browser. Split-the-bill enhancement deferred to AD.7.1 as planned.


## Phase AD.8 — Daily Code Claim in Now Playing + Auction Transparency (2026-07-27) — SHIPPED
- Backend: `daily_codes` + `daily_code_claims` collections. 5 endpoints — `GET /api/daily-code/current` (anonymous-friendly via `current_user_optional`), `POST /api/daily-code/claim` (auth'd, 409 on double-claim via unique index user+code), `GET /api/user/daily-code/history`, `POST /api/admin/daily-codes` (seed future code, 400 on duplicate date), `PATCH /api/admin/daily-codes/{id}` (edit before window opens). Streak ladder: 1x @ 1d · 1.2x @ 3d · 1.5x @ 7d · 2x @ 14+d (capped 2x). Yesterday-check gates streak continuation; miss-a-day → resets to 1. Hourly scheduler idempotently ensures today's code (60 min drift acceptable from mid-day boots).
- Frontend: `<DailyCodeWidget />` mounted in `LiveRadioStation.jsx:412` (order: `BannerZoneSlot zone="station_detail"` → widget). Anonymous users see "sign in to claim" nudge; auth'd see the 6-char code, streak flame + day count, and multiplier preview. Post-claim confetti + already_claimed disabled state. Dual-variant support via `useDesignVariant()` (legacy dark + radiolife light).
- **Bundled — Auction Transparency Panel**: `auction_events` collection with 30-day TTL. Fire-and-forget `log_auction_result` hook from AD.11/AD.3/AD.12 auction paths writes LOSER rows. Advertiser page `/advertiser/dashboard/auction-insights` shows last 24h losses grouped by reason (`higher_cpm`/`targeting_mismatch`/`wallet_exhausted`/…) with a **Boost bid** action per row (POST `/api/advertiser/{id}/auction-insights/boost` — supports `banner`|`advertiser_pw_sponsorship`|`notification`). Change > 20% flips campaign status → `pending_admin` for ADMOD.1 re-review; ≤ 20% goes live immediately.
- **Fix during this session — wallet_v2_service Points balance**: Phase F-2 ledger flip left `/api/wallet/me` reading the legacy `users.bigcoin_balance` mirror. AD.8 daily-code awards go through `PointsService.award(source="daily_code_claim")` which does NOT dual-write. Patched `wallet_v2_service.py:166-181` to source `points_balance` from `PointsService.get_balance()` (ledger truth) with legacy fallback.
- Tests: 22/22 backend PASS (`test_ad8_daily_code_and_auction_boost.py` at iteration_29) — includes multi-day backdated seed harness for 3d/7d/14d ladder rungs + streak-reset when yesterday missing + 20% pending_admin gate for all three boostable ad_types. Frontend live-verified in both `?design=legacy` and `?design=radiolife`. Zero regressions.

## Backlog (P0/P1/P2)
- **P2 · Deferred** AD.7.1 — Split-the-bill (needs group-checkout primitives, deferred from AD.3).
- **P2 · Blocked** AD.9 — Podcast Completion Points (blocked on Track 3 podcast infra).
- **P2 · Blocked** AD.5 — Trivia Sponsorship (blocked on trivia infra maturation).
- **P2** M-series monetization additions (M4 → M1 → M7 → M2 → M3 → M6 → M5), Flagship Sponsor CTA.
