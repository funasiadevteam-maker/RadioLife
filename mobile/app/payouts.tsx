// Unified Payouts & Earnings — advisor (15%) + merchant (5%) Stripe Connect.
// Earnings dashboard + weekly fees-vs-earnings insights + dated payout history
// + instant cash-out (graceful Stripe-dashboard fallback for Standard accounts).
// Mobile parity with the web Payments, Payouts & Earnings page.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import * as WebBrowser from 'expo-web-browser';
import api, { BACKEND } from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';

const money = (c?: number) => `$${(((c || 0) as number) / 100).toFixed(2)}`;
const fmtDate = (d?: string) => (d ? new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }) : '—');

const TYPE_META: Record<string, { label: string; icon: any; blurb: string }> = {
  advisor: { label: 'Expert / Advisor', icon: 'sparkles-outline', blurb: 'Get paid for readings & sessions' },
  merchant: { label: 'Business / Store', icon: 'storefront-outline', blurb: 'Get paid for sales & bookings' },
};
const CASHOUT_MSG: Record<string, string> = {
  no_instant_eligible_external_account: 'Add an instant-eligible debit card in Stripe to cash out instantly.',
  insufficient_instant_balance: 'No instant-available balance to cash out yet.',
  payouts_disabled: "Payouts aren't enabled on your Stripe account yet.",
};

export default function Payouts() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [history, setHistory] = useState<Record<string, any[]>>({});
  const [insights, setInsights] = useState<Record<string, any[]>>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [cashing, setCashing] = useState<string | null>(null);
  const [agreed, setAgreed] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    try {
      const [ov, hist, ins] = await Promise.all([
        api.get('/payouts/overview'),
        api.get('/payouts/history').catch(() => ({ data: { accounts: [] } })),
        api.get('/payouts/insights?weeks=6').catch(() => ({ data: { accounts: [] } })),
      ]);
      setData(ov.data);
      const hMap: Record<string, any[]> = {}; (hist.data.accounts || []).forEach((a: any) => { hMap[a.vendor_type] = a.transactions || []; });
      const iMap: Record<string, any[]> = {}; (ins.data.accounts || []).forEach((a: any) => { iMap[a.vendor_type] = a.weeks || []; });
      setHistory(hMap); setInsights(iMap);
    } catch { setData({ eligible: false, accounts: [] }); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const refreshStatus = async (vt: string) => { try { await api.post('/payouts/refresh', { vendor_type: vt }); } catch { /* no account */ } };

  const connect = async (vt: string) => {
    setBusy(vt);
    try {
      const r = await api.post('/payouts/onboard', { vendor_type: vt, agreement_accepted: true, origin_url: BACKEND });
      if (r.data?.onboarding_url) { await WebBrowser.openBrowserAsync(r.data.onboarding_url); await refreshStatus(vt); await load(); }
    } catch { /* reload state */ }
    finally { setBusy(null); }
  };

  const cashout = async (vt: string) => {
    setCashing(vt);
    try {
      const r = await api.post('/payouts/cashout', { vendor_type: vt });
      if (r.data?.status === 'fallback') {
        if (r.data.dashboard_url) await WebBrowser.openBrowserAsync(r.data.dashboard_url);
      } else { await load(); }
    } catch { /* ignore */ }
    finally { setCashing(null); }
  };

  const accounts = data?.accounts || [];
  const gate = !!data?.gate_on;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="payouts-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <View style={s.titleRow}>
          <Ionicons name="cash-outline" size={18} color={COLORS.green} />
          <Text style={s.topTitle}>Payouts & Earnings</Text>
        </View>
        <View style={{ width: 22 }} />
      </View>

      {loading ? (
        <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : accounts.length === 0 ? (
        <View style={s.centerPad} testID="payouts-not-eligible">
          <Ionicons name="alert-circle-outline" size={26} color={COLORS.gold} />
          <Text style={s.emptyTitle}>No vendor profile yet</Text>
          <Text style={s.muted}>Become a verified expert or register a business to start accepting payments.</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
          testID="payouts-page"
          refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
            onRefresh={() => { setRefreshing(true); load(); }} />}>
          {gate && accounts.some((a: any) => !a.ready) && (
            <View style={s.gate} testID="payouts-gate-banner">
              <Ionicons name="shield-checkmark" size={15} color={COLORS.purple} />
              <Text style={s.gateText}>Finish Stripe payout setup to start selling. Payments are blocked until your account is active.</Text>
            </View>
          )}

          {accounts.map((a: any) => {
            const meta = TYPE_META[a.vendor_type] || TYPE_META.merchant;
            const e = a.earnings || {};
            const isAgreed = !!agreed[a.vendor_type];
            return (
              <View key={a.vendor_type} style={s.card} testID={`payout-card-${a.vendor_type}`}>
                <View style={s.cardHead}>
                  <View style={s.iconWrap}><Ionicons name={meta.icon} size={18} color={COLORS.primary} /></View>
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.cardTitle}>{meta.label}</Text>
                    <Text style={s.cardSub} numberOfLines={1}>{a.display_name || meta.blurb}</Text>
                  </View>
                  <StatusPill ready={!!a.ready} hasAccount={!!a.has_account} />
                </View>

                <View style={s.feeRow}>
                  <View style={s.feeBox}>
                    <Text style={s.feeLbl}>PLATFORM FEE</Text>
                    <Text style={s.feeVal} testID={`payout-fee-${a.vendor_type}`}>{a.fee_pct}%</Text>
                  </View>
                  <View style={s.feeBox}>
                    <Text style={s.feeLbl}>CURRENCY</Text>
                    <Text style={s.feeVal}>{String(a.currency || '').toUpperCase()}</Text>
                  </View>
                </View>

                {/* Earnings dashboard + cash out */}
                <LinearGradient colors={['#059669', '#14B8A6']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                  style={s.earnCard} testID={`payouts-earnings-${a.vendor_type}`}>
                  <View style={s.earnHead}>
                    <View style={{ flex: 1 }}>
                      <Text style={s.earnLbl}>NET EARNINGS</Text>
                      <Text style={s.earnTotal} testID={`payouts-earnings-paid-${a.vendor_type}`}>{money(e.paid_cents)}</Text>
                    </View>
                    {a.ready && (
                      <TouchableOpacity style={s.cashBtn} onPress={() => cashout(a.vendor_type)}
                        disabled={cashing === a.vendor_type} testID={`payout-cashout-${a.vendor_type}`}>
                        {cashing === a.vendor_type
                          ? <ActivityIndicator size="small" color="#059669" />
                          : <><Ionicons name="flash" size={14} color="#059669" /><Text style={s.cashText}>Cash out</Text></>}
                      </TouchableOpacity>
                    )}
                  </View>
                  <Text style={s.earnSub}>{money(e.sales_cents)} sales · {money(e.fees_cents)} fee · {money(e.pending_cents)} pending</Text>
                </LinearGradient>

                {/* Fee Insights */}
                <FeeInsights weeks={insights[a.vendor_type] || []} vendorType={a.vendor_type} />

                {/* Payout History */}
                <PayoutHistory rows={history[a.vendor_type] || []} vendorType={a.vendor_type} />

                {a.ready ? (
                  <View style={s.activeRow} testID={`payout-active-${a.vendor_type}`}>
                    <Ionicons name="checkmark-circle" size={16} color={COLORS.green} />
                    <Text style={s.activeText}>Payouts active — you keep {100 - a.fee_pct}% of each sale.</Text>
                  </View>
                ) : a.has_account ? (
                  <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }, busy === a.vendor_type && { opacity: 0.5 }]}
                    onPress={() => connect(a.vendor_type)} disabled={busy === a.vendor_type}
                    testID={`payout-resume-${a.vendor_type}`}>
                    <Ionicons name="arrow-forward-circle" size={16} color="#fff" />
                    <Text style={common.btnPrimaryText}>{busy === a.vendor_type ? 'Opening…' : 'Finish Stripe setup'}</Text>
                  </TouchableOpacity>
                ) : (
                  <>
                    <Pressable style={s.agreeRow}
                      onPress={() => setAgreed((p) => ({ ...p, [a.vendor_type]: !p[a.vendor_type] }))}
                      testID={`payout-agree-${a.vendor_type}`}>
                      <Ionicons name={isAgreed ? 'checkbox' : 'square-outline'} size={20}
                        color={isAgreed ? COLORS.primary : COLORS.textMuted} />
                      <Text style={s.agreeText}>I agree to a {a.fee_pct}% platform fee per transaction and accept responsibility for any chargebacks, refunds and disputes.</Text>
                    </Pressable>
                    <TouchableOpacity style={[common.btnPrimary, { marginTop: 10 }, (!isAgreed || busy === a.vendor_type) && { opacity: 0.4 }]}
                      onPress={() => connect(a.vendor_type)} disabled={!isAgreed || busy === a.vendor_type}
                      testID={`payout-connect-${a.vendor_type}`}>
                      <Ionicons name="shield-checkmark" size={16} color="#fff" />
                      <Text style={common.btnPrimaryText}>{busy === a.vendor_type ? 'Opening…' : 'Set up payouts with Stripe'}</Text>
                    </TouchableOpacity>
                  </>
                )}
              </View>
            );
          })}

          <Text style={s.footnote}>
            Payouts settle to your connected Stripe account. The platform keeps the fee shown above from each transaction.
          </Text>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function FeeInsights({ weeks, vendorType }: { weeks: any[]; vendorType: string }) {
  const data = weeks || [];
  const max = Math.max(1, ...data.map((w) => Math.max(w.fees_cents || 0, w.net_cents || 0)));
  const total = data.reduce((sum, w) => sum + (w.net_cents || 0) + (w.fees_cents || 0), 0);
  return (
    <View style={s.insCard} testID={`payouts-insights-${vendorType}`}>
      <View style={s.insHead}>
        <Text style={s.insTitle}>FEES VS EARNINGS · 6 WEEKS</Text>
        <View style={s.legendRow}>
          <View style={s.legendDot} /><Text style={s.legendText}>Net</Text>
          <View style={[s.legendDot, { backgroundColor: COLORS.red }]} /><Text style={s.legendText}>Fees</Text>
        </View>
      </View>
      {total === 0 ? (
        <Text style={s.insEmpty} testID={`payouts-insights-empty-${vendorType}`}>No earnings in the last 6 weeks yet.</Text>
      ) : (
        <View style={s.insChart}>
          {data.map((w) => (
            <View key={w.week_start} style={s.insCol}>
              <View style={s.insBars}>
                <View style={[s.insBar, { height: Math.max(2, ((w.net_cents || 0) / max) * 60), backgroundColor: COLORS.green }]} />
                <View style={[s.insBar, { height: Math.max(2, ((w.fees_cents || 0) / max) * 60), backgroundColor: COLORS.red }]} />
              </View>
              <Text style={s.insLabel}>{w.label}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

function PayoutHistory({ rows, vendorType }: { rows: any[]; vendorType: string }) {
  const list = rows || [];
  return (
    <View style={s.histCard} testID={`payouts-history-${vendorType}`}>
      <View style={s.histHead}>
        <Ionicons name="receipt-outline" size={13} color={COLORS.textMuted} />
        <Text style={s.histTitle}>PAYOUT HISTORY</Text>
      </View>
      {list.length === 0 ? (
        <Text style={s.histEmpty} testID={`payouts-history-empty-${vendorType}`}>No transactions yet.</Text>
      ) : (
        list.slice(0, 15).map((t) => (
          <View key={t.id} style={s.histRow} testID={`payouts-history-row-${vendorType}`}>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.histNet}>{money(t.net_cents)} <Text style={s.histNetLbl}>net</Text></Text>
              <Text style={s.histMeta}>{fmtDate(t.date)} · {money(t.gross_cents)} gross · {money(t.fee_cents)} fee</Text>
            </View>
            <HistStatus status={t.status} />
          </View>
        ))
      )}
    </View>
  );
}

function HistStatus({ status }: { status: string }) {
  const ok = status === 'paid' || status === 'succeeded';
  const warn = status === 'pending' || status === 'held_no_account';
  const color = ok ? COLORS.green : warn ? COLORS.gold : status === 'failed' ? COLORS.red : COLORS.textMuted;
  return (
    <View style={[s.histPill, { backgroundColor: color + '1E' }]}>
      <Text style={[s.histPillText, { color }]}>{(status || '—').replace(/_/g, ' ')}</Text>
    </View>
  );
}

function StatusPill({ ready, hasAccount }: { ready: boolean; hasAccount: boolean }) {
  if (ready) return <View style={[s.pill, { backgroundColor: COLORS.green + '18' }]}><Text style={[s.pillText, { color: COLORS.green }]}>ACTIVE</Text></View>;
  if (hasAccount) return <View style={[s.pill, { backgroundColor: COLORS.gold + '22' }]}><Text style={[s.pillText, { color: COLORS.gold }]}>PENDING</Text></View>;
  return <View style={[s.pill, { backgroundColor: COLORS.surface }]}><Text style={[s.pillText, { color: COLORS.textMuted }]}>NOT SET UP</Text></View>;
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  centerPad: { flex: 1, padding: SPACING.xl, alignItems: 'center', justifyContent: 'center', gap: 8 },
  emptyTitle: { color: COLORS.textDim, fontSize: FONT.md, fontWeight: '800' },
  muted: { color: COLORS.textMuted, fontSize: FONT.sm, textAlign: 'center' },
  gate: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: COLORS.purple + '14', borderWidth: 1, borderColor: COLORS.purple + '33', borderRadius: RADIUS.md, padding: 12, marginBottom: SPACING.md },
  gateText: { flex: 1, color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', lineHeight: 17 },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  iconWrap: { width: 40, height: 40, borderRadius: RADIUS.md, backgroundColor: COLORS.primary + '14', alignItems: 'center', justifyContent: 'center' },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  cardSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  feeRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  feeBox: { backgroundColor: COLORS.surface, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 8 },
  feeLbl: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  feeVal: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: 2 },
  earnCard: { borderRadius: RADIUS.lg, padding: SPACING.md, marginTop: 12 },
  earnHead: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  earnLbl: { color: 'rgba(255,255,255,0.85)', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  earnTotal: { color: '#fff', fontSize: 30, fontWeight: '900', marginTop: 2 },
  earnSub: { color: 'rgba(255,255,255,0.92)', fontSize: FONT.xs, fontWeight: '700', marginTop: 6 },
  cashBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: '#fff', borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 8 },
  cashText: { color: '#059669', fontWeight: '900', fontSize: FONT.xs },
  insCard: { backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginTop: 12 },
  insHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  insTitle: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  legendRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  legendDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: COLORS.green },
  legendText: { color: COLORS.textMuted, fontSize: 9, fontWeight: '700', marginRight: 4 },
  insEmpty: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', paddingVertical: 12 },
  insChart: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', height: 78, gap: 4 },
  insCol: { flex: 1, alignItems: 'center', gap: 4 },
  insBars: { flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 60 },
  insBar: { width: 8, borderTopLeftRadius: 2, borderTopRightRadius: 2 },
  insLabel: { color: COLORS.textMuted, fontSize: 8, fontWeight: '700' },
  histCard: { backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginTop: 12 },
  histHead: { flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 8 },
  histTitle: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  histEmpty: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', paddingVertical: 12 },
  histRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, borderTopWidth: 1, borderTopColor: COLORS.cardBorder },
  histNet: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  histNetLbl: { color: COLORS.textMuted, fontWeight: '600', fontSize: FONT.xs },
  histMeta: { color: COLORS.textMuted, fontSize: 10, fontWeight: '600', marginTop: 1 },
  histPill: { borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 3 },
  histPillText: { fontSize: 8, fontWeight: '900', textTransform: 'uppercase' },
  activeRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12 },
  activeText: { flex: 1, color: COLORS.green, fontSize: FONT.sm, fontWeight: '700' },
  agreeRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginTop: 12 },
  agreeText: { flex: 1, color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', lineHeight: 17 },
  pill: { borderRadius: RADIUS.full, paddingHorizontal: 10, paddingVertical: 3 },
  pillText: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  footnote: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', marginTop: SPACING.sm, paddingHorizontal: SPACING.md },
});
