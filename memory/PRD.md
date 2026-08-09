# BigFM — PRD (Phase H v1 · Commute Mode MVP · 2026-07-24)

## Changelog — 2026-08-09 (RWD.4: Earn Streaks + Sponsored Bonuses + Fraud Alerts)
- **Earn Streaks** (`routes/rewards_earn.py`): daily streak with admin-configurable milestone bonuses (`earn_config.streak_bonuses`, default 3/7/14/30 days → +50/200/500/1000), best-streak persisted in `earn_streak_state`, milestone award idempotent per run (`streak:<days>:<uid>:<anchor>`). Surfaced in `/api/me/earn/overview` (`streak.{current,best,next,awarded_bonus}`); clients show next-milestone + fire the reward overlay on auto-award. `_get_config` now backfills new config keys for pre-existing docs.
- **Sponsored Bonuses** (`routes/merchant_ops.py`): time-boxed N× points windows tied to a venue. Admin CRUD `GET/POST /api/admin/bonus-windows` + `/{id}/deactivate` (multiplier bounded 1–10). Active windows surfaced in earn overview (`active_bonuses`) + `GET /api/me/earn/bonus-windows`, and the multiplier is APPLIED in `POST /api/rewards/scan-earn` (`bonus_multiplier` in response). Home + Earn banners on both surfaces.
- **Fraud Alerts** (`routes/merchant_ops.py`): auto-creates admin alerts when a merchant's coupon show-vs-scan gap crosses `fraud_config` thresholds (min_shows/flag_rate/min_unredeemed). `maybe_alert` hooks fire on scan-earn/coupon-show/redeem; `GET /api/admin/fraud-alerts`, `POST /api/admin/fraud-alerts/scan`, `/{id}/resolve`, `GET/PUT /api/admin/fraud-config`. (Clears the long-pending handoff P1.)
- **Web admin console** `/admin/merchant-ops` (`admin/MerchantOps.jsx`): fraud-alert list + resolve + run-scan, and bonus-window create/list/deactivate.
- **Testing**: iteration_45 — backend 14/14 pass; both frontends + admin verified; no bugs. Multiplier bound added post-review.
- **Still pending**: Merchant "Get More Customers" Marketplace (large — next dedicated build); earlier handoff merchant-ownership lock on `/api/merchant/redeem` + admin reward-tuning UI.


## Changelog — 2026-08-09 (RWD.2 Post-Action Rewards + RWD.3 Premium Cues + Brand Cleanup)
- **Brand Cleanup (durable, both layers)**: Rebranded user-visible "BigFM"/"Big FM" → "RadioLife" in the DB (`/app/scripts/rebrand_bigfm.py`, allowlist of display fields only) AND at the SOURCE across 128 backend files (case-sensitive sweep) so seeds no longer re-introduce it on boot. Fixed the 2 regressions the testing agent caught (channels `news_radio` name, `premium_subscriber`/`early_adopter` badges). **Protected**: lowercase slugs/emails (`admin@bigfm.dubai` login still 200), redemption codes, UUIDs, ad-system/ads.txt/VAST identifiers, the flagship validator User-Agent, and **10 real third-party stations** in `imported_radio_stations` (German BigFM network, "BigFM 106.2 UAE" — excluded via `SKIP_COLLECTIONS`; wrongly-renamed ones restored).
- **Post-Action Rewards (RWD.2)**: Global reward-celebration overlay on both surfaces — web `src/rewards/RewardOverlay.jsx` (RewardProvider + `useReward().celebrate`), mobile `src/components/RewardOverlay.tsx`. Shows "+N points", fresh balance, and 2 "keep earning" next actions. Wired into mission claim (both) and web daily-code claim. Proven e2e on web (claim → overlay → dismiss).
- **Premium Cues (RWD.3)**: Backend `routes/premium_cues.py` — `GET /api/me/premium/status` (entitlement from `users.is_premium` + enabled benefits + HONEST value calc: multiplier delta on base earning, reward payouts excluded), `GET /api/premium/benefits`, admin `GET/PUT /api/admin/premium/config` (benefits toggles, points_multiplier, trial, pricing — all tunable). New collection `premium_config`. Clients: web `/premium` (`premium/Premium.jsx`) + reusable `PremiumCue`; mobile `/premium` (`app/premium.tsx`) + `PremiumCue`. Home teasers + Earn-screen cues wired; cues hidden for premium users.
- **Testing**: iteration_44 — backend 16/18 (2 fails were the brand gaps, now fixed & directly re-verified: rebrand dry-run = 0 remaining, logins intact); web + mobile Premium screens + reward overlay verified.
- **Deferred (next dedicated phase)**: **Merchant "Get More Customers" Marketplace** (goal-first flow + merchant trivia/predict-win/games/giveaways/coupon-bidding) — too large to bundle; building next. Earlier handoff items (merchant-ownership lock on redeem, proactive fraud alerts, web admin tuning UI) also still pending.


## Changelog — 2026-08-09 (Phase RWD.1: Rewards "Earn Loop" — cross-platform)
- **Shared backend** (`routes/rewards_earn.py`, built on the Phase F-1 `PointsService`/`points_ledger`): platform-agnostic contract returning semantic `action` keys each client maps to its own route.
  - Listener: `GET /api/me/earn/overview` (balance, listener tier + points-to-next, daily goal, streak, ways-to-earn, missions), `GET /api/me/earn/ways-to-earn`, `POST /api/me/earn/missions/{id}/claim` (idempotent via unique `earn_mission_claims` index → PointsService award).
  - Admin (all `require_admin`, tunable — NOTHING hardcoded in clients): `GET/PUT /api/admin/earn/catalog` (earn-opportunity presentation + enable), `/api/admin/earn/missions` (daily/weekly, target/metric/sources/reward), `/api/admin/earn/config` (listener_tiers Bronze/Silver/Gold/Platinum + daily_goal target/bonus). Idempotent `$setOnInsert` seeds so admin edits survive reboots.
  - New collections: `earn_actions_catalog`, `earn_missions`, `earn_mission_claims`, `earn_config`.
- **Web** (`/app/frontend/src/rewards/*`): persistent **PointsPill** in top bar → drawer of top-3 ways + link to /earn; **WaysToEarnCard** on Home (top 5 + daily-goal bar + contextual Premium teaser → /pricing); full **/earn** screen (balance, tier progress, daily goal, streak, Available Now, daily+weekly missions with Claim).
- **Mobile** (`/app/mobile` — PointsPill + WaysToEarnCard components, `app/earn.tsx`, `src/api/earnApi.ts`): parity — header pill → bottom-sheet, Home card + Premium teaser (→ profile), `/earn` route with missions/claim. Same shared backend contract.
- **Also shipped this session**: Trivia **Practice Solo** fix (`TriviaRoom.jsx` — now launches a solo session with the room's category instead of bouncing back); RadioLife **app icon** set (mobile `icon/adaptive/splash` + `app.json`) and **web favicon** set (`favicon.ico` + PNG sizes + apple-touch + PWA manifest, wired in `index.html`).
- **Testing**: iteration_43 — backend 15/15 pytest pass (`tests/test_rewards_earn_loop.py`), both web + mobile UIs verified (pill, home card, /earn, mission claim contract incl. 400/409 idempotency). No blocking issues.
- **Still pending from earlier handoff** (NOT started): DB seed rebrand (leftover "BigFM"), merchant-ownership RBAC on `/api/merchant/redeem`, proactive fraud alerts, web admin tuning UI. Plus remaining roadmap phases (Premium cues, advertiser rate-card, merchant marketplace, video podcasts, 40K directory scaling).


## Changelog — 2026-08-06 (Phase 2/3: AI rewards, coupon fraud, merchant portal, game limits)
- **AI Reward Engine** (`routes/rewards_merchant.py`): `POST /api/rewards/scan-earn` awards BigCoin = amount × base × AI multiplier (Emergent LLM gpt-5.4, bounded 1.0–3.0, deterministic fallback); lifetime thresholds grant one-off bonus points + unlock bonus games + concert pass (idempotent via `users.rewards_thresholds_hit`). Mobile: Profile → "Scan & Earn" (`/scan-earn`).
- **Coupon-Fraud Tracking**: `POST /api/coupon-events/show` logs customer shows; `POST /api/merchant/redeem` reconciles the latest unredeemed show; `GET /api/admin/coupon-fraud` flags merchants with low redemption rate (dodging scans).
- **Restaurant Portal**: mobile `/merchant/redeem` (Profile → "Redeem & Loyalty") — redeem coupons + loyalty tier card; `GET /api/merchant/loyalty` tiers Standard/Silver/Gold (0/10/25 daily → 10/12/15%).
- **Game Frequency Limits**: admin `GET/PUT /api/games/limits` (per day/month/every-N-days); `GET /api/games/play-eligibility/{key}` + `POST /api/games/record-play` (429 when exceeded).
- **Admin provisioning**: `GET/PUT /api/rewards/config` (base rate, thresholds, merchant tiers) + game limits, all `require_admin`.
- **Testing**: iteration_42.json — backend 12/12 pass (`tests/test_iter42_rewards_merchant.py`); mobile verified; live gpt-5.4 output confirmed. Fixed loyalty-card refresh (inline flash vs blocking Alert).
- **Known limitations**: `/api/merchant/redeem` has no merchant-ownership RBAC yet (MVP — any authed user can redeem for a merchant_id); admin config UI is API-only (no web admin screen yet); some seeded game/coupon DB records still say "BigFM".


## Changelog — 2026-08-06 (Phase 1 of 3: filters, news reader+points, ads/premium)
- **Iconized Explore filters**: Country/Language/Genre are now 3 labeled iconized rows (earth/language/musical-notes) with larger readable chips. ('EDM' cased correctly, promo keys namespaced.)
- **Tappable news + native reader**: News cards + breaking cards open `/news-article` (native in-app reader: image, title, summary, source, 'Read full article' via in-app browser). Reading awards **+1 BigCoin per unique article**, server-capped at 10/day via `POST /api/news/read` (atomic claim + unique `{user_id,date}` index → no double-credit).
- **Ads between sections + premium skip**: `AdBanner` sprinkled between Home sections (browse_row/station_detail/bottom_bar) and above News headlines; already on games/wallet/listen. `AdBanner` now returns null for premium users (gated on `is_premium`/`premium_tier`) — ad-free for paying members. Renders nothing when no live campaign (no empty boxes).
- **Testing**: iteration_41.json — backend 8/8 pass; mobile flows verified.
- **Confirmed fixed**: "Couldn't load games" (was the demo-login token bug).
- **Remaining backlog** — Phase 2: AI-dynamic rewards (Emergent universal key) + coupon-fraud tracking (pull-vs-scan mismatch) + admin provisioning. Phase 3: restaurant 'More-tab' scan/redeem + restaurant loyalty tiers + admin-configurable game frequency limits. Also user asked to Claim Stripe LIVE via Publish (BYOK — user action; steps relayed via support).


## Changelog — 2026-08-06 (Advertiser Self-Serve + Analytics + Stripe top-ups + Local News tabs)
- **Advertiser Self-Serve (mobile + backend)**: ad wallet (`promo_wallets`), `POST /api/promoted/self-serve` creates a station promo with CPM/CPC bids (auto-active when funded, else `awaiting_funds`), `POST /api/promoted/{id}/toggle` pause/resume. New mobile screen `app/advertiser/promote-station.tsx` (reachable via Profile > 'Sponsor a station' and the advertiser home banner).
- **Sponsored Analytics**: `GET /api/promoted/mine` returns per-promo impressions/clicks/CTR/spend + totals; surfaced on the promote-station screen.
- **Stripe wallet top-ups**: `POST /api/promoted/wallet/topup` (packages $10/$25/$50/$100) → Stripe Checkout (existing env key, TEST mode); `GET /api/promoted/wallet/topup/status/{sid}` idempotently credits the wallet (status-poll fallback, no webhook dependency). Impression/click now debit the wallet and auto-pause a promo when depleted (house promos free). Going LIVE = claim Stripe account via Emergent Publish.
- **Local News tabs**: `/api/news/headlines?scope=local|national` (local=geo city market, national=resolved country); mobile News tab gets Local/National segmented tabs (`news-scope-local` / `news-scope-national`). NOTE: in-pod both resolve to US so content looks identical; diverges in real deployment.
- **Testing**: iteration_39.json — backend 14/14 pytest pass (`tests/test_iter39_advertiser_selfserve.py`); mobile flows verified.


## Changelog — 2026-08-06 (RadioLife.app rebrand + Promoted Stations + News fix)
- **Rebrand BigFM → RadioLife.app** across web + mobile (user-visible text only; internal keys/CSS/events/bundle IDs untouched). Wordmark `BigFM.AI → RadioLife.app`. Added tappable **funasianetwork.com** footer link (mobile FunAsiaFooter component on Home/Login/Profile; web LegalFooter, AppShell sidebar, LandingV2 + MarketingShell footers).
- **Home blockers fixed**: Top Played rail now renders; All Stations Genre filter now passes `category` param and re-fetches (iter37 bug).
- **News fix**: `/api/news/*` was served by an empty admin-curated Phase-R router shadowing the live NewsAPI feed. Added live NewsAPI fallback in `routes/news_phase_r.py` (public_headlines + public_breaking), geo-market aware, mapped to headline_text/summary_text shape. Mobile News tab + Home breaking banner now populated.
- **Demo login geo city**: `backend/auth.py` demo_login now resolves market/city from geo/IP (was hardcoded Dubai). Demo user name reset (no 'BigFM'). Home hero tagline + Radio header city now dynamic via `/api/geo/resolve_city`.
- **Demo-login bug fix**: `login.tsx` demo handler now wires session via api-client `saveToken` + AuthContext `setUser` (was stuck on splash spinner because AuthContext user stayed null).
- **Promoted / Sponsored stations (NEW)**: `routes/promoted_stations.py` (`/api/promoted/*`) — seed-on-empty from flagships, serve cards with `is_sponsored`, CPM/CPC impression+click tracking (spend accrual is **MOCKED** accounting-only, no wallet/Stripe settlement). Mobile Home: two new square-thumbnail rails (Top Played + Most Played Live, sponsored first w/ 'Sponsored' tag); All Stations: pinned 'Sponsored stations' header. Admin create endpoint + admin list included.
- **Testing**: iteration_38.json — backend 7/7 pytest pass; mobile + web flows verified.
- **Stripe "production"**: NOT switched. Cannot hardcode live keys; going live requires claiming the Stripe account via Emergent Publish/deploy (code already reads env-driven STRIPE_MODE/keys).


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
