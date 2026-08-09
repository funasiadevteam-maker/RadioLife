// Phase RWD.3 — reusable contextual Premium cue (mobile).
import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import { fetchPremiumStatus, PremiumStatus } from '../api/premiumApi';

const MESSAGES: Record<string, string> = {
  listen: 'Enjoy radio without platform audio ads.',
  rewards: 'Premium members earn boosted reward points.',
  games: 'Premium unlocks extra daily game entries.',
  default: 'Fewer ads · more AI · extra rewards',
};

export default function PremiumCue({ context = 'default' }: { context?: string }) {
  const router = useRouter();
  const [data, setData] = useState<PremiumStatus | null>(null);

  useEffect(() => {
    let cancel = false;
    fetchPremiumStatus().then((d) => { if (!cancel) setData(d); }).catch(() => {});
    return () => { cancel = true; };
  }, []);

  if (!data || data.is_premium) return null;
  let msg = MESSAGES[context] || MESSAGES.default;
  if (context === 'rewards' && data.points_multiplier > 1) {
    msg = `Premium members earn ${data.points_multiplier}× reward points.`;
  }

  return (
    <TouchableOpacity style={s.wrap} testID={`premium-cue-${context}`}
      onPress={() => router.push('/premium' as any)} activeOpacity={0.85}>
      <Ionicons name="sparkles" size={16} color={COLORS.purple} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.title}>Get more with Premium</Text>
        <Text style={s.sub} numberOfLines={1}>{msg}</Text>
      </View>
      <Ionicons name="chevron-forward" size={15} color={COLORS.purple} />
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  wrap: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: SPACING.md,
    borderRadius: RADIUS.lg, backgroundColor: COLORS.purple + '12',
    borderWidth: 1, borderColor: COLORS.purple + '33', marginBottom: SPACING.md,
  },
  title: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  sub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
});
