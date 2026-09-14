import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADIUS, FONT } from '../constants/theme';

/* P1 — mobile "N coupons left today" scarcity pill with a live countdown
   to the daily UTC-midnight reset. Mirrors the web CouponScarcityStrip. */

function useCountdown(resetsAt?: string | null): string {
  const [left, setLeft] = useState('');
  useEffect(() => {
    if (!resetsAt) return;
    const target = new Date(resetsAt).getTime();
    const tick = () => {
      const diff = Math.max(0, target - Date.now());
      const h = Math.floor(diff / 3.6e6);
      const m = Math.floor((diff % 3.6e6) / 6e4);
      const s = Math.floor((diff % 6e4) / 1000);
      const p = (n: number) => String(n).padStart(2, '0');
      setLeft(`${p(h)}:${p(m)}:${p(s)}`);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [resetsAt]);
  return left;
}

export default function CouponScarcityStrip({
  remaining, resetsAt, accent = '#0aa54b', testID = 'scarcity-strip',
}: {
  remaining: number | null | undefined;
  resetsAt?: string | null;
  accent?: string;
  testID?: string;
}) {
  const countdown = useCountdown(resetsAt);
  const unlimited = remaining === null || remaining === undefined;
  const soldOut = !unlimited && (remaining as number) <= 0;
  const color = soldOut ? COLORS.textMuted : accent;
  return (
    <View
      testID={testID}
      style={[st.pill, {
        backgroundColor: soldOut ? 'rgba(148,163,184,0.15)' : accent + '22',
        borderColor: soldOut ? 'rgba(148,163,184,0.4)' : accent + '66',
      }]}
    >
      {unlimited ? (
        <View style={st.row}>
          <Ionicons name="infinite" size={14} color={color} />
          <Text style={[st.txt, { color }]}>Unlimited today</Text>
        </View>
      ) : soldOut ? (
        <View style={st.row} testID={`${testID}-soldout`}>
          <Ionicons name="time-outline" size={14} color={color} />
          <Text style={[st.txt, { color }]}>All claimed · resets {countdown}</Text>
        </View>
      ) : (
        <View style={st.row}>
          <Ionicons name="flame" size={14} color={color} />
          <Text style={[st.txt, { color }]} testID={`${testID}-count`}>
            {(remaining as number).toLocaleString()} left today
          </Text>
          <Text style={{ color, opacity: 0.4 }}>·</Text>
          <Ionicons name="time-outline" size={12} color={color} />
          <Text style={[st.mono, { color }]} testID={`${testID}-countdown`}>{countdown}</Text>
        </View>
      )}
    </View>
  );
}

const st = StyleSheet.create({
  pill: {
    alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, borderWidth: 1,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  txt: { fontSize: FONT.sm, fontWeight: '800' },
  mono: { fontSize: FONT.sm, fontWeight: '800', fontVariant: ['tabular-nums'] },
});
