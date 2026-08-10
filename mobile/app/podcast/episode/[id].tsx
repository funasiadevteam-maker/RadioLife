import { useEffect, useState, useRef, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, Image,
  ActivityIndicator, StyleSheet, Alert, Linking, Pressable,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as WebBrowser from 'expo-web-browser';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../../src/constants/theme';
import {
  getEpisode, getEpisodeMagicClips, getEpisodeShoppableCards,
  episodeAudioUrl, shoppableClickUrl, subscribe, getEpisodeMedia,
} from '../../../src/api/podcastApi';

let AudioModule: any = null;
try { AudioModule = require('expo-audio'); } catch {}
let ExpoVideo: any = null;
try { ExpoVideo = require('expo-video'); } catch {}

function fmtSec(s: number) {
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}:${String(r).padStart(2, '0')}`;
}

function formatPrice(cents: number | null, currency?: string) {
  if (cents == null) return '';
  return `${currency || 'USD'} ${(cents / 100).toFixed(2)}`;
}

export default function EpisodeDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [episode, setEpisode] = useState<any>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [cards, setCards] = useState<any[]>([]);
  const [media, setMedia] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [paywall, setPaywall] = useState<any>(null); // 402 payload
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [dur, setDur] = useState(0);
  const soundRef = useRef<any>(null);
  const [subBusy, setSubBusy] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const ep = await getEpisode(id);
      setEpisode(ep);
      const [mc, sc, md] = await Promise.all([
        getEpisodeMagicClips(id).catch(() => []),
        getEpisodeShoppableCards(id).catch(() => []),
        getEpisodeMedia(id).catch(() => null),
      ]);
      setClips(mc);
      setCards(sc);
      setMedia(md);
    } catch (e: any) {
      if (e?.response?.status === 402) {
        setPaywall(e.response.data);
      } else {
        Alert.alert('Error', e?.response?.data?.detail || 'Could not load episode');
      }
    } finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  // Cleanup audio on unmount
  useEffect(() => {
    return () => { soundRef.current?.remove?.(); };
  }, []);

  const togglePlay = async () => {
    if (!id || !AudioModule) return;
    try {
      if (soundRef.current) {
        if (playing) {
          await soundRef.current.pause();
        } else {
          await soundRef.current.play();
        }
        setPlaying(!playing);
        return;
      }
      const player = AudioModule.useAudioPlayer
        ? null // hook-based — we'll use createAsync
        : null;
      // Use Sound API
      const snd = new AudioModule.Sound();
      await snd.loadAsync({ uri: episodeAudioUrl(id) });
      snd.setOnPlaybackStatusUpdate((status: any) => {
        if (status.isLoaded) {
          setPos(status.positionMillis / 1000);
          setDur(status.durationMillis ? status.durationMillis / 1000 : 0);
          if (status.didJustFinish) setPlaying(false);
        }
      });
      soundRef.current = snd;
      await snd.playAsync();
      setPlaying(true);
    } catch (e: any) {
      // Fallback: just mark as playing for UX; actual audio may not work in web preview
      setPlaying(!playing);
    }
  };

  const seekAudio = useCallback(async (sec: number) => {
    try { await soundRef.current?.setPositionAsync(sec * 1000); setPos(sec); } catch { /* not loaded */ }
  }, []);

  const onSubscribe = async () => {
    if (!paywall?.channel_id) return;
    setSubBusy(true);
    try {
      const data = await subscribe(paywall.channel_id);
      if (data?.checkout_url) {
        await WebBrowser.openBrowserAsync(data.checkout_url);
      }
    } catch (e: any) {
      Alert.alert('Subscribe', e?.response?.data?.detail || 'Failed');
    } finally { setSubBusy(false); }
  };

  const openShoppable = (cardId: string) => {
    Linking.openURL(shoppableClickUrl(cardId));
  };

  if (loading) return (
    <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
  );

  /* ── Paywall overlay ── */
  if (paywall) {
    const plan = paywall.plan || paywall.subscription_plan;
    const dollars = plan?.price_cents ? (plan.price_cents / 100).toFixed(2) : '?';
    return (
      <SafeAreaView style={common.screen} edges={['top']}>
        <TouchableOpacity testID="mobile-episode-back" onPress={() => router.back()} style={st.backBtn}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <View testID="mobile-episode-paywall" style={st.paywallWrap}>
          <View style={st.paywallCard}>
            <Text style={st.paywallLabel}>SUBSCRIBERS ONLY</Text>
            <Text style={st.paywallTitle}>{plan?.plan_name || 'Premium'}</Text>
            <Text style={st.paywallBody}>
              Get this episode + every bonus drop on this channel.
            </Text>
            <View style={st.paywallPriceRow}>
              <Text style={st.paywallPrice}>${dollars}</Text>
              <Text style={st.paywallPer}>/month USD</Text>
            </View>
            {plan?.features?.ad_free && <Text style={st.paywallFeat}>✓ Ad-free listening</Text>}
            {plan?.features?.early_access_hours > 0 && (
              <Text style={st.paywallFeat}>✓ {plan.features.early_access_hours}-hour early access</Text>
            )}
            {plan?.features?.bonus_episodes && <Text style={st.paywallFeat}>✓ Bonus episodes</Text>}
            <TouchableOpacity
              testID="mobile-episode-paywall-subscribe"
              style={st.paywallBtn}
              onPress={onSubscribe}
              disabled={subBusy}
            >
              <Text style={st.paywallBtnText}>
                {subBusy ? 'Opening checkout…' : `Start ${plan?.trial_days || 7}-day free trial`}
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  /* ── Normal episode detail ── */
  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView contentContainerStyle={{ paddingBottom: 60 }}>
        <TouchableOpacity testID="mobile-episode-back" onPress={() => router.back()} style={st.backBtn}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>

        {/* Player area */}
        <View testID="mobile-episode-player" style={st.playerArea}>
          <TouchableOpacity
            testID="mobile-episode-play-btn"
            onPress={togglePlay}
            style={st.playBtn}
            activeOpacity={0.8}
          >
            <Ionicons name={playing ? 'pause' : 'play'} size={40} color="#fff" />
          </TouchableOpacity>
          <Text style={st.epTitle}>{episode?.title}</Text>
          <ChapterScrubber
            pos={pos}
            dur={dur || media?.duration_seconds || 0}
            chapters={media?.chapters || []}
            onSeek={seekAudio}
          />
          {(dur > 0 || media?.duration_seconds) ? (
            <Text style={st.scrubberText}>{fmtSec(pos)} / {fmtSec(dur || media?.duration_seconds || 0)}</Text>
          ) : null}
          {episode?.description ? (
            <Text style={st.epDesc} numberOfLines={6}>{episode.description}</Text>
          ) : null}
        </View>

        {/* Video + chapters + transcript */}
        {media?.video_url ? <EpisodeVideoBlock media={media} /> : null}
        {!media?.video_url && media?.chapters?.length ? (
          <ChaptersBlock chapters={media.chapters}
            onSeek={async (sec: number) => { try { await soundRef.current?.setPositionAsync(sec * 1000); } catch {} }} />
        ) : null}
        {media?.transcript ? <TranscriptBlock transcript={media.transcript} /> : null}

        {/* Shoppable cards */}
        {cards.length > 0 && (
          <View testID="mobile-episode-shoppable" style={st.section}>
            <Text style={common.sectionTitle}>Shop the episode</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {cards.map(c => (
                <TouchableOpacity
                  key={c.id}
                  testID={`mobile-shoppable-tile-${c.id}`}
                  style={st.shopCard}
                  onPress={() => openShoppable(c.id)}
                  activeOpacity={0.7}
                >
                  {c.image_url ? (
                    <Image source={{ uri: c.image_url }} style={st.shopImg} />
                  ) : (
                    <View style={[st.shopImg, st.shopImgPlaceholder]}>
                      <Ionicons name="bag" size={20} color={COLORS.textDim} />
                    </View>
                  )}
                  <Text style={st.shopTitle} numberOfLines={1}>{c.title}</Text>
                  {c.price_cents != null && (
                    <Text style={st.shopPrice}>{formatPrice(c.price_cents, c.currency)}</Text>
                  )}
                  <View style={st.shopBtn}>
                    <Text style={st.shopBtnText}>Shop</Text>
                  </View>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Magic clips */}
        {clips.length > 0 && (
          <View testID="mobile-episode-highlights" style={st.section}>
            <Text style={common.sectionTitle}>Highlights</Text>
            {clips.map(c => (
              <View key={c.id} testID={`mobile-episode-clip-${c.id}`} style={st.clipRow}>
                <View style={{ flex: 1 }}>
                  <Text style={st.clipTitle}>{c.title || 'Untitled'}</Text>
                  <Text style={st.clipMeta}>
                    {fmtSec(c.start_sec || 0)}–{fmtSec(c.end_sec || 0)} · {((c.end_sec || 0) - (c.start_sec || 0)).toFixed(0)}s
                    · score {(c.score || 0).toFixed(2)}
                  </Text>
                </View>
                <Ionicons name="play-circle-outline" size={24} color={COLORS.secondary} />
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function ChapterScrubber({ pos, dur, chapters, onSeek }: {
  pos: number; dur: number;
  chapters: { title: string; start_seconds: number }[];
  onSeek: (sec: number) => void;
}) {
  const [w, setW] = useState(0);
  const hasChapters = chapters.length > 0;
  // Real playback duration drives the fill/thumb; when unknown (e.g. before
  // playback or a seeded episode with duration 0) fall back to the last
  // chapter start so markers still lay out correctly.
  const layoutDur = dur > 0
    ? dur
    : (hasChapters ? Math.max(...chapters.map((c) => c.start_seconds)) * 1.15 + 30 : 0);
  if (layoutDur <= 0) return null;
  const pct = dur > 0 ? Math.min(1, Math.max(0, pos / dur)) : 0;
  return (
    <View style={st.scrubberWrap} testID="mobile-episode-scrubber">
      <Pressable
        style={st.scrubTrack}
        onLayout={(e) => setW(e.nativeEvent.layout.width)}
        onPress={(e) => { if (dur > 0 && w > 0) onSeek((e.nativeEvent.locationX / w) * dur); }}
      >
        <View style={[st.scrubFill, { width: `${pct * 100}%` }]} />
        {chapters.map((c, i) => (
          <TouchableOpacity
            key={`m-${c.start_seconds}-${i}`}
            testID={`mobile-scrubber-marker-${i}`}
            hitSlop={10}
            onPress={() => onSeek(c.start_seconds)}
            style={[st.scrubMarker, { left: `${Math.min(100, Math.max(0, (c.start_seconds / layoutDur) * 100))}%` }]}
          />
        ))}
        {dur > 0 && <View style={[st.scrubThumb, { left: `${pct * 100}%` }]} />}
      </Pressable>
    </View>
  );
}

function ChaptersBlock({ chapters, onSeek }: {
  chapters: { title: string; start_seconds: number }[]; onSeek: (sec: number) => void;
}) {
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  return (
    <View style={st.section} testID="mobile-episode-chapters">
      <Text style={common.sectionTitle}>Chapters</Text>
      {chapters.map((c, i) => (
        <TouchableOpacity key={`${c.start_seconds}-${i}`} style={st.chapterRow}
          onPress={() => onSeek(c.start_seconds)} testID={`mobile-chapter-${i}`}>
          <Text style={st.chapterTime}>{fmt(c.start_seconds)}</Text>
          <Text style={st.chapterTitle} numberOfLines={1}>{c.title}</Text>
          <Ionicons name="play-circle-outline" size={18} color={COLORS.primary} />
        </TouchableOpacity>
      ))}
    </View>
  );
}

function EpisodeVideoBlock({ media }: { media: any }) {
  const player = ExpoVideo?.useVideoPlayer
    ? ExpoVideo.useVideoPlayer(media.video_url, (p: any) => { p.loop = false; })
    : null;
  const chapters: { title: string; start_seconds: number }[] = media.chapters || [];
  const fmt = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
  const seek = (sec: number) => { if (player) { try { player.currentTime = sec; player.play(); } catch { /* noop */ } } };
  const enterPip = () => { if (player) { try { player.startPictureInPicture(); } catch { /* pip unsupported */ } } };

  if (!ExpoVideo?.VideoView || !player) return null;
  const VideoView = ExpoVideo.VideoView;
  return (
    <View style={st.section} testID="mobile-episode-video">
      <VideoView
        player={player}
        style={st.videoPlayer}
        allowsPictureInPicture
        startsPictureInPictureAutomatically={false}
        contentFit="contain"
        nativeControls
      />
      <TouchableOpacity style={st.pipBtn} onPress={enterPip} testID="mobile-episode-pip-btn" activeOpacity={0.8}>
        <Ionicons name="scan-outline" size={16} color={COLORS.primary} />
        <Text style={st.pipText}>Picture-in-Picture</Text>
      </TouchableOpacity>
      <Text style={st.pipHint}>Available on the installed app (not the web preview).</Text>
      {chapters.length > 0 && (
        <View testID="mobile-episode-chapters" style={{ marginTop: SPACING.md }}>
          <Text style={common.sectionTitle}>Chapters</Text>
          {chapters.map((c, i) => (
            <TouchableOpacity key={`${c.start_seconds}-${i}`} style={st.chapterRow}
              onPress={() => seek(c.start_seconds)} testID={`mobile-chapter-${i}`}>
              <Text style={st.chapterTime}>{fmt(c.start_seconds)}</Text>
              <Text style={st.chapterTitle} numberOfLines={1}>{c.title}</Text>
              <Ionicons name="play-circle-outline" size={18} color={COLORS.primary} />
            </TouchableOpacity>
          ))}
        </View>
      )}
    </View>
  );
}

function TranscriptBlock({ transcript }: { transcript: string }) {
  const [open, setOpen] = useState(false);
  return (
    <View style={st.section} testID="mobile-episode-transcript">
      <TouchableOpacity style={st.transcriptToggle} onPress={() => setOpen(!open)} testID="mobile-transcript-toggle">
        <Text style={common.sectionTitle}>Transcript</Text>
        <Ionicons name={open ? 'chevron-up' : 'chevron-down'} size={18} color={COLORS.textDim} />
      </TouchableOpacity>
      {open && <Text style={st.transcriptText}>{transcript}</Text>}
    </View>
  );
}


const st = StyleSheet.create({
  videoPlayer: { width: '100%', aspectRatio: 16 / 9, backgroundColor: '#000', borderRadius: RADIUS.md },
  pipBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: SPACING.sm, paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10' },
  pipText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  pipHint: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', textAlign: 'center', marginTop: 6 },
  chapterRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  chapterTime: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800', width: 44 },
  chapterTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  transcriptToggle: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  transcriptText: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 21, marginTop: 8 },  backBtn: { padding: SPACING.lg },
  playerArea: { alignItems: 'center', paddingHorizontal: SPACING.lg, marginBottom: SPACING.lg },
  playBtn: {
    width: 80, height: 80, borderRadius: 40,
    backgroundColor: COLORS.primary, justifyContent: 'center', alignItems: 'center',
    marginBottom: SPACING.md,
  },
  epTitle: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text, textAlign: 'center', marginBottom: 4 },
  scrubberText: { fontSize: FONT.xs, color: COLORS.textDim, fontVariant: ['tabular-nums'], marginBottom: 8 },
  scrubberWrap: { width: '100%', paddingHorizontal: 4, marginTop: 4, marginBottom: 6 },
  scrubTrack: { height: 6, borderRadius: 3, backgroundColor: COLORS.surfaceBorder, justifyContent: 'center' },
  scrubFill: { position: 'absolute', left: 0, top: 0, bottom: 0, borderRadius: 3, backgroundColor: COLORS.primary },
  scrubMarker: { position: 'absolute', top: -3, width: 3, height: 12, borderRadius: 1.5, marginLeft: -1.5, backgroundColor: COLORS.gold },
  scrubThumb: { position: 'absolute', top: -4, width: 14, height: 14, borderRadius: 7, marginLeft: -7, backgroundColor: COLORS.primary, borderWidth: 2, borderColor: COLORS.card },
  epDesc: { fontSize: FONT.sm, color: COLORS.textDim, lineHeight: 20, textAlign: 'center' },
  section: { paddingHorizontal: SPACING.lg, marginTop: SPACING.lg },
  shopCard: {
    width: 140, padding: 10, borderRadius: RADIUS.sm, marginRight: 10,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  shopImg: { width: '100%', height: 80, borderRadius: 6, marginBottom: 8 },
  shopImgPlaceholder: { backgroundColor: COLORS.surface, justifyContent: 'center', alignItems: 'center' },
  shopTitle: { fontSize: FONT.sm, fontWeight: '600', color: COLORS.text, marginBottom: 2 },
  shopPrice: { fontSize: FONT.xs, color: COLORS.orange, marginBottom: 6 },
  shopBtn: {
    backgroundColor: COLORS.orange, paddingVertical: 4, paddingHorizontal: 10,
    borderRadius: 4, alignSelf: 'flex-start',
  },
  shopBtnText: { fontSize: FONT.xs, fontWeight: '700', color: '#000' },
  clipRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    padding: 10, marginBottom: 6, borderRadius: RADIUS.sm,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  clipTitle: { fontSize: FONT.sm, fontWeight: '600', color: COLORS.text },
  clipMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 2 },
  /* Paywall */
  paywallWrap: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: SPACING.lg },
  paywallCard: {
    width: '100%', maxWidth: 400, padding: 22, borderRadius: 14,
    borderWidth: 1, borderColor: 'rgba(245,158,11,0.4)',
    backgroundColor: '#1e1b3a',
  },
  paywallLabel: { fontSize: 11, color: COLORS.orange, letterSpacing: 0.6, marginBottom: 8 },
  paywallTitle: { fontSize: 22, fontWeight: '800', color: '#fff', marginBottom: 10 },
  paywallBody: { fontSize: 14, color: '#cbd5e1', marginBottom: 18 },
  paywallPriceRow: { flexDirection: 'row', alignItems: 'baseline', gap: 8, marginBottom: 14 },
  paywallPrice: { fontSize: 32, fontWeight: '900', color: '#fff' },
  paywallPer: { fontSize: 13, color: '#94a3b8' },
  paywallFeat: { fontSize: 13, color: '#e2e8f0', lineHeight: 24 },
  paywallBtn: {
    backgroundColor: COLORS.orange, paddingVertical: 12, paddingHorizontal: 18,
    borderRadius: 8, alignItems: 'center', marginTop: 18,
  },
  paywallBtnText: { fontWeight: '800', fontSize: 14, color: '#0a0a0c' },
});
