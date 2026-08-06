import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, TextInput,
  ActivityIndicator, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

export default function MerchantRedeem() {
  const router = useRouter();
  const [merchant, setMerchant] = useState('m_karak');
  const [code, setCode] = useState('');
  const [user, setUser] = useState('');
  const [busy, setBusy] = useState(false);
  const [loyalty, setLoyalty] = useState<any>(null);
  const [flash, setFlash] = useState<string>('');

  const loadLoyalty = useCallback(async (m: string) => {
    if (!m) return;
    try { const r = await api.get(`/merchant/loyalty?merchant_id=${encodeURIComponent(m)}`); setLoyalty(r.data); }
    catch { /* ignore */ }
  }, []);

  useEffect(() => { loadLoyalty(merchant); }, [loadLoyalty, merchant]);

  const redeem = async () => {
    setBusy(true);
    try {
      const r = await api.post('/merchant/redeem', {
        merchant_id: merchant,
        coupon_id: code || undefined,
        user_id: user || undefined,
      });
      setLoyalty(r.data.loyalty);
      setFlash(r.data.matched_show_event
        ? 'Redeemed ✓ — matched a customer show'
        : 'Recorded — no matching customer show found');
      setCode(''); setUser('');
      await loadLoyalty(merchant);
      setTimeout(() => setFlash(''), 3500);
    } catch { Alert.alert('Error', 'Could not redeem.'); }
    finally { setBusy(false); }
  };

  const rate = loyalty ? Math.round((loyalty.rate || 0) * 100) : 0;

  return (
    <SafeAreaView style={common.screen} testID="merchant-redeem-screen">
      <View style={s.top}>
        <TouchableOpacity onPress={() => router.back()} testID="merchant-redeem-back"><Ionicons name="arrow-back" size={20} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle}>Redeem & Loyalty</Text><View style={{ width: 20 }} />
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.lg }}>
        {/* Loyalty tier card */}
        <View style={s.loyaltyCard} testID="merchant-loyalty-card">
          <Text style={s.loyaltyLabel}>YOUR LOYALTY TIER</Text>
          <Text style={s.loyaltyTier}>{loyalty?.tier || '—'} · {rate}% rate</Text>
          <Text style={s.loyaltyMeta} testID="merchant-redemptions-today">{loyalty?.redemptions_today ?? 0} redemptions today</Text>
          {loyalty?.next_tier && (
            <Text style={s.loyaltyNext}>Reach {loyalty.next_tier.min_daily}/day for {Math.round(loyalty.next_tier.rate * 100)}% ({loyalty.next_tier.name})</Text>
          )}
        </View>

        <Text style={s.label}>Merchant ID</Text>
        <TextInput style={s.input} value={merchant} onChangeText={setMerchant} testID="merchant-id-input" placeholderTextColor={COLORS.textMuted} />
        <Text style={s.label}>Coupon / code</Text>
        <TextInput style={s.input} value={code} onChangeText={setCode} testID="merchant-code-input" placeholder="coupon id or code" placeholderTextColor={COLORS.textMuted} />
        <Text style={s.label}>Customer ID (optional)</Text>
        <TextInput style={s.input} value={user} onChangeText={setUser} testID="merchant-user-input" placeholder="customer user_id" placeholderTextColor={COLORS.textMuted} />

        <TouchableOpacity style={[common.btnPrimary, { marginTop: SPACING.lg }, busy && { opacity: 0.5 }]} onPress={redeem} disabled={busy} testID="merchant-redeem-btn">
          {busy ? <ActivityIndicator color="#fff" /> : (<><Ionicons name="qr-code" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Scan / Redeem</Text></>)}
        </TouchableOpacity>

        {!!flash && (
          <View style={s.flash} testID="merchant-redeem-flash">
            <Ionicons name="checkmark-circle" size={16} color={COLORS.green} />
            <Text style={s.flashText}>{flash}</Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  top: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm },
  topTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  loyaltyCard: { backgroundColor: COLORS.primary, borderRadius: RADIUS.xl, padding: SPACING.lg, marginBottom: SPACING.lg },
  loyaltyLabel: { color: 'rgba(255,255,255,0.8)', fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1.5 },
  loyaltyTier: { color: '#fff', fontSize: FONT.xxl, fontWeight: '900', marginTop: 4 },
  loyaltyMeta: { color: '#fff', fontSize: FONT.sm, fontWeight: '700', marginTop: 6 },
  loyaltyNext: { color: 'rgba(255,255,255,0.85)', fontSize: FONT.xs, marginTop: 4 },
  label: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1, marginTop: SPACING.md, marginBottom: 6 },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.border, paddingHorizontal: 14, paddingVertical: 12, color: COLORS.text, fontSize: FONT.md, fontWeight: '600' },
  flash: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: SPACING.md, padding: SPACING.md, borderRadius: RADIUS.lg, backgroundColor: '#ecfdf5', borderWidth: 1, borderColor: '#a7f3d0' },
  flashText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', flex: 1 },
});
