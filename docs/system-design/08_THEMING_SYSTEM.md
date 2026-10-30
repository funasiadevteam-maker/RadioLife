# 08 — Theming System (Light/Dark · Scheduled · Accents · Auto-Contrast)

A cross-platform theming system shared by web and mobile, synced per signed-in user via the
backend. This is the most recent area of active work (test iterations 233–235).

## Shared contract — `GET/PUT /api/shell/prefs`

`routes/shell.py` persists a single JSON preferences object on the user doc:

```json
{
  "theme": "light | dark | system",
  "accent": "violet | coral | teal | amber | blue",
  "theme_schedule": { "enabled": false, "dark_hour": 19, "light_hour": 7 }
}
```

- `VALID_ACCENTS = {violet, coral, teal, amber, blue}` (violet is the default).
- PUT does **partial** updates with defensive validation: invalid accent → violet, invalid theme →
  dark, bad hours → defaults (19/7). Cross-user isolation + cross-session sync are tested
  (backend 23/23, iter234).
- Because it's one shared endpoint, a change on web appears on the user's mobile and vice-versa.

## Web (`/app/frontend`)

- **Store**: `theme/useTheme.js` (Zustand) holds mode/accent/schedule and reconciles with the
  server (`/api/shell/prefs`). A hydrate-race guard prevents a fast user tap at startup being
  overwritten by the server reconcile.
- **Application**: `data-theme` and `data-accent` attributes on `<html>` drive CSS. `index.css`
  defines theme variables and, per accent, overrides `--brand-solid` / `--brand-grad-*` /
  `--accent-*` (violet = no attribute → default look, zero regression).
- **Auto-Contrast tokens** (iter235): `--on-accent` (ink placed **on** an accent fill — bright
  accents like coral/amber use dark ink, teal/blue/violet use white) and `--accent-ink` (the accent
  tone for accent-coloured **text/borders** on the page background, theme-aware: darker in light,
  lighter in dark). Shared classes were rewired: `.fz-grad`/`.fz-chip-active` → `var(--on-accent)`,
  `.fz-brand`/`.fz-chip` → `var(--accent-ink)`.
- **UI entry points**: `pages/AppearanceSettings.jsx` (`/settings/appearance` — mode + accent +
  scheduled dark), `theme/AccentSwatches.jsx`, `theme/ThemeToggle`, onboarding
  (`components/FeatureOnboarding.jsx` "Choose your look"), and a Light/Dark quick pick on
  `Login.js`.

## Mobile (`/app/mobile`)

- **Context**: `src/theme/ThemeProvider.tsx` exposes `useAppTheme()` (mode/accent/schedule), synced
  to the same `/api/shell/prefs`.
- **Tokens**: `src/theme/tokens.ts` holds the palette, the `ACCENTS` config, and
  `withAccent(t, accent, scheme)` which re-tints brand tokens
  (`brand/brandEnd/electric/magenta/primary/purple/pink`) and sets contrast-safe `onAccent`
  (bright accent → dark ink) and theme-aware `accentInk`. `ACCENTS[k].onSwatch` colours the
  selected-swatch checkmark.
- **UI entry points**: `src/theme/AccentSwatches.tsx`, Profile appearance section
  (`accent-swatches` + Scheduled Dark steppers), onboarding
  (`src/social/InterestOnboarding.tsx` "CHOOSE YOUR LOOK"), and a Light/Dark quick pick on
  `app/login.tsx`.

## Scheduled Dark Mode

Fixed, adjustable times (default Dark 19:00 / Light 07:00; no geolocation). When enabled, the local
clock drives the effective theme and a ~60s ticker re-evaluates; picking a manual mode turns the
schedule off. Deterministic (e.g. `dark_hour=0`, `light_hour=23` → dark).

## Design tokens (brand)

From `design_guidelines.json`: brand purple `#9333EA` → pink `#EC4899`; display font **Outfit**,
body **Plus Jakarta Sans**; radius tokens sm 6 / md 12 / lg 20 / pill 999; 8pt spacing scale. The
app persona: *"premium, unified social-audio — clean daylight feeds transitioning to a cinematic,
glassy midnight-navy listening lounge."*

## By-design limitation

Only **token-driven** elements re-tint with the accent. Components with **hardcoded** hex (e.g. the
FUUSIC wordmark) intentionally do not recolour. When adding UI that should follow the accent, use
the theme tokens / CSS variables — not literal colours.
