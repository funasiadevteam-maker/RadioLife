// FUUSIC Travel — mobile My Trips. Booked BigPoints orders + saved
// flights/hotels/cars (My Trips Sync). GET /travel/orders + /travel/saved.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, Linking,
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
type Saved = {
  saved_id: string; trip_type: string; title: string; subtitle?: string;
  deep_link?: string; price_label?: string;
};
type SavedGroups = { flights: Saved[]; hotels: Saved[]; cars: Saved[] };

const money = (c: number) => `$${Math.round((c || 0) / 100)}`;
const TYPE_ICON: Record<string, any> = {
  flight: 'airplane', hotel: 'bed', package: 'briefcase',
  experience: 'compass', cruise: 'boat', car: 'car-sport',
};

function fmtDate(iso: string) {
  try { return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' }); }
  catch { return ''; }
}

const SAVED_SECTIONS: { key: keyof SavedGroups; label: string; icon: any }[] = [
  { key: 'flights', label: 'Saved flights', icon: 'airplane' },
  { key: 'hotels', label: 'Saved hotels', icon: 'bed' },
  { key: 'cars', label: 'Saved cars', icon: 'car-sport' },
];

export default function TravelTripsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<Order[]>([]);
  const [saved, setSaved] = useState<SavedGroups>({ flights: [], hotels: [], cars: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = async () => {
    try {
      const [o, sv] = await Promise.all([
        api.get('/travel/orders').catch(() => ({ data: { items: [] } })),
        api.get('/travel/saved').catch(() => ({ data: {} })),
      ]);
      setItems(o.data?.items || []);
      setSaved({ flights: sv.data?.flights || [], hotels: sv.data?.hotels || [], cars: sv.data?.cars || [] });
    } finally { setLoading(false); setRefreshing(false); }
  };
  useEffect(() => { load(); }, []);

  const removeSaved = async (s: Saved) => {
    setSaved((prev) => ({
      flights: prev.flights.filter((x) => x.saved_id !== s.saved_id),
      hotels: prev.hotels.filter((x) => x.saved_id !== s.saved_id),
      cars: prev.cars.filter((x) => x.saved_id !== s.saved_id),
    }));
    await api.delete(`/travel/saved/${s.saved_id}`).catch(() => {});
  };

  const savedCount = saved.flights.length + saved.hotels.length + saved.cars.length;
  const empty = items.length === 0 && savedCount === 0;

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
      ) : empty ? (
        <View style={[common.center, { paddingHorizontal: 30 }]} testID="trips-empty">
          <Text style={{ fontSize: 44 }}>🧳</Text>
          <Text style={s.emptyTitle}>No trips yet</Text>
          <Text style={s.emptySub}>Book a deal or save a flight, hotel or car and it'll show up here.</Text>
          <TouchableOpacity onPress={() => router.push('/shop/travel' as any)} style={s.browse} testID="trips-browse">
            <Text style={s.browseTxt}>Browse deals</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 90, gap: 12 }}
          testID="trips-list"
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
            onRefresh={() => { setRefreshing(true); load(); }} />}>
          {items.length > 0 && (
            <>
              <Text style={s.sectionTitle}>Booked</Text>
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
            </>
          )}

          {SAVED_SECTIONS.map(({ key, label, icon }) => (
            saved[key].length > 0 ? (
              <View key={key} style={{ gap: 8 }} testID={`trips-saved-${key}`}>
                <Text style={s.sectionTitle}>{label}</Text>
                {saved[key].map((sv) => (
                  <View key={sv.saved_id} style={s.savedCard} testID={`saved-${sv.saved_id}`}>
                    <TouchableOpacity activeOpacity={0.85} disabled={!sv.deep_link}
                      onPress={() => sv.deep_link && Linking.openURL(sv.deep_link).catch(() => {})}
                      style={s.savedMain}>
                      <View style={s.savedIcon}>
                        <Ionicons name={TYPE_ICON[sv.trip_type] || 'airplane'} size={16} color={COLORS.primary} />
                      </View>
                      <View style={{ flex: 1, minWidth: 0 }}>
                        <Text style={s.title} numberOfLines={1}>{sv.title}</Text>
                        {sv.subtitle ? <Text style={s.dest} numberOfLines={1}>{sv.subtitle}</Text> : null}
                      </View>
                      {sv.price_label ? <Text style={s.price}>{sv.price_label}</Text> : null}
                    </TouchableOpacity>
                    <TouchableOpacity onPress={() => removeSaved(sv)} testID={`saved-remove-${sv.saved_id}`}
                      hitSlop={8} style={{ paddingHorizontal: 10 }}>
                      <Ionicons name="close" size={16} color={COLORS.textMuted} />
                    </TouchableOpacity>
                  </View>
                ))}
              </View>
            ) : null
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  sectionTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', marginTop: 4 },
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
  savedCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, overflow: 'hidden' },
  savedMain: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, minWidth: 0 },
  savedIcon: { width: 34, height: 34, borderRadius: 10, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  emptyTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: 8 },
  emptySub: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '600', textAlign: 'center', marginTop: 4 },
  browse: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 20, paddingVertical: 11, marginTop: 16 },
  browseTxt: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
});
