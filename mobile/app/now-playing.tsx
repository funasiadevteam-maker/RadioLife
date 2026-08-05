import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { usePlayerStore } from '../src/stores/usePlayerStore';
import { togglePlayback, releaseCurrent } from '../src/services/audioController';
import { nativePlay, nativePause } from '../src/services/nativePlayerBridge';
import SafeImage from '../src/components/SafeImage';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';

export default function NowPlayingScreen() {
  const router = useRouter();
  const {
    playing, activeChannelName, activeChannelThumb, activeChannel,
    currentSeg, setPlaying, history, skipUsed, skipLimit,
    setActiveChannel, setCurrentSeg, setSession,
  } = usePlayerStore();

  const title = currentSeg?.track_title || 'Live Radio';
  const artist = currentSeg?.track_artist || activeChannelName || 'RadioLife';
  const rjName = currentSeg?.rj_voice_name || currentSeg?.rj_hosts?.[0]?.name;

  const togglePlay = () => {
    const nowPlaying = togglePlayback();
    setPlaying(nowPlaying);
    if (nowPlaying) nativePlay(); else nativePause();
  };

  const stop = () => {
    releaseCurrent();
    nativePause();
    setPlaying(false);
    setSession(null);
    setCurrentSeg(null);
    setActiveChannel(null, null, null);
    router.back();
  };

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={s.scroll}>
        {/* Close bar */}
        <TouchableOpacity testID="now-playing-close" onPress={() => router.back()} style={s.closeBtn}>
          <Ionicons name="chevron-down" size={24} color={COLORS.textDim} />
        </TouchableOpacity>

        {/* Artwork */}
        <View style={s.artworkWrap}>
          <SafeImage
            uri={activeChannelThumb}
            fallbackText={activeChannelName || 'FM'}
            size={220}
            borderRadius={RADIUS.xl}
            style={s.artwork}
          />
        </View>

        {/* Track info */}
        <Text testID="now-playing-title" style={s.title} numberOfLines={2}>{title}</Text>
        <Text testID="now-playing-artist" style={s.artist} numberOfLines={1}>{artist}</Text>
        {rjName && (
          <View style={s.rjBadge}>
            <Ionicons name="mic" size={12} color={COLORS.primary} />
            <Text style={s.rjText}>RJ {rjName}</Text>
          </View>
        )}

        {/* Channel label */}
        <View testID="now-playing-channel" style={s.channelPill}>
          <View style={s.liveDot} />
          <Text style={s.channelLabel}>{activeChannelName || activeChannel || 'LIVE'}</Text>
        </View>

        {/* Transport controls */}
        <View style={s.controls}>
          <TouchableOpacity testID="now-playing-skip-back" style={s.ctrlBtn}>
            <Ionicons name="play-skip-back" size={24} color={COLORS.textDim} />
          </TouchableOpacity>
          <TouchableOpacity
            testID="now-playing-play-pause"
            style={s.playBtn}
            onPress={togglePlay}
          >
            <Ionicons name={playing ? 'pause' : 'play'} size={30} color="#fff" />
          </TouchableOpacity>
          <TouchableOpacity testID="now-playing-skip-fwd" style={s.ctrlBtn}>
            <Ionicons name="play-skip-forward" size={24} color={COLORS.textDim} />
          </TouchableOpacity>
        </View>

        {/* Stop */}
        <TouchableOpacity testID="now-playing-stop" style={s.stopBtn} onPress={stop}>
          <Ionicons name="stop" size={16} color={COLORS.red} />
          <Text style={s.stopText}>Stop</Text>
        </TouchableOpacity>

        {/* Skip counter */}
        <Text style={s.skipText}>
          {skipUsed} / {skipLimit} skips used
        </Text>

        {/* History */}
        {history.length > 0 && (
          <View style={s.historySection}>
            <Text style={common.sectionTitle}>RECENTLY PLAYED</Text>
            {history.slice().reverse().map((seg, i) => (
              <View key={seg.segment_id + i} testID={`history-item-${i}`} style={s.histRow}>
                <Ionicons name="musical-note" size={14} color={COLORS.textMuted} />
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={s.histTitle} numberOfLines={1}>{seg.track_title || 'Track'}</Text>
                  <Text style={s.histArtist} numberOfLines={1}>{seg.track_artist || '—'}</Text>
                </View>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { alignItems: 'center', padding: SPACING.xl, paddingBottom: 60 },
  closeBtn: { alignSelf: 'center', padding: 8, marginBottom: SPACING.lg },
  artworkWrap: {
    marginBottom: SPACING.xl,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.12,
    shadowRadius: 16,
    elevation: 8,
  },
  artwork: {},
  title: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, textAlign: 'center' },
  artist: { fontSize: FONT.lg, color: COLORS.textDim, marginTop: 4, textAlign: 'center' },
  rjBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 8,
    backgroundColor: 'rgba(242,107,42,0.08)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: RADIUS.full,
  },
  rjText: { fontSize: FONT.xs, color: COLORS.primary, fontWeight: '700' },
  channelPill: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: SPACING.lg,
    backgroundColor: COLORS.inputBg, paddingHorizontal: 14, paddingVertical: 6, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.inputBorder,
  },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.green },
  channelLabel: { fontSize: FONT.xs, fontWeight: '800', color: COLORS.text, letterSpacing: 1.5, textTransform: 'uppercase' },
  controls: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 32, marginTop: SPACING.xl,
  },
  ctrlBtn: { padding: 10, opacity: 0.7 },
  playBtn: {
    width: 72, height: 72, borderRadius: 36, backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
    shadowColor: COLORS.primary, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 8, elevation: 6,
  },
  skipText: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: SPACING.md },
  stopBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: SPACING.lg,
    paddingHorizontal: 20, paddingVertical: 10, borderRadius: RADIUS.full,
    borderWidth: 1.5, borderColor: COLORS.red,
  },
  stopText: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '800' },
  historySection: { width: '100%', marginTop: SPACING.xl },
  histRow: {
    flexDirection: 'row', alignItems: 'center', paddingVertical: 10,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder,
  },
  histTitle: { fontSize: FONT.md, fontWeight: '600', color: COLORS.text },
  histArtist: { fontSize: FONT.xs, color: COLORS.textMuted, marginTop: 1 },
});
