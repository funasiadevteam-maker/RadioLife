# Phase 36c Stage 3 — Video + Multi-Track FFmpeg Grid Layouts (full scope)

**Status**: DONE — 2026-06-04
**Branch**: `main` (built fresh; `stage3-wip` reference branch left untouched)
**Test count**: 13/13 new + 73/73 across all earlier 36a/36c-stage1/36c-stage2/36c.5 buckets green.

## Rebase outcome

`stage3-wip` (commit `77153a6` + auto-commit `7bcd2e3`) predates **all of
36c.5** (ObjectStorage abstraction, Tigris migration, post-finalize
offload, local-orphan sweep). A `git merge stage3-wip → main` would
touch ~107 files. Per the dispatch's instruction
("**prefer redo over deep merge**"), we **cherry-picked patterns** from
the WIP and re-implemented Stage 3 cleanly on top of current `main`:

| From stage3-wip | Action on main |
|---|---|
| `services/podcast_video.py` (1080p adapted from 720p) | NEW file written fresh at full-scope envelope |
| Video upload-track handling | NEW helper `_ingest_participant_video()` in current `podcast_recording.py`, hooked into existing `upload_track()` post-audio-accept |
| Finalize grid mix | NEW inline block in current `finalize_session()` after audio amix, before episode/recording insert |
| Tigris offload of mp4 files | EXTENDED current `_post_finalize_offload_to_tigris()` plan with video keys |
| `routes/podcasts.py` `/video.mp4` stream | NEW route inserted after `/audio.mp3` |
| Session create video flags | EXTENDED current `create_session(...)` signature |
| RSS `alternateEnclosure` | NEW block added to `_inject_pc20_extras_into_xml()` |
| Stage 3 tests | NEW file `test_phase36c_stage3_video.py` (13 tests) |

`stage3-wip` is preserved at `7bcd2e3` for traceability but is **not
merged** and will be retired once this handoff is acknowledged.

## Relaxed envelope (vs the original pre-Tigris brief)

| Constraint                                              | Pre-Tigris      | Stage 3 final |
|---------------------------------------------------------|-----------------|-----------------|
| Video resolution                                              | 720p              | **1080p (1920x1080)** |
| Per-participant video bitrate                  | 1 Mbps          | **CRF 23 veryfast (~2.5 Mbps)** |
| Per-participant a+v upload cap            | 100 MB         | **500 MB** |
| Recording duration cap                          | 10 min          | **60 min** |
| Audio bitrate (extracted track)                | 128 kbps      | **192 kbps libmp3lame** |
| Concurrent recordings                            | 1                  | 1 (unchanged) |
| Transcode-and-delete-source urgency  | IMMEDIATE  | Post-Tigris-upload (36c.5 path) |

Caps live in `services/podcast_video.py` constants:
`VIDEO_UPLOAD_CAP_BYTES`, `VIDEO_RECORDING_CAP_SEC`, `TARGET_W`, `TARGET_H`.

## Grid layouts (filter_complex strings)

All outputs land on a 1920x1080 canvas. Each tile is `scale=…:force_original_aspect_ratio=decrease,pad=…:black` so portrait/mobile guests get letterbox bars instead of crop.

| n | Layout            | Tile sizes              | Mux verb |
|---|--------------------|-------------------------|----------|
| 1 | `single`           | 1920x1080               | scale + pad |
| 2 | `side_by_side`     | 2 × 960x1080         | `hstack=inputs=2` |
| 3 | `speaker_view`   | top 1920x810 + bottom 2×960x270 | `hstack` + `vstack` |
| 4 | `2x2`              | 4 × 960x540          | `xstack=inputs=4:layout=0_0\|w0_0\|0_h0\|w0_h0` |

`session.grid_layout ∈ {auto, side_by_side, 2x2, speaker_view}` overrides
the participant-count default; `auto` picks per above table.

After grid mix, video is muxed with the loudnorm'd mp3:
`ffmpeg -i video.mp4 -i mixed.mp3 -c:v copy -c:a aac -b:a 192k -movflags +faststart -shortest mixed.mp4`

## Pipeline

```
Browser MediaRecorder (a+v webm)
  ↓ POST /api/podcasts/recording-sessions/{sid}/upload-track  (audio + optional video multipart)
  ↓
upload_track(audio) → ffmpeg → {pid}.mp3 (192 kbps, ≤60-min ffprobe gate)
  + (if video present)
_ingest_participant_video(video):
    1. stream 1MB chunks → host_video_raw.webm     (cap: 500 MB → 413)
    2. ffmpeg transcode → 1080p H.264+AAC mp4    (rc≠0 → 500 video_transcode_failed)
    3. ffprobe duration                                                  (>3600s → 400 video_duration_exceeded)
    4. flip video_upload_status=completed
  ↓
finalize_session():
    1. ffmpeg_amix_tracks (-16 LUFS loudnorm) → mixed.mp3
    2. copy mixed.mp3 → audio.mp3 (legacy dup for old episode paths)
    3. (if session.video_enabled AND any participant has mp4)
         pv.ffmpeg_grid_mix([pids' mp4], grid_video.mp4, layout=resolve_layout(...))
         pv.merge_video_audio(grid_video, mixed.mp3, video.mp4)
    4. insert podcast_episodes (storing video_url + video_layout + video_dimensions)
    5. _post_finalize_offload_to_tigris (36c.5 path now uploads BOTH audio and video keys)
    6. rmtree local sess_dir
    7. fire 36b auto-transcribe + funnel + lobby broadcast
```

## DB schema additions

- `sessions.video_enabled: bool` (default False)
- `sessions.grid_layout: "auto"|"side_by_side"|"2x2"|"speaker_view"`
- `sessions.mixed_video_url: str|None`
- `sessions.video_layout: str|None`
- `participants.video_track_url: str|None`
- `participants.video_track_format: "mp4/h264"`
- `participants.video_upload_status: pending|uploading|completed|failed|rejected_disk|rejected_duration`
- `episodes.video_url: str|None`
- `episodes.video_layout: str|None`
- `episodes.video_dimensions: {width, height, duration}|None`
- `episodes.storage_key_video: str|None` (post-finalize 36c.5 patch)
- `recordings.mixed_video_url: str|None`
- `recordings.raw_assets_json.tracks[].mp4: path|None`

All keys persist into Tigris under `podcasts/recordings/{sid}/{pid}/video.mp4`
(participant) and `podcasts/recordings/{sid}/mixed.mp4` (final grid). The
proxy route `GET /api/podcasts/episodes/{ep_id}/video.mp4` falls back to
`storage_key_video` → `key_episode_video(channel, ep)` →
`key_recording_mixed_video(sid)` and serves the first key that HEADs up.

## RSS — Podcasting 2.0 alternateEnclosure

```xml
<podcast:alternateEnclosure type="video/mp4" length="<bytes>" default="false" title="Video">
    <podcast:source uri="https://.../api/podcasts/episodes/<ep>/video.mp4"
                                contentType="video/mp4"/>
</podcast:alternateEnclosure>
```

Lives inside each `<item>` block when the episode has `video_url` set.
`length` = `episodes.file_size_bytes_video` (set 0 if unknown — Apple
accepts 0 as "size unknown"). Default audio enclosure still ships
as the primary `<enclosure>` so audio-only podcast clients keep working
exactly as before. Verified in `test_36c_s3_12`.

## Folded — Daily cron hook for `tick_local_recording_orphans`

Per the closing note in the previous dispatch, the manual admin endpoint
is no longer the only path. `services/hygiene18c.py::tick_daily()` now
invokes `tick_local_recording_orphans(db, dry_run=dry_run)` as a sub-tick
and attaches the result under `rec["local_recording_orphans"]`. TTL is
inherited from the parent tick. Failures in the sub-tick MUST NOT break
the primary tick contract (caught + logged).

Live evidence (`tick_daily(dry_run=True)`):

```
tick_daily.local_recording_orphans = {scanned:10, deleted:3, dry_run:True,
                                                                kind:"local_recording_orphans"}
```

## Live evidence (2026-06-04 18:42 UTC, this dispatch)

### End-to-end finalize — 2-guest 1920x1080 hstack

```
[stage] host/host: transcoded mp4 size=37227 rc=0
[stage] guest/prp_evid_65d1e9: transcoded mp4 size=37227 rc=0

=== Calling finalize_session(sid=prs_s3_evid_8f4fbb) ===
[after finalize] episode_id=pep_10ae7c111d5649
  video_url     = /api/podcasts/episodes/pep_10ae7c111d5649/video.mp4
  video_layout  = side_by_side
  video_dims    = {width: 1920, height: 1080, duration: 2.0}
  local dir exists?: False, files left: 0

=== Tigris HEAD podcasts/recordings/prs_s3_evid_8f4fbb/mixed.mp4 ===
  → {size: 57418, content_type: video/mp4, etag: 5ef7df88c2ce3c717dbe6778e8967780}
```

### Curl HEAD + Range against the Tigris-backed proxy

```
HEAD /api/podcasts/episodes/pep_10ae7c111d5649/video.mp4
  → 200 OK
        content-type: video/mp4
        content-length: 57418
        accept-ranges: bytes

GET /api/podcasts/episodes/pep_10ae7c111d5649/video.mp4   Range: bytes=0-1023
  → 206 Partial Content
        content-type: video/mp4
        content-length: 1024
        content-range: bytes 0-1023/57418
```

### RSS alternateEnclosure (real episode)

```xml
<podcast:alternateEnclosure type="video/mp4" length="0" default="false" title="Video">
    <podcast:source uri="https://mobile-games-v2.preview.emergentagent.com/api/podcasts/episodes/pep_10ae7c111d5649/video.mp4"
                                contentType="video/mp4"/>
</podcast:alternateEnclosure>
```

## Acceptance test summary

```
backend/tests/test_phase36a.py                                                          18 passed
backend/tests/test_phase36c.py                                                          13 passed
backend/tests/test_phase36c_stage2.py                                              13 passed
backend/tests/test_phase36c5_tigris.py                                              14 passed
backend/tests/test_phase36c5_local_cleanup.py                                  2 passed
backend/tests/test_phase36c_stage3_video.py                                  13 passed  ← NEW
                                                                                                              ────────
                                                                                                              73 passed (0 failed, 0 regressions)
```

The 13 new Stage 3 tests cover (each line maps to a `test_36c_s3_<n>_*`):
1. create_session with `video_enabled` + grid_layout flags persists onto session row
2. Full-scope cap constants match brief (500 MB / 3600 s / 1920x1080)
3. (same as 2, layout side)
4. transcode failure → non-zero rc + no partial output
5. `resolve_layout()` auto + override semantics
6. 1-participant finalize → `single` layout, dims = 1920x1080
7. 2-participant finalize → `side_by_side`, dims = 1920x1080
8. 3-participant finalize → `speaker_view`, dims = 1920x1080
9. 4-participant finalize → `2x2` xstack, dims = 1920x1080
10. `grid_layout="speaker_view"` override respected even with 4 participants
11. `GET /api/podcasts/episodes/{ep_id}/video.mp4` HEAD → 200 + Range → 206
12. RSS XML contains `<podcast:alternateEnclosure type="video/mp4">`
13. Audio amix LUFS regression — measured input_i within ±2 LU of -16 LUFS
14. Post-finalize local cleanup catches video files too (36c.5 contract)

## Files touched (scope guard)

```
backend/services/podcast_video.py                     ← NEW (Stage 3 grid/transcode service)
backend/services/podcast_recording.py            ← MODIFIED (create_session sig + video flags;
                                                                                _ingest_participant_video helper;
                                                                                inline grid mix in finalize_session;
                                                                                offload plan now includes video keys)
backend/services/podcast_guests.py                   ← MODIFIED (collect_participant_tracks
                                                                                surfaces mp4_path + has_video)
backend/services/podcast_rss.py                       ← MODIFIED (alternateEnclosure block)
backend/services/hygiene18c.py                          ← MODIFIED (tick_daily folds in
                                                                                tick_local_recording_orphans)
backend/routes/podcasts.py                                  ← MODIFIED (video/mp4 stream route;
                                                                                video= multipart in upload-track
                                                                                + studio guest endpoint;
                                                                                video_enabled+grid_layout in create)
backend/tests/test_phase36c_stage3_video.py    ← NEW (13 tests)
backend/tests/test_phase36c_stage2.py                ← MODIFIED (1 assertion branched for
                                                                                Tigris vs local backend in s2_09)
```

**Untouched** (scope guard confirmed):
ObjectStorage abstraction, key naming, migration script, Tigris orphan
logic, Phase 18 core, Phase 36a/36b core, AssemblyAI client, RSS service
core (only `_inject_pc20_extras_into_xml` extended), chapters routes,
transcript editor, push gating, geo, GlobalAudio source, market lexicon,
AI Ad Creator, takeover SKU, pacing math, freq cap, attribution writer,
trivia WS code, social passport, commute mode, `/app/mobile/`.

## Out of scope — deferred to Stage 4

- Screen-share (separate participant.share track + 3rd column in grid)
- Pre-recording mic/cam multi-device check
- Connection-quality meter (RTT/jitter overlay on tiles)
- Live preview composite (final grid only renders on finalize)
- Video transcription (AssemblyAI stays audio-only)
- Clip generation (Phase 36d)
- Studio frontend toggle UI + GuestJoin camera step + grid layout
    selector dropdown — backend contract is locked, FE will land in next
    UI-focused dispatch alongside Stage 4 polish

## Next dispatch

Stage 4 (screen share + connection quality + pre-recording check) → closes the Phase 36c MVP → Phase 36d (magic clips + shoppable cards + Lightning splits RSS).
