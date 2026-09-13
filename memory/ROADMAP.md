# RadioLife — ROADMAP (prioritized backlog)

The Universal Advertising API (Partner API v1, Phases A→F) is COMPLETE (see CHANGELOG.md). Consumer features were paused to build it and can now resume.

## P0 — ✅ DONE (2026-09): game-win wallet crediting + daily streak
- **Real game-win crediting** ✅: `POST /api/play/resolve` now credits the BigPoints wallet via `bigcoin.award` when a `bigcoin` prize is won. Verified.
- **Daily play-streak bonus** ✅: +10 BP/day growing bonus, capped +70, once per UTC day, resets on a missed day. `GET /api/play/streak`. Verified.
- Remaining polish (optional): surface streak + awarded BigPoints in the game WinReveal UI (web + mobile). **BigPoints DB migration** of legacy "BigCoin"-labelled docs still pending.

## Premium Dining Club — remaining phases (Phase 1 backend ✅ DONE + tested iter126)
- **Phase 2 — Merchant dashboard**: enroll locations, VEG/NON_VEG daily meal + rotation, per-meal-period capacity, blackout dates, billing ($500/location/mo default, configurable), analytics. (backend merchant CRUD + web+mobile UI)
- **Phase 3 — Consumer UI (web + mobile)**: Dining home, enroll flow (Premium bundle disclosure → 3-14 meals/week → pay), Use-a-Meal (VEG/NON_VEG → pre-spin aggregate → SPIN wheel animation or Surprise Me → reveal → one reroll → accept → $9.99 → QR pass). Wheel lands on the server-decided winner.
- **Phase 4 — Admin + Partner API + Webhooks**: admin fairness dashboard + settings UI; extend Partner API v1 for restaurant systems; dining.* webhooks.
- Non-blocking hardening (iter126): merchant-role guard on `/merchant/redeem`, https origin_url, wider abandon cooldown, batch merchant lookups, don't echo raw QR token in `/pass`.

## P1 — Consumer storefront & scarcity (deferred, resume after Dining Club)
- **`/store/:id` branded coupon landing** + `my-coupons` (FPK storefront).
- **FPK coupon-cap dashboard** (admin) + player "coupons left today" scarcity strip with live midnight countdown.
- **Public landing page focus**: refactor logged-out marketing Home to sell the consumer listening proposition first.
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
