// FUUSIC Travel — mobile My Trips (booked travel orders).
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';

type Order = {
  order_id: string; title: string; deal_type: string; destination: string;
  image_url?: string; travelers: number; total_cents: number;
  status: string; confirmation: string; created_at: string;
};

const money = (c: number) => `$${Math.round((c || 0) / 100)}`;
const TYPE_ICON: Record<string, any> = {
  flight: 'airplane', hotel: 'bed', package: 'briefcase',
  experience: 'compass', cruise: 'boat',
};

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return ''; }
}

export default function TravelTripsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<Order[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const r = await api.get('/travel/orders');
      setItems(r.data?.items || []);
    } catch { setItems([]); }
    finally { setLoading(false); setRefreshing(false); }
  };
  useEffect(() => { load(); }, []);

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="trips-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>My Trips</Text>
        <View style={{ width: 22 }} />
      </View>

      {loading ? (
        <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : items.length === 0 ? (
        <View style={[common.center, { paddingHorizontal: 30 }]} testID="trips-empty">
          <Text style={{ fontSize: 44 }}>🧳</Text>
          <Text style={s.emptyTitle}>No trips yet</Text>
          <Text style={s.emptySub}>Book a deal and it'll show up here with your confirmation.</Text>
          <TouchableOpacity onPress={() => router.push('/shop/travel' as any)} style={s.browse} testID="trips-browse">
            <Text style={s.browseTxt}>Browse deals</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 90, gap: 12 }}
          testID="trips-list"
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
            onRefresh={() => { setRefreshing(true); load(); }} />}>
          {items.map((o) => (
            <View key={o.order_id} style={s.card} testID={`trip-${o.order_id}`}>
              <View style={s.thumb}>
                {o.image_url ? <Image source={{ uri: o.image_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" transition={150} /> : null}
              </View>
              <View style={{ flex: 1, padding: 10 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name={TYPE_ICON[o.deal_type] || 'airplane'} size={13} color={COLORS.primary} />
                  <Text style={s.title} numberOfLines={1}>{o.title}</Text>
                </View>
                <Text style={s.dest} numberOfLines={1}>{o.destination}</Text>
                <View style={s.metaRow}>
                  <View style={s.statusBadge}><Text style={s.statusTxt}>{(o.status || 'confirmed')}</Text></View>
                  <Ionicons name="ticket-outline" size={12} color={COLORS.textDim} />
                  <Text style={s.conf}>{o.confirmation}</Text>
                  <Ionicons name="people-outline" size={12} color={COLORS.textMuted} />
                  <Text style={s.small}>{o.travelers}</Text>
                </View>
                <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 }}>
                  <Text style={s.price}>{money(o.total_cents)}</Text>
                  <Text style={s.small}>{fmtDate(o.created_at)}</Text>
                </View>
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  card: { flexDirection: 'row', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, overflow: 'hidden' },
  thumb: { width: 104, backgroundColor: COLORS.inputBg },
  title: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', flex: 1 },
  dest: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 6, flexWrap: 'wrap' },
  statusBadge: { backgroundColor: COLORS.green, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2 },
  statusTxt: { color: '#fff', fontSize: 9, fontWeight: '900', textTransform: 'capitalize' },
  conf: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  small: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  price: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  emptyTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: 8 },
  emptySub: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '600', textAlign: 'center', marginTop: 4 },
  browse: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 20, paddingVertical: 11, marginTop: 16 },
  browseTxt: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
});
