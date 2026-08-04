import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, Alert, ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { useAuth } from '../../src/contexts/AuthContext';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const MARKETS = [
  { value: 'dubai', label: 'Dubai' },
  { value: 'dfw', label: 'DFW' },
  { value: 'global_sa', label: 'Global SA' },
];

export default function AdvertiserOnboard() {
  const router = useRouter();
  const { refresh } = useAuth();
  const [step, setStep] = useState(1);
  const [form, setForm] = useState({
    name: '', contact_email: '', contact_phone: '',
    market: 'dubai', address: '',
  });
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!form.name || !form.contact_email) {
      Alert.alert('Required', 'Business name + contact email are required');
      setStep(1);
      return;
    }
    setBusy(true);
    try {
      const r = await api.post('/advertiser/onboard', form);
      Alert.alert('Success', 'Advertiser account created');
      await refresh();
      router.replace('/advertiser');
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not onboard');
    } finally {
      setBusy(false);
    }
  };

  const stepLabels = ['Profile', 'Stripe', 'Team'];

  return (
    <SafeAreaView style={common.screen} testID="advertiser-onboard">
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} testID="onboard-back">
            <Ionicons name="arrow-back" size={20} color={COLORS.textDim} />
          </TouchableOpacity>

          <Text style={s.title}>Start advertising on BigFM</Text>
          <Text style={s.subtitle}>
            Reach the diaspora through AI radio. Top up your ad wallet, build a
            campaign in 5 steps, go live in minutes.
          </Text>

          {/* Step indicator */}
          <View style={s.stepRow}>
            {stepLabels.map((label, i) => (
              <View
                key={label}
                style={[s.stepPill, step >= i + 1 && s.stepPillActive]}
              >
                <Text style={[s.stepPillText, step >= i + 1 && s.stepPillTextActive]}>
                  {i + 1}. {label}
                </Text>
              </View>
            ))}
          </View>

          {/* Step 1: Profile */}
          {step === 1 && (
            <View testID="onboard-step-profile">
              <Text style={common.label}>BUSINESS NAME</Text>
              <TextInput
                style={common.input}
                placeholderTextColor={COLORS.textMuted}
                placeholder="Karak Cafe"
                value={form.name}
                onChangeText={(t) => setForm({ ...form, name: t })}
                testID="mobile-advertiser-onboard-name"
              />

              <Text style={[common.label, { marginTop: SPACING.md }]}>CONTACT EMAIL</Text>
              <TextInput
                style={common.input}
                placeholderTextColor={COLORS.textMuted}
                placeholder="ads@yourbusiness.com"
                keyboardType="email-address"
                autoCapitalize="none"
                value={form.contact_email}
                onChangeText={(t) => setForm({ ...form, contact_email: t })}
                testID="mobile-advertiser-onboard-email"
              />

              <Text style={[common.label, { marginTop: SPACING.md }]}>PHONE (OPTIONAL)</Text>
              <TextInput
                style={common.input}
                placeholderTextColor={COLORS.textMuted}
                placeholder="+971 50 000 0000"
                keyboardType="phone-pad"
                value={form.contact_phone}
                onChangeText={(t) => setForm({ ...form, contact_phone: t })}
                testID="mobile-advertiser-onboard-phone"
              />

              <Text style={[common.label, { marginTop: SPACING.md }]}>PRIMARY MARKET</Text>
              <View style={s.marketRow}>
                {MARKETS.map((m) => (
                  <TouchableOpacity
                    key={m.value}
                    style={[s.marketChip, form.market === m.value && s.marketChipActive]}
                    onPress={() => setForm({ ...form, market: m.value })}
                    testID={`onboard-market-${m.value}`}
                  >
                    <Text style={[s.marketChipText, form.market === m.value && s.marketChipTextActive]}>
                      {m.label}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>

              <TouchableOpacity style={[common.btnPrimary, { marginTop: SPACING.lg }]} onPress={() => setStep(2)} testID="onboard-next-1">
                <Text style={common.btnPrimaryText}>Continue</Text>
                <Ionicons name="arrow-forward" size={16} color="#fff" />
              </TouchableOpacity>
            </View>
          )}

          {/* Step 2: Stripe info */}
          {step === 2 && (
            <View testID="onboard-step-stripe">
              <View style={common.card}>
                <Text style={s.cardText}>
                  We will create a Stripe customer for your account. You can top
                  up your ad wallet later from the Billing page.
                </Text>
                <View style={{ marginTop: SPACING.sm }}>
                  <Text style={s.bulletText}>• No charge today.</Text>
                  <Text style={s.bulletText}>• Card on file via Stripe Checkout when you fund balance.</Text>
                  <Text style={s.bulletText}>• You can pause / refund unspent balance any time.</Text>
                </View>
              </View>
              <View style={[s.navRow, { marginTop: SPACING.lg }]}>
                <TouchableOpacity style={common.btnGhost} onPress={() => setStep(1)}>
                  <Text style={common.btnGhostText}>Back</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[common.btnPrimary, { flex: 1 }]} onPress={() => setStep(3)} testID="onboard-next-2">
                  <Text style={common.btnPrimaryText}>Continue</Text>
                  <Ionicons name="arrow-forward" size={16} color="#fff" />
                </TouchableOpacity>
              </View>
            </View>
          )}

          {/* Step 3: Team info + Submit */}
          {step === 3 && (
            <View testID="onboard-step-team">
              <View style={common.card}>
                <Text style={s.cardText}>
                  You're the owner. Invite teammates as managers (full edit access) or
                  analysts (read-only) after onboarding from Settings.
                </Text>
              </View>
              <View style={[s.navRow, { marginTop: SPACING.lg }]}>
                <TouchableOpacity style={common.btnGhost} onPress={() => setStep(2)}>
                  <Text style={common.btnGhostText}>Back</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[common.btnPrimary, { flex: 1 }, busy && { opacity: 0.5 }]}
                  onPress={submit}
                  disabled={busy}
                  testID="mobile-advertiser-onboard-submit"
                >
                  {busy ? (
                    <ActivityIndicator size="small" color="#fff" />
                  ) : (
                    <>
                      <Text style={common.btnPrimaryText}>Create advertiser</Text>
                      <Ionicons name="arrow-forward" size={16} color="#fff" />
                    </>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 80 },
  backBtn: { marginBottom: SPACING.md },
  title: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '800', marginBottom: SPACING.xs },
  subtitle: { color: COLORS.textDim, fontSize: FONT.md, lineHeight: 22, marginBottom: SPACING.lg },
  stepRow: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.xl },
  stepPill: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.surfaceBorder,
  },
  stepPillActive: { borderColor: COLORS.secondary },
  stepPillText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1, textTransform: 'uppercase' },
  stepPillTextActive: { color: COLORS.secondary },
  marketRow: { flexDirection: 'row', gap: SPACING.sm, flexWrap: 'wrap' },
  marketChip: {
    paddingHorizontal: 16, paddingVertical: 10, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.surfaceBorder,
  },
  marketChipActive: { borderColor: COLORS.secondary, backgroundColor: 'rgba(59,130,246,0.08)' },
  marketChipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  marketChipTextActive: { color: COLORS.secondary },
  cardText: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 20 },
  bulletText: { color: COLORS.textDim, fontSize: FONT.xs, lineHeight: 18, marginTop: 2 },
  navRow: { flexDirection: 'row', gap: SPACING.sm },
});
