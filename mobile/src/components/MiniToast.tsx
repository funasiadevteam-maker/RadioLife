import React, { useEffect, useRef } from 'react';
import { Animated, StyleSheet, Text } from 'react-native';

// Lightweight, transient toast for share/points feedback on mobile.
export default function MiniToast({ message, onDone }: { message?: string | null; onDone?: () => void }) {
  const op = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (!message) return;
    Animated.timing(op, { toValue: 1, duration: 180, useNativeDriver: true }).start();
    const t = setTimeout(() => {
      Animated.timing(op, { toValue: 0, duration: 220, useNativeDriver: true })
        .start(() => onDone && onDone());
    }, 1900);
    return () => clearTimeout(t);
  }, [message]);
  if (!message) return null;
  return (
    <Animated.View pointerEvents="none" style={[styles.wrap, { opacity: op }]} testID="mini-toast">
      <Text style={styles.txt}>{message}</Text>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    position: 'absolute', bottom: 96, alignSelf: 'center',
    backgroundColor: '#4c1d95', borderColor: 'rgba(255,255,255,0.15)', borderWidth: 1,
    borderRadius: 22, paddingHorizontal: 18, paddingVertical: 11,
  },
  txt: { color: '#fff', fontWeight: '800', fontSize: 13 },
});
