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
