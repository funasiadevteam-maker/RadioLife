# Phase CLAIM.1 — Discovery Audit

_Generated 2026-07-27.  Read-only audit — zero code changes in Step 0._

## Executive Summary

**Phase 42-C claim infrastructure already ships** — a functional
station-claim + owner-override + admin-review pipeline is already live
in production.  CLAIM.1 is a **delta** on top of 42-C, not a green-field
build.  Roughly **~60% of the acceptance criteria are already satisfied**;
CLAIM.1 needs to add the missing 40% — file-upload proof docs, an admin
approval queue for *edits* (not just claims), banner + description-audio
uploaders, and a Claim Radio Hub landing page.

### What already exists (Phase 42-C, live)

| Concern | Component | Status |
|---|---|---|
| Claim collection | `radio_station_claims` (7 indexes via `station_claim_service.ensure_indexes`) | ✅ |
| Owner profile | `station_owner_profiles` (one per user, links `owner_profile_id` back to station) | ✅ |
| Station↔claim link | `imported_radio_stations.claim_status/claim_id/owner_profile_id/claim_badge_visible/claimed_at` | ✅ |
| Owner overrides | `imported_radio_stations.owner_overrides` dict — `{logo_url, description, market_city, market_country, bio}` | ✅ |
| Email-domain auto-verify | `station_claim_service.email_domain_matches_homepage()` + mocked email logger (`mocked_emails`) | ✅ |
| Public claim endpoints | `POST /api/radio/claims` (submit), `GET /my`, `GET /{id}`, `POST /verify/{token}`, `POST /{id}/abandon` | ✅ |
| Owner endpoints | `GET /api/owner/dashboard`, `PATCH /api/owner/stations/{station_id}` | ✅ |
| Admin queue endpoints | `GET/POST /api/admin/radio/claims{,/{id}/approve,/{id}/reject}` | ✅ |
| Frontend routes | `/claim/station/:id` (wizard, 630 LOC), `/claim/verify/:token`, `/owner/dashboard`, `/admin/radio-claims` | ✅ |

### What DOES NOT exist (CLAIM.1 delta scope)

| Concern | Gap | CLAIM.1 work |
|---|---|---|
| Proof-of-ownership file uploads | Current claim payload accepts JSON only — no business card image, no email screenshot, no gov ID, no station license doc | Add multipart branch on `POST /api/radio/claims` + `proof_documents[]` field + admin viewer |
| Owner edit approval workflow | `PATCH /api/owner/stations/{id}` mutates the station IMMEDIATELY — no admin gate | New `station_edit_requests` collection + endpoints (submit / list / withdraw / admin approve/reject) |
| Description **text** field (dedicated) | Owner overrides has `description` (short) + `bio` (long) fields, no markdown / rich text | Add `description_text` on station doc (or reuse `bio`) |
| Description **audio** clip (30 sec intro) | Not present anywhere | Add `description_audio_url` + `description_audio_duration_sec` + upload endpoint |
| **Banner image** | Not present (station has `favicon` + `logo_url` — square logo — but no wide hero) | Add `banner_image_url` + upload endpoint |
| `owner_edited_at` timestamp | Not present | Add on approved edit apply |
| `owner_editable` / `auto_publish_edits` per-station toggle | Not present | Add + admin endpoint |
| Claim Radio Hub page | `/claim-radio` not routed — 42-C has `/claim/station/:id` (single-station wizard) but no browse + directory | New page component + `GET /api/stations/claimable` endpoint |
| Dispute claims (station already claimed) | 42-C returns 409 `already_claimed` outright | Optionally accept as `claim_status="dispute"` for admin arbitration (user brief says "admin decides" — implement dispute path) |
| Dual-design (`useDesignVariant`) parity on existing 42-C UIs | None of `OwnerDashboard.jsx`, `ClaimStationWizard.jsx`, `ClaimVerify.jsx`, `AdminRadioClaims.jsx` import the hook | Add branch classnames on all 4 files |

### Files that already exist (do NOT recreate — extend instead)

**Backend (all functional, tested in 42-C):**
- `/app/backend/services/station_claim_service.py` (265 LOC)
- `/app/backend/routes/station_claims.py` (303 LOC — mounts `/api/radio/claims` + `/api/owner`)
- `/app/backend/routes/admin_station_claims.py` (132 LOC — mounts `/api/admin/radio/claims`)
- `/app/backend/scripts/seed_station_claims.py`

**Frontend (all mounted in `App.js`):**
- `/app/frontend/src/ClaimStationWizard.jsx` (630 LOC — per-station wizard at `/claim/station/:id`)
- `/app/frontend/src/ClaimVerify.jsx` (160 LOC — email verify landing at `/claim/verify/:token`)
- `/app/frontend/src/OwnerDashboard.jsx` (384 LOC — owner dashboard at `/owner/dashboard`)
- `/app/frontend/src/Admin/AdminRadioClaims.jsx` (360 LOC — admin queue at `/admin/radio-claims`)

### New files CLAIM.1 will create

**Backend (5 new files):**
1. `backend/scripts/init_claim1_collections.py`     — idempotent index setup for the 1 new collection + station-schema field seeding
2. `backend/services/station_edit_request_service.py`     — CRUD + approval lifecycle for `station_edit_requests`
3. `backend/services/station_upload_service.py`     — MIME/size validation + persist to `/app/backend/static/{claim_proofs,station_media}/…`
4. `backend/routes/station_edit_requests.py`     — owner + admin edit-request endpoints
5. `backend/routes/station_claim_hub.py`     — `/api/stations/claimable` browse endpoint

**Backend extensions (in existing files):**
6. `backend/routes/station_claims.py` — extend `POST /api/radio/claims` to accept multipart with proof docs
7. `backend/routes/admin_station_claims.py` — extend detail endpoint to expose proof-doc URLs
8. `backend/server.py` — mount 2 new routers + boot init

**Frontend (in CLAIM.1b — deferred to the next batch):**
- New `/claim-radio` hub page component
- Extend `ClaimStationWizard.jsx` with proof file upload step
- Extend `OwnerDashboard.jsx` with edit-request submission for description text/audio/banner
- Extend `AdminRadioClaims.jsx` with proof-viewer + edit-request queue
- Apply `useDesignVariant` on all 4 existing components

### New collections CLAIM.1 will introduce

Only **1** new collection needed (the 42-C `radio_station_claims` already
covers the "ownership claim" collection the CLAIM.1 brief describes; we
just add `proof_documents` field to it — schemaless so non-breaking):

**`station_edit_requests`**:
```
id, station_id, station_source ("imported_radio_stations"), owner_user_id,
owner_profile_id,
proposed_changes:   dict[str, Any],     # sanitized before insert
change_type:            "metadata" | "description_text" | "description_audio" |
                                  "banner_image" | "logo" | "stream_url" | "multiple",
edit_status:              "draft" | "pending" | "approved" | "rejected" | "withdrawn",
admin_reviewer_id, review_notes, reviewed_at,
uploaded_files:        [{field, file_url, mime, bytes, uploaded_at}],
created_at, updated_at
```

### Station document extensions (via `$set`, non-breaking)

Added lazily to `imported_radio_stations` docs when the owner submits an
edit or admin approves one:

- `description_text` (up to 10,000 chars markdown)
- `description_audio_url`, `description_audio_duration_sec`
- `banner_image_url`
- `owner_edited_at`   (ISO string)
- `owner_editable`    (bool, default true — admin can flip off)
- `auto_publish_edits` (bool, default false — admin per-station override)

None of these break existing queries — MongoDB is schemaless.

### Assumptions confirmed

1. ✅ Existing `radio_station_claims` covers the "ownership claim" role; add proof docs there rather than creating a second collection.
2. ✅ Existing `station_owner_profiles` covers the "owner identity" role.
3. ✅ Existing admin approval + email-domain verify code paths cover the "claim" side of the acceptance criteria.
4. ✅ File uploads for banner/audio can reuse the FUN.1.3 pattern (`/app/backend/static/{namespace}/{slug}.{ext}` + `POST /api/…/logo`-style multipart handlers).
5. ✅ File uploads for proof docs go to `/app/backend/static/claim_proofs/{claim_id}/{filename}` with server-side auth check — never returned in an unauthenticated response.
6. ✅ CLAIM.1 backend can ship independently of CLAIM.1 frontend — existing wizard already POSTs to the same endpoint we're extending, and the multipart branch is additive.

### Notification service

MOCKED via `mocked_emails` collection.  `station_claim_service._log_mock_email`
already handles claim verification emails.  For CLAIM.1 we add TWO
`_log_mock_email` calls at edit-approval / rejection time; no new
provider integration.

## Ship plan

**CLAIM.1a (this session)** — Backend only.
- Step 0: this discovery doc ✅
- Step 1: DB init script + station-doc field additions (idempotent)
- Step 2: `station_upload_service.py` + `station_edit_request_service.py`
- Step 3: 2 new routers (`station_edit_requests.py`, `station_claim_hub.py`) + extend existing 2 routers (`station_claims.py` for proof upload, `admin_station_claims.py` for proof viewer)
- Boot init + router mount in `server.py`
- E2E curl demo of the delta (submit claim with proof → admin approve → owner submits edit → admin approves edit → station reflects new fields)
- OpenAPI verification

**CLAIM.1b (next session)** — Frontend only.
- Extend existing 4 UI components (wizard + owner dashboard + admin queue + verify)
- New Claim Radio Hub landing page + route
- Dual-design polish on all 5 files
- Screenshots on both design variants
