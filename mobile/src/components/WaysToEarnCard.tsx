// Phase RWD.1 — "Ways to Earn Today" home card + Premium teaser (mobile).
import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import { fetchEarnOverview, routeForAction, ionIcon, EarnOverview } from '../api/earnApi';

export default function WaysToEarnCard() {
  const router = useRouter();
  const [data, setData] = useState<EarnOverview | null>(null);

  useEffect(() => {
    let cancel = false;
    fetchEarnOverview().then((d) => { if (!cancel) setData(d); }).catch(() => {});
    return () => { cancel = true; };
  }, []);

  if (!data) return null;
  const ways = (data.ways_to_earn || []).slice(0, 5);
  const goal = data.daily_goal;
  const bonuses = data.active_bonuses || [];

  return (
    <View style={s.wrap} testID="home-ways-to-earn">
      {bonuses.map((b) => (
        <View key={b.window_id} style={s.bonus} testID={`home-bonus-${b.window_id}`}>
          <Ionicons name="flash" size={16} color={COLORS.gold} />
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={s.bonusTitle} numberOfLines={1}>{b.title}</Text>
            {!!b.sponsor_name && (
              <Text style={s.bonusSub} numberOfLines={1}>Sponsored by {b.sponsor_name}</Text>
            )}
          </View>
          <Text style={s.bonusMult}>{b.multiplier}×</Text>
        </View>
      ))}
      <View style={s.card}>
        <View style={s.head}>
          <View style={s.headLeft}>
            <Ionicons name="sparkles" size={16} color={COLORS.gold} />
            <Text style={s.title}>Ways to Earn Today</Text>
          </View>
          <TouchableOpacity onPress={() => router.push('/earn' as any)} testID="ways-see-all">
            <Text style={s.seeAll}>See all</Text>
          </TouchableOpacity>
        </View>

        {goal && (
          <>
            <Text style={s.goalText} testID="ways-daily-goal">
              Daily goal · {goal.earned}/{goal.target} pts
              {goal.bonus_points ? ` — +${goal.bonus_points} bonus` : ''}
            </Text>
            <View style={s.track}>
              <View style={[s.fill, { width: `${goal.pct}%` }]} />
            </View>
          </>
        )}

        {ways.map((w) => (
          <TouchableOpacity key={w.key} style={s.row} testID={`ways-item-${w.key}`}
            onPress={() => router.push(routeForAction(w.action) as any)} activeOpacity={0.85}>
            <View style={s.rowIcon}>
              <Ionicons name={ionIcon(w.icon)} size={16} color={COLORS.primary} />
            </View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.rowTitle} numberOfLines={1}>{w.title}</Text>
              <Text style={s.rowSub} numberOfLines={1}>{w.subtitle}</Text>
            </View>
            <Text style={s.rowPts}>+{w.points}{w.unit ? ` ${w.unit}` : ''}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Contextual Premium teaser — full Premium cue system lands later. */}
      <TouchableOpacity style={s.premium} testID="home-premium-teaser"
        onPress={() => router.push('/premium' as any)} activeOpacity={0.85}>
        <Ionicons name="sparkles" size={16} color={COLORS.purple} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.premiumTitle}>Get more with Premium</Text>
          <Text style={s.premiumSub} numberOfLines={1}>Fewer ads · more AI · extra rewards</Text>
        </View>
        <Ionicons name="chevron-forward" size={15} color={COLORS.purple} />
      </TouchableOpacity>
    </View>
  );
}

const s = StyleSheet.create({
  wrap: { marginHorizontal: SPACING.md, marginBottom: SPACING.md, gap: SPACING.sm },
  card: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1,
    borderColor: COLORS.cardBorder, padding: SPACING.md, gap: 10,
  },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  headLeft: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  title: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  seeAll: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '700' },
  goalText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  track: { height: 6, borderRadius: 3, backgroundColor: COLORS.inputBg, overflow: 'hidden' },
  fill: { height: '100%', backgroundColor: COLORS.gold },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 8, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder,
  },
  rowIcon: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  rowTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  rowSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  rowPts: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '800' },
  premium: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: SPACING.md,
    borderRadius: RADIUS.lg, backgroundColor: COLORS.purple + '12',
    borderWidth: 1, borderColor: COLORS.purple + '33',
  },
  premiumTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  premiumSub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  bonus: {
    flexDirection: 'row', alignItems: 'center', gap: 8, padding: SPACING.md,
    borderRadius: RADIUS.lg, backgroundColor: COLORS.gold + '18',
    borderWidth: 1, borderColor: COLORS.gold + '44',
  },
  bonusTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  bonusSub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  bonusMult: { color: COLORS.gold, fontSize: FONT.md, fontWeight: '900' },
});
