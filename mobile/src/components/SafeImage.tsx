import React, { useState } from 'react';
import { Image, Text, StyleSheet, ImageProps, ImageURISource } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { RADIUS } from '../constants/theme';

interface SafeImageProps extends Omit<ImageProps, 'source'> {
  uri?: string | null;
  fallbackText?: string;
  size?: number;
  borderRadius?: number;
}

/**
 * SafeImage — gradient + initials fallback when image URL 404s or fails.
 * Matches the web SafeImage contract.
 */
export default function SafeImage({
  uri, fallbackText = '?', size = 48, borderRadius = RADIUS.md, style, ...rest
}: SafeImageProps) {
  const [failed, setFailed] = useState(false);

  if (!uri || failed) {
    const initials = fallbackText
      .split(/[\s-]+/)
      .filter(Boolean)
      .map(w => w[0]?.toUpperCase())
      .slice(0, 2)
      .join('');
    return (
      <LinearGradient
        colors={['#ff2d95', '#c026d3', '#7c3aed']}
        start={{ x: 0, y: 0 }}
        end={{ x: 1, y: 1 }}
        style={[s.fallback, { width: size, height: size, borderRadius }, style]}
        testID="safe-image-fallback"
      >
        <Text style={[s.initials, { fontSize: size * 0.36 }]}>{initials || '?'}</Text>
      </LinearGradient>
    );
  }

  return (
    <Image
      source={{ uri } as ImageURISource}
      onError={() => setFailed(true)}
      style={[{ width: size, height: size, borderRadius }, style]}
      testID="safe-image"
      {...rest}
    />
  );
}

const s = StyleSheet.create({
  fallback: { alignItems: 'center', justifyContent: 'center' },
  initials: { color: '#fff', fontWeight: '900', letterSpacing: 1 },
});
