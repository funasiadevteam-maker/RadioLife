// FUUSIC Shop — buy tickets to venue events (mobile).
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Alert,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useReward } from '../../../src/components/RewardOverlay';

const money = (c: number) => (c === 0 ? 'Free' : `$${(c / 100).toFixed(2)}`);
const fmt = (s: string) => { try { return new Date(s).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }); } catch { return s; } };

export default function ShopEvents() {
  const router = useRouter();
  const { celebrate } = useReward();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [qty, setQty] = useState<Record<string, number>>({});

  const load = async () => {
    try { const r = await api.get(`/shop/businesses/${id}/events`); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]);

  const q = (eid: string) => qty[eid] || 1;
  const setQ = (eid: string, v: number) => setQty((m) => ({ ...m, [eid]: Math.max(1, v) }));

  const buy = async (ev: any, method: string) => {
    setBusy(true);
    try {
      const r = await api.post('/shop/events/purchase', { event_id: ev.event_id, qty: q(ev.event_id), method, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/shop/events/purchase/${r.data.session_id}/status`);
        if (st.data.status !== 'paid') { setBusy(false); return; }
      }
      celebrate({ title: 'Tickets booked!', subtitle: `${ev.title}` });
      load(); setBusy(false);
    } catch (e: any) { Alert.alert('Purchase failed', e?.response?.data?.detail?.code || 'Try again'); setBusy(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Unavailable.</Text></View>;
  const ppd = data.points_per_dollar || 100;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="evt-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title} numberOfLines={1}>{data.public_name} Events</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="evt-root">
        {data.mine?.length > 0 && (
          <View style={s.mine} testID="evt-mine">
            <Text style={s.mineTitle}>Your tickets</Text>
            {data.mine.map((t: any) => (
              <View key={t.ticket_id} style={s.mineCard} testID={`evt-ticket-${t.ticket_id}`}>
                <Text style={s.mineName}>{t.event_title} · {t.qty}×</Text>
                <Text style={s.mineCode}>{t.code}</Text>
              </View>
            ))}
          </View>
        )}

        {!data.items?.length && !data.mine?.length && <Text style={{ color: COLORS.textDim, textAlign: 'center', marginTop: 40 }} testID="evt-empty">No upcoming events here yet.</Text>}

        {(data.items || []).map((ev: any) => {
          const pointsCost = Math.round((ev.price_cents / 100) * ppd) * q(ev.event_id);
          const canPoints = ev.allow_points && (ev.price_cents === 0 || data.points_balance >= pointsCost);
          return (
            <View key={ev.event_id} style={s.card} testID={`evt-${ev.event_id}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={s.evtTitle}>{ev.title}</Text>
                <Text style={s.evtPrice}>{money(ev.price_cents)}</Text>
              </View>
              <View style={s.metaRow}><Ionicons name="calendar" size={13} color={COLORS.textMuted} /><Text style={s.meta}>{fmt(ev.starts_at)}</Text></View>
              {!!ev.location && <View style={s.metaRow}><Ionicons name="location" size={13} color={COLORS.textMuted} /><Text style={s.meta}>{ev.location}</Text></View>}
              {!!ev.description && <Text style={s.desc}>{ev.description}</Text>}
              <Text style={[s.cap, ev.sold_out ? { color: COLORS.red } : { color: COLORS.green }]} testID={`evt-remaining-${ev.event_id}`}>
                {ev.sold_out ? 'SOLD OUT' : `${ev.remaining} tickets left`}
              </Text>
              {!ev.sold_out && (
                <>
                  <View style={s.qtyRow}>
                    <TouchableOpacity style={s.qtyBtn} onPress={() => setQ(ev.event_id, q(ev.event_id) - 1)} testID={`evt-qty-minus-${ev.event_id}`}><Ionicons name="remove" size={16} color={COLORS.text} /></TouchableOpacity>
                    <Text style={s.qtyVal} testID={`evt-qty-${ev.event_id}`}>{q(ev.event_id)}</Text>
                    <TouchableOpacity style={s.qtyBtn} onPress={() => setQ(ev.event_id, Math.min(ev.remaining, q(ev.event_id) + 1))} testID={`evt-qty-plus-${ev.event_id}`}><Ionicons name="add" size={16} color={COLORS.text} /></TouchableOpacity>
                  </View>
                  <View style={{ flexDirection: 'row', gap: 8, marginTop: 12 }}>
                    {ev.allow_card && ev.price_cents > 0 && (
                      <TouchableOpacity style={[s.buyCard, busy && { opacity: 0.5 }]} disabled={busy} onPress={() => buy(ev, 'card')} testID={`evt-buy-card-${ev.event_id}`}>
                        <Ionicons name="card" size={15} color="#fff" /><Text style={s.buyCardText}>Buy</Text>
                      </TouchableOpacity>
                    )}
                    {(ev.allow_points || ev.price_cents === 0) && (
                      <TouchableOpacity style={[s.buyPts, (busy || !canPoints) && { opacity: 0.4 }]} disabled={busy || !canPoints} onPress={() => buy(ev, 'points')} testID={`evt-buy-points-${ev.event_id}`}>
                        <Ionicons name="server" size={15} color={COLORS.text} /><Text style={s.buyPtsText}>{ev.price_cents === 0 ? 'Free ticket' : `${pointsCost} pts`}</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                </>
              )}
            </View>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 8 },
  title: { color: COLORS.text, fontSize: 20, fontWeight: '900', flex: 1 },
  mine: { borderWidth: 2, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10', borderRadius: RADIUS.lg, padding: 14, marginBottom: 16 },
  mineTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 8 },
  mineCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: 12, marginBottom: 8, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  mineName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  mineCode: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 16, marginBottom: 12 },
  evtTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', flex: 1 },
  evtPrice: { color: COLORS.primary, fontSize: FONT.md, fontWeight: '900' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  meta: { color: COLORS.textMuted, fontSize: FONT.xs },
  desc: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 6 },
  cap: { fontSize: FONT.xs, fontWeight: '900', marginTop: 8 },
  qtyRow: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 12 },
  qtyBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  qtyVal: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', width: 24, textAlign: 'center' },
  buyCard: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 11 },
  buyCardText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  buyPts: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, paddingVertical: 11 },
  buyPtsText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
});
