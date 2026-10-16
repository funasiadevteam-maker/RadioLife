import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, SafeAreaView, ActivityIndicator,
  Modal, useWindowDimensions,
} from 'react-native';
import Svg, { G, Path, Circle, Defs, RadialGradient, Stop, Text as SvgText } from 'react-native-svg';
import Animated, {
  useSharedValue, useAnimatedStyle, withTiming,
  Easing, runOnJS, interpolate,
} from 'react-native-reanimated';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image as ExpoImage } from 'expo-image';
import { TUBE, TFONT } from '../../src/constants/tube';
import { WHEEL_BACKDROP } from '../../src/constants/gameArt';
import api from '../../src/api/client';

const VB = 320, CX = 160, CY = 160, R = 150, LABEL_R = 100;
let createAudioPlayer: any;
try { createAudioPlayer = require('expo-audio').createAudioPlayer; } catch (_) {}

function polar(r: number, degFromTop: number) {
  const t = ((degFromTop - 90) * Math.PI) / 180;
  return [CX + r * Math.cos(t), CY + r * Math.sin(t)];
}
function slicePath(i: number, seg: number) {
  const [x0, y0] = polar(R, i * seg);
  const [x1, y1] = polar(R, (i + 1) * seg);
  const large = seg > 180 ? 1 : 0;
  return `M ${CX} ${CY} L ${x0.toFixed(2)} ${y0.toFixed(2)} A ${R} ${R} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)} Z`;
}
function shorten(label: string): [string, string] {
  const m = /^(\d+)\s*pts$/i.exec(label);
  if (m) return [m[1], 'pts'];
  if (/jackpot/i.test(label)) return ['5000', 'JACKPOT'];
  const parts = label.split(' ');
  if (parts.length > 1) return [parts[0], parts.slice(1).join(' ')];
  return [label, ''];
}

const CONFETTI_COLORS = ['#a855f7', '#ec4899', '#fbbf24', '#22d3ee', '#10b981'];
function ConfettiPiece({ delay, startX, w }: any) {
  const t = useSharedValue(0);
  useEffect(() => {
    t.value = withTiming(1, { duration: 1400, easing: Easing.out(Easing.quad) });
  }, []);
  const color = CONFETTI_COLORS[Math.floor(Math.random() * CONFETTI_COLORS.length)];
  const drift = (Math.random() - 0.5) * 120;
  const style = useAnimatedStyle(() => ({
    position: 'absolute',
    left: startX,
    top: interpolate(t.value, [0, 1], [-30, 520]),
    transform: [{ translateX: interpolate(t.value, [0, 1], [0, drift]) },
                { rotate: `${interpolate(t.value, [0, 1], [0, 540])}deg` }],
    opacity: interpolate(t.value, [0, 0.85, 1], [1, 1, 0]),
  }));
  return <Animated.View style={[style, { width: 9, height: 14, borderRadius: 2, backgroundColor: color }]} />;
}
function Confetti({ show }: any) {
  const { width } = useWindowDimensions();
  if (!show) return null;
  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {Array.from({ length: 22 }).map((_, i) => (
        <ConfettiPiece key={i} startX={Math.random() * width} />
      ))}
    </View>
  );
}

export default function WheelGameScreen() {
  const { game_id } = useLocalSearchParams<{ game_id?: string }>();
  const gameId = game_id || 'wheel_house';
  const router = useRouter();
  const { width } = useWindowDimensions();
  const size = Math.min(width - 40, 340);

  const [cfg, setCfg] = useState<any>(null);
  const [spinning, setSpinning] = useState(false);
  const [prize, setPrize] = useState<any>(null);
  const [muted, setMuted] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confetti, setConfetti] = useState(0);

  const rot = useSharedValue(0);
  const rotRef = useRef(0);
  const playerRef = useRef<any>(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get('/games/wheel/config', { params: { game_id: gameId } }); setCfg(data); }
    catch (_) { setError('Couldn’t load the wheel.'); }
  }, [gameId]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => () => { try { playerRef.current?.release?.(); } catch (_) {} }, []);

  const startBgm = () => {
    if (muted || !cfg?.bgm_url || !createAudioPlayer) return;
    try {
      if (!playerRef.current) {
        playerRef.current = createAudioPlayer(cfg.bgm_url);
        playerRef.current.loop = true;
        playerRef.current.volume = 0.35;
      }
      playerRef.current.play();
    } catch (_) {}
  };
  const toggleMute = () => {
    setMuted((m) => {
      const nm = !m;
      try { if (nm) playerRef.current?.pause?.(); else playerRef.current?.play?.(); } catch (_) {}
      return nm;
    });
  };

  const onSettle = (data: any) => {
    setSpinning(false);
    setCfg((c: any) => ({ ...c, spins_left: data.spins_left }));
    setPrize(data.prize);
    if (data.prize.kind !== 'none') setConfetti((n) => n + 1);
  };

  const spin = async () => {
    if (spinning || !cfg || cfg.spins_left <= 0) return;
    setSpinning(true); setPrize(null);
    startBgm();
    try {
      const { data } = await api.post('/games/wheel/spin', { game_id: gameId });
      const n = cfg.segments.length;
      const seg = 360 / n;
      const ci = data.segment_index * seg + seg / 2;
      const next = Math.ceil((rotRef.current + 1) / 360) * 360 + 6 * 360 + ((360 - ci) % 360);
      rotRef.current = next;
      rot.value = withTiming(next, { duration: 4200, easing: Easing.bezier(0.16, 1, 0.3, 1) },
        (finished) => { if (finished) runOnJS(onSettle)(data); });
    } catch (e: any) {
      setSpinning(false);
      if (e?.response?.status === 429) setCfg((c: any) => ({ ...c, spins_left: 0 }));
      else setError('Spin failed — try again.');
    }
  };

  const wheelStyle = useAnimatedStyle(() => ({ transform: [{ rotate: `${rot.value}deg` }] }));

  const segs = useMemo(() => {
    if (!cfg) return [];
    const n = cfg.segments.length; const seg = 360 / n;
    return cfg.segments.map((s: any, i: number) => {
      const am = i * seg + seg / 2; const [lx, ly] = polar(LABEL_R, am);
      const [big, small] = shorten(s.label);
      return { ...s, i, path: slicePath(i, seg), am, lx, ly, big, small };
    });
  }, [cfg]);

  if (error && !cfg) return (
    <SafeAreaView style={st.center}><Text style={{ color: '#fff', marginBottom: 12 }}>{error}</Text>
      <Pressable onPress={() => router.back()} style={st.backBtn}><Text style={{ color: '#fff' }}>Go back</Text></Pressable></SafeAreaView>
  );
  if (!cfg) return <SafeAreaView style={st.center}><ActivityIndicator color="#fff" /></SafeAreaView>;

  const out = cfg.spins_left <= 0;

  return (
    <SafeAreaView style={st.root} testID="wheel-game">
      <View style={st.header}>
        <Pressable onPress={() => router.back()} testID="wheel-back" style={st.iconBtn}><Ionicons name="arrow-back" size={20} color="#fff" /></Pressable>
        <Text style={st.hTitle}>Wheel of Fortune</Text>
        <Pressable onPress={toggleMute} testID="wheel-mute" style={st.iconBtn}><Ionicons name={muted ? 'volume-mute' : 'volume-high'} size={20} color="#fff" /></Pressable>
      </View>

      {(cfg.logo_url || cfg.sponsor_name) ? (
        <View style={st.sponsor} testID="wheel-sponsor">
          {cfg.logo_url ? <ExpoImage source={{ uri: cfg.logo_url }} style={st.logo} contentFit="cover" /> : null}
          <Text style={st.sponsorTxt}>Sponsored by <Text style={{ color: '#fff', fontWeight: '900' }}>{cfg.sponsor_name}</Text></Text>
        </View>
      ) : null}

      <View style={[st.stage, { marginTop: 12 }]}>
        <ExpoImage source={{ uri: WHEEL_BACKDROP }} style={StyleSheet.absoluteFill} contentFit="cover" />
        <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(10,6,28,0.5)' }]} />
        <View style={{ width: size, height: size + 20 }}>
          <View style={st.pointer} />
          <Animated.View style={[wheelStyle, { width: size, height: size }]}>
            <Svg width={size} height={size} viewBox={`0 0 ${VB} ${VB}`}>
              <Defs>
                <RadialGradient id="gloss" cx="50%" cy="38%" r="65%">
                  <Stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
                  <Stop offset="45%" stopColor="#ffffff" stopOpacity="0.06" />
                  <Stop offset="100%" stopColor="#000000" stopOpacity="0.28" />
                </RadialGradient>
              </Defs>
              <Circle cx={CX} cy={CY} r={R + 6} fill="#1e1030" stroke="#fbbf24" strokeWidth={4} />
              {segs.map((s: any) => (
                <Path key={s.i} d={s.path} fill={s.color} stroke="rgba(0,0,0,0.25)" strokeWidth={1.5} />
              ))}
              {segs.map((s: any) => (
                <G key={`l${s.i}`} rotation={s.am} origin={`${s.lx}, ${s.ly}`}>
                  <SvgText x={s.lx} y={s.ly - 2} fill="#fff" fontSize={15} fontWeight="900" textAnchor="middle">{s.big}</SvgText>
                  <SvgText x={s.lx} y={s.ly + 11} fill="rgba(255,255,255,0.85)" fontSize={8} fontWeight="700" textAnchor="middle">{s.small}</SvgText>
                </G>
              ))}
              <Circle cx={CX} cy={CY} r={R} fill="url(#gloss)" />
            </Svg>
          </Animated.View>
          <Pressable onPress={spin} disabled={spinning || out} testID="wheel-spin"
                     style={[st.hub, { left: size / 2 - 40, top: size / 2 - 40, opacity: (spinning || out) ? 0.7 : 1 }]}>
            {spinning ? <ActivityIndicator color="#000" /> : <Text style={st.hubTxt}>SPIN</Text>}
          </Pressable>
        </View>
      </View>

      <View style={{ alignItems: 'center', marginTop: 16 }}>
        {out ? <Text style={{ color: '#fbbf24', fontWeight: '800' }} testID="wheel-no-spins">Out of spins — come back tomorrow! 🎡</Text>
          : <Text style={{ color: TUBE.textMuted }} testID="wheel-spins-left"><Text style={{ color: '#fff', fontWeight: '900' }}>{cfg.spins_left}</Text> spins left today</Text>}
      </View>

      <Confetti show={confetti > 0} key={confetti} />

      <Modal visible={!!prize} transparent animationType="fade" onRequestClose={() => setPrize(null)}>
        <Pressable style={st.modalBg} onPress={() => setPrize(null)} testID="wheel-prize-modal">
          <Pressable style={st.prizeCard} onPress={() => {}}>
            <View style={[st.prizeIcon, { backgroundColor: prize?.kind === 'none' ? 'rgba(255,255,255,0.08)' : '#fbbf24' }]}>
              <Ionicons name={prize?.kind === 'coupon' ? 'gift' : prize?.kind === 'none' ? 'sparkles-outline' : 'sparkles'} size={30} color={prize?.kind === 'none' ? '#cbd5e1' : '#000'} />
            </View>
            <Text style={st.prizeH}>{prize?.kind === 'none' ? 'So close!' : 'You won! 🎉'}</Text>
            <Text style={[st.prizeVal, { color: prize?.kind === 'none' ? '#94a3b8' : '#fbbf24' }]}>{prize?.label}</Text>
            {prize?.kind === 'coupon' ? <Text style={st.prizeSub}>Saved to your wallet{prize?.sponsor ? ` · ${prize.sponsor}` : ''}</Text> : null}
            {prize?.kind === 'points' ? <Text style={st.prizeSub}>Added to your balance</Text> : null}
            <Pressable onPress={() => setPrize(null)} testID="wheel-prize-close" style={st.prizeBtn}><Text style={{ color: '#fff', fontWeight: '900' }}>{out ? 'Done' : 'Spin again'}</Text></Pressable>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0b0c16' },
  center: { flex: 1, backgroundColor: '#0b0c16', alignItems: 'center', justifyContent: 'center' },
  backBtn: { paddingHorizontal: 16, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.1)', alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 10 },
  hTitle: { color: '#fff', fontWeight: '900', fontSize: TFONT.md },
  iconBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.1)', alignItems: 'center', justifyContent: 'center' },
  sponsor: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 2 },
  stage: { alignSelf: 'center', borderRadius: 28, overflow: 'hidden', padding: 20, alignItems: 'center', shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 20, shadowOffset: { width: 0, height: 16 } },
  logo: { width: 34, height: 34, borderRadius: 17 },
  sponsorTxt: { color: '#cbd5e1', fontSize: TFONT.xs },
  pointer: { position: 'absolute', top: -2, alignSelf: 'center', zIndex: 20, width: 0, height: 0, borderLeftWidth: 15, borderRightWidth: 15, borderTopWidth: 26, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: '#fbbf24' },
  hub: { position: 'absolute', width: 80, height: 80, borderRadius: 40, backgroundColor: '#fbbf24', alignItems: 'center', justifyContent: 'center', zIndex: 10, borderWidth: 3, borderColor: '#fff7e0', shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 8, shadowOffset: { width: 0, height: 4 } },
  hubTxt: { color: '#000', fontWeight: '900', letterSpacing: 1, fontSize: TFONT.sm },
  modalBg: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', alignItems: 'center', justifyContent: 'center', padding: 24 },
  prizeCard: { width: '100%', maxWidth: 300, borderRadius: 24, padding: 24, alignItems: 'center', backgroundColor: '#241436', borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)' },
  prizeIcon: { width: 64, height: 64, borderRadius: 32, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  prizeH: { color: '#fff', fontSize: TFONT.md, fontWeight: '900', marginBottom: 4 },
  prizeVal: { fontSize: 26, fontWeight: '900', marginBottom: 6 },
  prizeSub: { color: '#cbd5e1', fontSize: TFONT.xs, marginBottom: 8 },
  prizeBtn: { marginTop: 8, width: '100%', height: 46, borderRadius: 23, backgroundColor: '#a855f7', alignItems: 'center', justifyContent: 'center' },
});
