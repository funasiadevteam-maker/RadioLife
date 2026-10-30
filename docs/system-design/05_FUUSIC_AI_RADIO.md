# 05 — FUUSIC Fun AI Radio (the core)

This is the product's heart: making radio **interactive** without becoming on-demand music.
It spans the backend (`routes/fun_ai.py`, `services/fun_ai_service.py`,
`services/grok_realtime.py`, `services/fun_ai_radio_policy.py`) and both clients
(web `InteractiveNews.jsx` + `FunAI/FunAiMemory.jsx` + the NowPlaying player; mobile
`app/fun-ai-news.tsx` + `app/fun-ai-memory.tsx` + `src/fun-ai/*`).

## The four pillars

1. **Conversational AI RJ** — real-time speech-to-speech voice via **xAI Grok Realtime Voice**.
2. **Interactive News** — four modes: Morning Briefing · News in 2 Mins · Deep Dive · Follow This
   Story, all source-grounded.
3. **Radio Programming Policy Engine** — guardrails that keep the AI radio-first.
4. **Companion Memory + RJ Personalities + Sponsor Breaks** — personalization & monetization.

## Voice architecture — ephemeral tokens (security-critical)

The permanent `XAI_API_KEY` **never leaves the backend**. Flow:

```
client                         backend (grok_realtime.py)                 xAI
  │  POST /api/fun-ai/session         │                                    │
  │ ─────────────────────────────────▶  mint_client_secret()              │
  │                                   │  POST /v1/realtime/client_secrets ─▶│
  │                                   │  ◀── { value, expires_at } ─────────│
  │ ◀── { client_secret, ws_url,      │                                    │
  │       model, instructions,        │                                    │
  │       tools, voice, session_id }  │                                    │
  │                                                                        │
  │  connect WS wss://api.x.ai/v1/realtime?model=...                       │
  │  subprotocol: "xai-client-secret.<value>"  ──────────────────────────▶ │
  │  ◀───────────────── speech-to-speech audio + tool calls ─────────────▶ │
  │  POST /api/fun-ai/session/end { session_id, voice_seconds }            │
```

- Model/voice/provider come from `FUN_AI_VOICE_MODEL` (default `grok-voice-latest`),
  `FUN_AI_GROK_VOICE` (default `eve`), `FUN_AI_VOICE_PROVIDER` (default `grok`).
- The client secret is short-lived (60–600s, default `FUN_AI_SESSION_SECONDS=300`) and passed as a
  **WebSocket subprotocol**, so even a leaked token expires fast and can't act as the API key.

## Session creation (`POST /api/fun-ai/session`)

Two **surfaces**:
- `news` — the Interactive News anchor (mode + optional topic; opens with verified updates on the
  listener's followed stories).
- `player` — the "Talk to Fun AI on the Radio Player" anchor, scoped to the current station; the
  tool set and instructions depend on whether the station is FUUSIC-managed or third-party.

The server composes the AI's **instructions** from three parts and injects them into the session:
`{personality} {anchor/mode or player instructions} {memory_instructions}`, plus a tool spec. It
also enforces **quotas** before minting a token:
- Daily session cap (`FUN_AI_MAX_SESSIONS_PER_DAY`) → `429 session_limit`.
- Daily voice minutes (`FUN_AI_MAX_VOICE_MINUTES_PER_DAY_FREE` / `_PREMIUM`) → `429 quota_exceeded`.
- `403 fun_ai_disabled` if the feature flag is off; `503 voice_unconfigured` if no `XAI_API_KEY`
  (the standard, non-voice news program still plays in that case).

Sessions are logged to `db.fun_ai_sessions`; `/session/end` records `voice_seconds` against the
daily quota.

## Radio Programming Policy Engine (`fun_ai_radio_policy.py`)

**Fun AI is never the final authority on radio actions.** Every action that comes out of a
conversation is validated against a configurable, jurisdiction-aware policy doc stored in
`app_settings` (`fun_ai_radio_policy`) so admins can tune it without code.

Default guardrails:
- **On-demand is denied** — `play_exact_song`, `play_song`, `queue_song`, `play_artist_sequence`
  are refused. This is what keeps FUUSIC a *radio* product, not a jukebox.
- **FUUSIC-managed stations** allow: `format_change`, `mood_change`, `energy_change`,
  `language_change`, `station_preference`, `change_station`, `skip` (rate-limited,
  `skip_per_hour=6`), `record_feedback`.
- **Third-party live stations** are locked: only `change_station` + `record_feedback` (the AI may
  switch stations but never re-order someone else's stream).
- Eligible programming options are enumerated in `FORMATS` (energy/mood/genre/language).

The player surface calls `policy.resolve_station_type(...)` to decide the allowed tool set, and
`/api/fun-ai/radio/action` + `/radio/undo` route steering actions through this engine.

## RJ Personalities

Selectable anchor personas (Friendly · Energetic · Calm · Funny · Thoughtful) via
`svc.list_personalities()` / `DEFAULT_PERSONALITY`; the chosen persona's `personality_instructions`
are prepended to the session prompt. Stored per user in Fun AI preferences
(`GET/PUT /api/fun-ai/preferences`).

## Companion Memory

Approved listener preferences the AI honours **every** session. Shared contract:
`GET/PUT/POST /api/fun-ai/memory`, `POST /memory/remove`, `POST /memory/clear`. Categories:
favourite genres, favourite stations, disliked genres, languages, interests. ON by default with an
on/off toggle + clear-all; injected server-side via `memory_instructions`. Auth-gated (self-hides
for signed-out users). UI: web `FunAI/FunAiMemory.jsx` (embedded in Interactive News + NowPlaying),
mobile `src/fun-ai/FunAiMemory.tsx` + dedicated `app/fun-ai-memory.tsx` screen (Profile → Companion
Memory).

## Interactive News

`GET /api/fun-ai/news/briefing` builds the program from the existing news system
(`db.news_articles` + NewsData provider) and returns `breaks[]` for sponsor insertion. The four
modes shape length/depth (`svc.mode_instructions`). "Follow This Story" is backed by the follows
API: `GET/POST/DELETE /api/fun-ai/follows` + `GET /follows/updates` (the session opens with
verified updates on followed stories). `POST /api/fun-ai/news/search` does source-grounded
retrieval (the Grok `search_news` tool).

## Sponsor Breaks (monetization)

`briefing` returns `breaks[]` with placement by `after_index`: **opening** (−1), **mid**
(`mid_after_segment`, clamped), **closing** (segment count).
- **Paid breaks** (have `audio_url`) play recorded audio.
- **Text-only sponsorship** breaks show a disclosed "Sponsored" card **and** are read aloud (web
  `speechSynthesis`, mobile `expo-speech`).
- Each break start fires `POST /api/fun-ai/news/break-event` → an impression that decrements the
  paid-ad budget via `rj_sponsored_read_service.record_play`.
- **Premium users are ad-free** (`breaks == []`). Every break has a **Skip** control.
- Admin visibility: `GET /api/admin/fun-ai/break-report?days=` (impressions by placement, unique
  listeners, paid-spend) surfaced in web `AdminFunAiNews.jsx`. Program sponsorship
  (opening/closing) is free underwriting and carries no spend.

Collections: `fun_ai_sessions`, `fun_ai_sponsor_events`, `rj_sponsored_reads`,
`rj_sponsored_read_plays`; sponsor config in `app_settings` (`fun_ai_news`).

## Fun AI endpoint map (`/api/fun-ai`)

| Method & path | Purpose |
|---------------|---------|
| `GET /config` | Flags, voice availability, personalities, modes, sponsor summary |
| `POST /session` · `POST /session/end` | Mint ephemeral token / record usage |
| `GET /news/briefing` · `POST /news/search` | Build program / source-grounded search |
| `GET/PUT /preferences` | Personality & Fun AI prefs |
| `GET/PUT/POST /memory` · `POST /memory/remove` · `POST /memory/clear` | Companion Memory |
| `POST /news/break-event` | Sponsor break impression |
| `GET/POST /follows` · `DELETE /follows/{id}` · `GET /follows/updates` | Follow This Story |
| `GET /radio/formats` · `GET /radio/now-playing` | Programming options / current state |
| `POST /radio/action` · `POST /radio/undo` | Policy-checked steering actions |
| `GET /usage` | Daily voice-minute / session usage |

## Feature flags (backend `.env`)

`FUN_AI_ENABLED`, `FUN_AI_NEWS_ENABLED`, `FUN_AI_COMPANION_ENABLED`, `FUN_AI_SPONSORSHIP_ENABLED`,
`FUN_AI_VOICE_PROVIDER`, `FUN_AI_VOICE_MODEL`, `FUN_AI_GROK_VOICE`, `FUN_AI_SESSION_SECONDS`,
`FUN_AI_MAX_VOICE_MINUTES_PER_DAY_FREE|PREMIUM`, `FUN_AI_MAX_SESSIONS_PER_DAY`, `XAI_API_KEY`.
