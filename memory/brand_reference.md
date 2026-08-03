# BigFM AI — brand reference (Phase 15a anchor)

## Source
`bigfantv.com` was scoped as the visual anchor. Scrape (2026-05-27) shows the
domain currently resolves to the deployed BigFM Phase-1 login. There is no
independent third-party brand to clone — the brand IS BigFM. We treat the
explicit Phase 15a token spec as the source of truth and lay the new shell
on top of the existing deployment.

## Design vocabulary — extracted from the user brief
Tone: late-night radio confidence. Energetic but uncluttered. Cards float
on a near-black canvas, accents pulse only on live / game / reward moments.

### Surfaces
- `--bg-base: #0A0A0F`        — page canvas (solid, never gradient).
- `--bg-elevated: #14141C`    — primary card surface.
- `--bg-glass: rgba(255,255,255,0.04)` + `backdrop-blur(20px)` — overlays,
  mini-player, action sheets. Restrained: never on dense tables.
- Card border: 1px `rgba(255,255,255,0.06)` + soft shadow
  (`0 2px 8px rgba(0,0,0,0.4), 0 8px 32px rgba(0,0,0,0.25)`).
- Radii: 12px default, 20px cards, 28px hero player, `9999px` pills.

### Accents
- `--accent-electric: #00D4FF` — radio, primary CTAs (replaces the old
  pink primary).
- `--accent-magenta:  #FF2E8E` — gaming, Play & Win.
- `--accent-gold:     #FFB400` — rewards, wallet, Passport.
- `--accent-success:  #00E08A`
- `--accent-live:     #FF3B30` — pulsing red dot for live shows, scores.

### Type
- Display (radio player, TV surface, hero): **Space Grotesk 700**, tight
  tracking (`-0.02em`).
- Body / UI: **Inter 400/500/600**.
- Mono (game codes, QR captions, debug overlays): **JetBrains Mono 400/600**.

### Motion
- 150ms `ease-out` for interactive states (hover, focus, press).
- 200ms fade + 4px Y translate for route changes.
- Confetti + haptic on the mobile win moment (Play & Win, Trivia).
- Cards lift 2px on hover desktop only.

### Buttons
- Pill geometry for primary CTAs (`rounded-full`, height 44 desktop / 48
  mobile).
- Outline cyan for secondary ("Try the demo").
- Ghost (`bg-transparent`, white/65) for utility.

### Glassmorphism scope
- Mini-player background.
- Action sheets (mobile bottom drawer, desktop modals).
- Floating toast.
NOT for: data tables, dense lists, dashboards, admin grids.

## Layout vocabulary
- Desktop (≥1024): left rail 240px (collapsible 64px) + top bar + main +
  bottom player.
- Tablet (768–1023): icon rail 64px + 6-col main + bottom player.
- Mobile (<768): bottom tab (5 visible + overflow), persistent mini-player
  above tab bar.
- "One codebase, two layouts" — desktop is not a stretched mobile.

## Components born in 15a
- `Card`, `Button`, `Chip`, `StationTile`, `GameTile`, `WalletItemCard`,
  `MiniPlayer` (stub).

## Future phases that inherit this vocab
- 15b — Radio / Wallet / Trivia route polish.
- 15c — Public marketing pages.
- 16 — Live Trivia + TV display + Venue Staff (TV surface uses Space
  Grotesk display weight + accent-electric / accent-live).
- 18 — Advertiser Dashboard (electric primary, gold conversion rail).
