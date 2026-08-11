import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import { useAuth } from '../src/contexts/AuthContext';
import api from '../src/api/client';

const METRICS = [
  { key: 'ambassador_points_alltime', label: 'Ambassador', icon: 'sparkles' as const },
  { key: 'listening_minutes_7d', label: 'Listening 7d', icon: 'time' as const },
  { key: 'badges_earned_7d', label: 'Badges 7d', icon: 'ribbon' as const },
  { key: 'referrals_engaged_30d', label: 'Referrals', icon: 'person-add' as const },
  { key: 'coupons_redeemed_30d', label: 'Coupons', icon: 'pricetag' as const },
  { key: 'commutes_completed_30d', label: 'Commutes', icon: 'car' as const },
];

const RANK_COLORS = ['#ffd75e', '#cfd6df', '#d29c6c'];

export default function LeaderboardScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [cities, setCities] = useState<any[]>([]);
  const [city, setCity] = useState('Dubai');
  const [metric, setMetric] = useState('ambassador_points_alltime');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [showCityPicker, setShowCityPicker] = useState(false);

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/leaderboards/cities');
        setCities(r.data.items || []);
      } catch {}
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await api.get(`/leaderboards/${encodeURIComponent(city)}?metric=${metric}`);
      setData(r.data);
    } catch {
      Alert.alert('Error', 'Could not load leaderboard');
    } finally { setLoading(false); }
  }, [city, metric]);

  useEffect(() => { if (!authLoading && user) load(); }, [load, authLoading, user]);

  const myMe = data?.your_rank ? { rank: data.your_rank, value: data.your_value || 0 } : null;
  const myInTop = data?.top_n?.some((r: any) => r.rank === data?.your_rank);

  return (
    <SafeAreaView style={st.screen} testID="leaderboard-screen">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        <TouchableOpacity onPress={() => router.back()} style={st.backRow} testID="lb-back-btn">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={st.backText}>back</Text>
        </TouchableOpacity>

        {/* Header */}
        <View style={st.headerRow}>
          <View style={{ flex: 1 }}>
            <Text style={st.pageTitle}><Ionicons name="trophy" size={20} color={COLORS.gold} /> City Leaderboards</Text>
          </View>
          <TouchableOpacity style={st.cityBtn} onPress={() => setShowCityPicker(!showCityPicker)} testID="lb-city-picker">
            <Ionicons name="location" size={12} color={COLORS.secondary} />
            <Text style={st.cityText}>{city}</Text>
            <Ionicons name="chevron-down" size={12} color={COLORS.textDim} />
          </TouchableOpacity>
        </View>

        {showCityPicker && (
          <View style={st.cityMenu}>
            {cities.length === 0 && <Text style={st.cityEmpty}>No cities online yet.</Text>}
            {cities.map(c => (
              <TouchableOpacity key={c.city} style={st.cityOption} testID={`lb-city-opt-${c.city}`}
                onPress={() => { setCity(c.city); setShowCityPicker(false); }}>
                <Text style={st.cityOptionText}>{c.city}</Text>
                <Text style={st.cityPop}>{c.active_user_count} listeners</Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* Metric tabs */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={st.metricScroll}
          contentContainerStyle={{ gap: 6, paddingRight: SPACING.md }} testID="lb-metric-tabs">
          {METRICS.map(m => (
            <TouchableOpacity key={m.key} style={[st.metricTab, metric === m.key && st.metricActive]}
              onPress={() => setMetric(m.key)} testID={`lb-tab-${m.key}`}>
              <Ionicons name={m.icon} size={11} color={metric === m.key ? COLORS.primary : COLORS.textDim} />
              <Text style={[st.metricLabel, metric === m.key && { color: COLORS.primary }]}>{m.label}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Loading */}
        {loading && (
          <View style={st.loadingBox} testID="lb-loading">
            <ActivityIndicator size="large" color={COLORS.primary} />
            <Text style={st.loadingText}>Loading {city}…</Text>
          </View>
        )}

        {/* No data */}
        {!loading && data && !data.available && (
          <View style={st.emptyBox} testID="lb-empty">
            <Ionicons name="trophy" size={32} color={COLORS.textDim} />
            <Text style={st.emptyTitle}>No leaderboard yet</Text>
            <Text style={st.emptySub}>{city} needs more active listeners for a board to populate.</Text>
          </View>
        )}

        {/* Your rank pin */}
        {!loading && myMe && !myInTop && data?.your_rank > 50 && (
          <View style={st.yourRankPin} testID="lb-your-rank-pin">
            <Text style={st.yourRankText}>You&apos;re ranked <Text style={{ fontWeight: '800', color: COLORS.gold }}>#{data.your_rank}</Text> ({data.your_value}) — keep going!</Text>
          </View>
        )}

        {/* Rows */}
        {!loading && data?.available && (data.top_n || []).slice(0, 50).map((row: any) => {
          const isMe = data.your_rank === row.rank;
          const rankColor = row.rank <= 3 ? RANK_COLORS[row.rank - 1] : COLORS.textDim;
          const initial = (row.display_name || '?').charAt(0).toUpperCase();
          const isAnon = !!row.is_anonymous;
          return (
            <View key={`${row.rank}-${row.user_id || row.display_name}`}
              style={[st.row, isMe && { borderColor: COLORS.gold, borderWidth: 1 }]} testID={`lb-row-${row.rank}`}>
              <Text style={[st.rankNum, { color: rankColor }]}>#{row.rank}</Text>
              <View style={[st.rowAvatar, isAnon && { opacity: 0.4 }]}>
                <Text style={st.rowAvatarText}>{isAnon ? '?' : initial}</Text>
              </View>
              <View style={{ flex: 1, marginLeft: 10 }}>
                <Text style={[st.rowName, isAnon && { fontStyle: 'italic', opacity: 0.5 }]}>{row.display_name}</Text>
                {row.handle && !isAnon && <Text style={st.rowHandle}>@{row.handle}</Text>}
              </View>
              <Text style={st.rowValue}>{(row.value || 0).toLocaleString()}</Text>
            </View>
          );
        })}

        {!loading && data?.available && (data.top_n || []).length === 0 && (
          <Text style={st.emptySub}>No entries yet.</Text>
        )}

        {!loading && data?.available && (
          <Text style={st.metaLine}>
            {data.active_user_count} active listeners · computed {data.computed_at ? new Date(data.computed_at).toLocaleString() : 'never'}
          </Text>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.sm },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  headerRow: { flexDirection: 'row', alignItems: 'center', marginBottom: SPACING.md },
  pageTitle: { color: COLORS.text, fontSize: 20, fontWeight: '900' },
  cityBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  cityText: { color: COLORS.text, fontSize: 12, fontWeight: '700' },
  cityMenu: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.sm, marginBottom: SPACING.md },
  cityEmpty: { color: COLORS.textDim, fontSize: 12, padding: SPACING.sm },
  cityOption: { flexDirection: 'row', justifyContent: 'space-between', padding: SPACING.sm, borderRadius: RADIUS.sm },
  cityOptionText: { color: COLORS.text, fontSize: 13, fontWeight: '600' },
  cityPop: { color: COLORS.textDim, fontSize: 11 },
  metricScroll: { marginBottom: SPACING.md },
  metricTab: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  metricActive: { borderColor: COLORS.primary, backgroundColor: 'rgba(242,107,42,0.08)' },
  metricLabel: { color: COLORS.textDim, fontSize: 11, fontWeight: '600' },
  loadingBox: { alignItems: 'center', paddingVertical: SPACING.xxl },
  loadingText: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: SPACING.sm },
  emptyBox: { alignItems: 'center', paddingVertical: SPACING.xxl },
  emptyTitle: { color: COLORS.text, fontSize: 16, fontWeight: '700', marginTop: SPACING.sm },
  emptySub: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 4, textAlign: 'center' },
  yourRankPin: { backgroundColor: 'rgba(255,215,0,0.06)', borderWidth: 1, borderColor: COLORS.gold, borderRadius: RADIUS.md, padding: SPACING.md, marginBottom: SPACING.md },
  yourRankText: { color: COLORS.textDim, fontSize: 12, textAlign: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.sm, marginBottom: 4, borderWidth: 1, borderColor: COLORS.cardBorder },
  rankNum: { width: 36, fontSize: 13, fontWeight: '800', textAlign: 'center' },
  rowAvatar: { width: 32, height: 32, borderRadius: 16, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  rowAvatarText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  rowName: { color: COLORS.text, fontSize: 13, fontWeight: '600' },
  rowHandle: { color: COLORS.textDim, fontSize: 10 },
  rowValue: { color: COLORS.text, fontSize: 14, fontWeight: '800', marginLeft: 8 },
  metaLine: { color: COLORS.textDim, fontSize: 10, textAlign: 'center', marginTop: SPACING.md },
});
