// Shop browse — search / category / filter results.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { BizCard } from '../(tabs)/shop';

const SORTS = [['featured', 'Featured'], ['bigpoints', 'Most BigPoints'], ['rating', 'Top Rated']];

export default function ShopBrowse() {
  const router = useRouter();
  const params = useLocalSearchParams<{ category?: string; q?: string; filter?: string }>();
  const [items, setItems] = useState<any[]>([]);
  const [query, setQuery] = useState(params.q || '');
  const [sort, setSort] = useState('featured');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get('/shop/businesses', {
        params: { category: params.category, q: query || undefined, sort },
      });
      setItems(r.data.items || []);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [params.category, query, sort]);
  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="browse-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <View style={s.searchBar}>
          <Ionicons name="search" size={16} color={COLORS.textMuted} />
          <TextInput style={s.searchInput} value={query} onChangeText={setQuery}
            placeholder="Search businesses" placeholderTextColor={COLORS.textMuted}
            returnKeyType="search" onSubmitEditing={load} testID="browse-search" />
        </View>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ flexGrow: 0 }}
        contentContainerStyle={s.sortRow}>
        {SORTS.map(([k, label]) => (
          <TouchableOpacity key={k} style={[s.sortChip, sort === k && s.sortOn]}
            onPress={() => setSort(k)} testID={`browse-sort-${k}`}>
            <Text style={[s.sortText, sort === k && s.sortTextOn]}>{label}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {loading ? <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View> : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, gap: 14 }} testID="browse-root">
          <Text style={s.count}>{items.length} result{items.length === 1 ? '' : 's'}
            {params.category ? ` · ${params.category}` : ''}</Text>
          {items.map((b) => (
            <BizCard key={b.business_id} b={b} wide onPress={() => router.push(`/shop/${b.business_id}`)} />
          ))}
          {items.length === 0 && <Text style={s.empty}>No businesses found.</Text>}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  searchBar: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 9 },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.sm, padding: 0 },
  sortRow: { paddingHorizontal: SPACING.md, gap: 8, paddingVertical: SPACING.sm },
  sortChip: { flexShrink: 0, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  sortOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  sortText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  sortTextOn: { color: '#fff' },
  count: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: 30 },
});
