// Shop Home — RadioLife Super Marketplace consumer entry.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

interface Biz {
  business_id: string; public_name: string; category: string; subcategory?: string;
  cover_url?: string; default_bigpoints: number; rating?: number;
  featured?: boolean; sponsored?: boolean;
}
interface Section { key: string; title: string; items: Biz[]; }
interface Cat { key: string; name: string; icon?: string; }

export default function ShopHome() {
  const router = useRouter();
  const [headline, setHeadline] = useState('SHOP LOCAL. EARN BIGPOINTS.');
  const [cats, setCats] = useState<Cat[]>([]);
  const [filters, setFilters] = useState<string[]>([]);
  const [sections, setSections] = useState<Section[]>([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/shop/home');
      setHeadline(r.data.headline);
      setCats(r.data.categories || []);
      setFilters(r.data.filters || []);
      setSections((r.data.sections || []).filter((s: Section) => s.items.length));
    } catch { /* ignore */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const goSearch = () => router.push({ pathname: '/shop/browse', params: { q: query } });

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={{ paddingBottom: 90 }} testID="shop-home-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}>

        <View style={s.hero}>
          <Text style={s.eyebrow}>RADIOLIFE SHOP</Text>
          <Text style={s.headline}>{headline}</Text>
          <View style={s.searchBar}>
            <Ionicons name="search" size={18} color={COLORS.textMuted} />
            <TextInput style={s.searchInput} value={query} onChangeText={setQuery}
              placeholder="What are you looking for?" placeholderTextColor={COLORS.textMuted}
              returnKeyType="search" onSubmitEditing={goSearch} testID="shop-search-input" />
          </View>
        </View>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.catRow} testID="shop-categories">
          {cats.map((c) => (
            <TouchableOpacity key={c.key} style={s.catChip} testID={`shop-cat-${c.key}`}
              onPress={() => router.push({ pathname: '/shop/browse', params: { category: c.key } })}>
              <View style={s.catIcon}>
                <Ionicons name={(c.icon || 'storefront') as any} size={20} color={COLORS.primary} />
              </View>
              <Text style={s.catLabel} numberOfLines={1}>{c.name}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={s.filterRow} testID="shop-filters">
          {filters.map((f) => (
            <TouchableOpacity key={f} style={s.filterChip}
              onPress={() => router.push({ pathname: '/shop/browse', params: { filter: f } })}>
              <Text style={s.filterText}>{f}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        <TouchableOpacity style={s.sellCard} onPress={() => router.push('/sell')} testID="shop-sell-cta">
          <View style={{ flex: 1 }}>
            <Text style={s.sellTitle}>Sell on RadioLife</Text>
            <Text style={s.sellSub}>List your business & reward local customers with BigPoints.</Text>
          </View>
          <Ionicons name="arrow-forward-circle" size={30} color="#fff" />
        </TouchableOpacity>

        <View style={s.quickRow}>
          <TouchableOpacity style={s.quickBtn} onPress={() => router.push('/shop/orders')} testID="shop-my-orders">
            <Ionicons name="receipt-outline" size={18} color={COLORS.primary} />
            <Text style={s.quickText}>Orders</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.quickBtn} onPress={() => router.push('/shop/bookings')} testID="shop-my-bookings">
            <Ionicons name="calendar-outline" size={18} color={COLORS.primary} />
            <Text style={s.quickText}>Bookings</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.quickBtn} onPress={() => router.push('/merchant/dashboard')} testID="shop-merchant-dash">
            <Ionicons name="storefront-outline" size={18} color={COLORS.primary} />
            <Text style={s.quickText}>Merchant</Text>
          </TouchableOpacity>
        </View>

        <View style={s.quickRow}>
          <TouchableOpacity style={s.quickBtn} onPress={() => router.push('/shop/loyalty')} testID="shop-my-loyalty">
            <Ionicons name="ribbon-outline" size={18} color={COLORS.gold} />
            <Text style={s.quickText}>My Loyalty</Text>
          </TouchableOpacity>
          <TouchableOpacity style={s.quickBtn} onPress={() => router.push('/shop/my-memberships')} testID="shop-my-memberships">
            <Ionicons name="ribbon" size={18} color={COLORS.primary} />
            <Text style={s.quickText}>Memberships</Text>
          </TouchableOpacity>
        </View>

        {sections.map((sec) => (
          <View key={sec.key} style={{ marginTop: SPACING.lg }} testID={`shop-section-${sec.key}`}>
            <Text style={s.sectionTitle}>{sec.title}</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 12 }}>
              {sec.items.map((b) => (
                <BizCard key={b.business_id + sec.key} b={b}
                  onPress={() => router.push(`/shop/${b.business_id}`)} />
              ))}
            </ScrollView>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

export function BizCard({ b, onPress, wide }: { b: Biz; onPress: () => void; wide?: boolean }) {
  return (
    <TouchableOpacity style={[s.card, wide && { width: '100%' }]} onPress={onPress}
      testID={`shop-biz-${b.business_id}`} activeOpacity={0.85}>
      <View style={s.coverWrap}>
        <Image source={{ uri: b.cover_url }} style={s.cover} contentFit="cover" transition={200} />
        {b.sponsored && <View style={s.sponsoredTag}><Text style={s.sponsoredText}>Sponsored</Text></View>}
        <View style={s.ptsBadge}>
          <Text style={s.ptsGlyph}>₿</Text>
          <Text style={s.ptsText}>Earn {b.default_bigpoints}</Text>
        </View>
      </View>
      <View style={{ padding: 10 }}>
        <Text style={s.bizName} numberOfLines={1}>{b.public_name}</Text>
        <View style={s.metaRow}>
          <Text style={s.bizCat} numberOfLines={1}>{b.subcategory || b.category}</Text>
          {b.rating ? (
            <View style={s.ratingRow}>
              <Ionicons name="star" size={11} color={COLORS.gold} />
              <Text style={s.ratingText}>{b.rating.toFixed(1)}</Text>
            </View>
          ) : null}
        </View>
      </View>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  hero: { paddingHorizontal: SPACING.md, paddingTop: SPACING.lg, paddingBottom: SPACING.sm },
  eyebrow: { color: COLORS.primary, fontSize: 11, fontWeight: '900', letterSpacing: 1.5 },
  headline: { color: COLORS.text, fontSize: 26, fontWeight: '900', marginTop: 4, marginBottom: 14, lineHeight: 30 },
  searchBar: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 14, paddingVertical: 12 },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.sm, padding: 0 },
  catRow: { paddingHorizontal: SPACING.md, gap: 14, paddingVertical: SPACING.sm },
  catChip: { alignItems: 'center', width: 68 },
  catIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: COLORS.primary + '15', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  catLabel: { color: COLORS.textDim, fontSize: 11, fontWeight: '700', textAlign: 'center' },
  filterRow: { paddingHorizontal: SPACING.md, gap: 8, paddingBottom: SPACING.sm },
  filterChip: { flexShrink: 0, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  filterText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  sellCard: { marginHorizontal: SPACING.md, marginTop: SPACING.sm, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, padding: 16 },
  sellTitle: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  sellSub: { color: '#fff', opacity: 0.9, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  quickRow: { flexDirection: 'row', gap: 10, paddingHorizontal: SPACING.md, marginTop: SPACING.sm },
  quickBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.md, paddingVertical: 12 },
  quickText: { color: COLORS.primary, fontWeight: '800', fontSize: FONT.sm },
  sectionTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', paddingHorizontal: SPACING.md, marginBottom: 10 },
  card: { width: 220, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, overflow: 'hidden' },
  coverWrap: { position: 'relative' },
  cover: { width: '100%', height: 120, backgroundColor: COLORS.inputBg },
  sponsoredTag: { position: 'absolute', top: 8, left: 8, backgroundColor: 'rgba(0,0,0,0.6)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  sponsoredText: { color: '#fff', fontSize: 9, fontWeight: '800' },
  ptsBadge: { position: 'absolute', bottom: 8, right: 8, flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.gold, paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full },
  ptsGlyph: { color: '#3a2a00', fontSize: 11, fontWeight: '900' },
  ptsText: { color: '#3a2a00', fontSize: 11, fontWeight: '900' },
  bizName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  metaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 3 },
  bizCat: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', flex: 1 },
  ratingRow: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  ratingText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
});
