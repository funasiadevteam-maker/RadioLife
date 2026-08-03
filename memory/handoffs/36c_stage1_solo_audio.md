# Phase 36c Stage 1 — Solo Audio Recording Studio

**Status**: ✅ COMPLETE (2026-06-04). 10/10 new BE tests + 5/5 new FE tests. No regressions across 36a/36b/18d (59 passed, 1 pre-existing skip). Live curl round-trip green including HEAD/Range on the produced audio. Built at disciplined-disk scope per constrained `/app` headroom (522-830 MB free).

**Bug-fix patch** (2026-06-04, second dispatch): ✅ 3/3 reviewer issues resolved. **13/13 BE tests** + **7/7 FE tests** (3 new BE + 2 new FE) green. Live curl evidence at the bottom of this doc.

## Stage 1 scope (what shipped this dispatch)

Solo audio recording only. Stages 2-4 (guest invites, video, screen share) follow in separate dispatches. The schema + LiveKit abstraction is forward-compatible so those stages layer on without rewrites.

```
Creator → /creator/studio/new
        ↓                        (channel picker + title + Start)
POST /creators/{cid}/recording-sessions
        ↓                        (mints host LiveKit token MOCK; creates pending session
        ↓                         + host participant row; enforces single-active-session gate)
POST /recording-sessions/{sid}/start                                     → status=recording
[ browser MediaRecorder records up to 10 minutes ]
POST /recording-sessions/{sid}/stop                                        → status=processing
POST /recording-sessions/{sid}/upload-track    (streaming multipart)
                                                                                                                  ↓
                                                                                                              [ 1 MB chunks; mid-flight disk check every 5 MB ]
                                                                                                              [ FFmpeg webm/opus → mp3 128k ]
                                                                                                              [ raw webm DELETED immediately on transcode success ]
POST /recording-sessions/{sid}/finalize                                  → solo: copy host.mp3 → mixed.mp3 + audio.mp3
                                                                                                                  ↓
                                                                                                                podcast_episodes draft created with storage_path
                                                                                                                pointing at the session dir; auto-fires 36b
                                                                                                                kick_transcription()
        ↓
nav → /creator/episodes/{ep_id}/edit (36b transcript editor)
```

## LiveKit env contract

```
LIVEKIT_API_KEY=...        # all three required for live mode
LIVEKIT_API_SECRET=...
LIVEKIT_URL=...                # e.g. wss://your-livekit.cloud
```

If any of the three is missing or empty, `livekit_client.is_live()` returns False and every call returns a deterministic mock:

| Call                                                | Mock return                                                                                                  |
|----------------------------------|-----------------------------------------------|
| `mint_room_token(room, identity, role)` | `mock_lk_token_{room}_{identity}_{role}`                          |
| `create_room(room, max_participants)`   | `{room_name, sid: "mock_room_sid_xxx", mode: "mock", ...}` |
| `livekit_url()`                                            | `"mock://livekit"`                                                                              |
| `delete_room(room)`                                  | no-op                                                                                                            |

The live path uses the official `livekit-api` Python SDK via a **lazy import** inside `_live_*` helpers — the SDK is NOT a hard dependency of mock-mode deployments.

## DB collections

```
podcast_recording_sessions {
    id, creator_id, channel_id, title,
    status:                                  pending | recording | processing | completed | cancelled,
    recording_mode:                solo | interview | panel,    # only solo used in Stage 1
    video_enabled,                      # false in Stage 1
    screen_share_enabled,        # false in Stage 1
    livekit_room_name, livekit_room_sid, livekit_url,
    mixed_audio_url,
    total_duration_seconds,
    episode_id,                              # set on finalize
    started_at, ended_at, created_at, updated_at
}
podcast_recording_participants {
    id, session_id, user_id, role: host | guest,
    guest_name, guest_email, joined_at, left_at,
    audio_track_url, video_track_url,
    upload_status: pending | completed | failed,
    consent_accepted, device_info_json, error_message,
    created_at
}
podcast_recordings {
    id, session_id, creator_id,
    mixed_audio_url, mixed_video_url,
    raw_assets_json, duration_seconds, processing_status, created_at
}
recording_disk_events {
    id, timestamp, free_bytes_at_event,
    code: disk_constrained | disk_pressure | track_already_uploaded,
    session_id, route, user_id
}
```

## Disk gates — disciplined-disk regime (Stage 1)

| Gate                                                  | Trigger                                                                                  | Response                                                                                                                |
|----------------------------------|-------------------------------------------|----------------------------------------------------------|
| **Single-active-session**         | any other session in `recording`/`processing` | **409** `{code: "disk_constrained", message: ...}` + audit row |
| **Mid-upload disk pressure**  | `shutil.disk_usage('/app').free < 200 MB` at any 5 MB checkpoint | **503** `{code: "disk_pressure", ...}` + `Retry-After: 60` header + partial-file delete + audit row |
| **Transcode-and-delete-source** | every successful upload                            | raw webm/mp4 unlinked as soon as FFmpeg produces mp3 |
| **Duration cap**                          | client_duration_seconds > 600                  | **400** `{code: "duration_exceeded"}`                                            |
| **Upload size cap**                  | streamed total > 100 MB                                 | **413** `{code: "upload_too_large"}`                                            |
| **Idempotency**                          | second upload for same (sid, role) when first is completed | **409** `{code: "track_already_uploaded"}` + audit row |

`GET /api/podcasts/admin/recording-disk-events` returns the last 50 events for visibility. Sample row from this dispatch's live curls:
```
2026-06-04T06:53:02    code=disk_constrained  free_mb=827  route=create_session
2026-06-04T06:52:12    code=disk_pressure     free_mb=100  route=upload_track
2026-06-04T06:52:12    code=track_already_uploaded  free_mb=828  route=upload_track
```

## MediaRecorder MIME negotiation (frontend)

Pick order (first supported wins):
```
audio/webm;codecs=opus           ← Chromium/Firefox (preferred)
audio/webm
audio/mp4;codecs=mp4a.40.2     ← Safari fallback
audio/mp4
audio/ogg;codecs=opus              ← rare; backstop
```
1-second timeslices accumulated in memory (POC: 60 s → <10 MB; Stage 1: 10 min → ~75 MB at 128 kbps audio). 128 kbps target via `audioBitsPerSecond`.

Browser-side mic constraints:
```
{audio: {echoCancellation: true, noiseSuppression: true,
              autoGainControl: true, sampleRate: 48000}, video: false}
```

## Endpoints reference (Stage 1)

| Method | Path                                                                                                                                                              | Notes                                                                                                                                |
|--------|-----------------------------------------------------------------------------------------------|------------------------------------------------------------|
| POST    | `/api/podcasts/creators/{cid}/recording-sessions`                                       | create + mint host token + single-active-session gate |
| POST    | `/api/podcasts/recording-sessions/{sid}/start`                                              | pending → recording                                                            |
| POST    | `/api/podcasts/recording-sessions/{sid}/stop`                                                | recording → processing; 10-min cap                                |
| POST    | `/api/podcasts/recording-sessions/{sid}/upload-track`                              | streaming multipart, all disk gates, idempotent      |
| POST    | `/api/podcasts/recording-sessions/{sid}/finalize`                                        | mix (solo: copy) + create draft episode + auto-fire 36b |
| GET      | `/api/podcasts/recording-sessions/{sid}`                                                            | polling + participant list                                                  |
| DELETE | `/api/podcasts/recording-sessions/{sid}`                                                            | cancel + delete storage dir + LiveKit room              |
| GET      | `/api/podcasts/recording-sessions/{sid}/audio/{name}`                              | raw host/mixed mp3 fetch (admin/debug)                  |
| GET      | `/api/podcasts/admin/integrations/livekit/status`                                  | `{is_live, mode, api_key_present, api_secret_present, url_present}` |
| GET      | `/api/podcasts/admin/recording-disk-events`                                                | last N disk-gate audit rows                                          |

## Frontend pages

- `/creator/studio/new` — channel picker + title + recording_mode + Start. POC banner ("Solo audio only for now") + LiveKit MOCK banner.
- `/creator/studio/{sid}` — live studio panel: mic permission CTA → AnalyserNode level meter (green/yellow/red) → record/stop buttons → 10-min countdown timer (warns red at 9:00, auto-stops at 10:00) → upload + finalize phases → navigates to `/creator/episodes/{ep_id}/edit` on completion.
- GlobalAudio safety: imperative pause via `window.bigfmAudio.pause()` at mount, `.resume()` on unmount if it was playing. Does NOT touch GlobalAudio source.

## Tests added (10 BE + 5 FE)

| Test                                                                                  | Coverage                                                                                                              |
|-----------------------------------------------|--------------------------------------------------------------------|
| `test_36c_01_livekit_mock_token_shape`        | `mock_lk_token_{room}_{identity}_{role}` exact match  |
| `test_36c_02_session_state_machine`              | pending → recording → processing transitions                |
| `test_36c_03_duration_cap_enforced`              | 601 s stop → 400 `duration_exceeded`                                  |
| `test_36c_04_upload_size_cap`                          | 101 MB stream aborted with 413                                              |
| `test_36c_05_idempotent_upload`                      | 2nd upload for same role → 409 `track_already_uploaded` |
| `test_36c_06_concurrent_session_disk_constrained` | 409 + audit row written |
| `test_36c_07_disk_pressure_aborts_upload` | mock `_free_bytes` < 200 MB → 503 + `Retry-After` + audit |
| `test_36c_08_transcode_and_delete_source` | raw webm absent on disk post-upload                              |
| `test_36c_09_finalize_creates_episode_and_fires_transcription` | draft episode + 36b transcript completed/processing |
| `test_36c_10_cancel_cleans_storage`              | dir removed + status flipped                                            |

FE tests cover: StudioNew picker rendering, POC/MOCK banners visibility, Studio panel rendering with mic CTA + pre-roll checklist, 10-min cap text + auto-transcribe note, session-ID + LiveKit room debug surface.

## Live curl evidence (this dispatch)

```
POST /creators/crt_admin_qa/recording-sessions
  → session_id: prs_79d1002d3e2740, livekit_token: mock_lk_token_..._host

POST /creators/crt_admin_qa/recording-sessions   (while first is recording)
  → HTTP 409 {code: "disk_constrained", message: "Another recording session is active."}

POST /recording-sessions/prs_.../upload-track  (5s sine.webm, 49 KB)
  → HTTP 200 {upload_status: completed, size_bytes: 81128}
  → on-disk: host.mp3 only; raw .webm deleted

POST /recording-sessions/prs_.../finalize
  → HTTP 200 {episode_id: pep_2e16ebabe77f48, duration_seconds: 4.0}
  → 36b transcript auto-fired: status=completed, provider=mock, 8 utterances

HEAD /api/podcasts/episodes/pep_.../audio.mp3
  → HTTP 200, content-length: 65245, accept-ranges: bytes

GET /api/podcasts/episodes/pep_.../audio.mp3   Range: bytes=0-1023
  → HTTP 206, content-range: bytes 0-1023/65245, body=1024 bytes

GET /admin/recording-disk-events?limit=5
  → audit log shows disk_constrained, disk_pressure, track_already_uploaded events
```

Net disk delta after a full solo round-trip: **0 MB** (transcode-and-delete-source policy works).

## What's deferred (Stages 2-4)

| Stage     | Surface                                                                                                  |
|--------|-------------------------------------------------------------------------|
| **2**     | `PodcastGuestInvites` table, public `/studio/join/{token}` consent page, host lobby admit/kick, SendGrid invite (MOCKED with copy-link UI) |
| **3**     | Video upload + per-participant tracks + FFmpeg `amix` + `loudnorm I=-16` + grid filter_complex (2=side-by-side, 3-4=2x2) |
| **4**     | Screen-share start/stop + `connection_quality_log` 5-second tick + browser pre-recording mic/cam check page |

## Files touched / created

**Created**:
- `services/livekit_client.py` (lazy SDK; mock + live)
- `services/podcast_recording.py` (session lifecycle, disk gates, transcode)
- `frontend/src/Studio.jsx` (StudioNew + Studio panel)
- `tests/test_phase36c.py` (10 tests)
- `frontend/src/__tests__/Phase36c.test.jsx` (5 tests)
- `/app/memory/handoffs/36c_stage1_solo_audio.md` (this file)

**Extended** (no rewrites): `routes/podcasts.py` (11 new endpoints + 2 admin endpoints), `frontend/src/App.js` (2 new Routes).

**Untouched** per guardrail: AssemblyAI client, RSS service, chapters routes, transcript editor itself, Phase 18 files, Phase 36a/36b core, hygiene whitelist core (no need to extend — `storage/podcasts/recordings/**` is naturally outside `PRUNE_DIRS`), push gating, geo, GlobalAudio source, market lexicon, AI Ad Creator, takeover SKU, pacing math, freq cap, attribution writer, trivia WS, social passport, commute mode, `/app/mobile/`.

## Hygiene note

The Phase 36c hygiene whitelist extension mentioned in the original brief (whitelist `recordings/{sid}/*` for non-cancelled sessions ≤ 30 days) was reviewed and is **not needed**: `services/hygiene18c.py::PRUNE_DIRS` covers only `/app/backend/storage/{streams,segments,tracks}` and `/app/backend/static/ad_creatives` — `storage/podcasts/recordings/**` is already outside the hygiene cron's scope. Re-evaluate if PRUNE_DIRS expands during Phase 36d/e cleanup work.

## Next: Phase 36c Stage 2 — Guest invites + waiting room

---

# Bug-Fix Patch (2026-06-04) — Stage 1 Reviewer Tickets

The Stage 1 reviewer found two real bugs and asked for one path-parity move. All three are resolved here. Scope was strictly limited to the six files explicitly named in the ticket; no Phase 18 / AssemblyAI / RSS / transcript-editor / mobile code was touched.

## Bug #1 — Channel picker showed "No approved channels yet" despite active channels existing

**Root cause**: `Studio.jsx` previously hit the aggregated `GET /api/podcasts/me` endpoint and read `r.data.channels` straight through. Whenever that single request failed (auth blip, transient 5xx, or a creator profile reshape), the array fell back to `[]` and the picker rendered the placeholder — even though the creator did have approved+active channels visible via the canonical creator-scoped endpoint.

**Fix**: Move to an explicit two-step flow with client-side filtering and explicit CTAs.

```
Studio.jsx::StudioNew useEffect
  1. GET /api/podcasts/creators/me                       → resolve creator
        ↓ creator == null OR application_status != "approved"
        → setNextRoute("/creator/apply")  + show "Apply as creator" CTA
        ↓ creator is approved
  2. GET /api/podcasts/creators/{creator.id}/channels   → fetch raw list
        ↓ filter client-side: approval_status === "approved" && active === true
        ↓ filtered.length > 0
        → setChannels(filtered); setChannelId(filtered[0].id); nextRoute = null
        ↓ filtered.length == 0
        → setNextRoute("/creator/podcasts/new") + show "Create a channel first" CTA
```

Edge cases handled in the same effect:
- `creators/me` 4xx/5xx → treat as "no creator" → "Apply as creator" CTA
- `creators/{cid}/channels` 4xx/5xx → treat as "no active channels" → "Create a channel first" CTA
- Pending/inactive channels → silently filtered out client-side (defense in depth even though the backend already filters via `approval_status` + `active`)

Both new edge-case CTAs are wired through the existing `data-testid="studio-next-route-cta"` element with a `<Link>` to the correct route.

## Bug #2 — 10-minute (600s) duration cap not wired to the upload endpoint

**Root cause**: The Stage 1 cap was enforced only on `/stop` (via `client_duration_seconds`). The `/upload-track` endpoint accepted any duration and called transcode + finalize regardless. A client that skipped `/stop` (or lied about duration there) could push an arbitrarily long mp3 onto disk and into the episodes table.

**Fix**: Dual enforcement, defense in depth.

| Layer                                    | When                                              | Action                                                                                          |
|-------------------------------|----------------------------------|-----------------------------------------------------|
| **Client fast-fail**            | top of `upload_track()` service  | If `client_duration_seconds > 600` → **400** `{code: duration_exceeded, cap_seconds: 600}` BEFORE any byte is streamed (no partial file, no transcode). |
| **Server authoritative**  | after FFmpeg transcode      | Run `ffprobe -v error -show_entries format=duration -of csv=p=0 <mp3>` on the produced mp3. If > 600s → delete the mp3, flip `participants.upload_status` to `rejected_duration`, write a `recording_disk_events` row with `code: "duration_exceeded"`, raise **400** `{code: duration_exceeded, server_duration_seconds: X.X}`. |

Plumbing:
- `routes/podcasts.py::post_upload_track` now accepts `client_duration_seconds: float = Form(0)` and forwards it to the service.
- `Studio.jsx::uploadAndFinalize` appends `client_duration_seconds=String(elapsed||0)` to the `FormData`.
- `services/podcast_recording.py::upload_track` lazy-imports `services.podcasts.ffprobe_duration` and runs it on the transcoded mp3. On success it also returns `server_duration_seconds` in the response body for client observability.

The server gate fires even when the client omits the field or lies — it's the authoritative source of truth.

## Issue #3 — Path parity for the disk-events audit endpoint

**Before**: dual-mounted at `/api/podcasts/admin/recording-disk-events` AND `/api/admin/podcasts/recording-disk-events` (both 200).

**After**: canonical path `/api/admin/podcasts/recording-disk-events` (200, admin-only). Legacy path responds with **308 Permanent Redirect** to the canonical path, preserving the query string. The redirect handler itself is unauthenticated — auth is enforced at the redirect target — so external clients with stale URLs get a clean 308 → 401/200 chain.

```
GET  /api/podcasts/admin/recording-disk-events?limit=5
  → 308 Permanent Redirect
  → Location: /api/admin/podcasts/recording-disk-events?limit=5
```

## Tests added (3 BE + 2 FE) — all green

| Test                                                                                                       | Coverage                                                                                                                                                  |
|------------------------------------------------|--------------------------------------------------------------------------------------|
| `test_36c_11_client_duration_fast_fail_on_upload`           | `client_duration_seconds=750` → 400 short-circuit; zero bytes streamed; no host_raw* on disk; no host.mp3. |
| `test_36c_12_server_ffprobe_duration_rejects_and_deletes_mp3` | Patches `ffprobe_duration` to return 700; verifies 400 raised, host.mp3 deleted, participant flipped to `rejected_duration`, +1 `duration_exceeded` audit row. |
| `test_36c_13_disk_events_path_parity_308_redirect`           | `TestClient(follow_redirects=False)` on the legacy path returns 308 with Location ending in the canonical path + preserved query string. |
| `Bug #1: channel picker renders approved+active channel via 2-step flow` (FE) | seeds the 2-step mock; asserts approved+active option renders, pending option filtered out, "No approved channels yet" placeholder absent, `studio-next-route-cta` absent. |
| `Bug #1: no-creator path shows 'Apply as creator' CTA` (FE) | `creators/me` returns `{creator: null}`; asserts `studio-next-route-cta` element is present and contains "Apply as creator" text. |

Final counts: **13/13 BE tests pass** in `tests/test_phase36c.py`, **7/7 FE tests pass** in `src/__tests__/Phase36c.test.jsx`.

## Live curl evidence (this patch)

```
# Path parity — 308 redirect
GET  /api/podcasts/admin/recording-disk-events?limit=10  (no auth)
  → HTTP 308
  → location: /api/admin/podcasts/recording-disk-events?limit=10

# Path parity — full follow with admin token
GET  /api/podcasts/admin/recording-disk-events?limit=5   (admin Bearer)
  → 308 → GET /api/admin/podcasts/recording-disk-events?limit=5 → 200
  → body shows duration_exceeded audit rows from test_36c_12

# Bug #1 — 2-step channel flow
GET  /api/podcasts/creators/me                              → 200 {creator: crt_admin_qa, application_status: approved}
GET  /api/podcasts/creators/crt_admin_qa/channels  → 200 {channels: [ch_admin_qa (approved+active), pch_... (approved+active)]}

# Bug #2 — client fast-fail
POST /api/podcasts/recording-sessions/prs_60c.../upload-track
  (audio=tiny.webm  participant_role=host  client_duration_seconds=750)
  → HTTP 400 {code: "duration_exceeded", cap_seconds: 600,
                       message: "Recording exceeded the 10-minute Stage 1 cap (client-reported: 750.0s)."}

# Bug #2 — normal upload with truthful client_duration_seconds
POST /api/podcasts/recording-sessions/prs_60c.../upload-track
  (audio=tiny.webm  participant_role=host  client_duration_seconds=2)
  → HTTP 200 {upload_status: "completed", size_bytes: 33062,
                       server_duration_seconds: 2.037551,
                       audio_track_url: "/api/podcasts/recording-sessions/.../audio/host.mp3"}
```

## Files touched in this patch (6 files, per scope guard)

- `backend/routes/podcasts.py` — added `client_duration_seconds: Form` to `post_upload_track`; replaced dual-mounted disk-events route with canonical + 308 legacy redirect.
- `backend/services/podcast_recording.py` — added server-side `ffprobe_duration` gate after transcode; returns `server_duration_seconds` in success response.
- `frontend/src/Studio.jsx` — replaced `/podcasts/me` aggregated fetch with 2-step `creators/me` + `creators/{cid}/channels`, client-side filter, explicit edge-case CTAs; appended `client_duration_seconds` to upload FormData.
- `backend/tests/test_phase36c.py` — added tests 11, 12, 13.
- `frontend/src/__tests__/Phase36c.test.jsx` — fixed `seedNew` mock to match new 2-step flow; added `seedNoCreator` helper + 2 new test cases.
- `/app/memory/handoffs/36c_stage1_solo_audio.md` — this Bug-Fix Patch section.

## Next: Phase 36c Stage 2 — Guest invites + waiting room (still queued)
