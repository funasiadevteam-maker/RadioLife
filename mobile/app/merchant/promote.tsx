// Merchant "Promote my Shop" (Phase F) — buy a tiered promotion via Stripe
// hosted Checkout that boosts the shop higher in Shop search + the Promoted
// rail. Goes live only after admin approval.
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useReward } from '../../src/components/RewardOverlay';

const money = (c: number) => `$${((c || 0) / 100).toFixed(2)}`;
const STATUS_LABEL: Record<string, string> = {
  pending_payment: 'Awaiting payment', pending_review: 'In review',
  active: 'Live', rejected: 'Rejected', expired: 'Expired',
};

export default function Promote() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [tiers, setTiers] = useState<any[]>([]);
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [t, m] = await Promise.all([
        api.get('/merchant/marketplace/promotion/tiers'),
        api.get('/merchant/marketplace/promotion'),
      ]);
      setTiers(t.data.tiers || []);
      setData(m.data);
    } catch { setData({ no_profile: true }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const buy = async (tier: string) => {
    setBusy(tier);
    try {
      const r = await api.post('/merchant/marketplace/promotion/checkout', {
        tier, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/merchant/marketplace/promotion/${r.data.promotion_id}/status`);
        if (st.data.status === 'pending_review') celebrate({ points: 0, title: 'Submitted for review 🚀' });
        load();
      }
    } catch { celebrate({ points: 0, title: 'Could not start checkout' }); }
    finally { setBusy(null); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  if (data?.no_profile) return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="promote-back"><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle}>Promote my Shop</Text><View style={{ width: 22 }} />
      </View>
      <View style={common.center}><Text style={{ color: COLORS.textDim }}>You don&apos;t have a business yet.</Text></View>
    </SafeAreaView>
  );

  const active = data?.active;
  const history = (data?.items || []).filter((p: any) => !active || p.promotion_id !== active.promotion_id);

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="promote-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Promote my Shop</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="promote-root">
        <Text style={s.intro}>Boost <Text style={{ fontWeight: '900' }}>{data?.public_name}</Text> to the top of Shop search and the &quot;Promoted near you&quot; rail. Promotions go live once our team approves them.</Text>

        {active && (
          <View style={s.activeCard} testID="promote-active">
            <Ionicons name="checkmark-circle" size={20} color={COLORS.green} />
            <Text style={s.activeText}>You&apos;re promoted — {active.name}, live until {new Date(active.expires_at).toLocaleDateString()}.</Text>
          </View>
        )}

        {tiers.map((t) => {
          const isActiveTier = active && active.tier === t.tier;
          return (
            <View key={t.tier} style={[s.card, t.tier === 'boost_14' && s.cardHot]} testID={`promote-tier-${t.tier}`}>
              <View style={s.cardHead}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="trending-up" size={16} color={COLORS.primary} />
                  <Text style={s.tierName}>{t.name}</Text>
                  {t.tier === 'boost_14' && <View style={s.popBadge}><Text style={s.popText}>POPULAR</Text></View>}
                </View>
                <Text style={s.price}>{money(t.price_cents)}</Text>
              </View>
              <Text style={s.blurb}>{t.blurb}</Text>
              <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }, isActiveTier && { opacity: 0.5 }]}
                onPress={() => buy(t.tier)} disabled={!!busy || isActiveTier} testID={`promote-buy-${t.tier}`}>
                {busy === t.tier ? <ActivityIndicator color="#fff" />
                  : <Text style={common.btnPrimaryText}>{isActiveTier ? 'Current promotion' : `Promote for ${t.days} days`}</Text>}
              </TouchableOpacity>
            </View>
          );
        })}

        {history.length > 0 && (
          <View style={{ marginTop: 8 }}>
            <Text style={s.histTitle}>History</Text>
            {history.map((p: any) => (
              <View key={p.promotion_id} style={s.histRow} testID={`promote-history-${p.promotion_id}`}>
                <Text style={s.histName}>{p.name} · {p.price_cents ? money(p.price_cents) : 'COMP'}</Text>
                <Text style={[s.histStatus, p.status === 'active' && { color: COLORS.green }, p.status === 'rejected' && { color: COLORS.red }]}>{STATUS_LABEL[p.status] || p.status}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md, lineHeight: 20 },
  activeCard: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.green + '15', borderWidth: 1, borderColor: COLORS.green + '55', borderRadius: RADIUS.md, padding: 12, marginBottom: SPACING.md },
  activeText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  cardHot: { borderColor: COLORS.primary, borderWidth: 2 },
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  tierName: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  popBadge: { backgroundColor: COLORS.primary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  popText: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  price: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  blurb: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 6, lineHeight: 19 },
  histTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 8 },
  histRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  histName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  histStatus: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900' },
});
