// Perk Redemption Scan (mobile) — bar staff/owner validate & burn a drink code.
import React, { useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams, Stack } from 'expo-router';
import * as Haptics from 'expo-haptics';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../../src/constants/theme';

const STATUS: any = {
  valid: { color: COLORS.green, icon: 'checkmark-circle', text: 'Valid — ready to redeem' },
  redeemed: { color: COLORS.gold, icon: 'close-circle', text: 'Already redeemed' },
  expired: { color: COLORS.red, icon: 'time-outline', text: 'Expired' },
  not_found: { color: COLORS.textMuted, icon: 'help-circle', text: 'No matching code' },
};

export default function BarStaffScan() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);

  const lookup = async () => {
    if (code.trim().length < 3) return;
    setBusy(true); setResult(null);
    try { const { data } = await api.post(`/bar-games/${id}/staff/lookup`, { code: code.trim() }); setResult(data); }
    catch (_) {} finally { setBusy(false); }
  };
  const redeem = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/bar-games/${id}/staff/redeem`, { code: code.trim() });
      if (data.ok) { Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {}); setResult({ status: 'redeemed', perk: result?.perk }); }
      else setResult((r: any) => ({ ...r, status: data.status }));
    } catch (_) {} finally { setBusy(false); }
  };

  const st = result && STATUS[result.status];

  return (
    <SafeAreaView style={s.screen} testID="bar-scan-screen">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} testID="scan-back"><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.hTitle}>Redeem a perk</Text>
      </View>

      <View style={{ padding: SPACING.md, gap: 12 }}>
        <Text style={s.lbl}>Customer's code</Text>
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput value={code} onChangeText={(v) => setCode(v.toUpperCase())} placeholder="BAR-XXXXXXXX" autoCapitalize="characters"
            placeholderTextColor={COLORS.textMuted} style={[s.input, { flex: 1 }]} testID="scan-code" />
          <TouchableOpacity onPress={lookup} disabled={busy} style={s.checkBtn} testID="scan-lookup">
            {busy && !st ? <ActivityIndicator color="#fff" /> : <Text style={s.checkTxt}>Check</Text>}
          </TouchableOpacity>
        </View>

        {st ? (
          <View style={[s.result, { backgroundColor: st.color + '1a', borderColor: st.color + '55' }]} testID="scan-result">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={st.icon} size={18} color={st.color} />
              <Text style={{ color: st.color, fontWeight: '900', fontSize: FONT.md }}>{st.text}</Text>
            </View>
            {result.perk ? (
              <View style={{ marginTop: 8 }}>
                <Text style={{ color: COLORS.text, fontWeight: '900', fontSize: FONT.lg }}>{result.perk.emoji} {result.perk.label}</Text>
                <Text style={{ color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 }}>{result.perk.code} · {result.perk.customer}</Text>
              </View>
            ) : null}
            {result.status === 'valid' ? (
              <TouchableOpacity onPress={redeem} disabled={busy} style={s.redeemBtn} testID="scan-redeem">
                {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="checkmark-circle" size={15} color="#fff" /><Text style={s.redeemTxt}>Redeem now</Text></>}
              </TouchableOpacity>
            ) : null}
          </View>
        ) : null}
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: SPACING.md, paddingTop: SPACING.sm, paddingBottom: SPACING.sm },
  back: { width: 38, height: 38, borderRadius: 19, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.cardBorder },
  hTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  lbl: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.inputBorder, paddingHorizontal: 12, paddingVertical: 12, color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  checkBtn: { paddingHorizontal: 18, borderRadius: RADIUS.md, backgroundColor: COLORS.text, alignItems: 'center', justifyContent: 'center' },
  checkTxt: { color: COLORS.bg, fontWeight: '900', fontSize: FONT.sm },
  result: { borderRadius: RADIUS.lg, borderWidth: 1, padding: 16, marginTop: 6 },
  redeemBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 46, borderRadius: 23, backgroundColor: COLORS.green, marginTop: 12 },
  redeemTxt: { color: '#fff', fontWeight: '900', fontSize: FONT.md },
});
