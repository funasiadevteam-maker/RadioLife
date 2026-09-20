# FUUSIC Rebrand — Technical Debt / Legacy Identifiers Report
_Generated during the RadioLife → FUUSIC consumer rebrand (Phase 1: visible branding)._

The **consumer brand is now FUUSIC**. Per the rebrand spec, technical identifiers
were intentionally **not** renamed to avoid production/migration risk. This file
tracks what remains and the recommended action.

## Central brand config (source of truth)
- Web: `/app/frontend/src/config/brand.js`
- Mobile: `/app/mobile/src/config/brand.ts`
- Backend: `/app/backend/core/brand.py`
Prefer reading brand strings from these going forward instead of hardcoding.

## Category A — MUST REMAIN (backward-compat / would break prod)
| Identifier | Where | Why keep |
|---|---|---|
| `bigfm_session` | auth cookie name (backend + clients) | Renaming logs out all users; separate migration. |
| `radiolife` design-variant key | `design` state / `design_radiolife/` dir (86 files) | Persisted per-user design selection; legacy variant, not New Look V2. |
| `bigfm:*` events | client event bus (~97) | Analytics/event continuity. |
| `com.bigfm.app` | iOS `bundleIdentifier` / Android `package` | Store identity; changing breaks installs/updates. |
| `/api/*` routes, DB collections (`social_*`, `live_*`, `user_ledgers`, …) | backend | Contract + stored data continuity. |
| `MAILGUN_DOMAIN=radiolife.app`, `MAILGUN_FROM` address | `backend/.env` | Verified sending domain. Display name is now forced to "FUUSIC" in `mailgun_client.send_email`; the @radiolife.app address stays until domain cutover. |

## Category B — SAFE TO RENAME LATER (cosmetic, low risk)
- `design_radiolife/` variant copy still says "RadioLife" internally (excluded from this pass). Only surfaces when the legacy `radiolife` design is explicitly enabled.
- Component symbols renamed by this pass (consistent, compile-clean): `RadioLifeStubPage`→`FUUSICStubPage` (App.js), `SellOnRadioLife`→`SellOnFUUSIC` (mobile), `isRadioLife`→`isFUUSIC` (Login.js).
- Frontend jest tests under `src/**/__tests__` had brand strings auto-updated to FUUSIC (not run by the app; verify in CI).

## Category C — DEFERRED (Phase 3 — needs external setup)
- **Production domain** `fuusic.com`: not switched. `radiolife.app` still used for links/emails. Switch only after DNS + TLS + OAuth origins are ready. Make domain config-driven.
- **Google/Apple OAuth**: origins/redirect URIs unchanged (still radiolife.app). Update at domain cutover.
- **App Store / Play**: display name asset is FUUSIC; do NOT resubmit or change bundle IDs here.
- **Mobile native icon/splash**: image assets replaced with the FUUSIC mark and splash bg set to `#0B1020`; only visible after a native build (Publish), not in Expo Go/web preview.

## Category D — KEEP AS-IS (not the consumer master brand)
- **FunAsia** and **Big FM** and partner **radio stations**: these are content/station brands that appear *inside* FUUSIC Listen. Not renamed.
- The **Radio** feature (e.g. "Start My Radio", "AI Radio", "News Radio"): radio is a FUUSIC feature, not the master brand — copy kept.

## Done in this pass (visible brand → FUUSIC)
- Central brand config (3 surfaces) + core `brand.py`.
- Metadata: `index.html` title/description/OG+Twitter, `manifest.json`, mobile `app.json` name + splash/adaptive bg.
- Favicons / PWA icons / OG image regenerated to the FUUSIC mark (`/frontend/public/fuusic-*`, favicons overwritten).
- Central lockup `BigFmBrand` → renders `FUUSIC` (city dropped).
- Header/footer split lockups (`AppShellV2`, `PublicHomeNewLookV2`, `PortalLogin`) + micro-taglines → "Listen · Connect · Play · Shop · Earn".
- Public coming-soon hero → "Everything you love, together." + broadened copy.
- `/about` → FUUSIC brand story + F·U·U·S·I·C meaning.
- Scoped token replace `RadioLife`→`FUUSIC` across 156 web + 40 mobile + 178 backend files (emails/subjects/notifications/copy/titles), excluding `design_radiolife/`, backend `tests/`.
- Email From **display name** forced to FUUSIC (address/domain untouched).

## Follow-up pass (iter163 fixes)
- Fixed all UPPERCASE `RADIOLIFE` display strings the first (CamelCase-only) pass missed: web login/pricing/radio/games/admin eyebrows+footers, mobile shop/play/dining eyebrows + login footer, and the "RADIOLIFE · DREAM MATCH" text baked onto Match Card PNGs → now "FUUSIC · DREAM MATCH".
- Mobile Stripe/onboarding `origin_url` and the listening-room share link no longer hardcode `https://radiolife.app` — they now use `EXPO_PUBLIC_BACKEND_URL` (correct in every environment).

## Still present ON PURPOSE (do not "fix" without a migration)
- **Domain / email addresses** (`radiolife.app`, `support@radiolife.app`, `partner@radiolife.app`, advisor `@advisor.radiolife`, soft-launch/UAT email link fallbacks): the live, working domain. Switch to `fuusic.com` only at the Phase-3 domain cutover (needs DNS/TLS/OAuth + real mailboxes). Do NOT invent fuusic.com emails before mailboxes exist.
- **Storage keys**: `radiolife-cart`, `radiolife-saved-for-later` (mobile) — renaming drops users' carts/saved items.
- **Design-variant key** `variant === "radiolife"` (~104 refs) + `design_radiolife/` screens — legacy design; not New Look V2.
- **Station/channel ids** e.g. default `activeChannel || 'radiolife'`, `station_type=radiolife`, Stripe metadata `radiolife_wallet`, JWT issuer `radiolife-ads`, seed `RadioLife Tee` (TEST fixture).

Recommended guard: a pre-commit grep on `/RADIO\s*LIFE/i` in `frontend/src` + `mobile` (excluding `design_radiolife/`) to stop brand-name drift.
