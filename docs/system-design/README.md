# FUUSIC — System Design & Project Documentation

> Generated as an onboarding + architecture reference for the FUUSIC cross-platform app
> (one shared backend + web + mobile). Read these in order if you're new.

FUUSIC began as **"Interactive AI Radio"** — turning traditional radio into a personalized,
conversational experience (AI RJ, interactive news, talk-to-the-radio) **without** becoming an
on-demand music service. Over many iterations it grew into a full **social-audio super-app**:
radio + social + marketplace/commerce + games + a programmatic advertising (Partner) API +
payments. You will see three brand names in the code for historical reasons — they are the
**same app**:

| Name | Where it shows up |
|------|-------------------|
| **FUUSIC** | Current product/brand, FastAPI title, design system |
| **RadioLife** | PRD/CHANGELOG, test credentials, many docs |
| **BigFM** | Early code (`bigfm_*` cookies, `*.bigfm.dubai` test emails, `core/brand.py`) |

## Document index

| # | File | What it covers |
|---|------|----------------|
| 00 | [00_PROJECT_OVERVIEW.md](./00_PROJECT_OVERVIEW.md) | Product vision, surfaces, repo map, quick start, glossary |
| 01 | [01_SYSTEM_ARCHITECTURE.md](./01_SYSTEM_ARCHITECTURE.md) | High-level architecture, ports/routing, request flow, deploy hardening |
| 02 | [02_BACKEND_DESIGN.md](./02_BACKEND_DESIGN.md) | FastAPI layering, server.py, routes/services/models/core, Mongo patterns, auth |
| 03 | [03_FRONTEND_WEB_DESIGN.md](./03_FRONTEND_WEB_DESIGN.md) | React web app, routing, design variants, state, theming entry points |
| 04 | [04_MOBILE_DESIGN.md](./04_MOBILE_DESIGN.md) | Expo/React Native app, expo-router, native/web split, storage/upload, permissions |
| 05 | [05_FUUSIC_AI_RADIO.md](./05_FUUSIC_AI_RADIO.md) | The core: Grok realtime voice, interactive news, policy engine, RJ personas, memory, sponsor breaks |
| 06 | [06_DATA_MODEL.md](./06_DATA_MODEL.md) | Key MongoDB collections grouped by domain |
| 07 | [07_INTEGRATIONS.md](./07_INTEGRATIONS.md) | Third-party integrations, keys, test/live modes, what's mocked |
| 08 | [08_THEMING_SYSTEM.md](./08_THEMING_SYSTEM.md) | Light/Dark/Scheduled, Accent colours, Auto-Contrast (web + mobile) |

## At-a-glance scale

- **Backend**: FastAPI + MongoDB (Motor async). `server.py` ≈ 8.4k lines, ~240 route modules, ~265 service modules, ~306 `include_router` calls. All API paths under `/api`.
- **Web**: React 19 + React Router 7 + Zustand + Tailwind/shadcn + framer-motion. ~736 source files, 157 pages, 128 components, multiple design systems.
- **Mobile**: Expo SDK 54 + expo-router 6 + React Native 0.81 + Reanimated 4. ~220 files, ~140 route screens, tab-based IA.

## Other living docs (pre-existing, authoritative for history/backlog)

- `/app/memory/PRD.md` — product requirements + dated changelog of everything shipped
- `/app/memory/CHANGELOG.md` — newest work log
- `/app/memory/ROADMAP.md` — prioritized backlog
- `/app/memory/test_credentials.md` — all test logins & demo fixtures
- `/app/docs/PARTNER_API.md` — the programmatic advertising API (v1)
