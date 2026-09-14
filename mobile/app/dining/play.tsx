// Dining Club — mobile Use-a-Meal: pick → spin wheel / surprise → reveal → reroll → accept → pay.
import React, { useState, useCallback, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import Svg, { Path, Circle, G, Text as SvgText } from 'react-native-svg';
import Animated, { useSharedValue, useAnimatedStyle, withTiming, Easing, runOnJS } from 'react-native-reanimated';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

const money = (c?: number) => `$${(((c ?? 0)) / 100).toFixed(2)}`;
const WHEEL = 280;
const SEG_COLORS = ['#F26B2A', '#F59E0B', '#3B82F6', '#16A34A', '#7C3AED', '#E11D48'];

function polar(cx: number, cy: number, r: number, ang: number) {
  const a = (ang - 90) * Math.PI / 180;
  return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
}
function wedge(cx: number, cy: number, r: number, start: number, end: number) {
  const s = polar(cx, cy, r, end), e = polar(cx, cy, r, start);
  const large = end - start <= 180 ? 0 : 1;
  return `M ${cx} ${cy} L ${s.x} ${s.y} A ${r} ${r} 0 ${large} 0 ${e.x} ${e.y} Z`;
}

function Wheel({ segments, rotation }: { segments: number; rotation: any }) {
  const cx = WHEEL / 2, cy = WHEEL / 2, r = WHEEL / 2 - 6;
  const seg = 360 / segments;
  const style = useAnimatedStyle(() => ({ transform: [{ rotate: `${rotation.value}deg` }] }));
  return (
    <View style={{ width: WHEEL, height: WHEEL, alignItems: 'center', justifyContent: 'center' }}>
      <View style={s.pointer} />
      <Animated.View style={style}>
        <Svg width={WHEEL} height={WHEEL}>
          <G>
            {Array.from({ length: segments }).map((_, i) => {
              const start = i * seg, end = (i + 1) * seg;
              const mid = polar(cx, cy, r * 0.66, start + seg / 2);
              return (
                <G key={i}>
                  <Path d={wedge(cx, cy, r, start, end)} fill={SEG_COLORS[i % SEG_COLORS.length]} stroke="#fff" strokeWidth={2} />
                  <SvgText x={mid.x} y={mid.y} fill="#fff" fontSize={16} fontWeight="bold" textAnchor="middle">{i + 1}</SvgText>
                </G>
              );
            })}
            <Circle cx={cx} cy={cy} r={26} fill="#fff" />
          </G>
        </Svg>
      </Animated.View>
      <View style={s.hub}><Ionicons name="restaurant" size={22} color={COLORS.primary} /></View>
    </View>
  );
}

export default function DiningPlay() {
  const router = useRouter();
  const rotation = useSharedValue(0);
  const [phase, setPhase] = useState<'choose' | 'wheel' | 'reveal'>('choose');
  const [veg, setVeg] = useState<'VEG' | 'NON_VEG'>('VEG');
  const [period, setPeriod] = useState<'LUNCH' | 'DINNER'>('LUNCH');
  const [session, setSession] = useState<any>(null);
  const [pre, setPre] = useState<any>(null);
  const [winner, setWinner] = useState<any>(null);
  const [canReroll, setCanReroll] = useState(false);
  const [segments, setSegments] = useState(10);
  const [busy, setBusy] = useState(false);
  const [spinning, setSpinning] = useState(false);
  const [err, setErr] = useState('');
  const [lastPref, setLastPref] = useState<any>(null);

  useEffect(() => {
    api.get('/dining-club').then((r) => {
      const lp = r.data?.last_pref;
      if (lp?.veg_preference) {
        setLastPref(lp);
        setVeg(lp.veg_preference === 'NON_VEG' ? 'NON_VEG' : 'VEG');
        setPeriod(lp.meal_period === 'DINNER' ? 'DINNER' : 'LUNCH');
      }
    }).catch(() => {});
  }, []);

  const start = async (override?: { veg: 'VEG' | 'NON_VEG'; period: 'LUNCH' | 'DINNER' }) => {
    const v = override?.veg || veg;
    const p = override?.period || period;
    if (override) { setVeg(v); setPeriod(p); }
    setBusy(true); setErr('');
    try {
      const r = await api.post('/dining-club/selection/start', { veg_preference: v, meal_period: p });
      const sess = r.data.session;
      setSession(sess); setPre(sess.pre_spin);
      setSegments(Math.min(10, sess.pre_spin?.restaurants_available || 10));
      if (['FIRST_RESULT', 'FINAL_RESULT'].includes(sess.status)) {
        const v = await api.get(`/dining-club/selection/${sess.session_id}`);
        setWinner(v.data.winner); setCanReroll(v.data.can_reroll); setPhase('reveal');
      } else { setPhase('wheel'); }
    } catch (e: any) { setErr(e?.response?.data?.detail?.code || 'Could not start'); }
    finally { setBusy(false); }
  };

  const reveal = useCallback((w: any, reroll: boolean) => {
    setWinner(w); setCanReroll(reroll); setSpinning(false); setPhase('reveal');
  }, []);

  const doSpin = async (method: 'wheel' | 'random') => {
    if (spinning) return;
    setSpinning(true); setErr('');
    try {
      const r = await api.post(`/dining-club/selection/${session.session_id}/${method === 'wheel' ? 'spin' : 'random'}`);
      const { winner: w, winner_index, segments: segs, can_reroll } = r.data;
      if (method === 'random') { reveal(w, can_reroll); return; }
      const n = segs || segments;
      const seg = 360 / n;
      const desiredMod = (360 - (winner_index + 0.5) * seg) % 360;
      const currentMod = ((rotation.value % 360) + 360) % 360;
      const delta = (desiredMod - currentMod + 360) % 360;
      const target = rotation.value + 360 * 5 + delta;
      rotation.value = withTiming(target, { duration: 2800, easing: Easing.out(Easing.cubic) }, (fin) => {
        if (fin) runOnJS(reveal)(w, can_reroll);
      });
    } catch (e: any) { setSpinning(false); setErr(e?.response?.data?.detail?.code || 'Spin failed'); }
  };

  const doReroll = async () => {
    setBusy(true);
    try { await api.post(`/dining-club/selection/${session.session_id}/reroll`); setWinner(null); setPhase('wheel'); }
    catch (e: any) { setErr(e?.response?.data?.detail?.code || 'Reroll failed'); }
    finally { setBusy(false); }
  };

  const doAccept = async () => {
    setBusy(true);
    try {
      const a = await api.post(`/dining-club/selection/${session.session_id}/accept`);
      const orderId = a.data.order_id;
      const co = await api.post('/dining-club/checkout', { order_id: orderId, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL });
      if (co.data.requires_payment && co.data.checkout_url) {
        Linking.openURL(co.data.checkout_url);
        router.push(`/dining/pass?order_id=${orderId}` as any);
      } else {
        router.push(`/dining/pass?order_id=${orderId}` as any);
      }
    } catch (e: any) { setErr(e?.response?.data?.detail?.code || 'Could not reserve'); }
    finally { setBusy(false); }
  };

  const abandon = async () => {
    try { await api.post(`/dining-club/selection/${session.session_id}/abandon`); } catch { /* ignore */ }
    router.back();
  };

  return (
    <SafeAreaView style={s.screen} testID="dining-play">
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="play-back"><Ionicons name="chevron-back" size={24} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.headerTitle}>Your Dining Wheel</Text><View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, alignItems: 'center', paddingBottom: 60 }}>
        {err ? <Text style={s.err} testID="play-error">{err.replace(/_/g, ' ')}</Text> : null}

        {phase === 'choose' && (
          <View style={{ width: '100%' }} testID="play-choose">
            <Text style={s.h1}>Where are you eating today?</Text>
            <Text style={s.sub}>Pick a preference — up to 10 restaurants behind the wheel.</Text>
            {lastPref ? (
              <TouchableOpacity style={s.quickPlay} disabled={busy} testID="dining-quickplay-btn"
                onPress={() => start({ veg: lastPref.veg_preference === 'NON_VEG' ? 'NON_VEG' : 'VEG', period: lastPref.meal_period === 'DINNER' ? 'DINNER' : 'LUNCH' })}>
                {busy ? <ActivityIndicator color={COLORS.gold} /> : <Ionicons name="flash" size={18} color={COLORS.gold} />}
                <View style={{ flex: 1 }}>
                  <Text style={s.quickPlayText}>Quick play — {lastPref.veg_preference === 'VEG' ? 'Veg' : 'Non-Veg'} · {lastPref.meal_period === 'DINNER' ? 'Dinner' : 'Lunch'}</Text>
                  <Text style={s.quickPlaySub}>Straight to the wheel</Text>
                </View>
                <Ionicons name="arrow-forward" size={18} color={COLORS.primary} />
              </TouchableOpacity>
            ) : null}
            <Text style={s.label}>PREFERENCE</Text>
            <View style={s.row}>
              <Choice active={veg === 'VEG'} onPress={() => setVeg('VEG')} icon="leaf" label="Veg" color={COLORS.green} />
              <Choice active={veg === 'NON_VEG'} onPress={() => setVeg('NON_VEG')} icon="flame" label="Non-Veg" color={COLORS.primary} />
            </View>
            <Text style={[s.label, { marginTop: SPACING.md }]}>MEAL</Text>
            <View style={s.row}>
              <Choice active={period === 'LUNCH'} onPress={() => setPeriod('LUNCH')} icon="sunny" label="Lunch" color={COLORS.gold} />
              <Choice active={period === 'DINNER'} onPress={() => setPeriod('DINNER')} icon="moon" label="Dinner" color={COLORS.secondary} />
            </View>
            <TouchableOpacity style={[s.cta, { marginTop: SPACING.lg }]} onPress={() => start()} disabled={busy} testID="play-find">
              {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="sparkles" size={18} color="#fff" /><Text style={s.ctaText}>Find my restaurants</Text></>}
            </TouchableOpacity>
          </View>
        )}

        {phase === 'wheel' && (
          <View style={{ alignItems: 'center', width: '100%' }} testID="play-wheel">
            <Text style={s.h1}>{segments} restaurants. One surprise.</Text>
            <Text style={s.sub}>{pre?.within_miles ? `Within ~${pre.within_miles} miles · ` : ''}{(pre?.cuisine_mix || []).slice(0, 4).join(' · ')}</Text>
            <Wheel segments={segments} rotation={rotation} />
            <TouchableOpacity style={[s.cta, { marginTop: SPACING.lg }]} onPress={() => doSpin('wheel')} disabled={spinning} testID="dining-spin-btn">
              <Ionicons name="disc" size={18} color="#fff" /><Text style={s.ctaText}>{spinning ? 'Spinning…' : 'Spin for my restaurant'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={s.ghost} onPress={() => doSpin('random')} disabled={spinning} testID="dining-surprise-btn">
              <Ionicons name="shuffle" size={16} color={COLORS.textDim} /><Text style={s.ghostText}>Surprise me</Text>
            </TouchableOpacity>
          </View>
        )}

        {phase === 'reveal' && winner && (
          <View style={{ width: '100%' }} testID="play-reveal">
            <Text style={s.kicker}>YOU GOT</Text>
            <Text style={s.winner} testID="reveal-name">{winner.name}</Text>
            <Text style={s.sub}>{winner.cuisine} · {String(winner.restaurant_class || '').replace('_', ' ')} · {winner.distance_miles} mi</Text>
            <View style={s.mealCard}>
              <Text style={s.mealKicker}>TODAY'S {veg === 'VEG' ? 'VEG' : 'NON-VEG'} MEAL</Text>
              <Text style={s.mealTitle}>{winner.todays_meal?.title || "Chef's selected meal"}</Text>
              <Text style={s.price}>{money(winner.meal_price_cents ?? 999)}</Text>
            </View>
            <Text style={s.addr}><Ionicons name="location" size={14} color={COLORS.primary} /> {winner.address}</Text>
            <TouchableOpacity style={[s.cta, { marginTop: SPACING.md }]} onPress={doAccept} disabled={busy} testID="dining-accept-btn">
              {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="checkmark-circle" size={18} color="#fff" /><Text style={s.ctaText}>Accept · pay {money(winner.meal_price_cents ?? 999)}</Text></>}
            </TouchableOpacity>
            {canReroll ? (
              <TouchableOpacity style={s.ghost} onPress={doReroll} disabled={busy} testID="dining-reroll-btn">
                <Ionicons name="refresh" size={16} color={COLORS.textDim} /><Text style={s.ghostText}>Not feeling it? One more spin</Text>
              </TouchableOpacity>
            ) : (
              <TouchableOpacity style={s.ghost} onPress={abandon} testID="reveal-exit">
                <Text style={s.ghostText}>Exit without using a meal</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function Choice({ active, onPress, icon, label, color }: any) {
  const tid = { "Veg": "dining-pref-veg", "Non-Veg": "dining-pref-nonveg",
                "Lunch": "dining-period-lunch", "Dinner": "dining-period-dinner" }[label] || `choice-${label}`;
  return (
    <TouchableOpacity style={[s.choice, active && { borderColor: color, backgroundColor: color + '18' }]} onPress={onPress} testID={tid}>
      <Ionicons name={icon} size={18} color={active ? color : COLORS.textMuted} />
      <Text style={[s.choiceText, active && { color }]}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  headerTitle: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text },
  h1: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, textAlign: 'center' },
  sub: { fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center', marginTop: 6, marginBottom: SPACING.md },
  label: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5, marginBottom: 8 },
  row: { flexDirection: 'row', gap: SPACING.sm },
  choice: { flex: 1, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', paddingVertical: 14, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg },
  choiceText: { fontWeight: '700', color: COLORS.textMuted },
  quickPlay: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, backgroundColor: COLORS.gold + '18', borderWidth: 1, borderColor: COLORS.gold + '66', borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.lg },
  quickPlayText: { color: COLORS.text, fontWeight: '900', fontSize: FONT.md },
  quickPlaySub: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 1 },
  cta: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, paddingVertical: 16, width: '100%' },
  ctaText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
  ghost: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', marginTop: SPACING.md, paddingVertical: 12 },
  ghostText: { color: COLORS.textDim, fontWeight: '600' },
  pointer: { position: 'absolute', top: -2, zIndex: 3, width: 0, height: 0, borderLeftWidth: 12, borderRightWidth: 12, borderTopWidth: 20, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: COLORS.text },
  hub: { position: 'absolute', width: 52, height: 52, borderRadius: 26, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center', borderWidth: 2, borderColor: COLORS.primary },
  kicker: { color: COLORS.primary, fontWeight: '800', letterSpacing: 2, textAlign: 'center', fontSize: FONT.xs },
  winner: { fontSize: FONT.hero, fontWeight: '900', color: COLORS.text, textAlign: 'center' },
  mealCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.xl, padding: SPACING.lg, alignItems: 'center', marginTop: SPACING.md },
  mealKicker: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5 },
  mealTitle: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text, marginTop: 6, textAlign: 'center' },
  price: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.gold, marginTop: 6 },
  addr: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: SPACING.md },
  err: { color: COLORS.red, fontWeight: '700', marginBottom: SPACING.sm, textTransform: 'capitalize' },
});
