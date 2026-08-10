// Buy More BigCoin — top up balance with a card (Stripe Checkout).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

interface Pkg {
  package_id: string; bigcoin: number; bonus: number; price_cents: number; total_bigcoin: number;
}
const money = (c: number) => `$${(c / 100).toFixed(0)}`;

export default function BigCoinTopUp() {
  const router = useRouter();
  const params = useLocalSearchParams<{ needed?: string }>();
  const { celebrate } = useReward();
  const [items, setItems] = useState<Pkg[]>([]);
  const [balance, setBalance] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/bigcoin/topup/packages');
      setItems(r.data.items || []);
      setBalance(r.data.points_balance || 0);
    } catch { /* unauth */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const buy = async (p: Pkg) => {
    setBusyId(p.package_id);
    try {
      const r = await api.post('/bigcoin/topup/checkout', {
        package_id: p.package_id,
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
      });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        // Back from checkout — settle the credit.
        const st = await api.get(`/bigcoin/topup/${r.data.session_id}/status`);
        if (st.data.status === 'paid') {
          setBalance(st.data.balance_after ?? balance);
          celebrate({ points: st.data.credited || p.total_bigcoin, title: 'BigCoin added!' });
        }
      }
    } catch { celebrate({ points: 0, title: 'Top up failed' }); }
    finally { setBusyId(null); await load(); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  const needed = params.needed ? Number(params.needed) : 0;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="topup-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Buy BigCoin</Text>
        <View style={s.balPill}>
          <Text style={s.balGlyph}>₿</Text>
          <Text style={s.balText} testID="topup-balance">{balance}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="topup-root">
        {needed > 0 && (
          <View style={s.needCard} testID="topup-need-banner">
            <Ionicons name="alert-circle" size={18} color={COLORS.primary} />
            <Text style={s.needText}>You need {needed} more BigCoin to redeem that gift card.</Text>
          </View>
        )}
        <Text style={s.intro}>Top up instantly with your card. 100 BigCoin = $1.</Text>

        {items.map((p) => (
          <TouchableOpacity key={p.package_id} style={s.card} onPress={() => buy(p)}
            disabled={!!busyId} testID={`topup-pkg-${p.package_id}`} activeOpacity={0.85}>
            <View style={s.coinIcon}><Text style={s.coinGlyph}>₿</Text></View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.amount}>{p.total_bigcoin} BigCoin</Text>
              {p.bonus > 0 && <Text style={s.bonus}>+{p.bonus} bonus included</Text>}
            </View>
            <View style={s.priceBtn}>
              {busyId === p.package_id
                ? <ActivityIndicator color="#fff" />
                : <Text style={s.priceText}>{money(p.price_cents)}</Text>}
            </View>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  balPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '22', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  balGlyph: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  balText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  needCard: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.primary + '12', borderWidth: 1, borderColor: COLORS.primary + '55', marginBottom: SPACING.md },
  needText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', flex: 1 },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  coinIcon: { width: 46, height: 46, borderRadius: 23, backgroundColor: COLORS.gold + '22', alignItems: 'center', justifyContent: 'center' },
  coinGlyph: { color: COLORS.gold, fontSize: 22, fontWeight: '900' },
  amount: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  bonus: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  priceBtn: { backgroundColor: COLORS.primary, paddingHorizontal: 18, paddingVertical: 10, borderRadius: RADIUS.full, minWidth: 64, alignItems: 'center' },
  priceText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
});
