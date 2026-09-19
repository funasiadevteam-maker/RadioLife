# RadioLife — Team Test Login Credentials

Preview app: https://mobile-games-v2.preview.emergentagent.com
Portal / staff login: `/portal/login`   ·   Consumer login: `/login`

> App logins only. This file intentionally contains **no** API keys or secrets.

## App accounts (email / password)
| Role | Email | Password | Notes |
|------|-------|----------|-------|
| Admin | admin@bigfm.dubai | AdminPass123! | Full admin panel (/admin), soft-launch, appearance switch |
| Business owner | test@bigfm.dubai | TestUser123! | Owns a merchant + Premium; dining merchant "Test Bistro" |
| Premium (owner + Dining Club) | demo@bigfm.dubai | DemoPass123! | Owns 2 merchants, Premium, active Dining Club, $10 Fun Pizza gift card |
| Premium (ad-free) | premium@bigfm.dubai | PremiumTest123! | Ad-free consumer |
| Free consumer | freeuser@bigfm.dubai | FreePass123! | Plain free user (sees ads/banners) |

## Mobile (Expo)
- Password login is disabled on mobile — tap **"Try the demo"** to sign in as `demo@bigfm.dubai`.

## Handy test values
- Shop redeem staff PIN: **4242** (web `/shop/redeem`, mobile `/shop-redeem`)
- Stripe test card: **4242 4242 4242 4242**, exp 12/34, CVC 123, any ZIP (preview uses Stripe test keys)
- Merchant ticket codes: web (test@) `TEST1234` / `TEST5678`; mobile (demo@) `DEMO1234` / `DEMO5678`

_Note: engineering-only secrets (Partner API keys, Google OAuth, Stripe) live in `/app/memory/test_credentials.md` — share those only with engineers who need them._
