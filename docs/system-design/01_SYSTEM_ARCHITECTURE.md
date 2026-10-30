# 01 — System Architecture

## One backend, two clients

```
                         ┌─────────────────────────────────────────────┐
                         │                 Clients                     │
                         │                                             │
   ┌─────────────────┐   │   ┌──────────────────┐  ┌────────────────┐ │
   │  Web (React 19) │   │   │ Web preview :3000│  │ Expo web :3001 │ │
   │  /app/frontend  │───┼──▶│                  │  │ /app/mobile    │ │
   └─────────────────┘   │   └──────────────────┘  └────────────────┘ │
                         └──────────────┬──────────────────────────────┘
                                        │  HTTPS, path-based routing
                        /api/*  ────────┼──────────  everything else → client
                                        ▼
                         ┌─────────────────────────────────────────────┐
                         │        FastAPI backend  0.0.0.0:8001         │
                         │        /app/backend/server.py                │
                         │  APIRouter(prefix="/api") + ~306 routers     │
                         │  + Partner API router (prefix "/api/v1")     │
                         └──────────────┬──────────────────────────────┘
                                        │
             ┌──────────────┬───────────┼───────────┬──────────────────┐
             ▼              ▼           ▼            ▼                  ▼
        MongoDB         xAI Grok    OpenAI /     Stripe /          Tigris (S3)
       (Motor async)   Realtime     Emergent     Stripe Connect   object storage
                        Voice       LLM key                        (boto3)
             │              │           │            │                  │
             └── LiveKit (mock) · Mailgun · NewsData · Google Maps · Travelpayouts ──┘
```

### Why path-based routing matters

The ingress sends any request whose path starts with `/api` to the backend on `8001`; all other
paths go to the active client. **Every backend route must therefore be mounted under `/api`**
(the Partner API uses `/api/v1`). `localhost:8001` works for local curl but will not give a true
end-to-end response from a client — always test clients against the external
`REACT_APP_BACKEND_URL` / `EXPO_PUBLIC_BACKEND_URL`.

## Services & ports

| Service | Supervisor name | Bind | Hot reload | Notes |
|---------|-----------------|------|-----------|-------|
| Backend | `backend` | `0.0.0.0:8001` | yes | FastAPI/uvicorn |
| Web | `frontend` | `:3000` | yes | CRA/craco dev server |
| Mobile | `mobile` | `:3001` | **no** (preview) | Expo/Metro web preview — **restart after changes** |

The web preview URL is `REACT_APP_BACKEND_URL`'s host; the Expo preview is a different host
(usually with `expo.` inserted). Never hardcode either — read from `.env`.

## Per-surface backend URL (the env split)

- Web → `process.env.REACT_APP_BACKEND_URL` + `/api/...`
- Mobile → `process.env.EXPO_PUBLIC_BACKEND_URL` + `/api/...` (no port appended)
- Backend DB → `os.environ['MONGO_URL']`, `os.environ['DB_NAME']`

## Request lifecycle (typical authenticated call)

1. Client sends `GET /api/<resource>` with the session **cookie** (web) or
   `Authorization: Bearer <token>` (mobile).
2. Ingress routes `/api/*` → backend.
3. Middleware runs (CORS, security headers, launch-guard for soft-launch mode, cache middleware).
4. The matching `APIRouter` handler resolves the user via `current_user` /
   `current_user_optional` (in `auth.py`) and executes.
5. Handlers delegate to a **service** module for business logic; services read/write MongoDB via
   Motor and call external providers as needed.
6. Responses return **serialized Pydantic models / plain dicts** — never raw Mongo docs with
   `ObjectId` (see `02_BACKEND_DESIGN.md`).

## Configuration & secrets

All config is environment-driven (nothing hardcoded). Backend `.env` holds integration keys:
Mongo, Stripe (+ mode), OpenAI, Emergent LLM/Push keys, xAI (`XAI_API_KEY` + `FUN_AI_*` flags),
ElevenLabs, Mailgun, Tigris (S3), LiveKit, NewsData/NewsAPI, Google (Maps/OAuth), Travelpayouts,
and feature flags. Clients only ever receive the public backend URL (+ Stripe publishable key +
Maps key on web). Secrets never reach the client; e.g. `XAI_API_KEY` stays server-side and the
browser/phone gets a short-lived **ephemeral token** instead (see `05_FUUSIC_AI_RADIO.md`).

> Keys are managed via the platform's secure secrets UI. Never read/print or edit key values in
> chat or `.env` directly for user-provided secrets.

## Deploy hardening (baked into `server.py` / `core/db.py`)

The app runs in Kubernetes with a bounded deploy-ready window, so startup is defensive:

- **Non-blocking startup handlers** — `@app.on_event("startup")` handlers (index creation + ~21
  seeders) are monkey-patched into fire-and-forget `asyncio.create_task(...)`, so the ASGI
  lifespan reaches `yield` instantly instead of blocking on Mongo for tens of seconds.
- **Mongo-free health probes** — `/health`, `/healthz` (root scope, not `/api`) resolve
  synchronously without touching Mongo, reporting `uptime_seconds` + `version` so K8s readiness
  passes while seeders are still running.
- **Fast-failing Mongo client** — `core/db.py` builds the Motor client with a 3s
  `serverSelectionTimeoutMS` and falls back to a localhost placeholder if SRV DNS resolution
  fails at construction, so a transient DNS blip surfaces as a clean request-time 500 instead of
  a boot crash + rollback.

## Testing & verification

- Backend: `curl` the external backend URL; pytest suites in `/app/backend/tests`.
- Web: screenshot the web preview URL; Playwright DOM assertions for client-only UI.
- Mobile: screenshot the **Expo** preview URL (never curl the mobile UI). Restart `mobile` first.
- The **testing agent** writes `/app/test_reports/iteration_<n>.json`; the latest iterations here
  are 232–235 (Companion Memory/Sponsor Breaks, Light/Dark onboarding, Accents/Scheduled Dark,
  Auto-Contrast).
