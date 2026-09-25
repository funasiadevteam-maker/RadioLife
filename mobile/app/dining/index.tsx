// Dining Club — mobile home + enrollment (Expo). Warm theme, Bearer auth.
import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useAuth } from '../../src/contexts/AuthContext';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

const money = (c?: number) => `$${(((c ?? 0)) / 100).toFixed(2)}`;

export default function DiningHome() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [home, setHome] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [meals, setMeals] = useState(5);
  const [veg, setVeg] = useState<'VEG' | 'NON_VEG'>('VEG');

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const load = useCallback(async () => {
    try { const r = await api.get('/dining-club'); setHome(r.data); }
    catch { /* ignore */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { if (!authLoading && user) load(); }, [load, authLoading, user]);

  const subscribe = async () => {
    setBusy(true);
    try {
      const r = await api.post('/dining-club/subscribe', { meals_per_week: meals, veg_default: veg });
      if (r.data.requires_payment && r.data.checkout_url) { Linking.openURL(r.data.checkout_url); }
      else { await load(); }
    } catch (e: any) {
      // surfaced inline; keep simple
    } finally { setBusy(false); }
  };

  if (loading) {
    return <SafeAreaView style={s.screen}><View style={s.center}><ActivityIndicator color={COLORS.primary} /></View></SafeAreaView>;
  }

  const m = home?.membership;
  const c = home?.credits || {};
  const notPremium = home?.premium_required && !home?.is_premium;
  const premiumPrice = home?.premium_price?.amount_cents;

  return (
    <SafeAreaView style={s.screen} testID="dining-home">
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="dining-back"><Ionicons name="chevron-back" size={24} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.headerTitle}>Dining Club</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}>
        <LinearGradient colors={['#F26B2A', '#F59E0B']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <Text style={s.heroKicker}>FUUSIC DINING CLUB</Text>
          <Text style={s.heroTitle}>Stop deciding{'\n'}where to eat.</Text>
          <Text style={s.heroSub}>Choose Veg or Non-Veg — we spin you a surprise restaurant. Every meal a flat {money(home?.meal_price_cents)}.</Text>
        </LinearGradient>

        <TouchableOpacity onPress={() => router.push('/dining/dice')} testID="dining-dice-cta"
          style={{ flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: SPACING.md, padding: SPACING.md, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.gold + '55', backgroundColor: COLORS.gold + '14' }}>
          <Ionicons name="dice" size={20} color={COLORS.gold} />
          <View style={{ flex: 1 }}>
            <Text style={{ color: COLORS.text, fontWeight: '900', fontSize: FONT.md }}>Roll the dice — win a free meal for 8</Text>
            <Text style={{ color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 }}>1 in 12 chance · one roll a day</Text>
          </View>
          <Ionicons name="arrow-forward" size={18} color={COLORS.gold} />
        </TouchableOpacity>

        {m && m.status === 'active' ? (
          <>
            <View style={s.statsRow}>
              <Stat icon="restaurant" v={c.available ?? 0} l="Meals" />
              <Stat icon="time" v={c.expiring_soon ?? 0} l="Expiring" />
              <Stat icon="calendar" v={home?.days_remaining ?? 0} l="Days left" />
            </View>
            <TouchableOpacity style={s.cta} onPress={() => router.push('/dining/play')} testID="dining-use-meal-btn">
              <Ionicons name="sparkles" size={18} color="#fff" /><Text style={s.ctaText}>Use a Meal</Text>
            </TouchableOpacity>
            <Text style={s.metaLine}>{m.meals_per_week} meals/week · Premium member</Text>
          </>
        ) : (
          <View style={s.card} testID="dining-enroll">
            {notPremium && (
              <View style={s.bundle}>
                <Ionicons name="star" size={16} color={COLORS.gold} />
                <Text style={s.bundleText}>Premium-only benefit. Joining bundles FUUSIC Annual Premium{premiumPrice ? ` (${money(premiumPrice)}/yr)` : ''} + Dining Club.</Text>
              </View>
            )}
            <Text style={s.label}>MEALS PER WEEK</Text>
            <View style={s.stepper}>
              <TouchableOpacity style={s.stepBtn} onPress={() => setMeals(Math.max(3, meals - 1))} testID="meals-dec"><Ionicons name="remove" size={22} color={COLORS.text} /></TouchableOpacity>
              <Text style={s.stepVal} testID="meals-val">{meals}</Text>
              <TouchableOpacity style={s.stepBtn} onPress={() => setMeals(Math.min(14, meals + 1))} testID="meals-inc"><Ionicons name="add" size={22} color={COLORS.text} /></TouchableOpacity>
            </View>
            <Text style={s.hint}>Min 3 · Max 14 · {meals * 4} meal credits over 30 days</Text>

            <Text style={[s.label, { marginTop: SPACING.md }]}>DEFAULT PREFERENCE</Text>
            <View style={s.prefRow}>
              <Pref active={veg === 'VEG'} onPress={() => setVeg('VEG')} icon="leaf" label="Veg" color={COLORS.green} />
              <Pref active={veg === 'NON_VEG'} onPress={() => setVeg('NON_VEG')} icon="flame" label="Non-Veg" color={COLORS.primary} />
            </View>

            <TouchableOpacity style={[s.cta, { marginTop: SPACING.lg }]} onPress={subscribe} disabled={busy} testID="dining-join">
              {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="restaurant" size={18} color="#fff" /><Text style={s.ctaText}>Join Dining Club</Text></>}
            </TouchableOpacity>
          </View>
        )}

        <TouchableOpacity style={s.ghost} onPress={() => Linking.openURL(`${process.env.EXPO_PUBLIC_BACKEND_URL}/dining/merchant`)} testID="dining-merchant-link">
          <Ionicons name="storefront-outline" size={16} color={COLORS.textDim} /><Text style={s.ghostText}>Restaurant portal</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ icon, v, l }: any) {
  return (
    <View style={s.stat}>
      <Ionicons name={icon} size={18} color={COLORS.primary} />
      <Text style={s.statVal}>{v}</Text>
      <Text style={s.statLabel}>{l}</Text>
    </View>
  );
}
function Pref({ active, onPress, icon, label, color }: any) {
  return (
    <TouchableOpacity style={[s.pref, active && { borderColor: color, backgroundColor: color + '18' }]} onPress={onPress} testID={`pref-${label}`}>
      <Ionicons name={icon} size={18} color={active ? color : COLORS.textMuted} />
      <Text style={[s.prefText, active && { color }]}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  headerTitle: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text },
  hero: { borderRadius: RADIUS.xl, padding: SPACING.lg, marginBottom: SPACING.lg },
  heroKicker: { color: 'rgba(255,255,255,0.85)', fontSize: FONT.xs, fontWeight: '800', letterSpacing: 2, marginBottom: 8 },
  heroTitle: { color: '#fff', fontSize: FONT.hero, fontWeight: '900', lineHeight: 40 },
  heroSub: { color: 'rgba(255,255,255,0.92)', fontSize: FONT.md, marginTop: 10 },
  statsRow: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.lg },
  stat: { flex: 1, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, alignItems: 'center' },
  statVal: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, marginTop: 4 },
  statLabel: { fontSize: FONT.xs, color: COLORS.textMuted, textTransform: 'uppercase', letterSpacing: 1 },
  cta: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, paddingVertical: 16 },
  ctaText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
  metaLine: { textAlign: 'center', color: COLORS.textMuted, fontSize: FONT.sm, marginTop: SPACING.sm },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.xl, padding: SPACING.lg },
  bundle: { flexDirection: 'row', gap: 8, backgroundColor: COLORS.gold + '18', borderRadius: RADIUS.md, padding: SPACING.md, marginBottom: SPACING.md },
  bundleText: { flex: 1, color: COLORS.textDim, fontSize: FONT.sm },
  label: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5, marginBottom: 8 },
  stepper: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.inputBg, borderRadius: RADIUS.lg, padding: SPACING.sm },
  stepBtn: { width: 48, height: 48, borderRadius: RADIUS.md, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.cardBorder },
  stepVal: { fontSize: 32, fontWeight: '900', color: COLORS.text },
  hint: { color: COLORS.textMuted, fontSize: FONT.sm, marginTop: 8 },
  prefRow: { flexDirection: 'row', gap: SPACING.sm },
  pref: { flex: 1, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', paddingVertical: 14, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg },
  prefText: { fontWeight: '700', color: COLORS.textMuted },
  ghost: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', marginTop: SPACING.lg, paddingVertical: 12 },
  ghostText: { color: COLORS.textDim, fontWeight: '600' },
});
