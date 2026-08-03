# Phase 36a — Podcast Foundation

**Status**: ✅ COMPLETE (2026-06-03, hardened 2026-06-03). 91 BE + 31 FE green, public RSS feed live on preview URL, Apple+Spotify compliance verified end-to-end. Includes 2 post-MVP hardening fixes (see "Hardening" section below).

## Env vars to flip when LiveKit + AssemblyAI keys land (Phases 36b/36c)

```
# Phase 36b — Transcription (mocked until set)
ASSEMBLYAI_API_KEY=<set when ready; missing → mock transcripts>

# Phase 36c — WebRTC studio (mocked until set)
LIVEKIT_API_KEY=<from LiveKit dashboard>
LIVEKIT_API_SECRET=<from LiveKit dashboard>
LIVEKIT_URL=wss://<your-project>.livekit.cloud
LIVEKIT_RECORDING_S3_BUCKET=<bucket for egress recordings>

# Phase 36a — already in use, override as needed
PODCASTS_STORAGE_ROOT=/app/backend/storage/podcasts
PODCAST_PUBLIC_BASE_URL=https://mobile-games-v2.preview.emergentagent.com
```

No 36b/36c code paths exist yet. The above is documented here so the next phase can flip features on by setting env vars without re-reading the codebase.

## Files shipped (NEW; no Phase 18 file modified)

| Path | Purpose |
|------|---------|
| `services/podcasts.py`             | DB ops, slug, FFmpeg transcode, ffprobe duration |
| `services/podcast_rss.py`         | feedgen-based RSS 2.0 + iTunes XML, feedparser validation |
| `routes/podcasts.py`               | 3 routers: `/api/podcasts/*`, `/api/admin/podcasts/*`, public `/podcasts/{slug}/rss.xml` |
| `frontend/src/Podcasts.jsx`     | Listener Podcasts tab — discovery grid + channel detail |
| `frontend/src/Creator.jsx`        | Creator dashboard — apply flow, channels, distribution |
| `frontend/src/AdminPodcasts.jsx` | Admin moderation queue — applications + channels |
| `frontend/src/setupProxy.js`    | EXTENDED — added `/podcasts/:slug/rss.xml` forward to backend (uses `app.get` not `app.use`) |
| `backend/tests/test_phase36a.py` | 14 BE tests |
| `frontend/src/__tests__/Phase36a.test.jsx` | 5 FE tests |
| `server.py`                              | EXTENDED — mount 3 new routers + lifespan static-precedence probe |
| `App.js`                                  | EXTENDED — `/podcasts`, `/creator`, `/admin/podcasts/*` routes |
| `requirements.txt`              | EXTENDED — `feedgen`, `feedparser`, `lxml` |

## Collections (all NEW; no existing collection touched)

- `podcast_creators`           — `{id, user_id, display_name, bio, contact_email, market, application_status: pending|approved|rejected, applied_at, approved_at, approved_by, rejection_reason}`
- `podcast_channels`           — `{id, creator_id, slug, title, description, category, language, city, cover_image_url, explicit_flag, subscriber_only, rss_enabled, active, approval_status, tags, follower_count, created_at, updated_at}`
- `podcast_episodes`           — `{id, channel_id, guid, title, description, show_notes, tags, audio_url, audio_url_external, video_url, cover_image_url, duration_seconds, file_size_bytes, season, episode_number, episode_type, explicit_flag, subscriber_only, publish_status: draft|published|scheduled|imported_draft|archived, published_at, scheduled_publish_time, source, storage_path, created_at, updated_at, archived_at}`
- `podcast_feeds`                 — `{channel_id, cached_xml, last_built_at, invalidated_at}` (5-min TTL)
- `podcast_platform_submissions` — `{id, channel_id, platform_name, platform_status: not_submitted|pending|live|rejected, submission_url, platform_show_url, last_checked_at}`
- `podcast_followers`         — `{user_id, channel_id, followed_at}`

## Endpoints

### Creator / listener
- `POST   /api/podcasts/creators/apply`
- `GET    /api/podcasts/creators/me`
- `POST   /api/podcasts/creators/{creator_id}/channels`
- `GET    /api/podcasts/creators/{creator_id}/channels`
- `PATCH  /api/podcasts/channels/{ch_id}`
- `GET    /api/podcasts/channels/{ch_id}`                 (public read; only active+approved)
- `GET    /api/podcasts/discover?category=&market=&q=`
- `POST   /api/podcasts/channels/{ch_id}/episodes`     (multipart upload + FFmpeg transcode + ffprobe)
- `GET    /api/podcasts/channels/{ch_id}/episodes`
- `PATCH  /api/podcasts/channels/{ch_id}/episodes/{ep_id}`
- `POST   /api/podcasts/channels/{ch_id}/episodes/{ep_id}/publish`
- `DELETE /api/podcasts/channels/{ch_id}/episodes/{ep_id}` (soft-archive)
- `GET    /api/podcasts/episodes/{ep_id}`                  (listener-side, published-only)
- `GET    /api/podcasts/episodes/{ep_id}/audio.mp3`  (streams transcoded file; falls back to external URL for imported episodes)
- `GET    /api/podcasts/channels/{ch_id}/rss`           (admin/creator preview; same content)
- `POST   /api/podcasts/channels/{ch_id}/feeds/validate` — runs Apple+Spotify checklist
- `POST   /api/podcasts/channels/{ch_id}/import-rss` — preserves external GUIDs, skips duplicates
- `POST   /api/podcasts/channels/{ch_id}/redirect`     — sets `itunes:new-feed-url` for migration
- `GET    /api/podcasts/channels/{ch_id}/distribution`
- `POST   /api/podcasts/channels/{ch_id}/distribution/submit`
- `POST   /api/podcasts/channels/{ch_id}/follow`

### Admin
- `GET    /api/admin/podcasts/creator-applications?status=pending`
- `POST   /api/admin/podcasts/creator-applications/{cid}/approve`
- `POST   /api/admin/podcasts/creator-applications/{cid}/reject`        `{reason}`
- `GET    /api/admin/podcasts/channels?approval_status=`
- `POST   /api/admin/podcasts/channels/{ch_id}/approve`     (also sets active=True)
- `POST   /api/admin/podcasts/channels/{ch_id}/reject`        `{reason}`

### Public root path (proxied via `setupProxy.js` → FastAPI)
- `GET    /podcasts/{slug}/rss.xml` — 200 `application/rss+xml`, 5-min cache, iTunes-compatible

## Live verification (real preview URL, real Mongo)

```
POST https://mobile-games-v2.preview.emergentagent.com/api/podcasts/creators/apply
        body: {display_name, bio, contact_email, market}
→ {id: "crt_…", application_status: "pending", ...}     ✓

POST .../api/admin/podcasts/creator-applications/{cid}/approve  (admin auth)
→ {application_status: "approved"}                                       ✓

POST .../api/podcasts/channels/{ch_id}/feeds/validate
→ {valid: true, apple_compliant: true, spotify_compliant: true,
     errors: [], warnings: [], item_count: 1}                                ✓

GET  .../podcasts/e2e-smoke-show/rss.xml
→ HTTP 200, content-type: application/rss+xml, 2153 bytes
   <rss xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" version="2.0">
     <channel>
       <title>E2E Smoke Show</title>
       <atom:link rel="self" .../>
       <itunes:explicit>no</itunes:explicit>
       <itunes:category text="Technology"/>
       <itunes:owner>...</itunes:owner>
       <item>...<enclosure type="audio/mpeg" length="9876"/>...</item>
     </channel>
   </rss>                                                                                  ✓
```

## Static-precedence guard

Lesson learned from Phase 18d ads.txt: when a backend route at site-root collides with a file in `/app/frontend/public/`, the dev server silently masks the dynamic route.

New `server.py` lifespan probe logs a WARN on every boot for any of:
- `/app/frontend/public/ads.txt`         (lesson from 18d)
- `/app/frontend/public/app-ads.txt`  (ditto)
- `/app/frontend/public/**/rss.xml`    (Phase 36a)

`setupProxy.js` now forwards three site-root paths to FastAPI:
- `/ads.txt`                                                (Phase 18d, `app.use` mount)
- `/app-ads.txt`                                         (Phase 18d, `app.use` mount)
- `/podcasts/:slug/rss.xml`                      (Phase 36a, `app.get` with re-attached `req.url`)

Why `app.get` here: `app.use(path, ...)` strips the mount path before middleware runs, but `app.get` doesn't. The middleware re-attaches `req.originalUrl` to `req.url` so the proxy forwards the full path to FastAPI.

**Production parity reminder**: when this app deploys, the ingress / nginx / CF config MUST mirror these three forwards. Documented inline in `setupProxy.js` header.

## Test counts

- BE: **91 passed, 1 skipped** (was 87 → +4 new hardening tests in `test_phase36a.py`). The skip is the preview-URL e2e from 18d that needs the env var.
- FE: **31 passed** (was 26 → +5 new in `Phase36a.test.jsx`).
- Zero existing tests regressed.

## Untouched (scope guard honored)

AI Ad Creator, takeover SKU, pacing math, freq cap logic, attribution writer, hygiene whitelist core (extended only via lifespan probe, not core logic), push gating, geo precedence, GlobalAudio, market lexicon arrays, trivia WebSocket, social passport, commute mode, Phase 18 advertiser stack, `/app/mobile/`.

## Mocked / parked

- Recording (browser WebRTC) — Phase 36c.
- Transcription — Phase 36b (AssemblyAI).
- AI title / show-notes / chapter generation — Phase 36b/d.
- Real-platform-API auto-submission to Apple/Spotify/etc. — Phase 2.
- Full RSS-import-with-rehost (currently external audio plays through redirect to source URL) — Phase 2.
- Hygiene whitelist for podcast files — soft-archived only; the existing `hygiene18c.tick_daily()` doesn't list `/podcasts/**` yet (deferred; podcast files live under their own root so they're untouched by current hygiene).
- Mobile Expo podcast surface — Phase 36f.

## Hardening (2026-06-03, post-MVP) — 2 fixes

Two production-critical hardening fixes applied to `routes/podcasts.py` only. No DB schema, no other files touched. All 4 new tests + 3 live curl verifications green.

### Fix #1 — Reject silent partial-create on wrong audio field name

**Symptom**: A creator POSTing to `/api/podcasts/channels/{ch_id}/episodes` with the wrong multipart field name (e.g. `audio_file=` instead of `audio=`) — or with an empty file — used to return 200 with a "zombie" episode row that had `duration_seconds=null` and `file_size_bytes=0`. The row stayed unpublishable, polluted the feed validator, and creators had no error to act on.

**Fix**: `upload_episode()` now enforces:
1. **Pre-ingest**: If neither `audio` (non-empty upload) nor `audio_url_external` is provided → `HTTPException(422, {code: "audio_required", message: ...})`.
2. **Post-ingest defense-in-depth**: If the ingested row has zero size or zero duration (corrupted file, ffmpeg failure), delete the row and raise `HTTPException(422, {code: "audio_unreadable", ...})`. Never persist a zombie.

**Error envelope shape**:
```json
{"detail": {"code": "audio_required",
              "message": "Audio file is required and must be non-empty. Use form field name 'audio' (mp3/m4a/wav) or pass `audio_url_external` for RSS re-publish."}}
```

### Fix #2 — HEAD + byte-range support on episode audio

**Symptom**: Apple Podcasts, Overcast and Pocket Casts probe enclosures with `HEAD` requests (and many clients use `Range: bytes=A-B` for seek/resume). The previous route only handled plain GET, so Apple's validator marked feeds as "audio unreachable".

**Fix**: `stream_episode_audio()` is now declared via `@api_route(..., methods=["GET", "HEAD"])` and:
- **HEAD** → 200 with `Content-Length`, `Accept-Ranges: bytes`, `Content-Type: audio/mpeg`, empty body.
- **GET, no Range** → 200 full body, `Accept-Ranges: bytes` (so clients know they can range-request later).
- **GET, `Range: bytes=A-B`** → 206 Partial Content + `Content-Range: bytes A-B/<size>` + the exact slice.
- **Range out of bounds** → 416 with `Content-Range: */<size>`.
- **Malformed Range** → falls through to full body.
- **Externally-hosted (RSS-imported) episodes** → 302 to `audio_url_external`; HEAD on a 302 is acceptable to Apple + Overcast.

### Live curl verification (preview URL, real Mongo)

```
# 1. Wrong field name → 422
curl -b session.jar -X POST \
     "$API/api/podcasts/channels/ch_admin_qa/episodes" \
     -F "title=Wrong Field Test" \
     -F "audio_file=@/tmp/tiny.mp3;type=audio/mpeg"
→ HTTP 422
   {"detail":{"code":"audio_required","message":"Audio file is required and must be non-empty. Use form field name 'audio' (mp3/m4a/wav) or pass `audio_url_external` for RSS re-publish."}}

# 2. HEAD on audio.mp3 → 200 with Content-Length + Accept-Ranges
curl -I "$API/api/podcasts/episodes/pep_19c9d8f801fa4f/audio.mp3"
→ HTTP/2 200
   content-type: audio/mpeg
   content-length: 48945
   accept-ranges: bytes

# 3. GET with Range: bytes=0-1023 → 206 Partial Content
curl -D - -H "Range: bytes=0-1023" \
     "$API/api/podcasts/episodes/pep_19c9d8f801fa4f/audio.mp3" -o /tmp/range.bin
→ HTTP/2 206
   content-type: audio/mpeg
   content-length: 1024
   content-range: bytes 0-1023/48945
   accept-ranges: bytes
   (body is exactly 1024 bytes)
```

### Tests added (4 new, in `tests/test_phase36a.py` lines 295-422)

| Test | What it verifies |
|------|------------------|
| `test_episode_upload_rejects_wrong_field_name_with_422` | `audio=None` → 422 `audio_required`, zero zombie rows |
| `test_episode_upload_rejects_empty_audio_with_422`     | Zero-byte UploadFile → 422 `audio_required`, zero zombie rows |
| `test_episode_audio_head_returns_200_with_content_length` | HEAD → 200 + `Content-Length`>0 + `Accept-Ranges: bytes` + empty body |
| `test_episode_audio_range_request_returns_206_partial_content` | `Range: bytes=0-1023` → 206 + `Content-Range: bytes 0-1023/<size>` + exactly 1024 bytes |

All 4 pass. Full `test_phase36a.py` now 18/18 green (was 14).

## Next: Phase 36b — AI transcription + AI title/show-notes/chapters
