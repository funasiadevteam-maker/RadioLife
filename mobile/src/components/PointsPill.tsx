// Phase RWD.1 — persistent points pill for the mobile header.
// Shows the live points balance; tapping opens a bottom-sheet modal
// with the top "ways to earn right now" + a link to the Earn screen.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Modal, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import { fetchEarnOverview, routeForAction, ionIcon, EarnOverview } from '../api/earnApi';

export default function PointsPill() {
  const router = useRouter();
  const [data, setData] = useState<EarnOverview | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancel = false;
    fetchEarnOverview().then((d) => { if (!cancel) setData(d); }).catch(() => {});
    return () => { cancel = true; };
  }, []);

  const balance = data?.balance ?? 0;
  const topWays = (data?.ways_to_earn || []).filter((w) => w.eligible).slice(0, 3);

  const go = (action?: string) => {
    setOpen(false);
    router.push(routeForAction(action) as any);
  };

  return (
    <>
      <TouchableOpacity style={s.pill} testID="points-pill" onPress={() => setOpen(true)} activeOpacity={0.85}>
        <Ionicons name="cash" size={15} color={COLORS.gold} />
        <Text style={s.pillText} testID="points-pill-balance">{balance.toLocaleString()}</Text>
      </TouchableOpacity>

      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <Pressable style={s.backdrop} onPress={() => setOpen(false)} />
        <View style={s.sheet} testID="points-pill-sheet">
          <View style={s.handle} />
          <View style={s.sheetHead}>
            <Text style={s.sheetTitle}>Ways to earn right now</Text>
            <TouchableOpacity onPress={() => setOpen(false)} testID="points-pill-close">
              <Ionicons name="close" size={20} color={COLORS.textDim} />
            </TouchableOpacity>
          </View>

          {data?.tier && (
            <Text style={s.tier} testID="points-pill-tier">
              <Text style={{ color: COLORS.primary, fontWeight: '800' }}>{data.tier.name}</Text>
              {data.tier.next ? ` · ${data.tier.points_to_next.toLocaleString()} pts to ${data.tier.next.name}` : ''}
            </Text>
          )}

          {topWays.length === 0 && (
            <Text style={s.empty}>You&apos;re all caught up today 🎉</Text>
          )}
          {topWays.map((w) => (
            <TouchableOpacity key={w.key} style={s.row} testID={`pill-way-${w.key}`}
              onPress={() => go(w.action)} activeOpacity={0.85}>
              <View style={s.rowIcon}>
                <Ionicons name={ionIcon(w.icon)} size={16} color={COLORS.primary} />
              </View>
              <Text style={s.rowTitle} numberOfLines={1}>{w.title}</Text>
              <Text style={s.rowPts}>+{w.points}{w.unit ? ` ${w.unit}` : ''}</Text>
              <Ionicons name="chevron-forward" size={15} color={COLORS.textMuted} />
            </TouchableOpacity>
          ))}

          <TouchableOpacity style={s.seeAll} testID="pill-see-all"
            onPress={() => { setOpen(false); router.push('/earn' as any); }}>
            <Text style={s.seeAllText}>See all ways to earn</Text>
            <Ionicons name="chevron-forward" size={14} color={COLORS.primary} />
          </TouchableOpacity>
        </View>
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  pill: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    paddingHorizontal: 10, height: 34, borderRadius: 17,
    backgroundColor: COLORS.gold + '18', borderWidth: 1, borderColor: COLORS.gold + '55',
  },
  pillText: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: {
    backgroundColor: COLORS.bg, borderTopLeftRadius: RADIUS.xl, borderTopRightRadius: RADIUS.xl,
    padding: SPACING.lg, paddingBottom: SPACING.xl + 8, gap: SPACING.sm,
  },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: COLORS.surfaceBorder, marginBottom: SPACING.sm },
  sheetHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  sheetTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  tier: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', marginBottom: 4 },
  empty: { color: COLORS.textMuted, fontSize: FONT.sm, paddingVertical: 8 },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    padding: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.card,
    borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  rowIcon: { width: 30, height: 30, borderRadius: 15, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  rowTitle: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  rowPts: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '800' },
  seeAll: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, paddingVertical: 10, marginTop: 4 },
  seeAllText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
});
