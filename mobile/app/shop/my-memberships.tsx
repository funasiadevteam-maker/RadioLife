// Membership Wallet (mobile) — "My Memberships" across venues with claim
// buttons per benefit and renewal dates.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c?: number) => (c == null ? '' : `$${(c / 100).toFixed(2)}`);
const fmtDate = (iso?: string) => {
  if (!iso) return null;
  try { return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }); }
  catch { return null; }
};

export default function MyMemberships() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [savings, setSavings] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [pick, setPick] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ id: string; msg: string } | null>(null);

  const load = useCallback(async () => {
    try { const r = await api.get('/shop/memberships/mine'); setItems(r.data.items || []); }
    catch { /* ignore */ } finally { setLoading(false); setRefreshing(false); }
    api.get('/shop/memberships/savings').then((r) => setSavings(r.data)).catch(() => {});
  }, []);
  useEffect(() => { load(); }, [load]);

  const entId = (b: any) => b.entitlement_id || b.benefit_id;
  const claim = async (m: any, b: any) => {
    const eid = entId(b);
    if (b.options?.length && !pick[eid]) { setFlash({ id: eid, msg: 'Pick an option first' }); return; }
    setBusy(eid); setFlash(null);
    try {
      await api.post(`/shop/memberships/${m.membership_id}/claim`, { entitlement_id: eid, option: pick[eid] || null });
      await load();
      setFlash({ id: eid, msg: 'Claimed! 🎉' });
    } catch (e: any) {
      setFlash({ id: eid, msg: e?.response?.data?.detail?.code === 'limit_reached' ? 'Limit reached this period' : 'Could not claim' });
    } finally { setBusy(null); }
  };
  const orderItem = (m: any, b: any, it: any) => {
    router.push(`/shop/menu/${m.business_id}?item=${it.id}&apply_entitlement=${entId(b)}` as any);
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="mymem-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title}>My Memberships</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 100 }} testID="mymem-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary} onRefresh={() => { setRefreshing(true); load(); }} />}>
        {savings && savings.lifetime_savings_cents > 0 && (
          <View style={s.savings} testID="savings-tracker">
            <Ionicons name="trending-up" size={26} color="#fff" />
            <View style={{ flex: 1 }}>
              <Text style={s.savingsMonth} testID="savings-month">{money(savings.month_savings_cents)}<Text style={s.savingsMonthSub}> this month</Text></Text>
              <Text style={s.savingsSub}>{money(savings.lifetime_savings_cents)} saved all-time · {savings.lifetime_count} perks used</Text>
            </View>
          </View>
        )}
        {!items.length ? (
          <View style={{ alignItems: 'center', paddingVertical: 60 }} testID="mymem-empty">
            <Ionicons name="ribbon-outline" size={44} color={COLORS.textMuted} />
            <Text style={{ color: COLORS.textDim, fontWeight: '800', marginTop: 12 }}>No memberships yet</Text>
            <TouchableOpacity style={[common.btnGhost, { marginTop: 16, paddingHorizontal: 24 }]} onPress={() => router.push('/shop')} testID="mymem-browse">
              <Text style={common.btnGhostText}>Explore the Shop</Text>
            </TouchableOpacity>
          </View>
        ) : items.map((m) => (
          <View key={m.membership_id} style={s.card} testID={`mymem-${m.membership_id}`}>
            <View style={s.cardHead}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                  <Ionicons name="ribbon" size={16} color={COLORS.primary} />
                  <Text style={s.plan} numberOfLines={1}>{m.plan_name || 'Membership'}</Text>
                </View>
                <Text style={s.sponsor} numberOfLines={1}>{m.sponsor_name}</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={s.price}>{money(m.price_cents)}<Text style={s.per}>/{m.interval || 'mo'}</Text></Text>
                {fmtDate(m.current_period_end) && (
                  <Text style={s.renew}>Renews {fmtDate(m.current_period_end)}</Text>
                )}
              </View>
            </View>

            {(m.benefits || []).map((b: any) => {
              const out = b.remaining <= 0;
              const eid = entId(b);
              const orderable = ['item', 'product', 'category'].includes(b.target_type) && (b.eligible_items || []).length > 0;
              return (
                <View key={eid} style={s.benefit} testID={`mymem-benefit-${eid}`}>
                  <View style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.bLabel} numberOfLines={1}>{b.label}</Text>
                      <Text style={s.bMeta}>{b.remaining} of {b.qty} left this {b.period}{b.available_now === false ? ' · off-hours' : ''}</Text>
                    </View>
                    {!orderable && (
                      <TouchableOpacity
                        style={[s.claimBtn, out && s.claimBtnOut]}
                        disabled={out || busy === eid}
                        onPress={() => claim(m, b)}
                        testID={`mymem-claim-${eid}`}>
                        {busy === eid ? <ActivityIndicator color="#fff" size="small" />
                          : <Text style={[s.claimText, out && { color: COLORS.textMuted }]}>{out ? 'Used' : 'Claim'}</Text>}
                      </TouchableOpacity>
                    )}
                  </View>

                  {orderable && !out && (
                    <View style={{ marginTop: 8 }}>
                      <Text style={s.orderHint}>ORDER WITH THIS MEMBERSHIP</Text>
                      <ScrollView horizontal showsHorizontalScrollIndicator={false} testID={`mymem-order-row-${eid}`}>
                        {b.eligible_items.map((it: any) => (
                          <TouchableOpacity key={it.id} style={s.orderCard} onPress={() => orderItem(m, b, it)} testID={`mymem-order-${eid}-${it.id}`}>
                            {!!it.image_url && <Image source={{ uri: it.image_url }} style={s.orderImg} contentFit="cover" />}
                            <Text style={s.orderName} numberOfLines={2}>{it.name}</Text>
                            <View style={s.orderCta}><Ionicons name="bag-add" size={11} color={COLORS.primary} /><Text style={s.orderCtaText}>Order</Text></View>
                          </TouchableOpacity>
                        ))}
                      </ScrollView>
                    </View>
                  )}

                  {b.options?.length > 0 && !orderable && !out && (
                    <View style={s.optRow}>
                      {b.options.map((o: string) => (
                        <TouchableOpacity key={o} onPress={() => setPick((p) => ({ ...p, [eid]: o }))}
                          style={[s.opt, pick[eid] === o && s.optOn]} testID={`mymem-opt-${eid}-${o}`}>
                          <Text style={[s.optText, pick[eid] === o && { color: '#fff' }]}>{o}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  )}
                  {flash?.id === eid && <Text style={s.flash}>{flash.msg}</Text>}
                </View>
              );
            })}
            {!(m.benefits || []).length && <Text style={s.bMeta}>No claimable perks on this plan.</Text>}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  savings: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: COLORS.primary, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  savingsMonth: { color: '#fff', fontSize: 22, fontWeight: '900' },
  savingsMonthSub: { fontSize: FONT.sm, fontWeight: '800', opacity: 0.85 },
  savingsSub: { color: '#fff', fontSize: 11, fontWeight: '700', opacity: 0.9, marginTop: 2 },
  title: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  cardHead: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: 10 },
  plan: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  sponsor: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  price: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  per: { color: COLORS.textMuted, fontWeight: '700' },
  renew: { color: COLORS.textDim, fontSize: 11, fontWeight: '700', marginTop: 2 },
  benefit: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, padding: 12, marginTop: 10 },
  bLabel: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  bMeta: { color: COLORS.textDim, fontSize: 11, fontWeight: '700', marginTop: 2 },
  claimBtn: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 18, paddingVertical: 9, minWidth: 72, alignItems: 'center' },
  claimBtnOut: { backgroundColor: COLORS.surfaceBorder },
  claimText: { color: '#fff', fontWeight: '900', fontSize: FONT.sm },
  optRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 8 },
  orderHint: { color: COLORS.textMuted, fontSize: 10, fontWeight: '900', marginBottom: 6 },
  orderCard: { width: 108, marginRight: 8, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, overflow: 'hidden', padding: 0 },
  orderImg: { width: '100%', height: 64, backgroundColor: COLORS.inputBg },
  orderName: { color: COLORS.text, fontSize: 11, fontWeight: '800', paddingHorizontal: 8, paddingTop: 6, lineHeight: 14 },
  orderCta: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 8, paddingVertical: 6 },
  orderCtaText: { color: COLORS.primary, fontSize: 10, fontWeight: '900' },
  opt: { paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  optOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  optText: { color: COLORS.textDim, fontSize: 11, fontWeight: '800' },
  flash: { color: COLORS.primary, fontSize: 11, fontWeight: '800', marginTop: 6 },
});
