# 04 — Mobile App Design (`/app/mobile`)

Expo SDK 54 / React Native 0.81 app, served through the **Expo web preview** (`:3001`) and Expo
Go. Calls the shared API via `EXPO_PUBLIC_BACKEND_URL` + `/api`.

## Stack

| Concern | Choice |
|---------|--------|
| Framework | Expo SDK ~54, React Native 0.81 |
| Routing | `expo-router` 6 (file-based) |
| State | Zustand (`src/stores`) |
| Animation | `react-native-reanimated` 4, `react-native-gesture-handler` |
| Images | `expo-image` (always — never bare RN `Image`) |
| Audio/Video | `expo-audio`, `expo-video`, `expo-speech` (used for text-only sponsor reads) |
| Icons | `@react-native-vector-icons` (Ionicons per design guidelines) |
| HTTP | `axios` |

## Routing (expo-router, file = route)

- `app/_layout.tsx` — root layout: providers (incl. `ThemeProvider`), icon prewarm, push
  registration. **Preserve the prewarm/providers already here.**
- `app/(tabs)/_layout.tsx` — bottom-tab navigator using expo-router `Tabs`. Several screens in the
  group are hidden from the bar via `options={{ href: null }}` (e.g. `listen`, `radio`, `wallet`)
  and reached by navigation instead; the visible tabs cover Home / News / Shop / Social / Games /
  Profile etc.
- `app/index.tsx` — entry route `/`; `app/login.tsx`, `app/onboarding.tsx`.
- Feature routes mirror the domains, e.g. `app/fun-ai-news.tsx`, `app/fun-ai-memory.tsx`,
  `app/now-playing.tsx`, `app/shop/*`, `app/merchant/*`, `app/social/dreams/*`, `app/dining/*`,
  `app/games/*`, `app/advertiser/*`, `app/bar/*`. (~140 route files total.)
- Navigate with `useRouter()` / `useLocalSearchParams()`; keep non-route code under `src/`.

## `src/` layout

| Folder | Contents |
|--------|----------|
| `fun-ai/` | `FunAiMemory.tsx` (Companion Memory), `grokVoiceNative.native.ts` + `grokVoiceNative.ts` (the native/web split — see below) |
| `theme/` | `ThemeProvider.tsx` (context), `tokens.ts` (palette + `ACCENTS` + `withAccent` + contrast), `AccentSwatches.tsx` |
| `stores/` | `usePlayerStore.ts`, `useFeaturePrefs.ts`, `useBigCoinStore.ts`, `useCartStore`/`useProductCart`/`useSavedForLater`, `useStationsStore`, `useTriviaRoom`, `gateStore` |
| `components/` | ~29 shared RN components (SafeImage, BarGameCard, MiniToast, player bits…) |
| `social/` | Social tab pieces incl. `InterestOnboarding.tsx`, `wall.tsx` |
| `utils/` | `currency`, `distance`, `fileToBase64`, `gameFX`, `geocode`, `normalizeRoomCode`, `pushNotifications` |
| `api/`, `services/`, `hooks/`, `contexts/`, `config/`, `constants/` | supporting layers |

## Native vs web split (critical — do not break)

Live microphone capture for "Talk to Fun AI" uses a **native-only audio module** that would crash
the Expo **web** preview. The code is split by Metro's platform resolution:

- `src/fun-ai/grokVoiceNative.native.ts` — the real native implementation (mic streaming to Grok).
- `src/fun-ai/grokVoiceNative.ts` — a **web-safe stub** so the web preview can render.

Metro picks `.native.ts` on device and `.ts` on web automatically. Keep this separation intact; it
is the reason the mobile app previews at all.

> Live voice (and anything needing native audio/push) **cannot be validated on Expo Go or the web
> preview** — it requires a native build via the Emergent **Publish** button. Always tell the user
> this before claiming it works.

## Mobile conventions

- Components: React Native only (`View`, `Text`, `Pressable`, `ScrollView`). **All text in
  `<Text>`.** Use `onPress` (not `onClick`), `StyleSheet.create()` (no CSS/`className`), and
  `testID` (not `data-testid`).
- Backend calls via `EXPO_PUBLIC_BACKEND_URL` + `/api` (no port). Auth is a **Bearer token** (demo
  login), not a cookie.
- Install deps with `yarn expo install` (SDK-pinned), run from `/app/mobile`.
- Respect safe areas; horizontal chip rows never wrap (single horizontal scroller); never use RN
  `Alert` — use bottom sheets / toasts.
- Permissions (camera/mic/photos/notifications/location) follow the contextual request → handle
  all states → "Open Settings" on permanent denial flow, declared in `app.json`.
- **Restart `mobile` (`sudo supervisorctl restart mobile`) after changes** — the preview does not
  reliably hot-reload.

## Theming on mobile

`ThemeProvider.tsx` exposes `useAppTheme()` (mode + accent + schedule), persisted via
`GET/PUT /api/shell/prefs`. Colours come from `tokens.ts` where `withAccent(t, accent, scheme)`
re-tints brand tokens and sets contrast-safe `onAccent` / `accentInk`. See `08_THEMING_SYSTEM.md`.
