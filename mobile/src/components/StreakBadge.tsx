import React, { useEffect, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api/client';

// Daily-play streak flame for the games hub.
export default function StreakBadge({ refreshKey = 0 }: { refreshKey?: number }) {
  const [s, setS] = useState<any>(null);

  useEffect(() => {
    let alive = true;
    api.get('/games/streak')
      .then((r) => { if (alive) setS(r.data); })
      .catch(() => {});
    return () => { alive = false; };
  }, [refreshKey]);

  if (!s) return null;
  const n = s.current_streak || 0;
  const hot = n > 0;

  return (
    <View
      style={[st.wrap, {
        borderColor: hot ? 'rgba(251,146,60,0.5)' : 'rgba(255,255,255,0.12)',
        backgroundColor: hot ? 'rgba(251,146,60,0.14)' : 'rgba(255,255,255,0.05)',
      }]}
      testID="streak-badge"
    >
      <Ionicons name="flame" size={18} color={hot ? '#fb923c' : '#64748b'} />
      <View>
        <Text style={st.count} testID="streak-count">{n}-day streak</Text>
        <Text style={st.sub}>
          {s.claim_available ? `Play today for +${s.pending_bonus_points} pts` : 'Bonus claimed today'}
        </Text>
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  wrap: {
    flexDirection: 'row', alignItems: 'center', gap: 10, alignSelf: 'flex-start',
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1, marginTop: 12,
  },
  count: { color: '#fff', fontSize: 13, fontWeight: '900' },
  sub: { color: '#c4b5fd', fontSize: 10.5 },
});
