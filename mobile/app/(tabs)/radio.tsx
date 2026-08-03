import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ActivityIndicator, ScrollView,
  Alert, SafeAreaView,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/contexts/AuthContext';
import api, { radioApi, BACKEND } from '../../src/api/client';
import { COLORS, SPACING, RADIUS, FONT } from '../../src/constants/theme';
import ChannelSwitcher from '../../src/components/ChannelSwitcher';
import { useGateStore } from '../../src/stores/gateStore';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { updateNowPlaying, nativePlay, nativePause, subscribeRemoteEvents } from '../../src/services/nativePlayerBridge';

let createAudioPlayer: any;
try {
  const mod = require('expo-audio');
  createAudioPlayer = mod.createAudioPlayer;
} catch {}

const fmt = (s: number) => {
  if (!isFinite(s) || s < 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
};
const fmtCountdown = (s: number) => {
  if (!isFinite(s) || s <= 0) return '0:00';
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
};

export default function RadioScreen() {
  const { user, loading: authLoading, logout } = useAuth();
  const router = useRouter();
  const params = useLocalSearchParams<{ channel?: string }>();
  const openGate = useGateStore((s) => s.openGate);

  // Global player store
  const store = usePlayerStore();
  const {
    sessionId, channels, activeChannel, currentSeg, history,
    playing, currentTime, duration, skipUsed, skipLimit, skipResetIn,
    setSession, setChannels, setActiveChannel, setCurrentSeg, pushHistory,
    setPlaying, setCurrentTime, setDuration, setSkipState,
  } = store;

  const [switching, setSwitching] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [advancing, setAdvancing] = useState(false);
  const [skipCountdown, setSkipCountdown] = useState(0);

  const playerRef = useRef<any>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const endFiredRef = useRef(false);
  const sessionRef = useRef<string | null>(null);

  /* ── Auth guard ── */
  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
    if (!user.onboarding_complete) { router.replace('/onboarding'); return; }
  }, [user, authLoading]);

  /* ── Fetch channels ── */
  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/channels');
        const chs = r.data.channels || [];
        setChannels(chs);
        if (!activeChannel) setActiveChannel(r.data.default);
      } catch {}
    })();
  }, []);

  /* ── Deep-link channel param ── */
  useEffect(() => {
    if (params.channel && channels.length > 0) {
      setActiveChannel(params.channel);
    }
  }, [params.channel, channels]);

  useEffect(() => { sessionRef.current = sessionId; }, [sessionId]);

  /* ── Lock-screen remote events ── */
  useEffect(() => {
    const cleanup = subscribeRemoteEvents(
      () => { try { playerRef.current?.play?.(); setPlaying(true); nativePlay(); } catch {} },
      () => { try { playerRef.current?.pause?.(); setPlaying(false); nativePause(); } catch {} },
      () => { skip(); },
    );
    return () => cleanup?.();
  }, []);

  /* ── BigCoin heartbeat ── */
  useEffect(() => {
    if (!user || !sessionId) return;
    const id = setInterval(async () => {
      try {
        if (playing) await api.post('/bigcoin/heartbeat', { session_id: sessionRef.current });
      } catch {}
    }, 60000);
    return () => clearInterval(id);
  }, [user, sessionId, playing]);

  /* ── Audio cleanup on unmount ── */
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
      try { playerRef.current?.release?.(); } catch {}
    };
  }, []);

  /* ── Skip countdown ticker ── */
  useEffect(() => {
    if (skipResetIn <= 0) { setSkipCountdown(0); return; }
    setSkipCountdown(skipResetIn);
    const t0 = Date.now();
    const id = setInterval(() => {
      const elapsed = Math.floor((Date.now() - t0) / 1000);
      const left = Math.max(0, skipResetIn - elapsed);
      setSkipCountdown(left);
      if (left <= 0) {
        clearInterval(id);
        refreshSkipState();
      }
    }, 1000);
    return () => clearInterval(id);
  }, [skipResetIn]);

  const refreshSkipState = async () => {
    try {
      const r = await radioApi.get('/radio/skip_state');
      setSkipState(r.data.used, r.data.limit, r.data.reset_in_sec || 0);
    } catch {}
  };

  const applySkipState = (ss: any) => {
    if (!ss) return;
    setSkipState(ss.used, ss.limit, ss.reset_in_sec || 0);
  };

  /* ── Resolve channel metadata for Now Playing ── */
  const getChannelMeta = (slug: string | null) => {
    const ch = channels.find((c: any) => c.slug === slug);
    return {
      name: ch?.name || 'BigFM Radio',
      thumb: ch?.thumbnail_url || null,
    };
  };

  /* ── Play a segment using expo-audio + push to lock-screen ── */
  const playSegment = async (seg: any) => {
    if (pollRef.current) clearInterval(pollRef.current);
    try { playerRef.current?.release?.(); } catch {}
    playerRef.current = null;
    endFiredRef.current = false;

    if (!createAudioPlayer) {
      Alert.alert('Audio Error', 'Audio module not available');
      return;
    }

    try {
      const url = `${BACKEND}${seg.segment_url}`;
      const player = createAudioPlayer(url);
      playerRef.current = player;
      player.play();
      setPlaying(true);

      // Push lock-screen metadata (native only, no-op on web)
      const chMeta = getChannelMeta(seg.channel_slug || activeChannel);
      updateNowPlaying(
        url,
        seg.track_title || 'Now playing',
        seg.track_artist || 'BigFM',
        chMeta.name,           // dynamic — never hardcoded "Dubai"
        chMeta.thumb,
      );

      pollRef.current = setInterval(() => {
        const p = playerRef.current;
        if (!p) return;
        try {
          const ct = p.currentTime || 0;
          const dur = p.duration || 0;
          const isPlaying = p.playing ?? false;
          setCurrentTime(ct);
          setDuration(dur);
          setPlaying(isPlaying);

          if (dur > 1 && ct >= dur - 0.3 && !isPlaying && !endFiredRef.current) {
            endFiredRef.current = true;
            handleSegmentEnd();
          }
        } catch {}
      }, 300);
    } catch {
      Alert.alert('Audio Error', 'Could not play segment');
    }
  };

  /* ── Segment end → auto-advance ── */
  const handleSegmentEnd = async () => {
    setAdvancing(true);
    try {
      const r = await radioApi.get('/radio/next', { params: { session_id: sessionRef.current } });
      applySkipState(r.data.skip_state);
      const seg = r.data.segment;
      if (seg) {
        setCurrentSeg(seg);
        pushHistory(seg);
        await playSegment(seg);
      }
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not get next segment');
    }
    setAdvancing(false);
  };

  /* ── Start radio ── */
  const startRadio = async () => {
    if (starting || sessionId) return;
    setStarting(true);
    try {
      const body = { channel: activeChannel };
      const r = await radioApi.post('/radio/start', body);
      setSession(r.data.session_id);
      sessionRef.current = r.data.session_id;
      applySkipState(r.data.skip_state);
      const seg = r.data.segment;
      setCurrentSeg(seg);
      pushHistory(seg);
      if (seg.channel_slug) {
        const ch = channels.find((c: any) => c.slug === seg.channel_slug);
        setActiveChannel(seg.channel_slug, ch?.name, ch?.thumbnail_url);
      }
      await playSegment(seg);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const code = detail?.code;
      if (e?.response?.status === 403 && code) {
        openGate(detail, { slug: detail.channel, name: detail.channel_name });
      } else {
        Alert.alert('Error', typeof detail === 'string' ? detail : 'Could not start radio');
      }
    } finally { setStarting(false); }
  };

  /* ── Play / Pause ── */
  const togglePlay = () => {
    const p = playerRef.current;
    if (!p) return;
    try {
      if (p.playing) { p.pause(); setPlaying(false); nativePause(); }
      else { p.play(); setPlaying(true); nativePlay(); }
    } catch {}
  };

  /* ── Skip ── */
  const skip = async () => {
    if (advancing || !sessionId) return;
    setAdvancing(true);
    try { playerRef.current?.pause?.(); } catch {}
    try {
      const r = await radioApi.post('/radio/skip', null, { params: { session_id: sessionId } });
      applySkipState(r.data.skip_state);
      const seg = r.data.segment;
      setCurrentSeg(seg);
      pushHistory(seg);
      await playSegment(seg);
    } catch (e: any) {
      if (e?.response?.status === 429) {
        const d = e.response.data || {};
        const retry = d.retry_after_sec || 0;
        setSkipState(d.used || skipLimit, skipLimit, retry);
        Alert.alert(
          'Skip limit reached',
          `Slow down, DJ — you have hit your skip limit. Try again in ${fmtCountdown(retry)}.\n\nGo Premium for unlimited skips.`
        );
        try { playerRef.current?.play?.(); setPlaying(true); } catch {}
      } else {
        Alert.alert('Error', e?.response?.data?.detail || 'Could not skip');
      }
    } finally { setAdvancing(false); }
  };

  /* ── Switch channel ── */
  const switchChannel = async (slug: string) => {
    if (!sessionId) { setActiveChannel(slug); return; }
    if (switching || slug === activeChannel) return;
    setSwitching(slug);
    try { playerRef.current?.pause?.(); } catch {}
    try {
      const r = await api.post('/radio/switch_channel', { session_id: sessionId, channel: slug });
      applySkipState(r.data.skip_state);
      const ch = channels.find((c: any) => c.slug === (r.data.channel_slug || slug));
      setActiveChannel(r.data.channel_slug || slug, ch?.name, ch?.thumbnail_url);

      if (r.data.tuning_sfx_url && createAudioPlayer) {
        if (pollRef.current) clearInterval(pollRef.current);
        try { playerRef.current?.release?.(); } catch {}
        const sfx = createAudioPlayer(`${BACKEND}${r.data.tuning_sfx_url}`);
        playerRef.current = sfx;
        sfx.play();
      }

      const poll = setInterval(async () => {
        try {
          const rr = await api.get('/radio/ready', { params: { session_id: sessionId } });
          if (rr.data.ready && rr.data.segment) {
            clearInterval(poll);
            const seg = rr.data.segment;
            applySkipState(rr.data.skip_state);
            setCurrentSeg(seg);
            pushHistory(seg);
            await playSegment(seg);
            setSwitching(null);
          }
        } catch {}
      }, 1500);
      setTimeout(() => { clearInterval(poll); setSwitching(null); }, 60000);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 403 && detail?.code) {
        openGate(detail, { slug: detail.channel, name: detail.channel_name });
      } else {
        Alert.alert('Error', typeof detail === 'string' ? detail : 'Could not switch');
      }
      setSwitching(null);
    }
  };

  const doLogout = async () => {
    try { playerRef.current?.pause?.(); } catch {}
    store.reset();
    await logout();
    router.replace('/login');
  };
  const skipRemaining = Math.max(0, skipLimit - skipUsed);
  const skipExhausted = skipUsed >= skipLimit;
  const inRJ = currentSeg && currentTime >= (currentSeg.rj_start_sec || Infinity);
  const isDuo = currentSeg?.rj_format === 'duo';
  const duoLabel = isDuo && currentSeg?.rj_hosts?.length >= 2
    ? `${currentSeg.rj_hosts[0].name} × ${currentSeg.rj_hosts[1].name}` : null;

  if (authLoading || !user) {
    return <View style={s.center} testID="radio-loading"><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={s.screen}>
      <ScrollView contentContainerStyle={s.scrollContent}>
        {/* Header */}
        <View style={s.header} testID="radio-header">
          <View style={s.brandRow}>
            <View style={s.dot} />
            <Text style={s.brandName} testID="brand-bigfm">BigFM <Text style={s.brandDxb}>Dubai</Text></Text>
          </View>
          <View style={s.headerRight}>
            <TouchableOpacity onPress={() => router.push('/channels')} testID="nav-channels" style={s.headerBtn}>
              <Ionicons name="grid" size={18} color={COLORS.textDim} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => router.push('/lobbies')} testID="nav-lobbies" style={s.headerBtn}>
              <Ionicons name="people" size={18} color={COLORS.textDim} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => router.push('/play-and-win')} testID="nav-play-and-win" style={s.headerBtn}>
              <Ionicons name="game-controller" size={18} color={COLORS.textDim} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => router.push('/commute')} testID="nav-commute" style={s.headerBtn}>
              <Ionicons name="car-outline" size={18} color={COLORS.textDim} />
            </TouchableOpacity>
            <TouchableOpacity onPress={doLogout} testID="menu-logout-btn" style={s.headerBtn}>
              <Ionicons name="log-out" size={18} color={COLORS.textDim} />
            </TouchableOpacity>
          </View>
        </View>

        <Text style={s.tagline} testID="radio-tag">DIL SE · DUBAI SE</Text>

        {/* Channel Switcher Strip */}
        {channels.length > 0 && (
          <ChannelSwitcher
            channels={channels}
            activeSlug={activeChannel}
            switching={switching}
            isPremium={!!user.is_premium}
            onSwitch={(slug) => sessionId ? switchChannel(slug) : setActiveChannel(slug)}
            onLocked={(ch) => openGate(ch.access || { code: 'access_denied', message: 'Channel locked' }, { slug: ch.slug, name: ch.name })}
          />
        )}

        {/* See all channels link */}
        <TouchableOpacity
          style={s.seeAllBtn}
          onPress={() => router.push('/channels')}
          testID="see-all-channels-btn"
        >
          <Ionicons name="grid-outline" size={14} color={COLORS.secondary} />
          <Text style={s.seeAllText}>See all channels</Text>
          <Ionicons name="chevron-forward" size={12} color={COLORS.secondary} />
        </TouchableOpacity>

        {/* Launch / Now Playing */}
        {!sessionId ? (
          <View style={s.launchArea} testID="radio-launch">
            <TouchableOpacity
              style={[s.onAirBtn, starting && { opacity: 0.6 }]}
              onPress={startRadio} disabled={starting}
              testID="on-air-button" activeOpacity={0.7}
            >
              {starting ? (
                <ActivityIndicator size={48} color={COLORS.primary} />
              ) : (
                <Ionicons name="radio" size={56} color={COLORS.primary} />
              )}
              <Text style={s.onAirLabel}>{starting ? 'TUNING IN...' : 'ON AIR'}</Text>
              <Text style={s.onAirSub}>
                {starting ? 'PHIR MILTE HAIN' :
                  activeChannel ? `TAP TO START · ${(channels.find(c => c.slug === activeChannel)?.name || '').toUpperCase()}` :
                  'TAP TO START · NON-STOP RADIO'}
              </Text>
            </TouchableOpacity>
            <Text style={s.welcomeText} testID="launch-sub">
              Welcome back, {user.name?.split(' ')[0]}. Pick a channel, then tap ON AIR.
            </Text>
          </View>
        ) : (
          <View style={s.nowPlaying} testID="radio-deck">
            {/* Status */}
            <View style={s.npStatusRow} testID="np-status">
              <View style={[s.pulse, inRJ && { backgroundColor: COLORS.secondary }]} />
              <Text style={s.npStatusText}>
                {inRJ
                  ? (isDuo ? 'BANTER · LIVE BREAK' : `RJ ${currentSeg?.rj_voice_name?.toUpperCase()} · LIVE BREAK`)
                  : 'ON AIR · NOW PLAYING'}
              </Text>
              {isDuo && (
                <View style={s.duoBadge}>
                  <Ionicons name="people" size={10} color={COLORS.secondary} />
                  <Text style={s.duoBadgeText}>DUO</Text>
                </View>
              )}
              {currentSeg?.channel_name && (
                <View style={s.channelTag}>
                  <Text style={s.channelTagText}>{currentSeg.channel_name.toUpperCase()}</Text>
                </View>
              )}
            </View>

            {duoLabel && (
              <Text style={s.duoHosts} testID="duo-hosts">Hosts: <Text style={{ fontWeight: '800' }}>{duoLabel}</Text></Text>
            )}

            {/* Track Info */}
            <Text style={s.trackTitle} testID="np-track">{currentSeg?.track_title || '—'}</Text>
            <Text style={s.trackArtist}>{currentSeg?.track_artist || ''}</Text>

            {/* Progress Bar */}
            <View style={s.progressBar} testID="seg-bar">
              <View style={[s.progressFill, { width: `${duration > 0 ? (currentTime / duration) * 100 : 0}%` }]} />
            </View>
            <View style={s.timeRow} testID="seg-times">
              <Text style={s.timeText}>{fmt(currentTime)}</Text>
              <Text style={s.timeText}>{fmt(duration)}</Text>
            </View>

            {/* Controls */}
            <View style={s.controlsRow}>
              <TouchableOpacity style={s.playBtn} onPress={togglePlay} testID="play-pause-btn">
                <Ionicons name={playing ? 'pause' : 'play'} size={28} color="#fff" />
              </TouchableOpacity>
              <TouchableOpacity
                style={[s.skipBtn, (advancing || (skipExhausted && !user.is_premium)) && { opacity: 0.4 }]}
                onPress={skip}
                disabled={advancing || (skipExhausted && !user.is_premium)}
                testID="skip-btn"
              >
                {advancing ? <ActivityIndicator size={18} color={COLORS.textDim} /> : <Ionicons name="play-skip-forward" size={18} color={COLORS.textDim} />}
                <Text style={s.skipText}>
                  {advancing ? 'Switching...'
                    : user.is_premium ? 'Skip · ∞'
                    : skipExhausted ? `Resets ${fmtCountdown(skipCountdown)}`
                    : `Skip · ${skipRemaining}/${skipLimit}`}
                </Text>
              </TouchableOpacity>
            </View>

            {/* Skip Meta */}
            <View style={s.skipMetaRow} testID="skip-meta">
              <Ionicons name="time-outline" size={11} color={COLORS.textMuted} />
              {user.is_premium ? (
                <>
                  <Ionicons name="diamond" size={11} color={COLORS.gold} />
                  <Text style={s.skipMeta}>VIP · UNLIMITED SKIPS</Text>
                </>
              ) : skipExhausted ? (
                <Text style={[s.skipMeta, { color: COLORS.orange }]}>
                  SKIP LIMIT HIT · RESETS IN <Text style={{ fontWeight: '900' }}>{fmtCountdown(skipCountdown)}</Text>
                </Text>
              ) : (
                <Text style={s.skipMeta}>{skipUsed}/{skipLimit} SKIPS USED · 1H ROLLING</Text>
              )}
            </View>

            {/* RJ Script */}
            {currentSeg?.rj_script && (
              <View style={[s.rjBubble, inRJ && { borderColor: COLORS.secondary }]} testID="rj-bubble">
                <Text style={s.rjTag}>
                  {isDuo ? `DUO BANTER · ${duoLabel?.toUpperCase()}` : `RJ ${currentSeg.rj_voice_name?.toUpperCase()} · HINGLISH BREAK`}
                </Text>
                <Text style={s.rjScript}>{currentSeg.rj_script}</Text>
              </View>
            )}

            {/* History */}
            {history.length > 1 && (
              <View style={s.historySection} testID="history-ticker">
                <Text style={s.historySectionTitle}>JUST PLAYED</Text>
                {history.slice(0, -1).slice(-4).map((seg: any, i: number) => (
                  <View key={seg.segment_id || i} style={s.historyRow} testID={`history-row-${i}`}>
                    <Text style={s.historyTrack} numberOfLines={1}>{seg.track_title}</Text>
                    <Text style={s.historyArtist} numberOfLines={1}>— {seg.track_artist}</Text>
                  </View>
                ))}
              </View>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  scrollContent: { paddingBottom: 40 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: SPACING.md, paddingTop: SPACING.lg },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },
  brandName: { color: '#fff', fontSize: FONT.xl, fontWeight: '900' },
  brandDxb: { color: COLORS.secondary },
  headerRight: { flexDirection: 'row', gap: 8 },
  headerBtn: { padding: 8, borderRadius: RADIUS.sm, backgroundColor: COLORS.card },
  tagline: { color: COLORS.textMuted, fontSize: FONT.xs, letterSpacing: 3, fontWeight: '700', textAlign: 'center', marginBottom: SPACING.md },
  seeAllBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    paddingVertical: 8, marginHorizontal: SPACING.md, marginBottom: SPACING.md,
  },
  seeAllText: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 0.5 },
  launchArea: { alignItems: 'center', paddingVertical: SPACING.xxl, paddingHorizontal: SPACING.lg },
  onAirBtn: {
    width: 200, height: 200, borderRadius: 100, alignItems: 'center', justifyContent: 'center',
    backgroundColor: COLORS.card, borderWidth: 2, borderColor: COLORS.primary,
  },
  onAirLabel: { color: '#fff', fontSize: FONT.xl, fontWeight: '900', marginTop: SPACING.sm },
  onAirSub: { color: COLORS.textMuted, fontSize: FONT.xs, letterSpacing: 1, fontWeight: '700', marginTop: 4, textAlign: 'center' },
  welcomeText: { color: COLORS.textDim, fontSize: FONT.md, textAlign: 'center', marginTop: SPACING.lg, lineHeight: 22 },
  nowPlaying: { padding: SPACING.lg },
  npStatusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: SPACING.md, flexWrap: 'wrap' },
  pulse: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.green },
  npStatusText: { color: COLORS.textDim, fontSize: FONT.xs, letterSpacing: 1.5, fontWeight: '700' },
  duoBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: 'rgba(0,217,255,0.1)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.sm },
  duoBadgeText: { color: COLORS.secondary, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  channelTag: { backgroundColor: COLORS.card, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.sm },
  channelTagText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1 },
  duoHosts: { color: COLORS.textDim, fontSize: FONT.xs, letterSpacing: 1, marginBottom: SPACING.sm },
  trackTitle: { color: '#fff', fontSize: FONT.xxl, fontWeight: '900', marginBottom: 4 },
  trackArtist: { color: COLORS.textDim, fontSize: FONT.lg, marginBottom: SPACING.lg },
  progressBar: { height: 4, backgroundColor: COLORS.cardBorder, borderRadius: 2 },
  progressFill: { height: 4, backgroundColor: COLORS.primary, borderRadius: 2 },
  timeRow: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6, marginBottom: SPACING.lg },
  timeText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', letterSpacing: 1 },
  controlsRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.lg, justifyContent: 'center', marginBottom: SPACING.md },
  playBtn: {
    width: 64, height: 64, borderRadius: 32, backgroundColor: COLORS.primary,
    alignItems: 'center', justifyContent: 'center',
  },
  skipBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 12, borderRadius: RADIUS.lg, backgroundColor: COLORS.card },
  skipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  skipMetaRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, marginBottom: SPACING.lg },
  skipMeta: { color: COLORS.textMuted, fontSize: FONT.xs, letterSpacing: 1.5, fontWeight: '700' },
  rjBubble: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.lg },
  rjTag: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5, marginBottom: 8 },
  rjScript: { color: COLORS.textDim, fontSize: FONT.md, lineHeight: 22 },
  historySection: { marginTop: SPACING.sm },
  historySectionTitle: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2, marginBottom: SPACING.sm },
  historyRow: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  historyTrack: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  historyArtist: { color: COLORS.textMuted, fontSize: FONT.xs },
});
