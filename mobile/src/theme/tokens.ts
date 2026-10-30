// FUUSIC unified mobile theme tokens — Light + Dark. Semantic keys mirror the
// web design_guidelines.json AND stay drop-in compatible with the legacy
// `TUBE` palette (bg, elevated, glass, line, text, electric, gold, …) so
// screens migrate by swapping `TUBE.` → `t.` and wrapping StyleSheet in a
// makeStyles(t) factory. Shared with web via the same /api/shell/prefs value.

export const THEME = {
  dark: {
    bg: '#0B0F19',
    elevated: '#151B2B',
    glass: 'rgba(255,255,255,0.05)',
    line: 'rgba(255,255,255,0.09)',
    lineStrong: 'rgba(255,255,255,0.16)',
    card: '#151B2B',
    cardBorder: 'rgba(139,124,246,0.16)',
    text: '#F4F6FF',
    textDim: '#9AA3BF',
    textMuted: '#6B7490',
    // brand (purple → pink) — `electric`/`magenta` kept as aliases for legacy screens
    brand: '#A855F7',
    brandEnd: '#EC4899',
    electric: '#A855F7',
    magenta: '#A855F7',
    pink: '#EC4899',
    gold: '#FFD54A',
    green: '#22C55E',
    live: '#EF4444',
    onAccent: '#0A0A0C',
    accentInk: '#C084FC',
    inputBg: '#161C2E',
    inputBorder: 'rgba(255,255,255,0.12)',
    tabBarBg: '#0B0F19',
    tabBarBorder: 'rgba(255,255,255,0.09)',
    statusBar: 'light' as const,
    // COLORS-palette aliases (legacy warm-light screens migrate COLORS.→t.)
    primary: '#A855F7',
    secondary: '#3B82F6',
    surface: 'rgba(255,255,255,0.04)',
    surfaceBorder: 'rgba(255,255,255,0.10)',
    red: '#EF4444',
    orange: '#F59E0B',
    purple: '#A855F7',
    cardShadow: 'rgba(0,0,0,0.55)',
    statusBarStyle: 'light' as const,
  },
  light: {
    bg: '#FFFFFF',
    elevated: '#F4F4F5',
    glass: 'rgba(16,24,48,0.03)',
    line: '#E8E8EC',
    lineStrong: '#D4D4D8',
    card: '#FFFFFF',
    cardBorder: '#E4E4E7',
    text: '#101830',
    textDim: '#5C6880',
    textMuted: '#8B93A9',
    brand: '#9333EA',
    brandEnd: '#EC4899',
    electric: '#9333EA',
    magenta: '#9333EA',
    pink: '#EC4899',
    gold: '#C98A00',
    green: '#16A34A',
    live: '#E02020',
    onAccent: '#FFFFFF',
    accentInk: '#7E22CE',
    inputBg: '#F4F4F5',
    inputBorder: '#E4E4E7',
    tabBarBg: '#FFFFFF',
    tabBarBorder: '#E8E8EC',
    statusBar: 'dark' as const,
    // COLORS-palette aliases (legacy warm-light screens migrate COLORS.→t.)
    primary: '#9333EA',
    secondary: '#3B82F6',
    surface: 'rgba(16,24,48,0.03)',
    surfaceBorder: '#E4E4E7',
    red: '#E11D48',
    orange: '#F26B2A',
    purple: '#7C3AED',
    cardShadow: 'rgba(120,72,32,0.10)',
    statusBarStyle: 'dark' as const,
  },
};

export type ThemeTokens = typeof THEME.dark;
export type Appearance = 'light' | 'dark' | 'system';
export type AccentKey = 'violet' | 'coral' | 'teal' | 'amber' | 'blue';

// User-selectable accent. `violet` is the default (no override → keep the
// per-theme brand hues). Others re-tint the brand tokens on both themes.
export const ACCENTS: Record<AccentKey, { solid: string; end: string; swatch: string; onSwatch: string }> = {
  violet: { solid: '', end: '', swatch: '#A855F7', onSwatch: '#FFFFFF' },
  coral: { solid: '#F26B2A', end: '#FB7185', swatch: '#F26B2A', onSwatch: '#2A1200' },
  teal: { solid: '#0D9488', end: '#06B6D4', swatch: '#0D9488', onSwatch: '#FFFFFF' },
  amber: { solid: '#D97706', end: '#F59E0B', swatch: '#D97706', onSwatch: '#231600' },
  blue: { solid: '#2563EB', end: '#6366F1', swatch: '#2563EB', onSwatch: '#FFFFFF' },
};

// Text/icon colour to place ON an accent FILL (button, selected chip). Only the
// bright accents need dark ink; violet keeps the theme's own onAccent.
const ACCENT_ON: Partial<Record<AccentKey, string>> = {
  coral: '#2A1200', amber: '#231600', teal: '#FFFFFF', blue: '#FFFFFF',
};
// Accent tone for accent-coloured TEXT/BORDERS on the page bg — darker in Light,
// lighter in Dark, so it stays crisp against the background either way.
const ACCENT_INK_DARK: Record<AccentKey, string> = {
  violet: '#C084FC', coral: '#FB923C', teal: '#2DD4BF', amber: '#FBBF24', blue: '#93C5FD',
};
const ACCENT_INK_LIGHT: Record<AccentKey, string> = {
  violet: '#7E22CE', coral: '#C2410C', teal: '#0F766E', amber: '#B45309', blue: '#1D4ED8',
};

export function withAccent(t: ThemeTokens, accent: AccentKey, scheme: 'light' | 'dark' = 'dark'): ThemeTokens {
  const a = ACCENTS[accent];
  const accentInk = (scheme === 'light' ? ACCENT_INK_LIGHT : ACCENT_INK_DARK)[accent] || t.brand;
  if (!a || !a.solid) return { ...t, accentInk };   // violet: keep brand + theme onAccent
  return {
    ...t,
    brand: a.solid, brandEnd: a.end, electric: a.solid, magenta: a.solid,
    primary: a.solid, purple: a.solid, pink: a.end,
    onAccent: ACCENT_ON[accent] ?? t.onAccent,
    accentInk,
  };
}

