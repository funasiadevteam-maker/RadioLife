# P2 hygiene backlog — routes/podcasts.py

Deferred from Phase 19b P0+P1 hardening sweep. **Not security-critical.**

## 404 vs 403 standardization (~12 inline sites)
Several routes (lines 256, 316, 357, 392, 581, 618, 677, 803, 842, 864, 890, 907)
collapse ownership-mismatch into a 404 `channel_not_found` response. The
canonical helpers (`_own_channel_or_403`, `_own_session_or_403`,
`_own_episode_or_403`) introduced in Phase 19b correctly return 403
`not_your_*`. Pick one policy and apply across all sites.

## Pagination caps to add
- `GET /channels/{cid}/episodes` — no `limit` query param; bounded at 200
- Admin `/channels` — `.to_list(500)` fixed; should accept `limit`

## Double-registered admin status routes
- `assemblyai/status` (lines 970 + 1436) — registered on both
  `admin_podcasts_router` AND `podcasts_router`
- `livekit/status` — same shape

## Dead code
- `POST /episodes/{eid}/ai/generate-clips-suggestions` — 501 stub since
  Phase 36d shipped the real clips pipeline at a different route

## Semantic naming
- action-cards routes pass `user["user_id"]` as `creator_id` into the service.
  Functional (same key for ownership check) but mislabeled. Rename consumer or
  pass real `creator["id"]`.

## Visual hygiene
- Line ~1335 — `@podcasts_router.post(...)` decorator starts on the same line
  as the previous route's closing brace; needs a blank line.

## P2-data-model-decoupling — value_config / lightning_splits storage split
PATCH `/channels/{cid}/value-config` writes into `channel.value_config.splits`
(sub-doc on the channel row), but `PUT /channels/{cid}/lightning-splits` and the
RSS render path use the separate `podcast_lightning_splits` collection. After a
legitimate owner PATCH, the channel doc shows empty splits while the
lightning_splits collection retains the prior data. The two storage paths
appear partially decoupled. **No security or user-visible impact** (RSS still
renders from the collection), but future RSS render changes should consolidate
to one source of truth.

Files: `routes/podcasts.py` PATCH value-config sites + `services/podcast_lightning.py`.
