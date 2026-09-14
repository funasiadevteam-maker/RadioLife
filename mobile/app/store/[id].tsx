import React, { useEffect, useState } from 'react';
import {
  View, Text, StyleSheet, ScrollView, ActivityIndicator, SafeAreaView,
  TouchableOpacity, RefreshControl,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import api from '../../src/api/client';
import CouponScarcityStrip from '../../src/components/CouponScarcityStrip';

const GAME_ICON: Record<string, string> = {
  spin_wheel: '🎡', scratch_card: '🎟️', quiz: '❓', mystery_box: '🎁',
  memory_match: '🧠', word_puzzle: '🔤', pick_a_card: '🃏',
};

export default function StoreScreen() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [waitlisted, setWaitlisted] = useState<Set<string>>(new Set());
  const [joining, setJoining] = useState<string | null>(null);

  const load = async () => {
    try {
      const r = await api.get(`/store/${id}`);
      setData(r.data);
      setError(null);
    } catch (e: any) {
      setError(e?.response?.data?.detail?.code || e?.response?.data?.detail || 'Store not found');
    }
  };
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    api.get('/me/waitlist').then(r => setWaitlisted(new Set(r.data.campaign_ids || []))).catch(() => {});
  }, [id]);
  const joinWaitlist = async (campaignId: string) => {
    setJoining(campaignId);
    try {
      await api.post(`/store/${id}/waitlist`, { campaign_id: campaignId });
      setWaitlisted(s => new Set(s).add(campaignId));
    } catch { /* ignore */ } finally { setJoining(null); }
  };
  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  if (error) {
    return (
      <SafeAreaView style={st.center} testID="store-error">
        <Ionicons name="storefront-outline" size={40} color={COLORS.textMuted} />
        <Text style={st.errText}>Store not found</Text>
        <TouchableOpacity style={st.ghostBtn} onPress={() => router.replace('/(tabs)/games')}>
          <Text style={st.ghostText}>Browse games</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }
  if (!data) {
    return <View style={st.center} testID="store-loading"><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const { brand, games, coupons_left_today, resets_at } = data;
  const accent = brand.primary || COLORS.primary;

  return (
    <SafeAreaView style={st.screen} testID="store-page">
      <ScrollView contentContainerStyle={st.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={accent} />}>

        <TouchableOpacity onPress={() => router.back()} style={st.back} testID="store-back">
          <Ionicons name="chevron-back" size={16} color={COLORS.textDim} />
          <Text style={st.backText}>back</Text>
        </TouchableOpacity>

        {/* Branded header */}
        <View style={[st.hero, { backgroundColor: accent + '18', borderColor: accent + '40' }]}>
          <View style={st.heroRow}>
            <View style={[st.logo, { backgroundColor: accent }]}>
              <Text style={st.logoText}>{String(brand.name || '?').slice(0, 2).toUpperCase()}</Text>
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[st.official, { color: accent }]}>OFFICIAL STORE</Text>
              <Text style={st.brandName} testID="store-name">{brand.name}</Text>
            </View>
          </View>
          <Text style={st.tagline}>{brand.tagline}</Text>
          <View style={{ marginTop: SPACING.md }}>
            <CouponScarcityStrip remaining={coupons_left_today} resetsAt={resets_at}
                                 accent={accent} testID="store-scarcity" />
          </View>
        </View>

        {/* Games */}
        <Text style={st.sectionTitle}>PLAY &amp; WIN COUPONS</Text>
        {games.length === 0 ? (
          <View style={st.emptyWrap} testID="store-empty">
            <Ionicons name="ticket-outline" size={36} color={COLORS.textMuted} />
            <Text style={st.emptyText}>No live games right now.</Text>
          </View>
        ) : (
          <View style={st.grid} testID="store-games">
            {games.map((g: any) => {
              const soldOut = g.is_coupon_game && g.remaining_today !== null && g.remaining_today <= 0;
              return (
                <TouchableOpacity key={g.campaign_id} style={st.gameCard} activeOpacity={0.85}
                  onPress={() => router.push(`/game/${g.campaign_id}`)}
                  testID={`store-game-${g.campaign_id}`}>
                  <Text style={st.gameIcon}>{GAME_ICON[g.game_type] || '🎮'}</Text>
                  <Text style={st.gameTitle}>{g.title}</Text>
                  <Text style={st.gameDesc} numberOfLines={2}>{g.description}</Text>
                  <View style={st.gameFooter}>
                    {g.is_coupon_game ? (
                      <Text style={[st.gameLeft, { color: soldOut ? COLORS.textMuted : accent }]}
                            testID={`store-game-${g.campaign_id}-left`}>
                        {g.remaining_today === null ? 'Unlimited today'
                          : soldOut ? 'Sold out today'
                          : `${g.remaining_today.toLocaleString()} left today`}
                      </Text>
                    ) : <Text style={st.gameLeftMuted}>BigPoints</Text>}
                    {soldOut ? (
                      waitlisted.has(g.campaign_id) ? (
                        <View style={st.waitlistedPill} testID={`store-game-${g.campaign_id}-waitlisted`}>
                          <Ionicons name="checkmark" size={13} color={COLORS.green} />
                          <Text style={st.waitlistedText}>On waitlist</Text>
                        </View>
                      ) : (
                        <TouchableOpacity style={st.remindBtn} onPress={() => joinWaitlist(g.campaign_id)}
                          disabled={joining === g.campaign_id} testID={`store-game-${g.campaign_id}-remindme`}>
                          {joining === g.campaign_id
                            ? <ActivityIndicator size="small" color={COLORS.primary} />
                            : <Ionicons name="notifications-outline" size={13} color={COLORS.primary} />}
                          <Text style={st.remindText}>Remind me</Text>
                        </TouchableOpacity>
                      )
                    ) : (
                      <View style={[st.playBtn, { backgroundColor: accent }]}>
                        <Text style={st.playText}>Play</Text>
                        <Ionicons name="arrow-forward" size={13} color="#0a0a0b" />
                      </View>
                    )}
                  </View>
                </TouchableOpacity>
              );
            })}
          </View>
        )}

        <TouchableOpacity style={st.viewCoupons} onPress={() => router.push('/coupons?tab=mine')} testID="store-view-coupons">
          <Ionicons name="pricetag" size={14} color={COLORS.text} />
          <Text style={st.viewCouponsText}>View my coupons</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg, gap: SPACING.sm },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  back: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.sm },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  errText: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800' },
  ghostBtn: { marginTop: SPACING.md, paddingHorizontal: 20, paddingVertical: 10, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  ghostText: { color: COLORS.textDim, fontWeight: '700', fontSize: FONT.sm },
  hero: { borderRadius: RADIUS.xl, borderWidth: 1, padding: SPACING.lg, marginBottom: SPACING.lg },
  heroRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  logo: { width: 56, height: 56, borderRadius: RADIUS.lg, alignItems: 'center', justifyContent: 'center' },
  logoText: { color: '#0a0a0b', fontWeight: '900', fontSize: FONT.xl },
  official: { fontSize: 10, fontWeight: '900', letterSpacing: 1.5 },
  brandName: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900' },
  tagline: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: SPACING.sm },
  sectionTitle: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 2, marginBottom: SPACING.md },
  grid: { gap: SPACING.sm },
  gameCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.sm },
  gameIcon: { fontSize: 30, marginBottom: 6 },
  gameTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800' },
  gameDesc: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 2 },
  gameFooter: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: SPACING.md },
  gameLeft: { fontSize: FONT.xs, fontWeight: '900' },
  gameLeftMuted: { fontSize: FONT.xs, fontWeight: '700', color: COLORS.textMuted },
  playBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 14, paddingVertical: 7, borderRadius: RADIUS.full },
  playText: { color: '#0a0a0b', fontWeight: '900', fontSize: FONT.sm },
  remindBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, paddingVertical: 7, borderRadius: RADIUS.full, backgroundColor: COLORS.primary + '18', borderWidth: 1, borderColor: COLORS.primary + '55' },
  remindText: { color: COLORS.primary, fontWeight: '800', fontSize: FONT.xs },
  waitlistedPill: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 12, paddingVertical: 7, borderRadius: RADIUS.full, backgroundColor: 'rgba(22,163,74,0.15)' },
  waitlistedText: { color: COLORS.green, fontWeight: '800', fontSize: FONT.xs },
  emptyWrap: { alignItems: 'center', padding: SPACING.xl },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: SPACING.sm },
  viewCoupons: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginTop: SPACING.lg, paddingVertical: 12, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  viewCouponsText: { color: COLORS.text, fontWeight: '800', fontSize: FONT.sm },
});
