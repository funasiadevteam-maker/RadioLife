// Sell on FUUSIC — business registration (single-scroll wizard).
import React, { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

const POINT_COST_CENTS = 3; // $0.03 default; server is source of truth
const SELL_OPTIONS = [
  ['menu', 'Restaurant Menu'], ['products', 'Products'], ['services', 'Services'],
  ['appointments', 'Appointments'], ['memberships', 'Memberships'],
  ['gift_cards', 'Gift Cards'], ['events', 'Events'],
];

export default function SellOnFUUSIC() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [cats, setCats] = useState<any[]>([]);
  const [existing, setExisting] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [f, setF] = useState({
    legal_name: '', public_name: '', description: '', phone: '', website: '',
    category: '', city: '', default_points: '150', points_per_dollar: '2',
  });
  const [sells, setSells] = useState<string[]>([]);
  const [commissionAgreed, setCommissionAgreed] = useState(false);
  const [parityCertified, setParityCertified] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [c, p] = await Promise.all([
          api.get('/shop/categories'),
          api.get('/merchant/marketplace/profile').catch(() => ({ data: { profile: null } })),
        ]);
        setCats(c.data.items || []);
        setExisting(p.data.profile);
      } catch { /* ignore */ }
      finally { setLoading(false); }
    })();
  }, []);

  const set = (k: string, v: string) => setF((p) => ({ ...p, [k]: v }));
  const toggleSell = (k: string) => setSells((p) => p.includes(k) ? p.filter((x) => x !== k) : [...p, k]);

  const pts = parseInt(f.default_points || '0', 10) || 0;
  const costDisplay = `$${((pts * POINT_COST_CENTS) / 100).toFixed(2)}`;
  const isRestaurant = f.category === 'restaurant';
  const selectedCat = cats.find((c) => c.key === f.category);
  const minPts = selectedCat?.min_bigpoints || 0;

  const canSubmit = f.legal_name && f.public_name && f.category && pts >= minPts
    && commissionAgreed && (!isRestaurant || parityCertified) && sells.length > 0;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    try {
      const r = await api.post('/merchant/marketplace/onboarding', {
        business_type: f.category, legal_name: f.legal_name, public_name: f.public_name,
        description: f.description || null, phone: f.phone || null, website: f.website || null,
        category: f.category, locations: f.city ? [{ city: f.city, address: '' }] : [],
        sells, bigpoints: { mode: 'default', default_points: pts,
          points_per_dollar: parseFloat(f.points_per_dollar) || 2 },
        funding_mode: 'auto_deduct', commission_agreed: commissionAgreed,
        price_parity_certified: parityCertified,
      });
      if (r.data.ok) {
        celebrate({ points: 0, title: 'Submitted for approval!' });
        router.back();
      }
    } catch (e: any) {
      celebrate({ points: 0, title: e?.response?.data?.detail?.code || 'Submission failed' });
    } finally { setBusy(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="sell-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Sell on FUUSIC</Text>
        <View style={{ width: 22 }} />
      </View>

      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : undefined} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 40 }} testID="sell-root">
          {existing && (
            <View style={s.statusCard} testID="sell-existing">
              <Ionicons name="information-circle" size={18} color={COLORS.primary} />
              <Text style={s.statusText}>
                You already have a listing ({existing.status}). Submitting again updates it.
              </Text>
            </View>
          )}

          <Text style={s.label}>BUSINESS NAME (PUBLIC)</Text>
          <TextInput style={s.input} value={f.public_name} onChangeText={(v) => set('public_name', v)}
            placeholder="e.g. The Grill House" placeholderTextColor={COLORS.textMuted} testID="sell-public-name" />

          <Text style={s.label}>LEGAL BUSINESS NAME</Text>
          <TextInput style={s.input} value={f.legal_name} onChangeText={(v) => set('legal_name', v)}
            placeholder="e.g. Grill House LLC" placeholderTextColor={COLORS.textMuted} testID="sell-legal-name" />

          <Text style={s.label}>CATEGORY</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chipRow}>
            {cats.map((c) => (
              <TouchableOpacity key={c.key} style={[s.chip, f.category === c.key && s.chipOn]}
                onPress={() => set('category', c.key)} testID={`sell-cat-${c.key}`}>
                <Text style={[s.chipText, f.category === c.key && s.chipTextOn]}>{c.name}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <Text style={s.label}>WHAT DO YOU SELL?</Text>
          <View style={s.wrapRow}>
            {SELL_OPTIONS.map(([k, label]) => (
              <TouchableOpacity key={k} style={[s.chip, sells.includes(k) && s.chipOn]}
                onPress={() => toggleSell(k)} testID={`sell-offer-${k}`}>
                <Text style={[s.chipText, sells.includes(k) && s.chipTextOn]}>{label}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={s.label}>CITY</Text>
          <TextInput style={s.input} value={f.city} onChangeText={(v) => set('city', v)}
            placeholder="e.g. Dubai" placeholderTextColor={COLORS.textMuted} testID="sell-city" />

          <Text style={s.label}>PHONE (OPTIONAL)</Text>
          <TextInput style={s.input} value={f.phone} onChangeText={(v) => set('phone', v)}
            keyboardType="phone-pad" placeholder="+971 ..." placeholderTextColor={COLORS.textMuted} testID="sell-phone" />

          <Text style={s.label}>DESCRIPTION (OPTIONAL)</Text>
          <TextInput style={[s.input, { height: 74, textAlignVertical: 'top' }]} multiline
            value={f.description} onChangeText={(v) => set('description', v)}
            placeholder="Tell customers about your business" placeholderTextColor={COLORS.textMuted} testID="sell-desc" />

          <Text style={s.section}>BigPoints Reward</Text>
          <Text style={s.hint}>Choose how many BigPoints customers earn. BigPoints help attract & retain FUUSIC customers.</Text>

          <Text style={s.label}>BIGPOINTS PER TRANSACTION</Text>
          <TextInput style={s.input} value={f.default_points} onChangeText={(v) => set('default_points', v)}
            keyboardType="number-pad" placeholder="150" placeholderTextColor={COLORS.textMuted} testID="sell-points" />
          {minPts > 0 && pts < minPts && (
            <Text style={s.warn}>Minimum for {selectedCat?.name} is {minPts} BigPoints.</Text>
          )}

          <View style={s.costCard} testID="sell-cost-preview">
            <View>
              <Text style={s.costLabel}>YOUR BIGPOINTS COST</Text>
              <Text style={s.costCalc}>{pts} × $0.03</Text>
            </View>
            <Text style={s.costValue}>{costDisplay}</Text>
          </View>

          <TouchableOpacity style={s.checkRow} onPress={() => setCommissionAgreed((v) => !v)} testID="sell-commission-agree">
            <Ionicons name={commissionAgreed ? 'checkbox' : 'square-outline'} size={22}
              color={commissionAgreed ? COLORS.primary : COLORS.textMuted} />
            <Text style={s.checkText}>I agree to the FUUSIC commission for my category
              {selectedCat ? ` (${selectedCat.commission_pct}%)` : ''}.</Text>
          </TouchableOpacity>

          {isRestaurant && (
            <TouchableOpacity style={s.checkRow} onPress={() => setParityCertified((v) => !v)} testID="sell-parity">
              <Ionicons name={parityCertified ? 'checkbox' : 'square-outline'} size={22}
                color={parityCertified ? COLORS.primary : COLORS.textMuted} />
              <Text style={s.checkText}>I certify my FUUSIC menu prices match my own website&apos;s prices.</Text>
            </TouchableOpacity>
          )}

          <TouchableOpacity
            style={[common.btnPrimary, { marginTop: 18 }, !canSubmit && { opacity: 0.5 }]}
            onPress={submit} disabled={busy || !canSubmit} testID="sell-submit">
            {busy ? <ActivityIndicator color="#fff" />
              : <><Ionicons name="checkmark-circle" size={16} color="#fff" />
                <Text style={common.btnPrimaryText}>Submit for Approval</Text></>}
          </TouchableOpacity>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  statusCard: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary + '10', borderWidth: 1, borderColor: COLORS.primary + '44', borderRadius: RADIUS.md, padding: 12, marginBottom: SPACING.md },
  statusText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '700', flex: 1 },
  label: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.1, marginTop: SPACING.md, marginBottom: 6 },
  input: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, paddingHorizontal: 12, paddingVertical: 11, color: COLORS.text, fontSize: FONT.sm },
  chipRow: { gap: 8, paddingVertical: 2 },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { flexShrink: 0, paddingHorizontal: 14, paddingVertical: 9, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  chipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  chipTextOn: { color: '#fff' },
  section: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', marginTop: SPACING.lg },
  hint: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 4, marginBottom: 4 },
  warn: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700', marginTop: 6 },
  costCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.gold + '18', borderRadius: RADIUS.lg, padding: 16, marginTop: 14 },
  costLabel: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  costCalc: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', marginTop: 2 },
  costValue: { color: COLORS.text, fontSize: 24, fontWeight: '900' },
  checkRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, marginTop: 14 },
  checkText: { flex: 1, color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', lineHeight: 19 },
});
