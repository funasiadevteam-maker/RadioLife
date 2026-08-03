# Phase 36b — AI Transcription + AI Show-Notes Pipeline

**Status**: ✅ COMPLETE (2026-06-03). 101 BE (10 + 2 OpenAI-gated new) + 36 FE green. 6 live curls verified. Apple Podcasts 2.0 namespace (`<podcast:chapters>` + `<podcast:transcript>`) flowing in the public RSS.

## What we built

### Auto-fire policy (3-step pipeline, never auto-applies)

```
Episode publish
        ↓  (route hook in routes/podcasts.py::publish_ep)
kick_transcription()    ← creates `podcast_transcripts` row, status=pending
        ↓                                                ← mock: completes inline (<2s)
        ↓                                                ← live: status=processing, polled every 30s
status: completed
        ↓  (auto-fired inside _advance_row on completion)
generate_metadata()    ← logs to `podcast_ai_tasks`, stored but not applied
        ↓
Creator reviews UI → clicks "Apply & publish" → apply_metadata() PATCHes the episode
        ↓
RSS feed cache invalidated → next /podcasts/{slug}/rss.xml fetch rebuilds with new
title/description/show_notes/chapters AND adds <podcast:chapters> + <podcast:transcript>
```

### Env var contract

```
ASSEMBLYAI_API_KEY=...    # absent → MOCK mode (inline completion, no poll cron)
                                                                  # present → live AssemblyAI v2 with poll cron every 30s
OPENAI_API_KEY=...               # already wired (used by AI Ad Creator + AI RJ + trivia)
                                                                  # absent → generate_metadata returns empty shape; row logged as error
```

`ASSEMBLYAI_API_KEY` is the only NEW env var. No other env or rewiring touched.

### AssemblyAI client (`services/assemblyai_client.py`)

- `is_live() -> bool`     — reads env, no caching (allows hot-flip during dev).
- `submit_transcription(audio_url, language_hint, episode_title, episode_id) -> transcript_id`
    - Live: `POST /v2/transcript` with `speaker_labels=true`, `auto_chapters=false`
        (chapters come from OpenAI for editorial control), `format_text=true`,
        `punctuate=true`, `language_detection=true` unless `language_hint` is "en"/"hi".
    - Mock: deterministic `mock_{episode_id}` ID + 8 plausibly-conversational utterances
        that reference the episode title so downstream AI generates meaningful titles.
- `poll_transcription(transcript_id)` — single GET; mock returns the prebuilt payload.
- `cancel_transcription(transcript_id)` — best-effort DELETE; non-fatal on failure.

### Transcription service (`services/podcast_transcription.py`)

- `kick_transcription(db, episode_id)` — idempotent. Creates row, submits, then in mock
    mode synchronously calls `_advance_row` so the request returns `status=completed`.
- `_advance_row(db, row_id)` — single poll cycle; on completion auto-fires `generate_metadata`
    inside try/except (AI failures never break the transcript update).
- `poll_pending_transcriptions(db)` — advances every `processing` row by one cycle.
    Server lifespan wires this as a 30s asyncio task ONLY in live mode.
- `patch_transcript_text(db, ep_id, text)` — collapses utterances to a single "EDITED"
    block and flips `manual_edit=True` so downstream AI knows.
- `utterances_to_srt(utterances)` — pure SRT formatter (`HH:MM:SS,mmm --> ...` + speaker prefix).

### AI metadata pipeline (`services/podcast_ai_metadata.py`)

- Model: `gpt-4o-mini`, `response_format=json_object`, temperature 0.75, 60s timeout.
- Reuses the same `from openai import OpenAI` client as `services/ai_ad_creator.py`
    and `services/trivia_ai.py`. **No new SDK installed.**
- Prompt pillars:
    1. Channel `category` + `language` injected into the system prompt.
    2. For Hinglish channels: **title MUST be English-only** (no Devanagari);
        description / show-notes / social captions preserve Hinglish words naturally.
    3. Chapter boundaries MUST align to utterance `start` timestamps (passed in JSON).
    4. Chapter count tiers (utterance-aligned):
        - ≤10 min → 3
        - 10-30 min → 4
        - 30-60 min → 6
        - >60 min → 7 (capped)
- `_normalize(payload, duration, target_chapters)` enforces:
    - Monotonic strictly-increasing `start_time_seconds`.
    - `end_time_seconds` re-derived from next chapter's start (last = duration).
    - Field length caps: title ≤ 80, desc ≤ 300, show_notes ≤ 4000, summary_short ≤ 150,
        summary_long ≤ 1000, twitter ≤ 240, instagram/linkedin ≤ 2000, youtube ≤ 4000.
    - Every chapter stamped `chapter_source: "ai"`.
- Every run logged to `podcast_ai_tasks` with input_json, output_json, total_latency_ms,
    status. Creators can re-roll without losing prior versions.

### Schema additions

```
podcast_transcripts {                    podcast_ai_tasks {
    id, episode_id, channel_id,             id, episode_id, channel_id,
    provider: assemblyai|mock,             task_type: "metadata",
    transcript_id, status,                       input_json, output_json,
    text, utterances_json [],                 status,    error_message,
    language_code, confidence_score,         total_latency_ms,
    error_message, manual_edit,             created_at, completed_at
    created_at, completed_at             }
}
```

`podcast_episodes` gains optional fields on apply: `chapters[]` (with `chapter_source`),
`social_captions {twitter,instagram,linkedin,youtube}`, `seo_keywords[]`, `hashtags[]`,
`sponsor_read_suggestions[]`, `summary_short`, `summary_long`.

### New endpoints (all under `/api/podcasts`)

| Method   | Path                                                                                                            | Purpose                                                                              |
|----------|----------------------------------------------------------------------------------------|--------------------------------------------------------------|
| POST       | `/episodes/{ep_id}/transcribe`                                                            | Creator force-transcribe                                          |
| GET        | `/episodes/{ep_id}/transcript`                                                              | Read latest transcript row                                      |
| PATCH    | `/episodes/{ep_id}/transcript`                                                              | Edit transcript text                                                  |
| POST       | `/episodes/{ep_id}/ai/generate-metadata`                                | Re-roll AI metadata                                                |
| POST       | `/episodes/{ep_id}/ai/generate-clips-suggestions`        | 501 placeholder (Phase 36d)                              |
| GET        | `/episodes/{ep_id}/ai/history`                                                              | Prior generation runs                                              |
| POST       | `/episodes/{ep_id}/apply-metadata`                                              | PATCH episode + invalidate RSS                            |
| GET        | `/episodes/{ep_id}/chapters.json`                                                  | Podcasting 2.0 chapters JSON                              |
| GET        | `/episodes/{ep_id}/transcript.srt`                                                  | SRT subtitles                                                              |
| POST       | `/admin/podcasts/episodes/{ep_id}/retranscribe`                | Admin force re-transcribe                                  |
| GET        | `/admin/integrations/assemblyai/status`                                  | `{is_live, mode, provider}`                                  |

### RSS feed extension (`services/podcast_rss.py`)

- `build_feed_xml(..., completed_transcript_ep_ids=set)` — new kwarg used by
    `get_or_build_xml` to inject the podcasting-2.0 namespace + per-item tags.
- `_inject_podcasting20_tags(xml, ...)` — careful string post-process (feedgen 0.9 has
    no built-in podcasting-2.0 extension): adds `xmlns:podcast="https://podcastindex.org/namespace/1.0"`
    to the `<rss>` element + injects `<podcast:chapters url=".../chapters.json" type="application/json+chapters"/>`
    for episodes with chapters, and `<podcast:transcript url=".../transcript.srt" type="application/srt" language="en"/>`
    for episodes with a completed transcript.

### Static-precedence guard (extended from 36a)

Server lifespan now also scans `/app/frontend/public/` for impostor `chapters.json` and
`transcript.srt` files and logs a WARN if found (these live under `/api/` so the ingress
already routes them, but the warning keeps devs honest).

### MOCKED-mode honest UX

- Admin endpoint `GET /api/admin/podcasts/integrations/assemblyai/status` returns
    `{is_live: false, mode: "mock", api_key_present: false}` when the key is absent.
- TranscriptEditor displays an amber banner with the literal text
    "Transcription is in MOCK mode. Set `ASSEMBLYAI_API_KEY` to get real diarized transcripts."

### FE — `TranscriptEditor.jsx` route `/creator/episodes/:ep_id/edit`

- Left: speaker-labeled utterance list (renameable speakers, editable text, timestamps).
- Right: AI metadata panel with title alternatives (chips), description, markdown
    show-notes, chapters timeline, SEO keyword chips, 4-tab social captions, sponsor reads.
- Top banner: `Draft → AI is transcribing… → Transcript ready · AI metadata generating… → Ready to publish`.
- MOCK-mode amber banner appears in mock mode.
- Bottom: "Re-roll", "Apply & publish" buttons.

## Test counts (2026-06-03)

| Suite                                   | Status                                                                                              |
|----------------------------------|--------------------------------------------------------------------------|
| `tests/test_phase36a.py`  | 18/18 (no regressions)                                                              |
| `tests/test_phase36b.py`  | 12/12 (10 always-on + 2 OpenAI-gated; both run with OPENAI_API_KEY set) |
| `tests/test_phase18d.py`  | 16/16                                                                                              |
| All FE                                  | 110/110 (+5 new Phase36b.test.jsx)                                            |

The Phase 36b unit suite covers all 12 acceptance criteria in the spec
(AssemblyAI mock round-trip, kick + auto-complete in mock mode, publish auto-fires,
poll no-op, full metadata shape, chapter-count tiers, apply invalidates RSS,
PATCH transcript collapses + manual_edit, RSS Podcasting 2.0 tags, chapters.json +
transcript.srt routes, Hinglish title-English rule, AssemblyAI status endpoint).

## Live curl evidence (preview URL)

```
# 1. POST /transcribe → completed (mock)
{"id":"ptr_da8243925ec342", "episode_id":"pep_e2ed7580732645",
  "provider":"mock", "status":"completed", "utterances": 8, "confidence": 0.93}

# 2. GET /transcript → 200, 8 utterances, speaker A/B
{"status":"completed", "provider":"mock", utterances: 8}
first utt: {speaker: A, start: 0, end: 3200, text: "Welcome back to the show..."}

# 3. POST /ai/generate-metadata → 200, full payload
title: 'Understanding the 36b QA Framework'
title_alternatives: ['The Essentials of 36b QA', 'Exploring 36b QA in Depth', 'Key Insights on 36b QA']
chapters: 3 ([(Introduction, 0.0), (Setting Realistic Expectations, 3.0), (Framework for Success, 14.0)])
seo_keywords: ['QA framework', '36b QA', 'quality assurance', 'tech insights', ...]
social keys: ['instagram', 'linkedin', 'twitter', 'youtube']
sponsor_reads: 1
hashtags: ['#QA', '#TechPodcast', '#QualityAssurance', '#36bQA', ...]

# 4. GET /podcasts/{slug}/rss.xml → contains namespace + per-item tags
xmlns:podcast: present
<podcast:chapters> tag count: 1
<podcast:transcript> tag count: 1

# 5. GET /chapters.json → 200, application/json
{"version":"1.2.0","title":"Understanding the 36b QA Episode",
  "chapters":[{"startTime":0.0,"endTime":3.0,"title":"Introduction to 36b QA Episode"}...]}

# 6. GET /transcript.srt → 200, application/x-subrip, 1212 bytes
1
00:00:00,000 --> 00:00:03,200
[Speaker A] Welcome back to the show. Today we're talking about 36b QA Episode.
2
00:00:03,200 --> 00:00:08,100
[Speaker B] Thanks for having me. This topic is super relevant right now...
```

## Files touched / created

**Created** (BE): `services/assemblyai_client.py`, `services/podcast_transcription.py`,
`services/podcast_ai_metadata.py`, `tests/test_phase36b.py`.
**Created** (FE): `src/TranscriptEditor.jsx`, `src/__tests__/Phase36b.test.jsx`.
**Extended** (no rewrites): `routes/podcasts.py` (new endpoints + publish auto-kick),
`services/podcast_rss.py` (Podcasting 2.0 injection), `server.py` (lifespan poller +
precedence-guard), `src/App.js` (one new Route).

**Untouched**: AI Ad Creator, takeover SKU, pacing math, freq cap, attribution writer,
hygiene whitelist core, push gating, geo precedence, GlobalAudio, market lexicon,
trivia WS, social passport, commute mode, Phase 18a/b/c/d advertiser stack, `/app/mobile/`.

## Known constraints / deviations

- **Chapters live on `podcast_episodes.chapters[]`** (sub-doc with `chapter_source`)
    rather than a separate `podcast_episode_chapters` collection. This keeps RSS+JSON
    generation a single doc read and matches how the spec describes the field.
- **No actual AssemblyAI call in this fork** — `ASSEMBLYAI_API_KEY` is absent so the
    live code path (`is_live() == True`) is untested end-to-end. The live HTTP code
    is documented inline in `assemblyai_client.py` and follows AssemblyAI v2 docs.
- **AI generation requires `OPENAI_API_KEY`** (already present in `.env`); when the
    key is absent, `generate_metadata` logs `status=error` to `podcast_ai_tasks` and
    returns an empty shape. The amber MOCK banner only flags AssemblyAI mode today;
    we could add an OpenAI-mode banner the same way if/when the key gets removed.

## Next: Phase 36c — LiveKit recording studio (Phase 0 POC first)

---

## 2026-06-03 — Round-2 hardening

Tester report: 5/7 pass. 1 real bug + 1 spec mismatch + 1 minor naming leak.
All three fixed below. Total Phase 36b tests now **16/16 green** (12 + 4 new).

### Fix R2-1 — Chapter starts now snap to utterance.start (zero tolerance)

**Bug**: LLM rounded chapter starts to whole seconds (3.0, 14.0) instead of using
actual utterance boundaries (3.2, 14.5). The brief explicitly required exact
utterance-boundary alignment.

**Fix** (`services/podcast_ai_metadata.py`):
- New function `_snap_chapters_to_utterances(raw_chapters, utterances, …)`
  finds for every chapter the utterance whose `start` is closest to the LLM's
  proposed start, then sets the chapter's `start_time_seconds` to that exact
  `utterance.start` value (converted ms → seconds).
- Same for end times: snap to the next chapter's snapped start (or, for the
  last chapter, the closest utterance.end).
- **Tolerance is ZERO** — exact match required after snap.
- If two consecutive chapters snap to the same utterance, **the duplicate is
  dropped** (chapter count may shrink — still respects the MAX cap from the
  tier rule). Monotonic strict-increasing is also enforced post-snap.
- Tracing: every snap is logged into a new `chapter_alignment_log` array on
  `podcast_ai_tasks.output_json` with shape:
  ```
  {llm_proposed_start, snapped_start, snap_delta_ms, source_utterance_index,
    dropped_as_duplicate?, dropped_as_non_monotonic?}
  ```

**Live proof**:
```
utterance.start universe:    [0.0, 3.2, 8.1, 14.5, 22.3, 28.9, 38.0, 44.0]
chapter starts returned:        [0.0, 3.2, 14.5]
ALL aligned to utterance.start: True

alignment_log:
  proposed= 0.000s  →  snapped= 0.000s  (Δ=     +0 ms, utt_idx=0)
  proposed= 3.000s  →  snapped= 3.200s  (Δ=+200 ms, utt_idx=1)
  proposed=14.000s  →  snapped=14.500s  (Δ=+500 ms, utt_idx=3)
```

### Fix R2-2 — `script_preference` channel field for Hinglish vs Devanagari titles

**Spec mismatch**: Tester's Test 7 expected NO Devanagari in `language="hi"`
titles. The brief actually said "title English unless the channel language is
`hi`". The code was correct per spec — but the UX nuance (Hinglish vs full
Hindi) was missing.

**Fix** (channel schema + AI prompt):
- New optional channel field `script_preference: "auto" | "latin" | "devanagari"`
  (default `"auto"`). Wired through `services/podcasts.py` create + update.
- `services/podcast_ai_metadata.py::_build_prompt` now accepts `script_preference`
  and adjusts the title rule:
    - `latin`         → "Latin script only, no Devanagari" (recommended for Hinglish)
    - `devanagari` → "Devanagari when natural for the transcript"
    - `auto`           → previous behavior (hi → Devanagari OK; others → Latin)
- Creator channel form exposes a 3-option `<select>` with helpful copy.

**Live proof** (Hinglish channel, `language="hi"`, `script_preference="latin"`):
```
title:                                                'Karak chai aur Dubai memories'
description (first 140 ch):     'Is episode mein hum karak chai aur Dubai ke yaadon ki baat karte hain. Suniyega kaise har gali corner pe yeh chai milti hai aur bachpan ki y'
title contains Devanagari?: False
PASS: script_preference=latin → no Devanagari in title
```
Description preserves Hinglish ("Is episode mein hum…karak chai aur Dubai…"); title is Latin only.

### Fix R2-3 — GET /transcript exposes `utterances` alongside `utterances_json`

**Naming leak**: The Mongo column name `utterances_json` was bleeding into
the API contract.

**Fix** (`routes/podcasts.py::get_transcript_route`):
- Response now contains BOTH keys with identical content. `utterances` is the
  new canonical name; `utterances_json` is kept for ONE release cycle as a
  deprecation buffer for the mobile + creator UI.
- DB column name unchanged (too disruptive to migrate).

**Live proof**:
```
response keys: [..., 'utterances', 'utterances_json']
has 'utterances':                          True  → 3 entries
has 'utterances_json' (legacy):  True  → 3 entries
same length:                                       True
same content (object equality):    True
first utterance:  {speaker: A, start: 0, end: 5000, text: 'Aaj hum baat karenge…'}
```

### Files touched (round 2, strictly within scope)

- `services/podcast_ai_metadata.py` — added `_snap_chapters_to_utterances`;
    threaded `utterances` + `script_preference` through `_build_prompt`,
    `_normalize`, `generate_metadata`; added `chapter_alignment_log` to
    `_empty_metadata` and `podcast_ai_tasks.output_json`.
- `services/podcasts.py` — added `script_preference` to `create_channel` doc +
    `update_channel` allowed-fields set.
- `routes/podcasts.py` — `get_transcript_route` aliases `utterances_json` →
    `utterances`. Nothing else touched.
- `tests/test_phase36b.py` — strengthened test 5 with exact-alignment assertion;
    added tests 13, 14, 15, 16 (snap, dedupe, latin-script, utterances key).
- `frontend/src/Creator.jsx` — added a `<select data-testid="channel-form-script-preference">`
    in the New Channel modal.

**Untouched** (scope guard honored): AssemblyAI client, RSS service,
chapters.json, transcript.srt, Phase 18 files, Phase 36a hardening code,
hygiene whitelist, geo, GlobalAudio, market lexicon, AI Ad Creator, takeover
SKU, pacing math, freq cap logic, attribution writer, trivia WS, social
passport, commute mode, `/app/mobile/`.

### Test counts (after round 2)

| Suite                                   | Before | After                                                  |
|----------------------------------|--------|-----------------------------------------|
| `tests/test_phase36b.py` | 12     | **16** (+4: snap, dedupe, latin, utt-key) |
| `tests/test_phase36a.py` | 18     | 18 (no regressions)                           |
| `tests/test_phase18d.py` | 16     | 16 (no regressions)                           |

### Deferred (per user direction)

- `podcast:funding` + `podcast:value` Lightning splits → Phase 36d.
- `.git` housekeeping → user will ask separately before Phase 36c.
