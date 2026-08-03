# Phase 18 — Mobile Advertiser Mirror Handoff

## Screen Routes

| Route | File | testID | Purpose |
|-------|------|--------|---------|
| `/advertiser` | `app/advertiser/index.tsx` | `advertiser-home` | Balance, campaigns list, top-up |
| `/advertiser/onboard` | `app/advertiser/onboard.tsx` | `advertiser-onboard` | 3-step onboarding form |
| `/advertiser/ai-create` | `app/advertiser/ai-create.tsx` | `ai-creator` | AI Ad Creator (script+voice+image) |
| `/advertiser/campaign/new` | `app/advertiser/campaign/new.tsx` | `campaign-wizard` | 4-step campaign wizard |
| `/advertiser/campaign/[id]` | `app/advertiser/campaign/[id].tsx` | `campaign-detail` | Campaign detail with 3 tabs |

## Key testIDs

- `mobile-advertiser-onboard-submit` — onboard form submit
- `mobile-advertiser-onboard-name` — business name input
- `mobile-advertiser-onboard-email` — contact email input
- `mobile-advertiser-topup-btn` — top-up button
- `mobile-advertiser-new-campaign` — new campaign CTA
- `mobile-ai-create-submit` — AI Creator entry in wizard
- `ai-generate-btn` — generate ad button
- `ai-step-script` / `ai-step-safety` / `ai-step-voice` / `ai-step-image` — progress stages
- `ai-safety` — safety verdict badge
- `ai-latency-chip` — latency display
- `wizard-step-1..4` — wizard step containers
- `wizard-attribution-window-hours` — attribution window input
- `freq-caps-editor` — frequency caps editor
- `mobile-campaign-conversions-tab` — conversions tab
- `mobile-campaign-overview-tab` — overview tab
- `conv-impressions` / `conv-saves` / `conv-redemptions` / `conv-checkins` — funnel KPIs
- `pacing-status-pill` — pacing status indicator
- `campaign-edit-window` / `campaign-save-window` — attribution window edit

## API Endpoints Used

All endpoints match the web frontend exactly:
- `GET /api/advertiser/me`
- `POST /api/advertiser/onboard`
- `POST /api/advertiser/{aid}/topup`
- `GET /api/advertiser/{aid}/campaigns`
- `POST /api/advertiser/{aid}/campaigns`
- `POST /api/advertiser/{aid}/campaigns/{cid}/submit`
- `GET /api/advertiser/{aid}/campaigns/{cid}`
- `GET /api/advertiser/{aid}/campaigns/{cid}/performance`
- `GET /api/advertiser/{aid}/campaigns/{cid}/attribution`
- `GET /api/advertiser/{aid}/campaigns/{cid}/pacing`
- `PATCH /api/advertiser/{aid}/campaigns/{cid}`
- `POST /api/advertiser/{aid}/campaigns/{cid}/pause`
- `POST /api/advertiser/{aid}/campaigns/{cid}/resume`
- `POST /api/advertiser/{aid}/ai/generate`
- `POST /api/advertiser/{aid}/ai/save`

## Deviations from Web

1. **Campaign wizard is 4 steps** (vs web's 5): Basics, Creative, Targeting, Advanced — condensed for mobile thumb-friendly flow.
2. **Creative upload not available** — only AI Creator path on mobile; upload requires multipart file selection.
3. **AI Creator image preview** shows placeholder text instead of actual image render (base64 image loading deferred).
4. **Top-up** opens Stripe Checkout in `expo-web-browser` (in-app browser) vs web's direct redirect.
5. **No admin screens** on mobile (ads queue, analytics, pacing health panel) — web-only.

## Audio Non-Interference

The advertiser screens do NOT import or interact with:
- `audioInit.ts`
- `nativePlayerBridge.ts`
- `usePlayerStore.ts`
- `react-native-track-player`

Background audio continues uninterrupted while using advertiser screens.
