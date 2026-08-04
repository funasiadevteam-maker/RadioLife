import { StyleSheet } from 'react-native';

/* ── BigFM Warm Design Tokens ──
   Friendly, high-readability palette: warm cream bg, white rounded cards,
   warm near-black text, coral-orange brand accent, golden BigCoin, soft shadows.
   Icons use clean outline (line) style across the app. */

export const COLORS = {
  bg: '#FBF5EC',           // warm cream
  primary: '#F26B2A',      // coral orange (brand accent)
  secondary: '#3B82F6',    // blue accent (predict / links)
  gold: '#F59E0B',         // amber-500 — BigCoin
  text: '#1C1917',         // warm near-black (stone-900)
  textDim: '#57534E',      // stone-600
  textMuted: '#A8A29E',    // stone-400
  surface: 'rgba(0,0,0,0.02)',
  surfaceBorder: '#EFE6DA', // warm border
  card: '#FFFFFF',
  cardBorder: '#EFE6DA',   // warm border
  green: '#16A34A',        // green-600
  red: '#E11D48',          // rose-600
  orange: '#F26B2A',       // aligned with primary
  purple: '#7C3AED',       // violet-600
  inputBg: '#F6EFE5',      // warm input
  inputBorder: '#E4D8C8',  // warm input border

  /* extras */
  cardShadow: 'rgba(120,72,32,0.10)',
  tabBarBg: '#FFFFFF',
  tabBarBorder: '#EFE6DA',
  statusBarStyle: 'dark' as const,
};

export const SPACING = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 };
export const RADIUS = { sm: 10, md: 14, lg: 18, xl: 24, full: 999 };
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
