import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import api from '../../src/api/client';

interface Category {
  id: string;
  name: string;
  icon?: string;
  tagline?: string;
  market?: string;
}

interface HistoryItem {
  session_id: string;
  category_slug?: string;
  difficulty?: number;
  final_score: number;
  bigcoin_awarded: number;
}

export default function TriviaTab() {
  const router = useRouter();
  const [cats, setCats] = useState<Category[]>([]);
  const [market, setMarket] = useState('');
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [c, h] = await Promise.all([
        api.get('/trivia/categories'),
        api.get('/trivia/me/history?limit=5').catch(() => ({ data: { items: [] } })),
      ]);
      setCats(c.data?.categories || []);
      setMarket(c.data?.market || '');
      setHistory(h.data?.items || []);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  if (loading) {
    return (
      <View style={common.center} testID="trivia-loading">
        <ActivityIndicator size="large" color={COLORS.primary} />
        <Text style={s.loadingText}>Loading trivia…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={common.screen} testID="trivia-root">
      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
      >
        {/* Header */}
        <View style={s.headerRow}>
          <View style={s.liveChip}>
            <View style={s.liveDot} />
            <Text style={s.liveText}>TRIVIA · {market ? market.toUpperCase() : '…'}</Text>
          </View>
        </View>

        <Text style={s.heroTitle}>
          Pick a topic,{' '}
          <Text style={{ color: COLORS.primary }}>play solo</Text>
          <Text style={{ color: COLORS.textDim }}> or </Text>
          <Text style={{ color: COLORS.secondary }}>with friends.</Text>
        </Text>
        <Text style={s.heroSub}>
          10 questions, server-timed, AI-generated for your city. Earn BigCoin on every session.
        </Text>

        {/* Action buttons */}
        <View style={s.actionRow}>
          <TouchableOpacity
            style={common.btnPrimary}
            onPress={() => router.push('/trivia/rooms/create')}
            testID="trivia-create-room-btn"
          >
            <Ionicons name="add" size={16} color="#fff" />
            <Text style={common.btnPrimaryText}>Host live room</Text>
          </TouchableOpacity>
          <TouchableOpacity
            style={common.btnGhost}
            onPress={() => router.push('/trivia/join')}
            testID="trivia-join-room-btn"
          >
            <Ionicons name="people" size={16} color={COLORS.textDim} />
            <Text style={common.btnGhostText}>Join with code</Text>
          </TouchableOpacity>
        </View>

        {/* Category grid */}
        <View testID="trivia-categories">
          {cats.length === 0 && (
            <View style={[common.card, s.emptyCard]}>
              <Ionicons name="help-circle-outline" size={24} color={COLORS.textDim} />
              <Text style={s.emptyText}>No active categories for your market yet.</Text>
            </View>
          )}
          {cats.map((c) => (
            <TouchableOpacity
              key={c.id}
              style={s.catCard}
              onPress={() => router.push(`/trivia/play?cat=${encodeURIComponent(c.id)}`)}
              testID={`trivia-category-${c.id}`}
              activeOpacity={0.7}
            >
              <View style={s.catIcon}>
                <Text style={s.catIconText}>{c.icon || '🧠'}</Text>
              </View>
              <View style={{ flex: 1 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Text style={s.catName}>{c.name}</Text>
                  {c.market && c.market !== 'global' && (
                    <View style={s.marketChip}>
                      <Text style={s.marketChipText}>{c.market.toUpperCase()}</Text>
                    </View>
                  )}
                </View>
                {c.tagline ? <Text style={s.catTagline}>{c.tagline}</Text> : null}
              </View>
              <Ionicons name="chevron-forward" size={18} color={COLORS.textDim} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Recent history */}
        {history.length > 0 && (
          <View testID="trivia-history" style={{ marginTop: SPACING.lg }}>
            <Text style={common.sectionTitle}>Your recent runs</Text>
            <View style={common.card}>
              {history.map((h, i) => (
                <View key={h.session_id} style={[s.histRow, i > 0 && s.histBorder]}>
                  <Text style={s.histLabel}>{h.category_slug || '—'} · diff {h.difficulty}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                    <Text style={s.histScore}>{h.final_score}</Text>
                    <Text style={s.histBc}>+{h.bigcoin_awarded} BC</Text>
                  </View>
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  loadingText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.sm },
  headerRow: { marginBottom: SPACING.sm },
  liveChip: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.green },
  liveText: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', letterSpacing: 2 },
  heroTitle: { fontSize: 28, fontWeight: '900', color: COLORS.text, lineHeight: 34, marginBottom: 8 },
  heroSub: { fontSize: 13, color: COLORS.textDim, lineHeight: 18, marginBottom: SPACING.md },
  actionRow: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.lg },
  emptyCard: { alignItems: 'center', gap: 8 },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center' },
  catCard: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.md,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md,
    marginBottom: SPACING.sm,
  },
  catIcon: {
    width: 48, height: 48, borderRadius: RADIUS.md,
    backgroundColor: 'rgba(242,107,42,0.12)',
    alignItems: 'center', justifyContent: 'center',
  },
  catIconText: { fontSize: 24 },
  catName: { fontSize: 16, fontWeight: '800', color: COLORS.text },
  catTagline: { fontSize: 11, color: COLORS.textDim, marginTop: 2 },
  marketChip: {
    backgroundColor: 'rgba(59,130,246,0.12)',
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full,
  },
  marketChipText: { fontSize: 9, fontWeight: '700', color: COLORS.secondary },
  histRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 10 },
  histBorder: { borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.06)' },
  histLabel: { fontSize: 12, color: COLORS.textDim },
  histScore: { fontSize: 16, fontWeight: '800', color: COLORS.secondary },
  histBc: { fontSize: 11, fontWeight: '700', color: COLORS.gold },
});
