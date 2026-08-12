// Merchant self-serve coupons — create / toggle / delete. Mobile.
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;

export default function MerchantCoupons() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [code, setCode] = useState('');
  const [type, setType] = useState<'percent' | 'amount'>('percent');
  const [value, setValue] = useState('10');
  const [minSpend, setMinSpend] = useState('');

  const load = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/coupons'); setItems(r.data.items || []); }
    catch { /* no profile */ } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const create = async () => {
    setBusy(true); setError(null);
    try {
      await api.post('/merchant/marketplace/coupons', {
        code: code.trim().toUpperCase(), type, value: Number(value),
        min_spend_cents: Math.round(Number(minSpend || 0)), per_user_limit: 1,
      });
      setCode(''); setValue('10'); setMinSpend(''); load();
    } catch (e: any) { setError(e?.response?.data?.detail?.code || 'Could not create'); }
    finally { setBusy(false); }
  };

  const toggle = async (c: any) => {
    await api.patch(`/merchant/marketplace/coupons/${c.coupon_id}`, {
      code: c.code, type: c.type, value: c.value, min_spend_cents: c.min_spend_cents,
      max_discount_cents: c.max_discount_cents, usage_limit: c.usage_limit,
      per_user_limit: c.per_user_limit, active: !c.active });
    load();
  };
  const remove = async (c: any) => { await api.delete(`/merchant/marketplace/coupons/${c.coupon_id}`); load(); };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="merchant-coupons-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Coupons</Text>
        <View style={{ width: 22 }} />
      </View>

      {loading ? <View style={common.center}><ActivityIndicator color={COLORS.primary} /></View> : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="merchant-coupons-root">
          <View style={s.form} testID="merchant-coupon-form">
            <Text style={s.formTitle}>New coupon</Text>
            <TextInput style={s.input} value={code} onChangeText={setCode} autoCapitalize="characters"
              placeholder="CODE (e.g. SAVE10)" placeholderTextColor={COLORS.textMuted} testID="coupon-code-input" />
            <View style={s.typeRow}>
              <TouchableOpacity style={[s.typeBtn, type === 'percent' && s.typeOn]} onPress={() => setType('percent')} testID="coupon-type-percent">
                <Text style={[s.typeText, type === 'percent' && { color: COLORS.primary }]}>% Percent</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.typeBtn, type === 'amount' && s.typeOn]} onPress={() => setType('amount')} testID="coupon-type-amount">
                <Text style={[s.typeText, type === 'amount' && { color: COLORS.primary }]}>$ Amount</Text>
              </TouchableOpacity>
            </View>
            <Text style={s.label}>{type === 'percent' ? 'Percent off (1–100)' : 'Amount off (cents)'}</Text>
            <TextInput style={s.input} value={value} onChangeText={setValue} keyboardType="number-pad" testID="coupon-value-input" />
            <Text style={s.label}>Minimum spend (cents, optional)</Text>
            <TextInput style={s.input} value={minSpend} onChangeText={setMinSpend} keyboardType="number-pad" testID="coupon-minspend-input" />
            {!!error && <Text style={s.err} testID="merchant-coupon-error">{error}</Text>}
            <TouchableOpacity style={[common.btnPrimary, (busy || !code.trim()) && { opacity: 0.5 }]} disabled={busy || !code.trim()}
              onPress={create} testID="coupon-create-btn">
              {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="add" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Create coupon</Text></>}
            </TouchableOpacity>
          </View>

          <Text style={s.section}>Your coupons</Text>
          {!items.length ? <Text style={s.empty} testID="merchant-coupons-empty">No coupons yet.</Text>
            : items.map((c) => (
              <View key={c.coupon_id} style={s.card} testID={`merchant-coupon-${c.coupon_id}`}>
                <View style={s.cardIcon}><Ionicons name="pricetag" size={16} color={COLORS.primary} /></View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.cardName}>{c.code} · {c.type === 'percent' ? `${c.value}% off` : `${money(c.value)} off`}</Text>
                  <Text style={s.cardSub}>{c.min_spend_cents > 0 ? `Min ${money(c.min_spend_cents)} · ` : ''}used {c.used_count}{c.usage_limit ? `/${c.usage_limit}` : ''}</Text>
                </View>
                <TouchableOpacity onPress={() => toggle(c)} testID={`coupon-toggle-${c.coupon_id}`}
                  style={[s.badge, { backgroundColor: c.active ? COLORS.green + '18' : COLORS.inputBg }]}>
                  <Text style={[s.badgeText, { color: c.active ? COLORS.green : COLORS.textMuted }]}>{c.active ? 'Active' : 'Off'}</Text>
                </TouchableOpacity>
                <TouchableOpacity onPress={() => remove(c)} testID={`coupon-remove-${c.coupon_id}`} style={s.removeBtn}>
                  <Ionicons name="trash-outline" size={16} color={COLORS.red} />
                </TouchableOpacity>
              </View>
            ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  form: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 14, gap: 10 },
  formTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  typeRow: { flexDirection: 'row', gap: 8 },
  typeBtn: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg },
  typeOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '12' },
  typeText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '900' },
  label: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  err: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '800' },
  section: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: 20, marginBottom: 10 },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  card: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 10 },
  cardIcon: { width: 38, height: 38, borderRadius: 12, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  cardName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  cardSub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  badge: { borderRadius: RADIUS.full, paddingHorizontal: 10, paddingVertical: 5 },
  badgeText: { fontSize: 11, fontWeight: '900' },
  removeBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
});
