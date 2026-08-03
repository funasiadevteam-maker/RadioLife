import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, ActivityIndicator, Alert,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as Sharing from 'expo-sharing';
import SafeImage from '../../src/components/SafeImage';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const TIP_PRESETS = [0, 100, 200, 500]; // cents

export default function PayCheckoutScreen() {
  const { token } = useLocalSearchParams<{ token: string }>();
  const router = useRouter();

  const [loading, setLoading] = useState(true);
  const [resolved, setResolved] = useState<any>(null);
  const [error, setError] = useState('');
  const [pointsToUse, setPointsToUse] = useState(0);
  const [tipCents, setTipCents] = useState(0);
  const [quote, setQuote] = useState<any>(null);
  const [quoteBusy, setQuoteBusy] = useState(false);
  const [payBusy, setPayBusy] = useState(false);
  const [receipt, setReceipt] = useState<any>(null);
  const [splitBusy, setSplitBusy] = useState(false);

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const r = await api.get(`/scan-to-pay/qr/${token}`);
        setResolved(r.data);
        computeQuote(0, 0);
      } catch (e: any) {
        setError(e?.response?.data?.detail?.code || e?.message || 'Invalid QR');
      } finally { setLoading(false); }
    })();
  }, [token]);

  const computeQuote = useCallback(async (pts: number, tip: number) => {
    setQuoteBusy(true);
    try {
      const r = await api.post('/scan-to-pay/quote', {
        qr_token: token, points_to_use: pts, tip_cents: tip,
      });
      setQuote(r.data);
    } catch (e: any) {
      setQuote(null);
    } finally { setQuoteBusy(false); }
  }, [token]);

  useEffect(() => {
    if (!resolved) return;
    const t = setTimeout(() => computeQuote(pointsToUse, tipCents), 250);
    return () => clearTimeout(t);
  }, [pointsToUse, tipCents, resolved, computeQuote]);

  const pay = async () => {
    if (!quote) return;
    setPayBusy(true);
    try {
      const auth = await api.post('/scan-to-pay/authorize', {
        qr_token: token, points_to_use: pointsToUse, tip_cents: tipCents,
        payment_method_id: 'pm_card_visa', // Stripe test mode
      });
      const cap = await api.post('/scan-to-pay/capture', {
        transaction_id: auth.data.transaction_id,
      });
      setReceipt({ ...auth.data, ...cap.data, merchant: resolved.merchant });
    } catch (e: any) {
      Alert.alert('Payment Failed', e?.response?.data?.detail?.code || e?.message || 'Try again');
    } finally { setPayBusy(false); }
  };

  const startSplit = async () => {
    if (!resolved) return;
    setSplitBusy(true);
    try {
      const r = await api.post('/scan-to-pay/splits', {
        qr_token: token,
        payer_count: 2,
        shares: [
          { label: 'You', amount_cents: Math.floor((quote?.total_cents || 0) / 2) },
          { label: 'Friend', amount_cents: Math.ceil((quote?.total_cents || 0) / 2) },
        ],
      });
      const inviteUrl = `https://mobile-games-v2.preview.emergentagent.com/split/${r.data.invite_token}`;
      if (await Sharing.isAvailableAsync()) {
        await Sharing.shareAsync(inviteUrl, { dialogTitle: 'Split the bill with a friend' });
      } else {
        Alert.alert('Share this link', inviteUrl);
      }
    } catch (e: any) {
      Alert.alert('Split Error', e?.response?.data?.detail?.code || e?.message || 'Could not create split');
    } finally { setSplitBusy(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  // Error state
  if (error) return (
    <SafeAreaView style={common.screen}>
      <View style={s.errorWrap}>
        <TouchableOpacity onPress={() => router.back()} style={{ alignSelf: 'flex-start', padding: 4 }}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Ionicons name="alert-circle" size={48} color={COLORS.red} />
        <Text style={s.errorTitle}>Payment Error</Text>
        <Text style={s.errorText}>{error}</Text>
        <TouchableOpacity style={common.btnPrimary} onPress={() => router.back()}>
          <Text style={common.btnPrimaryText}>Go Back</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );

  // Receipt
  if (receipt) return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={s.receiptWrap}>
        <Ionicons name="checkmark-circle" size={64} color={COLORS.green} />
        <Text style={s.receiptTitle} testID="pay-receipt-title">Payment Successful!</Text>
        <Text style={s.receiptMerchant}>{receipt.merchant?.name || 'Merchant'}</Text>
        <View style={[common.card, { marginTop: SPACING.lg, width: '100%' }]}>
          <Row label="Subtotal" value={formatCents(receipt.subtotal_cents)} />
          {receipt.tip_cents > 0 && <Row label="Tip" value={formatCents(receipt.tip_cents)} />}
          {receipt.points_used > 0 && <Row label="BigCoin used" value={`-${receipt.points_used} BC`} />}
          <View style={s.divider} />
          <Row label="Total paid" value={formatCents(receipt.charge_cents)} bold />
        </View>
        {receipt.bigcoin_earned > 0 && (
          <View style={s.earnedCard} testID="pay-bigcoin-earned">
            <Ionicons name="sparkles" size={20} color={COLORS.gold} />
            <Text style={s.earnedText}>+{receipt.bigcoin_earned} BigCoin earned!</Text>
          </View>
        )}
        <TouchableOpacity style={[common.btnPrimary, { marginTop: SPACING.xl, width: '100%' }]}
          onPress={() => router.replace('/(tabs)/wallet')} testID="pay-done-btn">
          <Text style={common.btnPrimaryText}>Done</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );

  // Checkout
  const merchant = resolved?.merchant;
  const maxPoints = Math.min(resolved?.max_points_allowed || 0, resolved?.user_balance || 0);

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={s.scroll}>
        <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>

        {/* Merchant header */}
        <View style={s.merchantHeader} testID="pay-merchant-header">
          <SafeImage uri={merchant?.logo_url} fallbackText={merchant?.name || 'M'} size={56} borderRadius={14} />
          <View style={{ flex: 1, marginLeft: 14 }}>
            <Text style={s.merchantName}>{merchant?.name || 'Merchant'}</Text>
            {merchant?.address && <Text style={s.merchantAddr}>{merchant.address}</Text>}
          </View>
        </View>

        {/* Bill items */}
        <View style={common.card} testID="pay-bill-card">
          <Text style={common.label}>ORDER SUMMARY</Text>
          {(resolved?.items || []).map((it: any, i: number) => (
            <View key={i} style={s.lineRow}>
              <Text style={s.lineLabel}>{it.name || `Item ${i+1}`}</Text>
              <Text style={s.lineVal}>{formatCents(it.amount_cents)}</Text>
            </View>
          ))}
          <View style={s.divider} />
          <View style={s.lineRow}>
            <Text style={[s.lineLabel, { fontWeight: '800' }]}>Subtotal</Text>
            <Text style={[s.lineVal, { fontWeight: '800' }]}>{formatCents(resolved?.subtotal_cents || 0)}</Text>
          </View>
        </View>

        {/* Points slider */}
        {maxPoints > 0 && (
          <View style={common.card}>
            <Text style={common.label}>USE BIGCOIN ({resolved?.user_balance || 0} available)</Text>
            <View style={s.pointsRow}>
              {[0, Math.floor(maxPoints/4), Math.floor(maxPoints/2), maxPoints].map((v, i) => (
                <TouchableOpacity key={i} style={[common.pill, pointsToUse === v && common.pillActive]}
                  onPress={() => setPointsToUse(v)} testID={`points-${v}`}>
                  <Text style={[common.pillText, pointsToUse === v && common.pillTextActive]}>{v}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        )}

        {/* Tip presets */}
        <View style={common.card}>
          <Text style={common.label}>ADD TIP</Text>
          <View style={s.tipRow}>
            {TIP_PRESETS.map(t => (
              <TouchableOpacity key={t} style={[common.pill, tipCents === t && common.pillActive]}
                onPress={() => setTipCents(t)} testID={`tip-${t}`}>
                <Text style={[common.pillText, tipCents === t && common.pillTextActive]}>
                  {t === 0 ? 'No tip' : formatCents(t)}
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Quote total */}
        {quote && (
          <View style={[common.card, { backgroundColor: COLORS.inputBg }]}>
            <Row label="Subtotal" value={formatCents(quote.subtotal_cents)} />
            {quote.tip_cents > 0 && <Row label="Tip" value={formatCents(quote.tip_cents)} />}
            {quote.points_discount_cents > 0 && <Row label="BigCoin discount" value={`-${formatCents(quote.points_discount_cents)}`} />}
            <View style={s.divider} />
            <Row label="You pay" value={formatCents(quote.charge_cents)} bold />
          </View>
        )}
        {quoteBusy && <ActivityIndicator size="small" color={COLORS.primary} style={{ marginTop: 8 }} />}

        {/* Pay button */}
        <TouchableOpacity style={[common.btnPrimary, { marginTop: SPACING.lg }, payBusy && { opacity: 0.5 }]}
          onPress={pay} disabled={payBusy || !quote} testID="pay-submit-btn">
          {payBusy ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="card" size={18} color="#fff" />}
          <Text style={common.btnPrimaryText}>
            {payBusy ? 'Processing...' : `Pay ${quote ? formatCents(quote.charge_cents) : '...'}`}
          </Text>
        </TouchableOpacity>

        {/* Split CTA */}
        <TouchableOpacity style={[common.btnGhost, { marginTop: SPACING.md }]}
          onPress={startSplit} disabled={splitBusy} testID="split-bill-btn">
          {splitBusy ? <ActivityIndicator size="small" color={COLORS.textDim} /> : <Ionicons name="people" size={16} color={COLORS.textDim} />}
          <Text style={common.btnGhostText}>Split with a friend</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <View style={s.lineRow}>
      <Text style={[s.lineLabel, bold && { fontWeight: '800', color: COLORS.text }]}>{label}</Text>
      <Text style={[s.lineVal, bold && { fontWeight: '800', color: COLORS.text }]}>{value}</Text>
    </View>
  );
}

function formatCents(c: number): string {
  return `AED ${(c / 100).toFixed(2)}`;
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 60, gap: 12 },
  errorWrap: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: SPACING.xl, gap: 12 },
  errorTitle: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  errorText: { fontSize: FONT.md, color: COLORS.textDim, textAlign: 'center' },
  receiptWrap: { padding: SPACING.xl, alignItems: 'center', paddingTop: 60 },
  receiptTitle: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text, marginTop: 16 },
  receiptMerchant: { fontSize: FONT.lg, color: COLORS.textDim, marginTop: 4 },
  earnedCard: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: SPACING.lg,
    backgroundColor: '#fffbeb', padding: 14, borderRadius: RADIUS.md, borderWidth: 1, borderColor: '#fef3c7',
  },
  earnedText: { fontSize: FONT.md, fontWeight: '700', color: COLORS.gold },
  merchantHeader: { flexDirection: 'row', alignItems: 'center', marginVertical: SPACING.md },
  merchantName: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  merchantAddr: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 2 },
  lineRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 6 },
  lineLabel: { fontSize: FONT.md, color: COLORS.textDim },
  lineVal: { fontSize: FONT.md, color: COLORS.text, fontWeight: '600' },
  divider: { height: 1, backgroundColor: COLORS.surfaceBorder, marginVertical: 8 },
  pointsRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 8 },
  tipRow: { flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginTop: 8 },
});
