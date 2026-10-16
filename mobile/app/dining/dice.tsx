// Dining Club — Roll-a-Dice promo (mobile). Roll two dice; a double six (12)
// wins a free meal for 8. Win chance is exactly 1/12 (server-weighted RNG).
// Premium redesign: real pip faces + tumble animation + AI-art stage.
// Outcome stays 100% server-authoritative (die1/die2 from /dining-club/dice/roll).
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image as ExpoImage } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import Animated, {
  useSharedValue, useAnimatedStyle, withTiming, withRepeat, interpolate, Easing,
} from 'react-native-reanimated';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import { DICE_STAGE } from '../../src/constants/gameArt';

// 3x3 pip layout per face (grid cells 0..8 that are filled).
const PIPS: Record<number, number[]> = {
  1: [4], 2: [0, 8], 3: [0, 4, 8], 4: [0, 2, 6, 8],
  5: [0, 2, 4, 6, 8], 6: [0, 2, 3, 5, 6, 8],
};

function Die({ value, rolling }: { value: number; rolling: boolean }) {
  const r = useSharedValue(0);
  useEffect(() => {
    if (rolling) {
      r.value = withRepeat(withTiming(1, { duration: 420, easing: Easing.inOut(Easing.ease) }), -1, true);
    } else {
      r.value = withTiming(0, { duration: 220 });
    }
  }, [rolling]);
  const aStyle = useAnimatedStyle(() => ({
    transform: [
      { rotate: `${interpolate(r.value, [0, 1], [-20, 20])}deg` },
      { translateY: interpolate(r.value, [0, 0.5, 1], [0, -10, 0]) },
      { scale: interpolate(r.value, [0, 0.5, 1], [1, 1.07, 1]) },
    ],
  }));
  const on = new Set(PIPS[value] || [4]);
  return (
    <Animated.View style={aStyle} testID="dice-die">
      <LinearGradient colors={['#ffffff', '#efe8ff', '#e3d6ff']} start={{ x: 0.3, y: 0.2 }} end={{ x: 1, y: 1 }} style={s.die}>
        {Array.from({ length: 9 }).map((_, i) => (
          <View key={i} style={s.pipCell}>
            {on.has(i) ? <View style={s.pip} /> : null}
          </View>
        ))}
      </LinearGradient>
    </Animated.View>
  );
}

export default function DiningDice() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [rolling, setRolling] = useState(false);
  const [d1, setD1] = useState(1);
  const [d2, setD2] = useState(1);
  const [result, setResult] = useState<any>(null);
  const spinRef = useRef<any>(null);

  const load = () => api.get('/dining-club/dice').then((r) => {
    setData(r.data);
    if (r.data?.last_result) { setResult(r.data.last_result); setD1(r.data.last_result.die1); setD2(r.data.last_result.die2); }
  }).catch(() => {});
  useEffect(() => { load(); return () => clearInterval(spinRef.current); }, []);

  const roll = async () => {
    if (rolling) return;
    setRolling(true); setResult(null);
    spinRef.current = setInterval(() => {
      setD1(1 + Math.floor(Math.random() * 6));
      setD2(1 + Math.floor(Math.random() * 6));
    }, 90);
    try {
      const r = await api.post('/dining-club/dice/roll');
      setTimeout(() => {
        clearInterval(spinRef.current);
        setD1(r.data.die1); setD2(r.data.die2); setResult(r.data); setRolling(false); load();
      }, 1400);
    } catch (e: any) {
      clearInterval(spinRef.current); setRolling(false);
      const detail = e?.response?.data?.detail;
      if (detail?.code === 'already_rolled_today' && detail?.result) {
        setResult(detail.result); setD1(detail.result.die1); setD2(detail.result.die2); load();
      }
    }
  };

  const cfg = data?.config || {};
  const canRoll = data?.can_roll && !rolling;

  return (
    <SafeAreaView style={s.screen} testID="dining-dice">
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="dice-back"><Ionicons name="chevron-back" size={24} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.headerTitle}>Roll & Win</Text>
        <View style={{ width: 24 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, alignItems: 'center', paddingBottom: 60 }}>
        <Text style={s.h1}>Roll two dice — win a free meal for 8</Text>
        <Text style={s.sub}>{cfg.how_it_works || 'Land a double six and your whole table eats free.'}</Text>
        <View style={s.oddsChip}><Text style={s.oddsTxt}>Winning odds: {cfg.win_chance || '1 in 12'}</Text></View>

        {/* AI-art dice stage */}
        <View style={s.stage}>
          <ExpoImage source={{ uri: DICE_STAGE }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <View style={[StyleSheet.absoluteFill, { backgroundColor: 'rgba(10,6,28,0.55)' }]} />
          <View style={s.diceRow}>
            <Die value={d1} rolling={rolling} />
            <Text style={s.plus}>+</Text>
            <Die value={d2} rolling={rolling} />
          </View>
        </View>

        {result && !rolling ? (
          <View style={[s.resultCard, result.win && s.resultWin]} testID="dice-result">
            {result.win ? (
              <>
                <Ionicons name="trophy" size={30} color={COLORS.gold} />
                <Text style={s.winTitle}>You won!</Text>
                <Text style={s.winSub}>{result.prize}</Text>
                <View style={s.codeBox} testID="dice-win-code">
                  <Ionicons name="ticket" size={16} color={COLORS.gold} /><Text style={s.codeTxt}>{result.code}</Text>
                </View>
                <Text style={s.fine}>Show this code at a participating restaurant to redeem.</Text>
              </>
            ) : (
              <>
                <Text style={s.loseTitle}>You rolled {result.total}. So close!</Text>
                <Text style={s.winSub}>Only a double six (12) wins. Come back tomorrow.</Text>
              </>
            )}
          </View>
        ) : null}

        {canRoll ? (
          <TouchableOpacity activeOpacity={0.85} onPress={roll} disabled={rolling} testID="dice-roll-btn" style={{ width: '100%' }}>
            <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.cta}>
              {rolling ? <ActivityIndicator color="#fff" /> : <><Ionicons name="dice" size={18} color="#fff" /><Text style={s.ctaText}>Roll the dice</Text></>}
            </LinearGradient>
          </TouchableOpacity>
        ) : (!rolling ? <Text style={s.used} testID="dice-used">You've used today's roll. Come back tomorrow!</Text> : null)}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  headerTitle: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text },
  h1: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, textAlign: 'center', marginTop: SPACING.sm },
  sub: { fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center', marginTop: 6 },
  oddsChip: { marginTop: 12, backgroundColor: COLORS.primary + '18', borderColor: COLORS.primary + '44', borderWidth: 1, borderRadius: 999, paddingHorizontal: 14, paddingVertical: 6 },
  oddsTxt: { color: COLORS.primary, fontWeight: '800', fontSize: FONT.xs },
  stage: { width: '100%', maxWidth: 380, borderRadius: 28, overflow: 'hidden', marginVertical: 28, alignSelf: 'center', shadowColor: '#000', shadowOpacity: 0.5, shadowRadius: 20, shadowOffset: { width: 0, height: 16 } },
  diceRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 20, paddingVertical: 38 },
  die: { width: 90, height: 90, borderRadius: 20, padding: 12, flexDirection: 'row', flexWrap: 'wrap', borderWidth: 3, borderColor: COLORS.gold, shadowColor: '#7c3aed', shadowOpacity: 0.4, shadowRadius: 14, shadowOffset: { width: 0, height: 10 } },
  pipCell: { width: '33.333%', height: '33.333%', alignItems: 'center', justifyContent: 'center' },
  pip: { width: 15, height: 15, borderRadius: 999, backgroundColor: '#7c3aed' },
  plus: { color: '#fff', fontSize: 26, fontWeight: '900' },
  resultCard: { width: '100%', borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.card, padding: SPACING.lg, alignItems: 'center', marginBottom: SPACING.md },
  resultWin: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '14' },
  winTitle: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900', marginTop: 6 },
  loseTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', textAlign: 'center' },
  winSub: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 4, textAlign: 'center' },
  codeBox: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12, paddingHorizontal: 16, paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1, borderStyle: 'dashed', borderColor: COLORS.gold, backgroundColor: COLORS.inputBg },
  codeTxt: { color: COLORS.gold, fontWeight: '900', fontSize: FONT.md, letterSpacing: 1 },
  fine: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 10, textAlign: 'center' },
  cta: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', borderRadius: RADIUS.lg, paddingVertical: 16, width: '100%' },
  ctaText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
  used: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: SPACING.sm },
});
