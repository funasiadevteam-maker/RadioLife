// RadioLife Shop — buy & redeem prepaid packages (mobile).
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Alert,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useReward } from '../../../src/components/RewardOverlay';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;

export default function ShopPackages() {
  const router = useRouter();
  const { celebrate } = useReward();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { const r = await api.get(`/shop/businesses/${id}/packages`); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]);

  const buy = async (pkg: any, method: string) => {
    setBusy(true);
    try {
      const r = await api.post('/shop/packages/purchase', { package_id: pkg.package_id, method, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/shop/packages/purchase/${r.data.session_id}/status`);
        if (st.data.status !== 'paid') { setBusy(false); return; }
      }
      celebrate({ title: 'Package purchased!', subtitle: `${pkg.credits} credits added` });
      load(); setBusy(false);
    } catch (e: any) { Alert.alert('Purchase failed', e?.response?.data?.detail?.code || 'Try again'); setBusy(false); }
  };
  const redeem = async (purchaseId: string) => {
    try { const r = await api.post(`/shop/packages/${purchaseId}/redeem`); celebrate({ title: 'Redeemed!', subtitle: `${r.data.credits_remaining} left` }); load(); }
    catch (e: any) { Alert.alert('Redeem failed', e?.response?.data?.detail?.code || 'Try again'); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Unavailable.</Text></View>;
  const ppd = data.points_per_dollar || 100;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="pkg-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title} numberOfLines={1}>{data.public_name} Packages</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="pkg-root">
        {data.mine?.length > 0 && (
          <View style={s.mine} testID="pkg-mine">
            <Text style={s.mineTitle}>Your packages</Text>
            {data.mine.map((m: any) => (
              <View key={m.purchase_id} style={s.mineCard} testID={`pkg-mine-${m.purchase_id}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={s.mineName}>{m.name}</Text>
                  <Text style={s.mineMeta}>{m.credits_remaining}/{m.credits_total} left</Text>
                </View>
                <TouchableOpacity style={[s.redeemBtn, m.credits_remaining <= 0 && { opacity: 0.4 }]} disabled={m.credits_remaining <= 0}
                  onPress={() => redeem(m.purchase_id)} testID={`pkg-redeem-${m.purchase_id}`}>
                  <Text style={s.redeemText}>{m.credits_remaining <= 0 ? 'Used up' : 'Redeem one'}</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {!data.items?.length && !data.mine?.length && <Text style={{ color: COLORS.textDim, textAlign: 'center', marginTop: 40 }} testID="pkg-empty">No packages offered here yet.</Text>}

        {(data.items || []).map((p: any) => {
          const pointsCost = Math.round((p.price_cents / 100) * ppd);
          const canPoints = p.allow_points && data.points_balance >= pointsCost;
          return (
            <View key={p.package_id} style={s.card} testID={`pkg-product-${p.package_id}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={s.planName}>{p.name}</Text>
                <Text style={s.planPrice}>{money(p.price_cents)}</Text>
              </View>
              <Text style={s.planDesc}>{p.credits} credits{p.description ? ` · ${p.description}` : ''}</Text>
              <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                {p.allow_card && (
                  <TouchableOpacity style={[s.buyCard, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => buy(p, 'card')} testID={`pkg-buy-card-${p.package_id}`}>
                    <Ionicons name="card" size={15} color="#fff" /><Text style={s.buyCardText}>Buy</Text>
                  </TouchableOpacity>
                )}
                {p.allow_points && (
                  <TouchableOpacity style={[s.buyPts, (busy || !canPoints) && { opacity: 0.4 }]} disabled={busy || !canPoints} onPress={() => buy(p, 'points')} testID={`pkg-buy-points-${p.package_id}`}>
                    <Ionicons name="server" size={15} color={COLORS.text} /><Text style={s.buyPtsText}>{pointsCost} pts</Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 8 },
  title: { color: COLORS.text, fontSize: 20, fontWeight: '900', flex: 1 },
  mine: { borderWidth: 2, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10', borderRadius: RADIUS.lg, padding: 14, marginBottom: 16 },
  mineTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 8 },
  mineCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  mineName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  mineMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800' },
  redeemBtn: { marginTop: 10, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 9, alignItems: 'center' },
  redeemText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 16, marginBottom: 12 },
  planName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  planPrice: { color: COLORS.primary, fontSize: FONT.md, fontWeight: '900' },
  planDesc: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 4 },
  buyCard: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 11 },
  buyCardText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  buyPts: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, paddingVertical: 11 },
  buyPtsText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
});
