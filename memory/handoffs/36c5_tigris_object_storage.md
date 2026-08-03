# Phase 36c.5 — Tigris Object Storage Migration

## 🔐 SECURITY — ROTATE ALL SECRETS BEFORE PRODUCTION

`.env` files (`backend/.env`, `frontend/.env`, `mobile/.env`) were **tracked in git history** until commit `4e40f32` (2026-06-04) when they were `git rm --cached`'d and added to `/app/.gitignore`. **Every secret that has ever been in any of those files is therefore in historical commits accessible via `git log -p` / `git show <SHA>:backend/.env`.** All of the following MUST be rotated by the user before production:

- **Tigris** `TIGRIS_ACCESS_KEY_ID` + `TIGRIS_SECRET_ACCESS_KEY` (just added — rotate after the migration verifies, or rotate now and re-run the probe).
- **OpenAI** `OPENAI_API_KEY` (Phase 0 onward).
- **ElevenLabs** `ELEVENLABS_API_KEY` (Phase 0 onward).
- **ACRCloud** `ACRCLOUD_*` (music recognition / fingerprint).
- **Stripe** `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` (all phases that touched payments).
- **GAM Fernet key** (advertiser stack token encryption).
- **Emergent LLM key** `EMERGENT_LLM_KEY` (used in 36b for transcription + 36c for AI metadata).
- **AssemblyAI** `ASSEMBLYAI_API_KEY` (if ever set — currently MOCKED, but rotate if any historical value existed).
- **LiveKit** `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `LIVEKIT_URL` (Stage 1-2 MOCKED currently, but rotate any historical values).
- **SendGrid** `SENDGRID_API_KEY` (currently MOCKED).
- **Apple** `APPLE_*` SIWA, APNs, MusicKit keys (mostly empty stubs but rotate any historical value).

Git is forever — `git rm --cached` does **not** purge prior commits. For a true purge, run a history rewrite (`git filter-repo --invert-paths --path backend/.env --path frontend/.env --path mobile/.env`) followed by force-push, but this is destructive for clones and CI tooling; rotation is the safer + standard remediation.

---

## What landed in 36c.5

| Surface                                                            | Change                                                                                  |
|----------------------------------------|---------------------------------------------------------------|
| `backend/services/object_storage.py` (NEW) | `ObjectStorage` ABC + `LocalDiskStorage` + `TigrisStorage` impls + `get_storage()` factory + 11 canonical key builders. |
| `backend/.env`                                                  | added `STORAGE_BACKEND=tigris`, `TIGRIS_*` keys + `TIGRIS_BUCKET=bigfm-storage`. Removed legacy `TIGRIS_ENDPOINT="http://localhost:8085"` stub. |
| `backend/routes/podcasts.py`              | `audio.mp3` proxy route gained Tigris fallback (when local file missing) preserving HEAD/Range + 206 contract. Added `GET /api/admin/podcasts/integrations/tigris/status`. |
| `scripts/probe_tigris.py` (NEW)             | Standalone Tigris reachability probe — all 7 contract methods (`list_buckets`, `create_bucket`, `put_object`, `head_object`, `get_object` w/Range, `generate_presigned_url`, `delete_object`). |
| `scripts/migrate_local_to_tigris.py` (NEW) | `--dry-run` / `--apply` migrator with canonical path→key mapping + size verification + idempotent re-run. |
| `backend/tests/test_phase36c5_tigris.py` (NEW) | 12 tests (8 live against Tigris, 4 pure local). All green. |
| `/app/.gitignore`                                          | `.env / *.env / backend/.env / frontend/.env / mobile/.env` now excluded; `!.env.example` allowlist preserved. |

### Object-storage contract

```python
class ObjectStorage(ABC):
    def upload(*, local_path, key, content_type) -> {key, size, content_type, backend}
    def download(*, key, local_path) -> int (bytes)
    def delete(*, key) -> bool
    def exists(*, key) -> bool
    def head(*, key) -> {size, content_type, etag} | None
    def get_signed_url(*, key, expires_in=3600) -> str
    def open_range(*, key, start, end) -> bytes
    def list_keys(*, prefix="") -> Iterator[{key, size}]
```

`get_storage()` is a lazy singleton driven by `STORAGE_BACKEND` env var. `local` and `tigris` are the only valid values.

### Canonical key naming

```
podcasts/channels/{ch_id}/{ep_id}/audio.mp3
podcasts/channels/{ch_id}/{ep_id}/cover.jpg
podcasts/channels/{ch_id}/{ep_id}/video.mp4
podcasts/recordings/{sid}/{pid}/audio.mp3
podcasts/recordings/{sid}/{pid}/video.mp4
podcasts/recordings/{sid}/mixed.mp3
podcasts/recordings/{sid}/mixed.mp4
music/tracks/{track_id}.mp3
rj/{rj_id}.mp3
ad_creatives/{creative_id}.{mp3|webp|jpg|png}
chapters/{ep_id}.json
transcripts/{ep_id}.srt
```

### Read path: proxy vs redirect

- **`/api/podcasts/episodes/{id}/audio.mp3`** stays a **proxy** route — same auth + HEAD/Range contract, but internally it now tries local disk first and falls back to `TigrisStorage.open_range()` when the local file is gone. This preserves the public RSS-feed enclosure URLs (podcast apps cache RSS) — the URL never changes, only the backend swaps file source.
- **Tigris signed URLs** (1h expiry) are available via `get_signed_url()` for any future internal redirect-style consumer (e.g. mobile clients with a short-lived token). Not used by the RSS feed by design.

### Migration script

`scripts/migrate_local_to_tigris.py`:

| Mode             | Behavior                                                                                                                                            |
|--------------|----------------------------------------------------------------------------------------------------------|
| `--dry-run` | Walk local tree, report would-migrate count + bytes + canonical key mapping. Reads only. Idempotent. |
| `--apply`    | Same walk, but actually uploads to Tigris, HEADs to verify size, then deletes the local copy. Skips files already present in Tigris with matching size. Re-running is safe (idempotent). |

The mapper is deliberately conservative — it ONLY migrates files matching known patterns (tracks/, rj/, ad_creatives/, chapters/, transcripts/, podcasts/recordings/<sid>/{host,host_video,prp_*,mixed,audio}.{mp3,mp4}). Anything else (SFX library, station_ids, transient transcode intermediates) is left on disk and reported as "skipped (unmapped)".

### Migration evidence (2026-06-04, this dispatch)

```
DISK BEFORE:  /dev/nvme0n10  9.0G/9.8G used, 810M free; /app/backend/storage = 6.6M
DRY-RUN     :  scanned=100, would-upload=1 (575,573 B / 0.55 MB), unmapped=99,
                            errors=0, deletions=0
LIVE             :  scanned=100, uploaded=1, deleted_local=1, errors=0, unmapped=99
DISK AFTER  :  /dev/nvme0n10  9.0G/9.8G used, 808M free; /app/backend/storage = 6.1M
                          (NB: at 92% disk-fill, freeing 0.5 MB of mp3 doesn't move the
                              df-h needle visibly; the value of this migration is in
                              FUTURE writes going to Tigris, NOT this single byte-clip
                              of historical reclaim. Future recording sessions will
                              write directly to Tigris via the abstraction.)
TIGRIS STATE: 67 objects, 13,053,223 bytes (~12.5 MB) total in bigfm-storage
                          (the prior 65 objects were uploaded by the migration script
                              + tests across earlier dispatches; this dispatch added 2 new
                              objects from test_36c5_10 / test_36c5_13).
```

Skipped (unmapped) files left intentionally on local disk:
- `sfx/library/*` (14 SFX clips — shared utility, not per-tenant)
- `sfx/station_id/*` (10 station IDs — bundled assets)
- `sfx/tuning.mp3` (boot jingle)
- `voice_previews/*` (14 RJ voice samples — bundled)
- `imaging/*`, `og_default.png`, `podcasts/*` (bundled defaults)

These are intentionally NOT migrated — they are version-pinned bundled assets that
ship with the backend container, not per-user/tenant content.

### Stage 3 unlock prep (DOCUMENTED ONLY — do NOT relax in this dispatch)

Once Tigris is fully load-tested at production scale, the following caps can relax in the resumed Stage 3 dispatch:

| Gate                                              | Today (36c.5 closing) | Available in resumed Stage 3 |
|---------------------------------------|-----------------------------|--------------------------------|
| Concurrent active recordings | 1                                                | Stay at 1 (Mongo write-lock simplicity preferred) |
| Combined upload cap                | 100 MB                                  | 500 MB                                                |
| Per-track video cap                  | 75 MB                                    | up to 500 MB                                  |
| Recording duration cap          | 10 min                                    | 60 min                                                |
| Video resolution target          | 720p @ 1 Mbps                | 1080p @ 2-3 Mbps                          |
| Transcode-and-delete-source | IMMEDIATE                          | transcode-then-upload-then-delete-local |

All Stage 1+2 gates remain enforced today and through any production load test.

### Live curl evidence (this dispatch, 2026-06-04 18:01 UTC)

```
HEAD /api/podcasts/episodes/pep_evidence_36c5/audio.mp3
  → HTTP/2 200, content-type: audio/mpeg, content-length: 81128,
        accept-ranges: bytes
       (no local file on disk — episode pointed at /nonexistent;
         body served via TigrisStorage.head() + open_range() from key
         podcasts/channels/ch_evidence_36c5/pep_evidence_36c5/audio.mp3)

GET /api/podcasts/episodes/pep_evidence_36c5/audio.mp3  Range: bytes=0-1023
  → HTTP/2 206, content-range: bytes 0-1023/81128, content-length: 1024
        ← served from Tigris via boto3 get_object(Range=…) inside open_range()

GET /api/admin/podcasts/integrations/tigris/status (admin auth)
  → 200 {backend:"tigris", is_live:true, bucket:"bigfm-storage",
                endpoint:"https://fly.storage.tigris.dev",
                total_objects:67, total_size_bytes:13053223,
                last_check_at:"2026-06-04T18:01:42.073668+00:00"}
```

### Test count

- **14/14 new BE tests pass** in `tests/test_phase36c5_tigris.py`:
  1. local-disk round-trip
  2. Tigris live round-trip (upload/exists/head/download/range/delete)
  3. signed URL serves content
  4. signed URL honors `Range:` → 206 + Content-Range
  5. factory dispatches on STORAGE_BACKEND env
  6. canonical key builders
  7. local backend blocks `../` traversal
  8. migration `--dry-run` does not mutate disk
  9. admin `/integrations/tigris/status` envelope shape
  10. `/episodes/{id}/audio.mp3` proxy streams from Tigris with HEAD/Range
  11. `list_keys` paginates + filters by prefix
  12. migration mapper recognises 14 canonical/unmapped path cases
  13. **hygiene Tigris orphan pruner dry-run shape + transient TTL respected**
  14. **hygiene Tigris orphan pruner early-returns on STORAGE_BACKEND=local**

### Phase 36c.5 add-on this dispatch — hygiene Tigris orphan pruner

- `services/hygiene18c.py::tick_tigris_orphans(db, ttl_hours=168, dry_run=False, max_scan=10000)`
- `routes/phase18c.py::POST /api/admin/hygiene/tigris-orphans?ttl_hours=&dry_run=`
- Whitelist crawl scans `podcast_episodes`, `podcast_recording_sessions`,
    `podcast_recording_participants`, `tracks`, `rj_audio`, `ad_creatives`,
    builds the union of all referenced Tigris keys.
- Anything in the bucket older than TTL and NOT in the whitelist is deleted.
- Test-fixture prefix `_test/` + `_list_` + `_probe/` get a hard 1-hour cutoff
    so leaked test objects don't sit forever.
- Result row logged to `hygiene_runs` with `kind:"tigris_orphans"`.
- **No regression** in Phase 36c stages 1/2 BE tests (26 tests still pass).
- Stage 3 work remains on `stage3-wip` branch (commit `77153a6`) — unchanged.

### Out-of-scope confirmation

Untouched (per scope guard): Phase 18 advertiser stack, AssemblyAI client logic (Tigris only swaps the file-save path for transcripts), RSS service core, transcript editor, geo, GlobalAudio, market lexicon, AI Ad Creator script-generation logic, takeover SKU, pacing math, freq cap, attribution writer, trivia WS, social passport, commute mode, `/app/mobile/`.

Stage 1+2 disk gates explicitly UNCHANGED: 1 concurrent recording (409 disk_constrained), 100 MB upload cap, 10-min duration cap, ffprobe authoritative duration gate, 503 disk_pressure mid-upload, transcode-and-delete-source.

---

## 2026-06-04 — Local cleanup hardening (post-tester WARN)

Tester reported 3/4 PASS + 1 WARN on the original 36c.5 land: read path was solid but `finalize_session` was leaving local `host.mp3 / audio.mp3 / mixed.mp3` on disk → defeated the migration over time.

### Fix

`services/podcast_recording.py::finalize_session` now invokes
`_post_finalize_offload_to_tigris(...)` immediately after the
`podcast_recording_sessions` "completed" update + before transcription.
Sequencing is:
1. transcode (already happened at upload-track time)
2. amix + loudnorm into `mixed.mp3` (+ copy to `audio.mp3`)
3. write `podcast_episodes`/`podcast_recordings`/session-update rows
4. **Tigris: upload mixed.mp3 → key `podcasts/recordings/{sid}/mixed.mp3`**
5. **Tigris: upload each `prp_*.mp3` to `…/{sid}/{pid}/audio.mp3` + `host.mp3` to `…/{sid}/host/audio.mp3`**
6. **HEAD-verify each uploaded key size matches local size**
7. **Delete every verified local file**
8. **`os.rmdir(sess_dir)` (swallow OSError if non-empty)**
9. Patch `podcast_episodes.storage_key_audio = key_recording_mixed_audio(sid)` for fast lookups
10. Insert `hygiene_runs` row with `kind:"post_finalize_offload"`
11. Fire 36b auto-transcribe + funnel + lobby broadcast (unchanged)

On any upload/HEAD-verify failure: the local file is KEPT, the failure is
logged with `code:"tigris_upload_size_mismatch"` (or
`tigris_upload_error:<ExcName>`), and the rest of the finalize path
still completes (episode + recordings rows are valid, just not yet on
Tigris — the local-orphan sweep below catches up).

### Safety net — local-recording-orphan hygiene sweep

`services/hygiene18c.py::tick_local_recording_orphans(db, dry_run)`
walks `/app/backend/storage/podcasts/recordings/*/`, intersects each
session dir with its `podcast_recording_sessions.status` and HEAD-checks
the canonical Tigris keys for every local file. A dir is deleted ONLY when:
- session status ∈ `{completed, cancelled, failed}`
- STORAGE_BACKEND == "tigris"
- every key required by the dir's contents HEADs up (non-zero size)

Otherwise the dir is preserved + the issue is logged. Envelope:
`{run_at, kind:"local_recording_orphans", scanned, deleted_count, freed_bytes, dry_run, errors}`.

Admin trigger: `POST /api/admin/hygiene/local-recording-orphans?dry_run=true|false`.

### Test additions (`tests/test_phase36c5_local_cleanup.py`, 2 tests)
1. `test_finalize_deletes_local_files_after_tigris_upload` — stage host.mp3,
    seed minimal rows, call `finalize_session`, assert local sess dir is
    empty/gone AND Tigris mixed.mp3 key HEADs up AND
    `podcast_episodes.storage_key_audio` is set.
2. `test_local_recording_orphans_hygiene_sweeps_completed_session_dirs` —
    plant two completed sessions, only one with the matching Tigris key.
    Dry-run reports deleted_count≥1 without mutating. Apply-mode deletes
    the verified dir, KEEPS the un-verified one + logs
    `tigris_keys_missing`.

### Test update
`tests/test_phase36c_stage2.py::test_36c_s2_09_multi_track_amix_finalize_and_speaker_map`
post-finalize assertion now branches on `STORAGE_BACKEND`: on tigris,
asserts mixed.mp3 is GONE from disk + Tigris key is present + non-zero;
on local, asserts the legacy local-file contract still holds.

### Live curl evidence (2026-06-04 18:21 UTC)

```
POST /api/admin/hygiene/local-recording-orphans?dry_run=true
  → 200 {
       run_at: 2026-06-04T18:21:52.371Z,
       kind: "local_recording_orphans",
       scanned: 8, deleted_count: 3, freed_bytes: 0,
       dry_run: true,
       errors: ["prs_05d6…: tigris_keys_missing — leaving dir in place",
                  "prs_8ce2…: tigris_keys_missing — leaving dir in place", …5 total]
}

HEAD /api/podcasts/episodes/pep_277c0d0d883449/audio.mp3
  → 200 audio/mpeg content-length:33062 accept-ranges:bytes
GET   …audio.mp3 Range: bytes=0-1023
  → 206 content-range:bytes 0-1023/33062 content-length:1024
```

### End-to-end finalize evidence (Python harness)

```
[before finalize] sess_dir contents:
    host.mp3  (24809 B)

=== Calling finalize_session(sid=prs_evidence_eed1ff12) ===

[after finalize] result = {session_id: prs_evidence_eed1ff12,
                                            episode_id: pep_62a4af50a84a4e,
                                            mixed_audio_url: /api/.../mixed.mp3,
                                            duration_seconds: 2.04, track_count: 1}
[after finalize] sess_dir GONE (rmdir succeeded):
    /app/backend/storage/podcasts/recordings/prs_evidence_eed1ff12

=== Tigris HEAD podcasts/recordings/prs_evidence_eed1ff12/mixed.mp3 ===
  → {size: 33062, content_type: audio/mpeg,
        etag: 5f542291fe18568ad65e2f2831404b54}
```

### Final test count (this dispatch)
- 36a: 18/18 ✅
- 36b: 16/16 ✅
- 36c (stage1): 13/13 ✅
- 36c stage2: 13/13 ✅
- 36c.5 tigris: 14/14 ✅
- 36c.5 local cleanup: 2/2 ✅
- **Total: 76/76 green, zero regressions.**

### Scope guard confirmed clean
Files modified: `services/podcast_recording.py`, `services/hygiene18c.py`,
`routes/phase18c.py`, `tests/test_phase36c_stage2.py`,
`tests/test_phase36c5_local_cleanup.py` (NEW). Nothing else touched.
