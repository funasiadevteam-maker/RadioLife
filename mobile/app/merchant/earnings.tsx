// Merchant Earnings — memberships sold, gross, platform fee, net (mobile
// parity of web MerchantEarningsRadioLife). Reads GET /merchant/marketplace/earnings.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c?: number) => `$${(((c || 0) as number) / 100).toFixed(2)}`;

export default function MerchantEarnings() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/merchant/marketplace/earnings');
        setData(r.data);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, []);

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="earnings-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <View style={s.titleRow}>
          <Ionicons name="trending-up" size={18} color={COLORS.green} />
          <Text style={s.topTitle}>Earnings</Text>
        </View>
        <View style={{ width: 22 }} />
      </View>

      {loading ? (
        <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : !data ? (
        <View style={s.centerPad}><Text style={s.muted}>Couldn&apos;t load earnings.</Text></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="rl-merchant-earnings-page">
          {/* Net payout headline */}
          <LinearGradient colors={['#059669', '#14B8A6']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
            style={s.netCard} testID="earnings-net-card">
            <Text style={s.netLabel}>NET PAYOUT · ALL TIME</Text>
            <Text style={s.netTotal} testID="earnings-net-total">{money(data.net_cents)}</Text>
            <Text style={s.netSub}>{money(data.gross_cents)} collected · {money(data.fee_cents)} platform fee</Text>
          </LinearGradient>

          {/* Stat grid */}
          <View style={s.statGrid}>
            <View style={s.stat} testID="earnings-sold">
              <Text style={s.statNum}>{data.memberships_sold}</Text>
              <Text style={s.statLbl}>Memberships sold</Text>
            </View>
            <View style={s.stat} testID="earnings-month-net">
              <Text style={s.statNum}>{money(data.month?.net_cents)}</Text>
              <Text style={s.statLbl}>Net this month</Text>
            </View>
            <View style={s.stat} testID="earnings-month-fee">
              <Text style={s.statNum}>{money(data.month?.fee_cents)}</Text>
              <Text style={s.statLbl}>Fee this month</Text>
            </View>
          </View>

          {/* Transactions */}
          <Text style={s.section}>RECENT MEMBERSHIP SALES</Text>
          {(data.transactions || []).length === 0 ? (
            <View style={s.emptyCard} testID="earnings-empty">
              <Ionicons name="ribbon" size={22} color={COLORS.gold} />
              <Text style={s.emptyTitle}>No membership sales yet.</Text>
              <Text style={s.emptySub}>Sales appear here once shoppers subscribe to your memberships.</Text>
            </View>
          ) : (
            <View testID="earnings-tx-list">
              {(data.transactions || []).map((t: any) => (
                <View key={t.earning_id} style={s.txRow} testID={`earnings-tx-${t.earning_id}`}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.txName} numberOfLines={1}>{t.plan_name || 'Membership'}</Text>
                    <Text style={s.txMeta}>{money(t.gross_cents)} · {Math.round(t.fee_pct)}% fee ({money(t.fee_cents)})</Text>
                  </View>
                  <Text style={s.txNet}>+{money(t.net_cents)}</Text>
                </View>
              ))}
            </View>
          )}

          <Text style={s.footnote}>
            The platform fee is set by your category and any negotiated rate. Payouts are settled to your account separately.
          </Text>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  centerPad: { padding: SPACING.xl, alignItems: 'center' },
  muted: { color: COLORS.textMuted, fontSize: FONT.sm },
  netCard: { borderRadius: RADIUS.xl, padding: SPACING.lg, marginBottom: SPACING.md },
  netLabel: { color: 'rgba(255,255,255,0.85)', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  netTotal: { color: '#fff', fontSize: 38, fontWeight: '900', marginTop: 2 },
  netSub: { color: 'rgba(255,255,255,0.92)', fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  statGrid: { flexDirection: 'row', gap: 10, marginBottom: SPACING.lg },
  stat: { flex: 1, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 12, alignItems: 'center' },
  statNum: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  statLbl: { color: COLORS.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center', marginTop: 2 },
  section: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1.5, marginBottom: SPACING.sm },
  emptyCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.lg, alignItems: 'center', gap: 4 },
  emptyTitle: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  emptySub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', textAlign: 'center' },
  txRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  txName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  txMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  txNet: { color: '#047857', fontSize: FONT.sm, fontWeight: '900' },
  footnote: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', marginTop: SPACING.md, paddingHorizontal: SPACING.md },
});
