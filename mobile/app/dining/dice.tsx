// Dining Club — Roll-a-Dice promo (mobile). Roll two dice; a double six (12)
// wins a free meal for 8. Win chance is exactly 1/12 (server-weighted RNG).
import React, { useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

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

        <View style={s.diceRow}>
          <View style={s.die} testID="dice-die"><Text style={s.dieTxt}>{d1}</Text></View>
          <Text style={s.plus}>+</Text>
          <View style={s.die} testID="dice-die"><Text style={s.dieTxt}>{d2}</Text></View>
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
          <TouchableOpacity style={s.cta} onPress={roll} disabled={rolling} testID="dice-roll-btn">
            {rolling ? <ActivityIndicator color="#fff" /> : <><Ionicons name="dice" size={18} color="#fff" /><Text style={s.ctaText}>Roll the dice</Text></>}
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
  diceRow: { flexDirection: 'row', alignItems: 'center', gap: 18, marginVertical: 36 },
  die: { width: 84, height: 84, borderRadius: 18, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center', borderWidth: 3, borderColor: COLORS.gold },
  dieTxt: { color: '#0a0c18', fontSize: 44, fontWeight: '900' },
  plus: { color: COLORS.textDim, fontSize: 26, fontWeight: '900' },
  resultCard: { width: '100%', borderRadius: RADIUS.xl, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.card, padding: SPACING.lg, alignItems: 'center', marginBottom: SPACING.md },
  resultWin: { borderColor: COLORS.gold, backgroundColor: COLORS.gold + '14' },
  winTitle: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900', marginTop: 6 },
  loseTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', textAlign: 'center' },
  winSub: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 4, textAlign: 'center' },
  codeBox: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12, paddingHorizontal: 16, paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1, borderStyle: 'dashed', borderColor: COLORS.gold, backgroundColor: COLORS.inputBg },
  codeTxt: { color: COLORS.gold, fontWeight: '900', fontSize: FONT.md, letterSpacing: 1 },
  fine: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 10, textAlign: 'center' },
  cta: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, paddingVertical: 16, width: '100%' },
  ctaText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
  used: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: SPACING.sm },
});
