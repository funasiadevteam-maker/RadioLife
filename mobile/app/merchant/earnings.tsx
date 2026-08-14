// Merchant Earnings — memberships sold, gross/fee/net, 30-day trends chart,
// and Stripe Connect payouts (connect + withdraw + instant). Mobile parity.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as WebBrowser from 'expo-web-browser';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useReward } from '../../src/components/RewardOverlay';

const money = (c?: number) => `$${(((c || 0) as number) / 100).toFixed(2)}`;

function TrendsChart({ daily }: { daily: any[] }) {
  const days = daily || [];
  const max = Math.max(1, ...days.map((d) => d.net_cents || 0));
  const total = days.reduce((a, d) => a + (d.net_cents || 0), 0);
  return (
    <View style={s.card} testID="earnings-trends">
      <View style={s.trendHead}>
        <Text style={s.trendLabel}>LAST 30 DAYS</Text>
        <Text style={s.trendTotal}>{money(total)} net</Text>
      </View>
      {total === 0 ? (
        <Text style={s.trendEmpty} testID="earnings-trends-empty">No sales in the last 30 days yet.</Text>
      ) : (
        <View style={s.chartRow}>
          {days.map((d) => {
            const h = d.net_cents > 0 ? Math.max(8, Math.round((d.net_cents / max) * 92)) : 3;
            return <View key={d.date} style={[s.bar, { height: h, backgroundColor: d.net_cents > 0 ? COLORS.green : COLORS.cardBorder }]} testID={`earnings-bar-${d.date}`} />;
          })}
        </View>
      )}
    </View>
  );
}

export default function MerchantEarnings() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);

  const loadEarnings = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/earnings'); setData(r.data); } catch { /* ignore */ }
  }, []);
  const loadStatus = useCallback(async () => {
    try { const r = await api.get('/merchant/marketplace/connect/status'); setStatus(r.data); }
    catch { setStatus({ has_account: false, connected: false }); }
  }, []);

  const loadAll = useCallback(async () => {
    await Promise.all([loadEarnings(), loadStatus()]);
    setLoading(false); setRefreshing(false);
  }, [loadEarnings, loadStatus]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const connectPayouts = async () => {
    setBusy(true);
    try {
      await api.post('/merchant/marketplace/connect/account');
      const r = await api.post('/merchant/marketplace/connect/onboarding-link', { platform: 'mobile' });
      if (r.data.url) { await WebBrowser.openBrowserAsync(r.data.url); await loadStatus(); }
    } catch { celebrate({ points: 0, title: "Couldn't start payout setup" }); }
    finally { setBusy(false); }
  };

  const withdraw = async () => {
    setBusy(true);
    try {
      const r = await api.post('/merchant/marketplace/payout/withdraw');
      celebrate({ points: 0, title: `Transferred ${money(r.data.amount_cents)} 🎉` });
      await loadEarnings();
    } catch (e: any) {
      celebrate({ points: 0, title: e?.response?.data?.detail?.message || 'Withdrawal failed' });
    } finally { setBusy(false); }
  };

  const instant = async () => {
    setBusy(true);
    try {
      const r = await api.post('/merchant/marketplace/payout/instant');
      celebrate({ points: 0, title: `Instant payout ${money(r.data.amount_cents)} on its way` });
    } catch (e: any) {
      celebrate({ points: 0, title: e?.response?.data?.detail?.message || 'Instant payout unavailable' });
    } finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="earnings-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <View style={s.titleRow}>
          <Ionicons name="trending-up" size={18} color={COLORS.green} />
          <Text style={s.topTitle}>Earnings</Text>
        </View>
        <View style={{ width: 22 }} />
      </View>

      {loading ? (
        <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : !data ? (
        <View style={s.centerPad}><Text style={s.muted}>Couldn&apos;t load earnings.</Text></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="rl-merchant-earnings-page"
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary} onRefresh={() => { setRefreshing(true); loadAll(); }} />}>
          {/* Net payout headline */}
          <LinearGradient colors={['#059669', '#14B8A6']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
            style={s.netCard} testID="earnings-net-card">
            <Text style={s.netLabel}>NET PAYOUT · ALL TIME</Text>
            <Text style={s.netTotal} testID="earnings-net-total">{money(data.net_cents)}</Text>
            <Text style={s.netSub}>{money(data.gross_cents)} collected · {money(data.fee_cents)} platform fee</Text>
          </LinearGradient>

          {/* Payouts (Stripe Connect) */}
          {status && (
            <View style={s.card} testID="earnings-payouts">
              <View style={s.payHead}>
                <Ionicons name="cash-outline" size={16} color={COLORS.green} />
                <Text style={s.payTitle}>Payouts</Text>
                {status.connected && (
                  <View style={s.connChip}><Ionicons name="checkmark-circle" size={12} color={COLORS.green} /><Text style={s.connChipText}>Connected</Text></View>
                )}
              </View>
              {status.connected ? (
                <>
                  <Text style={s.payHint}>Available to withdraw</Text>
                  <Text style={s.payAmount} testID="payouts-available">{money(data.available_cents)}</Text>
                  <View style={s.payBtnRow}>
                    <TouchableOpacity style={[s.withdrawBtn, (busy || (data.available_cents || 0) <= 0) && { opacity: 0.4 }]}
                      onPress={withdraw} disabled={busy || (data.available_cents || 0) <= 0} testID="payouts-withdraw">
                      <Ionicons name="cash" size={15} color="#fff" />
                      <Text style={s.withdrawText}>{busy ? 'Working…' : 'Withdraw'}</Text>
                    </TouchableOpacity>
                    <TouchableOpacity style={[s.instantBtn, busy && { opacity: 0.4 }]} onPress={instant} disabled={busy} testID="payouts-instant">
                      <Ionicons name="flash" size={15} color="#fff" />
                      <Text style={s.withdrawText}>Cash out now</Text>
                    </TouchableOpacity>
                  </View>
                  <Text style={s.payFine}>Withdraw sends your net to your Stripe balance (bank on schedule). &quot;Cash out now&quot; pays your bank instantly for a small fee.</Text>
                </>
              ) : (
                <>
                  <Text style={s.payHint}>{status.has_account ? 'Finish your payout setup to start receiving money.' : 'Connect a bank via Stripe to receive your earnings.'}</Text>
                  {(status.requirements_due || []).length > 0 && (
                    <View style={s.reqBox} testID="payouts-requirements">
                      <Ionicons name="alert-circle" size={13} color="#B45309" />
                      <Text style={s.reqText}>More info needed: {(status.requirements_due || []).slice(0, 4).join(', ')}</Text>
                    </View>
                  )}
                  <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }, busy && { opacity: 0.5 }]} onPress={connectPayouts} disabled={busy} testID="payouts-connect">
                    <Ionicons name="cash" size={16} color="#fff" />
                    <Text style={common.btnPrimaryText}>{busy ? 'Opening…' : status.has_account ? 'Finish payout setup' : 'Connect payouts'}</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
          )}

          {/* 30-day trends */}
          <TrendsChart daily={data.daily} />

          {/* Stat grid */}
          <View style={s.statGrid}>
            <View style={s.stat} testID="earnings-sold">
              <Text style={s.statNum}>{data.memberships_sold}</Text>
              <Text style={s.statLbl}>Memberships sold</Text>
            </View>
            <View style={s.stat} testID="earnings-month-net">
              <Text style={s.statNum}>{money(data.month?.net_cents)}</Text>
              <Text style={s.statLbl}>Net this month</Text>
            </View>
            <View style={s.stat} testID="earnings-month-fee">
              <Text style={s.statNum}>{money(data.month?.fee_cents)}</Text>
              <Text style={s.statLbl}>Fee this month</Text>
            </View>
          </View>

          {/* Transactions */}
          <Text style={s.section}>RECENT MEMBERSHIP SALES</Text>
          {(data.transactions || []).length === 0 ? (
            <View style={s.emptyCard} testID="earnings-empty">
              <Ionicons name="ribbon" size={22} color={COLORS.gold} />
              <Text style={s.emptyTitle}>No membership sales yet.</Text>
              <Text style={s.emptySub}>Sales appear here once shoppers subscribe to your memberships.</Text>
            </View>
          ) : (
            <View testID="earnings-tx-list">
              {(data.transactions || []).map((t: any) => (
                <View key={t.earning_id} style={s.txRow} testID={`earnings-tx-${t.earning_id}`}>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.txName} numberOfLines={1}>{t.plan_name || 'Membership'}</Text>
                    <Text style={s.txMeta}>{money(t.gross_cents)} · {Math.round(t.fee_pct)}% fee ({money(t.fee_cents)})</Text>
                  </View>
                  <Text style={s.txNet}>+{money(t.net_cents)}</Text>
                </View>
              ))}
            </View>
          )}

          <Text style={s.footnote}>
            The platform fee is set by your category and any negotiated rate. Payouts settle to your connected account via Stripe.
          </Text>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  centerPad: { padding: SPACING.xl, alignItems: 'center' },
  muted: { color: COLORS.textMuted, fontSize: FONT.sm },
  netCard: { borderRadius: RADIUS.xl, padding: SPACING.lg, marginBottom: SPACING.md },
  netLabel: { color: 'rgba(255,255,255,0.85)', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  netTotal: { color: '#fff', fontSize: 38, fontWeight: '900', marginTop: 2 },
  netSub: { color: 'rgba(255,255,255,0.92)', fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  payHead: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  payTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', flex: 1 },
  connChip: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.green + '18', borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2 },
  connChipText: { color: COLORS.green, fontSize: 9, fontWeight: '900' },
  payHint: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 6 },
  payAmount: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900', marginTop: 2 },
  payBtnRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  withdrawBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: COLORS.green, borderRadius: RADIUS.full, paddingVertical: 12 },
  instantBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: COLORS.text, borderRadius: RADIUS.full, paddingVertical: 12, paddingHorizontal: 16 },
  withdrawText: { color: '#fff', fontWeight: '900', fontSize: FONT.sm },
  payFine: { color: COLORS.textMuted, fontSize: 10, fontWeight: '600', marginTop: 8, lineHeight: 15 },
  reqBox: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, backgroundColor: '#FEF3C7', borderRadius: RADIUS.sm, padding: 8, marginTop: 8 },
  reqText: { flex: 1, color: '#B45309', fontSize: 11, fontWeight: '700' },
  trendHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  trendLabel: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1 },
  trendTotal: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  trendEmpty: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', paddingVertical: 16 },
  chartRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 100 },
  bar: { flex: 1, borderTopLeftRadius: 2, borderTopRightRadius: 2 },
  statGrid: { flexDirection: 'row', gap: 10, marginBottom: SPACING.lg },
  stat: { flex: 1, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 12, alignItems: 'center' },
  statNum: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  statLbl: { color: COLORS.textMuted, fontSize: 10, fontWeight: '700', textAlign: 'center', marginTop: 2 },
  section: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1.5, marginBottom: SPACING.sm },
  emptyCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.lg, alignItems: 'center', gap: 4 },
  emptyTitle: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  emptySub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', textAlign: 'center' },
  txRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  txName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  txMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  txNet: { color: '#047857', fontSize: FONT.sm, fontWeight: '900' },
  footnote: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', marginTop: SPACING.md, paddingHorizontal: SPACING.md },
});
