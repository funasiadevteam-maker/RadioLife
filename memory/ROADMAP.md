# RadioLife — ROADMAP (prioritized backlog)

The Universal Advertising API (Partner API v1, Phases A→F) is COMPLETE (see CHANGELOG.md). Consumer features were paused to build it and can now resume.

## P0 — Resume paused consumer features
- **Real game-win crediting**: `POST /api/play/resolve` resolves a win but does NOT credit the BigPoints wallet balance — wire it to `services.bigcoin.award` so wins actually increase the balance. (backend + verify on web)
- **Daily play-streak bonus**: +10 BP/day growing bonus, capped at +70, resets on a missed day. (`backend/routes/games_streak.py` + consumer UI)
- **BigPoints DB migration**: existing game_prizes/campaign docs still labelled "BigCoin"; source already renamed — migrate stored docs.

## P1 — Consumer storefront & scarcity
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
