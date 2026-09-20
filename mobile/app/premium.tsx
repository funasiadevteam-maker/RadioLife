// Phase RWD.3 — Premium comparison + value screen (mobile) at /premium.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useAuth } from '../src/contexts/AuthContext';
import { fetchPremiumStatus, PremiumStatus } from '../src/api/premiumApi';

const FREE_FEATURES = ['AI & Live Radio', 'Podcasts & Games', 'Rewards & Wallet', 'Local deals'];

export default function PremiumScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [data, setData] = useState<PremiumStatus | null>(null);

  useEffect(() => {
    if (!authLoading && !user) { router.replace('/login'); return; }
    if (!authLoading && user) fetchPremiumStatus().then(setData).catch(() => {});
  }, [authLoading, user, router]);

  if (!data) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const v = data.value || { month_points_earned: 0, premium_bonus_points_estimate: 0 };
  const cur = data.currency || 'USD';

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="premium-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>FUUSIC Premium</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="premium-root">
        <View style={s.hero}>
          <Ionicons name="sparkles" size={22} color={COLORS.purple} />
          <Text style={s.heroText}>Fewer interruptions. More AI. Bigger rewards.</Text>
        </View>

        {data.is_premium ? (
          <View style={s.card} testID="premium-active">
            <Ionicons name="checkmark-circle" size={28} color={COLORS.green} style={{ alignSelf: 'center' }} />
            <Text style={s.activeTitle}>You&apos;re a Premium member</Text>
            <Text style={s.activeSub}>Enjoy every benefit below.</Text>
          </View>
        ) : (
          <View style={s.card} testID="premium-value">
            <Text style={s.kicker}>YOUR PREMIUM VALUE THIS MONTH</Text>
            <View style={s.valueRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.valueBig} testID="premium-bonus-estimate">
                  +{(v.premium_bonus_points_estimate || 0).toLocaleString()}
                </Text>
                <Text style={s.valueSub}>
                  bonus points{data.points_multiplier > 1 ? ` at ${data.points_multiplier}×` : ''}
                </Text>
              </View>
              <View style={{ flex: 1 }}>
                <Text style={[s.valueBig, { color: COLORS.text }]}>
                  {(v.month_points_earned || 0).toLocaleString()}
                </Text>
                <Text style={s.valueSub}>earned this month</Text>
              </View>
            </View>
          </View>
        )}

        <View style={s.cols}>
          <View style={[s.col, { flex: 1 }]} testID="premium-free-col">
            <Text style={s.colTitle}>Free</Text>
            {FREE_FEATURES.map((f) => (
              <View key={f} style={s.featRow}>
                <Ionicons name="checkmark" size={14} color={COLORS.textMuted} />
                <Text style={s.featTextDim}>{f}</Text>
              </View>
            ))}
          </View>
          <View style={[s.col, { flex: 1, borderColor: COLORS.purple + '66' }]} testID="premium-plus-col">
            <View style={s.colTitleRow}>
              <Ionicons name="sparkles" size={14} color={COLORS.purple} />
              <Text style={s.colTitle}>Premium</Text>
            </View>
            {data.benefits.map((b) => (
              <View key={b.key} style={s.featRow} testID={`premium-benefit-${b.key}`}>
                <Ionicons name="checkmark" size={14} color={COLORS.green} />
                <Text style={s.featText} numberOfLines={2}>{b.title}</Text>
              </View>
            ))}
          </View>
        </View>

        <View style={s.adNote} testID="premium-adfree-note">
          <Ionicons name="shield-checkmark" size={15} color={COLORS.green} />
          <Text style={s.adNoteText}>
            No FUUSIC-inserted audio or display ads. Third-party live stations
            may carry their own broadcast advertising. Opt-in extras like local
            offers, Dining Club and games stay available.
          </Text>
        </View>


        {!data.is_premium && (
          <>
            {data.monthly_price != null && (
              <Text style={s.price}>{cur} {data.monthly_price}/mo · {cur} {data.annual_price}/yr</Text>
            )}
            <TouchableOpacity style={s.cta} testID="premium-start"
              onPress={() => router.push('/(tabs)/profile' as any)}>
              <Text style={s.ctaText}>
                {data.trial_days > 0 ? `Try Premium free for ${data.trial_days} days` : 'Start Premium'}
              </Text>
            </TouchableOpacity>
            {data.trial_days > 0 && (
              <Text style={s.fine}>Then {cur} {data.annual_price}/yr. Cancel anytime.</Text>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg,
  },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  hero: { alignItems: 'center', gap: 6, marginVertical: SPACING.md },
  heroText: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center' },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  kicker: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 2, marginBottom: 10 },
  valueRow: { flexDirection: 'row', gap: SPACING.md },
  valueBig: { color: COLORS.gold, fontSize: FONT.xxl, fontWeight: '900' },
  valueSub: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  activeTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', textAlign: 'center', marginTop: 6 },
  activeSub: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: 2 },
  cols: { flexDirection: 'row', gap: SPACING.sm },
  col: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, gap: 8 },
  colTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  colTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  featRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  featText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '600', flex: 1 },
  featTextDim: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', flex: 1 },
  price: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: SPACING.lg },
  cta: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 14, alignItems: 'center', marginTop: SPACING.sm },
  ctaText: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
  fine: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', marginTop: 6 },
  adNote: {
    flexDirection: 'row', alignItems: 'flex-start', gap: 8,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1,
    borderColor: COLORS.cardBorder, padding: SPACING.md, marginTop: SPACING.md,
  },
  adNoteText: { color: COLORS.textDim, fontSize: FONT.xs, lineHeight: 17, flex: 1 },
});
