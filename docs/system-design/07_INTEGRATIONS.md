# 07 — Integrations

All integration config is environment-driven in `/app/backend/.env`. Keys never reach the client;
clients receive only the public backend URL (+ Stripe publishable key & Google Maps key on web).
Third-party work should always go through the platform's `integration_expert` playbooks, and
user-supplied secrets through the secure secrets UI — never read/print/edit key values directly.

## Status summary

| Integration | Env var(s) | Purpose | Status |
|-------------|-----------|---------|--------|
| **MongoDB** | `MONGO_URL`, `DB_NAME` | Primary datastore (Motor async) | Live |
| **xAI Grok Realtime Voice** | `XAI_API_KEY`, `FUN_AI_*` | Conversational AI RJ (speech-to-speech) | Live (user key; server-side ephemeral tokens) |
| **Emergent LLM key** | `EMERGENT_LLM_KEY` | OpenAI text/image + Gemini image via `emergentintegrations` | Live |
| **OpenAI** | `OPENAI_API_KEY`, `OPENAI_IMAGE_API_KEY` | RJ script text, TTS/STT, GPT Image | Live (note: has historically hit credit limits — RJ voiceovers degrade to music-only) |
| **ElevenLabs** | `ELEVENLABS_API_KEY`, `ELEVENLABS_DAILY_CHAR_CAP` | RJ TTS voices | Configured (env value noted as an invalid key-id in test creds — prefer OpenAI TTS demo voices) |
| **Stripe** | `STRIPE_API_KEY`/`SECRET`/`PUBLISHABLE`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_MODE` | Payments, hosted checkout, subscriptions | Live keys in pod env; preview runs **test mode** (`cs_test_...`, card 4242…) |
| **Stripe Connect** | (shares Stripe keys) | Vendor/advisor/restaurant payouts (Express accounts, transfers) | Live infra; KYC incomplete headlessly |
| **Mailgun** | `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `MAILGUN_FROM`, `EMAIL_PROVIDER` | Transactional email (outbid alerts, launch blasts, invites) | Live |
| **Tigris (S3)** | `STORAGE_BACKEND`, `TIGRIS_*` (`ACCESS_KEY_ID`/`SECRET`/`ENDPOINT_URL`/`REGION`/`BUCKET`) | Object storage via boto3 — tracks, artwork, creatives (presigned PUT) | Live |
| **LiveKit** | `LIVEKIT_URL`/`API_KEY`/`API_SECRET`/`PROVIDER` | Live audio/video rooms (dream live Q&A, live shopping) | **MOCKED** (mock-safe client; real A/V needs a native build) |
| **NewsData / NewsAPI** | `NEWSDATA_API_KEY`, `NEWSAPI_API_KEY`, `NEWS_PROVIDER`, limits | Source news for Interactive News | Live |
| **AssemblyAI** | `ASSEMBLYAI_API_KEY` | Podcast / audio transcription | Live |
| **Google Maps** | `GOOGLE_MAPS_API_KEY`, `MAPS_PROVIDER` | Places, geocoding, nearby | Live |
| **Google OAuth** | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` | Own-client sign-in (web cookie / mobile deep-link token) | Preview works; **prod blocked** on redirect-URI config in user's GCP (`redirect_uri_mismatch` 400) |
| **Apple Sign-In** | (SIWA via `routes/auth_apple.py`, `services/apple_siwa.py`) | Mobile/web Apple login | **Blocked** — user must supply the `.p8` key |
| **Travelpayouts / Aviasales / Klook** | `TRAVELPAYOUTS_API_TOKEN`, `TRAVELPAYOUTS_WL_MARKER`, `TRAVELPAYOUTS_SUBID` | Affiliate travel (Shop → Travel) | Live (affiliate IDs) |
| **Emergent Push** | `EMERGENT_PUSH_KEY` | Device push notifications | Placeholder until deploy; **needs** Firebase `google-services.json` + a native build; cannot test on Expo Go/preview. **Never edit the key value.** |
| **Predexon** | `PREDEXON_API_KEY`, `PREDEXON_BASE_URL` | Prediction data provider | Configured |
| **ACRCloud** | `ACRCLOUD_TOKEN` | Music/audio recognition | Configured |
| **GAM / OpenRTB / SSP adapters** | `GAM_FERNET_KEY`, `OPENRTB_FLOOR_CENTS`, `OPENRTB_TIMEOUT_MS` | Programmatic ad demand (Magnite, PubMatic, OpenX, Index Exchange, mock) | Adapter layer (mock + real adapters) |

## Emergent LLM / Universal key — what it covers

`EMERGENT_LLM_KEY` (via the `emergentintegrations` library) is used for Claude text, OpenAI text +
image (GPT Image), Gemini image (Nano Banana), and OpenAI Whisper/TTS/STT. It does **not** cover
other third-party audio or arbitrary providers. For AI media on fal.ai, the Emergent Universal Key
can be used in `universal_key` mode. Do not install provider SDKs directly — use the integration
playbooks.

## What's mocked / pending (be honest about these)

- **LiveKit A/V** — mocked in preview; real media only on a native build after Publish.
- **Google OAuth (prod)** — blocked until the user adds the production redirect URI in GCP.
- **Apple Sign-In** — blocked until the user supplies the `.p8` file.
- **Push notifications** — in-app alerts work; real device push needs `google-services.json` + a
  native build.
- **Stripe in preview** — test mode; "LIVE" keys exist but preview checkout returns `cs_test_...`.

## Known runtime caveat (from PRD)

OpenAI credit exhaustion can make RJ script/voiceover generation fail; the radio pipeline
(`server.py _build_one_segment`) **degrades to a music-only segment** on any RJ/LLM/TTS upstream
failure so playback never stalls — the voiceover simply goes silent until credits/keys are
restored.
