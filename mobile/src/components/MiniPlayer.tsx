import React from 'react';
import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { usePlayerStore } from '../stores/usePlayerStore';
import { togglePlayback, hasPlayer } from '../services/audioController';
import { nativePlay, nativePause } from '../services/nativePlayerBridge';
import api from '../api/client';
import SafeImage from './SafeImage';
import { COLORS, FONT, SPACING } from '../constants/theme';

/**
 * MiniPlayer — persistent bottom bar showing now-playing station.
 * Rendered in the root layout, above the tab bar.
 * Tap to navigate to full /now-playing screen.
 */
export default function MiniPlayer() {
  const { playing, activeChannelName, activeChannelThumb, activeChannel, currentSeg, setPlaying } = usePlayerStore();
  const router = useRouter();

  // Only show when there's an active channel
  if (!activeChannelName) return null;

  const inviteListen = async (e: any) => {
    e.stopPropagation?.();
    try {
      const content = { id: activeChannel || 'radiolife', name: activeChannelName || 'FUUSIC Radio', favicon: activeChannelThumb || '' };
      const { data } = await api.post('/social/rooms', { visibility: 'public', content_type: 'live', content });
      router.push(`/social/room/${data.room_id}` as any);
    } catch (_) { router.push('/social' as any); }
  };

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

      <TouchableOpacity testID="mini-player-invite" style={{ width: 40, height: 40, alignItems: 'center', justifyContent: 'center' }} onPress={inviteListen}>
        <Ionicons name="people" size={20} color="#fff" />
      </TouchableOpacity>

      <TouchableOpacity
        testID="mini-player-toggle"
        style={s.playBtn}
        onPress={(e) => {
          e.stopPropagation?.();
          if (!hasPlayer()) {
            // No live audio session yet — open the full player to start one.
            router.push('/now-playing');
            return;
          }
          const nowPlaying = togglePlayback();
          setPlaying(nowPlaying);
          if (nowPlaying) nativePlay(); else nativePause();
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
