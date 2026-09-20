import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, Alert, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../src/contexts/AuthContext';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';

const TPL_ICON: Record<string, string> = {
  tpl_spin_wheel: '🎡', tpl_scratch_card: '🪙', tpl_quiz: '🎯',
  tpl_mystery_box: '🎁', tpl_slot_machine: '🎰', tpl_memory_match: '🧠', tpl_word_puzzle: '✒️',
};

export default function PlayAndWinScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [state, setState] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [drivingMode, setDrivingMode] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
  }, [user, authLoading]);

  const reload = useCallback(async () => {
    try {
      const r = await api.get('/games_v2/play_and_win');
      setState(r.data);
      setDrivingMode(!!r.data.driving_mode_on);
    } catch { Alert.alert('Error', 'Failed to load games'); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { if (!authLoading && user) reload(); }, [reload, authLoading, user]);

  const toggleDriving = async () => {
    try {
      const r = await api.post('/games_v2/user/driving_mode', { on: !drivingMode });
      setDrivingMode(r.data.driving_mode_on);
    } catch { Alert.alert('Error', 'Could not toggle'); }
  };

  if (authLoading || !user) {
    return <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={s.screen} testID="play-and-win-page">
      <ScrollView refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); reload(); }}
        tintColor={COLORS.primary} />}>
        {/* Header */}
        <View style={s.header}>
          <View style={{ flex: 1 }}>
            <TouchableOpacity onPress={() => router.back()} style={s.backRow} testID="paw-back">
              <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
              <Text style={s.backText}>back to radio</Text>
            </TouchableOpacity>
            <Text style={s.title}>Play & Win</Text>
            <Text style={s.sub}>Spin · scratch · quiz · mystery box. Prizes from BigCoin, sponsor coupons, exclusive unlocks.</Text>
          </View>
          <TouchableOpacity
            style={[s.drivingBtn, drivingMode && { backgroundColor: COLORS.green, borderColor: COLORS.green }]}
            onPress={toggleDriving} testID="driving-mode-toggle">
            <Ionicons name="car" size={14} color={drivingMode ? '#fff' : COLORS.textDim} />
            <Text style={[s.drivingText, drivingMode && { color: '#fff' }]}>
              Driving {drivingMode ? 'ON' : 'OFF'}
            </Text>
          </TouchableOpacity>
        </View>

        {drivingMode && (
          <View style={s.drivingBanner} testID="driving-banner">
            <Ionicons name="shield-checkmark" size={14} color={COLORS.green} />
            <Text style={s.drivingBannerText}>Driving mode is on — Play Now replaced by Save for later.</Text>
          </View>
        )}

        {loading || !state ? (
          <View style={s.loadWrap}><ActivityIndicator size="large" color={COLORS.primary} /></View>
        ) : (
          <>
            <Section title="Unlocked for you" icon="sparkles" testId="section-unlocked"
              items={state.unlocked_for_you || []} drivingMode={drivingMode} router={router} />
            {(state.expiring_soon || []).length > 0 && (
              <Section title="Expiring soon" icon="time" testId="section-expiring"
                items={state.expiring_soon} drivingMode={drivingMode} router={router} />
            )}
            {(state.played_history || []).length > 0 && (
              <View style={s.section} testID="section-played-history">
                <Text style={s.sectionTitle}>
                  <Ionicons name="trophy" size={14} color={COLORS.gold} /> Played history
                  <Text style={s.badge}> {state.played_history.length}</Text>
                </Text>
                {state.played_history.slice(0, 10).map((h: any) => (
                  <View key={h.session_id} style={s.historyCard} testID={`history-${h.session_id}`}>
                    <View style={[s.resultTag, h.result === 'win' && { backgroundColor: COLORS.green }]}>
                      <Text style={s.resultTagText}>{h.result === 'win' ? '🏆 WIN' : 'LOSE'}</Text>
                    </View>
                    <Text style={s.historyMeta}>{new Date(h.started_at).toLocaleString()}</Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Section({ title, icon, testId, items, drivingMode, router }: any) {
  return (
    <View style={s.section} testID={testId}>
      <Text style={s.sectionTitle}>
        <Ionicons name={icon} size={14} color={COLORS.secondary} /> {title}
        <Text style={s.badge}> {items.length}</Text>
      </Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: SPACING.sm, paddingHorizontal: SPACING.md }}>
        {items.length === 0 ? (
          <Text style={s.emptyText}>No campaigns here yet.</Text>
        ) : items.map((c: any) => (
          <CampaignCard key={c.campaign_id} campaign={c} drivingMode={drivingMode} router={router} />
        ))}
      </ScrollView>
    </View>
  );
}

function CampaignCard({ campaign, drivingMode, router }: any) {
  const icon = TPL_ICON[campaign.template_id] || '🎮';
  const primary = campaign.brand_colors_json?.primary || COLORS.primary;
  return (
    <View style={[s.card, { borderTopColor: primary, borderTopWidth: 3 }]} testID={`paw-card-${campaign.campaign_id}`}>
      <View style={[s.cardIcon, { backgroundColor: primary }]}>
        <Text style={{ fontSize: 24 }}>{icon}</Text>
      </View>
      <Text style={s.cardSponsor} numberOfLines={1}>
        <Ionicons name="gift" size={9} color={COLORS.secondary} /> {campaign.sponsor_name}
      </Text>
      <Text style={s.cardTitle} numberOfLines={2}>{campaign.title}</Text>
      {campaign.top_prize_title && (
        <Text style={s.cardPrize} numberOfLines={1}>
          <Ionicons name="cash" size={11} color={COLORS.gold} /> {campaign.top_prize_title}
        </Text>
      )}
      {campaign.description && <Text style={s.cardDesc} numberOfLines={2}>{campaign.description}</Text>}
      {campaign.is_platform_funded && (
        <View style={s.houseTag}><Text style={s.houseTagText}>FUUSIC HOUSE</Text></View>
      )}
      <TouchableOpacity
        style={[s.playBtn, drivingMode && { backgroundColor: COLORS.card }]}
        onPress={() => router.push(`/game/${campaign.campaign_id}`)}
        disabled={false}
        testID={`play-btn-${campaign.campaign_id}`}>
        <Text style={s.playBtnText}>{drivingMode ? 'Save for later' : 'Play now'}</Text>
        <Ionicons name={drivingMode ? 'car' : 'game-controller'} size={12} color="#fff" />
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', padding: SPACING.md, paddingTop: SPACING.lg, gap: SPACING.md },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  title: { color: COLORS.text, fontSize: 28, fontWeight: '900' },
  sub: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 18, marginTop: 4 },
  drivingBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.cardBorder, alignSelf: 'flex-start',
  },
  drivingText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  drivingBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: 'rgba(34,197,94,0.1)', paddingHorizontal: SPACING.md,
    paddingVertical: 8, marginHorizontal: SPACING.md, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: 'rgba(34,197,94,0.3)', marginBottom: SPACING.sm,
  },
  drivingBannerText: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '600', flex: 1 },
  loadWrap: { paddingVertical: 60, alignItems: 'center' },
  section: { marginBottom: SPACING.lg },
  sectionTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800', paddingHorizontal: SPACING.md, marginBottom: SPACING.sm },
  badge: { color: COLORS.textMuted, fontWeight: '600' },
  emptyText: { color: COLORS.textMuted, fontSize: FONT.sm, paddingVertical: 20 },
  card: {
    width: 220, backgroundColor: COLORS.card, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.sm,
    overflow: 'hidden',
  },
  cardIcon: { width: 48, height: 48, borderRadius: RADIUS.md, alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  cardSponsor: { color: COLORS.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, marginBottom: 2 },
  cardTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginBottom: 4, lineHeight: 18 },
  cardPrize: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '700', marginBottom: 4 },
  cardDesc: { color: COLORS.textMuted, fontSize: 10, lineHeight: 14, marginBottom: 6 },
  houseTag: { alignSelf: 'flex-start', paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.sm, backgroundColor: 'rgba(242,107,42,0.1)', marginBottom: 6 },
  houseTagText: { color: COLORS.primary, fontSize: 8, fontWeight: '800', letterSpacing: 1 },
  playBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: COLORS.primary, paddingVertical: 8, borderRadius: RADIUS.md, marginTop: 'auto' as any,
  },
  playBtnText: { color: '#fff', fontWeight: '700', fontSize: FONT.xs },
  historyCard: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: SPACING.md, paddingVertical: 6,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder,
  },
  resultTag: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.sm, backgroundColor: COLORS.textMuted },
  resultTagText: { color: '#fff', fontSize: FONT.xs, fontWeight: '800' },
  historyMeta: { color: COLORS.textMuted, fontSize: FONT.xs },
});
