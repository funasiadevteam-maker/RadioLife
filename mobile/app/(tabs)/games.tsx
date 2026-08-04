import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  ActivityIndicator, RefreshControl, SafeAreaView,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import { fetchPlayAndWin, HOUSE_CAMPAIGNS } from '../../src/api/gamesApi';
import useBigCoinStore from '../../src/stores/useBigCoinStore';

/* Games hub (Phase 39M.3).
   Feed comes from GET /api/games_v2/play_and_win. The old
   `/api/games/discover` + `/api/games/state` calls were dropped: the
   former only ever returns merchant campaigns carrying an `active` flag
   and an `end_at` (the house games have neither, so it was always empty)
   and the latter is a Phase-5 shim.

   NOTE ON COOLDOWNS: games_v2 exposes no `next_available_at` /
   cooldown field anywhere, so we show the listener's REAL play count
   from `played_history` instead of inventing a countdown. */

type CampaignItem = {
  campaign_id: string;
  template_id?: string;
  title: string;
  description?: string;
  sponsor_name?: string;
  top_prize_title?: string;
  prize_count?: number;
  is_platform_funded?: boolean;
  end_at?: string | null;
};

type PlayedRow = { campaign_id: string; result?: string; status?: string };

const TEMPLATE_META: Record<string, { label: string; icon: string; color: string }> = {
  tpl_spin_wheel: { label: 'SPIN & WIN', icon: 'aperture', color: '#a855f7' },
  tpl_quiz: { label: 'QUIZ', icon: 'help-circle', color: '#f59e0b' },
  tpl_scratch_card: { label: 'SCRATCH CARD', icon: 'gift', color: '#ec4899' },
  tpl_slot_machine: { label: 'SLOTS', icon: 'apps', color: '#3b82f6' },
  tpl_memory_match: { label: 'MEMORY MATCH', icon: 'grid', color: '#14b8a6' },
  tpl_word_puzzle: { label: 'WORD PUZZLE', icon: 'text', color: '#8b5cf6' },
  tpl_mystery_box: { label: 'MYSTERY BOX', icon: 'cube', color: '#f97316' },
  tpl_pick_a_card: { label: 'PICK A CARD', icon: 'albums', color: '#0ea5e9' },
};

/* House games have purpose-built screens; everything else uses the
   generic games_v2 player at /game/[campaignId]. */
const DEDICATED_ROUTES: Record<string, string> = {
  [HOUSE_CAMPAIGNS.spin]: '/games/spin',
  [HOUSE_CAMPAIGNS.trivia]: '/games/trivia-game',
  [HOUSE_CAMPAIGNS.lyric]: '/games/lyric-game',
};

function routeForCampaign(campaignId: string) {
  return DEDICATED_ROUTES[campaignId] || `/game/${campaignId}`;
}

export default function GamesHub() {
  const router = useRouter();
  const [campaigns, setCampaigns] = useState<CampaignItem[]>([]);
  const [played, setPlayed] = useState<PlayedRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [failed, setFailed] = useState(false);

  const balance = useBigCoinStore((s) => s.balance);
  const balanceLoaded = useBigCoinStore((s) => s.loaded);
  const refreshBalance = useBigCoinStore((s) => s.refresh);

  const load = useCallback(async () => {
    try {
      const { unlockedForYou, playedHistory } = await fetchPlayAndWin();
      setCampaigns(unlockedForYou);
      setPlayed(playedHistory);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Keep the BigCoin chip honest whenever the tab regains focus (e.g.
  // straight after winning a game).
  useFocusEffect(
    useCallback(() => { refreshBalance(); }, [refreshBalance]),
  );

  const onRefresh = () => { setRefreshing(true); refreshBalance(); load(); };

  const playCount = (campaignId: string) =>
    played.filter((p) => p.campaign_id === campaignId).length;

  const winCount = (campaignId: string) =>
    played.filter((p) => p.campaign_id === campaignId && p.result === 'win').length;

  const featured = campaigns.find((c) => c.campaign_id === HOUSE_CAMPAIGNS.spin);
  const others = campaigns.filter((c) => c.campaign_id !== HOUSE_CAMPAIGNS.spin);

  const QUICK_GAMES = [
    { id: 'spin', icon: 'aperture-outline', label: 'Spin & Win', desc: 'Spin the wheel for BigCoin & coupons', color: '#a855f7', route: '/games/spin' },
    { id: 'trivia', icon: 'musical-notes-outline', label: 'Music Trivia', desc: 'Guess the song and earn BigCoin', color: '#f59e0b', route: '/games/trivia-game' },
    { id: 'lyric', icon: 'mic-outline', label: 'Guess the Lyric', desc: 'Finish the lyric to win rewards', color: '#ec4899', route: '/games/lyric-game' },
  ];

  if (loading) {
    return (
      <SafeAreaView style={s.screen} testID="games-hub-loading">
        <View style={s.center}>
          <ActivityIndicator size="large" color={COLORS.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={s.screen} testID="games-hub-page">
      <ScrollView
        contentContainerStyle={s.scrollContent}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh}
            tintColor={COLORS.primary} colors={[COLORS.primary]} />
        }
      >
        {/* Header */}
        <View style={s.header}>
          <View style={s.headerIcon}>
            <Ionicons name="game-controller" size={22} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.headerLabel}>PLAY & WIN</Text>
            <Text style={s.headerTitle}>Games</Text>
          </View>
          <TouchableOpacity
            style={s.coinChip}
            onPress={() => router.push('/wallet')}
            activeOpacity={0.85}
            testID="games-bigcoin-chip"
          >
            <Text style={s.coinGlyph}>₿</Text>
            <Text style={s.coinAmount} testID="games-bigcoin-balance">
              {balanceLoaded ? balance : '—'}
            </Text>
          </TouchableOpacity>
        </View>

        <Text style={s.headerSubtitle}>
          Spin the wheel, test your music trivia, or make predictions to win prizes.
        </Text>

        {/* Featured: Spin & Win Card */}
        <TouchableOpacity
          style={s.featuredCard}
          onPress={() => router.push('/games/spin')}
          activeOpacity={0.85}
          testID="featured-spin-card"
        >
          <View style={s.featuredBadge}>
            <Text style={s.featuredBadgeText}>FEATURED</Text>
          </View>
          <View style={s.featuredContent}>
            <View style={s.featuredIconWrap}>
              <Ionicons name="aperture" size={36} color="#fff" />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.featuredTitle}>{featured?.title || 'Spin the Wheel'}</Text>
              <Text style={s.featuredDesc}>
                {featured?.top_prize_title
                  ? `Top prize: ${featured.top_prize_title}`
                  : (featured?.description || 'Spin to win BigCoin, coupons & more!')}
              </Text>
              {playCount(HOUSE_CAMPAIGNS.spin) > 0 && (
                <Text style={s.playedNote} testID="featured-play-count">
                  Played {playCount(HOUSE_CAMPAIGNS.spin)}×
                  {winCount(HOUSE_CAMPAIGNS.spin) > 0
                    ? ` · ${winCount(HOUSE_CAMPAIGNS.spin)} win${winCount(HOUSE_CAMPAIGNS.spin) > 1 ? 's' : ''}`
                    : ''}
                </Text>
              )}
              <View style={s.featuredBtn}>
                <Text style={s.featuredBtnText}>SPIN NOW</Text>
                <Ionicons name="arrow-forward" size={14} color="#fff" />
              </View>
            </View>
          </View>
        </TouchableOpacity>

        {/* Quick Games Grid */}
        <Text style={s.sectionTitle}>QUICK GAMES</Text>
        <View style={s.quickGrid}>
          {QUICK_GAMES.map((g) => (
            <TouchableOpacity
              key={g.id}
              style={s.quickCard}
              onPress={() => router.push(g.route as any)}
              activeOpacity={0.85}
              testID={`quick-game-${g.id}`}
            >
              <View style={[s.quickIconWrap, { backgroundColor: `${g.color}15` }]}>
                <Ionicons name={g.icon as any} size={24} color={g.color} />
              </View>
              <View style={{ flex: 1 }}>
                <Text style={s.quickLabel}>{g.label}</Text>
                <Text style={s.quickDesc}>{g.desc}</Text>
              </View>
              <Ionicons name="chevron-forward" size={14} color={COLORS.textMuted} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Predict & Win Section */}
        <Text style={s.sectionTitle}>PREDICTIONS</Text>
        <TouchableOpacity
          style={s.predictCard}
          onPress={() => router.push('/games/predict')}
          activeOpacity={0.85}
          testID="predict-win-card"
        >
          <View style={s.predictIconWrap}>
            <Ionicons name="trophy" size={28} color="#f59e0b" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.predictTitle}>Predict & Win</Text>
            <Text style={s.predictDesc}>
              Free community predictions. Make your pick & win prizes!
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color={COLORS.textMuted} />
        </TouchableOpacity>

        {/* Live games_v2 campaigns (GET /api/games_v2/play_and_win) */}
        {others.length > 0 && (
          <>
            <Text style={s.sectionTitle}>MORE GAMES LIVE NOW</Text>
            <View style={s.campaignGrid}>
              {others.map((g) => {
                const meta = TEMPLATE_META[g.template_id || ''] || {
                  label: 'GAME', icon: 'game-controller', color: COLORS.primary,
                };
                const plays = playCount(g.campaign_id);
                return (
                  <TouchableOpacity
                    key={g.campaign_id}
                    style={s.campaignCard}
                    onPress={() => router.push(routeForCampaign(g.campaign_id) as any)}
                    activeOpacity={0.85}
                    testID={`game-card-${g.campaign_id}`}
                  >
                    <View style={[s.campaignIconWrap, { backgroundColor: `${meta.color}18` }]}>
                      <Ionicons name={meta.icon as any} size={22} color={meta.color} />
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={[s.campaignType, { color: meta.color }]}>{meta.label}</Text>
                      <Text style={s.campaignName} numberOfLines={1}>{g.title}</Text>
                      <Text style={s.campaignMerchant} numberOfLines={1}>
                        {g.top_prize_title
                          ? `Top prize: ${g.top_prize_title}`
                          : (g.sponsor_name || 'BigFM')}
                        {plays > 0 ? ` · played ${plays}×` : ''}
                      </Text>
                    </View>
                    <Ionicons name="chevron-forward" size={16} color={COLORS.textMuted} />
                  </TouchableOpacity>
                );
              })}
            </View>
          </>
        )}

        {/* Empty / failed states */}
        {campaigns.length === 0 && (
          <View style={s.emptyCard} testID="games-empty">
            <Ionicons
              name={failed ? 'cloud-offline-outline' : 'game-controller-outline'}
              size={40}
              color={COLORS.textMuted}
            />
            <Text style={s.emptyTitle}>
              {failed ? "Couldn't load games" : 'No extra games right now'}
            </Text>
            <Text style={s.emptyDesc}>
              {failed
                ? 'Pull down to try again.'
                : 'Try the quick games above or check back later for new campaigns.'}
            </Text>
          </View>
        )}

        <View style={{ height: 80 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  scrollContent: { padding: SPACING.lg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 8 },
  headerIcon: {
    width: 44, height: 44, borderRadius: 12,
    backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  headerLabel: {
    fontSize: FONT.xs, color: COLORS.textMuted, fontWeight: '700',
    letterSpacing: 1, marginBottom: 2,
  },
  headerTitle: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text },
  coinChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: '#fffbeb', borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: '#fcd34d',
    paddingHorizontal: 12, paddingVertical: 7,
  },
  coinGlyph: { fontSize: FONT.md, fontWeight: '900', color: COLORS.gold },
  coinAmount: { fontSize: FONT.md, fontWeight: '900', color: COLORS.text },
  playedNote: {
    fontSize: FONT.xs, color: COLORS.textMuted, fontWeight: '700', marginBottom: 8,
  },
  headerSubtitle: {
    fontSize: FONT.sm, color: COLORS.textDim, marginBottom: SPACING.lg,
    lineHeight: 18,
  },

  // Featured card
  featuredCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.lg, marginBottom: SPACING.lg,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06, shadowRadius: 8, elevation: 3,
    overflow: 'hidden',
  },
  featuredBadge: {
    backgroundColor: '#a855f7', borderRadius: RADIUS.full,
    paddingHorizontal: 10, paddingVertical: 3,
    alignSelf: 'flex-start', marginBottom: 12,
  },
  featuredBadgeText: { color: '#fff', fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  featuredContent: { flexDirection: 'row', alignItems: 'center', gap: 16 },
  featuredIconWrap: {
    width: 64, height: 64, borderRadius: 20,
    backgroundColor: '#a855f7',
    alignItems: 'center', justifyContent: 'center',
  },
  featuredTitle: { fontSize: FONT.xl, fontWeight: '900', color: COLORS.text, marginBottom: 4 },
  featuredDesc: { fontSize: FONT.sm, color: COLORS.textDim, lineHeight: 18, marginBottom: 10 },
  featuredBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: COLORS.primary, borderRadius: RADIUS.full,
    paddingHorizontal: 16, paddingVertical: 8, alignSelf: 'flex-start',
  },
  featuredBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800', letterSpacing: 0.5 },

  // Section
  sectionTitle: {
    fontSize: FONT.sm, fontWeight: '800', color: COLORS.textDim,
    letterSpacing: 1, marginBottom: SPACING.md, marginTop: SPACING.sm,
  },

  // Quick games
  quickGrid: { gap: 8, marginBottom: SPACING.lg },
  quickCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.md,
  },
  quickIconWrap: {
    width: 44, height: 44, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center',
  },
  quickLabel: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  quickDesc: { fontSize: FONT.xs, fontWeight: '500', color: COLORS.textMuted, marginTop: 2 },

  // Predict card
  predictCard: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: '#f59e0b40',
    padding: SPACING.lg, marginBottom: SPACING.lg,
  },
  predictIconWrap: {
    width: 52, height: 52, borderRadius: 16,
    backgroundColor: '#f59e0b15',
    alignItems: 'center', justifyContent: 'center',
  },
  predictTitle: { fontSize: FONT.lg, fontWeight: '900', color: COLORS.text, marginBottom: 2 },
  predictDesc: { fontSize: FONT.sm, color: COLORS.textDim, lineHeight: 18 },

  // Campaign grid
  campaignGrid: { gap: 8, marginBottom: SPACING.lg },
  campaignCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.md,
  },
  campaignIconWrap: {
    width: 44, height: 44, borderRadius: 12,
    alignItems: 'center', justifyContent: 'center',
  },
  campaignType: {
    fontSize: 10, fontWeight: '800', color: '#a855f7',
    letterSpacing: 0.6, marginBottom: 2,
  },
  campaignName: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  campaignMerchant: { fontSize: FONT.xs, color: COLORS.textMuted, marginTop: 2 },

  // Empty
  emptyCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.xl, alignItems: 'center',
  },
  emptyTitle: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text, marginTop: 12 },
  emptyDesc: { fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center', marginTop: 6 },
});
