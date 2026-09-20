import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator, Linking,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TSPACE, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', text: '#F5F3FF', dim: '#a5a0c0',
  violet: '#a855f7', accent2: '#7c3aed', green: '#34d399',
};
const money = (c: number) => `$${((c || 0) / 100).toFixed(2)}`;

export default function StudioScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<any>(undefined); // undefined=loading, null=not advisor
  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/payouts/status'); setData(data); }
    catch (_) { setData(null); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const onboard = async () => {
    try { const { data } = await api.post('/social/payouts/onboarding/start', { origin_url: 'https://radiolife.app' }); if (data.onboarding_url) Linking.openURL(data.onboarding_url); }
    catch (_) {}
  };
  const refresh = async () => { try { await api.post('/social/payouts/status/refresh'); load(); } catch (_) {} };

  return (
    <View style={[s.root, { paddingTop: insets.top }]}>
      <View style={s.header}>
        <Pressable testID="studio-back" onPress={() => router.back()} style={s.back}><Ionicons name="chevron-back" size={22} color={D.text} /></Pressable>
        <Text style={s.hTitle}>Advisor Studio</Text>
      </View>
      {data === undefined ? <View style={s.center}><ActivityIndicator color={D.violet} /></View>
        : data === null ? (
          <View style={s.center} testID="studio-not-advisor">
            <Ionicons name="briefcase-outline" size={34} color={D.violet} />
            <Text style={s.emptyTitle}>Advisor tools</Text>
            <Text style={s.emptySub}>Become a verified advisor to earn from private readings and host live Q&A. Apply from the Advisors tab.</Text>
            <Pressable testID="studio-goto-advisors" onPress={() => router.replace('/social/dreams' as any)} style={s.primary}><Text style={s.primaryTxt}>Go to Advisors</Text></Pressable>
          </View>
        ) : (
          <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 14 }} showsVerticalScrollIndicator={false} testID="advisor-payouts">
            <View style={s.card}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <Ionicons name="cash-outline" size={18} color={D.green} /><Text style={s.cardTitle}>Earnings & payouts</Text>
                <Text style={s.fee}>Platform fee {data.commission_pct}%</Text>
              </View>
              <View style={s.statRow}>
                <Stat label="Paid out" value={money(data.earnings?.paid_cents)} />
                <Stat label="Pending" value={money(data.earnings?.pending_cents)} />
                <Stat label="On hold" value={money(data.earnings?.held_cents)} />
              </View>
              {data.payouts_enabled
                ? <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}><Text style={s.enabled}>✓ Payouts enabled</Text><Pressable onPress={refresh}><Text style={s.link}>Refresh</Text></Pressable></View>
                : <View style={{ marginTop: 8 }}>
                    <Text style={s.note}>Connect a payout account (Stripe, test mode in preview) to receive your share of paid readings.</Text>
                    <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
                      <Pressable testID="payouts-onboard" onPress={onboard} style={[s.primary, { flexDirection: 'row', gap: 6 }]}><Ionicons name="open-outline" size={15} color="#fff" /><Text style={s.primaryTxt}>Set up payouts</Text></Pressable>
                      <Pressable testID="payouts-refresh" onPress={refresh} style={s.ghost}><Text style={s.ghostTxt}>I've finished</Text></Pressable>
                    </View>
                  </View>}
            </View>

            <View style={s.card}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><Ionicons name="radio" size={18} color={D.violet} /><Text style={s.cardTitle}>Host a live Q&A</Text></View>
              <Text style={s.note}>Go live to answer the community's dream questions in real time.</Text>
              <Pressable testID="studio-host-live" onPress={() => router.push('/social/dreams/live' as any)} style={[s.primary, { marginTop: 10 }]}><Text style={s.primaryTxt}>Open Live Q&A</Text></Pressable>
            </View>

            <GetFeatured />

            {(data.ledger || []).length > 0 && (<>
              <Text style={s.section}>PAYOUT HISTORY</Text>
              {data.ledger.map((p: any, i: number) => (
                <View key={i} style={s.ledger}>
                  <View style={{ flex: 1 }}><Text style={s.ledgerAmt}>{money(p.advisor_share_cents)}</Text><Text style={s.ledgerMeta}>of {money(p.gross_cents)} · {p.status.replace(/_/g, ' ')}</Text></View>
                </View>
              ))}
            </>)}
          </ScrollView>
        )}
    </View>
  );
}

function Stat({ label, value }: any) {
  return <View style={s.stat}><Text style={s.statVal}>{value}</Text><Text style={s.statLbl}>{label}</Text></View>;
}

function GetFeatured() {
  const [cfg, setCfg] = useState<any>(null);
  const [surface, setSurface] = useState('both');
  const [an, setAn] = useState<any>(null);
  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/ads/config'); setCfg(data); } catch (_) {}
    try { const { data } = await api.get('/social/ads/analytics'); setAn(data); } catch (_) {}
  }, []);
  useEffect(() => { load(); }, [load]);
  if (!cfg || !cfg.is_advisor) return null;
  const active = cfg.active_promotion;
  const buy = async (tier: string) => {
    try { const { data } = await api.post('/social/ads/checkout', { tier, surface, origin_url: 'https://radiolife.app' }); if (data.checkout_url) Linking.openURL(data.checkout_url); } catch (_) {}
  };
  return (
    <View style={s.card} testID="get-featured">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        <Ionicons name="rocket" size={18} color="#fbbf24" /><Text style={s.cardTitle}>Get featured</Text>
        <Pressable onPress={load} style={{ marginLeft: 'auto' }}><Text style={s.link}>Refresh</Text></Pressable>
      </View>
      {an && an.totals && (an.totals.views > 0 || an.totals.bookings > 0 || (an.promotions || []).length > 0) && (
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }} testID="ad-analytics">
          <Stat label="Views" value={an.totals.views} />
          <Stat label="Bookings" value={an.totals.bookings} />
          <Stat label="Revenue" value={money(an.totals.revenue_cents)} />
        </View>
      )}
      {active
        ? <View style={s.featActive} testID="featured-active"><Text style={s.featActiveTxt}>★ Featured on {active.surface_label} until {new Date(active.ends_at).toLocaleDateString()}</Text></View>
        : (<>
          <Text style={[s.note, { marginTop: 10 }]}>Pin yourself to the top with a Featured badge. Doesn’t affect reviews or fairness.</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
            {cfg.surfaces.map((su: any) => (
              <Pressable key={su.key} testID={`feature-surface-${su.key}`} onPress={() => setSurface(su.key)} style={[s.surf, surface === su.key && s.surfA]}><Text style={[s.surfTxt, surface === su.key && { color: '#fff' }]}>{su.label}</Text></Pressable>
            ))}
          </View>
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 8 }}>
            {cfg.tiers.map((t: any) => (
              <Pressable key={t.key} testID={`feature-tier-${t.key}`} onPress={() => buy(t.key)} style={s.tier}>
                <Text style={s.tierPrice}>{money(t.price_cents)}</Text><Text style={s.tierLbl}>{t.label}</Text>
              </Pressable>
            ))}
          </View>
        </>)}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: D.bg },
  featActive: { backgroundColor: 'rgba(251,191,36,0.1)', borderColor: 'rgba(251,191,36,0.25)', borderWidth: 1, borderRadius: 14, padding: 12, marginTop: 8 },
  featActiveTxt: { color: '#fcd34d', fontSize: TFONT.xs, lineHeight: 18 },
  surf: { flex: 1, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.05)', alignItems: 'center', justifyContent: 'center' },
  surfA: { backgroundColor: D.accent2 },
  surfTxt: { color: D.dim, fontSize: 11, fontWeight: '800' },
  tier: { flex: 1, backgroundColor: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 16, paddingVertical: 12, alignItems: 'center' },
  tierPrice: { color: D.text, fontSize: TFONT.md, fontWeight: '900' },
  tierLbl: { color: '#6d6a86', fontSize: 10, marginTop: 2 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 30, gap: 10 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 10 },
  back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  hTitle: { color: D.text, fontSize: TFONT.xl, fontWeight: '900' },
  emptyTitle: { color: D.text, fontSize: TFONT.lg, fontWeight: '900', marginTop: 4 },
  emptySub: { color: D.dim, fontSize: TFONT.sm, textAlign: 'center', lineHeight: 20 },
  card: { backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 22, padding: 16 },
  cardTitle: { color: D.text, fontSize: TFONT.md, fontWeight: '900' },
  fee: { color: '#6d6a86', fontSize: 11, marginLeft: 'auto' },
  statRow: { flexDirection: 'row', gap: 8, marginTop: 12 },
  stat: { flex: 1, backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 16, paddingVertical: 12, alignItems: 'center' },
  statVal: { color: D.text, fontSize: TFONT.lg, fontWeight: '900' },
  statLbl: { color: '#6d6a86', fontSize: 10, textTransform: 'uppercase', letterSpacing: 1, marginTop: 2 },
  enabled: { color: D.green, fontWeight: '900', fontSize: TFONT.sm },
  link: { color: D.dim, fontSize: TFONT.xs, textDecorationLine: 'underline' },
  note: { color: D.dim, fontSize: TFONT.xs, lineHeight: 18 },
  primary: { backgroundColor: D.accent2, height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 },
  primaryTxt: { color: '#fff', fontWeight: '900', fontSize: TFONT.sm },
  ghost: { backgroundColor: 'rgba(255,255,255,0.06)', height: 42, borderRadius: 21, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 18 },
  ghostTxt: { color: '#cbd5e1', fontWeight: '900', fontSize: TFONT.sm },
  section: { color: D.dim, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 1 },
  ledger: { flexDirection: 'row', backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 16, padding: 14 },
  ledgerAmt: { color: D.text, fontSize: TFONT.md, fontWeight: '900' },
  ledgerMeta: { color: D.dim, fontSize: 11, marginTop: 2 },
});
