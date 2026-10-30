# 02 — Backend Design

FastAPI + MongoDB (Motor async) + Pydantic 2. The backend is the **single source of truth** and
is platform-agnostic: the same routes serve web and mobile.

## Layering

```
request → server.py (app, middleware, /api router)
            └─ routes/<feature>.py      ── thin HTTP layer (APIRouter, validation, auth deps)
                 └─ services/<feature>.py ── business logic, orchestration, external calls
                      └─ core/db.py        ── Motor client + `db` singleton
                      └─ models/*.py        ── Pydantic models / Mongo (de)serialization
```

- **routes/** (~240 modules) — each file is an `APIRouter`; handlers stay thin: parse input,
  check auth, call a service, return a serialized model. Routers are registered in `server.py`
  via ~306 `include_router(...)` calls (many gated behind try/except so one bad import can't take
  the whole app down).
- **services/** (~265 modules) — where the real work lives: AI orchestration, auctions, payments,
  moderation, seeding, provider adapters, etc. Routes should delegate here.
- **models/** — `billing.py`, `games.py`, `radio.py`, `rj.py`, `tracks.py` plus shared helpers.
- **core/** — `db.py` (Mongo singleton), `config.py` (env), `brand.py`, `features.py`
  (feature catalog/personalization), `origins.py` (public-origin resolution for Stripe
  redirects), `home_config.py`, `ranges.py`, `state.py`.

## `server.py` (the hub, ~8.4k lines)

Responsibilities:
- Create `app = FastAPI(title="FUUSIC POC", openapi_url="/api/openapi.json")` and
  `api = APIRouter(prefix="/api")`.
- Install middleware: CORS (`CORS_ORIGINS`), security headers, soft-launch `LaunchGuardMiddleware`,
  cache middleware.
- Mount static asset dirs under `/api/static/...` and register every feature router.
- Define core radio endpoints (`/api/radio/start|next|skip`, segment building with AI-RJ
  voiceovers) and the startup seeders/index creators.
- Deploy hardening (non-blocking startup, health probes) — see `01_SYSTEM_ARCHITECTURE.md`.

> Because it is huge, **extend via `routes/` + `services/` modules**, not by piling more into
> `server.py`. Splitting `server.py` further is an acknowledged refactor backlog item.

## Auth (`auth.py`)

- **Session model**: cookie `bigfm_session` (web) **or** `Authorization: Bearer <token>` (mobile
  / curl). TTL 7 days. `POST /api/auth/register | login | logout`, `GET /api/auth/me`
  (= `GET /api/users/me`).
- **Dependencies**: `current_user(request)` (401 if missing), `current_user_optional`,
  `require_admin(user)` (403 unless `role=admin`). Use these in every protected route.
- **Password**: bcrypt (`bcrypt==4.1.3`). Never store plaintext.
- **OAuth**: the app now uses its **own** Google OAuth client (server-side auth-code flow):
  `GET /api/auth/google/login` → 302 → Google; `GET /api/auth/google/callback` issues our session
  (cookie on web, deep-link token on mobile). Apple Sign-In via `routes/auth_apple.py` +
  `services/apple_siwa.py`. Both prod flows are **blocked on user-supplied config** (GCP redirect
  URI / Apple `.p8`) — see PRD "Pending Issues".

> Any change to auth (login, hashing, tokens, reset, seeding) must go through `integration_expert`
> first — do not hand-roll auth edits.

## MongoDB conventions

`ObjectId` is not JSON-serializable, so **never return raw Mongo documents**. The expected pattern
(see `models/`):

- A `PyObjectId` annotated type coerces `ObjectId → str`.
- A base document model maps `_id → id` with `to_mongo()` / `from_mongo()` helpers.
- Read: `Model.from_mongo(doc)`. Write: `instance.to_mongo()`. Exclude `_id` from responses.
- Timestamps: `datetime.now(timezone.utc)` (never `utcnow()`); store ISO strings where needed.
- Route ordering: define specific routes (e.g. `/users/me`) **before** parameterized ones
  (`/users/{id}`).

Collections are created/indexed lazily at startup via `ensure_*_indexes(db)` seeders (fire-and-
forget). Idempotent demo seeders populate preview fixtures (businesses, advisors, games, etc.).

## Feature flags & config-driven behaviour

- `core/features.py` — canonical catalog of user-facing feature pillars (listen is mandatory;
  social/live/shop/play/dining/earn/explore are optional) used for Home/nav personalization.
- Fun AI flags (`FUN_AI_ENABLED`, `FUN_AI_NEWS_ENABLED`, `FUN_AI_COMPANION_ENABLED`,
  `FUN_AI_SPONSORSHIP_ENABLED`, voice provider/model/limits) gate the AI radio layer.
- `STRIPE_MODE`, soft-launch `business_setup_mode_enabled`, and many admin-tunable
  `system_config` docs drive runtime behaviour without code changes.

## Partner API v1 (`/api/v1`)

A separate, programmatic advertising surface built by extending the internal ad/game/sponsorship
engines — **not** a rebuild. API-key / OAuth2 auth with LIVE vs SANDBOX isolation, Idempotency-Key
+ `external_id` de-dup, cursor pagination, HMAC-signed webhooks, per-partner rate limits + feature
flags + IP allowlist. Phases A→F are complete (campaigns, creatives, booking, merchant/rewards/
conversions, bulk jobs, analytics, billing, developer portal). Full detail:
`/app/docs/PARTNER_API.md`. Keys & test harness: `/app/memory/test_credentials.md`.

## Key backend subsystems (service → what it does)

| Area | Representative services |
|------|------------------------|
| Fun AI radio | `grok_realtime.py`, `fun_ai_service.py`, `fun_ai_radio_policy.py`, `radio_policy.py`, `rj_persona_service.py`, `rj_sponsored_read_service.py`, `news_rj_script.py` |
| Radio/audio | `recommendations.py`, `radio_browser_import.py`, `flagship_station_service.py`, `loudness.py`, `audio_qa.py`, `sfx_library.py` |
| Voice/TTS/STT | `elevenlabs_tts.py`, `openai_tts.py`, `assemblyai_client.py`, `voice_config.py`, `voices.py` |
| News | `news.py`, `news_api_provider.py`, `newsdata_client.py`, `news_radio_renderer.py`, `news_teaser.py` |
| Commerce | `marketplace_service.py`, `dining_club.py`, `scan_to_pay_service.py`, `gift_card_service.py`, `membership_entitlements.py` |
| Payments | `stripe_client.py`, `payment_service.py`, `stripe_connect_service.py`, `billing_service.py`, `commission_service.py` |
| Ads | `rail_auction.py`, `ad_decisioning.py`, `preroll_ad_service.py`, `banner_ad_provider.py`, `partner_api*.py`, `openrtb_auction.py` |
| Games/rewards | `games_v2.py`, `points_service.py`, `bigcoin.py`, `streaks.py`, `predict_win_*` |
| Social | `social_feed.py`, `social_following.py`, `who_to_follow.py`, dreams (`dream_*` routes) |
| Infra/support | `object_storage.py` (Tigris/S3), `mailgun_client.py`, `push_service.py`, `livekit_client.py` (mock-safe), `security_middleware.py`, `cache_middleware.py`, `launch_guard.py` |
