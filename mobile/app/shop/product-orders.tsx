// My product orders — fulfillment tracker (Marketplace Phase D).
import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, RefreshControl } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const STEPS = ['paid', 'packed', 'shipped', 'delivered'];
const LABELS: Record<string, string> = { pending_payment: 'Awaiting Payment', paid: 'Paid', packed: 'Packed', shipped: 'Shipped', delivered: 'Delivered', canceled: 'Canceled' };

export default function ProductOrders() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/shop/product-orders');
      const list = r.data.items || [];
      await Promise.all(list.filter((o: any) => o.payment_status !== 'paid' && o.session_id)
        .map((o: any) => api.get(`/shop/product-orders/${o.order_id}/status`).catch(() => null)));
      const r2 = await api.get('/shop/product-orders');
      setItems(r2.data.items || []);
    } catch { /* ignore */ } finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="porders-back" style={{ padding: 2 }}><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle}>My Deliveries</Text>
        <View style={{ width: 22 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="porders-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary} onRefresh={() => { setRefreshing(true); load(); }} />}>
        {!items.length && (
          <View style={{ alignItems: 'center', marginTop: 60 }} testID="porders-empty">
            <Ionicons name="cube-outline" size={48} color={COLORS.textMuted} /><Text style={{ color: COLORS.textDim, marginTop: 12, fontWeight: '700' }}>No orders yet.</Text>
          </View>
        )}
        {items.map((o) => {
          const idx = STEPS.indexOf(o.status);
          return (
            <View key={o.order_id} style={s.card} testID={`porder-${o.order_id}`}>
              <View style={s.head}>
                <Text style={s.biz} numberOfLines={1}>{o.business_name}</Text>
                <View style={s.pill}><Text style={s.pillText} testID={`porder-status-${o.order_id}`}>{LABELS[o.status] || o.status}</Text></View>
              </View>
              <Text style={s.meta}>{(o.items || []).reduce((n: number, i: any) => n + i.qty, 0)} items · {money(o.total_cents)} · {o.fulfillment}{o.delivery_fee_cents > 0 ? ` (+${money(o.delivery_fee_cents)})` : ''}</Text>
              {o.status !== 'canceled' && idx >= 0 && (
                <View style={s.tracker}>
                  {STEPS.map((st, i) => (
                    <React.Fragment key={st}>
                      <View style={[s.dot, i <= idx && s.dotOn]}>{i <= idx && <Ionicons name="checkmark" size={11} color="#fff" />}</View>
                      {i < STEPS.length - 1 && <View style={[s.line, i < idx && s.lineOn]} />}
                    </React.Fragment>
                  ))}
                </View>
              )}
              {o.fulfillment === 'delivery' && !!o.address && <Text style={s.addr}>📍 {o.address}</Text>}
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
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  biz: { flex: 1, color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  pill: { backgroundColor: COLORS.secondary + '22', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  pillText: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '900' },
  meta: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', marginTop: 6 },
  tracker: { flexDirection: 'row', alignItems: 'center', marginTop: 14 },
  dot: { width: 22, height: 22, borderRadius: 11, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  dotOn: { backgroundColor: COLORS.green, borderColor: COLORS.green },
  line: { flex: 1, height: 2, backgroundColor: COLORS.cardBorder },
  lineOn: { backgroundColor: COLORS.green },
  addr: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 10 },
});
