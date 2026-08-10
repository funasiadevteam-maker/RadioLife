// Merchant Subscription — Starter $29 / Pro $99 (Marketplace Phase B).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useReward } from '../../src/components/RewardOverlay';

const money = (c: number) => `$${(c / 100).toFixed(0)}`;

export default function Subscribe() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [plans, setPlans] = useState<any[]>([]);
  const [current, setCurrent] = useState<any>(null);
  const [active, setActive] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [p, m] = await Promise.all([
        api.get('/merchant/marketplace/subscription/plans'),
        api.get('/merchant/marketplace/subscription'),
      ]);
      setPlans(p.data.items || []);
      setCurrent(m.data.subscription);
      setActive(!!m.data.active);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const subscribe = async (planId: string) => {
    setBusyId(planId);
    try {
      const r = await api.post('/merchant/marketplace/subscription/checkout', {
        plan_id: planId, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/merchant/marketplace/subscription/status/${r.data.session_id}`);
        if (st.data.active) { celebrate({ points: 0, title: 'You\'re live on RadioLife! 🎉' }); load(); return; }
      }
    } catch { celebrate({ points: 0, title: 'Subscription failed' }); }
    finally { setBusyId(null); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="subscribe-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Merchant Plans</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="subscribe-root">
        {active && (
          <View style={s.activeCard} testID="subscribe-active">
            <Ionicons name="checkmark-circle" size={20} color={COLORS.green} />
            <Text style={s.activeText}>Your {current?.plan_id || ''} plan is active — you&apos;re live on the Shop.</Text>
          </View>
        )}
        <Text style={s.intro}>List your business, reward customers with BigPoints, and accept pickup orders. Cancel anytime.</Text>

        {plans.map((p) => {
          const isCurrent = active && current?.plan_id === p.plan_id;
          return (
            <View key={p.plan_id} style={[s.card, p.plan_id === 'pro' && s.cardPro]} testID={`plan-${p.plan_id}`}>
              <View style={s.planHead}>
                <Text style={s.planName}>{p.name}</Text>
                {p.plan_id === 'pro' && <View style={s.badge}><Text style={s.badgeText}>POPULAR</Text></View>}
              </View>
              <Text style={s.price}>{money(p.price_cents)}<Text style={s.per}>/{p.interval}</Text></Text>
              <View style={{ marginTop: 10 }}>
                {(p.features || []).map((f: string, i: number) => (
                  <View key={i} style={s.featRow}>
                    <Ionicons name="checkmark" size={15} color={COLORS.green} />
                    <Text style={s.featText}>{f}</Text>
                  </View>
                ))}
              </View>
              <TouchableOpacity
                style={[common.btnPrimary, { marginTop: 14 }, isCurrent && { opacity: 0.5 }]}
                onPress={() => subscribe(p.plan_id)} disabled={!!busyId || isCurrent}
                testID={`subscribe-${p.plan_id}`}>
                {busyId === p.plan_id ? <ActivityIndicator color="#fff" />
                  : <Text style={common.btnPrimaryText}>{isCurrent ? 'Current Plan' : `Subscribe · ${money(p.price_cents)}/mo`}</Text>}
              </TouchableOpacity>
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  activeCard: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.green + '15', borderWidth: 1, borderColor: COLORS.green + '55', borderRadius: RADIUS.md, padding: 12, marginBottom: SPACING.md },
  activeText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.lg, marginBottom: SPACING.md },
  cardPro: { borderColor: COLORS.primary, borderWidth: 2 },
  planHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  planName: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  badge: { backgroundColor: COLORS.primary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  badgeText: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  price: { color: COLORS.text, fontSize: 34, fontWeight: '900', marginTop: 6 },
  per: { color: COLORS.textMuted, fontSize: FONT.md, fontWeight: '700' },
  featRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  featText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
});
