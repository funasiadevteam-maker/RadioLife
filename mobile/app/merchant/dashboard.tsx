// Merchant Dashboard — orders, BigPoints, happy hour (Marketplace Phase B).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, Switch, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const NEXT: Record<string, string> = { accepted: 'preparing', preparing: 'ready', ready: 'picked_up' };
const NEXT_LABEL: Record<string, string> = {
  accepted: 'Start Preparing', preparing: 'Mark Ready', ready: 'Mark Picked Up' };

export default function MerchantDashboard() {
  const router = useRouter();
  const [dash, setDash] = useState<any>(null);
  const [orders, setOrders] = useState<any[]>([]);
  const [hh, setHh] = useState<any>({ enabled: false, start_hour: 17, end_hour: 19, multiplier: 2 });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [savingHh, setSavingHh] = useState(false);

  const load = useCallback(async () => {
    try {
      const [d, o, h] = await Promise.all([
        api.get('/merchant/marketplace/dashboard'),
        api.get('/merchant/marketplace/orders'),
        api.get('/merchant/marketplace/happy-hour'),
      ]);
      setDash(d.data);
      setOrders(o.data.items || []);
      if (h.data.happy_hour) setHh(h.data.happy_hour);
    } catch { /* ignore */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const advance = async (order: any) => {
    const next = NEXT[order.status];
    if (!next) return;
    try {
      await api.patch(`/merchant/marketplace/orders/${order.order_id}/status`, { status: next });
      load();
    } catch { /* ignore */ }
  };

  const saveHh = async (patch: any) => {
    const nextHh = { ...hh, ...patch };
    setHh(nextHh); setSavingHh(true);
    try { await api.patch('/merchant/marketplace/happy-hour', nextHh); load(); }
    catch { /* ignore */ }
    finally { setSavingHh(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  const noProfile = !dash;
  const inactive = dash && !dash.subscription_active;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="merchant-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Merchant Dashboard</Text>
        <TouchableOpacity onPress={() => router.push('/merchant/menu')} testID="merchant-menu-link">
          <Ionicons name="restaurant-outline" size={20} color={COLORS.text} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="merchant-dash-root"
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}>

        {noProfile ? (
          <View style={s.notice} testID="merchant-no-profile">
            <Ionicons name="storefront-outline" size={22} color={COLORS.primary} />
            <Text style={s.noticeText}>You don&apos;t have a business yet.</Text>
            <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }]} onPress={() => router.push('/sell')} testID="merchant-sell-cta">
              <Text style={common.btnPrimaryText}>Sell on RadioLife</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <>
            {inactive && (
              <TouchableOpacity style={s.subBanner} onPress={() => router.push('/merchant/subscribe')} testID="merchant-sub-banner">
                <Ionicons name="lock-closed" size={18} color="#fff" />
                <Text style={s.subBannerText}>Subscribe to list & sell on RadioLife →</Text>
              </TouchableOpacity>
            )}

            <Text style={s.biz}>{dash.public_name}</Text>

            <View style={s.statGrid}>
              <View style={s.stat}><Text style={s.statNum} testID="stat-open-orders">{dash.open_orders}</Text><Text style={s.statLbl}>Open Orders</Text></View>
              <View style={s.stat}><Text style={s.statNum}>{money(dash.revenue_cents)}</Text><Text style={s.statLbl}>Revenue</Text></View>
              <View style={s.stat}><Text style={s.statNum}>{dash.bigpoints_spent}</Text><Text style={s.statLbl}>Points Spent</Text></View>
              <View style={s.stat}><Text style={s.statNum}>{dash.menu_item_count}</Text><Text style={s.statLbl}>Menu Items</Text></View>
            </View>

            <View style={s.rowBtns}>
              <TouchableOpacity style={[s.linkBtn]} onPress={() => router.push('/merchant/menu')} testID="merchant-open-menu">
                <Ionicons name="restaurant" size={16} color={COLORS.primary} />
                <Text style={s.linkText}>Menu Builder</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.linkBtn]} onPress={() => router.push('/merchant/services')} testID="merchant-open-services">
                <Ionicons name="cut" size={16} color={COLORS.primary} />
                <Text style={s.linkText}>Services</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[s.linkBtn]} onPress={() => router.push('/merchant/subscribe')} testID="merchant-open-sub">
                <Ionicons name="card" size={16} color={COLORS.primary} />
                <Text style={s.linkText}>{dash.subscription_active ? 'Plan' : 'Subscribe'}</Text>
              </TouchableOpacity>
            </View>

            {/* Happy Hour */}
            <View style={s.card} testID="merchant-happy-hour">
              <View style={s.hhHead}>
                <View style={{ flex: 1 }}>
                  <Text style={s.cardTitle}>Happy Hour Boost</Text>
                  <Text style={s.cardHint}>
                    Give {hh.multiplier}X BigPoints during set hours{dash.happy_hour_active_now ? ' · LIVE NOW' : ''}.
                  </Text>
                </View>
                <Switch value={!!hh.enabled} onValueChange={(v) => saveHh({ enabled: v })}
                  trackColor={{ true: COLORS.primary }} testID="hh-toggle" disabled={savingHh} />
              </View>
              {hh.enabled && (
                <View style={s.hhRow}>
                  <View style={s.hhField}>
                    <Text style={s.hhLbl}>START (0-23)</Text>
                    <TextInput style={s.hhInput} keyboardType="number-pad" defaultValue={String(hh.start_hour)}
                      onEndEditing={(e) => saveHh({ start_hour: Math.min(23, Math.max(0, parseInt(e.nativeEvent.text || '0', 10) || 0)) })}
                      testID="hh-start" />
                  </View>
                  <View style={s.hhField}>
                    <Text style={s.hhLbl}>END (0-23)</Text>
                    <TextInput style={s.hhInput} keyboardType="number-pad" defaultValue={String(hh.end_hour)}
                      onEndEditing={(e) => saveHh({ end_hour: Math.min(23, Math.max(0, parseInt(e.nativeEvent.text || '0', 10) || 0)) })}
                      testID="hh-end" />
                  </View>
                  <View style={s.hhField}>
                    <Text style={s.hhLbl}>MULTIPLIER</Text>
                    <TextInput style={s.hhInput} keyboardType="decimal-pad" defaultValue={String(hh.multiplier)}
                      onEndEditing={(e) => saveHh({ multiplier: Math.min(5, Math.max(1, parseFloat(e.nativeEvent.text || '2') || 2)) })}
                      testID="hh-mult" />
                  </View>
                </View>
              )}
            </View>

            {/* Incoming orders */}
            <Text style={s.section}>Incoming Orders</Text>
            {!orders.length && <Text style={s.empty} testID="merchant-orders-empty">No paid orders yet.</Text>}
            {orders.map((o) => (
              <View key={o.order_id} style={s.orderCard} testID={`merchant-order-${o.order_id}`}>
                <View style={s.orderHead}>
                  <Text style={s.orderCode}>#{o.pickup_code}</Text>
                  <Text style={s.orderStatus}>{o.status}</Text>
                </View>
                {(o.items || []).map((it: any, i: number) => (
                  <Text key={i} style={s.orderItem}>{it.qty}× {it.name}</Text>
                ))}
                <Text style={s.orderTotal}>{money(o.total_cents)} · rewards {o.points_to_award} BigPoints</Text>
                {NEXT[o.status] && (
                  <TouchableOpacity style={s.advBtn} onPress={() => advance(o)} testID={`merchant-advance-${o.order_id}`}>
                    <Text style={s.advText}>{NEXT_LABEL[o.status]}</Text>
                    <Ionicons name="arrow-forward" size={15} color="#fff" />
                  </TouchableOpacity>
                )}
                {o.status === 'picked_up' && (
                  <View style={s.doneRow}><Ionicons name="checkmark-circle" size={16} color={COLORS.green} />
                    <Text style={s.doneText}>Completed · {o.points_to_award} BigPoints awarded</Text></View>
                )}
              </View>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  notice: { alignItems: 'center', marginTop: 40, padding: SPACING.lg },
  noticeText: { color: COLORS.textDim, fontWeight: '700', marginTop: 10 },
  subBanner: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.md, padding: 14, marginBottom: SPACING.md },
  subBannerText: { color: '#fff', fontWeight: '900', fontSize: FONT.sm, flex: 1 },
  biz: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', marginBottom: SPACING.md },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: SPACING.md },
  stat: { flexGrow: 1, flexBasis: '46%', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 14 },
  statNum: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  statLbl: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  rowBtns: { flexDirection: 'row', gap: 10, marginBottom: SPACING.md },
  linkBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.md, paddingVertical: 12 },
  linkText: { color: COLORS.primary, fontWeight: '800', fontSize: FONT.sm },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  hhHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  cardHint: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 3 },
  hhRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  hhField: { flex: 1 },
  hhLbl: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 0.8, marginBottom: 4 },
  hhInput: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.sm, paddingHorizontal: 10, paddingVertical: 8, color: COLORS.text, fontWeight: '800', textAlign: 'center' },
  section: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 10, marginTop: 4 },
  empty: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: 12 },
  orderCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 14, marginBottom: 10 },
  orderHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  orderCode: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', letterSpacing: 2 },
  orderStatus: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900', textTransform: 'uppercase' },
  orderItem: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  orderTotal: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 6 },
  advBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, backgroundColor: COLORS.primary, borderRadius: RADIUS.md, paddingVertical: 11, marginTop: 10 },
  advText: { color: '#fff', fontWeight: '900', fontSize: FONT.sm },
  doneRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 },
  doneText: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '800' },
});
