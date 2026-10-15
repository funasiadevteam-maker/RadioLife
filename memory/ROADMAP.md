# RadioLife — ROADMAP (prioritized backlog)

The Universal Advertising API (Partner API v1, Phases A→F) is COMPLETE (see CHANGELOG.md). Consumer features were paused to build it and can now resume.

## 🔜 FUUSIC SOCIAL-FIRST PROGRAM (2026-06 fork) — milestone backlog
Milestone 1 (Production Repair + login visibility) is DONE & tested green (see CHANGELOG). Remaining milestones, in order:
- **M2 — Complete Following ecosystem**: unified Following directory (People/Creators/Stations/Businesses/Clubs/Advisors), follow ANY catalog station (50k+ via stable canonical ids, lightweight follow mapping for third-party stations), interest-based "Who to Follow" recommendations (music genre / language / region / business / club / advisor) with Follow / Not Interested / Hide + explanation labels.
- **M3 — Station social automation**: Station Portal → Shows & Clips (schedule, host, rights, publish mode: Manual/AI Draft/Approved Auto-Publish, default AI Draft), authorized short-buffer recording, AI clip drafts, daily highlights digest + notifications, StationActivityFeedAdapter to unify social_posts + station_posts into one wall item.
- **M4 — Daily Readings**: user-controlled Daily Horoscope / Tarot / Numerology / Fortune subscription (Daily/Weekly/Off, timezone, dedupe/cache), PRIVATE reading cards on the owner's own feed only, AI-generated disclaimers, never in public feed metadata.
- **M5 — Business monetization**: organic business posts from the Merchant Portal (no pay-to-reach-followers), Boost/Sponsored Post wizard reusing existing advertiser/campaign/billing infra, Sponsored feed card (labelled, Hide/Report), configurable placement (1 after ~6–10 organic), Premium ad-free respected, Admin → Social Operations + "Why is this post not showing?" diagnostic.
- **M6 — Clip & Share + My Feed Preferences**: authorized 30s radio-clip creation (server buffer, waveform select, RadioClipSocialCard), Follow Show + reminders, and `/settings/feed` feed-preferences (All Updates / Daily Highlights / Live Only / Mute per followed entity) + DailyFeedDigestService.
- **M7 — Premium Games visual redesign**: AI artwork (GPT Image — user choice) persisted to object storage, real interactive Wheel/Dice/Trivia/Scratch/Predict (server-authoritative outcomes), Play Home redesign (desktop + mobile), social sharing of real wins.

## ✅ DONE (2026-06 fork, iter182) — Background import + sample banners + banner cleanups
- **Background bulk import** ✅: `/api/admin/tracks/bulk-upload?background=1` spools then returns 202 + job_id and processes off-request (poll `/api/me/bulk-upload/jobs/{job_id}`); admin can close the tab. Web toggle + live job tracker.
- **Sample banners** ✅: 118 category-themed Pillow composites (123 total house sample campaigns) populate the advertiser rail rotation with variety. Re-run `python -m scripts.seed_sample_banners` from /app/backend.
- **Banner cleanups** ✅: CTR unit unified to a fraction across endpoints; server-side weight clamp (1–10).

## Remaining backlog (next up)
- **Push Notifications (P2, mobile)** — real FCM/Firebase (`google-services.json`) instead of in-app alerts. INTEGRATION; needs a Publish native build (can't be tested on Expo Go / web preview). Only build on explicit user request.
- **Mobile parity (P2)** — the new advertiser self-serve banners + background-import UX are web-only; mirror on mobile if desired.
- **Bulk-upload streaming (P3, optional)** — `_spool_upload_to_disk` reads each file fully into memory; bounded by the 30 MB client chunk so fine in practice, but could restore 1 MB chunked reads to match its docstring for true 5 GB single-request safety.

## P0 — ✅ DONE (2026-09): game-win wallet crediting + daily streak
- **Real game-win crediting** ✅: `POST /api/play/resolve` now credits the BigPoints wallet via `bigcoin.award` when a `bigcoin` prize is won. Verified.
- **Daily play-streak bonus** ✅: +10 BP/day growing bonus, capped +70, once per UTC day, resets on a missed day. `GET /api/play/streak`. Verified.
- Remaining polish (optional): surface streak + awarded BigPoints in the game WinReveal UI (web + mobile). **BigPoints DB migration** of legacy "BigCoin"-labelled docs still pending.

## Premium Dining Club — remaining phases (Phase 1 backend ✅ DONE + tested iter126)
- **Phase 2 — Merchant dashboard**: enroll locations, VEG/NON_VEG daily meal + rotation, per-meal-period capacity, blackout dates, billing ($500/location/mo default, configurable), analytics. (backend merchant CRUD + web+mobile UI)
- **Phase 3 — Consumer UI (web + mobile)**: Dining home, enroll flow (Premium bundle disclosure → 3-14 meals/week → pay), Use-a-Meal (VEG/NON_VEG → pre-spin aggregate → SPIN wheel animation or Surprise Me → reveal → one reroll → accept → $9.99 → QR pass). Wheel lands on the server-decided winner.
- **Phase 4 — Admin + Partner API + Webhooks**: admin fairness dashboard + settings UI; extend Partner API v1 for restaurant systems; dining.* webhooks.
- Non-blocking hardening (iter126): merchant-role guard on `/merchant/redeem`, https origin_url, wider abandon cooldown, batch merchant lookups, don't echo raw QR token in `/pass`.

## P1 — ✅ DONE (2026-09): Consumer storefront & scarcity (web + mobile, iter130)
- **`/store/:id` branded coupon landing** ✅ (web `StorePage.jsx` + mobile `app/store/[id].tsx`) — brand header + games + play CTAs.
- **`my-coupons`** ✅ — unified owned coupons via `GET /api/me/wallet-coupons`; surfaced as a "My Coupons" tab in the existing web `CouponOffers.jsx` (`/offers`) and mobile `app/coupons.tsx`.
- **FPK coupon-cap dashboard** ✅ (admin `/admin/fpk-caps`) + **player "coupons left today" scarcity strip** ✅ with live UTC-midnight countdown (`CouponScarcityStrip`, both surfaces), backed by `GET /api/store/{id}` + `/scarcity` + `GET /api/admin/fpk/coupon-caps`.
- **Public landing page focus** ✅ — `marketing/Landing.jsx` now leads with a consumer "For listeners" section before the B2B sections.

## P1 — remaining (deferred)
- **Contextual commerce & play**: surface Shop/Play contextually from audio; normalize Social/Play/Shop deep links; remove internal labels.
- **Voice Match Art**: suggest an anchor voice for station genres.

## P2 — Later
- Picture-in-Picture for Creator Studio video podcasts.
- Clean up recurring mobile TS/ESLint warnings.
- More monetization (Lead Gen CPL, Prepaid Offers).

## Partner API — deferred non-blocking hardening (from iter121–125 reviews)
- Move list-endpoint cursor pagination into the DB query (several endpoints fetch `.limit(500/1000)` then paginate in memory).
- Cache 'final' billing invoices instead of regenerating on every read.
- Durable webhook retry queue (currently 3 in-request tries) + bounded emit fan-out (semaphore).
- Introduce dedicated `webhooks:read/write` scope gating (kept `campaigns:*` for back-compat).
- Webhook secret-rotation grace window (old secret currently invalid immediately).
- Refactor: break `/app/backend/server.py` (~7.6k lines) into domain routers/services.
