// Phase RWD.2 — global post-action reward celebration (mobile).
// useReward().celebrate({ points, title }) shows points earned, the fresh
// balance, and 2 "keep earning" next actions in a bottom-sheet modal.
import React, { createContext, useContext, useCallback, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Modal, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import { fetchEarnOverview, routeForAction, ionIcon, EarnWay } from '../api/earnApi';

interface CelebrateArgs { points: number; title?: string }
const RewardCtx = createContext<{ celebrate: (a: CelebrateArgs) => void }>({ celebrate: () => {} });
export const useReward = () => useContext(RewardCtx);

export function RewardProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [state, setState] = useState<{ points: number; title: string; balance: number | null; ways: EarnWay[] } | null>(null);

  const celebrate = useCallback(async ({ points, title }: CelebrateArgs) => {
    setState({ points, title: title || 'Points earned', balance: null, ways: [] });
    try {
      const d = await fetchEarnOverview();
      const ways = (d.ways_to_earn || []).filter((w) => w.eligible).slice(0, 2);
      setState({ points, title: title || 'Points earned', balance: d.balance, ways });
    } catch { /* keep basic celebration */ }
  }, []);

  const close = () => setState(null);

  return (
    <RewardCtx.Provider value={{ celebrate }}>
      {children}
      <Modal visible={!!state} transparent animationType="fade" onRequestClose={close}>
        <Pressable style={s.backdrop} onPress={close} />
        {state && (
          <View style={s.wrap} pointerEvents="box-none">
            <View style={s.card} testID="reward-overlay">
              <View style={s.iconWrap}>
                <Ionicons name="sparkles" size={26} color={COLORS.gold} />
              </View>
              <Text style={s.kicker}>{state.title.toUpperCase()}</Text>
              <View style={s.pointsRow} testID="reward-points">
                <Ionicons name="cash" size={24} color={COLORS.gold} />
                <Text style={s.points}>+{state.points}</Text>
              </View>
              {state.balance != null && (
                <Text style={s.balance} testID="reward-balance">
                  New balance · <Text style={{ color: COLORS.text, fontWeight: '800' }}>{state.balance.toLocaleString()}</Text>
                </Text>
              )}

              {state.ways.length > 0 && (
                <View style={s.ways}>
                  <Text style={s.waysLabel}>KEEP EARNING</Text>
                  {state.ways.map((w) => (
                    <TouchableOpacity key={w.key} style={s.wayRow} testID={`reward-keep-${w.key}`}
                      onPress={() => { close(); router.push(routeForAction(w.action) as any); }}>
                      <Ionicons name={ionIcon(w.icon)} size={15} color={COLORS.primary} />
                      <Text style={s.wayTitle} numberOfLines={1}>{w.title}</Text>
                      <Text style={s.wayPts}>+{w.points}{w.unit ? ` ${w.unit}` : ''}</Text>
                      <Ionicons name="chevron-forward" size={13} color={COLORS.textMuted} />
                    </TouchableOpacity>
                  ))}
                </View>
              )}

              <TouchableOpacity style={s.doneBtn} testID="reward-done" onPress={close}>
                <Text style={s.doneText}>Nice!</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}
      </Modal>
    </RewardCtx.Provider>
  );
}

const s = StyleSheet.create({
  backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.55)' },
  wrap: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: SPACING.lg },
  card: {
    width: '100%', maxWidth: 360, backgroundColor: COLORS.bg, borderRadius: RADIUS.xl,
    borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.lg, alignItems: 'center', gap: 8,
  },
  iconWrap: { width: 56, height: 56, borderRadius: 28, backgroundColor: COLORS.gold + '22', alignItems: 'center', justifyContent: 'center' },
  kicker: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 2 },
  pointsRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  points: { color: COLORS.gold, fontSize: FONT.hero, fontWeight: '900' },
  balance: { color: COLORS.textDim, fontSize: FONT.sm },
  ways: { width: '100%', gap: 8, marginTop: 8 },
  waysLabel: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 2 },
  wayRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, borderRadius: RADIUS.md,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  wayTitle: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  wayPts: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '800' },
  doneBtn: { width: '100%', backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 12, alignItems: 'center', marginTop: 10 },
  doneText: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
});
