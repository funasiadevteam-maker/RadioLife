# RadioLife — PRD (Phase H v1 · Commute Mode MVP · 2026-07-24)

## Changelog — 2026-08-09 (CS.1 + Insights SHIPPED: Creator Studio video/chapters/transcripts + Listing Insights)
- **Verified: testing agent iteration_51 — backend 16/16 PASS + regression (iter49 19 + iter50 23), mobile all testIDs verified. Real Tigris signed URL returned on video upload. One flagged issue (chapters hidden on audio-only episodes) FIXED post-report.**
- **Creator Studio video** (`routes/creator_video.py`, prefix `/api/podcasts`): `POST /episodes/{id}/video` (multipart) streams to **Tigris object storage** via `object_storage.get_storage()` → sets `video_storage_key` + `media_type=video`; `GET /episodes/{id}/media` returns fresh 6h signed `video_url` + chapters + transcript; `PUT /episodes/{id}/chapters` (sorted, validated) + `PUT /episodes/{id}/transcript`. All creator-ownership-gated (channel.creator_id → podcast_creators.user_id; admin allowed). 500MB cap, video content-type check.
- **Creator UI** (`mobile/app/creator/episode/[id].tsx`): `VideoChaptersEditor` — pick+upload video (expo-document-picker), add/remove chapters (title + m:s), transcript editor, save.
- **Consumer playback** (`mobile/app/podcast/episode/[id].tsx`): `EpisodeVideoBlock` (expo-video `VideoView`, PIP enabled), tappable chapters (seek), collapsible transcript. Chapters now render for BOTH video (`EpisodeVideoBlock`) and audio-only (`ChaptersBlock`, seeks the audio `soundRef`). Added `expo-video` config plugin to app.json. **PIP only works in a native Publish build — not Expo Go/web preview.**
- **Listing Insights** (`merchant_marketplace.py`): daily rollup collection `featured_daily` (bumped on `discovery/featured` impressions + featured click clicks/spend); `GET /api/merchant/featured/{id}/insights?days=7` (owner-gated) → 7-day series + totals + budget. Mobile `/merchant/insights/[id]` — totals row (Views/Taps/Tap-rate/Spend) + custom 7-day bar chart; reachable from marketplace featured rows (`mkt-insights-*`).
- **Object storage = Tigris** (S3-compatible, `STORAGE_BACKEND`/`TIGRIS_*` in backend/.env) — used for all Creator Studio video.
- **NEXT (approved, deferred to next turn)**: Booking CPA (venues pay per booking) + Gift Card Market (buy/gift local gift cards via points or Stripe). Then P2: `source=all` DB-pagination; RN deprecation cleanup (shadow*→boxShadow, props.pointerEvents); tunein http mixed-content.


## Changelog — 2026-08-09 (MKT.4 SHIPPED: Web New Look cream/orange + Listing Analytics + Notification Bell)
- **Verified: testing agent iteration_50 — backend 75/75 PASS (5 new + 70 regression), mobile fully verified; web verified by main-agent screenshots (agent's web miss was a login-timing artifact, no code bug).**
- **Object storage note (for Creator Studio next)**: app uses **Tigris** (S3-compatible) via `STORAGE_BACKEND`/`TIGRIS_ENDPOINT_URL`/`TIGRIS_BUCKET` in backend/.env — Creator Studio video uploads will reuse this same bucket.
- **Web New Look (cream/orange)**: the web `design_radiolife` variant was stale purple/pink; refreshed to brand cream/orange (`RL_COLORS` gradient `#F26B2A→#F59E0B`, primitives RLButton/RLChip/RLBadge, `AppShellRadioLife` bg `#FBF5EC` + orange Legacy toggle). Recolored `DiscoverRadioLife`, `RewardsWalletRadioLife`, and shared RL components (PointsBalanceCard/CouponCard/etc). NEW `GamingRadioLife.jsx` (Play & Win, `/api/games/discover`) wired at `/play` in `RadioLifeOverlay`. Activate via `?design=radiolife` or the toggle (auth required). Verified rl-gaming-page / rl-rewards-page / rl-discover-page all cream/orange.
- **Listing Analytics** (mobile `/merchant/marketplace`): per-campaign stats row (`mkt-stats-*`) reading the existing list payload — Featured→Views/Taps, Spin/Scratch→Plays/Wins, Trivia→Answers/Correct, Coupon→Claims, Giveaway→Entries, plus a Spend pill. No new endpoint.
- **Notification Bell** (mobile Home): unread-count badge (`home-notif-badge`) from `GET /api/me/notifications/unread_count`; hides at 0, updates after reading.
- **NEXT (user-approved)**: Creator Studio — video podcast upload via **Tigris object storage** + chapters + transcripts + PIP (PIP best-effort; needs a Publish build to validate). Then P2: extra business monetization (booking CPA, lead-gen CPL, gift cards, memberships); `source=all` DB-pagination; deprecated RN style props cleanup (shadow*→boxShadow, pointerEvents), mobile TS/lint.


## Changelog — 2026-08-09 (MKT.3 SHIPPED & VERIFIED: Winner Notifications + inbox feed + Featured Listings)
- **Verified via testing agent (iteration_49): backend 19/19 PASS + 51/51 regression, mobile + web verified, NO bugs. Post-review fraud hardening added + re-verified.**
- **Winner Notifications**: `draw_giveaway` enqueues a `giveaway_winner` notification (via `routes.notifications._enqueue`, dedupe `giveaway_win:<cid>:<uid>`, enqueue errors now logged) into each winner's inbox. Mobile `/notifications` — previously toggles-only — now shows a live **inbox FEED** (`GET /api/me/notifications`, `notif-inbox`) with unread dots + tap-to-mark-read (`POST /api/me/notifications/{id}/read`). NOTE: inbox routes are under `/api/me/notifications`.
- **Featured Listings** (marketplace type `featured`, rate `featured_listing` CPA — rate card now 10 items): merchant pays to pin a venue to local discovery (tagline + bid_cents + budget in `/merchant/marketplace`). Consumer `GET /api/discovery/featured` (bid desc, excludes exhausted, counts impressions) → "FEATURED NEAR YOU" rail on mobile Home (`home-featured-*`). `POST /api/discovery/featured/{id}/click` charges bid_cents, auto-pauses on exhaustion.
- **Click-fraud hardening** (post-iter49 review): featured click now requires auth (anon → 401) and bills at most once per user per campaign per day via unique-indexed `featured_clicks`; returns `charged: true/false`. Verified.
- **NEXT (user-approved order)**: (3a) Creator Studio — video podcast upload via **built-in object storage** + chapters + transcripts + PIP (PIP best-effort; needs a Publish build to validate); (4a) Try New Look — bring the web cream/orange variant to web Gaming/Wallet/Discover. Then P2: extra business monetization (booking CPA, lead-gen CPL, gift cards, memberships), `source=all` DB-pagination, mobile TS/lint cleanup.


## Changelog — 2026-08-09 (MKT.2 SHIPPED & VERIFIED: Format Selector + Spin/Scratch + Giveaways + Directory Scaling)
- **Verified via testing agent (iteration_48): backend 26/26 PASS + 43/43 regression (MKT.1 25 + RWD.5 18), mobile + web verified, NO blockers.**
- **Campaign Format Selector** (advertiser MOBILE `app/advertiser/campaign/new.tsx` step 1): fetches `GET /api/rate-card/formats` (banner/audio/push/video → rate-card keys display_banner/audio_preroll/push_notification/video_ad) and shows each format's live price; the choice is sent as `targeting.ad_format` (free-form, non-breaking). New endpoint in `merchant_marketplace.py`.
- **Spin & Scratch instant-win games** (marketplace types `spin`/`scratch`): merchant sets win_points + win_probability + prize_label + budget. Consumer MOBILE `/brand-games` (linked from `/earn` `earn-brand-games`): `GET /api/brand-games/active`, `POST /api/brand-games/{id}/play` (one play/user, weighted RNG, awards points via idempotency_key, spends `instant_win_game` rate, auto-pauses on budget exhaustion). Reanimated spin animation on the play button.
- **Prize Giveaways** (type `giveaway`): merchant sets prize_desc + num_winners + budget. Consumer MOBILE `/brand-giveaways` (linked from `/earn` `earn-brand-giveaways`): `GET /api/brand-giveaways/active`, `POST /api/brand-giveaways/{id}/enter` (one entry/user, awards points). Merchant draws winners via `POST /api/merchant/marketplace/campaigns/{id}/draw` (owner/admin, random min(num_winners, entries), marks drawn+paused); `mkt-draw-*` button in the marketplace list.
- **Rate Card** grew to 9 items — added `instant_win_game` (CPA) + `giveaway_entry` (CPL); `_rate_card()` backfills new keys into pre-existing docs so admins can tune them.
- **Directory Scaling** (backend `routes/radio_unified.py`): `GET /api/radio/browse?source=imported` now takes a DB-level paginated fast path (`_browse_imported_fast`: `count_documents` + flagship-first `.sort().skip().limit()`) instead of the in-memory 2000-doc merge — the 40K+ directory now reports the true total (~5000+ active) and paginates correctly past page ~66. `source=all` merge path unchanged. Mobile Stations screen already had infinite scroll (`onEndReached`).
- **NEXT (remaining roadmap)**: P2 — video podcasts + Creator Studio, Try-New-Look parity, extra business monetization (featured listings, booking CPA, lead-gen CPL, gift cards, memberships); `source=all` DB-pagination; mobile TS/lint cleanup.
- **Low-pri follow-ups (iter48 review)**: instant-win CPA bills every play not just wins (by design—cost-per-play); insert/increment race on plays; draw audit log; giveaway entry deadline field.


## Changelog — 2026-08-09 (MKT.1 SHIPPED & VERIFIED: Merchant Marketplace + Rate Card + Brand Trivia + Demo Venue)
- **Verified via testing agent (iteration_47): backend 25/25 PASS + 32/32 regression, mobile + web verified, NO blockers.**
- **Demo Venue Seed**: `seed_marketplace()` (called in lifespan) idempotently seeds `businesses.biz_demo_marketplace` owned by the demo user + rate_card + indexes, so `/merchant/*` mobile flows are populated for the demo account.
- **Admin Rate Card Matrix** (WEB `/admin/rate-card`, `admin/RateCard.jsx`, nav `adnav-ads-rate-card`): 7 seeded inventory types (display_banner, audio_preroll, sponsored_rj, push_notification, coupon_featured, trivia_sponsored, video_ad) with CPM/CPA/CPL base/min/max/multipliers/enabled. `GET/PUT /api/admin/rate-card` (admin, validates model ∈ {CPM,CPA,CPL} + min≤max). Rates seed the marketplace pricing hints.
- **Merchant Marketplace "Get More Customers"** (MOBILE `/merchant/marketplace`, backend `routes/merchant_marketplace.py`): goal-first wizard — pick goal → recommended campaign type → form → launch. `GET /api/merchant/marketplace/goals` (4 goals + 2 types + rate hints). Campaign CRUD `POST/GET /api/merchant/marketplace/campaigns` + `/{id}/pause|activate`, ownership-locked via `_assert_merchant_owner`. Collection `merchant_campaigns`. Reachable from Profile (`menu-merchant-marketplace`); Sponsor-a-Bonus also now linked (`menu-merchant-bonuses`).
- **Branded Trivia Campaigns** (type=trivia): merchants author questions + reward_points + budget. Consumer MOBILE `/brand-trivia` (linked from `/earn` via `earn-brand-trivia`): `GET /api/brand-trivia/active` (hides answer_index, per-user answered state), `POST /api/brand-trivia/{id}/answer` awards points on correct (idempotent per user+question, fires reward overlay), spends `trivia_sponsored` rate from budget, auto-pauses when exhausted.
- **Featured Coupon Bidding** (type=coupon_bid): `GET /api/brand-coupons/featured` (sorted by bid_cents desc, excludes exhausted), `POST /api/brand-coupons/{id}/claim` (idempotent per user, awards reward_points_on_claim, spends bid_cents, auto-pauses).
- **NEXT (remaining roadmap)**: P1 Campaign Format Selector (advertiser creation forces Banner/Audio/Push/Video tied to rate card); P2 — 40K radio directory scaling, video podcasts + Creator Studio, Try-New-Look parity, extra business monetization (featured listings, booking CPA, lead-gen CPL, gift cards, memberships); mobile TS/lint cleanup.
- **Low-pri follow-ups (non-blocking, iter47 review)**: unify merchant not-owner error codes; guard floating-point cents drift on spent_usd; optional claim throttle; TuneIn logo Mixed-Content warning on mobile.


## Changelog — 2026-08-09 (RWD.5 VERIFIED: Redeem Ownership Lock + Weekly Streaks + Merchant Self-Serve Bonuses)
- **Verified via testing agent (iteration_46): backend 18/18 PASS + 32/32 regression (iter44+iter45), web + mobile parity confirmed, NO bugs.**
- **Redeem Ownership Lock**: `POST /api/merchant/redeem` + `POST /api/merchant/bonus-windows` enforce `_assert_merchant_owner` (403 non-owner, 404 unknown). `GET /api/merchant/my-businesses` filters to owned venues (admin sees all); `GET /api/merchant/bonus-windows` returns only caller's own; merchant deactivate is owner/admin-gated.
- **Weekly Streak Rewards** (`rewards_earn._maybe_weekly_streak_bonus`): completing ALL enabled weekly missions awards escalating bonus = `weekly_streak_base(150) × min(streak, cap=5)`, idempotent per week via `earn_weekly_completions` + award `idempotency_key=weekstreak:<week>:<uid>` (double-award impossible even under race). Surfaced in claim response `weekly_bonus` + overview `streak.weekly {current, next_reward}`.
- **Merchant Self-Serve Bonuses** (mobile `/merchant/bonuses`): owner creates time-boxed N× (1–10) window, hours 0<x≤168, budget_usd; create→list→deactivate cycle verified on both surfaces.
- **NEXT (per user, ordered 1→5)**: 1) P0 Merchant Marketplace "Get More Customers" goal-first flow (Trivia/Predict&Win/Games/Giveaways/Coupon-bidding), 2) P1 Admin Rate-Card Matrix (CPM/CPA/CPL), 3) P1 Campaign Format Selector, 4) P2 backlog (40K directory scaling, video podcasts + Creator Studio, Try-New-Look parity, extra business monetization), 5) mobile TS/lint cleanup.
- **Low-pri follow-ups (non-blocking, from iter46 review)**: unique index on `earn_weekly_completions(user_id, week_start)`; enforce/spend `budget_usd`; admin `deactivate_bonus_window` 404 on unknown; seed a demo-owned venue so `/merchant/bonuses` isn't empty for demo.


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

## Phase MON.3 — Booking CPA + Gift Card Market (mobile UI) + Chapter Scrubber Markers (2026-08-10) — SHIPPED
- **Booking CPA (mobile)**: `/app/mobile/app/bookings.tsx` wired into the Wallet tab action row (`wallet-bookings-btn`). Lists venues from active booking-type campaigns (`GET /api/bookings/available`), expandable slot/party/name/phone form → `POST /api/bookings/{campaign_id}/book` with confetti confirmation.
- **Gift Card Market (mobile)**: new `/app/mobile/app/giftcards.tsx` wired into Wallet action row (`wallet-giftcards-btn`). Shop tab lists auto-seeded catalog (`GET /api/giftcards/catalog`) with BigCoin balance pill; per-product buy panel supports amount denominations + pay-with points|card + optional gift-to email/message → `POST /api/giftcards/purchase` (points redeems instantly & celebrates; card opens Stripe checkout via WebBrowser). "My Cards" tab lists owned/gifted cards (`GET /api/giftcards/mine`).
- **Chapter Scrubber Markers**: `podcast/episode/[id].tsx` — new `ChapterScrubber` component draws gold chapter tick marks + progress fill/thumb on the audio player track; tap a marker to seek. Falls back to a chapter-derived layout duration when real duration is 0/unknown so markers always render (fix from iter52 HIGH).
- Backend for gift cards (`routes/gift_cards.py`, Phase GC.1) and bookings (in `routes/merchant_marketplace.py`) was pre-built; this phase delivered the mobile UIs + scrubber.
- Tests: iteration_52 — 11/12 backend PASS (points purchase skipped: demo balance < smallest denom, not a bug). Mobile: all testIDs present; scrubber markers confirmed rendering (count=2) after fix. Self-verified via screenshot.
- **Known minor (non-blocking, not in scope this phase)**: giftcards points-purchase idempotency key uses a fresh uuid per request (client `busy` guard prevents double-tap); giftcards Stripe `origin_url` uses the API host (consistent with existing platform checkout pattern).

## Phase MON.4 — Buy BigCoin + Gift Card Reveal + Video PIP + Booking Reminders (2026-08-10) — SHIPPED
- **Buy More BigCoin**: `routes/bigcoin_topup.py` — `GET /api/bigcoin/topup/packages` (4 packages, 100 BC=$1, bonus tiers), `POST /checkout` (Stripe), `GET /{session_id}/status` (credits ledger via PointsService, idempotent on session id, ownership-scoped). Mobile `/bigcoin-topup` screen + Wallet "Top Up" button (`wallet-topup-btn`) + inline "buy BigCoin" nudge on the Gift Card screen when points are short (`gc-topup-*`, passes `needed`).
- **Gift Card Reveal + Thanks**: gift cards now carry `revealed`/`thanks_sent`; `/mine` returns `received_gift`. New `POST /api/giftcards/{card_id}/reveal` and `POST /{card_id}/thanks` (enqueues `giftcard_thanks` notification to the buyer). Mobile My Cards shows a tap-to-scratch animated cover for received gifts (`gc-scratch-*`) then a "Send thanks" tap-back (`gc-thanks-*` → `gc-thanks-done-*`).
- **Video Picture-in-Picture**: PIP button (`mobile-episode-pip-btn`) on the video podcast player calling `player.startPictureInPicture()` (app.json already has `supportsPictureInPicture: true`). Added a "installed app only" hint. `_media_payload` now also honors a plain `ep.video_url` so PIP shows for episodes without a Tigris key. NOTE: PIP only works on a published native build, not Expo Go/web preview.
- **Booking Reminders (in-app)**: `POST /api/bookings/{id}/book` enqueues a `booking_reminder` into the Notifications inbox; new `GET /api/bookings/mine`. Mobile Bookings screen shows an upcoming-reservations reminder banner (`bookings-reminder`).
- Tests: iteration_53 — 13/13 backend pytest PASS; mobile UIs verified in Expo preview. PIP functional path validated only after Publish (native build).

## Phase MON.5 — House Games ×4 + Reservation Manager + Gift Card Redeem (2026-08-10) — SHIPPED
- **4 new always-on platform games**: `seed_extra_house_games` (services/games_v2.py, run at boot) seeds cmp_house_scratch/mystery/memory/word (is_platform_funded, open_to_all, no expiry) reusing existing templates + generic `/game/[campaignId]` player. Surfaced in the Games tab "MORE GAMES LIVE NOW" (deduped so hardcoded spin/trivia/lyric don't repeat).
- **Reservation Manager**: `/api/bookings/mine` now returns `status` + `available_slots`; new `POST /api/bookings/{id}/reschedule` and `/cancel`. Mobile `/reservations` screen (view/reschedule via slot chips/cancel); Bookings reminder banner is tappable → `/reservations`.
- **Gift Card Redeem**: `POST /api/giftcards/{card_id}/redeem {amount_cents}` deducts balance (400 insufficient_balance, status→spent at 0, logs gift_card_redemptions). Mobile My Cards shows a Redeem action with an animated balance tick-down.
- Tests: iteration_54 — 10 backend pytest pass / 3 data-skips (re-verified in UI); all mobile flows verified in Expo preview.
- **Known (non-blocking)**: gift-card redeem is self-contained (no merchant/POS binding yet) — will bind to Marketplace checkout in Phase B; cancelled bookings drop off the reservations list on reload by design.

## SUPER MARKETPLACE — planned (Phase A next)
Approved multi-phase build (spec: 80 sections). Decisions: build BOTH surfaces in lockstep per phase; use existing cream/orange RadioLife brand (NOT the spec's stale purple/pink note); "BigPoints" = existing BigCoin/points ledger; reuse existing Stripe Connect (stripe_connect.py, merchant_onboarding.py) + businesses schema.
- **Phase A (next)**: Admin BigPoints Economics ($0.03/point issuance cost, admin-configurable by market/category/merchant override) · Admin Category + Commission rules engine (no hardcoded %) · "Sell on RadioLife" 10-step business registration (reusing Stripe Connect) · Shop nav + Shop Home shell · Merchant BigPoints settings + cost preview + funding (prepaid + auto-deduct).
- Phases B–F: Restaurant pickup, Services/booking, Ecommerce, Gift cards/memberships/events, AI concierge + promoted marketplace.

## SUPER MARKETPLACE — Phase A1 (backend + admin) SHIPPED (2026-08-10)
Foundation for the local super-app. "BigPoints" = existing BigCoin; only the merchant-side issuance cost + platform commission are new.
- **services/marketplace.py**: economics engine. Default BigPoint issuance cost **$0.03/point (3.0¢)**, admin-configurable via `bigpoint_rates` (scopes global/market/category/merchant; resolver specificity merchant>category>market>global, effective-dated). Category commission via `marketplace_commission_rules` (priority merchant>market_category>category>market>global). `compute_economics()` splits commission vs BigPoints fee vs merchant net. Boot seed `seed_marketplace_foundation` (9 categories + per-category commission + global rate). Fixed Mongo tz-naive datetime compare with `_aware()`.
- **routes/marketplace_admin.py** (`/api/admin/marketplace/*`, admin-only): CRUD bigpoint-rates, categories, commission-rules; businesses list + approve/reject; dashboard.
- **routes/marketplace_merchant.py** (`/api/merchant/marketplace/*`): "Sell on RadioLife" onboarding (validations: bad_category, commission_agreement_required, bigpoints_required, below_min_bigpoints, restaurant price_parity_required) → pending profile mirrored into `businesses` (inactive until approved) + `merchant_bigpoint_accounts`; bigpoints settings + live $ cost preview; funding (prepaid Stripe top-up + status-credit; auto-reload; funding_mode prepaid|auto_deduct).
- **routes/shop.py** (`/api/shop/*`, public): categories, home (headline + 5 sections), businesses (approved only, sortable by bigpoints/rating/featured), business detail (+ ways-to-earn).
- **Web admin page** `/admin/marketplace` (AdminMarketplacePhaseA.jsx, legacy dark shell): Economics / Categories / Commission / Approvals tabs.
- Tests: iteration_55 — **34/34 pytest pass** (auth guards, validations, resolver specificity end-to-end, Stripe fund, approve→shop visibility). No blockers.

### Marketplace Phase A — REMAINING (next sub-steps)
- **A2 — "Sell on RadioLife" registration UI** on both surfaces (mobile Expo wizard + web page) hitting `/onboarding`.
- **A3 — Shop shell UI**: mobile new SHOP tab + nav (Home/Listen/Shop/Play/Wallet, Profile→avatar) + Shop Home; web Shop nav + Shop Home. Cream/orange.
- Then Phases B–F (restaurant pickup, services/booking, ecommerce, gift cards/memberships/events, AI concierge + promoted).

### Still pending (agreed "also this round", not yet built)
- **Games Daily Streak** (bonus for playing all house games in a day).
- **Reorder Favourites** (save favourite venue + rebook usual slot).
- **Gift Card Auto-Apply** — deferred to Phase B (needs Marketplace checkout).

## SUPER MARKETPLACE — Phase A2+A3 (Shop UI, both surfaces) SHIPPED (2026-08-10)
- **Demo businesses** (`seed_demo_businesses`, idempotent upsert on boot): 6 approved storefronts (Grill House, Spice Route, Brew & Bean, Glow Beauty, Urban Threads, Pulse Fitness) with cover images + BigPoints, so Shop looks alive.
- **Mobile Shop**: new **SHOP tab** (nav now Home/Listen/Shop/Play/Wallet/More; Games→Play). Screens: `(tabs)/shop.tsx` (Shop Home — headline, search, category chips, filters, Sell CTA, business-card rails), `shop/[id].tsx` (detail + ways-to-earn + CTA), `shop/browse.tsx` (search/sort/category grid), `sell.tsx` ("Sell on RadioLife" wizard with live $0.03 cost preview + commission/parity agreements → `/onboarding`). Cream/orange.
- **Web Shop** (RadioLife overlay + Tailwind): `ShopRadioLife.jsx` (home+browse), `ShopBusinessRadioLife.jsx` (detail), `SellOnRadioLife.jsx` (registration). Routes `/shop`, `/shop/:id`, `/sell` mapped in RadioLifeOverlay; bottom nav **Shop replaced Discover**. NOTE: like every RadioLife web screen, Shop shows once the "Enable RadioLife design" variant is on (platform-wide behavior, not Shop-specific; variant persistence deliberately left unchanged).
- **Games Daily Streak**: `routes/games_streak.py` — play all 4 new house games in a day → 100 BigCoin bonus (`GET/POST /api/games_v2/daily-streak[/claim]`, idempotent per day). Mobile banner in Play tab (`daily-streak-banner`, progress dots, claim).
- **Reorder Favourites**: `routes/favourites.py` — toggle favourite venue, list with usual slot, one-tap rebook (`/api/favourites/venues*`). Mobile heart on booking cards + Favourites+rebook section in Reservations.
- Tests: iteration_56 — backend 25/26 pass (1 skip: no public booking-campaign catalog to auto-discover a campaign_id); mobile all testIDs verified; web screens verified working behind the design toggle.
- Hardening applied post-test: preview points `ge=0`; demo seed now upserts (cover/points refresh on boot).

## SUPER MARKETPLACE — Phase B (Restaurant Pickup + Subscriptions) SHIPPED (2026-08-10)
Backend (new): `routes/marketplace_subscription.py`, `routes/marketplace_menu.py`, `routes/marketplace_orders.py`, `services/menu_import.py`; extended `services/marketplace.py`, `routes/shop.py`, `routes/marketplace_admin.py`.
- **Merchant Subscriptions**: Starter $29/mo, Pro $99/mo (seeded `subscription_plans`). Stripe Checkout `mode=subscription`. `GET/POST /api/merchant/marketplace/subscription[/plans|/checkout|/status/{sid}]`. ENFORCEMENT: `/api/shop/*` only lists businesses with `subscription_active=true`. Demo businesses auto-granted active (Pro). Admin comp/revoke: `POST /api/admin/marketplace/businesses/{id}/comp-subscription|revoke-subscription`.
- **Menu Builder**: CRUD + bulk `/api/merchant/marketplace/menu[/items[/{id}]|/bulk]`. Consumer `GET /api/shop/businesses/{id}/menu` (grouped sections). Demo menus seeded for grill/spice/brew.
- **AI menu import**: `POST /api/merchant/marketplace/menu/import/ai` (source_type image|pdf|url) via Gemini 2.5 Flash (EMERGENT_LLM_KEY); `/import/file` for Excel/CSV (openpyxl + csv). Returns preview items → bulk save.
- **Orders / Restaurant Pickup**: single-merchant cart → `POST /api/shop/orders/checkout` with **gift-card auto-apply** (highest-balance active card, deducted on payment) → Stripe for remainder (or free if fully covered). Lifecycle `accepted→preparing→ready→picked_up` via `PATCH /api/merchant/marketplace/orders/{id}/status`; **BigPoints awarded to buyer on picked_up** (idempotent, PointsService); prepaid merchants deduct inventory. Pickup code per order.
- **2X Happy Hour**: `PATCH /api/merchant/marketplace/happy-hour`; `effective_points()` applies multiplier during active window (reflected in menu + order points).
- **Merchant Dashboard**: `GET /api/merchant/marketplace/dashboard` (order counts, revenue, points spent, menu count, subscription + happy-hour state).
Web (RadioLife overlay, all under forced `/shop/*` — no design toggle needed): `/shop/menu/:id`, `/shop/orders`, `/shop/merchant`, `/shop/merchant/menu`, `/shop/merchant/subscribe`.
Mobile (Expo): `shop/menu/[id].tsx`, `shop/cart.tsx`, `shop/orders.tsx`, `merchant/dashboard.tsx`, `merchant/menu.tsx`, `merchant/subscribe.tsx`; cart store `useCartStore`.
Tests: iteration_57 — backend 27/28 then 28/28 after fix (happy_hour projection in shop.py fixed + verified; picked_up→canceled now guarded). Full lifecycle E2E incl. points-on-pickup verified. Mobile smoke 100%. Web /shop/* verified rendering via forced overlay.
Known MVP limitation: gift-card reservation is not locked across simultaneous checkout sessions (single-merchant, low-concurrency — acceptable for MVP).

## SUPER MARKETPLACE — Phase C + enhancements SHIPPED (2026-08-10)
Backend (new/updated): `routes/marketplace_services.py` (services+bookings), `services/menu_photos.py`, extended `routes/marketplace_menu.py`, `routes/marketplace_orders.py`, `server.py` (menu_photos StaticFiles mount + services indexes).
- **Reorder Favourites**: `POST /api/shop/orders/{id}/reorder` → returns still-available items (refreshed prices) + dropped[]; client re-fills cart. Web + mobile "Order Again".
- **Live Order Alerts**: on merchant status → `ready` (and `picked_up`) an in-app `station_notifications` row is enqueued for the buyer (dedupe_key `order_{status}_{id}`). In-app only (no push).
- **Menu Photos**: merchant UPLOAD (`POST /menu/items/{id}/photo`, base64, Pillow-validated + 8MB cap) OR AI generate (`/photo/ai`, Gemini Nano Banana `gemini-3.1-flash-image-preview`). Served public at `/api/static/menu_photos/`. Thumbnails on consumer menu + builder (both surfaces).
- **Service Bookings (Phase C, non-food)**: `service_items` (name, duration, price, reservation_fee_cents credited toward service, bigpoints) + weekly `service_availability` on profile. Consumer: `GET /api/shop/businesses/{id}/services`, `/services/{sid}/slots?date=`, `POST /api/shop/service-bookings/checkout` (reservation fee via Stripe, or free/confirmed if fee 0; 409 slot_taken), `GET /service-bookings[/{id}/status]`. Merchant: services CRUD, `GET/PATCH /availability`, `GET /bookings`, `PATCH /bookings/{id}/status` (confirmed→completed awards BigPoints, →no_show). Enforced by subscription_active.
Web screens: `/shop/services/:id`, `/shop/bookings`, `/shop/merchant/services`; Reorder on `/shop/orders`; photo controls on `/shop/merchant/menu`.
Mobile screens: `shop/services/[id].tsx`, `shop/bookings.tsx`, `merchant/services.tsx`; Reorder on `shop/orders.tsx`; photo controls on `merchant/menu.tsx`; Shop-tab quick links Orders/Bookings/Merchant.
Tests: iteration_58 — backend 35/35 passed; both surfaces smoke-verified; full web/mobile parity; no blocking bugs. Fixed post-test: menu-photo bytes now Pillow-validated (rejects non-images).
Deferred lows: desktop whitespace on `/shop/services/:id` (mobile-first layout); slots use UTC "today" (no merchant TZ); multi-merchant cart; price-parity monitoring.

## SUPER MARKETPLACE — Phase D (Ecommerce Products + Loyalty Tiers + Service Photos + Booking Reminders) SHIPPED (2026-06 fork)
Backend (pre-built, curl-verified earlier; formally verified this turn): `routes/marketplace_products.py`, `services/loyalty.py`; extended `routes/marketplace_services.py` (service photos), `server.py` (booking-reminder cron loop).
- **Ecommerce Products**: merchant catalogue CRUD with variants (label/price/stock), per-product upload OR AI photo (Nano Banana), delivery config (pickup/delivery/fee/free-over). Consumer `GET /api/shop/businesses/{id}/products`; single-merchant cart → `POST /api/shop/product-orders/checkout` (gift-card auto-apply → Stripe for remainder, stock decrement, delivery fee). Fulfillment lifecycle paid→packed→shipped→delivered (`PATCH /api/merchant/marketplace/products/orders/{id}/status`, invalid transitions rejected, `product_shipped` notification enqueued); **BigPoints awarded to buyer on delivered via `award_with_tier_bonus` (idempotent)**; prepaid merchants deduct balance; cancel restocks.
- **Loyalty Tiers** (`services/loyalty.py`): Bronze/Silver/Gold/Platinum from lifetime positive ledger deltas (0/1k/5k/15k → +0/5/10/15% bonus). `GET /api/shop/loyalty` (tier, progress, perks, all_tiers). `award_with_tier_bonus` awards base points then a separate loyalty-bonus ledger row.
- **Service Photos**: `POST /api/merchant/marketplace/services/items/{id}/photo` + `/photo/ai`; consumer services now expose `image_url`.
- **Booking Reminders**: morning-of in-app reminder cron loop in `server.py`.
- **Web screens added THIS turn** (RadioLife overlay, forced `/shop/*`): `ShopProductsRadioLife` (`/shop/products/:id`), `ShopProductOrdersRadioLife` (`/shop/product-orders`), `MerchantProductsRadioLife` (`/shop/merchant/products`), `LoyaltyRadioLife` (`/shop/loyalty`); service-photo controls added to `MerchantServicesRadioLife` + consumer thumbnails on `ShopServicesRadioLife`. Entry links wired: MerchantDash `merchant-open-products`, Shop home `shop-my-product-orders`/`shop-my-loyalty`, business-detail CTA → products.
- **Mobile entry points wired THIS turn**: shop `[id]` products CTA, merchant dashboard `merchant-open-products`, shop-home `shop-my-loyalty`, consumer service thumbnail.
- Tests: **iteration_59 — backend 31/31 pytest PASS**; web + mobile all testIDs functional; **100% cross-surface parity; no blocking bugs**. AI-photo endpoint not re-run (slow/rate-limit; upload path green).
- Non-blocking follow-ups (from iter59 review): desktop whitespace on RadioLife `/shop/*` (mobile-first layout); cookie banner overlaps bottom CTA; RN `shadow*`/`pointerEvents` deprecation warnings; merchant balance-decrement ordering on delivered; unthrottled Stripe polling on order-status GET; loyalty tiers hardcoded in code (not admin-tunable yet).

## SUPER MARKETPLACE — Wave A (Admin Loyalty Tuning + Shop Desktop Polish) SHIPPED (2026-06 fork)
First wave of the post-Phase-D backlog (build order confirmed with user: Wave A → Phase E → Multi-Merchant Cart).
- **Admin Loyalty Tuning**: loyalty tiers/perks are no longer hardcoded. `services/loyalty.py` now loads the ladder from `marketplace_loyalty_config` (single doc `config_id="global"`, idempotently seeded from `DEFAULT_TIERS` on first read; `get_tiers()` sorts ascending by min_points). New admin endpoints `GET/PUT /api/admin/marketplace/loyalty` (validates: non-empty, unique keys, base tier min_points==0). Web admin `/admin/marketplace` gains a **Loyalty Tiers** tab (`mkt-tab-loyalty`) — per-tier color/key/name/min-pts/bonus-%/perks editor with add/remove + Save (`loy-save`). Consumer `GET /api/shop/loyalty` + `award_with_tier_bonus` read the live config. Verified via curl (GET seeds defaults, PUT updates + validation 400) and admin-UI screenshot (4 tiers editable).
- **Shop Desktop Polish**: `AppShellRadioLife` takes a `wide` prop → container `max-w-3xl` (vs `max-w-md`) for all `/shop/*` + `/sell` routes (passed from `RadioLifeOverlay` via `shopRoute`); business grids on Shop home/browse now `grid-cols-2 sm:grid-cols-3`; fixed CTAs on business-detail + products cart widened to `max-w-3xl`. Cookie banner now suppressed on Shop/Sell routes (was overlapping the bottom checkout CTA). Verified via desktop screenshot (3-up grid fills width, no banner overlap).
- Self-tested (curl + screenshots); loyalty award path unchanged (defaults identical to prior hardcoded tiers, exercised by iter59 delivery/pickup/booking flows). No mobile changes in this wave.

## SUPER MARKETPLACE — Wave B = Phase E (Gift Cards / Memberships / Packages / Events) — NEXT
User-confirmed order: (1) Merchant Gift Cards, (2) Memberships, (3) Packages, (4) Events. Memberships = **recurring Stripe subscriptions** AND **entitlement/benefit rules** (e.g. "1 free coffee daily", meal plans — customer redeems included items per rules). Then Wave C = Multi-Merchant Cart (split into one order per merchant at checkout, single payment).

## Backlog (P0/P1/P2)
- **P1** Picture-in-Picture for Creator Studio video podcasts.
- **P1** Clean up recurring mobile TS/ESLint warnings (missing useEffect deps, unused vars, require-style imports).
- **P2** More business monetization: Lead Gen CPL, Prepaid Offers, Business Memberships.
- **P2** Verify 100% cream/orange "New Look" parity across remaining components.
- **P2 · Deferred** AD.7.1 — Split-the-bill (needs group-checkout primitives, deferred from AD.3).
- **P2 · Blocked** AD.9 — Podcast Completion Points (blocked on Track 3 podcast infra).
- **P2 · Blocked** AD.5 — Trivia Sponsorship (blocked on trivia infra maturation).
- **P2** M-series monetization additions (M4 → M1 → M7 → M2 → M3 → M6 → M5), Flagship Sponsor CTA.
