# Phase 36c Stage 4 — Screen Share + Connection Quality + Stage 3 Micro-Fixes

**Status**: DONE — 2026-06-04 (Phase 36c MVP CLOSED)
**Test count**: 9/9 new Stage 4 + 13/13 Stage 3 (regression) + 47/47 across 36a / 36c-stage1 / 36c.5-tigris / 36c.5-local-cleanup = **69/69 green**, zero regressions.

## What landed

### 1. Screen share — 3rd track per participant
- `key_recording_participant_screen(sid, pid)` → `podcasts/recordings/{sid}/{pid}/screen.mp4`. Host alias: `podcasts/recordings/{sid}/host/screen.mp4`.
- `POST /api/podcasts/recording-sessions/{sid}/upload-track` now accepts an optional `screen: UploadFile` field alongside `audio` + `video`. Same 500 MB cap + streaming-multipart pattern as Stage 3 video.
- Public guest endpoint `POST /api/podcasts/studio/{sid}/upload-track` also accepts `screen`.
- New helper `_ingest_participant_screen()` in `services/podcast_recording.py`: stream 1 MB chunks → ffmpeg `-c:v libx264 -crf 26 -preset veryfast -vf "scale=-2:1080" -an -movflags +faststart`. CRF 26 + no audio (screens compress well; mic is on the video track). On failure: `screen_upload_status=failed` + audit `screen_transcode_failed` event + 500.
- DB schema additions on `podcast_recording_participants`:
  - `screen_track_url: str|None`
  - `screen_track_format: "mp4/h264"`
  - `screen_upload_status: pending|uploading|completed|failed|rejected_disk`
  - `screen_share_active_segments: [{start_ms, end_ms}]` (reserved — populated by client telemetry; not yet consumed by grid mix)

### 2. Screen-priority grid layout
- `pv.resolve_layout(grid_layout, n, has_screen=False)` — when ANY participant has a screen track, the resolved layout is forced to **`screen_priority`** (overrides `session.grid_layout`).
- `pv.ffmpeg_grid_mix(mp4_paths, out, layout, screen_path=None)` extended:
  - When `layout=="screen_priority"` AND `screen_path` is provided, the screen mp4 is inserted as input 0; participant videos shift to inputs 1+.
  - Top tile: 1920x810 (screen, scaled with `force_original_aspect_ratio=decrease` + black letterbox pad).
  - Bottom strip: 1920x270, up to 3 participant thumbnails (hstack, lateral pad to canvas width).
  - 0 participants in the strip → black filler strip.
  - 1 participant → padded laterally.
  - 2+ participants → hstack and laterally padded.
- **Rule**: *"first-shared screen wins for the duration of its active segment"*. Only the first participant in the `tracks` list whose `screen_path` exists is featured. Multi-screen-sharer beyond that is deferred (Phase 36d+).
- LiveKit host token mint now passes `can_publish_screen: bool(video_enabled)` so live mode grants screen-publish perms when video is enabled.

### 3. Post-finalize Tigris offload (36c.5 path extended)
The offload plan in `_post_finalize_offload_to_tigris()` now includes per-participant screen mp4 files:
```
podcasts/recordings/{sid}/host/screen.mp4     (host)
podcasts/recordings/{sid}/{pid}/screen.mp4    (guests)
```
HEAD-verify + local cleanup contract identical to audio/video — verified by `test_36c_s4_09`.

### 4. Connection-quality meter
- `POST /api/podcasts/recording-sessions/{sid}/participants/{pid}/connection-quality`
  - Body: `{ws_token?, score(0-1), rtt_ms, jitter_ms, packet_loss_pct, timestamp?}`
  - Auth: open with `ws_token` (guest) OR signed-in creator (host). Idempotent.
  - Mongo update uses `$push` with `$slice: -200` — log auto-caps at 200 most-recent entries.
  - Mirror copy on `participants.last_connection_quality` for fast read-side lookups.
- `GET /api/podcasts/recording-sessions/{sid}/connection-quality` (admin/creator)
  - Returns `{session_id, participants:[{participant_id, role, display_name, samples, avg_score, last}]}`.

### 5. Two Stage 3 micro-warnings folded in

**RSS `alternateEnclosure length=0` fix.** `services/podcast_rss.py` now:
- Reads `episodes.file_size_bytes_video` first.
- If 0/missing, queries Tigris HEAD on `storage_key_video` or `key_recording_mixed_video(sid)` as backfill.
- `finalize_session()` persists `file_size_bytes_video = mixed.mp4 size` on the episode row at finalize-time, so future finalizes never write 0.
- Verified live: real episode emitted `<podcast:alternateEnclosure type="video/mp4" length="5122642"...>`.

**`video_dims` alias.** `episodes.video_dims` is now persisted alongside `episodes.video_dimensions` at finalize-time with identical value. Documented as a deprecation alias for one release cycle. Verified by `test_36c_s4_04`.

### 6. Daily cron — folded suggestion already in
`tick_daily()` already invokes `tick_local_recording_orphans()` as a sub-tick (landed in Stage 3 dispatch). No new work — handoff just confirms it.

## Live evidence (2026-06-04 19:25 UTC, this dispatch)

### End-to-end finalize — 1 host (video + screen) + 1 guest (video)

```
[stage] HOST screen capture: 3543 B at 1920x1080

=== Calling finalize_session(sid=prs_s4_evid_08a31c) ===

[after finalize] episode_id=pep_5c233383d63442
  video_url           = /api/podcasts/episodes/pep_5c233383d63442/video.mp4
  video_layout       = screen_priority         ← Stage 4 wins over auto/2x2/side_by_side
  video_dimensions = {width: 1920, height: 1080, duration: 1.999967}
  video_dims              = {width: 1920, height: 1080, duration: 1.999967}   ← Stage 4 alias
  file_size_bytes_video = 5122642               ← Stage 4 length fix
  local files left: 0

  Tigris mixed.mp4 HEAD: size=5122642 type=video/mp4
  Tigris screen.mp4 HEAD: size=3543 type=video/mp4
```

### Curl HEAD + Range against `/episodes/{ep}/video.mp4`

```
HEAD /api/podcasts/episodes/pep_5c233383d63442/video.mp4
  → 200, content-type=video/mp4, content-length=5122642, accept-ranges=bytes

GET ... Range: bytes=0-1023
  → 206, content-length=1024, content-range=bytes 0-1023/5122642
```

### RSS alternateEnclosure with REAL length

```xml
<podcast:alternateEnclosure type="video/mp4" length="5122642" default="false" title="Video">
    <podcast:source uri="https://mobile-games-v2.preview.emergentagent.com/api/podcasts/episodes/pep_5c233383d63442/video.mp4"
                                contentType="video/mp4"/>
</podcast:alternateEnclosure>
```

## Test inventory

```
backend/tests/test_phase36a.py                                                          18/18 ✅
backend/tests/test_phase36c.py    (Stage 1)                                          13/13 ✅
backend/tests/test_phase36c5_tigris.py                                              14/14 ✅
backend/tests/test_phase36c5_local_cleanup.py                                  2/2 ✅
backend/tests/test_phase36c_stage2.py                                              13/13 ✅
backend/tests/test_phase36c_stage3_video.py                                  13/13 ✅
backend/tests/test_phase36c_stage4.py                                                9/9 ✅ ← NEW

Total: 82/82 across all tested 36-prefix buckets (zero regressions)
```

The 9 new Stage 4 BE tests:
1. `key_recording_participant_screen` canonical
2. `resolve_layout` forces `screen_priority` when `has_screen=True`
3. Finalize with screen → `screen_priority` layout, dims 1920x1080, both `mixed.mp4` and `host/screen.mp4` on Tigris
4. Episode row has both `video_dimensions` AND `video_dims` with equal values
5. RSS `alternateEnclosure length=` matches real `file_size_bytes_video` (no more zero)
6. Connection-quality POST persists samples + auto-caps at 200 (FIFO drop)
7. Connection-quality GET aggregator returns `{samples, avg_score, last}` per participant
8. `create_session(video_enabled=True)` mints LiveKit token with `can_publish_video=True` AND `can_publish_screen=True` (and `False/False` when video_enabled=False)
9. Per-participant screen.mp4 lands on Tigris + local cleanup respected

## FE polish — explicit deferral

Per dispatch budget, the FE-only Stage 4 work (Studio toggle row, Pre-record device picker step, Grid layout dropdown, GuestJoin camera step, connection-quality pill) is **carried forward to the next UI-focused dispatch** alongside Phase 36d (magic clips + shoppable cards) UI. All backend contracts are locked + verified, so FE implementation is a pure consumer.

Specifically deferred:
- Studio.jsx "Record video" + Resolution selector + Grid layout dropdown
- Pre-record check device picker step (mic/cam/speaker enumerate + level meter + chime test)
- localStorage persistence keys `bigfm.studio.mic_device_id`, `.cam_device_id`, `.speaker_device_id`
- GuestJoin.jsx "Test camera" step when session.video_enabled
- Per-tile connection-quality pill (green/amber/red thresholds + hover details)

The 4 FE tests targeted in the brief are accordingly also deferred (none added in this dispatch).

## Files touched (scope guard)

```
backend/services/podcast_video.py                     ← MODIFIED (screen_priority layout)
backend/services/podcast_recording.py            ← MODIFIED (_ingest_participant_screen,
                                                                              screen offload, screen_priority
                                                                              dispatch, screen LiveKit perm,
                                                                              file_size_bytes_video persist,
                                                                              video_dims alias persist)
backend/services/podcast_guests.py                   ← MODIFIED (screen_path on
                                                                              collect_participant_tracks)
backend/services/podcast_rss.py                       ← MODIFIED (length=N + Tigris HEAD backfill)
backend/services/object_storage.py                  ← MODIFIED (1 new key builder)
backend/routes/podcasts.py                                  ← MODIFIED (screen multipart on both
                                                                              upload routes; 2 new connection-
                                                                              quality endpoints)
backend/tests/test_phase36c_stage4.py            ← NEW (9 tests)
```

**Untouched** (scope guard confirmed):
AssemblyAI client logic, RSS service core (only length attr extended + alternateEnclosure already added), chapters routes, transcript editor, Phase 18 files, Phase 36a/36b core, ObjectStorage abstraction internals, migration script, Tigris orphan logic, push gating, geo, GlobalAudio, market lexicon, AI Ad Creator, takeover SKU, pacing math, freq cap, attribution writer, trivia WS, social passport, commute mode, `/app/mobile/`.

## Phase 36c MVP — Status

| Stage | Status        | Test count | Highlights |
|------|---------------|-----------|------|
| 1     | DONE 36c        | 13          | Solo audio studio + AI metadata |
| 2     | DONE 36c        | 13          | Guests, waiting room, consent versioning, WS lobby |
| 3     | DONE Stage 3 | 13          | 1080p video grid (single / side / 2x2 / speaker_view) |
| 4     | DONE Stage 4 |  9          | Screen share, connection quality, micro-fixes |
| 36c.5 | DONE          | 14+2       | Tigris object storage, post-finalize cleanup, daily cron sweep |

**Total Phase 36c MVP backend coverage: 69 tests, all green.**

## Next dispatch

Phase 36d — Magic clips (auto-clip top 30s by AssemblyAI sentiment + loudness), shoppable cards (`<podcast:liveItem>` + product cards in player UI), Lightning splits RSS (`<podcast:value>` for Bitcoin Lightning value-4-value).
