// My Pickup Orders — status tracker (Marketplace Phase B).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const STEPS = ['accepted', 'preparing', 'ready', 'picked_up'];
const LABELS: Record<string, string> = {
  pending_payment: 'Awaiting Payment', accepted: 'Accepted', preparing: 'Preparing',
  ready: 'Ready for Pickup', picked_up: 'Picked Up', canceled: 'Canceled',
};
const COLORMAP: Record<string, string> = {
  pending_payment: COLORS.textMuted, accepted: COLORS.secondary, preparing: COLORS.gold,
  ready: COLORS.green, picked_up: COLORS.green, canceled: COLORS.red,
};

export default function Orders() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/shop/orders');
      const list = r.data.items || [];
      // Reconcile any pending-payment orders with Stripe.
      await Promise.all(list.filter((o: any) => o.payment_status !== 'paid' && o.session_id)
        .map((o: any) => api.get(`/shop/orders/${o.order_id}/status`).catch(() => null)));
      const r2 = await api.get('/shop/orders');
      setItems(r2.data.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="orders-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>My Orders</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="orders-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}>
        {!items.length && (
          <View style={{ alignItems: 'center', marginTop: 60 }} testID="orders-empty">
            <Ionicons name="receipt-outline" size={48} color={COLORS.textMuted} />
            <Text style={{ color: COLORS.textDim, marginTop: 12, fontWeight: '700' }}>No orders yet.</Text>
          </View>
        )}
        {items.map((o) => {
          const stepIdx = STEPS.indexOf(o.status);
          return (
            <View key={o.order_id} style={s.card} testID={`order-${o.order_id}`}>
              <View style={s.cardHead}>
                <Text style={s.bizName} numberOfLines={1}>{o.business_name}</Text>
                <View style={[s.statusPill, { backgroundColor: (COLORMAP[o.status] || COLORS.textMuted) + '22' }]}>
                  <Text style={[s.statusText, { color: COLORMAP[o.status] || COLORS.textDim }]} testID={`order-status-${o.order_id}`}>
                    {LABELS[o.status] || o.status}
                  </Text>
                </View>
              </View>
              <Text style={s.meta}>{(o.items || []).reduce((n: number, i: any) => n + i.qty, 0)} items · {money(o.total_cents)}
                {o.gift_card_applied_cents > 0 ? ` · gift card −${money(o.gift_card_applied_cents)}` : ''}</Text>

              {o.status !== 'canceled' && stepIdx >= 0 && (
                <View style={s.tracker}>
                  {STEPS.map((st, idx) => (
                    <React.Fragment key={st}>
                      <View style={[s.dot, idx <= stepIdx && s.dotOn]}>
                        {idx <= stepIdx && <Ionicons name="checkmark" size={11} color="#fff" />}
                      </View>
                      {idx < STEPS.length - 1 && <View style={[s.line, idx < stepIdx && s.lineOn]} />}
                    </React.Fragment>
                  ))}
                </View>
              )}

              <View style={s.footRow}>
                <View style={s.codeBox}>
                  <Text style={s.codeLabel}>PICKUP CODE</Text>
                  <Text style={s.code} testID={`order-code-${o.order_id}`}>{o.pickup_code}</Text>
                </View>
                <View style={s.ptsBox}>
                  <Text style={s.ptsGlyph}>₿</Text>
                  <Text style={s.ptsText}>
                    {o.points_awarded_done ? `+${o.points_to_award} earned` : `${o.points_to_award} on pickup`}
                  </Text>
                </View>
              </View>
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
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  bizName: { flex: 1, color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  statusPill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  statusText: { fontSize: FONT.xs, fontWeight: '900' },
  meta: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', marginTop: 6 },
  tracker: { flexDirection: 'row', alignItems: 'center', marginTop: 14 },
  dot: { width: 22, height: 22, borderRadius: 11, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  dotOn: { backgroundColor: COLORS.green, borderColor: COLORS.green },
  line: { flex: 1, height: 2, backgroundColor: COLORS.cardBorder },
  lineOn: { backgroundColor: COLORS.green },
  footRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 14 },
  codeBox: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 8 },
  codeLabel: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  code: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', letterSpacing: 3 },
  ptsBox: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '18', paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full },
  ptsGlyph: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  ptsText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '800' },
});
