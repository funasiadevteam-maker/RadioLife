import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ActivityIndicator, ScrollView, Dimensions,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Image as ExpoImage } from 'expo-image';
import Animated, { useSharedValue, useAnimatedStyle, withTiming } from 'react-native-reanimated';
import { createAudioPlayer } from 'expo-audio';
import api from '../../src/api/client';
import { GAME_ART } from '../../src/constants/gameArt';
import { gameFx, haptic } from '../../src/utils/gameFX';

const P = { bg: '#0b0c16', card: '#15131f', line: 'rgba(255,255,255,0.1)', text: '#fff', muted: '#8b8b9e', gold: '#fbbf24', violet: '#a855f7' };
const { width } = Dimensions.get('window');
const TILE = Math.min(96, (width - 32 - 24) / 3);

function Tile({ label, color, revealed, onReveal }: any) {
  const foil = useSharedValue(1);
  useEffect(() => { foil.value = withTiming(revealed ? 0 : 1, { duration: 400 }); }, [revealed]);
  const foilStyle = useAnimatedStyle(() => ({ opacity: foil.value }));
  return (
    <Pressable onPress={onReveal} style={[st.tile, { borderColor: color || P.line }]} testID="scratch-tile">
      <Text style={[st.tileLabel, { color: color || P.text }]} numberOfLines={2}>{label}</Text>
      <Animated.View style={[st.foil, foilStyle]} pointerEvents={revealed ? 'none' : 'auto'}>
        <Ionicons name="sparkles" size={22} color="rgba(0,0,0,0.35)" />
        <Text style={st.foilTxt}>Scratch</Text>
      </Animated.View>
    </Pressable>
  );
}

export default function ScratchScreen() {
  const router = useRouter();
  const { game_id } = useLocalSearchParams<{ game_id?: string }>();
  const gid = game_id || 'scratch_house';
  const [cfg, setCfg] = useState<any>(null);
  const [card, setCard] = useState<any>(null);
  const [revealed, setRevealed] = useState<boolean[]>([false, false, false]);
  const [spinsLeft, setSpinsLeft] = useState(0);
  const [busy, setBusy] = useState(false);
  const [muted, setMuted] = useState(false);
  const player = useRef<any>(null);

  useEffect(() => {
    api.get(`/games/wheel/config?game_id=${gid}`).then(({ data }) => { setCfg(data); setSpinsLeft(data.spins_left || 0); }).catch(() => {});
    return () => { try { player.current?.release?.(); } catch (_) {} };
  }, [gid]);

  const startBgm = useCallback(() => {
    if (muted || !cfg?.bgm_url) return;
    try {
      if (!player.current) { player.current = createAudioPlayer(cfg.bgm_url); player.current.loop = true; player.current.volume = 0.35; }
      player.current.play();
    } catch (_) {}
  }, [cfg, muted]);
  const toggleMute = () => {
    setMuted((m) => { const n = !m; try { n ? player.current?.pause?.() : player.current?.play?.(); } catch (_) {} return n; });
  };

  const done = card && revealed.every(Boolean);
  const play = async () => {
    if (busy || spinsLeft <= 0) return;
    setBusy(true); startBgm();
    try {
      const { data } = await api.post('/games/scratch/play', { game_id: gid });
      setCard(data); setRevealed([false, false, false]); setSpinsLeft(data.spins_left);
    } catch (e: any) {
      if (e?.response?.status === 429) setSpinsLeft(0);
    } finally { setBusy(false); }
  };
  const fx = (k: any, h: any) => { if (!muted) gameFx(k, h); else haptic(h); };
  const reveal = (i: number) => { if (!revealed[i]) fx('reveal', 'light'); setRevealed((r) => r.map((v, idx) => (idx === i ? true : v))); };
  const revealAll = () => { fx('reveal', 'light'); setRevealed([true, true, true]); };
  const prevDone = useRef(false);
  useEffect(() => {
    if (done && !prevDone.current) { prevDone.current = true; if (card?.win) fx('win', 'success'); else fx('lose', 'light'); }
    if (!done) prevDone.current = false;
  }, [done]);

  const prize = card?.prize;
  return (
    <SafeAreaView style={st.safe} edges={['top', 'bottom']}>
      <View style={st.header}>
        <Pressable onPress={() => router.back()} testID="scratch-back" style={st.hBtn}><Ionicons name="chevron-back" size={22} color={P.text} /></Pressable>
        <Text style={st.hTitle}>Scratch Card</Text>
        <Pressable onPress={toggleMute} testID="scratch-mute" style={st.hBtn}><Ionicons name={muted ? 'volume-mute' : 'volume-high'} size={20} color={P.muted} /></Pressable>
      </View>
      <ScrollView contentContainerStyle={{ padding: 16, alignItems: 'center' }} testID="scratch-game">
        {/* Premium AI-art hero */}
        <View style={st.hero} testID="scratch-hero">
          <ExpoImage source={{ uri: GAME_ART.scratch_win }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={['rgba(14,8,34,0.92)', 'rgba(14,8,34,0.2)']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={StyleSheet.absoluteFill} />
          <View style={st.heroBody}>
            <View style={st.heroPill}><Text style={st.heroPillTxt}>DAILY SCRATCH</Text></View>
            <Text style={st.heroTitle}>Scratch, match & win</Text>
            <Text style={st.heroSub}>Reveal all three — match 3 to win BigPoints or coupons.</Text>
          </View>
        </View>

        {cfg?.logo_url ? (
          <View style={st.sponsor} testID="scratch-sponsor">
            <ExpoImage source={{ uri: cfg.logo_url }} style={st.logo} contentFit="contain" />
            <Text style={st.sponsorTxt}>Sponsored by {cfg.sponsor_name}</Text>
          </View>
        ) : <Text style={st.brand}>FUUSIC · Scratch & win</Text>}

        <View style={st.cardBox}>
          {!card ? (
            spinsLeft <= 0
              ? <Ionicons name="ticket-outline" size={34} color={P.muted} />
              : <Text style={st.hint}>Tap "New card" then scratch the three tiles. Match 3 to win! 🎟️</Text>
          ) : (
            <View style={{ flexDirection: 'row', gap: 12 }}>
              {card.tiles.map((t: string, i: number) => (
                <Tile key={i} label={t} color={P.violet} revealed={revealed[i]} onReveal={() => reveal(i)} />
              ))}
            </View>
          )}
        </View>

        {done ? (
          <View style={[st.result, { borderColor: card.win ? P.gold : P.line }]} testID="scratch-result">
            <Text style={[st.resultTitle, { color: card.win ? P.gold : P.muted }]}>{card.win ? '🎉 You won!' : 'No match this time'}</Text>
            <Text style={st.resultPrize}>{card.win ? (prize?.kind === 'coupon' ? prize.label : `${prize?.points || 0} points`) : 'Try another card'}</Text>
            {card.streak?.bonus?.awarded ? (
              <Text style={st.streakLine} testID="scratch-streak-bonus">
                🔥 Day {card.streak.bonus.streak_day} streak · +{card.streak.bonus.points} pts{card.streak.bonus.bonus_spin ? ' · +1 bonus spin!' : ''}
              </Text>
            ) : null}
          </View>
        ) : null}

        <Text style={st.spins} testID="scratch-spins-left">{spinsLeft} card{spinsLeft === 1 ? '' : 's'} left today</Text>

        {spinsLeft <= 0 && !card ? (
          <Text style={st.noSpins} testID="scratch-no-spins">You're out of cards for today. Come back tomorrow! 🎟️</Text>
        ) : (!card || done) ? (
          <Pressable onPress={play} disabled={busy || spinsLeft <= 0} testID="scratch-play" style={{ width: '100%', marginTop: 12 }}>
            <LinearGradient colors={['#a855f7', '#ec4899']} style={st.playBtn}>
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={st.playTxt}>{card ? 'New card' : 'New card'}</Text>}
            </LinearGradient>
          </Pressable>
        ) : (
          <Pressable onPress={revealAll} testID="scratch-reveal-all" style={{ width: '100%', marginTop: 12 }}>
            <View style={[st.playBtn, { backgroundColor: P.gold }]}><Text style={[st.playTxt, { color: '#000' }]}>Reveal all</Text></View>
          </Pressable>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  safe: { flex: 1, backgroundColor: P.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, height: 52 },
  hBtn: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  hTitle: { color: P.text, fontSize: 17, fontWeight: '900' },
  sponsor: { alignItems: 'center', marginBottom: 10 },
  logo: { width: 64, height: 64, borderRadius: 14, marginBottom: 4 },
  sponsorTxt: { color: P.muted, fontSize: 11, fontWeight: '700' },
  brand: { color: P.violet, fontSize: 13, fontWeight: '900', marginBottom: 10 },
  hero: { width: '100%', minHeight: 128, borderRadius: 24, overflow: 'hidden', marginBottom: 16, justifyContent: 'flex-end', shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 16, shadowOffset: { width: 0, height: 12 } },
  heroBody: { padding: 16 },
  heroPill: { alignSelf: 'flex-start', backgroundColor: P.gold, borderRadius: 999, paddingHorizontal: 10, paddingVertical: 4, marginBottom: 8 },
  heroPillTxt: { color: '#1a1206', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  heroTitle: { color: '#fff', fontSize: 20, fontWeight: '900' },
  heroSub: { color: '#e3d9fb', fontSize: 12, marginTop: 4 },
  cardBox: { width: '100%', minHeight: 140, borderRadius: 20, borderWidth: 1, borderColor: 'rgba(251,191,36,0.25)', backgroundColor: '#1a1330', alignItems: 'center', justifyContent: 'center', padding: 16 },
  hint: { color: P.muted, fontSize: 13, textAlign: 'center', lineHeight: 19 },
  tile: { width: TILE, height: TILE, borderRadius: 14, borderWidth: 1, backgroundColor: '#0f0e1a', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  tileLabel: { fontSize: 12, fontWeight: '900', textAlign: 'center', paddingHorizontal: 4 },
  foil: { ...StyleSheet.absoluteFillObject, backgroundColor: '#c9b98a', alignItems: 'center', justifyContent: 'center' },
  foilTxt: { color: 'rgba(0,0,0,0.45)', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  result: { marginTop: 14, width: '100%', borderRadius: 16, borderWidth: 1, backgroundColor: 'rgba(255,255,255,0.03)', padding: 14, alignItems: 'center' },
  resultTitle: { fontSize: 16, fontWeight: '900' },
  resultPrize: { color: P.text, fontSize: 20, fontWeight: '900', marginTop: 2 },
  streakLine: { color: '#fb923c', fontSize: 13, fontWeight: '800', marginTop: 10, textAlign: 'center' },
  spins: { color: P.muted, fontSize: 12, fontWeight: '700', marginTop: 14 },
  noSpins: { color: P.muted, fontSize: 13, textAlign: 'center', marginTop: 12 },
  playBtn: { height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  playTxt: { color: '#fff', fontSize: 15, fontWeight: '900' },
});
