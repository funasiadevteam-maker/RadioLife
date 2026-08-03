# Phase 23 — Harmonize games_v2 + Add Missing CouponTools Primitives

**Status**: SPEC — re-scoped 2026-06-06 after audit.
**Supersedes**: prior "Phase 21 — Remaining Game Templates" entry AND the
original Phase 23 "build from scratch" framing (which was written before the
existing `games_v2` footprint was inventoried).
**Source**: user dispatch captured verbatim + Session 1 audit reality check.
**Companion doc** (REQUIRED reading before any code): `phase23_session1_audit.md`

---

## Reality check (this is NOT a greenfield build)

A mature `games_v2` system is **already in production** carrying live traffic:

- 1,008 game_campaigns rows (724 draft + 241 active + 42 pending_approval + 1 paused)
- 1,373 game_prizes rows
- 3,013 game_analytics_events rows
- 7 game_templates (5 of the 5 MVP types already exist as templates; only `pick_a_card` is net-new)
- 94 user_wallet_items rows including 29 with `source='game_win'` (these ARE the "game_winners" the spec calls for)
- 2,157 LOC of routes (`games_v2.py`, `games_v2_public.py`, `games_v2_phase8c.py`) + 3,613 LOC of services
- Frontend: 10 files calling `/api/games_v2/*`
- Mobile: 2 files calling `/api/games_v2/*`
- Backend logs show listeners actively playing campaigns `cmp_121e55c624b840` and `cmp_7480b468ec9243` as of 2026-06-06

**Any session that proposes a parallel `/api/games/*` route tree, a new
`backend/models/games.py` that redefines existing collections, or seeding the
5 MVP templates into `game_templates` (4 of 5 already exist) should be HALTED
and corrected.** The Phase 23 work is **harmonization + missing-primitive
additions**, not a from-scratch redesign.

URL space stays at `/api/games_v2/*` indefinitely. Renaming to `/api/games/*`
is deferred to a future tech-debt phase behind a backward-compat alias (per
the Phase 19 Part C precedent that kept the `channels` alias for mobile).

For the full inventory + field-name diff table + per-session re-scope, see
`phase23_session1_audit.md`.

---

## Goal (unchanged from original framing)

A simple, fun, instant-win promotional game system modeled on CouponTools.
Two creator tracks (BigFM admin + business advertiser). Simple wizard: pick
game → pick prize → set win rules → customize design → publish → user plays →
reward goes to wallet → QR redemption at the business.

The 80% case is already shipped in `games_v2`. Phase 23 closes the remaining
20%: missing audit primitives, harmonized template names, wizard refinement,
listener-side polish.

## NOT this (compliance line — UNCHANGED)
- NOT gambling, casino, betting, or wagering
- NO cash betting / paid chance games
- These are PROMOTIONAL coupon + reward games only
- Terms + odds disclosure where required; "no-purchase-necessary" language where required; age gating where needed; admin approval for business games

## Two creator tracks (status: ALREADY SHIPPED in games_v2)

### Admin-created (platform games) — SHIPPED
BigFM points, badges, premium trial credit, sponsor coupons, platform giveaways.
Backed by `is_platform_funded=True` campaign flag today; Phase 23 Session 2 adds
explicit `creator_type='admin'` column for clarity.

### Business-created (advertiser dashboard) — SHIPPED
Restaurant 10% off / free dessert / prepaid lunch. Salon 20% off haircut.
Dentist new-patient offer. Movie ticket giveaway. Grocery coupon. Club guest-list entry.

Business prize options (existing `game_prizes.prize_type` values cover most):
coupon, free item, % discount, $ discount, gift card, prepaid lunch/dinner,
product sampler, appointment offer, event ticket, movie ticket, concert
ticket, raffle entry, loyalty points, custom prize.

## Game types — MVP shortlist (5)

| MVP name | Existing template `game_type` | Status |
|---|---|---|
| Spin & Win | `spin_wheel` | EXISTS — UI label harmonize only |
| Scratch & Win | `scratch_card` | EXISTS — UI label harmonize only |
| Mystery Box | `mystery_box` | EXISTS — name match |
| Pick-a-Card | — | **NET-NEW** — add template + frontend component in Session 1.5 + 4 |
| Simple Quiz | `quiz` | EXISTS — UI label harmonize only |

## Phase 2 games (deferred from MVP frontend) — clarified

Note: `slot_machine` and `memory_match` already exist as templates in the live
DB (created earlier in the project). The Phase 2 deferral means **"do not
promote to MVP listener-facing template picker"** — NOT "delete from schema".
Existing campaigns using these templates continue to work; they're just
hidden from new-campaign template selection in the MVP wizard.

- Slot Machine Promo (3-reel match; template already in DB; promotional only, no cash)
- Memory Match (template already in DB)
- Match2Win (template NOT in DB; future net-new)
- Slide Puzzle (NOT in DB; future net-new)
- Catch Game (NOT in DB; only when not in driving mode; cross-link to Phase 39 safety_mode)

`word_puzzle` (existing 7th template) is **deprecated** — fold into Simple
Quiz variants per original spec. Will be hidden from new template picker
and marked `active=False` after a deprecation window confirms no active
campaigns depend on it.

## 7-step builder wizard (status: PARTIAL — single-page form exists)

Existing `frontend/src/AdvertiserGames.js` already supports advertiser
campaign creation in a single-page form. Phase 23 Session 3 refactors that
into the 7-step wizard per spec:

**Step 1 — Choose Game**: card grid with preview animation, best-use-case, difficulty level, recommended prize type per game.

**Step 2 — Choose Prize Type**: BigFM Points / Coupon / Free Item / Gift Card / Prepaid Meal / Product Sampler / Appointment Offer / Event Ticket / Movie Ticket / Concert Ticket / Giveaway Entry / Custom Prize. Business creator MUST pick a prize before publishing.

**Step 3 — Configure Prize Inventory**: prize name, description, value, quantity available, max wins per user, expiration date, redemption method, QR redemption enabled, staff validation required, terms.
- For Spin Wheel: multiple prize segments
- For Scratch/Mystery/Pick: prize tiers (grand / medium / small / consolation / no-win)

**Step 4 — Set Win Rules** (KEEP SIMPLE): Everyone wins | random win % | fixed prize quantity | first X players win | one play per user | one win per user | one play per day | must listen X min | must check in at business | must scan QR | must save coupon to wallet | must provide phone/email with consent. Show a simple "Prize Odds" table.

**Step 5 — Customize Design**: logo, brand colors, background image, title, short description, button text, win message, lose message, terms link, sponsor logo, station logo. Mobile-first beautiful animated display.

**Step 6 — Choose Placement**: Play & Win tab | post-listening-milestone | during ad | post-AI-RJ sponsor read | restaurant check-in | live trivia event | QR landing page | business profile page | podcast episode | push notification | route/location offer (cross-links Phase 39 location intelligence) | festival campaign.

**Step 7 — Publish**: preview mobile game, preview wallet item, preview QR redemption, confirm prize inventory + terms. Business-created → submit for admin approval via existing `POST /api/games_v2/advertiser/campaigns/{id}/submit_for_approval`.

## Listener experience

Game card: name + sponsor + prize preview + Play Now + Save for Later + time left + terms link.

On WIN: celebration animation + prize + Add to Wallet + Redeem Now + Get Directions + Share + Play Again (if allowed).
On LOSE: friendly message + optional consolation points + optional sponsor offer.

Wallet item: prize name, business name, expiration, QR code, redemption instructions, terms, staff-validation button if required. **Already shipped** in `frontend/src/Wallet.js` + backend `user_wallet_items` collection.

## BigFM Points listening milestone games (status: DORMANT — engine exists, table empty)

`services/game_unlock_engine.py` (417 LOC) + `user_game_unlocks` collection
already exist. The engine is not yet wired to the live listening-time
aggregator (collection has 0 docs in prod). Phase 23 Session 5 turns this on.

Examples: 15 min → Scratch & Win for 25 pts; 30 min → Spin & Win for 50-500 pts; 1 hour → Mystery Box; 5-day streak → bonus prize; complete live trivia → Pick-a-Card; sponsor station → sponsor game.

UI: "Unlocked Games" section in Play & Win tab (added Session 5).

## Business prize catalog (per business type — unchanged)

- **Restaurant**: 10%/15% off, free dessert/appetizer/drink (where allowed), prepaid lunch/dinner, family meal, gift card
- **Salon/Spa**: 15% off service, free consultation, free add-on, gift card, appointment discount
- **Dentist/Doctor/Service**: new-customer offer, consultation discount, appointment voucher, free estimate, service credit
- **Movie/Theater**: ticket giveaway, popcorn combo, discount ticket, movie badge
- **Concert/Event**: ticket giveaway, VIP upgrade, merch discount, after-party pass
- **Retail/Grocery**: product sample, coupon, gift card, bundle discount

## Display

Mobile-first, colorful, premium, fast, thumb-friendly, no clutter, no complex rules, confetti/win animation, optional sound effect, optional station/game stinger.

**TV/display mode** for venue games / live trivia big-screen: QR to play + game name + prize + sponsor logo + countdown + winner announcement. (Post-MVP)

## Admin controls (status: ALREADY SHIPPED)

Existing endpoints at `/api/games_v2/admin/*`: queue, approve, reject,
force_pause, resume, adjust_inventory, templates activate/deactivate,
unlock_grant, unlock_rules CRUD. Plus Phase 8c additions: inventory
reconcile, redemption audit log CSV, webhook delivery sweep.

## Business dashboard controls (status: ALREADY SHIPPED)

Existing endpoints at `/api/games_v2/advertiser/*`: create campaign, choose
prize (via campaign create payload), set inventory, set odds, design game,
publish (via submit_for_approval), view players (analytics), view winners
(via wallet_items join — to be formalized in Session 1.5), scan QR rewards,
export leads (Phase 8c), retarget players, clone past game.

## Analytics

Existing `game_analytics_events` collection (3,013 rows) + endpoints under
`/api/games_v2/advertiser/campaigns/{id}/analytics{,.csv}`. Phase 23 Session 5
extends with: leads captured, cost per play/win/redemption, revenue
attributed — using new `game_redemptions` audit table from Session 1.5.

## Database tables — SEE AUDIT DOC

See `phase23_session1_audit.md` §1 (existing footprint), §4 (field-name diff
table), and §5 (the 2 genuinely missing collections) for the full collection
inventory + per-field mapping verdict.

**Summary**:
- 8 of 9 spec collections **already exist** with live data
- 1 collection (`game_winners`) is **functionally already provided** by
  `user_wallet_items where source='game_win'` — add a `won_at` column + helper
  view, do NOT create a separate collection
- 1 collection (`game_redemptions`) is **genuinely missing** — add in
  Session 1.5 as the only net-new collection
- 0 destructive renames; 5 ADD-column migrations across Sessions 1.5 and 2

## MVP build scope (re-scoped)

Items 1-3 from original spec (admin creator / business creator / prize setup
wizard) are **already shipped in games_v2** — see audit doc. Phase 23 work
is harmonization + missing-primitive additions.

Remaining build scope (Sessions 1.5 through 7):
1. **Session 1.5** — `game_redemptions` collection + `won_at` column +
   transactional redeem wrapper + winners endpoint + backfill scripts
2. **Session 2** — campaign schema columns (placement_rules_json,
   eligibility_rules_json, win_rules_json, creator_type) + wizard backend
   validation harness + admin-creator endpoint
3. **Session 3** — 7-step wizard frontend (refactor existing AdvertiserGames.js)
4. **Session 4** — per-game subcomponent extraction + Pick-a-Card net-new
   component + Phase 2 game hiding (slot/memory/word_puzzle)
5. **Session 5** — wire `game_unlock_engine.py` to listening-time aggregator +
   "Unlocked Games" section + analytics extensions
6. **Session 6** — Wallet/QR polish + admin moderation queue audit (folds
   into Phase 19 Part B when that ships)
7. **Session 7** — mobile parity via `e1_expo_frontend_dev`

## Cross-phase dependencies (UNCHANGED — still valid)

- **Phase 18** (ad-stack) — game placement on "during ad" and "post-AI-RJ sponsor read" reuses the existing ad-decisioning service
- **Phase 19 Part B** (moderation queue, deferred) — existing `/api/games_v2/admin/queue` + approve/reject already in place; Phase 19 Part B should **wrap** these (add unified moderation_queue join view) rather than replace them
- **Phase 36e** (creator subscriptions, shipped) — premium-tier features could include "create unlimited business games" or "higher prize value caps"
- **Phase 39** (location intelligence + AI RJ personas, deferred) — placement option "route/location offer" reads from Phase 39's frequent-place + corridor detection; AI RJ persona can announce game wins ("Bhidu, you just won a free chai!")
- **Phase 22** (bulk upload, shipped) — game prize images / business logos / game backgrounds should use the same Tigris pipeline (`services/object_storage.py`). Note: existing `game_uploaded_assets` (61 rows) currently uses local disk — Tigris migration deferred (see audit §8 risk #7)

## Estimated build size (re-scoped down)

- Session 1.5 — missing primitives + backfills: **0.5 session** (was 1)
- Session 2 — wizard backend (schema additions, no new collections): **1 session**
- Session 3 — 7-step wizard frontend (refactor existing): **1 session** (was 1.5)
- Session 4 — game display extraction + Pick-a-Card net-new: **1 session** (was 1.5)
- Session 5 — unlock engine wiring + analytics extensions: **1 session**
- Session 6 — wallet/QR/moderation audit + polish: **0.5 session** (was 1)
- Session 7 — mobile parity: **1 session** (was 1.5)

**Total: ~6 sessions to MVP**, down from original ~7-8 estimate, because
~40% of the build was already shipped under games_v2.

## Pre-build asks (still blocking — UNCHANGED)

- Confirm region(s) for legal compliance — sweepstakes / promotional-game rules vary US state-by-state, India, EU. The "no-purchase-necessary" + age-gate copy needs region-aware variants.
- Confirm whether Slot Machine Promo (Phase 2 game) is acceptable in target markets — even non-cash slot mechanics are restricted in some jurisdictions (e.g. UK, some Indian states). Spec defaults to "promotional only" but legal review recommended before Phase 2.
- Decide whether business-created games should be FREE for all advertisers or gated behind a paid advertiser tier — affects pricing model + the advertiser dashboard.
