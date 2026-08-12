// Scan to Pay (customer) — generate a QR the shop scans to charge your saved
// card or BigPoints. Mobile.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import QRCode from 'react-native-qrcode-svg';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const BRAND: Record<string, string> = { visa: 'Visa', mastercard: 'Mastercard', amex: 'Amex', discover: 'Discover' };
const ERR: Record<string, string> = {
  insufficient_points: "You don't have enough BigPoints.",
  card_not_found: 'Add a card first.', bad_amount: 'Enter a valid amount.',
};

export default function ScanPay() {
  const router = useRouter();
  const [method, setMethod] = useState<'card' | 'points'>('card');
  const [cards, setCards] = useState<any[]>([]);
  const [payWith, setPayWith] = useState<string | null>(null);
  const [amount, setAmount] = useState('');
  const [token, setToken] = useState<string | null>(null);
  const [stage, setStage] = useState<'form' | 'qr' | 'charged' | 'expired'>('form');
  const [error, setError] = useState<string | null>(null);
  const [reportName, setReportName] = useState('');
  const [reported, setReported] = useState(false);
  const poll = useRef<any>(null);

  useEffect(() => {
    api.get('/shop/wallet/cards').then((r) => {
      setCards(r.data.cards || []);
      const def = (r.data.cards || []).find((c: any) => c.is_default);
      setPayWith(def ? def.id : (r.data.cards?.[0]?.id || null));
    }).catch(() => {});
  }, []);

  const stopPoll = () => { if (poll.current) { clearInterval(poll.current); poll.current = null; } };
  useEffect(() => stopPoll, []);

  const startPoll = useCallback((tk: string) => {
    stopPoll();
    poll.current = setInterval(async () => {
      try {
        const r = await api.get(`/shop/scanpay/token/${tk}/status`);
        if (r.data.status === 'charged') { setStage('charged'); stopPoll(); }
        else if (['expired', 'canceled', 'not_found'].includes(r.data.status)) { setStage('expired'); stopPoll(); }
      } catch { /* keep polling */ }
    }, 2500);
  }, []);

  const cents = Math.round(parseFloat(amount || '0') * 100);

  const generate = async () => {
    setError(null);
    if (!cents || cents <= 0) { setError('Enter an amount'); return; }
    if (method === 'card' && !payWith) { setError('Add a card first'); return; }
    try {
      const r = await api.post('/shop/scanpay/token', {
        method, amount_cents: cents, payment_method_id: method === 'card' ? payWith : undefined,
      });
      setToken(r.data.token); setStage('qr'); startPoll(r.data.token);
    } catch (e: any) { setError(ERR[e?.response?.data?.detail?.code] || 'Could not create QR'); }
  };

  const cancel = async () => {
    if (token) { try { await api.post(`/shop/scanpay/token/${token}/cancel`); } catch { /* ignore */ } }
    stopPoll(); setStage('form'); setToken(null);
  };

  const report = async () => {
    try {
      await api.post('/shop/scanpay/report-bypass', { business_name: reportName || undefined, note: 'Asked to pay outside the app' });
      setReported(true);
    } catch { /* ignore */ }
  };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="scanpay-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Scan to Pay</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="scanpay-root">
        {stage === 'charged' ? (
          <View style={s.result} testID="scanpay-charged">
            <Ionicons name="checkmark-circle" size={54} color={COLORS.green} />
            <Text style={s.resultTitle}>Paid {money(cents)}</Text>
            <Text style={s.resultSub}>The shop charged your {method === 'card' ? 'card' : 'BigPoints'}.</Text>
            <TouchableOpacity style={[common.btnPrimary, { marginTop: 18 }]} onPress={() => { setStage('form'); setToken(null); setAmount(''); }} testID="scanpay-done">
              <Text style={common.btnPrimaryText}>Done</Text>
            </TouchableOpacity>
          </View>
        ) : stage === 'qr' ? (
          <View style={s.qrCard} testID="scanpay-qr">
            <Text style={s.qrHint}>Show this to the shop to pay</Text>
            <Text style={s.qrAmount}>{money(cents)}</Text>
            <View style={s.qrBox} testID="scanpay-qr-code"><QRCode value={token || ' '} size={196} /></View>
            <Text style={s.qrToken} testID="scanpay-token">{token}</Text>
            <View style={s.waitRow}><ActivityIndicator color={COLORS.primary} /><Text style={s.waitText}>Waiting for the shop to scan…</Text></View>
            <TouchableOpacity onPress={cancel} testID="scanpay-cancel"><Text style={s.cancelText}>Cancel</Text></TouchableOpacity>
          </View>
        ) : stage === 'expired' ? (
          <View style={s.result} testID="scanpay-expired">
            <Ionicons name="warning" size={44} color="#f59e0b" />
            <Text style={s.resultTitle}>QR expired or canceled</Text>
            <TouchableOpacity style={[common.btnPrimary, { marginTop: 16 }]} onPress={() => { setStage('form'); setToken(null); }} testID="scanpay-retry">
              <Text style={common.btnPrimaryText}>Try again</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            <View style={s.card}>
              <Text style={s.cardTitle}>Pay in-store with a QR</Text>
              <View style={s.methodRow}>
                <TouchableOpacity style={[s.methodBtn, method === 'card' && s.methodOn]} onPress={() => setMethod('card')} testID="scanpay-method-card">
                  <Ionicons name="card" size={15} color={method === 'card' ? COLORS.primary : COLORS.textDim} />
                  <Text style={[s.methodText, method === 'card' && { color: COLORS.primary }]}>Card</Text>
                </TouchableOpacity>
                <TouchableOpacity style={[s.methodBtn, method === 'points' && s.methodOn]} onPress={() => setMethod('points')} testID="scanpay-method-points">
                  <Ionicons name="server" size={15} color={method === 'points' ? COLORS.primary : COLORS.textDim} />
                  <Text style={[s.methodText, method === 'points' && { color: COLORS.primary }]}>BigPoints</Text>
                </TouchableOpacity>
              </View>

              {method === 'card' && (cards.length ? cards.map((c) => (
                <TouchableOpacity key={c.id} style={[s.cardRow, payWith === c.id && s.cardRowOn]} onPress={() => setPayWith(c.id)} testID={`scanpay-card-${c.id}`}>
                  <View style={[s.radio, payWith === c.id && s.radioOn]} />
                  <Ionicons name="card-outline" size={16} color={COLORS.text} />
                  <Text style={s.cardRowText}>{BRAND[c.brand] || c.brand} •••• {c.last4}</Text>
                </TouchableOpacity>
              )) : (
                <TouchableOpacity style={s.addCard} onPress={() => router.push('/shop/wallet/cards')} testID="scanpay-add-card">
                  <Text style={s.addCardText}>Add a card first</Text>
                </TouchableOpacity>
              ))}

              <Text style={s.label}>Amount ($)</Text>
              <TextInput style={s.amountInput} value={amount} onChangeText={setAmount} keyboardType="decimal-pad" placeholder="0.00" placeholderTextColor={COLORS.textMuted} testID="scanpay-amount" />
              {!!error && <Text style={s.err} testID="scanpay-error">{error}</Text>}
              <TouchableOpacity style={common.btnPrimary} onPress={generate} testID="scanpay-generate">
                <Ionicons name="qr-code" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Generate QR</Text>
              </TouchableOpacity>
            </View>

            <View style={s.card} testID="scanpay-report">
              <Text style={s.reportTitle}>Asked to pay outside the app?</Text>
              <Text style={s.reportHint}>Report a shop that skipped the scan so we can look into it.</Text>
              {reported ? <Text style={s.reportDone} testID="scanpay-report-done">Thanks — reported for review.</Text> : (
                <View style={s.reportRow}>
                  <TextInput style={s.reportInput} value={reportName} onChangeText={setReportName} placeholder="Shop name" placeholderTextColor={COLORS.textMuted} testID="scanpay-report-input" />
                  <TouchableOpacity style={s.reportBtn} onPress={report} testID="scanpay-report-btn"><Text style={s.reportBtnText}>Report</Text></TouchableOpacity>
                </View>
              )}
            </View>
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 16, gap: 10, marginBottom: SPACING.md },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  methodRow: { flexDirection: 'row', gap: 8 },
  methodBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg },
  methodOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '12' },
  methodText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '900' },
  cardRow: { flexDirection: 'row', alignItems: 'center', gap: 10, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, padding: 11 },
  cardRowOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary + '12' },
  radio: { width: 16, height: 16, borderRadius: 8, borderWidth: 2, borderColor: COLORS.textMuted },
  radioOn: { borderColor: COLORS.primary, backgroundColor: COLORS.primary },
  cardRowText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  addCard: { borderWidth: 1, borderColor: COLORS.primary + '55', borderRadius: RADIUS.md, paddingVertical: 11, alignItems: 'center' },
  addCardText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  label: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  amountInput: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 12, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  err: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '800' },
  result: { alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 32, marginTop: 20 },
  resultTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', marginTop: 12 },
  resultSub: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', marginTop: 4, textAlign: 'center' },
  qrCard: { alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 24, marginTop: 8 },
  qrHint: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  qrAmount: { color: COLORS.text, fontSize: 30, fontWeight: '900', marginVertical: 8 },
  qrBox: { backgroundColor: '#fff', padding: 16, borderRadius: RADIUS.md },
  qrToken: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900', letterSpacing: 3, marginTop: 12 },
  waitRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12 },
  waitText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
  cancelText: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '900', marginTop: 16 },
  reportTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  reportHint: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  reportRow: { flexDirection: 'row', gap: 8 },
  reportInput: { flex: 1, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 9, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  reportBtn: { backgroundColor: COLORS.text, borderRadius: RADIUS.md, paddingHorizontal: 16, justifyContent: 'center' },
  reportBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  reportDone: { color: COLORS.green, fontSize: FONT.sm, fontWeight: '900' },
});
