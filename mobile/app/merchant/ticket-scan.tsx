// Merchant Ticket Scanner (mobile) — enter a ticket code to check a guest in.
import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, TextInput, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

type Result = { kind: 'ok' | 'warn' | 'err'; label: string; ticket?: any };

export default function MerchantTicketScan() {
  const router = useRouter();
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result | null>(null);

  const submit = async () => {
    const c = code.trim().toUpperCase();
    if (!c) return;
    setBusy(true); setResult(null);
    try {
      const r = await api.post('/merchant/marketplace/events/tickets/checkin', { code: c });
      const d = r.data;
      if (d.ok) setResult({ kind: 'ok', label: 'Checked in ✓', ticket: d.ticket });
      else if (d.status === 'already_checked_in') setResult({ kind: 'warn', label: 'Already checked in', ticket: d.ticket });
      else setResult({ kind: 'warn', label: `Ticket ${d.status}`, ticket: d.ticket });
    } catch (e: any) {
      const cd = e?.response?.data?.detail?.code;
      setResult({ kind: 'err', label: cd === 'ticket_not_found' ? 'Ticket not found' : 'Check-in failed' });
    } finally { setBusy(false); setCode(''); }
  };

  const tone = result?.kind === 'ok' ? { bg: '#ecfdf5', bd: '#a7f3d0', tx: '#047857', icon: 'checkmark-circle' as const }
    : result?.kind === 'warn' ? { bg: '#fffbeb', bd: '#fde68a', tx: '#b45309', icon: 'alert-circle' as const }
    : { bg: '#fef2f2', bd: '#fecaca', tx: '#b91c1c', icon: 'close-circle' as const };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="scan-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title}>Scan Tickets</Text>
      </View>
      <View style={{ padding: SPACING.md }} testID="scan-root">
        <Text style={s.sub}>Enter a guest&apos;s ticket code to check them in at the door.</Text>
        <View style={s.card}>
          <View style={s.inputWrap}>
            <Ionicons name="qr-code-outline" size={22} color={COLORS.primary} />
            <TextInput
              value={code}
              onChangeText={(v) => setCode(v.toUpperCase())}
              placeholder="Ticket code e.g. DEMO1234"
              placeholderTextColor={COLORS.textMuted}
              autoCapitalize="characters"
              autoFocus
              style={s.input}
              testID="scan-code-input" />
          </View>
          <TouchableOpacity style={[common.btnPrimary, (busy || !code.trim()) && { opacity: 0.5 }]}
            disabled={busy || !code.trim()} onPress={submit} testID="scan-submit">
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={common.btnPrimaryText}>Check In</Text>}
          </TouchableOpacity>
        </View>

        {result && (
          <View style={[s.result, { backgroundColor: tone.bg, borderColor: tone.bd }]} testID="scan-result">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name={tone.icon} size={22} color={tone.tx} />
              <Text style={{ color: tone.tx, fontWeight: '900', fontSize: FONT.md }}>{result.label}</Text>
            </View>
            {result.ticket && (
              <Text style={{ color: COLORS.textDim, fontSize: FONT.sm, marginTop: 6 }}>
                {result.ticket.event_title} · Code {result.ticket.code} · Qty {result.ticket.qty}
                {result.kind !== 'ok' && result.ticket.checked_in_at
                  ? `\nChecked in ${new Date(result.ticket.checked_in_at).toLocaleString()}` : ''}
              </Text>
            )}
          </View>
        )}
      </View>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  title: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  sub: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, gap: 12 },
  inputWrap: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 12 },
  input: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', letterSpacing: 2 },
  result: { marginTop: SPACING.md, borderWidth: 1, borderRadius: RADIUS.lg, padding: SPACING.md },
});
