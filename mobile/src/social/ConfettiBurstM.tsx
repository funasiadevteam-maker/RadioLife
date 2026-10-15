// FUUSIC — lightweight RN Animated confetti burst (no extra dependency).
import React, { useEffect, useRef } from 'react';
import { View, Animated, Easing, Dimensions, StyleSheet } from 'react-native';

const COLORS = ['#a855f7', '#ec4899', '#22c55e', '#f59e0b', '#38bdf8', '#f43f5e'];
const { width, height } = Dimensions.get('window');
const N = 28;

export default function ConfettiBurstM({ onDone }: { onDone?: () => void }) {
  const parts = useRef(Array.from({ length: N }).map(() => new Animated.ValueXY({ x: 0, y: 0 }))).current;
  const opac = useRef(parts.map(() => new Animated.Value(1))).current;

  useEffect(() => {
    const anims = parts.map((p, i) => {
      const angle = Math.random() * Math.PI * 2;
      const dist = 120 + Math.random() * 180;
      return Animated.parallel([
        Animated.timing(p, {
          toValue: { x: Math.cos(angle) * dist, y: Math.sin(angle) * dist + (200 + Math.random() * 140) },
          duration: 1200 + Math.random() * 600, easing: Easing.out(Easing.cubic), useNativeDriver: true,
        }),
        Animated.timing(opac[i], { toValue: 0, duration: 1500, useNativeDriver: true }),
      ]);
    });
    Animated.stagger(8, anims).start(() => onDone && onDone());
  }, []);

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill} testID="confetti-burst">
      {parts.map((p, i) => (
        <Animated.View key={i} style={{
          position: 'absolute', left: width / 2, top: height * 0.38,
          width: 9, height: i % 2 ? 9 : 5, borderRadius: i % 2 ? 5 : 1,
          backgroundColor: COLORS[i % COLORS.length], opacity: opac[i],
          transform: p.getTranslateTransform(),
        }} />
      ))}
    </View>
  );
}
