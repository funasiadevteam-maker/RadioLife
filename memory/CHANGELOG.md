# RadioLife — CHANGELOG (newest first)

History before 2026-09 lives in PRD.md (dated sections). Going forward, log shipped work here.

## 2026-09 — Universal Advertising API: Phases D, E, F (Partner API v1 extension)
Extended the existing `/api/v1` Partner API (no rebuild; reuses internal ad/game/sponsorship engines). LIVE/SANDBOX isolation; Idempotency-Key + external_id dedup + cursor pagination + normalized error envelope + X-RadioLife-API-Version/X-Request-ID everywhere.

- **Phase D — Booking APIs** (iter123, backend 36/36): sponsored games (reuse `games_v2.create_sponsored_game`), trivia/Predict&Win/AI-RJ sponsorships, audio/display inventory discovery. `GET /game-templates`, `POST/GET /sponsored-games`, `/predictions/eligible`, `/trivia/inventory`, `/inventory/{display,audio}`, `/sponsorships`.
- **Phase E — Merchant + Rewards/Conversions + Bulk/Async + Analytics + Billing** (iter124, backend 52/52): NEW `services/partner_api_phase_e.py`. Merchant businesses+offers CRUD; safe idempotent reward-events + conversions (validated, capped, dedup, NO wallet mutation); bulk sync via async jobs (`POST /bulk/{op}` → `GET /jobs/{id}`); `GET /analytics/summary|/timeseries`; `GET /billing/summary|/invoices`. NEW scopes rewards:write, conversions:read/write, jobs:read/write. NEW collections partner_merchants/offers/reward_events/conversions/jobs/invoices.
- **Phase F — Webhooks hardening + Developer Portal + admin mgmt + feature flags + IP allowlist + security** (iter125, backend 26/26 + web verified): expanded webhook event catalog + emit on D/E writes + secret rotation + delivery log/retry; per-key IP allowlist (403 ip_not_allowed); per-partner feature-flag overrides merged into `/capabilities`; admin partner mgmt (suspend/activate/rate-limit/flags/credentials/usage/key-revoke); partner suspension → 403 partner_suspended; security headers on all `/api/v1` responses. Web Developer Portal (`DeveloperApi.jsx`, /advertiser/dashboard/api) extended with IP allowlist editor, webhook event chips, secret rotation, delivery log+retry, and an interactive API Explorer.

Test creds/keys: `/app/memory/test_credentials.md`. Reports: `/app/test_reports/iteration_{123,124,125}.json`.
