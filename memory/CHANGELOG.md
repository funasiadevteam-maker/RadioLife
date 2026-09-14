# RadioLife — CHANGELOG (newest first)

History before 2026-09 lives in PRD.md (dated sections). Going forward, log shipped work here.

## 2026-09 — Waitlist Inbox + Restock Teaser (validated iter133, web + mobile)

- **Waitlist Inbox**: a "Waitlisted" row on the My Coupons view (web `CouponOffers.jsx` `WaitlistBlock`, mobile `coupons.tsx` `waitlistSection`) lists the FPK games the user is waiting on with a Stop/Leave action. Reuses `GET /api/me/waitlist` + `POST /api/store/{id}/waitlist/leave` (no backend change). Rendered as the My Coupons header so it shows even with zero coupons.
- **Restock Teaser**: sold-out storefront game cards (web `StorePage.jsx`, mobile `store/[id].tsx`) show "🔔 Fresh coupons drop at {local reset time}" derived from the store's `resets_at`.
- Refactors: web `MyCouponsView` now takes a `header` prop + builds a `body` var; mobile `MyCouponsList` uses a `body` var + outer-wrapper QR Modal. QR pass modal + all My Coupons states regression-verified.

## 2026-09 — Coupon QR Passes + Contextual Store Links (Pair 1, validated iter131)

- **Coupon QR Passes** (web + mobile): every owned coupon (from any of the 3 engines — games_v2 wallet items, ad-saved `db.coupons`, `/play` game wins) can mint ONE scannable QR pass and be settled in-store via a single redeem path. NEW `routes/coupon_pass.py`: `POST /api/me/coupons/pass {source,id}` (idempotent, returns a `clp_` token + PNG `qr_data_uri`), `GET /api/coupons/pass/{token}` (merchant preview), `POST /api/coupons/redeem/{token}` (staff-only: admin/advertiser/merchant; one-time; syncs the underlying source record). Web: "Show QR" modal in My Coupons (`CouponOffers.jsx`). Mobile: RN Modal QR in `coupons.tsx`.
- **Contextual "Shop this sponsor" links** (web + mobile): NEW `/api/sponsors/{advertiser_id}/store` resolver + `store` object injected into `/api/ads/current` (web ActionCard `ad-shop-sponsor`) and `/api/banner/serve` (mobile `AdBanner` chip) — appears only for sponsors whose advertiser runs an active storefront (games).

## 2026-09 — Sold-Out Waitlist + Picture-in-Picture (Pair 2, validated iter132 + fixes)

- **Sold-Out Waitlist "Remind me"** (web + mobile): when an FPK coupon game is sold out for the day, listeners tap "Remind me" to join a per-campaign waitlist and are pinged on restock via an in-app notification (`station_notifications` `coupon_restock`) AND a best-effort mobile push. NEW `routes/coupon_waitlist.py`: `POST /api/store/{advertiser_id}/waitlist`, `/waitlist/leave`, `GET /api/me/waitlist`, `POST /api/admin/waitlist/dispatch` (force-notify by default). Auto-dispatch piggybacks (rate-limited) on the public scarcity poll so restocks after the UTC-midnight reset ping on first traffic — no cron. Storefront cards (web `StorePage.jsx` + mobile `store/[id].tsx`) swap the Play CTA for Remind-me / "On waitlist" when `remaining_today==0`.
- **Picture-in-Picture for video podcasts**: WEB — NEW `components/PipVideoPlayer.jsx` floating player using `HTMLVideoElement.requestPictureInPicture()`, wired into the mounted `pages/PodcastDetail.jsx` (+ RadioLife variant) via a per-episode "Watch" button that lazy-loads `/api/podcasts/episodes/{id}/media`. MOBILE — expo-video `VideoView` PiP (`mobile-episode-pip-btn`, `allowsPictureInPicture`, `app.json supportsPictureInPicture:true`) was already present; added the hint testID.
- **⚠️ BUILD-ONLY**: mobile push (waitlist restock) and mobile PiP only work on a Published native build — NOT in Expo Go / web preview. Mobile push additionally needs the user's Firebase `google-services.json`. Push send reuses the existing Emergent relay (`services/push_service.send_push`); registration (`_layout.tsx` + `registerForPush` + app.json plugin) was already wired.
- QA seed: `scripts/seed_pair2_testdata.py` marks `cmp_fpk_spin` sold-out for the day + gives episode `ep_ui_demo` (channel `ch_ui_demo`) a sample video.

## 2026-09 — P1 Consumer Storefront & Discovery (web + mobile, validated iter130 FULL GREEN)

Built on the existing FPK sponsored-coupon games engine (advertiser `adv_fpk`, 7 games `cmp_fpk_*`, 5 coupon tiers 10/20/30/40/50% off with per-day caps 200/100/40/15/5). NEW `backend/routes/storefront.py` (read-only, platform-agnostic) wired in `server.py`:
- `GET /api/store/{advertiser_id}` (public) — branded storefront: brand (name/logo/colors), active games + per-game `remaining_today` (coupon scarcity computed from `daily_quantity_cap`/`daily_issued`/`daily_issued_date` with lazy today-rollover), aggregate `coupons_left_today`, `resets_at` (next UTC midnight). 404 for unknown advertiser.
- `GET /api/store/{advertiser_id}/scarcity` (public) — per-game + aggregate remaining today + reset time.
- `GET /api/me/wallet-coupons` (auth) — the user's owned coupons UNIFIED across `user_wallet_items` (coupon), `db.coupons` (ad-saved), and `db.plays` game wins (BigPoints wins excluded).
- `GET /api/admin/fpk/coupon-caps` (admin only) — per-game per-tier daily cap / issued-today / remaining + totals.

Web (`/app/frontend`): branded `StorePage.jsx` at `/store/:id`; `CouponOffers.jsx` extended with Deals / My Coupons tabs (reads `/api/me/wallet-coupons`, copyable codes, status pills, logged-out sign-in prompt) + FPK store link; admin `FpkCouponCaps.jsx` at `/admin/fpk-caps` (requireAdmin); reusable `CouponScarcityStrip.jsx` (live HH:MM:SS countdown to reset); marketing `Landing.jsx` refocused with a consumer-first "For listeners" section rendered BEFORE the B2B sections. Routes added in `App.js`.

Mobile (`/app/mobile`): branded `app/store/[id].tsx`; `app/coupons.tsx` extended with Deals / My Coupons tabs + FPK store banner (→ `/store/adv_fpk`); reusable `src/components/CouponScarcityStrip.tsx`. Store Play cards → `/game/{campaign_id}`.

Reports: `/app/test_reports/iteration_130.json` (backend 8/8 + web + mobile GREEN).

## 2026-09 — P0 wallet crediting + daily streak, and Premium Dining Club (Phases 1–4, validated iter129 FULL GREEN)

Dining Club final E2E (iter129) GREEN on both surfaces after fixing the Expo-preview CORS block (K8s ingress rewrites the Origin header; since all cross-origin callers use bearer tokens not cookies and web is same-origin, `server.py` CORS now returns a literal `Access-Control-Allow-Origin: *` with `allow_credentials=False` when `CORS_ORIGINS='*'`) and adding the merchant-role guard on `/api/merchant/dining-club/redeem`.


**P0 (consumer, verified via curl):** `POST /api/play/resolve` now CREDITS the BigPoints wallet when a `prize_type='bigcoin'` prize is won (was resolved but never credited) via `bigcoin.award`, and awards a consecutive-day play-streak bonus (+10/day, capped +70) once per UTC day (atomic per-day slot, no double-award, idempotent on replay). New `GET /api/play/streak` status. Files: `play_routes.py`.

**Premium Dining Club — Phase 1 backend (validated iter126, 17/17):** 30-day, Premium-only restaurant meal membership. Customer picks meals/week (3-14) + VEG/NON_VEG only; RadioLife assigns the restaurant via an EQUAL-PROBABILITY wheel (server-decided winner, one optional reroll, or Surprise Me), identity HIDDEN until the result; fixed $9.99/meal. NEW `services/dining_club.py` (config, per-credit FIFO+30-day-expiry ledger, subscription + 4 weekly grants/30-day term, equal-probability candidate/spin engine, selection state machine, reservations, signed single-use QR + redemption) and `routes/dining_club.py` (consumer `/api/dining-club/*`, merchant `/api/merchant/dining-club/redeem`, admin `/api/admin/dining-club/*` incl seed/settings/run-grants/fairness/mark-paid). Reuses Premium (`premium_gate`/`grant_premium`), BigPoints, Stripe (billing pattern; live returns cs_test_ URL, admin mark-paid for QA), secure RNG. 12 demo restaurants seeded.

## 2026-09 — Universal Advertising API: Phases D, E, F (Partner API v1 extension)
Extended the existing `/api/v1` Partner API (no rebuild; reuses internal ad/game/sponsorship engines). LIVE/SANDBOX isolation; Idempotency-Key + external_id dedup + cursor pagination + normalized error envelope + X-RadioLife-API-Version/X-Request-ID everywhere.

- **Phase D — Booking APIs** (iter123, backend 36/36): sponsored games (reuse `games_v2.create_sponsored_game`), trivia/Predict&Win/AI-RJ sponsorships, audio/display inventory discovery. `GET /game-templates`, `POST/GET /sponsored-games`, `/predictions/eligible`, `/trivia/inventory`, `/inventory/{display,audio}`, `/sponsorships`.
- **Phase E — Merchant + Rewards/Conversions + Bulk/Async + Analytics + Billing** (iter124, backend 52/52): NEW `services/partner_api_phase_e.py`. Merchant businesses+offers CRUD; safe idempotent reward-events + conversions (validated, capped, dedup, NO wallet mutation); bulk sync via async jobs (`POST /bulk/{op}` → `GET /jobs/{id}`); `GET /analytics/summary|/timeseries`; `GET /billing/summary|/invoices`. NEW scopes rewards:write, conversions:read/write, jobs:read/write. NEW collections partner_merchants/offers/reward_events/conversions/jobs/invoices.
- **Phase F — Webhooks hardening + Developer Portal + admin mgmt + feature flags + IP allowlist + security** (iter125, backend 26/26 + web verified): expanded webhook event catalog + emit on D/E writes + secret rotation + delivery log/retry; per-key IP allowlist (403 ip_not_allowed); per-partner feature-flag overrides merged into `/capabilities`; admin partner mgmt (suspend/activate/rate-limit/flags/credentials/usage/key-revoke); partner suspension → 403 partner_suspended; security headers on all `/api/v1` responses. Web Developer Portal (`DeveloperApi.jsx`, /advertiser/dashboard/api) extended with IP allowlist editor, webhook event chips, secret rotation, delivery log+retry, and an interactive API Explorer.

Test creds/keys: `/app/memory/test_credentials.md`. Reports: `/app/test_reports/iteration_{123,124,125}.json`.
