// Phase 5 — Gamified Bar Purchase (mobile). Drink-themed spin wheel on the
// bar's page. Renders nothing unless the business is a bar/club. A spin is
// unlocked by any paid order at this bar (server-verified).
import React, { useCallback, useEffect, useRef, useState } from 'react';
import { View, Text, Pressable, StyleSheet, ActivityIndicator, Animated, Easing } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import api from '../api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

const WHEEL_COLORS = ['#a855f7', '#ec4899', '#f59e0b', '#22d3ee', '#34d399', '#f472b6', '#8b5cf6'];

export default function BarGameCard({ businessId }: { businessId: string }) {
  const [data, setData] = useState<any>(null);
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState<any>(null);
  const spinAnim = useRef(new Animated.Value(0)).current;
  const rotRef = useRef(0);

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/bar-games/${businessId}`); setData(data); if (data?.last_result) setResult(data.last_result); }
    catch (_) { setData({ eligible: false }); }
  }, [businessId]);
  useEffect(() => { load(); }, [load]);

  const claim = async () => {
    try {
      const { data } = await api.post(`/bar-games/${businessId}/claim`);
      setData(data);
    } catch (_) {}
  };

  const spin = async () => {
    if (spinning) return;
    setSpinning(true); setResult(null);
    try {
      const { data: res } = await api.post(`/bar-games/${businessId}/spin`);
      const n = (res.segments || segments).length || 1;
      const seg = 360 / n;
      const target = 360 * 5 + (360 - (res.segment_index + 0.5) * seg);
      const next = rotRef.current - (rotRef.current % 360) + target;
      Animated.timing(spinAnim, { toValue: next, duration: 3200, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start(() => {
        rotRef.current = next;
        setSpinning(false);
        setResult(res);
        setData((d: any) => ({ ...d, spins_available: res.spins_available }));
      });
    } catch (_) { setSpinning(false); load(); }
  };

  if (!data || !data.eligible) return null;

  const segments = data.config?.segments || [];
  const n = segments.length || 1;
  const seg = 360 / n;
  const spins = data.spins_available || 0;
  const rotate = spinAnim.interpolate({ inputRange: [0, 360], outputRange: ['0deg', '360deg'] });

  return (
    <LinearGradient colors={['#1a1038', '#2a1148']} style={s.card} testID="bar-game-card">
      <View style={s.head}>
        <LinearGradient colors={['#a855f7', '#ec4899']} style={s.headIcon}><Ionicons name="wine" size={18} color="#fff" /></LinearGradient>
        <View style={{ flex: 1 }}>
          <Text style={s.title}>Spin the Bar Wheel</Text>
          <Text style={s.sub} numberOfLines={2}>{data.config?.how_it_works}</Text>
        </View>
      </View>

      <View style={s.wheelWrap}>
        <View style={s.pointer} />
        <Animated.View style={[s.wheel, { transform: [{ rotate }] }]}>
          {segments.map((sg: any, i: number) => (
            <View key={i} style={[s.sliceLabel, { transform: [{ rotate: `${(i + 0.5) * seg}deg` }, { translateY: -86 }, { rotate: `-${(i + 0.5) * seg}deg` }] }]}>
              <Text style={{ fontSize: 20 }}>{sg.emoji}</Text>
              <Text style={s.sliceTxt} numberOfLines={2}>{sg.label}</Text>
            </View>
          ))}
          {segments.map((_: any, i: number) => (
            <View key={`d${i}`} style={[s.divider, { transform: [{ rotate: `${i * seg}deg` }] }]} />
          ))}
          <View style={s.hub}><Ionicons name="sparkles" size={16} color="#7c3aed" /></View>
        </Animated.View>
      </View>

      {result && !spinning ? (
        <View style={[s.result, result.win && s.resultWin]} testID="bar-game-result">
          {result.win ? (
            <>
              <Text style={s.resultTitle}>🍸 {result.label}</Text>
              <View style={s.codeBox} testID="bar-game-code">
                <Ionicons name="ticket" size={14} color="#34d399" />
                <Text style={s.codeTxt}>{result.code}</Text>
              </View>
              <Text style={s.fine}>Show this code at the bar to redeem.</Text>
            </>
          ) : (
            <Text style={s.resultLose}>{result.emoji} {result.label} — no win this time.</Text>
          )}
        </View>
      ) : null}

      {spins > 0 ? (
        <Pressable onPress={spin} disabled={spinning} testID="bar-game-spin">
          <LinearGradient colors={['#a855f7', '#ec4899']} style={s.spinBtn}>
            {spinning ? <ActivityIndicator color="#fff" /> : <><Ionicons name="wine" size={18} color="#fff" /><Text style={s.spinTxt}>Spin now · {spins} left</Text></>}
          </LinearGradient>
        </Pressable>
      ) : (
        <View style={{ alignItems: 'center' }}>
          <Text style={s.locked} testID="bar-game-locked">Buy a round here to unlock a spin.</Text>
          <Pressable onPress={claim} testID="bar-game-claim" style={s.claimBtn}>
            <Ionicons name="refresh" size={13} color="#c4b5fd" />
            <Text style={s.claimTxt}>I just bought — unlock my spin</Text>
          </Pressable>
        </View>
      )}
    </LinearGradient>
  );
}

const s = StyleSheet.create({
  card: { marginTop: SPACING.md, borderRadius: RADIUS.xl, padding: SPACING.md, borderWidth: 1, borderColor: 'rgba(168,85,247,0.25)' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  headIcon: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  title: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  sub: { color: 'rgba(196,181,253,0.8)', fontSize: FONT.xs, marginTop: 2 },
  wheelWrap: { alignItems: 'center', justifyContent: 'center', marginTop: 16, height: 236 },
  pointer: { position: 'absolute', top: -2, zIndex: 10, width: 0, height: 0, borderLeftWidth: 11, borderRightWidth: 11, borderTopWidth: 18, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: '#fff' },
  wheel: { width: 220, height: 220, borderRadius: 110, borderWidth: 4, borderColor: 'rgba(255,255,255,0.8)', backgroundColor: '#2a1148', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  sliceLabel: { position: 'absolute', width: 64, alignItems: 'center' },
  sliceTxt: { color: '#fff', fontSize: 8, fontWeight: '900', textAlign: 'center', lineHeight: 10 },
  divider: { position: 'absolute', width: 1, height: 110, top: 0, backgroundColor: 'rgba(255,255,255,0.25)' },
  hub: { width: 44, height: 44, borderRadius: 22, backgroundColor: 'rgba(255,255,255,0.9)', alignItems: 'center', justifyContent: 'center' },
  result: { marginTop: 14, borderRadius: RADIUS.lg, padding: 14, alignItems: 'center', backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.12)' },
  resultWin: { backgroundColor: 'rgba(52,211,153,0.12)', borderColor: '#34d399' },
  resultTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '900' },
  resultLose: { color: '#fff', fontSize: FONT.sm, fontWeight: '700', textAlign: 'center' },
  codeBox: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.md, borderWidth: 1, borderStyle: 'dashed', borderColor: '#34d399', backgroundColor: 'rgba(0,0,0,0.3)' },
  codeTxt: { color: '#34d399', fontWeight: '900', fontSize: FONT.md, letterSpacing: 1 },
  fine: { color: 'rgba(196,181,253,0.7)', fontSize: FONT.xs, marginTop: 8, textAlign: 'center' },
  spinBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 48, borderRadius: 24, marginTop: 14 },
  spinTxt: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  locked: { color: 'rgba(196,181,253,0.85)', fontSize: FONT.sm, marginTop: 14, textAlign: 'center' },
  claimBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8, paddingHorizontal: 16, height: 36, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.1)' },
  claimTxt: { color: '#c4b5fd', fontSize: FONT.xs, fontWeight: '800' },
});
