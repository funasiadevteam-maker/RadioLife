# 00 — Project Overview

## What FUUSIC is

FUUSIC is an **interactive, AI-powered radio** experience delivered as one product across **web**
and **mobile**, backed by a **single shared API**. Its founding thesis:

> Make radio *interactive and personal* — a listener can talk to a fun AI RJ, steer the news,
> and get a companion that remembers their taste — **without** turning it into an on-demand
> music platform. Radio stays "lean-back"; the AI adds "lean-in" moments.

Around that core, the product has expanded into a **social-audio super-app**. The major domains:

1. **AI Radio & Audio** — live/imported radio stations (50k+ catalog), AI-curated "FUUSIC"
   stations, AI RJ voiceovers between tracks, podcasts, commute mode.
2. **Fun AI (the heart)** — conversational RJ via **xAI Grok Realtime Voice**, Interactive News
   (Morning Briefing / News in 2 Mins / Deep Dive / Follow This Story), a Radio Programming
   **Policy Engine**, RJ **Personalities**, **Companion Memory**, and **Sponsor Breaks**.
3. **Social** — feeds, following, Dreams & Guidance community (advisors, AI readings, live Q&A),
   live shopping shows.
4. **Commerce / Marketplace** — business storefronts, products/services/menus, memberships,
   gift cards, bookings, scan-to-pay, Premium Dining Club.
5. **Games & Rewards** — spin/scratch/trivia/predict-&-win, BigPoints/BigCoin wallet, streaks,
   sponsored games, bar games.
6. **Advertising** — banners, pre/mid-roll audio ads, sponsored stations, right-rail auctions,
   and a full **Partner API v1** (programmatic media buying, Phases A→F).
7. **Monetization plumbing** — Stripe payments & Connect payouts, subscriptions/Premium,
   commissions, vendor payouts.

## Surfaces

| Surface | Path | Stack | Backend URL env |
|---------|------|-------|-----------------|
| Web | `/app/frontend` | React 19, React Router 7, Tailwind + shadcn, Zustand, framer-motion | `REACT_APP_BACKEND_URL` |
| Mobile | `/app/mobile` | Expo SDK 54, expo-router 6, RN 0.81, Reanimated 4 | `EXPO_PUBLIC_BACKEND_URL` |
| Backend | `/app/backend` | FastAPI 0.110, Motor (async Mongo), Pydantic 2 | `MONGO_URL` / `DB_NAME` |

Both clients call the **same** `/api` contract. The backend is platform-agnostic; surface
differences live only in the clients. See `01_SYSTEM_ARCHITECTURE.md`.

## Repository map

```
/app
├── backend/                 FastAPI + MongoDB (shared API)
│   ├── server.py            Main app (~8.4k lines): FastAPI init, middleware, /api router, startup
│   ├── auth.py              Cookie+Bearer sessions, email/pw, Google/Apple OAuth glue
│   ├── routes/              ~240 feature route modules (each an APIRouter)
│   ├── services/            ~265 business-logic modules (the real work)
│   ├── models/              Pydantic/Mongo models (billing, games, radio, rj, tracks)
│   ├── core/                db, config, brand, features, origins, home_config, state
│   ├── scripts/             Seeders & one-off migrations
│   ├── tests/               pytest suites (also /app/test_reports/iteration_*.json)
│   └── .env                 MONGO_URL, DB_NAME, all integration keys (protected)
│
├── frontend/                React web client
│   └── src/
│       ├── App.js           Router + design-variant switch
│       ├── pages/ (157)     Route-level screens
│       ├── components/ (128) Shared UI incl. components/ui (shadcn)
│       ├── design_v2/       "New Look V2" premium dark shell (AppShellV2, HomeNewLookV2…)
│       ├── design_radiolife/ RadioLife screen set (NowPlayingRadioLife…)
│       ├── FunAI/           Fun AI web UI (FunAiMemory.jsx…)
│       ├── store/           Zustand stores (player, feature prefs, sleep timer…)
│       ├── theme/           useTheme store, AccentSwatches, ThemeToggle
│       └── index.css        CSS variables: theme + accent + auto-contrast tokens
│
├── mobile/                  Expo React Native client
│   ├── app/                 expo-router routes (file = route)
│   │   ├── (tabs)/          Bottom-tab screens (home, listen, shop, play, social, …)
│   │   └── _layout.tsx      Root layout (icon prewarm, providers) — preserve
│   └── src/
│       ├── fun-ai/          FunAiMemory.tsx + grok voice bridges
│       ├── theme/           ThemeProvider.tsx, tokens.ts (accents + contrast)
│       ├── stores/          Zustand stores
│       └── utils/           storage/ + upload helpers (reuse, don't reinvent)
│
├── memory/                  PRD.md, CHANGELOG.md, ROADMAP.md, test_credentials.md, discovery notes
├── docs/                    PARTNER_API.md, sales deck, + system-design/ (this set)
├── scripts/                 Repo-level utility scripts
└── test_reports/            testing-agent output (iteration_<n>.json)
```

## Quick start (inside the container — services already run under supervisor)

- Do **not** start servers yourself. Restart only after `.env`/dependency changes:
  `sudo supervisorctl restart backend | frontend | mobile`
- Backend: `0.0.0.0:8001`, Web: `3000`, Expo web preview: `3001`. Any `/api/*` path routes to
  the backend; everything else to the client.
- API smoke test (web): `curl $REACT_APP_BACKEND_URL/api/health` (also `/health`, `/healthz`).
- Logs: `tail -n 100 /var/log/supervisor/{backend,frontend,mobile}.*.log`.

## Test logins (full list in `/app/memory/test_credentials.md`)

| Role | Email | Password |
|------|-------|----------|
| Admin | `admin@bigfm.dubai` | `AdminPass123!` |
| Demo (Premium, owns business) | `demo@bigfm.dubai` | `DemoPass123!` |
| Business owner | `test@bigfm.dubai` | `TestUser123!` |
| Premium | `premium@bigfm.dubai` | `PremiumTest123!` |
| Free | `freeuser@bigfm.dubai` | `FreePass123!` |

> Web uses cookie auth (`POST /api/auth/login`). Mobile uses a Bearer token — tap **Try the demo**
> (`demo-login-btn` → `POST /api/auth/demo`); password login is disabled on mobile by design.

## Glossary

- **Fun AI** — the interactive AI layer (RJ voice + news + memory + sponsor breaks). Code lives in
  `routes/fun_ai.py`, `services/fun_ai_service.py`, `services/grok_realtime.py`,
  `services/fun_ai_radio_policy.py`.
- **RJ** — Radio Jockey / AI DJ. Voiceovers between tracks and the conversational anchor.
- **Policy Engine** — guardrails that keep Fun AI radio-first (what the AI may/may not do on air).
- **Companion Memory** — approved listener preferences the AI honours each session.
- **BigPoints / BigCoin** — the rewards wallet currency (points earned via plays/streaks/shares).
- **Partner API v1** — the programmatic advertising API under `/api/v1` (separate from `/api`).
- **New Look V2** — the premium dark web design variant (`/app/frontend/src/design_v2`).
- **Flagship stations** — hand-curated hero stations (e.g. Big 106.2) vs. the 50k imported catalog.
