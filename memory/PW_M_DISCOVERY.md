# Phase PW-M.0 — Merchant Predict & Win Discovery Audit

_Generated 2026-07-26.  Read-only audit — zero code changes made._

## Executive Summary

- **Predexon integration**: FULLY_EXISTS.  Read-only client + admin surface + auto-resolve sweeper already wired.  Table: `predict_win_campaigns` with `external_market_id`, `data_provider_id`, `external_provider_snapshot`.
- **Existing Predict & Win customer game**: FULLY_EXISTS.  Consumer entry + wallet award + notification + QR check-in pipeline all live.
- **Prediction table `merchant_eligible` flag**: NEEDS TO BE ADDED (no field with that name; closest is `creator_type` which is `admin` / `business` / `advertiser` today).
- **Merchant RBAC ready**: YES.  `services/merchant_rbac_service.py` ships `ROLE_PERMISSIONS` for owner / manager / cashier / marketing / analytics_only with a `resolve_merchant_with_role(permission=...)` gate.  `businesses` collection has `owner_user_id`, `staff_users[]`, `stripe_*` onboarding fields, `merchant_status`.
- **Wallet award flow reusable**: YES.  `services/predict_win_award_pipeline.py::_credit_prize_to_user` already writes `user_wallet_items` with `item_type="prediction_award"`, `redemption_source="predict_win"`, `source_campaign_id`, `source_prize_id`.
- **Estimated new tables needed**: **1-2** — `predict_win_merchant_campaigns` (merchant activations linking a shared Predexon prediction to a specific merchant + coupon prize) plus `predict_win_merchant_pricing` singleton if we want per-merchant pricing.  A `merchant_eligible` bool + `predexon_pool` bool on `predict_win_campaigns` avoids a second table for the "one prediction → many merchant activations" pattern.
- **Estimated new services needed**: **2** — `predict_win_merchant_service.py` (activation lifecycle, prize→wallet mapping via existing pipeline) and a light `predict_win_merchant_matcher.py` if we auto-fan predictions to merchants by category/city.
- **Estimated new endpoints needed**: **~10-12** — split across `/api/merchant/predict-win/*` (create activation, list, submit-approval, resolve, analytics) and `/api/admin/predict-win/merchant/*` (approval queue, per-merchant auto-approve toggle).
- **Duplication risk (5)**:
  1. **`predict_win_business.py`** already lets a `business_radio` community-station owner author Predict & Win campaigns.  This is NOT the same as a MER.2 merchant (a `businesses` row).  Don't build a parallel authoring UI — reuse the same POST/PATCH/prize routes if practical.
  2. **`predict_win_self_serve.py`** already implements advertiser self-serve with Stripe pricing + `pending_payment` → `pending` → `approved`.  If merchant flow needs Stripe pricing too, extend rather than fork.
  3. **`game_campaigns`** (`services/game_service.py`) is a SEPARATE stack for `spin_win` / `scratch_win` and DOES have `merchant_id`.  Do NOT confuse with `predict_win_campaigns`.
  4. **`_credit_prize_to_user`** already writes `user_wallet_items` — the merchant redemption side (`merchant_staff.py::cashier_redeem`) reads `coupons`/`offers` tables, NOT `user_wallet_items`.  A merchant PW coupon prize needs to bridge the two (either issue a `coupons` row alongside the wallet item, or teach `cashier_redeem` to consume `user_wallet_items`).
  5. **`admin_predexon.py::/import-market`** already inserts a `predict_win_campaigns` doc in `approval_status="draft"`.  A merchant flow that also imports Predexon must NOT create a duplicate campaign — should link via `external_market_id` (there's already a 409 idempotency guard on that field for admin imports).

---

## 1. Predexon integration

**Status**: FULLY_EXISTS

**Files**:
- `/app/backend/services/predexon_client.py` — read-only httpx client, `x-api-key` auth, retry+logging.  Public API: `list_open_markets`, `get_market`, `get_market_resolution`, `normalize_outcomes`, `map_resolution_to_option_id`, `key_loaded`.
- `/app/backend/routes/admin_predexon.py` — 3 admin routes:
  - `GET  /api/admin/prediction/predexon/health`
  - `GET  /api/admin/prediction/external-markets` (list + already-imported markers)
  - `POST /api/admin/prediction/import-market`      (creates a **draft** `predict_win_campaigns` row)
- `/app/backend/scripts/seed_predexon_provider.py` — seeds `prediction_data_providers` row `provider_name="predexon"`.
- `/app/backend/services/predict_win_sweeper.py` — auto-resolves locked campaigns whose `data_provider` is Predexon by calling `get_market_resolution` and stamping `predict_win_resolutions.result_source="predexon"`.
- `/app/frontend/src/Admin/ImportPredexonModal.jsx` — admin UI to browse + import Predexon markets.

**Prediction table**: `predict_win_campaigns` (see Section 3).

**Fields written from a Predexon import** (`admin_predexon.py::import_market`, ~line 291-328):
```
_id, campaign_id, title, description, event_type ("general_prediction"),
event_label, category, city=None, region=None, language="en",
cover_image_url=None,
question: { prompt, answer_options: [{option_id: "opt_1", label: "…"}] },
start_time, lock_time, resolve_by,
winner_rules_json: {"selection_rule": "first_n_correct", "first_n": 1, "tiebreaker": "earliest"},
data_provider_id ("predexon" provider row),
compliance_settings_id,
external_market_id, external_market_url,
external_provider_snapshot: {provider_name: "predexon", title, category, imported_at},
creator_type: "admin",
approval_status: "draft",   # goes through admin approve/reject
approved_by, approved_at, rejected_by, rejected_at,
status: "draft",             # lifecycle: draft→scheduled→live→locked→resolved/cancelled
created_by, created_at, updated_at, deleted_at
```

**Sync/import cadence**:
- Import: **on-demand** via admin UI (`ImportPredexonModal.jsx` → `POST /import-market`).  No cron.
- Resolution: `predict_win_sweeper` runs every `PREDICT_WIN_SWEEP_INTERVAL_SEC` (default 60s) — bootstrapped in `server.py`.  For predexon-provider campaigns whose `resolve_by` has passed, it hits `get_market_resolution`, maps outcome → option_id, mints `predict_win_resolutions` row, fires the award pipeline.

**API-log collection**: `prediction_api_logs` (TTL-managed by `ensure_predexon_log_ttl`).  Never persists the API key.

**Reusable schema**: Above import shape is exactly what a merchant-activation flow can extend — same collection, additional fields.

**Gaps for PW-M**:
- No `merchant_eligible` flag on `predict_win_campaigns` yet — the admin must opt-in a Predexon-sourced campaign as available to merchants.
- No fan-out helper that reads a predexon-sourced campaign and creates N merchant activations.  (Section 7 discusses whether we add a `predict_win_merchant_campaigns` table or overload the existing collection.)

---

## 2. Existing Predict & Win game (customer side)

**Status**: FULLY_EXISTS

**Files**:
- `/app/backend/routes/predict_win_consumer.py` — customer endpoints, mounted at `/api/predict-win`:
  - `GET  /api/predict-win/active`                                            (list live/scheduled)
  - `GET  /api/predict-win/campaigns/{campaign_id}`
  - `POST /api/predict-win/campaigns/{campaign_id}/enter`  (make a pick)
  - `GET  /api/predict-win/my-picks`
  - `POST /api/predict-win/checkin`                                          (redeem venue QR)
- `/app/backend/services/predict_win_award_pipeline.py` — fan-out after a resolution row is minted.  `_credit_prize_to_user` handles points/BigCoin/badge/wallet-item.
- `/app/backend/services/predict_win_sweeper.py` — lifecycle cron (60s).
- `/app/backend/routes/predict_win_admin_sweeper.py` — admin control of the sweeper.
- `/app/backend/routes/predict_win_tv.py` — TV kiosk pairing.
- `/app/frontend/src/PredictWin.jsx`                — consumer SPA (`/predict-win`)
- `/app/frontend/src/PredictWinCheckin.jsx`  — QR landing (`/predict-win/checkin`)
- `/app/frontend/src/PredictWinKiosk.jsx`      — TV kiosk (`/tv/predict-win/:pairing_code`)
- `/app/frontend/src/StationPredictWinTab.jsx` — business_radio station owner authoring surface (`/station/:slug/predict-win`)

**Entry endpoint**: `POST /api/predict-win/campaigns/{campaign_id}/enter`.
- Body: `{selected_option_id, source_context?, venue_checkin_id?}`.
- Auth: `current_user` required.
- Gates: `approval_status=="approved"`, `status not in {resolved, cancelled}`, `lock_time>now`, `option_id` must be valid, age gate + geo gate via `compliance_settings_id`, `venue_checkin_id` required when `checkin_required=True`.
- Writes to `predict_win_entries` (implied — used by sweeper & pipeline).

**Result resolution mechanism**:
1. **Predexon provider** → auto via `predict_win_sweeper::sweep_locked_to_resolved` (60s cron), stamps `predict_win_resolutions.result_source="predexon"`.
2. **Manual provider** → admin `POST /api/admin/predict-win/campaigns/{id}/force-resolve`.
3. **Business creator** → `POST /api/business/predict-win/campaigns/{id}/resolve`.

**Winner determination logic**: `services/predict_win_award_pipeline.py::_select_winners`.  Reads `winner_rules_json.selection_rule` (default `first_n_correct` with `first_n=1`, tiebreaker `earliest`) and the entries sorted by `entered_at`.

**Wallet award flow** (already merchant-ready):
- `_credit_prize_to_user(db, user_id, prize, award_id, campaign_id)`:
  - **points / bigcoin** → `$inc users.bigcoin_balance` + PointsService mirror.  Returns `("delivered", None)`.
  - **passport_badge** → upsert `user_badges`.
  - **everything else** (`merchandise`, `experience`, `coupon`, `gift_card`, `ticket`, `free_item`, `prepaid_meal`, `product_sample`, `giveaway_entry`, `custom`) → insert `user_wallet_items` with `item_type="prediction_award"`, `redemption_source="predict_win"`, `source_campaign_id`, `source_prize_id`.  Returns `(wallet_item_id, "in_wallet")`.

**Redemption flow (existing QR redemption path)**:
- `merchant_staff.py::POST /api/merchant/{merchant_id}/cashier/redeem` reads the `coupons` collection (NOT `user_wallet_items`).  It requires `permission=can_redeem_coupons` (roles: owner/manager/cashier).  Atomically flips `coupons.status→"redeemed"` and inserts a `merchant_redemptions` audit row.
- `games_v2_winners.py::POST /api/redemptions/validate` (games_v2 stack) reads `user_wallet_items` where `qr_token=redemption_code`.  This is the reusable path for prediction-award coupons IF we mint a QR token onto the wallet item at award time.

**Reusable schema**: All of the above.

**Gaps for PW-M**:
- No path today that mints a `coupons` row (with merchant scoping + merchant expiry) from a `user_wallet_items` prediction-award.  PW-M.1 will need to either:
  - (a) Extend `_credit_prize_to_user` to ALSO write a `coupons` row when `prize.merchant_id` is set (so `merchant_staff::cashier_redeem` picks it up), OR
  - (b) Stamp a `qr_token` onto the `user_wallet_items` row so `games_v2_winners::/redemptions/validate` handles it.
- Option (a) matches the merchant cashier UX customers already know; option (b) is a smaller diff.

---

## 3. Existing prediction table schema

**Status**: FULLY_EXISTS  (`predict_win_campaigns`)

**Files**:
- Constants + Pydantic models in `/app/backend/routes/predict_win_admin.py` (lines 42-77).
- Inserts in `admin_predexon.py`, `predict_win_admin.py`, `predict_win_business.py`, `predict_win_self_serve.py`.

**Reusable schema** (union of all writers):
```
_id: str                            # == campaign_id
campaign_id: str                (pwc_<hex14>)
title, description, event_label, category, city, region, language
cover_image_url

# The prediction question
question: {
    prompt: str,
    answer_options: [{option_id: "opt_1", label: str}, …]
}

# Timing (all timezone-aware UTC)
start_time, lock_time, resolve_by: datetime

# Winner selection
winner_rules_json: {selection_rule, first_n, tiebreaker, …}
compliance_settings_id: str

# EVENT_TYPES (admin-only): sports_game, live_sports_moment (disabled),
#                                                    restaurant_bar, club_event, movie_entertainment,
#                                                    business_custom, bigfm_admin
# BUSINESS_EVENT_TYPES (business_radio station owner):
#                                                    restaurant_bar, club_event, business_custom
event_type: str

# Provider link
data_provider_id: str            (→ prediction_data_providers)
external_market_id: str        (→ Predexon market id)
external_market_url: str
external_provider_snapshot: {provider_name, title, category, imported_at}

# Creator identity
creator_type: "admin" | "business" | "advertiser"
created_by: user_id
business_station_slug, business_owner_user_id     # business_radio flow
advertiser_id, pricing_snapshot, payment_intent_id, submitted_at   # advertiser flow

# APPROVAL — state machine: draft → pending_review → approved → rejected
#                                (self-serve also uses: draft → pending_payment → pending → approved)
approval_status: str  ∈ APPROVAL_STATES = {"draft","pending_review","approved","rejected"}
approval_reason, approved_by, approved_at, rejected_by, rejected_at

# LIFECYCLE — state machine: draft → scheduled → live → locked → resolved / cancelled
status: str  ∈ LIFECYCLE_STATES = {"draft","scheduled","live","locked","resolved","cancelled"}

# Business_radio extras
checkin_required: bool

# Soft-delete + timestamps
deleted_at, created_at, updated_at
```

**Answers to specific questions**:
- **`merchant_eligible` flag**: **NOT PRESENT** — will need to add in PW-M.1.
- **`jurisdiction` / `region` field**: `region` present but free-text, not enforced.  A canonical `jurisdiction` (ISO country) lives instead on `prediction_compliance_settings` (referenced by `compliance_settings_id`), which drives the geo-gate at entry time (`predict_win_consumer.py::_user_passes_geo_gate`).  Adequate for PW-M — no new column needed for jurisdiction if we tie merchant activations to a compliance profile.
- **`compliance_status` / `admin_approved` flag**: `approval_status` covers this (draft / pending_review / approved / rejected).  `_STRIPE_OVERRIDES` and merchant `merchant_status` are separate and already in place.
- **Answer options**: EMBEDDED array `question.answer_options` (not a separate table).  Each option `{option_id, label}`.
- **Resolution status field values**: `LIFECYCLE_STATES = {draft, scheduled, live, locked, resolved, cancelled}`.  There is NO `suspended` state today — admin uses `cancelled` (irreversible).  Approval also has a separate `rejected` terminal.

**Gaps for PW-M**:
- **Add** `merchant_eligible: bool` (default False; admin toggles True when a Predexon campaign should be surfaced in the merchant activation catalog).
- **Add** `merchant_pool_activations: [{merchant_id, activation_id, activation_status, created_at}]` OR a separate `predict_win_merchant_campaigns` collection — pick ONE.  See Section 7 recommendation.
- **Consider** adding a `suspended` lifecycle state so admins can pause a live merchant campaign without cancelling.

---

## 4. Existing merchant RBAC & dashboard

**Status**: FULLY_EXISTS

**Files**:
- `/app/backend/services/merchant_rbac_service.py` — role→permission map + `resolve_merchant_with_role(merchant_id, user, permission)` gate.
- `/app/backend/services/merchant_status_service.py` — `MERCHANT_STATUSES = {draft, stripe_onboarding_pending, verification_pending, submitted, approved, active, restricted, payouts_disabled, suspended, rejected}`.  Effective-status derivation combines Stripe truth with admin decisions.
- `/app/backend/routes/merchant_dashboard.py` — merchant surface (MER.1).
- `/app/backend/routes/merchant_staff.py` — invite/role/cashier/redeem endpoints (MER.2).
- `/app/backend/routes/merchant_onboarding.py` — Stripe Connect onboarding.
- `/app/backend/routes/admin_merchants.py` — admin approval / suspend.
- `/app/frontend/src/pages/merchant/*.jsx` — Merchant Shell + tabs (Dashboard, Games, Payouts, PrepaidMeals, PaymentLinks, GiftCards, etc.) — all use `useDesignVariant` for dual-design.

**Roles / permissions** (`ROLE_PERMISSIONS`):
```
owner:            invite_staff, edit_profile, create_links, refund, view_analytics,
                          redeem_coupons, edit_hours, view_payouts, manage_stripe, view_transactions
manager:          invite_staff, edit_profile, create_links, refund, view_analytics,
                          redeem_coupons, edit_hours, view_payouts, view_transactions
cashier:          redeem_coupons, view_analytics_limited
marketing:      create_links, view_analytics, view_transactions
analytics_only: view_analytics, view_payouts, view_transactions
```
Admin god-mode is a union of all permissions (via `_is_admin(user)`).

**`businesses` collection schema** (from `services/business_profile_service.py`, `routes/business_portal.py`):
```
business_id (str), slug (unique), name, category / category_id,
owner_user_id,  staff_users: [{user_id, role, active, added_at}],
stripe_account_id, stripe_charges_enabled, stripe_payouts_enabled,
stripe_details_submitted, stripe_onboarding_status,
merchant_status ∈ MERCHANT_STATUSES,
locations: [{lat, lng, address, hours, …}]  (per business_portal writes)
```
Merchant-owner check pattern:
```python
biz, role = await resolve_merchant_with_role(
    db, merchant_id=mid, user=user, permission="can_redeem_coupons")
```

**Reusable schema**: Everything above — the RBAC gate is the exact primitive we need for `POST /api/merchant/predict-win/*` endpoints.

**Gaps for PW-M**:
- Need a new permission `can_manage_predict_win` (or reuse `can_create_links` — it's already granted to owner + manager + marketing).  Recommend adding a fresh perm so merchants can grant PW campaign authorship independently.

---

## 5. Existing wallet + redemption stack

**Status**: FULLY_EXISTS

**Files**:
- `/app/backend/services/predict_win_award_pipeline.py::_credit_prize_to_user` (see Section 2 for shape).
- `/app/backend/services/games_v2.py` — writes `user_wallet_items` with a `qr_token` (used by games_v2_winners redemption).
- `/app/backend/services/games_v2_winners_redemptions.py` — validates via `user_wallet_items.qr_token`.
- `/app/backend/routes/merchant_staff.py::cashier_redeem` — validates via `coupons` collection.
- `/app/backend/routes/local_commerce.py::redeem/{qr_token}` — partner / QR flow.
- `/app/backend/routes/games_v2_public.py` + `/app/backend/routes/games_v2_winners.py` — public redemption endpoints.
- QR generation: `qrcode` lib (see imports in `games_v2.py`, `payment_link_service.py`, `local_commerce.py`, `games_v2_public.py`).

**`user_wallet_items` schema** (union of prediction + games_v2 writers):
```
_id / wallet_item_id, user_id,
item_type ("prediction_award" | "spin_win" | "scratch_win" | …),
prize_kind (points / merchandise / experience / coupon / gift_card / ticket / free_item / prepaid_meal / product_sample / giveaway_entry / custom / bigcoin),
title, description, value_amount, value_currency, image_url,
status ("in_wallet" | "redeemed" | "expired" | "revoked"),
redemption_source ("predict_win" | "games_v2" | …),
source_award_id, source_campaign_id, source_prize_id,
qr_token (games_v2 only today; PW would need this for staff scan),
expires_at (games_v2 only today),
created_at, redeemed_at, staff_user_id, merchant_id (on redeem)
```

**Redemption endpoints**:
- `POST /api/merchant/{merchant_id}/cashier/redeem`      — reads `coupons`; requires MER.2 RBAC.
- `POST /api/redemptions/validate`                                          — reads `user_wallet_items.qr_token`; body carries `business_id`.
- `POST /api/local-commerce/redeem/{qr_token}`             — legacy partner path.

**Reusable schema**: Yes — pick between the two redemption paths (see Section 2 gaps).

**Gaps for PW-M**:
- The prediction-award wallet items today have NO `qr_token`, NO `expires_at`, NO `merchant_id`.  For merchant PW prizes we need to add all three so the existing staff-scan UX works out of the box.

---

## 6. Existing admin Predict & Win controls

**Status**: FULLY_EXISTS

**Files**:
- `/app/backend/routes/predict_win_admin.py` (1261 lines) — full CRUD + approval + resolve.
- `/app/backend/routes/predict_win_self_serve.py` — advertiser + admin approval extension.
- `/app/backend/routes/predict_win_admin_sweeper.py` — sweeper pause/resume + status.
- `/app/frontend/src/Admin/PredictWinCampaigns.jsx` — admin list + approval UI.
- `/app/frontend/src/Admin/AdminPredictWinSelfServe.jsx` — pricing config + advertiser approval queue.

**Admin approval endpoints**:
```
GET    /api/admin/predict-win/campaigns                                             (list, filter by status/approval_status/event_type)
GET    /api/admin/predict-win/approval-queue                                     (approval_status=pending_review)
POST   /api/admin/predict-win/campaigns                                             (create)
PATCH  /api/admin/predict-win/campaigns/{id}                                    (edit while draft/rejected)
DELETE /api/admin/predict-win/campaigns/{id}                                    (soft-delete)
POST   /api/admin/predict-win/campaigns/{id}/submit-approval  (draft → pending_review)
POST   /api/admin/predict-win/campaigns/{id}/approve                (pending_review → approved, status→scheduled/live)
POST   /api/admin/predict-win/campaigns/{id}/reject                  (pending_review → rejected)
POST   /api/admin/predict-win/campaigns/{id}/force-resolve      (locked → resolved manually)
POST   /api/admin/predict-win/campaigns/{id}/prizes                    (add prize)
PATCH  /api/admin/predict-win/campaigns/{id}/prizes/{prize_id}
DELETE /api/admin/predict-win/campaigns/{id}/prizes/{prize_id}
GET    /api/admin/predict-win/event-types
GET    /api/admin/predict-win/providers
GET    /api/admin/predict-win/compliance          (list settings)
POST   /api/admin/predict-win/compliance          (create)
GET    /api/admin/predict-win/compliance/{settings_id}
PATCH  /api/admin/predict-win/compliance/{settings_id}
GET    /api/admin/predict-win/pricing                    (self-serve pricing singleton)
PATCH  /api/admin/predict-win/pricing
GET    /api/admin/predict-win/pending                  (advertiser pending queue)
POST   /api/admin/predict-win/{id}/approve       (advertiser flow)
POST   /api/admin/predict-win/{id}/reject          (advertiser flow)
```

**Admin RBAC access**: All routes require `Depends(require_admin)` (from `auth.py`).

**Reusable schema**: Yes — the same approval endpoints will drive merchant activation approval.  Only need a per-merchant filter on the list/queue endpoints (e.g., `?creator_type=merchant`).

**Gaps for PW-M**:
- No "per-merchant auto-approve" toggle today.  A `businesses.pw_auto_approve: bool` (default False, admin toggles per merchant) is a one-line addition.
- No "suspend live merchant campaign" endpoint — only `cancelled`.  Add a `POST /suspend` and a `POST /resume` if we want a soft pause.

---

## 7. Existing game template + campaign model

**Status**: PARTIALLY_EXISTS

**Two SEPARATE campaign stacks live in the codebase** — do NOT confuse:

### A. `predict_win_campaigns` (Predict & Win)
- Owner: this audit.
- Sources: admin, business_radio station owner, advertiser.
- Prize model: `predict_win_prizes` subcollection (attached via `POST /campaigns/{id}/prizes`).
- No `merchant_id` column today.  Business-radio flow uses `business_station_slug` + `business_owner_user_id`; advertiser flow uses `advertiser_id`.

### B. `game_campaigns` (Spin & Win / Scratch & Win) — `services/game_service.py`
- Owner: PG.1 (games platform).
- `GAME_TYPES = ("spin_win", "scratch_win")`.
- Has **`merchant_id`** column (Section: game_service.py line 126, 505, 630).
- Bound to `game_templates` (predefined wheel/scratch layouts).
- Prizes embedded in the doc: `prizes: [{prize_id, display_label, display_color, weight, quantity_won, …}]`.
- Fed to `games_v2` service which writes `user_wallet_items` with `qr_token` + `expires_at` + `merchant_id`.

**Does anything link a `predict_win_campaign` to a `businesses` row today?**
- **No direct FK.**  `business_station_slug` links to `community_radio_stations.slug` for the business_radio flow.  For MER.2 merchants (a `businesses` row), there is **no link at all** on `predict_win_campaigns`.

**Reusable pattern (from `game_campaigns`)**: Add a `merchant_id` column to `predict_win_campaigns` for merchant activations, and mirror the `game_campaigns` create/list pattern in a `predict_win_merchant_service.py`.

**Gaps for PW-M**:
- **Recommendation** (my proposed shape for user confirmation before PW-M.1):
  - **Do NOT create a new `predict_win_merchant_campaigns` collection.**  Reuse `predict_win_campaigns` and add:
    - `merchant_id: Optional[str]`                                              (present → this is a merchant activation)
    - `merchant_eligible: bool = False`                                    (admin flag on the Predexon-sourced parent campaign)
    - `parent_campaign_id: Optional[str]`                             (points to the shared Predexon parent when this row is a merchant activation)
    - `creator_type: "merchant"` (new value, sibling to admin/business/advertiser)
  - The "one Predexon prediction → many merchant campaigns" pattern becomes: admin imports Predexon → sets `merchant_eligible=True` on the parent → each merchant activation is a NEW row with `parent_campaign_id` pointing to it, prizes owned by the merchant.  Resolution cascades from parent to children via the sweeper (small extension).
  - Prizes remain in the existing `predict_win_prizes` subcollection scoped to the merchant activation.

---

## 8. Dual-design status

**Status**: PARTIALLY_EXISTS

**Files that already use `useDesignVariant`**:
- All `pages/merchant/*.jsx` (Shell + Games + PrepaidMeals + Payouts + PaymentLinks + GiftCards + Status + Apply + Onboarding + DashboardStub) — merchant surface is fully dual-design.
- All `pages/advertiser_v2/*.jsx` — advertiser surface is fully dual-design.
- `pages/play/*.jsx`, `pages/pay/*.jsx`, `WalletV2.jsx`, `BusinessProfile.jsx`, `AdminAdvertisersAD1.jsx`, `AdminFlagshipStations.jsx`.

**Files that DO NOT use `useDesignVariant`**:
- `/app/frontend/src/PredictWin.jsx`                                                          (consumer)
- `/app/frontend/src/PredictWinKiosk.jsx`
- `/app/frontend/src/PredictWinCheckin.jsx`
- `/app/frontend/src/StationPredictWinTab.jsx`                                (business_radio station owner authoring)
- `/app/frontend/src/Advertiser/AdvertiserPredictWin.jsx`
- `/app/frontend/src/Admin/AdminPredictWinSelfServe.jsx`
- `/app/frontend/src/Admin/PredictWinCampaigns.jsx`
- `/app/frontend/src/Admin/ImportPredexonModal.jsx`

**Reusable pattern**: The `merchant/*.jsx` files import from `@/hooks/useDesignVariant` and branch classnames.

**Gaps for PW-M**:
- If we mount a new **merchant PW campaign builder** inside `MerchantShell.jsx` (e.g., `/merchant/{mid}/predict-win/*`), it will inherit the dual-design automatically.
- The consumer PW view (`PredictWin.jsx`) is single-design today.  Not a blocker for PW-M — merchant activations will render inside the existing consumer list via `predict_win_consumer.py::/active`, so they visually match whatever the customer currently sees.

---

## Constraints observed

- **Zero code changes made** in this phase.
- **Zero DB migrations** run.
- **One new file** created: `/app/memory/PW_M_DISCOVERY.md` (this document).

## Assumptions confirmed / flagged

- **Predexon exists** — confirmed.  Client + admin surface + sweeper all live.  ✅
- **Admin approval default** — matches existing model; `APPROVAL_STATES` already implements draft → pending_review → approved / rejected.  Adding a `businesses.pw_auto_approve` per-merchant toggle is a one-field addition.  ✅
- **Multi-merchant same-prediction** — recommended shape uses `parent_campaign_id` on merchant activations pointing to a shared Predexon-sourced parent (see Section 7).  No collection duplication.
- **No trading UI ever** — FORBIDDEN_LEXICON_RE in `predict_win_admin.py` already rejects `bet|wager|gamble|spread|odds|buy_shares|sell_shares|order_book|exchange` in any text field.  Reused by the business + advertiser + admin authoring paths.  ✅
- **`_credit_prize_to_user`** already routes all non-points / non-badge prizes to `user_wallet_items` — no need to re-implement award delivery.  ✅

## Ready-to-build shortlist for PW-M.1 (for user approval)

Given the audit, PW-M.1 minimum viable slice:

1. **Backend**:
   a. Add fields to `predict_win_campaigns`: `merchant_id`, `merchant_eligible`, `parent_campaign_id`, plus extend `creator_type` enum with `"merchant"`.
   b. Add `businesses.pw_auto_approve: bool` (default False).
   c. New file `/app/backend/routes/predict_win_merchant.py` mounting `/api/merchant/predict-win/*` — create-activation, list, submit-approval, resolve-passthrough, analytics.  Use `resolve_merchant_with_role(permission="can_manage_predict_win")`.  Add the new permission to `owner` + `manager` roles.
   d. Extend `_credit_prize_to_user` — when `prize.merchant_id` is set, also stamp `qr_token` + `expires_at` + `merchant_id` on the `user_wallet_items` row so the existing `cashier_redeem` OR `redemptions/validate` path can consume it.
   e. Sweeper cascade — when a parent Predexon campaign resolves, fan out the same `winning_option_id` to all child merchant activations.

2. **Frontend**:
   a. `/app/frontend/src/pages/merchant/MerchantPredictWin.jsx` — mounted inside `MerchantShell` (inherits dual-design).  Tabs: **Catalog** (list Predexon-eligible parents) / **My Activations** / **Prizes** / **Analytics**.
   b. Admin: extend `/app/frontend/src/Admin/PredictWinCampaigns.jsx` with a `merchant_eligible` toggle on each Predexon-imported campaign card.
   c. Admin queue: extend `AdminPredictWinSelfServe.jsx` (or a sibling tab) with a "Merchant activations pending approval" list.

3. **Test surfaces** (curl):
   - Admin toggles `merchant_eligible=true` on a Predexon campaign.
   - Merchant lists eligible catalog.
   - Merchant creates activation with 1 coupon prize.
   - Merchant submits for approval; admin approves (or auto-approves if `pw_auto_approve=true`).
   - Parent Predexon campaign resolves → child activations resolve → winners get `user_wallet_items` with `merchant_id` + `qr_token` → merchant cashier scans → `merchant_redemptions` row minted.

**Estimated LOC**: ~600 backend + ~350 frontend (a Merchant Shell tab reuses existing shell chrome).

_End of audit._
