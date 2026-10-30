# 03 — Web Frontend Design (`/app/frontend`)

React 19 SPA served on `:3000`, calling the shared API via `REACT_APP_BACKEND_URL` + `/api`.

## Stack

| Concern | Choice |
|---------|--------|
| Framework | React 19 |
| Routing | `react-router-dom` 7 |
| Build | CRA + `craco` (`craco.config.js`) |
| Styling | Tailwind CSS + shadcn/ui (`src/components/ui`) + CSS variables (`index.css`) |
| State | Zustand (`src/store`, `src/theme`) + React context (`AuthContext.js`) |
| HTTP | `axios` |
| Animation | `framer-motion` |
| Charts | `recharts` |
| Icons | `lucide-react` (+ FontAwesome CDN in places) |
| Toasts | `sonner` |
| Payments | `@stripe/stripe-js` |

## Entry & routing

- `src/index.js` → `src/App.js`. `App.js` wires the router, global providers (auth, theme, player
  bridges, headless engines like the sleep timer and switch toast) and the **design-variant**
  switch.
- Pages (route-level) live in `src/pages/` (157) and several top-level `*.js/.jsx` files
  (e.g. `Home.jsx`, `Radio.js`, `InteractiveNews.jsx`, `Profile.js`, `Login.js`).
- Convention: **default export** for pages (`export default function PageName()`),
  **named export** for shared components (`export const ComponentName`).

## Design systems / variants

The web app carries more than one visual system, selectable via a header switcher / `?design=`:

| Variant | Folder | Description |
|---------|--------|-------------|
| **New Look V2** | `src/design_v2/` (38 files) | Premium dark, cinematic streaming home. `AppShellV2.jsx` is the shell that mounts nav, onboarding, and headless engines; `HomeNewLookV2.jsx`, `FuusicWorldGridV2.jsx`, `PlayerBarV2.jsx`, `RadioStationsHomeV2.jsx`. |
| **RadioLife** | `src/design_radiolife/` (93 files) | The RadioLife screen set, e.g. `screens/NowPlayingRadioLife.jsx` (the full-screen player hosting Talk-to-Fun-AI + Companion Memory). |
| **Classic / B** | top-level pages | Older default layouts, kept switchable. |

`classic_b` has historically been the default; `new_look_v2` is additive. When editing, confirm
which shell a change targets so you don't edit a non-active variant.

## State stores (`src/store`, `src/theme`)

- `store/usePlayerStore.js` — the single audio control surface. Tracks the active source (AI
  session / imported live station / podcast) and **enforces mutual exclusivity** (`setSession`
  atomically clears imported/podcast state) so two streams never play at once.
- `store/useFeaturePrefs.js` — which feature pillars the user enabled (drives Home + nav).
- `store/useSleepTimer.js`, `components/SleepTimerEngine.jsx` — headless sleep timer.
- `theme/useTheme.js` — Zustand theme store (mode/accent/schedule), persisted to
  `GET/PUT /api/shell/prefs`. See `08_THEMING_SYSTEM.md`.

## Key feature areas (web)

- **Radio**: `Radio.js`, `RadioDiscover.jsx`, `RadioHome.jsx`, `RadioBrowse.jsx`,
  `LiveRadioBrowse.jsx`. Discover highlights FUUSIC AI stations above the gold flagship strip,
  with Pinned / Resume / Recently-played rails.
- **Fun AI**: `InteractiveNews.jsx` (news modes + memory + sponsor breaks),
  `FunAI/FunAiMemory.jsx` (Companion Memory panel), and the player's Talk-to-Fun-AI entry on
  `design_radiolife/screens/NowPlayingRadioLife.jsx`. See `05_FUUSIC_AI_RADIO.md`.
- **Admin**: dozens of `Admin*.jsx` + `admin/` + `Admin/` (merchants, moderation, ad revenue,
  pacing, Fun AI sponsor report `AdminFunAiNews.jsx`, users, etc.).
- **Commerce / merchant**: `pages/merchant/*`, storefronts, dining club (`/dining*`), scan-to-pay.
- **Advertiser**: `advertiser/`, `pages/advertiser_v2/DeveloperApi.jsx` (Partner API portal +
  API explorer).
- **Settings**: `pages/AppearanceSettings.jsx` (`/settings/appearance`),
  `pages/PersonalizeHome.jsx` (`/settings/features`).

## Conventions that matter

- **`data-testid`** on every interactive / critical element (kebab-case, function-named). The
  testing agent relies on these. (Mobile uses `testID` — don't mix.)
- Use existing shadcn components in `src/components/ui` before adding new ones.
- Call the backend only via `REACT_APP_BACKEND_URL` with an `/api` prefix; never hardcode a URL.
- Images: use real URLs (stock/generated), render with `<img>`/shadcn; never inline base64.
