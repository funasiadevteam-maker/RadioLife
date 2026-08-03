import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { usePlayerStore } from '../stores/usePlayerStore';
import SafeImage from './SafeImage';
import { COLORS, FONT, SPACING } from '../constants/theme';

/**
 * MiniPlayer — persistent bottom bar showing now-playing station.
 * Rendered in the root layout, above the tab bar.
 * Tap to navigate to full /now-playing screen.
 */
export default function MiniPlayer() {
  const { playing, activeChannelName, activeChannelThumb, currentSeg, setPlaying } = usePlayerStore();
  const router = useRouter();

  // Only show when there's an active channel
  if (!activeChannelName) return null;

  const trackTitle = currentSeg?.track_title || 'Live Radio';
  const trackArtist = currentSeg?.track_artist || activeChannelName;

  return (
    <TouchableOpacity
      testID="mini-player"
      style={s.container}
      activeOpacity={0.9}
      onPress={() => router.push('/now-playing')}
    >
      <SafeImage
        uri={activeChannelThumb}
        fallbackText={activeChannelName || 'FM'}
        size={42}
        borderRadius={10}
      />

      <View style={s.info}>
        <Text style={s.title} numberOfLines={1} testID="mini-player-title">{trackTitle}</Text>
        <Text style={s.artist} numberOfLines={1} testID="mini-player-artist">{trackArtist}</Text>
      </View>

      <TouchableOpacity
        testID="mini-player-toggle"
        style={s.playBtn}
        onPress={(e) => {
          e.stopPropagation?.();
          setPlaying(!playing);
        }}
      >
        <Ionicons name={playing ? 'pause' : 'play'} size={22} color="#fff" />
      </TouchableOpacity>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.card,
    borderTopWidth: 1,
    borderTopColor: COLORS.cardBorder,
    paddingHorizontal: SPACING.md,
    paddingVertical: 10,
    gap: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.06,
    shadowRadius: 4,
    elevation: 4,
  },
  info: { flex: 1 },
  title: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  artist: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 1 },
  playBtn: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
