// My Service Bookings (Marketplace Phase C).
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
const LABELS: Record<string, string> = {
  pending_payment: 'Awaiting Payment', confirmed: 'Confirmed', completed: 'Completed',
  canceled: 'Canceled', no_show: 'No Show',
};
const CMAP: Record<string, string> = {
  pending_payment: COLORS.textMuted, confirmed: COLORS.secondary, completed: COLORS.green,
  canceled: COLORS.red, no_show: COLORS.red,
};

export default function Bookings() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/shop/service-bookings');
      const list = r.data.items || [];
      await Promise.all(list.filter((b: any) => b.payment_status !== 'paid' && b.session_id)
        .map((b: any) => api.get(`/shop/service-bookings/${b.booking_id}/status`).catch(() => null)));
      const r2 = await api.get('/shop/service-bookings');
      setItems(r2.data.items || []);
    } catch { /* ignore */ } finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="bookings-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>My Bookings</Text>
        <View style={{ width: 22 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="bookings-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary} onRefresh={() => { setRefreshing(true); load(); }} />}>
        {!items.length && (
          <View style={{ alignItems: 'center', marginTop: 60 }} testID="bookings-empty">
            <Ionicons name="calendar-outline" size={48} color={COLORS.textMuted} />
            <Text style={{ color: COLORS.textDim, marginTop: 12, fontWeight: '700' }}>No bookings yet.</Text>
          </View>
        )}
        {items.map((b) => (
          <View key={b.booking_id} style={s.card} testID={`booking-${b.booking_id}`}>
            <View style={s.head}>
              <Text style={s.biz} numberOfLines={1}>{b.business_name}</Text>
              <View style={[s.pill, { backgroundColor: (CMAP[b.status] || COLORS.textMuted) + '22' }]}>
                <Text style={[s.pillText, { color: CMAP[b.status] || COLORS.textDim }]} testID={`booking-status-${b.booking_id}`}>{LABELS[b.status] || b.status}</Text>
              </View>
            </View>
            <Text style={s.svc}>{b.service_name}</Text>
            <Text style={s.meta}>{b.date} · {b.start_time} · {b.duration_min} min</Text>
            <View style={s.footRow}>
              <Text style={s.price}>{money(b.price_cents)}{b.reservation_fee_cents > 0 ? ` · ${money(b.reservation_fee_cents)} paid` : ''}</Text>
              <View style={s.ptsBox}>
                <Text style={s.ptsGlyph}>₿</Text>
                <Text style={s.ptsText}>{b.points_awarded_done ? `+${b.points_to_award}` : `${b.points_to_award} on visit`}</Text>
              </View>
            </View>
          </View>
        ))}
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
  pill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  pillText: { fontSize: FONT.xs, fontWeight: '900' },
  svc: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 6 },
  meta: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', marginTop: 2 },
  footRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 10 },
  price: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  ptsBox: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '18', paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full },
  ptsGlyph: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  ptsText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '800' },
});
