// FUUSIC Travel — mobile deal detail + BigPoints demo booking.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';

type Deal = {
  deal_id: string; title: string; deal_type: string; destination: string;
  price_cents: number; strike_cents?: number; bigpoints: number; image_url?: string;
  blurb?: string; duration?: string; rating?: number; tags?: string[];
};

const money = (c: number) => `$${Math.round((c || 0) / 100)}`;
const TYPE_LABEL: Record<string, string> = {
  flight: 'Flight', hotel: 'Hotel', package: 'Package', experience: 'Experience', cruise: 'Cruise',
};

export default function TravelDeal() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [deal, setDeal] = useState<Deal | null>(null);
  const [loading, setLoading] = useState(true);
  const [travelers, setTravelers] = useState(1);
  const [booking, setBooking] = useState(false);
  const [confirmed, setConfirmed] = useState<any>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    api.get(`/travel/deals/${id}`).then((r) => setDeal(r.data?.deal || null))
      .catch(() => setDeal(null)).finally(() => setLoading(false));
  }, [id]);

  const book = async () => {
    setBooking(true);
    try {
      const r = await api.post(`/travel/deals/${id}/book`, { travelers });
      setConfirmed(r.data);
    } catch { /* inline */ }
    finally { setBooking(false); }
  };

  if (loading) return <SafeAreaView style={common.screen}><View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View></SafeAreaView>;
  if (!deal) return (
    <SafeAreaView style={common.screen}>
      <View style={common.center} testID="travel-detail-missing">
        <Text style={{ color: COLORS.textDim, fontWeight: '700' }}>Deal not found.</Text>
        <TouchableOpacity onPress={() => router.replace('/shop/travel' as any)} style={{ marginTop: 12 }}>
          <Text style={{ color: COLORS.primary, fontWeight: '900' }}>Back to Travel</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );

  const total = (deal.price_cents || 0) * travelers;

  return (
    <SafeAreaView style={common.screen} testID="travel-detail-root">
      <ScrollView contentContainerStyle={{ paddingBottom: 120 }}>
        <View style={s.hero}>
          <Image source={{ uri: deal.image_url }} style={s.heroImg} contentFit="cover" transition={150} />
          <TouchableOpacity onPress={() => router.back()} testID="travel-detail-back" style={s.backBtn}>
            <Ionicons name="chevron-back" size={22} color="#fff" />
          </TouchableOpacity>
          <View style={s.typeTag}><Text style={s.typeTagTxt}>{TYPE_LABEL[deal.deal_type] || 'Travel'}</Text></View>
        </View>

        <View style={{ padding: SPACING.md, gap: 12 }}>
          <View>
            <Text style={s.title}>{deal.title}</Text>
            <View style={s.metaRow}>
              <View style={s.metaItem}><Ionicons name="location-outline" size={14} color={COLORS.textMuted} /><Text style={s.metaTxt}>{deal.destination}</Text></View>
              {deal.duration ? <View style={s.metaItem}><Ionicons name="time-outline" size={14} color={COLORS.textMuted} /><Text style={s.metaTxt}>{deal.duration}</Text></View> : null}
              {deal.rating ? <View style={s.metaItem}><Ionicons name="star" size={13} color={COLORS.gold} /><Text style={[s.metaTxt, { color: COLORS.text, fontWeight: '800' }]}>{deal.rating.toFixed(1)}</Text></View> : null}
            </View>
          </View>

          {deal.blurb ? <Text style={s.blurb}>{deal.blurb}</Text> : null}

          {deal.tags && deal.tags.length > 0 ? (
            <View style={s.tags}>
              {deal.tags.map((tg) => <View key={tg} style={s.tag}><Text style={s.tagTxt}>{tg}</Text></View>)}
            </View>
          ) : null}

          <View style={s.ptsRow}>
            <Text style={s.ptsGlyph}>₿</Text>
            <Text style={s.ptsRowTxt}>Earn <Text style={{ fontWeight: '900' }}>+{deal.bigpoints}</Text> BigPoints on this booking</Text>
          </View>

          {confirmed ? (
            <View style={s.confirm} testID="travel-booking-confirmed">
              <View style={s.confirmIcon}><Ionicons name="checkmark" size={28} color={COLORS.primary} /></View>
              <Text style={s.confirmTitle}>Booking confirmed!</Text>
              <Text style={s.confirmSub}>Confirmation <Text style={{ color: COLORS.text, fontWeight: '900' }}>{confirmed.confirmation}</Text></Text>
              <Text style={s.confirmHint}>Total {money(confirmed.total_cents)} · demo BigPoints checkout</Text>
              <TouchableOpacity onPress={() => router.replace('/shop/travel' as any)} testID="travel-booking-done" style={s.bookBtn}>
                <Text style={s.bookBtnTxt}>Explore more deals</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              <View style={s.travRow}>
                <Text style={s.travLabel}>Travelers</Text>
                <View style={s.stepper}>
                  <TouchableOpacity onPress={() => setTravelers((n) => Math.max(1, n - 1))} testID="travel-travelers-dec" style={s.stepBtn}><Ionicons name="remove" size={18} color={COLORS.text} /></TouchableOpacity>
                  <Text style={s.travCount} testID="travel-travelers">{travelers}</Text>
                  <TouchableOpacity onPress={() => setTravelers((n) => Math.min(9, n + 1))} testID="travel-travelers-inc" style={s.stepBtn}><Ionicons name="add" size={18} color={COLORS.text} /></TouchableOpacity>
                </View>
              </View>
              <View style={s.bar}>
                <View style={{ flex: 1 }}>
                  <Text style={s.barLabel}>Total</Text>
                  <Text style={s.barTotal}>{money(total)}</Text>
                </View>
                <TouchableOpacity onPress={book} disabled={booking} testID="travel-book-btn" style={[s.bookBtn, { paddingHorizontal: 24 }]}>
                  <Text style={s.bookBtnTxt}>{booking ? 'Booking…' : 'Book with BigPoints'}</Text>
                </TouchableOpacity>
              </View>
            </>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  hero: { height: 240, backgroundColor: COLORS.inputBg },
  heroImg: { width: '100%', height: '100%' },
  backBtn: { position: 'absolute', top: 14, left: 14, width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(0,0,0,0.55)', alignItems: 'center', justifyContent: 'center' },
  typeTag: { position: 'absolute', bottom: 14, left: 14, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 5 },
  typeTagTxt: { color: '#fff', fontSize: FONT.xs, fontWeight: '900' },
  title: { color: COLORS.text, fontSize: 22, fontWeight: '900' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 4, flexWrap: 'wrap' },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  metaTxt: { color: COLORS.textMuted, fontSize: FONT.sm },
  blurb: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 21 },
  tags: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tag: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 5 },
  tagTxt: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', textTransform: 'capitalize' },
  ptsRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary + '15', borderRadius: RADIUS.lg, padding: 14 },
  ptsGlyph: { color: COLORS.primary, fontSize: 18, fontWeight: '900' },
  ptsRowTxt: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  travRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 14 },
  travLabel: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  stepBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  travCount: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', width: 24, textAlign: 'center' },
  bar: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 14 },
  barLabel: { color: COLORS.textMuted, fontSize: FONT.xs },
  barTotal: { color: COLORS.text, fontSize: 20, fontWeight: '900' },
  bookBtn: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 13, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  bookBtnTxt: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  confirm: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 20, alignItems: 'center' },
  confirmIcon: { width: 56, height: 56, borderRadius: 28, backgroundColor: COLORS.primary + '20', alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  confirmTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  confirmSub: { color: COLORS.textMuted, fontSize: FONT.sm, marginTop: 4 },
  confirmHint: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 2 },
});
