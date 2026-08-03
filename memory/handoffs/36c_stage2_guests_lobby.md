# Phase 36c Stage 2 — Guest Invites + Waiting Room

**Status**: ✅ COMPLETE (2026-06-04). 12/12 new BE tests + 6/6 new FE tests. 25/25 Phase 36c BE tests green. 123/123 FE tests green (zero regressions). End-to-end 2-guest live evidence captured, including FFmpeg `amix + loudnorm` measured at **-16.00 LUFS output** (target -16 ±1.0). Built within disciplined-disk scope (~805 MB free post-test).

Same scope discipline as Stage 1: no Phase 18 / AssemblyAI client / RSS / transcript editor / mobile code modified. Stage 1 disk gates (100 MB upload cap, 10-min duration gate, transcode-and-delete-source, 503 disk_pressure, 409 disk_constrained) remain enforced throughout.

## What landed

### Data model additions

| Collection                           | Purpose                                                                          |
|----------------------------------|------------------------------------------------------------|
| `podcast_guest_invites`        | Token-based invites with 7d TTL + lifecycle state machine. |
| `podcast_release_forms`        | Versioned consent snapshots (immutable audit trail). |
| `creator_studio_funnel`        | Append-only funnel analytics. |
| `podcast_recording_participants` | Extended with `lobby_status`, `admitted_at`, `kicked_at`, `ws_token`, `display_name`. |
| `podcast_recording_sessions`  | Extended with `force_mock`, `diarization_speaker_map`. |

### Invite lifecycle

```
       create_invite                accept_invite (token)              admit
pending ─────────────►  accepted ──── lobby ────► admitted
                                       │                                                        │
                                       │ cancel_invite                          │ kick
                                       ▼                                                        ▼
                                  cancelled                                            kicked
                                       │
                                       │ now > expires_at (sent_at + 7d)
                                       ▼
                                    expired
```

Distinct HTTP codes on the public lookup so the FE can show the right CTA:

| State        | HTTP | Body code         |
|----------|------|-----------------|
| pending  | 200  | (envelope) |
| accepted| 200  | (envelope, can rejoin) |
| expired  | 410  | invite_expired |
| cancelled| 423 | invite_cancelled |
| not found| 404  | invite_not_found |

### Versioned consent

`/app/backend/services/podcast_consent.py` is the single source of truth:
- `CONSENT_TEMPLATE_VERSION = 1`
- `CONSENT_TEMPLATE_V1`: full text, expanded at signing time with `{creator_display_name}` and `{channel_title}`.
- `render(creator_display_name, channel_title)` returns `{consent_version, consent_text}` — the full expanded text.

**Audit-trail-critical invariant**: when a guest signs, the FULL expanded text is snapshotted into `podcast_release_forms.consent_text` together with the version number. The template constant can later be rotated (bump `CONSENT_TEMPLATE_VERSION`, update `CONSENT_TEMPLATE_V1`) and historical forms remain authoritative — they reference their own snapshot, not the live constant.

`test_36c_s2_05_consent_snapshot_full_text_at_signing` proves this by mutating the constant in-process and verifying the stored form is unchanged.

### Endpoints added (11)

| Method  | Path                                                                                    | Auth        |
|------|-------------------------------------------------------------|-----------|
| POST | `/api/podcasts/recording-sessions/{sid}/invite-guest`         | creator   |
| GET    | `/api/podcasts/recording-sessions/{sid}/invites`                | creator   |
| POST | `/api/podcasts/recording-sessions/{sid}/invites/{iid}/cancel` | creator |
| POST | `/api/podcasts/recording-sessions/{sid}/lobby/admit/{pid}` | creator   |
| POST | `/api/podcasts/recording-sessions/{sid}/lobby/kick/{pid}`    | creator   |
| GET    | `/api/podcasts/studio/invites/{invite_token}`                       | none (public) |
| POST | `/api/podcasts/studio/invites/{invite_token}/accept`            | none (public) |
| GET    | `/api/podcasts/studio/invites/{invite_token}/state`              | none (public) |
| POST | `/api/podcasts/studio/{sid}/upload-track`                              | ws_token (guest) |
| WS      | `/api/podcasts/studio/{sid}/ws`                                              | session cookie OR ws_token |
| GET    | `/api/admin/podcasts/creator-studio-funnel`                          | admin     |
| POST | `/api/podcasts/studio/funnel-event`                                          | optional |

`POST /api/podcasts/creators/{cid}/recording-sessions` was extended with the `?force_mock=1` query param (admin-only no-op for non-admins).

`POST /api/podcasts/recording-sessions/{sid}/upload-track` (the authenticated host path) now accepts an optional `participant_id` form field, which is what lets the host upload host.mp3 (no participant_id) **and** lets the public guest upload endpoint reuse the same service code for guest tracks (with participant_id required).

### WebSocket protocol

Endpoint: `WS /api/podcasts/studio/{sid}/ws?token=<X>`

Auth tiers (server-side resolution):
1. Try `token` as a `sessions.token` (session-cookie value) → if the user is the session's creator, attach as `host:<user_id>`.
2. Otherwise try `token` as a `participant.ws_token` → attach as the participant's id.
3. Otherwise → 4401 close.

Hub: in-process `LobbyHub` (mirrors the `trivia_rooms` pattern — no shared infrastructure modified).

Message schema (JSON text frames):

| Direction              | Type                                  | Payload                                                                                |
|----------------------|-------------------------------------|----------------------------------------------------------|
| server → both    | `hello`                                  | `{role, you, session_status}`                                          |
| server → host     | `participant_joined_lobby` | `{participant: {id, display_name, joined_at}}` |
| server → guest    | `you_have_been_admitted`  | `{livekit_token, admitted_at}`                            |
| server → guest    | `you_have_been_kicked`       | `{}`                                                                                  |
| server → both    | `session_ended`                  | `{episode_id}`                                                            |
| client → server  | `ping`                                    | `{}` (server replies `pong`)                                |
| client → server  | `leave`                                  | `{}` (server detaches)                                                |

Note: FE GuestJoin.jsx + Studio.jsx both use a 3-4 sec polling fallback **in addition** to the WS — this is intentional defense in depth; the WS is the fast path, the poll is the resilience path.

### Multi-track mixing recipe

`services/podcast_guests.py::ffmpeg_amix_tracks`:

```
ffmpeg -y -i a.mp3 -i b.mp3 -i c.mp3 \
   -filter_complex "[0:a][1:a][2:a]amix=inputs=3:duration=longest:normalize=0[mix];\
                                [mix]loudnorm=I=-16:TP=-1.5:LRA=11[a]" \
   -map "[a]" -ac 2 -ar 44100 -codec:a libmp3lame -b:a 128k mixed.mp3
```

- `amix duration=longest` — preserves the longest track (no premature cutoff).
- `normalize=0` — disables ffmpeg's auto-attenuation so loudnorm gets a clean input.
- `loudnorm I=-16:TP=-1.5:LRA=11` — podcast-standard target (-16 LUFS integrated, -1.5 dBTP true peak, 11 LU range).
- Single-track sessions skip `amix` and just loudnorm-pass.

`finalize_session()` is the single entry point — it auto-collects every participant with `upload_status=completed`, sorts by `(joined_at, admitted_at)` (host first because admitted_at populated at create-time), then calls `ffmpeg_amix_tracks`. Output goes to both `mixed.mp3` (admin recording endpoint) and `audio.mp3` (the existing 36a episode-audio path — no route changes needed).

### Diarization speaker map

After finalize, `podcast_recording_sessions.diarization_speaker_map` is populated:
```
{
  "A": {"participant_id": "prp_host_x",     "display_name": "Host",        "role": "host"},
  "B": {"participant_id": "prp_guest_a",  "display_name": "Alex Guest", "role": "guest"},
  "C": {"participant_id": "prp_guest_b",  "display_name": "Sam Guest", "role": "guest"}
}
```

The convention is `A = host, B = first admitted guest, C = second, …`. This is the mapping the transcript editor (36b extension, later) will use to label speakers in the AssemblyAI/mocked output.

### Force-mock canary

`?force_mock=1` on `POST /api/podcasts/creators/{cid}/recording-sessions` forces the session onto the mock LiveKit path even if env vars are populated. Persisted on the session row so subsequent token mints (admit, accept) stay on the mock path.

- Admin users → honored.
- Non-admins → silently no-op (no 4xx). This means the FE/SDK doesn't need to special-case admins.

Use this flag during the eventual live-cutover by creating two sessions, one with `?force_mock=1` and one without, then A/B comparing connection quality, mint latency, room cleanup, etc.

### Creator-Studio Funnel

Append-only collection `creator_studio_funnel`:

```
{id, user_id?, event, timestamp, session_id?, channel_id?, meta?}
```

Events (whitelist): `picker_shown`, `picker_apply_cta_clicked`, `picker_create_channel_cta_clicked`, `session_started`, `guest_invited`, `guest_accepted`, `guest_admitted`, `guest_kicked`, `session_finalized`, `session_cancelled`.

Backend writes are fire-and-forget (best-effort try/except — never blocks the user action). FE drops events through `POST /api/podcasts/studio/funnel-event` (optionally authenticated). Admin reads through `GET /api/admin/podcasts/creator-studio-funnel?from=&to=&session_id=` with both aggregated counts and the last 200 raw rows for drilldown.

This is the analytics seed that monetization (36e) will use to prioritize where to add friction reduction — e.g., if `picker_apply_cta_clicked` >> `session_started`, the bottleneck is creator-application, not channel-creation.

## Live evidence (2026-06-04)

End-to-end: 1 host + 2 guests, session `prs_6dae94bbf74043`:

```
1. POST /api/podcasts/creators/crt_admin_qa/recording-sessions     → 200 session_id=prs_6dae94bbf74043 mode=mock
2. POST /api/podcasts/recording-sessions/.../start                                  → 200 status=recording
3. POST /api/podcasts/recording-sessions/.../invite-guest             ×2 → 200 tokens issued
4. GET    /api/podcasts/studio/invites/{tok}                                          → 200 (no auth) consent_version=1
5. POST /api/podcasts/studio/invites/{tok}/accept                              ×2 → 200 lobby_status=lobby
6. POST /api/podcasts/recording-sessions/.../lobby/admit/{pid}     ×2 → 200 lobby_status=admitted
7. POST /api/podcasts/recording-sessions/.../upload-track (host) → 200 host.mp3 server_duration=3.030s
8. POST /api/podcasts/studio/{sid}/upload-track (guest 1)             → 200 prp_4160…mp3 server_duration=3.030s
9. POST /api/podcasts/studio/{sid}/upload-track (guest 2)             → 200 prp_c05e…mp3 server_duration=3.030s
10. POST /api/podcasts/recording-sessions/.../finalize                    → 200 track_count=3 episode_id=pep_86735c96f1cb49
        diarization_speaker_map = {A: host, B: Alex Guest, C: Sam Guest}
```

Loudness JSON (FFmpeg `loudnorm print_format=json` on the produced mixed.mp3):
```
input_i  (LUFS):  -16.45
input_lra:           0.00
input_tp:             -11.23
output_i (LUFS):  -16.00     ← inside [-17.0, -15.0] target window ✅
output_tp:           -10.79
```

HEAD/Range on the episode audio (36a hardening reused for the mixed output):
```
HEAD /api/podcasts/episodes/pep_86735c96f1cb49/audio.mp3 → 200, content-length: 48945, accept-ranges: bytes
GET    /api/podcasts/episodes/pep_86735c96f1cb49/audio.mp3   Range: bytes=0-1024 → 206, 1025 bytes
```

Funnel sequence for the test session (`GET /api/admin/podcasts/creator-studio-funnel?session_id=...`):
```
counts: {guest_accepted:2, guest_admitted:2, guest_invited:2, session_finalized:1, session_started:1}
sequence:
  07:40:17 session_started
  07:40:17 guest_invited
  07:40:17 guest_invited
  07:40:37 guest_accepted
  07:41:30 guest_accepted
  07:41:30 guest_admitted
  07:41:30 guest_admitted
  07:41:43 session_finalized
```

Disk audit (zero `disk_pressure` codes during the 2-guest test):
```
events for prs_6dae94bbf74043: []
disk_pressure count: 0
```

## Tests

12 new BE tests in `tests/test_phase36c_stage2.py`:

| # | Coverage |
|--|----------|
| 01 | invite created, token = uuid4 hex, expires_at = sent_at + 7d (within 5s), `mocked_email_sent: true`, funnel row written |
| 02 | public envelope shape (no token/email leaks; consent_version + full text included) |
| 03 | 410 expired / 423 cancelled / 404 invalid distinct status codes |
| 04 | accept creates participant (lobby) + release form snapshot + ws_token + ip_hash |
| 05 | consent text snapshot survives template-constant rotation (mutate `CONSENT_TEMPLATE_V1` → old form unchanged) |
| 06 | 4-participant cap → 5th accept returns 409 `session_full` |
| 07 | host admit flips lobby_status, re-mints LiveKit token with publish=True, funnel event written |
| 08 | host kick flips lobby_status, calls `livekit_client.remove_participant` (mock-patched), audit timestamp set |
| 09 | multi-track finalize produces 3-track amix mp3 + speaker_map A/B/C + episode draft + 36b auto-fire |
| 10 | `force_mock=True` honored — `sess.force_mock=True`, `mode=mock` |
| 11 | funnel collection contains session_started + guest_invited + guest_accepted for the session |
| 12 | `LobbyHub` per-key fan-out (broadcast_to_role + broadcast_to_participant + detach cleanup) |

6 new FE tests in `src/__tests__/Phase36cStage2.test.jsx`:

| Coverage |
|----------|
| Studio: Invite modal renders, submit creates invite, "Copy link" banner shows new URL |
| Studio: Active invites list shows status pills (pending/cancelled), Cancel button calls backend, hidden on cancelled |
| Studio: Lobby ribbon shows waiting guests, Admit/Kick buttons call correct backend paths |
| Studio: 4-participant cap disables the "Invite guest" button, label becomes "Session full (4/4)" |
| GuestJoin: renders consent text + name input + email input + Test mic + Join lobby (disabled until name + consent) |
| GuestJoin: expired invite shows friendly "expired" error message |

## Out-of-scope verification

Confirmed no out-of-scope files modified. Touched files (this dispatch, 9 total):

- `backend/services/podcast_consent.py` (NEW)
- `backend/services/podcast_guests.py` (NEW — invite lifecycle, lobby, WS hub, amix recipe, funnel)
- `backend/services/livekit_client.py` (EXTEND: `is_live(force_mock=)`, `remove_participant`)
- `backend/services/podcast_recording.py` (EXTEND: `force_mock` in create_session, `participant_id` in upload_track, multi-track amix in finalize_session)
- `backend/routes/podcasts.py` (EXTEND: 11 new routes incl. WS, public guest paths, admin funnel)
- `backend/tests/test_phase36c_stage2.py` (NEW)
- `frontend/src/Studio.jsx` (EXTEND: GuestsAndLobbyPanel component appended)
- `frontend/src/GuestJoin.jsx` (NEW)
- `frontend/src/App.js` (EXTEND: 1 line — `<Route path="/studio/join/:token">`)
- `frontend/src/__tests__/Phase36cStage2.test.jsx` (NEW)
- `/app/memory/PRD.md` (UPDATE)
- `/app/memory/handoffs/36c_stage2_guests_lobby.md` (this file, NEW)

Untouched (Phase 36a/36b core, hygiene whitelist core, push gating, geo, GlobalAudio source, market lexicon, AI Ad Creator, takeover SKU, pacing math, freq cap, attribution writer, trivia WS code, social passport, commute mode, mobile, RSS service, chapters routes, transcript editor).

## Operational notes

- **Rate-limiting**: invite tokens are UUID4 (122 bits entropy), brute force is infeasible. We do NOT IP-rate-limit the public invite endpoints. If abuse appears later, add a rolling counter on `(ip_hash, hour)` in front of `get_public_invite` / `accept_invite`.
- **Memory**: `LobbyHub` is in-process — fine for a single-instance backend, won't survive a restart. Connections drop and reconnect via the FE's 4s polling fallback, so users feel a brief stall but no data loss. If we scale horizontally later, swap the hub for Redis pub/sub.
- **Disk**: 1 active session still the platform-wide limit. 4-participant cap is the per-session limit. Stage 2 added no new persistent storage paths beyond the existing `/app/backend/storage/podcasts/recordings/<sid>/` (now contains `host.mp3`, `{participant_id}.mp3` × N, `mixed.mp3`, `audio.mp3`). Hygiene whitelist already covers this path from Stage 1.
- **MOCKED**: SendGrid email send (logged to console only — the "Copy invite link" UI button is the real delivery channel). AssemblyAI (Stage 1+2 — replaced by inline mock). LiveKit (Stage 1+2 — `is_live()=False` by default).

## Next: Phase 36c Stage 3 — Video + multi-track grid

Anticipated work:
- Video MediaRecorder + per-participant track upload (`{pid}.webm` video).
- FFmpeg `xstack` / `vstack`+`hstack` 2×2 grid filter_complex.
- Per-participant audio sync via timestamps.
- Bitrate caps (~2 Mbps total) to keep within disk budget.
- LiveKit publish permissions extended to `can_publish_video=true` on admit.

---

## 2026-06-04 — Stage 2 audit closeout

Tester pass landed at 4/6 PASS + 2 HUMAN_REQUIRED audit-surface gaps (not code defects). Both are now closed with read-only admin introspection endpoints + 1 new BE test that proves the audit-trail invariant directly.

### What was added (scope guard: 3 files)

- `backend/routes/podcasts.py` — 2 new admin endpoints (read-only).
- `backend/tests/test_phase36c_stage2.py` — 1 new test (template-mutation immutability).
- `/app/memory/handoffs/36c_stage2_guests_lobby.md` — this section.

No service/recording/consent code modified. The way `podcast_release_forms` rows are written is untouched.

### New admin endpoints

| Method | Path | Returns |
|--------|------|---------|
| GET | `/api/admin/podcasts/sessions/{sid}/release-forms` | `{session_id, count, release_forms: [{id, participant_id, consent_text, consent_version, signed_at, ip_hash, status}]}` |
| GET | `/api/admin/podcasts/release-forms/{form_id}` | single form row (404 `release_form_not_found` on miss) |

Both are `admin_podcasts_router` (auth via `require_admin`), so they live under the canonical `/api/admin/podcasts/...` prefix established in Stage 1 path-parity work.

### Immutability proof (test `test_36c_s2_13`)

1. Session #1 — guest signs release form #1 on the live template (v1).
2. Snapshot the form's `consent_text` and `consent_version`.
3. Mutate `services.podcast_consent.CONSENT_TEMPLATE_V1` to a NEW text + bump `CONSENT_TEMPLATE_VERSION` to 2.
4. Session #2 — guest signs release form #2. Verify form #2 has the NEW text + version 2.
5. Re-fetch form #1 — assert `consent_text` byte-identical to the snapshot AND `consent_version == 1`.

Test passes. The template-constant rotation does NOT propagate retroactively to stored snapshots.

### Live evidence (curl, 2026-06-04)

Session: `prs_1a022d615ee940` (tester's 2-guest finalized session).

```
GET /api/admin/podcasts/sessions/prs_1a022d615ee940/release-forms
→ 200
  count: 2
  release_forms[0]: {id: prf_806bc80e873949, participant_id: prp_5a980f3bc00c4a,
                                   consent_version: 1, ip_hash: a61cc5cdef…,
                                   consent_text: "By joining this recording, you grant Admin QA permission…" (700+ chars)}
  release_forms[1]: {id: prf_cd508dfa7c634d, participant_id: prp_25e291c8595e43,
                                   consent_version: 1, ip_hash: c9cd4473ac…, full text snapshot}

GET /api/admin/podcasts/release-forms/prf_806bc80e873949
→ 200 single form payload matches the row from list endpoint above.

GET /api/admin/podcasts/creator-studio-funnel?session_id=prs_1a022d615ee940
→ 200
  counts: {session_started:1, guest_invited:2, guest_accepted:2, guest_admitted:2, session_finalized:1}
  All 5 event types ≥ 1 ✅
  events: 8 total, full chronological sequence:
    07:55:59 session_started
    07:56:21 guest_invited × 2
    07:56:28 guest_accepted × 2
    07:56:34 guest_admitted × 2
    07:56:56 session_finalized
```

Note: `consent_text` snapshots persist the full text at signing (700+ chars). The `ip_hash` is a sha256 truncated to 32 chars — raw IP never stored. `status: "signed"` on both rows.

### Test count delta

- BE: **26/26 pass** in Phase 36c (`test_phase36c.py` + `test_phase36c_stage2.py`) — was 25, now +1 with the new immutability test.
- FE: no changes (still 123/123 green; no FE surface added).

### Out of scope confirmation

Touched exactly 3 files. Did NOT modify:
- `services/podcast_consent.py`     (only read at test time via import)
- `services/podcast_guests.py`         (release-form writes already correct)
- `services/podcast_recording.py`  (no change)
- frontend (no surfaces added — admin auditors use the API directly or whatever future admin console reads it)

Phase 36c Stage 2 fully closed. Stage 3 (Video + multi-track FFmpeg grid layouts via `xstack`) is up next.
