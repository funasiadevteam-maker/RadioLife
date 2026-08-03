# Phase 36d Part A — AssemblyAI flipped to live mode

**Date:** 2026-06-05

## Change
- `/app/backend/.env` — added `ASSEMBLYAI_API_KEY` (32-char key, fingerprint `****8c27`).
- No code change required; `services/assemblyai_client.py::is_live()` toggles purely on env presence.
- `sudo supervisorctl restart backend` performed.

## Verification

### Boot log
```
Phase 36b: transcript poll cron started (live mode)
```
(Previously: `Phase 36b: AssemblyAI in MOCK mode (no API key)`)

### Integration-status endpoint
`GET /api/admin/podcasts/integrations/assemblyai/status` (admin):
```json
{
  "is_live": true,
  "api_key_present": true,
  "mode": "live",
  "provider": "assemblyai",
  "last_check_at": "2026-06-05T18:46:12.115006+00:00"
}
```

### Smoke test
Submitted a known-good short English audio (AssemblyAI's public
`5_common_sports_injuries.mp3` sample — pod has no real podcast
episodes with audio on Tigris; existing rows are sine-wave fixtures
~33-48 KB which would produce empty sentiment) with
`sentiment_analysis=true` + `auto_chapters=true`, polled to completion:

| Counter | Value |
|---|---|
| Transcript chars | 2,443 |
| Sentiment segments | 20 |
| Auto-chapters | 2 |
| Polls to completion | 7 (≈35 sec) |

All three Part-A acceptance assertions hold:
- `text` length > 0 ✓
- `sentiment_analysis_results` length ≥ 1 ✓
- `chapters` length ≥ 1 ✓

## Privacy
- Raw API key never printed to logs, tests, fixtures, frontend bundle, or
  this handoff. Only fingerprint `****<last-4>` is recorded.
- Smoke script (`/tmp/aai_smoke.py`) was created, executed, and **not
  committed** — sits outside `/app/` source tree.
- Transcript body text was never printed; only structural counters
  (`len(text)`, `len(sentiment_analysis_results)`, `len(chapters)`).
