// Listing Insights — 7-day trend for a Featured Listing (mobile).
import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, TouchableOpacity } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';

interface Point { day: string; impressions: number; clicks: number; spend_usd: number }

export default function ListingInsights() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try { const r = await api.get(`/merchant/featured/${id}/insights?days=7`); setData(r.data); }
      catch { /* not owner */ }
      finally { setLoading(false); }
    })();
  }, [id]);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  const series: Point[] = data?.series || [];
  const maxImp = Math.max(1, ...series.map((p) => p.impressions));
  const totals = data?.totals || {};
  const ctr = totals.impressions > 0 ? ((totals.clicks / totals.impressions) * 100).toFixed(1) : '0.0';

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="insights-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle} numberOfLines={1}>{data?.title || 'Insights'}</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="insights-root">
        {/* Totals */}
        <View style={s.totalsRow}>
          <View style={s.totalCard}><Text style={s.totalValue}>{totals.impressions ?? 0}</Text><Text style={s.totalLabel}>Views</Text></View>
          <View style={s.totalCard}><Text style={s.totalValue}>{totals.clicks ?? 0}</Text><Text style={s.totalLabel}>Taps</Text></View>
          <View style={s.totalCard}><Text style={s.totalValue}>{ctr}%</Text><Text style={s.totalLabel}>Tap rate</Text></View>
          <View style={s.totalCard}><Text style={s.totalValue}>${(totals.spend_usd ?? 0).toFixed(2)}</Text><Text style={s.totalLabel}>Spend</Text></View>
        </View>

        {/* Bar chart */}
        <Text style={s.section}>LAST 7 DAYS · VIEWS</Text>
        <View style={s.chart} testID="insights-chart">
          {series.map((p) => {
            const h = Math.round((p.impressions / maxImp) * 120);
            return (
              <View key={p.day} style={s.barCol} testID={`insights-bar-${p.day}`}>
                <Text style={s.barVal}>{p.impressions || ''}</Text>
                <View style={[s.bar, { height: Math.max(3, h) }]} />
                <Text style={s.barDay}>{p.day.slice(5)}</Text>
              </View>
            );
          })}
        </View>

        <View style={s.legend}>
          <Text style={s.legendText}>Budget ${(totals.budget_usd ?? 0)} · ${(totals.spend_usd ?? 0).toFixed(2)} spent</Text>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', flex: 1, textAlign: 'center', marginHorizontal: 8 },
  totalsRow: { flexDirection: 'row', gap: 8, marginBottom: SPACING.lg },
  totalCard: { flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  totalValue: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  totalLabel: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 0.5, textTransform: 'uppercase', marginTop: 2 },
  section: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.5, marginBottom: SPACING.md },
  chart: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', height: 170, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md },
  barCol: { flex: 1, alignItems: 'center', justifyContent: 'flex-end' },
  bar: { width: 18, borderRadius: 5, backgroundColor: COLORS.primary },
  barVal: { color: COLORS.textDim, fontSize: 9, fontWeight: '700', marginBottom: 4 },
  barDay: { color: COLORS.textMuted, fontSize: 9, fontWeight: '700', marginTop: 6 },
  legend: { marginTop: SPACING.md, alignItems: 'center' },
  legendText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
});
