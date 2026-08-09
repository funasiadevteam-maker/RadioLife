// Phase MKT.2 — Consumer Instant-Win Games (Spin & Scratch) — mobile.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import Animated, { useSharedValue, useAnimatedStyle, withTiming, withRepeat, withSequence, Easing } from 'react-native-reanimated';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

interface Game {
  campaign_id: string; type: string; sponsor_name?: string; title: string;
  prize_label?: string; win_points: number;
  played?: { won: boolean; awarded: number } | null;
}

export default function BrandGames() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [items, setItems] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [result, setResult] = useState<Record<string, { won: boolean; awarded: number }>>({});

  const load = useCallback(async () => {
    try { const r = await api.get('/brand-games/active'); setItems(r.data.items || []); }
    catch { /* unauth */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const play = async (g: Game) => {
    if (busy) return;
    setBusy(g.campaign_id);
    try {
      const r = await api.post(`/brand-games/${g.campaign_id}/play`);
      setResult((p) => ({ ...p, [g.campaign_id]: { won: r.data.won, awarded: r.data.awarded } }));
      if (r.data.won && r.data.awarded > 0) {
        celebrate({ points: r.data.awarded, title: 'You won!' });
      }
      await load();
    } catch { await load(); }
    finally { setBusy(null); }
  };

  if (loading) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="bg-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Instant Win</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}
        testID="brand-games-root">
        <Text style={s.intro}>Spin the wheel or scratch a card — win points instantly.</Text>

        {items.length === 0 && (
          <View style={s.card}>
            <Ionicons name="game-controller-outline" size={28} color={COLORS.textMuted} />
            <Text style={s.empty}>No games live right now.</Text>
            <Text style={s.dim}>Check back soon for new instant-win games.</Text>
          </View>
        )}

        {items.map((g) => {
          const res = result[g.campaign_id] || g.played;
          const done = !!res;
          return (
            <View key={g.campaign_id} style={s.card} testID={`bg-campaign-${g.campaign_id}`}>
              <View style={s.head}>
                <View style={s.gIcon}>
                  <Ionicons name={g.type === 'scratch' ? 'sparkles' : 'sync-circle'} size={22} color={COLORS.primary} />
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.title} numberOfLines={1}>{g.title}</Text>
                  {!!g.sponsor_name && <Text style={s.sponsor}>by {g.sponsor_name}</Text>}
                </View>
                <View style={s.ptsTag}>
                  <Ionicons name="trophy" size={13} color={COLORS.gold} />
                  <Text style={s.ptsText}>{g.prize_label}</Text>
                </View>
              </View>

              {done ? (
                <View style={[s.resultBox, res!.won ? s.won : s.lost]} testID={`bg-result-${g.campaign_id}`}>
                  <Ionicons name={res!.won ? 'trophy' : 'sad-outline'} size={22}
                    color={res!.won ? COLORS.green : COLORS.textMuted} />
                  <Text style={[s.resultText, { color: res!.won ? COLORS.green : COLORS.textMuted }]}>
                    {res!.won ? `You won +${res!.awarded} points!` : 'Not this time — try another game.'}
                  </Text>
                </View>
              ) : (
                <SpinPlayButton type={g.type} busy={busy === g.campaign_id}
                  onPress={() => play(g)} testID={`bg-play-${g.campaign_id}`} />
              )}
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

function SpinPlayButton({ type, busy, onPress, testID }:
  { type: string; busy: boolean; onPress: () => void; testID: string }) {
  const rot = useSharedValue(0);
  useEffect(() => {
    if (busy) {
      rot.value = withRepeat(withTiming(360, { duration: 600, easing: Easing.linear }), -1);
    } else {
      rot.value = withSequence(withTiming(0, { duration: 0 }));
    }
  }, [busy, rot]);
  const style = useAnimatedStyle(() => ({ transform: [{ rotate: `${rot.value}deg` }] }));
  return (
    <TouchableOpacity style={s.playBtn} onPress={onPress} disabled={busy} testID={testID} activeOpacity={0.85}>
      <Animated.View style={style}>
        <Ionicons name={type === 'scratch' ? 'sparkles' : 'sync-circle'} size={18} color="#fff" />
      </Animated.View>
      <Text style={s.playText}>{busy ? 'Playing…' : type === 'scratch' ? 'Scratch to reveal' : 'Spin now'}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  topbar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg,
  },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md, alignItems: 'stretch' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: SPACING.sm },
  gIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  title: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  sponsor: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  ptsTag: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '18', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full, maxWidth: 130 },
  ptsText: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '900' },
  playBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, paddingVertical: 14, borderRadius: RADIUS.md, marginTop: 4 },
  playText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800' },
  resultBox: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, borderRadius: RADIUS.md, borderWidth: 1, marginTop: 4 },
  won: { backgroundColor: COLORS.green + '14', borderColor: COLORS.green + '55' },
  lost: { backgroundColor: COLORS.inputBg, borderColor: COLORS.surfaceBorder },
  resultText: { fontSize: FONT.sm, fontWeight: '800', flex: 1 },
  empty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 8 },
  dim: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 4 },
});
