import React, { useEffect, useRef, useState } from 'react';
import { View, Text, StyleSheet } from 'react-native';
import Animated, {
  useSharedValue, useAnimatedStyle, withRepeat, withTiming, Easing, cancelAnimation,
} from 'react-native-reanimated';
import { Ionicons } from '@expo/vector-icons';
import api from '../api/client';

// Live auto-scrolling "just won" ticker for the games hub.
export default function WinnersTicker() {
  const [items, setItems] = useState<any[]>([]);
  const tx = useSharedValue(0);
  const setW = useRef(0);

  useEffect(() => {
    let alive = true;
    const load = () => api.get('/games/recent-wins', { params: { limit: 20 } })
      .then((r) => { if (alive) setItems(r.data.items || []); })
      .catch(() => {});
    load();
    const t = setInterval(load, 25000);
    return () => { alive = false; clearInterval(t); cancelAnimation(tx); };
  }, []);

  const start = (width: number) => {
    if (!width || setW.current === width) return;
    setW.current = width;
    cancelAnimation(tx);
    tx.value = 0;
    tx.value = withRepeat(
      withTiming(-width, { duration: Math.max(9000, Math.round(width * 16)), easing: Easing.linear }),
      -1, false);
  };

  const style = useAnimatedStyle(() => ({ transform: [{ translateX: tx.value }] }));
  if (!items.length) return null;

  const renderSet = (tag: boolean) => (
    <View style={st.set}
      onLayout={tag ? (e) => start(e.nativeEvent.layout.width) : undefined}>
      {items.map((it, i) => (
        <View key={i} style={st.item} testID={tag ? `winner-item-${i}` : undefined}>
          <Ionicons name="trophy" size={12} color="#fbbf24" />
          <Text style={st.name}>{it.display_name}</Text>
          <Text style={st.won}>won</Text>
          <Text style={st.prize}>{it.prize_label}</Text>
          <Text style={st.game}>on {it.game_label}</Text>
        </View>
      ))}
    </View>
  );

  return (
    <View style={st.wrap} testID="winners-ticker">
      <Animated.View style={[st.row, style]}>
        {renderSet(true)}
        {renderSet(false)}
      </Animated.View>
    </View>
  );
}

const st = StyleSheet.create({
  wrap: {
    overflow: 'hidden', borderRadius: 999, marginTop: 12,
    borderWidth: 1, borderColor: 'rgba(251,191,36,0.25)',
    backgroundColor: 'rgba(28,19,48,0.9)', paddingVertical: 9,
  },
  row: { flexDirection: 'row' },
  set: { flexDirection: 'row', alignItems: 'center', paddingLeft: 16 },
  item: { flexDirection: 'row', alignItems: 'center', gap: 5, marginRight: 24 },
  name: { color: '#fff', fontSize: 12.5, fontWeight: '800' },
  won: { color: '#c4b5fd', fontSize: 12.5 },
  prize: { color: '#fbbf24', fontSize: 12.5, fontWeight: '800' },
  game: { color: '#8b7fb0', fontSize: 12.5 },
});
