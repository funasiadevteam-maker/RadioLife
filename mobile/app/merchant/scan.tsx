// Merchant Scan to Charge — scan a customer's Scan-to-Pay QR (camera) or type
// the code, confirm the amount, and charge. Mobile.
import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ActivityIndicator, TextInput, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const ERR: Record<string, string> = {
  invalid_token: 'Code not recognised.', expired: 'This QR has expired.',
  canceled: 'The customer canceled this.', charged: 'Already charged.',
  card_declined: 'Card was declined.', already_used: 'Already charged.',
  no_marketplace_profile: 'Register your shop first.',
};

export default function MerchantScan() {
  const router = useRouter();
  const [permission, requestPermission] = useCameraPermissions();
  const [scanning, setScanning] = useState(false);
  const [code, setCode] = useState('');
  const [resolved, setResolved] = useState<any>(null);
  const [charged, setCharged] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const doResolve = async (raw: string) => {
    const t = raw.trim().toUpperCase();
    if (!t) return;
    setError(null); setBusy(true); setResolved(null);
    try {
      const r = await api.post('/shop/scanpay/resolve', { token: t });
      if (r.data.ok) { setResolved(r.data); setCode(t); }
      else setError(ERR[r.data.error] || 'Could not read code');
    } catch (e: any) { setError(ERR[e?.response?.data?.detail?.code] || 'Could not read code'); }
    finally { setBusy(false); }
  };

  const charge = async () => {
    setError(null); setBusy(true);
    try {
      const r = await api.post('/shop/scanpay/charge', { token: resolved.token });
      if (r.data.ok) setCharged(r.data);
      else setError(ERR[r.data.error] || 'Charge failed');
    } catch (e: any) { setError(ERR[e?.response?.data?.detail?.code] || 'Charge failed'); }
    finally { setBusy(false); }
  };

  const openCamera = async () => {
    setError(null);
    if (permission?.granted) { setScanning(true); return; }
    if (permission && !permission.canAskAgain) {
      Linking.openSettings(); return;
    }
    const res = await requestPermission();
    if (res.granted) setScanning(true);
    else if (!res.canAskAgain) setError('Camera blocked — enable it in Settings.');
  };

  const reset = () => { setCode(''); setResolved(null); setCharged(null); setError(null); setScanning(false); };

  if (scanning) {
    return (
      <SafeAreaView style={[common.screen, { backgroundColor: '#000' }]}>
        <CameraView style={{ flex: 1 }} facing="back" barcodeScannerSettings={{ barcodeTypes: ['qr'] }}
          onBarcodeScanned={({ data }) => { setScanning(false); doResolve(data); }} testID="merchant-scan-camera" />
        <TouchableOpacity style={s.camClose} onPress={() => setScanning(false)} testID="merchant-scan-camera-close">
          <Ionicons name="close" size={22} color="#fff" /><Text style={s.camCloseText}>Cancel</Text>
        </TouchableOpacity>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="merchant-scan-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Scan to Charge</Text>
        <View style={{ width: 22 }} />
      </View>

      <View style={{ padding: SPACING.md }} testID="merchant-scan-root">
        {charged ? (
          <View style={s.result} testID="merchant-scan-charged">
            <Ionicons name="checkmark-circle" size={54} color={COLORS.green} />
            <Text style={s.resultTitle}>Charged {money(charged.amount_cents)}</Text>
            <Text style={s.resultSub}>Paid by {charged.method === 'card' ? 'card' : 'BigPoints'}.</Text>
            <TouchableOpacity style={[common.btnPrimary, { marginTop: 18 }]} onPress={reset} testID="merchant-scan-again">
              <Text style={common.btnPrimaryText}>Charge another</Text>
            </TouchableOpacity>
          </View>
        ) : resolved ? (
          <View style={s.result} testID="merchant-scan-resolved">
            <Text style={s.resultSub}>{resolved.customer} wants to pay</Text>
            <Text style={s.bigAmount}>{money(resolved.amount_cents)}</Text>
            <View style={s.methodPill}>
              <Ionicons name={resolved.method === 'card' ? 'card' : 'server'} size={15} color={COLORS.primary} />
              <Text style={s.methodPillText}>{resolved.method === 'card' ? 'Saved card' : 'BigPoints'}</Text>
            </View>
            {!!error && <Text style={s.err} testID="merchant-scan-error">{error}</Text>}
            <TouchableOpacity style={[s.chargeBtn, busy && { opacity: 0.6 }]} disabled={busy} onPress={charge} testID="merchant-scan-charge">
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.chargeText}>Charge {money(resolved.amount_cents)}</Text>}
            </TouchableOpacity>
            <TouchableOpacity onPress={reset} testID="merchant-scan-cancel"><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>
          </View>
        ) : (
          <View style={s.card}>
            <Text style={s.cardTitle}>Charge a customer</Text>
            <TouchableOpacity style={s.scanCta} onPress={openCamera} testID="merchant-scan-open-camera">
              <Ionicons name="qr-code" size={18} color="#fff" />
              <Text style={s.scanCtaText}>Scan QR with camera</Text>
            </TouchableOpacity>
            <Text style={s.or}>or enter the code</Text>
            <TextInput style={s.input} value={code} onChangeText={setCode} autoCapitalize="characters"
              placeholder="SP••••••••" placeholderTextColor={COLORS.textMuted} testID="merchant-scan-input" />
            {!!error && <Text style={s.err} testID="merchant-scan-error">{error}</Text>}
            <TouchableOpacity style={[common.btnPrimary, (busy || !code.trim()) && { opacity: 0.5 }]} disabled={busy || !code.trim()}
              onPress={() => doResolve(code)} testID="merchant-scan-resolve">
              {busy ? <ActivityIndicator color="#fff" /> : <Text style={common.btnPrimaryText}>Look up</Text>}
            </TouchableOpacity>
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 16, gap: 12 },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  scanCta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.md, paddingVertical: 14 },
  scanCtaText: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  or: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', textAlign: 'center' },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 12, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', letterSpacing: 3, textAlign: 'center' },
  err: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '800' },
  result: { alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 28 },
  resultTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', marginTop: 12 },
  resultSub: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', marginTop: 4 },
  bigAmount: { color: COLORS.text, fontSize: 36, fontWeight: '900', marginVertical: 8 },
  methodPill: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary + '14', borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 6 },
  methodPillText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  chargeBtn: { width: '100%', backgroundColor: COLORS.green, borderRadius: RADIUS.full, paddingVertical: 15, alignItems: 'center', marginTop: 18 },
  chargeText: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
  cancelText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800', marginTop: 12 },
  camClose: { position: 'absolute', bottom: 40, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: 'rgba(0,0,0,0.6)', borderRadius: RADIUS.full, paddingHorizontal: 20, paddingVertical: 12 },
  camCloseText: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
});
