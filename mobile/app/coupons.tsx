import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, RefreshControl, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import api from '../src/api/client';
import { useAuth } from '../src/contexts/AuthContext';

const OFFER_CATS = ['all', 'food', 'drinks', 'entertainment', 'wellness', 'shopping'];

export default function CouponsScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [offers, setOffers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [cat, setCat] = useState('all');
  const [claiming, setClaiming] = useState<string | null>(null);
  const [bizMap, setBizMap] = useState<Record<string, any>>({});

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const loadFeed = async () => {
    try {
      const r = await api.get('/commerce/offers/feed');
      const items = r.data.items || [];
      setOffers(items);
      // Enrich with business name / category / rating (real data only)
      const ids = [...new Set(items.map((o: any) => o.business_id).filter(Boolean))];
      const results = await Promise.allSettled(ids.map((id) => api.get(`/business/${id}/profile`)));
      const map: Record<string, any> = {};
      results.forEach((res, i) => {
        if (res.status === 'fulfilled') {
          const m = res.value.data?.merchant || {};
          map[ids[i] as string] = { name: m.name, category: m.category, rating: m.average_rating, logo: m.logo_url };
        }
      });
      setBizMap(map);
    } catch { /* */ }
    finally { setLoading(false); }
  };

  useEffect(() => { if (!authLoading && user) loadFeed(); }, [authLoading, user]);
  const onRefresh = async () => { setRefreshing(true); await loadFeed(); setRefreshing(false); };

  const claimOffer = async (offerId: string) => {
    setClaiming(offerId);
    try {
      await api.post(`/commerce/offers/${offerId}/claim`, {});
      Alert.alert('Claimed!', 'Coupon saved to your wallet.');
      loadFeed();
    } catch (e: any) {
      const msg = e?.response?.data?.detail;
      Alert.alert('Error', typeof msg === 'string' ? msg : 'Could not claim offer');
    } finally { setClaiming(null); }
  };

  const filtered = cat === 'all' ? offers : offers.filter(o =>
    (o.category || '').toLowerCase() === cat || (o.offer_type || '').includes(cat));

  if (authLoading || loading) return <View style={st.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={st.screen} testID="coupons-screen">
      <ScrollView contentContainerStyle={st.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}>

        <View style={st.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={st.backBtn} testID="coupons-back-btn">
            <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
            <Text style={st.backText}>back</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => router.push('/(tabs)/wallet')} style={st.myCouponsBtn} testID="my-coupons-link">
            <Ionicons name="pricetag" size={12} color={COLORS.primary} />
            <Text style={st.myCouponsText}>My Coupons</Text>
          </TouchableOpacity>
        </View>
        <Text style={st.title}>Nearby Deals</Text>
        <Text style={st.sub}>Deals from businesses near you. Claim → redeem in-store.</Text>

        {/* Filter chips */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: SPACING.md }}>
          <View style={st.chipRow} testID="offer-category-filters">
            {OFFER_CATS.map(c => (
              <TouchableOpacity key={c} style={[st.filterChip, cat === c && st.filterActive]}
                onPress={() => setCat(c)} testID={`offer-cat-${c}`}>
                <Text style={[st.filterText, cat === c && { color: '#fff' }]}>{c === 'all' ? 'All' : c.charAt(0).toUpperCase() + c.slice(1)}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        {/* Offers grid */}
        {filtered.length === 0 ? (
          <View style={st.emptyWrap} testID="offers-empty">
            <Ionicons name="storefront" size={36} color={COLORS.textDim} />
            <Text style={st.emptyText}>No offers available right now.</Text>
          </View>
        ) : filtered.map(o => (
          <TouchableOpacity key={o.offer_id} style={st.offerCard} testID={`offer-card-${o.offer_id}`}
            onPress={() => router.push(`/offer/${o.offer_id}`)} activeOpacity={0.8}>
            <View style={st.offerRow}>
              <View style={st.discountTile}>
                <Text style={st.discountValue}>
                  {o.value_amount != null ? (o.offer_type === 'percent_off' ? `${o.value_amount}%` : `${o.value_amount}`) : 'DEAL'}
                </Text>
                <Text style={st.discountLabel}>{o.value_amount != null ? (o.offer_type === 'percent_off' ? 'OFF' : (o.value_currency || 'AED')) : ''}</Text>
              </View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={st.offerHeader}>
                  <View style={st.offerType}>
                    <Ionicons name="pricetag" size={10} color={COLORS.gold} />
                    <Text style={st.offerTypeText}>{(o.offer_type || '').replace(/_/g, ' ')}</Text>
                  </View>
                  {o.source && <Text style={st.sourceBadge}>{o.source}</Text>}
                </View>
                {bizMap[o.business_id]?.name ? (
                  <View style={st.bizRow}>
                    <Ionicons name="storefront" size={12} color={COLORS.primary} />
                    <Text style={st.bizName} numberOfLines={1}>{bizMap[o.business_id].name}</Text>
                    {bizMap[o.business_id].category ? <Text style={st.bizCat}>{bizMap[o.business_id].category}</Text> : null}
                    {bizMap[o.business_id].rating ? (
                      <View style={st.ratingPill}><Ionicons name="star" size={9} color={COLORS.gold} /><Text style={st.ratingText}>{Number(bizMap[o.business_id].rating).toFixed(1)}</Text></View>
                    ) : null}
                  </View>
                ) : null}
                <Text style={st.offerTitle} numberOfLines={2}>{o.title}</Text>
                {o.description ? <Text style={st.offerDesc} numberOfLines={2}>{o.description}</Text> : null}
                <View style={st.offerMeta}>
                  {o.end_at && <Text style={st.offerExpiry}><Ionicons name="time" size={10} color={COLORS.textDim} /> exp {new Date(o.end_at).toLocaleDateString()}</Text>}
                  {o.inventory_remaining != null && <Text style={[st.offerExpiry, o.inventory_remaining === 0 && { color: COLORS.red }]}>{o.inventory_remaining === 0 ? 'Sold out' : `${o.inventory_remaining} left`}</Text>}
                </View>
              </View>
            </View>
            {o.terms_text ? <Text style={st.terms} numberOfLines={2}>{o.terms_text}</Text> : null}
            <TouchableOpacity style={[st.claimBtn, (o.inventory_remaining === 0 || claiming === o.offer_id) && { opacity: 0.4 }]}
              onPress={() => claimOffer(o.offer_id)}
              disabled={o.inventory_remaining === 0 || claiming === o.offer_id}
              testID={`claim-offer-${o.offer_id}`}>
              {claiming === o.offer_id ? <ActivityIndicator size={12} color="#fff" /> :
                <><Ionicons name="gift" size={13} color="#fff" /><Text style={st.claimText}>Save coupon</Text></>}
            </TouchableOpacity>
          </TouchableOpacity>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  headerRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.xs },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  myCouponsBtn: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  myCouponsText: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700' },
  title: { color: COLORS.text, fontSize: 24, fontWeight: '900', marginBottom: 4 },
  sub: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  chipRow: { flexDirection: 'row', gap: 6 },
  filterChip: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  filterActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  filterText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  emptyWrap: { alignItems: 'center', padding: SPACING.xl },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: SPACING.sm },
  offerCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.cardBorder, shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 6, elevation: 2 },
  offerRow: { flexDirection: 'row', gap: SPACING.md },
  discountTile: { width: 68, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center', paddingVertical: SPACING.sm, alignSelf: 'flex-start' },
  discountValue: { color: '#fff', fontSize: 20, fontWeight: '900' },
  discountLabel: { color: 'rgba(255,255,255,0.9)', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  offerHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  bizRow: { flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 3 },
  bizName: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '800', maxWidth: '55%' },
  bizCat: { color: COLORS.textMuted, fontSize: 10, fontWeight: '600', textTransform: 'capitalize' },
  ratingPill: { flexDirection: 'row', alignItems: 'center', gap: 2, backgroundColor: '#fef3c7', borderRadius: RADIUS.sm, paddingHorizontal: 5, paddingVertical: 1 },
  ratingText: { color: COLORS.gold, fontSize: 10, fontWeight: '800' },
  offerType: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  offerTypeText: { color: COLORS.gold, fontSize: 10, fontWeight: '700', letterSpacing: 0.5 },
  sourceBadge: { backgroundColor: 'rgba(242,107,42,0.15)', paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full },
  offerTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800', marginBottom: 4 },
  offerDesc: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: 6 },
  offerMeta: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 6 },
  offerValue: { color: COLORS.green, fontSize: FONT.sm, fontWeight: '800' },
  offerExpiry: { color: COLORS.textDim, fontSize: FONT.xs },
  terms: { color: COLORS.textMuted, fontSize: FONT.xs, fontStyle: 'italic', marginBottom: 8 },
  offerActions: { flexDirection: 'row', gap: 8, marginTop: 4 },
  claimBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: RADIUS.md, backgroundColor: COLORS.primary },
  claimText: { color: '#fff', fontSize: FONT.sm, fontWeight: '700' },
});
