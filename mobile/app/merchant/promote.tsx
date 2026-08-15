// Merchant "Promote my Shop" (Phase F) — tiered Stripe promotion + promo
// analytics (extra views/orders), auto-renew via a saved card, and a
// per-impression Category Spotlight bid auction.
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Switch, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useReward } from '../../src/components/RewardOverlay';

const money = (c: number) => `$${((c || 0) / 100).toFixed(2)}`;
const cents = (c: number) => `${c}¢`;
const STATUS_LABEL: Record<string, string> = {
  pending_payment: 'Awaiting payment', pending_review: 'In review',
  active: 'Live', rejected: 'Rejected', expired: 'Expired',
};

function Stat({ label, value, extra }: { label: string; value: string | number; extra?: string | null }) {
  return (
    <View style={s.stat}>
      <Text style={s.statVal}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
      {extra ? <Text style={s.statExtra}>+{extra} vs before</Text> : null}
    </View>
  );
}

export default function Promote() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [tiers, setTiers] = useState<any[]>([]);
  const [data, setData] = useState<any>(null);
  const [analytics, setAnalytics] = useState<any>(null);
  const [cbid, setCbid] = useState<any>(null);
  const [cats, setCats] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [bidCat, setBidCat] = useState('');
  const [bidCents, setBidCents] = useState('5');
  const [topupDollars, setTopupDollars] = useState('10');

  const load = useCallback(async () => {
    try {
      const [t, m, a, cb, cc] = await Promise.all([
        api.get('/merchant/marketplace/promotion/tiers'),
        api.get('/merchant/marketplace/promotion'),
        api.get('/merchant/marketplace/promotion/analytics').catch(() => ({ data: { has_data: false } })),
        api.get('/merchant/marketplace/category-bid').catch(() => ({ data: {} })),
        api.get('/merchant/marketplace/category-bid/categories').catch(() => ({ data: { items: [] } })),
      ]);
      setTiers(t.data.tiers || []);
      setData(m.data);
      setAnalytics(a.data);
      setCbid(cb.data);
      setCats(cc.data.items || []);
      if (cb.data?.bid?.category) setBidCat(cb.data.bid.category);
      else if ((cc.data.items || [])[0]) setBidCat(cc.data.items[0].key);
      if (cb.data?.bid?.bid_cents) setBidCents(String(cb.data.bid.bid_cents));
    } catch { setData({ no_profile: true }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const buy = async (tier: string) => {
    setBusy(tier);
    try {
      const r = await api.post('/merchant/marketplace/promotion/checkout', { tier, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/merchant/marketplace/promotion/${r.data.promotion_id}/status`);
        if (st.data.status === 'pending_review') celebrate({ points: 0, title: 'Submitted for review 🚀' });
        load();
      }
    } catch { celebrate({ points: 0, title: 'Could not start checkout' }); }
    finally { setBusy(null); }
  };

  const toggleAutoRenew = async (enabled: boolean) => {
    const active = data?.active;
    if (!active) return;
    if (enabled && !data?.default_pm && !(data?.saved_cards || []).length) {
      celebrate({ points: 0, title: 'Add a card in Wallet first' });
      return;
    }
    try {
      await api.post(`/merchant/marketplace/promotion/${active.promotion_id}/auto-renew`,
        { enabled, payment_method_id: data?.default_pm });
      load();
    } catch { celebrate({ points: 0, title: 'Could not update auto-renew' }); }
  };

  const saveBid = async () => {
    setBusy('bid');
    try {
      const r = await api.post('/merchant/marketplace/category-bid/set',
        { category: bidCat, bid_cents: Math.max(1, parseInt(bidCents, 10) || 1) });
      setCbid((c: any) => ({ ...(c || {}), standing: r.data.standing }));
      load();
    } catch { celebrate({ points: 0, title: 'Could not save bid' }); }
    finally { setBusy(null); }
  };

  const topUp = async () => {
    setBusy('topup');
    try {
      const amt = Math.round(parseFloat(topupDollars) * 100);
      const r = await api.post('/merchant/marketplace/category-bid/topup/checkout',
        { amount_cents: amt, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        await api.get(`/merchant/marketplace/category-bid/topup/${r.data.session_id}/status`);
        load();
      }
    } catch { celebrate({ points: 0, title: 'Could not start top-up' }); }
    finally { setBusy(null); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (data?.no_profile) return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="promote-back"><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle}>Promote my Shop</Text><View style={{ width: 22 }} />
      </View>
      <View style={common.center}><Text style={{ color: COLORS.textDim }}>You don&apos;t have a business yet.</Text></View>
    </SafeAreaView>
  );

  const active = data?.active;
  const history = (data?.items || []).filter((p: any) => !active || p.promotion_id !== active.promotion_id);
  const bid = cbid?.bid;
  const standing = cbid?.standing;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="promote-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Promote my Shop</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="promote-root">
        <Text style={s.intro}>Boost <Text style={{ fontWeight: '900' }}>{data?.public_name}</Text> to the top of Shop search and the &quot;Promoted near you&quot; rail. Promotions go live once our team approves them.</Text>

        {active && (
          <View style={s.activeCard} testID="promote-active">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="checkmark-circle" size={20} color={COLORS.green} />
              <Text style={s.activeText}>You&apos;re promoted — {active.name}, until {new Date(active.expires_at).toLocaleDateString()}.</Text>
            </View>
            <View style={s.autoRow}>
              <View style={{ flex: 1 }}>
                <Text style={s.autoTitle}>Auto-renew</Text>
                <Text style={s.autoHint}>{data?.default_pm || (data?.saved_cards || []).length ? 'Charges your saved card at expiry.' : 'Add a card in Wallet to enable.'}</Text>
              </View>
              <Switch value={!!data?.auto_renew} onValueChange={toggleAutoRenew}
                trackColor={{ true: COLORS.green, false: COLORS.surfaceBorder }} testID="promote-autorenew-toggle" />
            </View>
          </View>
        )}

        {analytics?.has_data && (
          <View style={s.card} testID="promote-analytics">
            <Text style={s.cardTitle}><Ionicons name="bar-chart" size={15} color={COLORS.primary} />  Promotion impact</Text>
            <Text style={s.cardSub}>Since your {analytics.tier} promotion started</Text>
            <View style={s.statRow}>
              <Stat label="Views" value={analytics.views} extra={analytics.extra_views ? String(analytics.extra_views) : null} />
              <Stat label="Impressions" value={analytics.impressions} extra={analytics.extra_impressions ? String(analytics.extra_impressions) : null} />
            </View>
            <View style={s.statRow}>
              <Stat label="Orders" value={analytics.orders} extra={analytics.extra_orders ? String(analytics.extra_orders) : null} />
              <Stat label="Revenue" value={money(analytics.revenue_cents)} extra={analytics.extra_revenue_cents ? money(analytics.extra_revenue_cents) : null} />
            </View>
          </View>
        )}

        {tiers.map((t) => {
          const isActiveTier = active && active.tier === t.tier;
          return (
            <View key={t.tier} style={[s.card, t.tier === 'boost_14' && s.cardHot]} testID={`promote-tier-${t.tier}`}>
              <View style={s.cardHead}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                  <Ionicons name="trending-up" size={16} color={COLORS.primary} />
                  <Text style={s.tierName}>{t.name}</Text>
                  {t.tier === 'boost_14' && <View style={s.popBadge}><Text style={s.popText}>POPULAR</Text></View>}
                </View>
                <Text style={s.price}>{money(t.price_cents)}</Text>
              </View>
              <Text style={s.blurb}>{t.blurb}</Text>
              <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }, isActiveTier && { opacity: 0.5 }]}
                onPress={() => buy(t.tier)} disabled={!!busy || isActiveTier} testID={`promote-buy-${t.tier}`}>
                {busy === t.tier ? <ActivityIndicator color="#fff" />
                  : <Text style={common.btnPrimaryText}>{isActiveTier ? 'Current promotion' : `Promote for ${t.days} days`}</Text>}
              </TouchableOpacity>
            </View>
          );
        })}

        {/* Category Spotlight bid auction */}
        <View style={s.card} testID="promote-category-spotlight">
          <Text style={s.cardTitle}><Ionicons name="locate" size={15} color={COLORS.primary} />  Category Spotlight</Text>
          <Text style={s.cardSub}>Bid per impression to top one category. Highest bid ranks first; you only pay from your prepaid budget as your shop is shown.</Text>

          {standing && bid && (
            <View style={[s.standing, standing.outbid ? s.standingBad : s.standingGood]} testID="promote-bid-standing">
              <Text style={[s.standingTitle, { color: standing.outbid ? COLORS.red : COLORS.green }]}>
                {standing.rank ? `You're #${standing.rank} of ${standing.competitors} in ${bid.category}` : `Not ranking yet in ${bid.category}`}
              </Text>
              <Text style={s.standingSub}>Top bid {cents(standing.top_bid_cents)} · your bid {cents(bid.bid_cents)} · budget {money(bid.budget_cents)} left</Text>
              {standing.outbid && (
                <Text style={s.outbid} testID="promote-outbid-alert">You&apos;ve been outbid — bid {cents(standing.suggested_bid_cents)}+ to take #1.</Text>
              )}
            </View>
          )}

          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 8 }}>
            {cats.map((c) => (
              <TouchableOpacity key={c.key} onPress={() => setBidCat(c.key)} testID={`promote-bid-cat-${c.key}`}
                style={[s.catChip, bidCat === c.key && s.catChipOn]}>
                <Text style={[s.catChipText, bidCat === c.key && { color: '#fff' }]}>{c.name}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>

          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <View style={s.bidInputWrap}>
              <TextInput value={bidCents} onChangeText={setBidCents} keyboardType="number-pad"
                style={s.bidInput} testID="promote-bid-cents" />
              <Text style={s.bidUnit}>¢/imp</Text>
            </View>
            <TouchableOpacity style={s.bidBtn} onPress={saveBid} disabled={busy === 'bid'} testID="promote-bid-save">
              <Text style={s.bidBtnText}>{busy === 'bid' ? 'Saving…' : bid ? 'Update bid' : 'Place bid'}</Text>
            </TouchableOpacity>
          </View>

          {bid && (
            <View style={s.topupRow}>
              <View style={s.topupInputWrap}>
                <Text style={s.dollar}>$</Text>
                <TextInput value={topupDollars} onChangeText={setTopupDollars} keyboardType="decimal-pad"
                  style={s.topupInput} testID="promote-topup-amount" />
              </View>
              <TouchableOpacity style={s.topupBtn} onPress={topUp} disabled={busy === 'topup'} testID="promote-topup-btn">
                <Text style={s.topupBtnText}>{busy === 'topup' ? '…' : 'Add budget'}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {history.length > 0 && (
          <View style={{ marginTop: 8 }}>
            <Text style={s.histTitle}>History</Text>
            {history.map((p: any) => (
              <View key={p.promotion_id} style={s.histRow} testID={`promote-history-${p.promotion_id}`}>
                <Text style={s.histName}>{p.name} · {p.price_cents ? money(p.price_cents) : 'COMP'}{p.renewed ? ' · renewed' : ''}</Text>
                <Text style={[s.histStatus, p.status === 'active' && { color: COLORS.green }, p.status === 'rejected' && { color: COLORS.red }]}>{STATUS_LABEL[p.status] || p.status}</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md, lineHeight: 20 },
  activeCard: { backgroundColor: COLORS.green + '15', borderWidth: 1, borderColor: COLORS.green + '55', borderRadius: RADIUS.md, padding: 12, marginBottom: SPACING.md },
  activeText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  autoRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: COLORS.green + '33' },
  autoTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  autoHint: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  cardHot: { borderColor: COLORS.primary, borderWidth: 2 },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  cardSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2, marginBottom: 8, lineHeight: 17 },
  cardHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  tierName: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  popBadge: { backgroundColor: COLORS.primary, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full },
  popText: { color: '#fff', fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  price: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  blurb: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 6, lineHeight: 19 },
  statRow: { flexDirection: 'row', gap: 8, marginTop: 8 },
  stat: { flex: 1, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, padding: 10 },
  statVal: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  statLabel: { color: COLORS.textMuted, fontSize: 11, fontWeight: '700' },
  statExtra: { color: COLORS.green, fontSize: 11, fontWeight: '900', marginTop: 2 },
  standing: { borderRadius: RADIUS.md, padding: 10, marginBottom: 8, borderWidth: 1 },
  standingGood: { backgroundColor: COLORS.green + '12', borderColor: COLORS.green + '44' },
  standingBad: { backgroundColor: COLORS.red + '12', borderColor: COLORS.red + '44' },
  standingTitle: { fontSize: FONT.sm, fontWeight: '900' },
  standingSub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  outbid: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '900', marginTop: 4 },
  catChip: { flexShrink: 0, height: 34, justifyContent: 'center', paddingHorizontal: 14, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  catChipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  catChipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  bidInputWrap: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 10 },
  bidInput: { width: 44, color: COLORS.text, fontSize: FONT.md, fontWeight: '900', paddingVertical: 10, textAlign: 'center' },
  bidUnit: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
  bidBtn: { flex: 1, backgroundColor: COLORS.text, borderRadius: RADIUS.full, paddingVertical: 12, alignItems: 'center' },
  bidBtnText: { color: COLORS.card, fontSize: FONT.sm, fontWeight: '900' },
  topupRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10, paddingTop: 10, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder },
  topupInputWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 10 },
  dollar: { color: COLORS.textMuted, fontSize: FONT.md, fontWeight: '800' },
  topupInput: { flex: 1, color: COLORS.text, fontSize: FONT.md, fontWeight: '900', paddingVertical: 10, paddingHorizontal: 4 },
  topupBtn: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 18, paddingVertical: 12 },
  topupBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  histTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 8 },
  histRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  histName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  histStatus: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900' },
});
