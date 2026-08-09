// Phase RWD.1 — full "Earn Points" screen (mobile) at /earn.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useAuth } from '../src/contexts/AuthContext';
import { useReward } from '../src/components/RewardOverlay';
import PremiumCue from '../src/components/PremiumCue';
import {
  fetchEarnOverview, claimMission, routeForAction, ionIcon,
  EarnOverview, EarnMission,
} from '../src/api/earnApi';

export default function EarnScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const { celebrate } = useReward();
  const [data, setData] = useState<EarnOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [claiming, setClaiming] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { setData(await fetchEarnOverview()); }
    catch { /* unauth or error */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => {
    if (!authLoading && !user) router.replace('/login');
  }, [user, authLoading, router]);

  useEffect(() => { if (!authLoading && user) load(); }, [authLoading, user, load]);

  const onClaim = async (m: EarnMission) => {
    setClaiming(m.mission_id);
    try {
      const r = await claimMission(m.mission_id);
      await load();
      celebrate({ points: r.awarded, title: 'Mission complete' });
    } catch {
      /* already claimed or incomplete — refresh state */
      await load();
    } finally { setClaiming(null); }
  };

  if (loading || !data) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const ways = data.ways_to_earn || [];
  const daily = (data.missions || []).filter((m) => m.scope === 'daily');
  const weekly = (data.missions || []).filter((m) => m.scope === 'weekly');
  const goal = data.daily_goal;
  const tier = data.tier;
  const tierPct = tier?.next
    ? Math.min(100, Math.round((tier.lifetime_points / (tier.next.min_points || 1)) * 100))
    : 100;

  return (
    <SafeAreaView style={common.screen}>
      {/* Sticky header */}
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="earn-back" style={s.backBtn}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Earn Points</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}
        testID="earn-root">

        {/* Balance + tier */}
        <View style={s.balanceCard}>
          <View style={s.balanceRow}>
            <View>
              <Text style={s.kicker}>YOUR POINTS</Text>
              <View style={s.balAmtRow}>
                <Ionicons name="cash" size={24} color={COLORS.gold} />
                <Text style={s.balAmt} testID="earn-balance">{data.balance.toLocaleString()}</Text>
              </View>
            </View>
            {data.streak?.current > 0 && (
              <View style={s.streak} testID="earn-streak">
                <Ionicons name="flame" size={15} color={COLORS.primary} />
                <Text style={s.streakText}>{data.streak.current}-day</Text>
              </View>
            )}
          </View>

          {tier && (
            <View style={{ marginTop: 12 }} testID="earn-tier">
              <View style={s.tierRow}>
                <Text style={s.tierName}>{tier.name}</Text>
                {tier.next && (
                  <Text style={s.tierNext}>{tier.points_to_next.toLocaleString()} pts to {tier.next.name}</Text>
                )}
              </View>
              <View style={s.track}><View style={[s.fillPrimary, { width: `${tierPct}%` }]} /></View>
            </View>
          )}

          {goal && (
            <View style={{ marginTop: 12 }} testID="earn-daily-goal">
              <View style={s.tierRow}>
                <Text style={s.goalLabel}>Today&apos;s goal</Text>
                <Text style={s.goalLabel}>{goal.earned}/{goal.target} pts</Text>
              </View>
              <View style={s.track}><View style={[s.fillGold, { width: `${goal.pct}%` }]} /></View>
              {goal.bonus_points > 0 && !goal.complete && (
                <Text style={s.goalHint}>Finish for a +{goal.bonus_points} bonus.</Text>
              )}
            </View>
          )}
        </View>

        {/* Available now */}
        <Text style={s.section}>AVAILABLE NOW</Text>
        <PremiumCue context="rewards" />
        {ways.map((w) => (
          <TouchableOpacity key={w.key} testID={`earn-way-${w.key}`}
            style={[s.item, !w.eligible && { opacity: 0.5 }]}
            onPress={() => router.push(routeForAction(w.action) as any)} activeOpacity={0.85}>
            <View style={s.itemIcon}>
              <Ionicons name={ionIcon(w.icon)} size={17} color={COLORS.primary} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.itemTitle} numberOfLines={1}>{w.title}</Text>
              <Text style={s.itemSub} numberOfLines={1}>{w.subtitle}</Text>
            </View>
            <Text style={s.itemPts}>+{w.points}{w.unit ? ` ${w.unit}` : ''}</Text>
          </TouchableOpacity>
        ))}

        {daily.length > 0 && <Text style={s.section}>DAILY MISSIONS</Text>}
        {daily.map((m) => <MissionRow key={m.mission_id} m={m} claiming={claiming} onClaim={onClaim} />)}

        {weekly.length > 0 && <Text style={s.section}>WEEKLY CHALLENGES</Text>}
        {weekly.map((m) => <MissionRow key={m.mission_id} m={m} claiming={claiming} onClaim={onClaim} />)}

        <TouchableOpacity style={s.walletLink} testID="earn-view-history"
          onPress={() => router.push('/(tabs)/wallet' as any)}>
          <Text style={s.walletLinkText}>View wallet &amp; history</Text>
          <Ionicons name="chevron-forward" size={14} color={COLORS.primary} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function MissionRow({ m, claiming, onClaim }:
  { m: EarnMission; claiming: string | null; onClaim: (m: EarnMission) => void }) {
  const pct = Math.min(100, Math.round((m.progress / m.target) * 100));
  return (
    <View style={s.mission} testID={`mission-${m.mission_id}`}>
      <View style={s.missionHead}>
        <View style={s.itemIcon}>
          <Ionicons name={ionIcon(m.icon)} size={17} color={COLORS.primary} />
        </View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.itemTitle} numberOfLines={1}>{m.title}</Text>
          <Text style={s.itemSub}>{m.progress}/{m.target} · reward +{m.reward_points} pts</Text>
        </View>
        {m.claimed ? (
          <View style={s.claimedTag} testID={`mission-claimed-${m.mission_id}`}>
            <Ionicons name="checkmark" size={13} color={COLORS.green} />
            <Text style={s.claimedText}>Claimed</Text>
          </View>
        ) : m.claimable ? (
          <TouchableOpacity style={s.claimBtn} testID={`mission-claim-${m.mission_id}`}
            disabled={claiming === m.mission_id} onPress={() => onClaim(m)}>
            {claiming === m.mission_id
              ? <ActivityIndicator size="small" color="#fff" />
              : <><Ionicons name="gift" size={13} color="#fff" /><Text style={s.claimText}>Claim</Text></>}
          </TouchableOpacity>
        ) : (
          <Text style={s.pctText}>{pct}%</Text>
        )}
      </View>
      <View style={s.track}>
        <View style={[m.claimed ? s.fillGreen : s.fillPrimary, { width: `${pct}%` }]} />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  topbar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg,
  },
  backBtn: { padding: 2 },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  balanceCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1,
    borderColor: COLORS.cardBorder, padding: SPACING.md,
  },
  balanceRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  kicker: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 2 },
  balAmtRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 },
  balAmt: { color: COLORS.gold, fontSize: FONT.hero, fontWeight: '900' },
  streak: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.primary + '12', paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full },
  streakText: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800' },
  tierRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 },
  tierName: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  tierNext: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  goalLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  goalHint: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 4 },
  track: { height: 6, borderRadius: 3, backgroundColor: COLORS.inputBg, overflow: 'hidden' },
  fillPrimary: { height: '100%', backgroundColor: COLORS.primary },
  fillGold: { height: '100%', backgroundColor: COLORS.gold },
  fillGreen: { height: '100%', backgroundColor: COLORS.green },
  section: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1.5, marginTop: SPACING.lg, marginBottom: SPACING.sm },
  item: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 12, marginBottom: SPACING.sm,
    borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  itemIcon: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  itemTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  itemSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  itemPts: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '800' },
  mission: {
    padding: 12, marginBottom: SPACING.sm, borderRadius: RADIUS.md,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, gap: 10,
  },
  missionHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  claimBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: COLORS.primary, paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.md },
  claimText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800' },
  claimedTag: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  claimedText: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '800' },
  pctText: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '700' },
  walletLink: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 14, marginTop: SPACING.sm },
  walletLinkText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
});
