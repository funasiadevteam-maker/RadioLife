# Phase 36e — Stripe TEST-mode live API flip — handoff

**Date**: 2026-06-05 22:05 UTC
**Key fingerprint**: `sk_test_5...9wrs` (Stripe secret key, TEST environment)
**Publishable fingerprint**: `pk_test_5...dELgv` (also plumbed into frontend + mobile .env for future Elements use; not wired)

## What flipped
- `/app/backend/.env`: `STRIPE_MODE=live`, `STRIPE_SECRET_KEY=sk_test_...`, `STRIPE_PUBLISHABLE_KEY=pk_test_...`
- `/app/frontend/.env`: added `REACT_APP_STRIPE_PUBLISHABLE_KEY=pk_test_...`
- `/app/mobile/.env`: added `EXPO_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...`
- Backend restarted via `sudo supervisorctl restart backend`.

## Verification (in-pod)
```
stripe_mode():              live
is_live():                       True
stripe.api_key set:        True
stripe.api_key prefix:  sk_test_...

[1] Customer.list reachable                 → ok
[2] Product.create                                      → prod_UeOe4n4Sqvw7EV
[3] Price.create                                          → price_1Tf5qsL7GrHu8gquts5JWz5R ($9.99/mo, 7d trial)
[4] Product.retrieve                                  → name="BigFM Smoke Product (auto-cleanup)", active=True
[5] Price.retrieve                                      → recurring=month, trial_period_days=7
[6] Cleanup → archived both
```

Subscription-plan path is **fully exercised against the real Stripe TEST API**.

## ⚠️ Connect Express requires user activation
Stripe returned `InvalidRequestError: You can only create new accounts if you've signed up for Connect`
when calling `Account.create(type="express", ...)`. **No code change fixes this** — it's a one-time
user action in the Stripe dashboard:

→ https://dashboard.stripe.com/connect → "Activate Stripe Connect"

After activation, `POST /api/creators/{creator_id}/stripe-account` will produce real `acct_*` IDs
and onboarding URLs without any code change. The abstraction works correctly; Connect is just gated
by Stripe at the account-config layer.

## Webhook reminder
- `STRIPE_WEBHOOK_SECRET=` is still empty. The abstraction layer's webhook signature verifier
  is bypassed when this is unset (a log warning is emitted).
- To receive real Stripe-sent webhooks: register endpoint in Stripe dashboard →
  Developers → Webhooks pointing at
  `https://mobile-games-v2.preview.emergentagent.com/api/webhooks/stripe`. Copy the signing
  secret into `STRIPE_WEBHOOK_SECRET` in `/app/backend/.env` and restart.
- Until then, the admin mock-fire endpoint `POST /api/admin/stripe/mock/fire-webhook`
  remains the way to trigger synthetic webhook events for testing.

## Rollback procedure (if anything explodes)
```bash
# 1) Edit /app/backend/.env:
STRIPE_MODE=mock
# (leave STRIPE_SECRET_KEY in place — abstraction ignores it in mock mode)
# 2) Restart:
sudo supervisorctl restart backend
# 3) Confirm:
python3 -c "from services import stripe_client; print(stripe_client.stripe_mode())"
# → mock
```

## CRITICAL — DO NOT do without explicit per-dispatch user greenlight
- Never set `STRIPE_MODE=live` with a `sk_live_` key (production money).
- Never push the secret key into git or logs. The `.env` file is gitignored; verify before any
  `git add -A`.
