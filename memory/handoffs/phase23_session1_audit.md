# Phase 23 — Session 1 Audit (Option A)

**Status**: AUDIT-ONLY. No code, no schema changes, no route additions.
**Outcome**: original Session 1 dispatch (build from scratch) was unsafe — a
mature `games_v2` system is already in production. This doc maps what exists,
what is genuinely missing, and how Sessions 2-7 are re-scoped to modify in
place rather than build parallel.

**Companion read**: `/app/memory/handoffs/phase23_promotional_games_redesign.md`
(rewritten in same commit pair to acknowledge this reality).

---

## 1. Existing footprint — game_* collections in MongoDB

Probed against live DB on 2026-06-06.

| Collection | Doc count | Primary purpose | Owning routes | Owning services |
|---|---:|---|---|---|
| `game_templates` | 7 | MVP + Phase 2 game type catalog (spin_wheel, scratch_card, quiz, mystery_box, slot_machine, memory_match, word_puzzle) | `games_v2.py::/admin/templates*` | `games_v2.py` |
| `game_campaigns` | 1,008 | Campaign records (admin + business). Status dist: draft=724, active=241, pending_approval=42, paused=1 | `games_v2.py::/advertiser/campaigns*`, `/admin/queue`, `/campaigns/{id}*` | `games_v2.py` |
| `game_prizes` | 1,373 | Prize rows per campaign (multi-prize per campaign supported) | `games_v2.py::/advertiser/campaigns/{id}/prizes*` (implied — surfaced via campaign payload) | `games_v2_inventory.py` |
| `game_sessions` | 105 | Per-user play sessions. Result dist: win=28, won=1 (typo bug), lose=12, in-progress=64 | `games_v2.py::/campaigns/{id}/start`, `/sessions/{id}/submit`, `/sessions/{id}/claim_to_wallet` | `games_engine.py`, `games_v2.py` |
| `game_compliance_settings` | 1,008 | Per-campaign compliance metadata (odds_disclosure, age_restriction, geo, terms, approval_status, approved_by, rejection_notes). 1:1 with game_campaigns. | implicit via campaign creation flow | `games_v2_compliance.py` |
| `game_analytics_events` | 3,013 | Impressions/starts/completions/wins/saves/redemptions event log | `games_v2.py` (writes); `games_v2.py::/advertiser/campaigns/{id}/analytics*` (reads) | `games_v2.py` |
| `game_redemption_rules` | 1,008 | Per-campaign redemption config (requires_qr, requires_staff_validation, requires_location, one_time_use, expiration_days, terms_url) — separate from compliance_settings | implicit via campaign creation | `games_v2.py` |
| `game_inventory_ledger` | 551 | Append-only audit log of prize inventory deltas (campaign_id, prize_id, delta, inventory_after, reason, session_id, ts) | `games_v2_phase8c.py::/admin/inventory_reconcile*` | `games_v2_inventory.py` |
| `game_webhook_events` | 6,352 | Outbound webhook delivery queue + history (advertiser-configurable endpoints) | `games_v2_phase8c.py::/advertiser/webhooks*`, `/admin/webhooks/run_delivery_sweep` | `games_v2_webhooks.py` |
| `game_landing_pages` | 746 | Public landing pages (slug → campaign) + QR PNG cache | `games_v2_public.py::/api/public/game/{slug}*` | (inline in routes file) |
| `game_lead_forms` | 89 | Per-campaign lead capture form definitions | `games_v2_phase8c.py::/advertiser/campaigns/{id}/lead_form*` | `games_v2_leads.py` |
| `game_lead_submissions` | 59 | Captured lead rows (consent-gated) | `games_v2_phase8c.py::/campaigns/{id}/submit_lead`, `/advertiser/.../leads*` | `games_v2_leads.py` |
| `game_uploaded_assets` | 61 | Sponsor logos / backgrounds / station logos for campaigns | `games_v2.py::/advertiser/assets/upload`, `/assets/{filename}` | (inline) |
| `game_rate_limits` | 2 | Per-user / per-IP rate-limit counters | implicit | `games_v2.py` |
| `user_game_unlocks` | 0 | Listening-milestone unlock grants. Schema exists, never populated — `services/game_unlock_engine.py` exists but evidently not yet wired to listening-time triggers | `games_v2.py::/admin/unlock_grant`, `/me/unlocks`, `/admin/unlock_rules*` | `game_unlock_engine.py` |
| `rj_game_mentions_log` | 96 | AI RJ persona's audio mentions of active games | `games_v2.py::/rj_mention_log` | `games_v2.py` |
| `user_wallet_items` | 94 | **Functionally = game_winners + game_redemptions today.** Has campaign_id, prize_id, session_id, qr_token, qr_image_base64, redeemed_at, redeemed_by_actor, redemption_method, value_amount, value_currency, expires_at, status. Source dist: `game_win`=29, other=65 | `games_v2.py::/sessions/{id}/claim_to_wallet`, `/wallet/{id}/generate_qr`, `/redeem/{qr_token}` | `games_v2.py` |
| `game_sessions_legacy_phase5` | 25 | v1 → v2 migration leftover (Phase 5/8c) | none active | `games_v2.py::/admin/migrate_phase5_games` (one-shot) |
| `games_legacy_phase5` | 3 | v1 → v2 migration leftover | none active | (frozen) |
| `games` | 3 | **v1 leftover** (Phase 3 era — Spin/Trivia/Lyric POC). Still served by `routes/games.py` tagged `games-legacy`. | `routes/games.py::/api/games/{state,spin/play,trivia/*,lyric/*}` | `games_engine.py` |

---

## 2. Routes inventory

### `/api/games_v2/*` — main canonical surface (1,369 LOC, `routes/games_v2.py`)

**Listener (auth-required):**
- `GET /play_and_win` — list active campaigns for the listener
- `GET /campaigns/{campaign_id}` — single campaign detail
- `POST /campaigns/{campaign_id}/start` — start session
- `POST /sessions/{session_id}/submit` — submit play result
- `POST /sessions/{session_id}/claim_to_wallet` — convert win → wallet item
- `POST /sessions/{session_id}/save_for_later`
- `POST /campaigns/{campaign_id}/save_for_later`
- `POST /wallet/{wallet_item_id}/generate_qr` — generate QR for redemption
- `POST /redeem/{qr_token}` — staff scan endpoint
- `POST /user/driving_mode` / `PATCH /user/driving_mode` — driving safety toggle
- `GET /me/unlocks` — listener's milestone unlocks
- `GET /me/active_game_announce` — RJ hook
- `POST /rj_mention_log` — log RJ audio mention

**Advertiser (business owner):**
- `GET /advertiser/templates`
- `GET /advertiser/campaigns`
- `POST /advertiser/campaigns` — create draft
- `PATCH /advertiser/campaigns/{campaign_id}` — edit draft
- `GET /advertiser/campaigns/{campaign_id}`
- `POST /advertiser/campaigns/{campaign_id}/submit_for_approval`
- `POST /advertiser/campaigns/{campaign_id}/clone`
- `GET /advertiser/campaigns/{campaign_id}/analytics`
- `GET /advertiser/campaigns/{campaign_id}/distribution`
- `POST /advertiser/assets/upload` — sponsor logo / background

**Admin:**
- `GET /admin/queue` — pending-review campaigns
- `POST /admin/campaigns/{campaign_id}/approve`
- `POST /admin/campaigns/{campaign_id}/reject`
- `POST /admin/campaigns/{campaign_id}/force_pause`
- `POST /admin/campaigns/{campaign_id}/resume`
- `POST /admin/campaigns/{campaign_id}/adjust_inventory`
- `GET /admin/templates`, `POST /admin/templates/{id}/activate|deactivate`
- `POST /admin/migrate_phase5_games`
- `POST /admin/unlock_grant`
- `GET|POST|PATCH /admin/unlock_rules`, `POST /admin/unlock_rules/{id}/toggle_active`

**Asset proxy:**
- `GET|HEAD /assets/{filename}` — serves uploaded assets

### `/api/games_v2/*` — Phase 8c additions (588 LOC, `routes/games_v2_phase8c.py`)

Mounted under SAME `/api/games_v2` prefix:
- Lead forms: `POST|GET|DELETE /advertiser/campaigns/{id}/lead_form`, `GET /advertiser/campaigns/{id}/leads`, `GET .../leads.csv`, `GET /campaigns/{id}/lead_form`, `POST /campaigns/{id}/submit_lead`
- Webhooks: `POST|GET /advertiser/webhooks`, `POST /advertiser/webhooks/{id}/rotate_secret`, `POST .../test`, `DELETE .../webhooks/{id}`, `GET .../deliveries`
- Leaderboards: `GET /advertiser/leaderboard`, `GET /admin/leaderboard`
- Inventory reconcile: `GET|POST /admin/inventory_reconcile/{id}`, `GET /admin/inventory_reconcile_alerts`, `POST /admin/inventory_reconcile/run_daily_scan`
- Admin sweeps: `POST /admin/webhooks/run_delivery_sweep`
- Exports: `GET /admin/redemption_audit_log.csv`, `GET /advertiser/campaigns/{id}/analytics.csv`

### `/api/public/game/*` — public landing pages (91 LOC, `routes/games_v2_public.py`)
- `GET /{slug}` — public landing
- `GET /{slug}/qr.png` — cached QR PNG

### `/api/games/*` — **v1 legacy** (109 LOC, `routes/games.py`, tag `games-legacy`)
- `GET /state`
- `POST /spin/play`
- `POST /trivia/start`, `POST /trivia/answer`
- `POST /lyric/start`, `POST /lyric/answer`

Backed by 3 docs in `games` collection + the small POC engine. Likely retired
in spirit but still routed. **Deprecation candidate** — confirm no frontend
caller before drop.

---

## 3. Services inventory

| Service | LOC | Role |
|---|---:|---|
| `services/games_v2.py` | 1,656 | Main game engine for v2 — campaign lifecycle, session run, prize selection (RNG + probability_weight), wallet creation, QR mint, redemption validation |
| `services/games_v2_compliance.py` | 107 | Compliance row mgmt (odds disclosure, age restriction, geo, terms) — separate from `game_redemption_rules` |
| `services/games_v2_inventory.py` | 146 | Prize inventory decrement (atomic with `game_inventory_ledger` append) + reconcile |
| `services/games_v2_leaderboard.py` | 116 | Advertiser + admin leaderboard aggregations |
| `services/games_v2_leads.py` | 342 | Lead form CRUD + submission + CSV export |
| `services/games_v2_webhooks.py` | 493 | Outbound webhook delivery (signature, retry, sweep) |
| `services/game_unlock_engine.py` | 417 | Listening-milestone unlock rules → user_game_unlocks (currently dormant — table is empty in prod) |
| `services/games_engine.py` | 336 | **v1 engine** — Spin / Trivia / Lyric POC. Still imported by `routes/games.py`. Deprecation candidate alongside v1 routes. |

---

## 4. Field-name diff table

Spec field name (column 1) → existing field name (column 2) → verdict.

### `game_templates` (7 rows live)

| Spec | Existing | Verdict |
|---|---|---|
| `id` | `template_id` | RENAME spec → existing (existing pattern is `{collection}_id` everywhere in codebase) |
| `name` | `name` | KEEP |
| `game_type` | `game_type` | KEEP (but value rename — see below) |
| `description` | `description` | KEEP |
| `preview_image_url` | `preview_image_url` | KEEP |
| `preview_animation_url` | — | ADD (nullable; populate when frontend ships animations) |
| `default_config_json` | `default_config_json` | KEEP |
| `active` | `active` | KEEP |
| — | `max_prizes`, `min_prizes`, `version`, `created_at` | KEEP existing (not in spec but useful) |

**game_type value rename** (data migration, 7 rows):
| Existing value | Spec value | Verdict |
|---|---|---|
| `spin_wheel` | `spin_and_win` | OPTIONAL rename — UI label change is sufficient; storage value can stay |
| `scratch_card` | `scratch_and_win` | OPTIONAL rename — same |
| `quiz` | `simple_quiz` | OPTIONAL rename — same |
| `mystery_box` | `mystery_box` | KEEP |
| — | `pick_a_card` | **ADD** — net-new MVP game type (no existing template) |
| `slot_machine` | (Phase 2 deferred) | KEEP existing row; do NOT surface in MVP frontend template picker. Spec deferral now means "don't promote to MVP", not "delete from schema". |
| `memory_match` | (Phase 2 deferred) | KEEP existing row; same as above |
| `word_puzzle` | — | Existing extra; **DEPRECATE** in frontend template picker (fold into Simple Quiz variants per spec). Leave row with `active=False` after deprecation phase. |

**Verdict summary**: 1 net-new template (`pick_a_card`), 1 deprecation toggle (`word_puzzle.active=False`), 0 destructive renames. Storage `game_type` values stay; UI labels harmonize.

### `game_campaigns` (1,008 rows live)

| Spec | Existing | Verdict |
|---|---|---|
| `id` | `campaign_id` | KEEP existing pattern |
| `creator_type` | — (inferred via `is_platform_funded`+`created_by_user_id`+`business_id`) | **ADD** explicit enum column `creator_type ∈ {admin,business,advertiser}`. Backfill: `is_platform_funded=True` → admin, else business/advertiser based on advertiser_id presence |
| `created_by_user_id` | `created_by_user_id` | KEEP |
| `business_id` | `business_id` | KEEP |
| `advertiser_id` | `advertiser_id` | KEEP |
| `campaign_id` (spec lists this twice?) | `campaign_id` | (spec typo — already the row id) |
| `game_template_id` | `template_id` | KEEP existing name |
| `title` | `title` | KEEP |
| `description` | `description` | KEEP |
| `objective` | `objective` | KEEP |
| `status` | `status` | KEEP (values: draft, pending_approval, active, paused — spec calls it `published` for active, harmonize via UI mapping) |
| `start_time` | `start_at` | OPTIONAL rename — UI mapping is cheaper; field rename touches 1,008 rows + every query. KEEP existing. |
| `end_time` | `end_at` | KEEP existing (same reasoning) |
| `placement_rules_json` | (partial — in `targeting_json`) | **ADD** dedicated `placement_rules_json` column; backfill empty `{}`; new wizard writes here. `targeting_json` keeps audience targeting. |
| `eligibility_rules_json` | (in `game_config_json`) | **ADD** dedicated column; migration extracts `eligibility` subkey from `game_config_json` |
| `design_config_json` | `game_config_json` (mixed) + `brand_colors_json` + `sponsor_logo_url` + `sponsor_name` | KEEP existing split — they already work. New wizard writes the same fields. |
| `win_rules_json` | (in `game_config_json`) | **ADD** dedicated column; migration extracts `win_rules` subkey |
| `terms_text` | (in `game_redemption_rules.terms_url` + `game_compliance_settings.terms_text`) | KEEP in compliance_settings; do NOT duplicate on campaign |
| `approval_status` | (in `game_compliance_settings.approval_status`) | KEEP in compliance_settings (1:1 join is cheap); do NOT duplicate. Spec is wrong to put it on campaign. |
| `created_at` | `created_at` | KEEP |
| — | `bid_amount_cents`, `bid_type`, `budget_cents`, `funded_source`, `open_to_all`, `public_slug`, `rejection_reason`, `updated_at`, `approved_at`, `approved_by_user_id` | KEEP existing (advertiser bid/budget mechanics + audit columns; spec doesn't mention but production needs them) |

### `game_prizes` (1,373 rows live)

| Spec | Existing | Verdict |
|---|---|---|
| `id` | `prize_id` | KEEP |
| `game_campaign_id` | `campaign_id` | KEEP existing (consistent with rest of codebase) |
| `prize_type` | `prize_type` | KEEP |
| `title` | `title` | KEEP |
| `description` | `description` | KEEP |
| `value` | `value_amount` + `value_currency` | KEEP existing split (better for FX and multi-region) |
| `quantity_total` | `inventory_total` | OPTIONAL rename — KEEP existing (matches `inventory_remaining` and `inventory_ledger`) |
| `quantity_remaining` | `inventory_remaining` | KEEP existing |
| `probability_weight` | `probability_weight` | KEEP |
| `max_per_user` | `max_per_user` | KEEP |
| `expiration` | (in `expiration_policy_json`) | KEEP existing (richer than a single field) |
| `redemption_method` | `redemption_method` | KEEP |
| `coupon_id` / `offer_id` / `product_id` / `gift_card_id` / `event_id` | `linked_offer_id` + `linked_badge_id` | EXISTING is a single FK; spec wants typed FK per prize_type. **ADD** typed columns lazily as new prize types ship; for MVP `linked_offer_id` covers coupon+offer+gift_card. |
| `points_amount` | (in `value_amount` when prize_type=points) | KEEP existing convention |
| `active` | `active` | KEEP |
| — | `requires_location`, `requires_staff_validation`, `created_at` | KEEP existing |

---

## 5. Two genuinely missing collections

### `game_winners`

**Today**: this role is filled by `user_wallet_items where source='game_win'` (29 rows). That collection already carries `campaign_id`, `prize_id`, `session_id`, `qr_token`, `qr_image_base64`, `redeemed_at`, `redeemed_by_actor`, `value_amount`, `value_currency`, `expires_at`, `status`.

**Verdict**: do NOT create a separate `game_winners` collection. The spec field list is a 95% overlap with `user_wallet_items`. Instead, **add a missing view** (Mongo aggregation or denormalized query helper) that selects from `user_wallet_items where source IN ['game_win','game_consolation']` and projects spec-shaped winner records. Optionally add `won_at` column to `user_wallet_items` (currently inferred from `created_at`).

**Schema decision for Session 1.5**:
- ADD column `user_wallet_items.won_at` (defaults to `created_at` on backfill, written on new wins)
- ADD helper `services/games_v2.py::list_winners_for_campaign(campaign_id, ...)` reading from wallet_items
- ADD endpoint `GET /api/games_v2/advertiser/campaigns/{campaign_id}/winners` returning spec-shaped rows
- NO new collection

**Backfill query** (idempotent, dry-run-able):
```python
db.user_wallet_items.update_many(
    {"source": "game_win", "won_at": {"$exists": False}},
    [{"$set": {"won_at": "$created_at"}}],
)
```

### `game_redemptions`

**Today**: redemption events are stored inline on `user_wallet_items` via
`redeemed_at` + `redeemed_by_actor` + `redemption_method`. No append-only audit
table exists for games specifically. The `redemption_audit_log` collection (176
rows) is for **ad pod** redemptions, NOT games (keys: `partner_token_id`,
`qr_token_prefix`, `outcome`, `reason`, `ts`, `ip`).

**Verdict**: this one IS genuinely missing as a structured audit table. Create
it in Session 1.5.

**Schema decision for Session 1.5**:
```
game_redemptions {
  redemption_id: str (uuid),
  wallet_item_id: str (FK → user_wallet_items),
  campaign_id: str,
  prize_id: str,
  user_id: str,
  business_id: str | None,
  redemption_code: str,         # last 6 of qr_token, for staff display
  qr_token: str,                # full token (matches wallet_items.qr_token)
  redeemed_by_staff_id: str | None,
  redeemed_at: datetime,
  scanned_at: datetime,          # may differ from redeemed_at on review-required flows
  status: enum {pending, completed, voided, failed},
  reason: str | None,            # for failed/voided
  ip: str | None,
  ts: datetime,
}
```

Indexes: `(campaign_id, redeemed_at)`, `(wallet_item_id)` unique, `(qr_token)` unique.

**Backfill query** (one-shot script for Session 1.5):
```python
async for wi in db.user_wallet_items.find({"source": "game_win", "redeemed_at": {"$ne": None}}):
    await db.game_redemptions.update_one(
        {"wallet_item_id": wi["wallet_item_id"]},
        {"$setOnInsert": {
            "redemption_id": new_uuid(),
            "wallet_item_id": wi["wallet_item_id"],
            "campaign_id": wi["campaign_id"],
            "prize_id": wi["prize_id"],
            "user_id": wi["user_id"],
            "business_id": wi.get("business_id"),
            "redemption_code": wi["qr_token"][-6:],
            "qr_token": wi["qr_token"],
            "redeemed_by_staff_id": wi.get("redeemed_by_actor"),
            "redeemed_at": wi["redeemed_at"],
            "scanned_at": wi["redeemed_at"],
            "status": "completed",
            "ts": wi["redeemed_at"],
        }},
        upsert=True,
    )
```

Existing `POST /api/games_v2/redeem/{qr_token}` already does the wallet-side
update; Session 1.5 wraps it to also insert a `game_redemptions` row in the
same transaction (or close-to-it, given Mongo single-doc atomicity — see
"Risks" §8).

---

## 6. Frontend / mobile caller impact

### Frontend (`/app/frontend/src/`) — 10 files reference games_v2

| File | What it does |
|---|---|
| `PlayAndWin.js` | listener tab — calls `GET /play_and_win`, `GET /campaigns/{id}`, start/submit/claim |
| `GamePlayer.js` | individual game UI (5 game types) — calls campaign start/submit/save-for-later |
| `Wallet.js` | wallet items + QR display + redemption — calls `/wallet/{id}/generate_qr` |
| `LeadForm.js` | post-game lead capture — calls `/campaigns/{id}/lead_form`, `/submit_lead` |
| `RjActionCard.js` | RJ-driven game CTA — calls `/me/active_game_announce`, `/rj_mention_log` |
| `AdvertiserGames.js` | advertiser dashboard — list/create/edit campaigns |
| `AdvertiserPhase8c.js` | webhooks + lead forms UI |
| `AdvertiserInsights.js` | analytics + leaderboard |
| `AdminGamesApproval.js` | admin queue — calls `/admin/queue`, `/admin/campaigns/{id}/approve|reject` |
| `AdminPhase8c.js` | admin reconcile + sweeps |

### Mobile (`/app/mobile/app/`) — 2 files reference games_v2

| File | What it does |
|---|---|
| `play-and-win.tsx` | mobile listener tab |
| `game/[campaignId].tsx` | mobile game player |

**Conclusion**: Option C (full `/api/games_v2/*` → `/api/games/*` rename) blast
radius is **12 caller files** (10 web + 2 mobile) plus every test that calls
v2 paths. NOT worth doing in this phase. **Re-scoped plan keeps URLs at
`/api/games_v2/*`** indefinitely; rename can be a future tech-debt phase
behind a backward-compat alias (per the Phase 19 Part C precedent that kept
the `channels` alias for mobile).

---

## 7. Re-scoped Sessions 2-7 plan

All sessions modify in place under `/api/games_v2/*`. No parallel `/api/games/*`
tree introduced. URL space stays canonical at `_v2`.

### Session 1.5 — **Missing primitives** (next dispatch)
- ADD `game_redemptions` collection + Pydantic model in
  `backend/models/games.py` (new file, scoped to NEW models only —
  does NOT redefine existing collections)
- ADD `user_wallet_items.won_at` column + backfill
- ADD `services/games_v2_redemptions.py` (new) — transactional wrap around
  existing `redeem/{qr_token}` to also write `game_redemptions` audit row
- ADD `GET /api/games_v2/advertiser/campaigns/{cid}/winners` (winners view
  reading from wallet_items)
- ADD `GET /api/games_v2/admin/redemptions?campaign_id=&from=&to=` (admin
  redemption audit query)
- Backfill scripts: `scripts/backfill_phase23_winners_won_at.py`,
  `scripts/backfill_phase23_game_redemptions.py`
- Tests: idempotency of both backfills, transactional behavior of new redeem
  wrapper (winner+redemption row both written), winners endpoint shape

**Change from original spec**: original said "create 9 new collections + new
models/games.py + new routes/games.py". New plan creates 1 new collection
(`game_redemptions`), adds 1 column to existing collection, models file scoped
to only the new primitives.

### Session 2 — **Wizard backend** (per spec, no URL changes)
- ADD `game_campaigns.placement_rules_json`, `eligibility_rules_json`,
  `win_rules_json`, `creator_type` columns + backfills
- Extend `POST /api/games_v2/advertiser/campaigns` payload to accept the
  3 new JSON columns + `creator_type` (default inferred)
- Extend `PATCH /api/games_v2/advertiser/campaigns/{id}` to accept same
- ADD `POST /api/games_v2/admin/campaigns` (admin-creator path — distinct
  from advertiser path, auto-approved, sets `creator_type=admin`)
- Validation harness in `services/games_v2.py::validate_for_submit()` —
  checks ≥1 prize, valid win_rules, terms in compliance_settings, date sanity
- ADD `POST /api/games_v2/sessions/{id}/play` as a clearer alias for `/submit`
  (per spec naming), keep `/submit` as backward-compat alias

**Change from original spec**: no new collections; extend existing campaigns
schema with 3 columns; no rename of `/submit`, just an alias.

### Session 3 — **Wizard frontend (web)**
- Extend `AdvertiserGames.js` to 7-step wizard (currently 1-page form)
- Add Pick-a-Card to game type picker (template already missing — added in
  Session 1.5 seed bump)
- Reuse existing `AdvertiserPhase8c.js` lead form step

**Change from original spec**: no new components for admin path — admin
creator surface in `AdminGamesApproval.js` extended with an "admin-create"
button that routes to the same wizard with `creator_type=admin` pre-set.

### Session 4 — **5 MVP game display components**
- Existing `GamePlayer.js` already handles spin / scratch / quiz / mystery /
  slot — refactor to per-game subcomponent files
- ADD `PickACardGame.jsx` (genuinely new)
- Hide `slot_machine`, `memory_match`, `word_puzzle` from listener-facing
  template picker but KEEP working for already-created campaigns (rollback
  safety)

**Change from original spec**: not a from-scratch build — extraction +
hiding existing.

### Session 5 — **Listening-milestone unlocks + analytics**
- Wire `services/game_unlock_engine.py` into the listening-time aggregator
  (currently dormant — `user_game_unlocks` collection exists but empty)
- Surface "Unlocked Games" section in `PlayAndWin.js`
- Extend existing `AdvertiserInsights.js` with: leads captured, cost per
  play/win/redemption, revenue attributed (uses `game_analytics_events` +
  new `game_redemptions` audit)

**Change from original spec**: unlock engine ALREADY exists; this session
turns it on rather than building it.

### Session 6 — **Wallet + QR + listener Play & Win polish + admin moderation**
- Audit existing `Wallet.js` against spec wallet item fields (likely 90%
  match)
- Audit existing `AdminGamesApproval.js` against spec admin queue (already
  surfaces queue + approve/reject)
- Add admin-only `GET /api/games_v2/admin/redemptions.csv` export
- Per dispatch instruction: when Phase 19 Part B (unified moderation queue)
  later ships, **fold this admin queue into it**. Until then, in-place
  approval flow stays canonical.

**Change from original spec**: 90% audit + delta work; little net-new code.

### Session 7 — **Mobile mirror**
- Audit existing `mobile/app/play-and-win.tsx` + `mobile/app/game/[id].tsx`
  against any new fields shipped in Sessions 2-6
- Coordinate with `e1_expo_frontend_dev`
- DO NOT touch mobile in any other phase

**Change from original spec**: mobile already has the surface; this is parity
patching not a from-scratch mobile build.

---

## 8. Risks

1. **`game_sessions.result` data quality** — 1 row has `result='won'`, 28 have
   `result='win'`, 12 have `result='lose'`, 64 have `result=null` (sessions
   abandoned mid-flight). Session 1.5 should fix the `won`→`win` typo via
   migration and decide whether null-result sessions count as "abandoned" or
   "in-progress".

2. **Transactional redemption write** — Mongo is single-document atomic only.
   The new redeem wrapper writes BOTH `user_wallet_items.status=redeemed` AND
   inserts a `game_redemptions` row. Failure between the two leaves an
   orphaned wallet update or missing audit row. Mitigation: use Mongo
   transactions (replica set required) OR write redemption row FIRST with
   `status=pending`, then wallet update, then redemption row → `completed`.
   The latter is safer because the audit row remains even if wallet update
   fails. Session 1.5 implements this pattern.

3. **Inventory decrement already transactional** — `services/games_v2_inventory.py`
   uses `findOneAndUpdate` + appends `game_inventory_ledger` row. Session 1.5
   does NOT touch this; "transactional inventory decrement" requirement from
   original dispatch is already met.

4. **v1 `/api/games/*` routes still mounted** — `routes/games.py` tag
   `games-legacy` serves Spin/Trivia/Lyric POC against 3 docs in `games`
   collection. Verify no frontend caller (grep showed `frontend/src/Wallet.js`
   refs but to `/api/games_v2/*` paths, not v1). Likely safe to remove in a
   future cleanup phase, NOT in Phase 23. Documented for future deprecation.

5. **`user_game_unlocks` collection is empty** — schema exists, engine exists
   (`services/game_unlock_engine.py`, 417 LOC), but never populated. Session 5
   will discover whether the engine is wireable to current listening-time
   aggregator or needs a redesign. Risk: engine may have stale assumptions
   about Phase 5 data shape.

6. **`game_landing_pages` (746 rows) not in spec** — public landing pages with
   QR PNG cache. Spec doesn't acknowledge this surface. Decision deferred —
   either keep as-is (it works) or fold into Phase 23 design as "share game
   via QR". Documented for Session 3/6 wizard work.

7. **`game_uploaded_assets` (61 rows) uses ?? storage** — not Tigris per the
   recent Phase 22c migration. Sponsor logos / backgrounds are on local disk.
   Future Phase 22d local-cleanup window will need to handle these too. Out
   of scope for Phase 23 itself.

8. **`game_webhook_events` (6,352 rows) growth** — outbound webhook delivery
   log grows unboundedly. Sweep / retention policy needed eventually. Out of
   scope for Phase 23.

9. **Spec mismatches** noted in §4 are non-destructive — every spec field
   that exists by a different name can be mapped via the existing column. No
   spec field requires a DATA migration of the 1,008+1,373 live rows. Only
   3 ADD-column migrations needed in Session 2 (placement_rules_json,
   eligibility_rules_json, win_rules_json, creator_type) and 1 in Session 1.5
   (won_at on wallet_items).

10. **Phase 19 Part B integration** — original dispatch said "in-place
    approval flow becomes unified queue when Phase 19 Part B ships". Current
    `/admin/queue` + approve/reject endpoints are already in-place and live.
    Phase 19 Part B should be designed to **wrap** these existing endpoints
    (add a unified moderation_queue join view) rather than replace them.
    Document this when Phase 19 Part B is re-dispatched.

---

## 9. Decision summary (one-line per question)

- Q: Build 9 new collections? **A**: NO — 8 already exist with live data;
  add 1 (`game_redemptions`).
- Q: Build new `routes/games.py` + `models/games.py`? **A**: NO models file
  scoped to NEW primitives only; routes extend `routes/games_v2.py` in place.
- Q: Rename `/api/games_v2/*` → `/api/games/*`? **A**: NO — 12 caller files
  (10 web + 2 mobile) + every test. Defer to future tech-debt phase.
- Q: Seed 5 MVP templates? **A**: ADD only `pick_a_card` (1 net-new); the
  other 4 exist (`spin_wheel`, `scratch_card`, `mystery_box`, `quiz`).
- Q: Build in-place admin approval flow? **A**: ALREADY EXISTS at
  `/admin/queue` + `/admin/campaigns/{id}/approve|reject`.
- Q: Transactional inventory decrement? **A**: ALREADY EXISTS
  (`services/games_v2_inventory.py` + `game_inventory_ledger`).
- Q: Migrate live data? **A**: 5 ADD-column migrations across Sessions 1.5
  and 2 (`won_at`, `placement_rules_json`, `eligibility_rules_json`,
  `win_rules_json`, `creator_type`). NO destructive renames. NO row deletes.
