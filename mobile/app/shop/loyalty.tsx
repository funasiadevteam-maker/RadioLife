// Loyalty tier — progress + perks (Marketplace).
import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

export default function Loyalty() {
  const router = useRouter();
  const [d, setD] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.get('/shop/loyalty').then((r) => setD(r.data)).catch(() => setD(null)).finally(() => setLoading(false)); }, []);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!d) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Unavailable.</Text></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="loyalty-back" style={{ padding: 2 }}><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle}>My Loyalty</Text>
        <View style={{ width: 22 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="loyalty-root">
        <View style={[s.hero, { borderColor: d.color }]}>
          <View style={[s.badge, { backgroundColor: d.color }]}><Ionicons name="star" size={20} color="#fff" /></View>
          <Text style={s.tierName} testID="loyalty-tier">{d.tier_name}</Text>
          <Text style={s.bonus}>{d.bonus_pct > 0 ? `+${d.bonus_pct}% bonus BigPoints` : 'Start earning to level up'}</Text>
          <Text style={s.lifetime}>{d.lifetime_points.toLocaleString()} lifetime BigPoints</Text>
          {d.next_tier && (
            <>
              <View style={s.barBg}><View style={[s.barFill, { width: `${Math.round(d.progress * 100)}%`, backgroundColor: d.color }]} /></View>
              <Text style={s.toNext}>{d.points_to_next.toLocaleString()} more to {d.next_tier}</Text>
            </>
          )}
        </View>

        <Text style={s.section}>Your perks</Text>
        {(d.perks || []).map((p: string, i: number) => (
          <View key={i} style={s.perk}><Ionicons name="checkmark-circle" size={16} color={COLORS.green} /><Text style={s.perkText}>{p}</Text></View>
        ))}

        <Text style={s.section}>All tiers</Text>
        {(d.all_tiers || []).map((t: any) => (
          <View key={t.key} style={[s.tierRow, t.key === d.tier && { borderColor: d.color, borderWidth: 2 }]} testID={`loyalty-tier-${t.key}`}>
            <View style={[s.dot, { backgroundColor: t.color }]} />
            <Text style={s.trName}>{t.name}</Text>
            <Text style={s.trMeta}>{t.min_points.toLocaleString()}+ · +{t.bonus_pct}%</Text>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  hero: { alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 2, borderRadius: RADIUS.lg, padding: SPACING.lg },
  badge: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  tierName: { color: COLORS.text, fontSize: 26, fontWeight: '900', marginTop: 10 },
  bonus: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800', marginTop: 2 },
  lifetime: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 6 },
  barBg: { width: '100%', height: 8, borderRadius: 4, backgroundColor: COLORS.inputBg, marginTop: 14, overflow: 'hidden' },
  barFill: { height: 8, borderRadius: 4 },
  toNext: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 6, fontWeight: '700' },
  section: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: SPACING.lg, marginBottom: 10 },
  perk: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  perkText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  tierRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  dot: { width: 14, height: 14, borderRadius: 7 },
  trName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', flex: 1 },
  trMeta: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
});
