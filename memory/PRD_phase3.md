# BigFM — Phase 3 PRD (Premium + Stripe + Refactor)

## Goal
Free + Premium tier with Stripe Checkout (multi-currency: USD/AED/INR), premium
gates on 2 VIP-only channels, unlimited skips, and a clear architectural split
for future-phase scalability.

## What shipped (Phase 3)
- **Backend modular scaffolding**:
  - `/app/backend/routes/billing.py` — Stripe routes (`/api/billing/*`, `/api/webhook/stripe`)
  - `/app/backend/services/stripe_setup.py` — pricing plan registry (3 currencies)
  - `/app/backend/services/billing_service.py` — subscription mutations (grant/revoke/expire)
  - `/app/backend/services/currency.py` — header-only IP → currency detection
  - `/app/backend/models/billing.py` — Pydantic models (CheckoutRequest, SubscriptionOut, …)
  - `/app/backend/core/` (config, db, state, ranges, …) — shared scaffolding, ready for future migration
- **2 premium-only channels** seeded in `channels.py`: `vip_lounge`, `premium_mehfil` (different music_clock rotations)
- **Premium gates**:
  - `/api/radio/start` and `/api/radio/switch_channel` return 403 with `code: premium_required` when free users target a `premium_only` channel
  - `/api/radio/skip` unlimited for premium users (compliance.py)
- **Auth user surface**: `/api/auth/me` now returns `is_premium`, `premium_tier`, `reward_multiplier`, `subscription_status`, `subscription_period_end`, `cancel_at_period_end`
- **Frontend**:
  - `/pricing` page — gold premium card, currency picker, test banner, FAQ
  - `/billing/success` — polls `/api/billing/status/:id`, shows confetti + receipt + auto-redirect
  - Avatar gets gold ring + VIP badge when premium
  - Channel chips for `vip_lounge` / `premium_mehfil` show gold border + crown; locked for free users
  - Profile page has a `#billing` subscription tile
  - Skip control shows `Skip · ∞` for premium users
- **Seed**:
  - `premium@bigfm.dubai` / `PremiumTest123!` boots with a mocked active subscription doc
- **Test credentials**:
  - `/app/memory/test_credentials.md` updated with the new premium account

## What's deferred / next phase (carry-over)
- **Full `server.py` refactor** — billing logic now lives in routes/services/models/, but the radio engine (segments builder, prefetch, RJ scripts) still sits in `server.py`. Next phase task: move `_build_one_segment`, `_pick_next_track_personalized`, `_prefetch_next_segment`, `_resolve_channel`, `_log_play`, OG SSR landing, and admin upload routes into `routes/radio.py`, `routes/admin_tracks.py`, `routes/sharing.py`, and matching service modules. The new modular scaffolding under `core/`, `models/`, `services/` already supports this — the migration is mechanical.
- **Stripe Customer Portal** — Phase 3 ships `/billing/cancel` and `/billing/resume` (Mongo-only updates). A native Stripe Portal Session endpoint can be added when we move off the managed `sk_test_emergent` key.
- **Webhook signature secret** — `STRIPE_WEBHOOK_SECRET` is empty for Phase 3 (the Emergent library handles verification). Production must populate this when we flip to a self-managed Stripe account.
- **Ad-free enforcement** — `is_premium` flag is set, but Phase 4 will add the ad inventory + the actual ad-skipping path.

## Pricing matrix
| Currency | Price | Display |
|---------|-------|---------|
| USD | 12.00 | $12 |
| AED | 36.00 | AED 36 |
| INR | 999.00 | ₹999 |

All annual. Cancel anytime. No partial refunds. Test mode in Phase 3.

## Currency detection precedence
1. `?currency=USD|AED|INR` query param
2. `CF-IPCountry` request header → mapped via COUNTRY_TO_CURRENCY
3. `X-Country` request header → same mapping
4. Default → USD

Country → currency map: AE→AED, IN→INR, US/CA/AU/GB→USD, else USD.
