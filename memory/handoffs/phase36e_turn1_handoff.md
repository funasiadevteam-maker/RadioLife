# Phase 36e Turn 1 — Subscription Core (Stripe Mock Mode) — HANDOFF

**Status**: ✅ Code complete. Tests green. Ready for e1_tester dispatch.
**Mode**: `STRIPE_MODE=mock` strictly enforced. No live keys.

## Backend (10/10 tests passing)
`backend/tests/test_phase36e_turn1.py` — all 10 tests pass in 0.43s.

Endpoints live in `/api/openapi.json`:
```
POST   /api/creators/{creator_id}/stripe-account
GET    /api/creators/{creator_id}/stripe-account
POST   /api/creators/{creator_id}/stripe-account/onboarding-link
POST   /api/creators/{creator_id}/stripe-account/refresh
POST   /api/creators/{creator_id}/stripe-account/mock/complete
POST   /api/podcasts/channels/{channel_id}/subscription-plan
GET    /api/podcasts/channels/{channel_id}/subscription-plan
PATCH  /api/podcasts/channels/{channel_id}/subscription-plan
DELETE /api/podcasts/channels/{channel_id}/subscription-plan
POST   /api/podcasts/channels/{channel_id}/subscribe
GET    /api/podcasts/channels/{channel_id}/subscription-status
GET    /api/listener/subscriptions
POST   /api/listener/subscriptions/{lsub_id}/cancel
POST   /api/listener/subscriptions/{lsub_id}/resume
POST   /api/webhooks/stripe
POST   /api/admin/stripe/mock/fire-webhook
POST   /api/mock/stripe/checkout/{session_id}/complete
```

## Frontend (3/3 tests passing)
`frontend/src/__tests__/Phase36eTurn1.test.jsx` — all green.

Wiring landed:
- `CreatorChannelSettings.jsx` — `<SubscriptionPlanSection />` is the **third** section
  (after Magic Clips and Lightning Splits), preceded by a horizontal divider + a
  small all-caps "MONETIZATION" header. Both `LightningSplitsEditor` and
  `SubscriptionPlanSection` are explicitly imported (the earlier scaffold had
  missing imports + a typo `ch.creator_id` → fixed to `draft.creator_id`).
- `App.js` routes `/mock/stripe/checkout` and `/listener/subscriptions` already
  registered in the previous auto-commit.
- `backend/routes/podcasts.py` — `_settings_subset` now returns `creator_id`
  (single-field addition; required by the new section to call the creator-scoped
  Stripe endpoints).

## Mock-mode hygiene check
- `services/stripe_client.py` — single abstraction; `is_live()` defaults to mock.
- `grep "STRIPE_SECRET_KEY"` outside the abstraction → **clean** (0 hits).
- `grep "^import stripe"` outside the abstraction → **2 legacy hits**
  in `routes/billing_v6.py` and `routes/phase45.py`. These predate Phase 36e
  Turn 1 (Phase 45 advertiser billing surface) and are unrelated to the Turn 1
  abstraction. **Flagged for clean-up in a later refactor pass** — not blocking
  Turn 1 since they're not exercised by the Subscription flow.
- `backend/.env` has `STRIPE_MODE=test` which `stripe_client.stripe_mode()`
  normalizes to `mock` (only "live" flips it).

## End-to-end mock trace (script output, verbatim)
```
================================================================
PHASE 36e Turn 1 — Stripe-mock flow trace
STRIPE_MODE = mock
================================================================

[1] CREATE Connect Express account
   acct_id = acct_mock_03bfbc5b59bd6bd3

[2] FLIP charges_enabled (mock onboarding complete)

[3] CREATE plan ($4.99, 7-day trial)
   plan_id = csp_e56e1212bc4dc3 | stripe_price_id = price_mock_3a790ec02e89f5d3

[4] LISTENER subscribes
   subscription_id = lsub_5b9484ffe9caf7
   session_id        = cs_mock_61dd1d7e3f44ff44
   checkout_url    = /mock/stripe/checkout?session_id=cs_mock_61dd1d7e3f44ff44&price=price_mock_3a790ec02e89f5d3&trial=7&ref=lsub_5b9484ffe9caf7

[5] WEBHOOK customer.subscription.created (trialing)
   status = trialing | trial_end = 2026-06-12 20:24:36

[6] PAYWALL GATE — bonus episode
   non-subscriber → accessible = False
   subscriber          → accessible = True

[7] AD-SKIP check
   subscriber → ad-skip = True

[8] CANCEL + RESUME
   cancel_at_period_end = True
   after resume cancel_at_period_end = False

[9] subscription_events ledger
   → {'event_type': 'trial_started', 'stripe_event_id': 'evt_mock_1'}

[OK] Phase 36e Turn 1 — MOCK mode, no Stripe network egress.
```

## Mock checkout walk-through (visual)
Captured via Playwright at `/mock/stripe/checkout?session_id=cs_mock_demo_handoff&price=price_mock_premium&trial=7`:
- ⚠️ Top banner: "MOCK STRIPE CHECKOUT — DEVELOPMENT ONLY, NO PAYMENT PROCESSED"
- Body shows session_id / price_id / trial_days
- Two CTAs: "Simulate successful payment" (green) / "Simulate failure" (red)
- 🛑 Bottom banner: "MOCK MODE — flip backend STRIPE_MODE=live + provide STRIPE_SECRET_KEY"

PaywallCard + post-payment success states are covered by the Jest tests
(`paywall-card`, `paywall-start-trial`, `mock-checkout-success`,
`listener-sub-row-*`, `listener-sub-cancel-*`).

## What's deferred to Turn 2
- Conversion funnel dashboard (event instrumentation + 5-stage tracking + UI)
- First-episode publish nudge (banner + email scaffolding) is Turn 3
