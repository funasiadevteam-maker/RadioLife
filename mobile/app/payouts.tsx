// Unified Payouts & Earnings — advisor (15%) + merchant (5%) Stripe Connect.
// Reads /api/payouts/overview, onboards via /api/payouts/onboard (hosted link
// opened in the system browser), and re-syncs status on return. Mobile parity
// with the web Payments, Payouts & Earnings page.
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

const TYPE_META: Record<string, { label: string; icon: any; blurb: string }> = {
  advisor: { label: 'Expert / Advisor', icon: 'sparkles-outline', blurb: 'Get paid for readings & sessions' },
  merchant: { label: 'Business / Store', icon: 'storefront-outline', blurb: 'Get paid for sales & bookings' },
};

export default function Payouts() {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [agreed, setAgreed] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    try { const r = await api.get('/payouts/overview'); setData(r.data); }
    catch { setData({ eligible: false, accounts: [] }); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const refreshStatus = async (vendorType: string) => {
    try { await api.post('/payouts/refresh', { vendor_type: vendorType }); } catch { /* no account yet */ }
  };

  const connect = async (vendorType: string) => {
    setBusy(vendorType);
    try {
      const r = await api.post('/payouts/onboard', {
        vendor_type: vendorType, agreement_accepted: true, origin_url: BACKEND,
      });
      if (r.data?.onboarding_url) {
        await WebBrowser.openBrowserAsync(r.data.onboarding_url);
        await refreshStatus(vendorType);
        await load();
      }
    } catch { /* surfaced via reload state */ }
    finally { setBusy(null); }
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

                {/* Earnings dashboard */}
                <LinearGradient colors={['#059669', '#14B8A6']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                  style={s.earnCard} testID={`payouts-earnings-${a.vendor_type}`}>
                  <Text style={s.earnLbl}>NET EARNINGS</Text>
                  <Text style={s.earnTotal} testID={`payouts-earnings-paid-${a.vendor_type}`}>{money(e.paid_cents)}</Text>
                  <Text style={s.earnSub}>{money(e.sales_cents)} sales · {money(e.fees_cents)} fee · {money(e.pending_cents)} pending</Text>
                </LinearGradient>

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
  earnLbl: { color: 'rgba(255,255,255,0.85)', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  earnTotal: { color: '#fff', fontSize: 30, fontWeight: '900', marginTop: 2 },
  earnSub: { color: 'rgba(255,255,255,0.92)', fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  activeRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12 },
  activeText: { flex: 1, color: COLORS.green, fontSize: FONT.sm, fontWeight: '700' },
  agreeRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginTop: 12 },
  agreeText: { flex: 1, color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', lineHeight: 17 },
  pill: { borderRadius: RADIUS.full, paddingHorizontal: 10, paddingVertical: 3 },
  pillText: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  footnote: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', marginTop: SPACING.sm, paddingHorizontal: SPACING.md },
});
