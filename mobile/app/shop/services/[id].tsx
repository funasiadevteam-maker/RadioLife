// Consumer service booking — pick service, date & slot, pay reservation fee.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useReward } from '../../../src/components/RewardOverlay';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const dayLabel = (d: Date) => d.toLocaleDateString('en-US', { weekday: 'short', day: 'numeric' });
const iso = (d: Date) => d.toISOString().slice(0, 10);

export default function ServiceBooking() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { celebrate } = useReward();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<any>(null);
  const [dateIdx, setDateIdx] = useState(0);
  const [slots, setSlots] = useState<string[]>([]);
  const [slotLoading, setSlotLoading] = useState(false);
  const [booking, setBooking] = useState(false);

  const dates = Array.from({ length: 7 }, (_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return d; });

  useEffect(() => {
    api.get(`/shop/businesses/${id}/services`).then((r) => setData(r.data))
      .catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const loadSlots = useCallback(async (svc: any, di: number) => {
    if (!svc) return;
    setSlotLoading(true); setSlots([]);
    try {
      const r = await api.get(`/shop/businesses/${id}/services/${svc.service_id}/slots?date=${iso(dates[di])}`);
      setSlots(r.data.slots || []);
    } catch { setSlots([]); } finally { setSlotLoading(false); }
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectService = (svc: any) => { setSelected(svc); setDateIdx(0); loadSlots(svc, 0); };
  const selectDate = (di: number) => { setDateIdx(di); loadSlots(selected, di); };

  const book = async (startTime: string) => {
    setBooking(true);
    try {
      const r = await api.post('/shop/service-bookings/checkout', {
        business_id: id, service_id: selected.service_id, date: iso(dates[dateIdx]),
        start_time: startTime, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
      });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/shop/service-bookings/${r.data.booking_id}/status`);
        if (st.data.payment_status === 'paid') { celebrate({ points: 0, title: 'Booking confirmed! 🎉' }); router.replace('/shop/bookings'); return; }
      } else {
        celebrate({ points: 0, title: 'Booking confirmed! 🎉' }); router.replace('/shop/bookings'); return;
      }
    } catch { /* ignore */ } finally { setBooking(false); loadSlots(selected, dateIdx); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Services unavailable.</Text></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="svc-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle} numberOfLines={1}>{data.public_name}</Text>
        <TouchableOpacity onPress={() => router.push('/shop/bookings')} testID="svc-bookings">
          <Ionicons name="calendar-outline" size={20} color={COLORS.text} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }} testID="svc-root">
        <Text style={s.sectionTitle}>Choose a service</Text>
        {(data.services || []).map((svc: any) => (
          <TouchableOpacity key={svc.service_id} onPress={() => selectService(svc)}
            style={[s.svcCard, selected?.service_id === svc.service_id && s.svcCardOn]} testID={`svc-${svc.service_id}`}>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.svcName}>{svc.name}</Text>
              {!!svc.description && <Text style={s.svcDesc} numberOfLines={2}>{svc.description}</Text>}
              <Text style={s.svcMeta}>{svc.duration_min} min · {money(svc.price_cents)}
                {svc.reservation_fee_cents > 0 ? ` · ${money(svc.reservation_fee_cents)} reservation` : ''}</Text>
            </View>
            <Ionicons name={selected?.service_id === svc.service_id ? 'radio-button-on' : 'radio-button-off'} size={20} color={COLORS.primary} />
          </TouchableOpacity>
        ))}
        {(!data.services || !data.services.length) && <Text style={{ color: COLORS.textDim, marginTop: 12 }}>No services published yet.</Text>}

        {selected && (
          <>
            <Text style={s.sectionTitle}>Pick a day</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingRight: 12 }}>
              {dates.map((d, i) => (
                <TouchableOpacity key={i} onPress={() => selectDate(i)} style={[s.dateChip, dateIdx === i && s.dateChipOn]} testID={`svc-date-${i}`}>
                  <Text style={[s.dateChipText, dateIdx === i && { color: '#fff' }]}>{dayLabel(d)}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            <Text style={s.sectionTitle}>Available times</Text>
            {slotLoading ? <ActivityIndicator color={COLORS.primary} style={{ marginTop: 8 }} />
              : slots.length ? (
                <View style={s.slotGrid}>
                  {slots.map((t) => (
                    <TouchableOpacity key={t} onPress={() => book(t)} disabled={booking} style={s.slot} testID={`svc-slot-${t}`}>
                      <Text style={s.slotText}>{t}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              ) : <Text style={{ color: COLORS.textDim, marginTop: 8 }} testID="svc-no-slots">No open times that day.</Text>}
            {selected.reservation_fee_cents > 0 && (
              <Text style={s.feeNote}>You&apos;ll pay {money(selected.reservation_fee_cents)} now to reserve — credited toward your {money(selected.price_cents)} service.</Text>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  sectionTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginTop: SPACING.lg, marginBottom: 10 },
  svcCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 14, marginBottom: 8 },
  svcCardOn: { borderColor: COLORS.primary },
  svcName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  svcDesc: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  svcMeta: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800', marginTop: 4 },
  dateChip: { paddingHorizontal: 16, height: 44, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  dateChipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  dateChipText: { color: COLORS.text, fontWeight: '800', fontSize: FONT.sm },
  slotGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  slot: { paddingHorizontal: 16, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.primary + '12' },
  slotText: { color: COLORS.primary, fontWeight: '900', fontSize: FONT.sm },
  feeNote: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 14, lineHeight: 17 },
});
