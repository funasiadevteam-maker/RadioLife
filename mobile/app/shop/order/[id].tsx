// Live Order Tracker — polling status, "getting ready" stepper + store map.
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useReward } from '../../../src/components/RewardOverlay';
import NativeMap, { MAPS_AVAILABLE } from '../../../src/components/NativeMap';
import { routeLine } from '../../../src/utils/geocode';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const STEPS = ['accepted', 'preparing', 'ready', 'picked_up'];
const STEP_LABELS = ['Accepted', 'Preparing', 'Ready', 'Picked up'];
const LABELS: Record<string, string> = {
  pending_payment: 'Awaiting Payment', accepted: 'Order accepted', preparing: 'Getting your order ready',
  ready: 'Ready — head over!', picked_up: 'Picked up · enjoy!', canceled: 'Canceled',
};

const fmtClock = (ms: number) => {
  const s = Math.max(0, Math.round(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`;
};

export default function OrderTracker() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { celebrate } = useReward();
  const [order, setOrder] = useState<any>(null);
  const [geo, setGeo] = useState<{ lat: number; lng: number; address?: string } | null>(null);
  const [route, setRoute] = useState<{ lat: number; lng: number }[] | null>(null);
  const [nowTs, setNowTs] = useState(Date.now());
  const [loading, setLoading] = useState(true);
  const prevStatus = useRef<string | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get(`/shop/orders/${id}/status`);
      const o = r.data.order;
      // Celebrate the moment it becomes ready.
      if (o.status === 'ready' && prevStatus.current && prevStatus.current !== 'ready') {
        celebrate({ points: 0, title: 'Your order is ready! 🎉' });
      }
      prevStatus.current = o.status;
      setOrder(o);
      if (!geo && o.business_id) {
        api.get(`/shop/businesses/${o.business_id}`)
          .then((b) => setGeo(b.data?.business?.geo || null)).catch(() => {});
      }
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }, [id, geo, celebrate]);

  useEffect(() => { load(); }, [load]);

  // Poll while the order is still active.
  useEffect(() => {
    if (!order || ['picked_up', 'canceled'].includes(order.status)) return;
    const t = setInterval(load, 12000);
    return () => clearInterval(t);
  }, [order, load]);

  // Live prep countdown — tick every second until ready.
  useEffect(() => {
    if (!order || ['ready', 'picked_up', 'canceled'].includes(order.status)) return;
    const t = setInterval(() => setNowTs(Date.now()), 1000);
    return () => clearInterval(t);
  }, [order?.status]);

  // Delivery route line (store → customer) once both points are known.
  const dest = order?.delivery_address;
  useEffect(() => {
    if (order?.fulfillment === 'delivery' && geo && dest?.lat && dest?.lng) {
      routeLine({ lat: geo.lat, lng: geo.lng }, { lat: dest.lat, lng: dest.lng })
        .then(setRoute).catch(() => {});
    }
  }, [order?.fulfillment, geo, dest?.lat, dest?.lng]);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!order) {
    return (
      <SafeAreaView style={common.screen}>
        <View style={common.center}><Text style={{ color: COLORS.textDim, fontWeight: '700' }}>Order not found.</Text></View>
      </SafeAreaView>
    );
  }

  const stepIdx = STEPS.indexOf(order.status);
  const isReady = order.status === 'ready';
  const isDelivery = order.fulfillment === 'delivery';

  // Live prep timer.
  const readyAt = order.ready_at ? Date.parse(order.ready_at) : null;
  const remainingMs = readyAt != null ? readyAt - nowTs : null;
  const showTimer = ['accepted', 'preparing'].includes(order.status) && remainingMs != null;

  // Map region — fit both store + destination for delivery.
  let region: any;
  const hasDest = isDelivery && dest?.lat != null && dest?.lng != null;
  if (geo && hasDest) {
    region = {
      latitude: (geo.lat + dest.lat) / 2,
      longitude: (geo.lng + dest.lng) / 2,
      latitudeDelta: Math.max(Math.abs(geo.lat - dest.lat) * 1.8, 0.02),
      longitudeDelta: Math.max(Math.abs(geo.lng - dest.lng) * 1.8, 0.02),
    };
  } else if (geo) {
    region = { latitude: geo.lat, longitude: geo.lng, latitudeDelta: 0.02, longitudeDelta: 0.02 };
  }
  const mapMarkers = geo ? [
    { id: 'store', lat: geo.lat, lng: geo.lng, title: order.business_name },
    ...(hasDest ? [{ id: 'dest', lat: dest.lat, lng: dest.lng, title: 'Delivery address' }] : []),
  ] : [];

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.replace('/shop/orders')} testID="tracker-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Order Tracker</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 80 }} testID="tracker-root">
        <View style={[s.statusBanner, isReady && s.statusBannerReady]} testID="tracker-status">
          <Ionicons name={isReady ? 'checkmark-circle' : 'time'} size={22} color={isReady ? COLORS.green : COLORS.primary} />
          <View style={{ flex: 1 }}>
            <Text style={s.statusTitle}>{LABELS[order.status] || order.status}</Text>
            {!!order.eta_label && order.status !== 'picked_up' && (
              <Text style={s.statusEta} testID="tracker-eta">{isDelivery ? `Arrives in ${order.eta_label}` : order.eta_label}</Text>
            )}
          </View>
        </View>

        {/* Live prep countdown */}
        {showTimer && (
          <View style={s.timerCard} testID="tracker-timer">
            <Ionicons name="timer-outline" size={18} color={COLORS.primary} />
            <Text style={s.timerText}>
              {remainingMs! > 0
                ? `${isDelivery ? 'Arriving' : 'Ready'} in ${fmtClock(remainingMs!)}`
                : `Almost ${isDelivery ? 'there' : 'ready'}…`}
            </Text>
          </View>
        )}
        {isReady && (
          <View style={s.nudgeCard} testID="tracker-ready-nudge">
            <Ionicons name="walk" size={18} color={COLORS.green} />
            <Text style={s.nudgeText}>{isDelivery ? 'On its way — get ready to receive it!' : 'Your order is ready — head over now!'}</Text>
          </View>
        )}

        {order.status !== 'canceled' && stepIdx >= 0 && (
          <View style={s.stepper}>
            {STEPS.map((st, idx) => (
              <React.Fragment key={st}>
                <View style={{ alignItems: 'center', width: 64 }}>
                  <View style={[s.dot, idx <= stepIdx && s.dotOn]}>
                    {idx <= stepIdx && <Ionicons name="checkmark" size={12} color="#fff" />}
                  </View>
                  <Text style={[s.stepLabel, idx <= stepIdx && s.stepLabelOn]}>{STEP_LABELS[idx]}</Text>
                </View>
                {idx < STEPS.length - 1 && <View style={[s.line, idx < stepIdx && s.lineOn]} />}
              </React.Fragment>
            ))}
          </View>
        )}

        {/* Store / route map (native builds) */}
        {MAPS_AVAILABLE && region ? (
          <View style={s.mapWrap} testID="tracker-map">
            <NativeMap region={region} interactive={false} markers={mapMarkers} polyline={route || undefined} />
          </View>
        ) : (
          <View style={s.mapFallback} testID="tracker-map-fallback">
            <Ionicons name="map-outline" size={18} color={COLORS.textMuted} />
            <Text style={s.mapFallbackText}>
              {isDelivery ? (dest?.label || 'Your delivery address') : (geo?.address || order.business_name)}{'  '}· live map in the app build
            </Text>
          </View>
        )}

        <View style={s.card}>
          <Text style={s.bizName}>{order.business_name}</Text>
          <Text style={s.meta}>{(order.items || []).reduce((n: number, i: any) => n + i.qty, 0)} items · {money(order.total_cents)}</Text>
          {order.service_fee_cents > 0 && <Text style={s.feeLine}>Service fee {money(order.service_fee_cents)}</Text>}
          {order.delivery_fee_cents > 0 && <Text style={s.feeLine}>Delivery fee {money(order.delivery_fee_cents)}</Text>}
          {order.tax_cents > 0 && <Text style={s.feeLine}>{order.tax_label || 'Tax'} {money(order.tax_cents)}</Text>}
          <View style={s.codeBox}>
            <Text style={s.codeLabel}>{isDelivery ? 'ORDER CODE' : 'PICKUP CODE'}</Text>
            <Text style={s.code} testID="tracker-code">{order.pickup_code}</Text>
          </View>
        </View>

        <TouchableOpacity style={s.ordersBtn} onPress={() => router.replace('/shop/orders')} testID="tracker-all-orders">
          <Text style={s.ordersBtnText}>View all orders</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  statusBanner: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.primary + '12', borderWidth: 1, borderColor: COLORS.primary + '33', borderRadius: RADIUS.lg, padding: 16 },
  statusBannerReady: { backgroundColor: COLORS.green + '18', borderColor: COLORS.green + '55' },
  statusTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  statusEta: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800', marginTop: 2 },
  timerCard: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.primary + '12', borderWidth: 1, borderColor: COLORS.primary + '33', borderRadius: RADIUS.md, paddingVertical: 12, paddingHorizontal: 14, marginTop: 12 },
  timerText: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  nudgeCard: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.green + '18', borderWidth: 1, borderColor: COLORS.green + '55', borderRadius: RADIUS.md, paddingVertical: 12, paddingHorizontal: 14, marginTop: 12 },
  nudgeText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  stepper: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'center', marginTop: 20 },
  dot: { width: 24, height: 24, borderRadius: 12, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  dotOn: { backgroundColor: COLORS.green, borderColor: COLORS.green },
  stepLabel: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', marginTop: 6, textAlign: 'center' },
  stepLabelOn: { color: COLORS.text },
  line: { height: 2, flex: 0, width: 20, backgroundColor: COLORS.cardBorder, marginTop: 11 },
  lineOn: { backgroundColor: COLORS.green },
  mapWrap: { height: 180, borderRadius: RADIUS.lg, overflow: 'hidden', marginTop: 18, backgroundColor: COLORS.inputBg },
  mapFallback: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, padding: 14, marginTop: 18 },
  mapFallbackText: { flex: 1, color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, marginTop: 18 },
  bizName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  meta: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', marginTop: 6 },
  feeLine: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  codeBox: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 10, marginTop: 12, alignSelf: 'flex-start' },
  codeLabel: { color: COLORS.textMuted, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  code: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900', letterSpacing: 4 },
  ordersBtn: { alignItems: 'center', paddingVertical: 14, marginTop: 16 },
  ordersBtnText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
});
