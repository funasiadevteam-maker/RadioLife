import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  Modal, TextInput, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { usePlayerStore } from '../src/stores/usePlayerStore';
import { togglePlayback, releaseCurrent } from '../src/services/audioController';
import { nativePlay, nativePause } from '../src/services/nativePlayerBridge';
import SafeImage from '../src/components/SafeImage';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';

export default function NowPlayingScreen() {
  const router = useRouter();
  const {
    playing, activeChannelName, activeChannelThumb, activeChannel,
    currentSeg, setPlaying, history, skipUsed, skipLimit,
    setActiveChannel, setCurrentSeg, setSession,
  } = usePlayerStore();

  const title = currentSeg?.track_title || 'Live Radio';
  const artist = currentSeg?.track_artist || activeChannelName || 'FUUSIC';
  const rjName = currentSeg?.rj_voice_name || currentSeg?.rj_hosts?.[0]?.name;

  const slug = activeChannel || currentSeg?.channel_slug || '';
  const segUrl = currentSeg?.segment_url || '';
  const [following, setFollowing] = useState(false);
  const [followBusy, setFollowBusy] = useState(false);
  const [clipOpen, setClipOpen] = useState(false);
  const [comment, setComment] = useState('');
  const [visibility, setVisibility] = useState<'public' | 'friends'>('public');
  const [clipBusy, setClipBusy] = useState(false);
  const [clipDone, setClipDone] = useState(false);
  const [clipErr, setClipErr] = useState<string | null>(null);

  useEffect(() => {
    if (!slug) { setFollowing(false); return; }
    let on = true;
    api.get(`/radio/channels/${encodeURIComponent(slug)}/follow-status`)
      .then((r) => { if (on) setFollowing(!!r.data?.following); })
      .catch(() => { if (on) setFollowing(false); });
    return () => { on = false; };
  }, [slug]);

  const toggleFollow = async () => {
    if (!slug || followBusy) return;
    setFollowBusy(true);
    const next = !following;
    setFollowing(next);
    try {
      await api.post(`/radio/channels/${encodeURIComponent(slug)}/${next ? 'follow' : 'unfollow'}`,
        { channel_name: activeChannelName, channel_logo: activeChannelThumb });
    } catch { setFollowing(!next); }
    finally { setFollowBusy(false); }
  };

  const openClip = () => {
    setClipDone(false); setClipErr(null); setComment(''); setVisibility('public'); setClipOpen(true);
  };
  const shareClip = async () => {
    if (!segUrl) return;
    setClipBusy(true); setClipErr(null);
    try {
      await api.post('/radio/clips/share-segment', {
        channel_slug: slug, channel_name: activeChannelName, channel_logo: activeChannelThumb,
        segment_audio_url: segUrl, comment: comment.trim(), visibility,
        duration_seconds: 30, idempotency_key: `segclip_${Date.now()}`,
      });
      setClipDone(true);
      setTimeout(() => setClipOpen(false), 1100);
    } catch (e: any) {
      setClipErr(e?.response?.data?.detail?.message || "Couldn't share your clip — try again.");
    } finally { setClipBusy(false); }
  };

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
        {/* Top bar — close + Follow show */}
        <View style={s.topBar}>
          <TouchableOpacity testID="now-playing-close" onPress={() => router.back()} style={s.topBtn}>
            <Ionicons name="chevron-down" size={24} color={COLORS.textDim} />
          </TouchableOpacity>
          <TouchableOpacity testID="now-playing-follow-btn" onPress={toggleFollow}
            disabled={followBusy || !slug} style={[s.followBtn, following && s.followBtnOn]}>
            <Ionicons name={following ? 'heart' : 'heart-outline'} size={15}
              color={following ? '#fff' : COLORS.primary} />
            <Text style={[s.followTxt, following && s.followTxtOn]}>
              {following ? 'Following' : 'Follow'}
            </Text>
          </TouchableOpacity>
        </View>

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

        {/* Clip last 30s — FUUSIC-owned audio */}
        <TouchableOpacity testID="now-playing-clip-btn" onPress={openClip} disabled={!segUrl}
          style={[s.clipBtn, !segUrl && { opacity: 0.5 }]}>
          <Ionicons name="cut-outline" size={16} color={COLORS.primary} />
          <Text style={s.clipBtnTxt}>Clip last 30s</Text>
        </TouchableOpacity>

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

      <Modal visible={clipOpen} transparent animationType="slide" onRequestClose={() => setClipOpen(false)}>
        <View style={s.modalBackdrop}>
          <View style={s.modalCard}>
            <View style={s.modalHead}>
              <Text style={s.modalTitle}>Clip a Moment</Text>
              <TouchableOpacity testID="np-clip-close" onPress={() => setClipOpen(false)} style={s.modalClose}>
                <Ionicons name="close" size={20} color={COLORS.textDim} />
              </TouchableOpacity>
            </View>
            {clipDone ? (
              <View style={s.clipDone} testID="np-clip-done">
                <Ionicons name="checkmark-circle" size={44} color={COLORS.primary} />
                <Text style={s.clipDoneTxt}>Clip shared to your wall!</Text>
              </View>
            ) : (
              <>
                <Text style={s.clipSub}>
                  The last 30 seconds you just heard on {activeChannelName || 'FUUSIC'}.
                </Text>
                <TextInput testID="np-clip-comment" value={comment} onChangeText={setComment}
                  placeholder="Say something about this moment…" placeholderTextColor={COLORS.textMuted}
                  multiline style={s.clipInput} />
                <View style={s.visRow}>
                  {(['public', 'friends'] as const).map((k) => (
                    <TouchableOpacity key={k} testID={`np-clip-vis-${k}`} onPress={() => setVisibility(k)}
                      style={[s.visChip, visibility === k && s.visChipOn]}>
                      <Ionicons name={k === 'public' ? 'globe-outline' : 'people-outline'} size={14}
                        color={visibility === k ? '#fff' : COLORS.textDim} />
                      <Text style={[s.visTxt, visibility === k && s.visTxtOn]}>
                        {k === 'public' ? 'Public' : 'Friends'}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
                {clipErr && <Text style={s.clipErr} testID="np-clip-error">{clipErr}</Text>}
                <TouchableOpacity testID="np-clip-submit" onPress={shareClip} disabled={clipBusy || !segUrl}
                  style={[s.clipSubmit, (clipBusy || !segUrl) && { opacity: 0.6 }]}>
                  {clipBusy ? <ActivityIndicator color="#fff" /> : (
                    <>
                      <Ionicons name="cut-outline" size={16} color="#fff" />
                      <Text style={s.clipSubmitTxt}>Share to My Wall</Text>
                    </>
                  )}
                </TouchableOpacity>
              </>
            )}
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { alignItems: 'center', padding: SPACING.xl, paddingBottom: 60 },
  closeBtn: { alignSelf: 'center', padding: 8, marginBottom: SPACING.lg },
  topBar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', width: '100%', marginBottom: SPACING.lg },
  topBtn: { padding: 8 },
  followBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 14, height: 36, borderRadius: RADIUS.full, borderWidth: 1.5, borderColor: COLORS.primary, backgroundColor: 'transparent' },
  followBtnOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  followTxt: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  followTxtOn: { color: '#fff' },
  clipBtn: { flexDirection: 'row', alignItems: 'center', gap: 7, marginTop: SPACING.lg, paddingHorizontal: 18, paddingVertical: 10, borderRadius: RADIUS.full, backgroundColor: 'rgba(242,107,42,0.10)' },
  clipBtnTxt: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(10,8,20,0.6)', justifyContent: 'flex-end' },
  modalCard: { backgroundColor: COLORS.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: SPACING.xl, paddingBottom: 36 },
  modalHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: SPACING.md },
  modalTitle: { fontSize: FONT.xl, fontWeight: '900', color: COLORS.text },
  modalClose: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  clipSub: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  clipInput: { minHeight: 70, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.lg, padding: 12, color: COLORS.text, fontSize: FONT.md, textAlignVertical: 'top', marginBottom: SPACING.md, backgroundColor: COLORS.inputBg },
  visRow: { flexDirection: 'row', gap: 10, marginBottom: SPACING.md },
  visChip: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.inputBorder, backgroundColor: COLORS.inputBg },
  visChipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  visTxt: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  visTxtOn: { color: '#fff' },
  clipErr: { color: COLORS.red, fontSize: FONT.sm, marginBottom: 8 },
  clipSubmit: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 7, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 14 },
  clipSubmitTxt: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  clipDone: { alignItems: 'center', paddingVertical: 30, gap: 10 },
  clipDoneTxt: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
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
