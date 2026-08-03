import { StyleSheet } from 'react-native';

/* ── RadioLife Light-Mode Design Tokens ──
   Matches the web RadioLife palette: slate-50 bg, white cards,
   slate-900 text, pink brand accent, teal secondary. */

export const COLORS = {
  bg: '#f8fafc',           // slate-50
  primary: '#ff2d95',      // BigFM magenta
  secondary: '#00d9ff',    // BigFM teal
  gold: '#d97706',         // amber-600 (readable on light)
  text: '#0f172a',         // slate-900
  textDim: '#475569',      // slate-600
  textMuted: '#94a3b8',    // slate-400
  surface: 'rgba(0,0,0,0.02)',
  surfaceBorder: '#e2e8f0', // slate-200
  card: '#ffffff',
  cardBorder: '#e2e8f0',   // slate-200
  green: '#16a34a',        // green-600
  red: '#e11d48',          // rose-600
  orange: '#ea580c',       // orange-600
  purple: '#7c3aed',       // violet-600
  inputBg: '#f1f5f9',      // slate-100
  inputBorder: '#cbd5e1',  // slate-300

  /* extras */
  cardShadow: 'rgba(0,0,0,0.06)',
  tabBarBg: '#ffffff',
  tabBarBorder: '#e2e8f0',
  statusBarStyle: 'dark' as const,
};

export const SPACING = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 };
export const RADIUS = { sm: 8, md: 12, lg: 16, xl: 24, full: 999 };
export const FONT = { xs: 10, sm: 12, md: 14, lg: 16, xl: 20, xxl: 28, hero: 36 };

export const common = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  row: { flexDirection: 'row', alignItems: 'center' },
  pill: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: RADIUS.full,
    borderWidth: 1,
    borderColor: COLORS.cardBorder,
    backgroundColor: COLORS.card,
  },
  pillActive: {
    backgroundColor: COLORS.primary,
    borderColor: COLORS.primary,
  },
  pillText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  pillTextActive: { color: '#fff', fontWeight: '700' },
  mono: { fontVariant: ['tabular-nums'], letterSpacing: 1.5, textTransform: 'uppercase' as const },
  btnPrimary: {
    backgroundColor: COLORS.primary,
    paddingVertical: 16,
    borderRadius: RADIUS.lg,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    flexDirection: 'row' as const,
    gap: 8,
  },
  btnPrimaryText: { color: '#fff', fontWeight: '800', fontSize: FONT.md, letterSpacing: 0.5 },
  btnGhost: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: COLORS.cardBorder,
    paddingVertical: 14,
    borderRadius: RADIUS.lg,
    alignItems: 'center' as const,
    justifyContent: 'center' as const,
    flexDirection: 'row' as const,
    gap: 8,
  },
  btnGhostText: { color: COLORS.textDim, fontWeight: '600', fontSize: FONT.sm },
  input: {
    backgroundColor: COLORS.inputBg,
    borderWidth: 1,
    borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md,
    padding: 14,
    color: COLORS.text,
    fontSize: FONT.md,
  },
  label: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5, textTransform: 'uppercase' as const, marginBottom: 6 },
  sectionTitle: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2, textTransform: 'uppercase' as const, marginBottom: SPACING.md },
  card: {
    backgroundColor: COLORS.card,
    borderWidth: 1,
    borderColor: COLORS.cardBorder,
    borderRadius: RADIUS.lg,
    padding: SPACING.lg,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.05,
    shadowRadius: 3,
    elevation: 2,
  },
});
