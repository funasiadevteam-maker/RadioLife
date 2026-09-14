// Dining Club — mobile meal pass: restaurant reveal + single-use QR.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, Linking,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import QRCode from 'react-native-qrcode-svg';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

const money = (c?: number) => `$${(((c ?? 0)) / 100).toFixed(2)}`;

export default function DiningPass() {
  const router = useRouter();
  const { order_id, session_id } = useLocalSearchParams<{ order_id?: string; session_id?: string }>();
  const [data, setData] = useState<any>(null);
  const [status, setStatus] = useState<'loading' | 'pending' | 'ready' | 'error'>('loading');

  useEffect(() => {
    let stop = false, tries = 0;
    const run = async () => {
      try {
        if (session_id) {
          const r = await api.get(`/dining-club/checkout/status/${session_id}`);
          if (r.data.status === 'paid') { const p = await api.get(`/dining-club/pass/${r.data.order_id}`); if (!stop) { setData(p.data); setStatus('ready'); } return; }
          if (!stop && tries++ < 20) setTimeout(run, 2500); else if (!stop) setStatus('pending');
          return;
        }
        const p = await api.get(`/dining-club/pass/${order_id}`);
        if (!stop) {
          if (p.data?.order?.status === 'paid') { setData(p.data); setStatus('ready'); }
          else if (tries++ < 20) setTimeout(run, 2500); else setStatus('pending');
        }
      } catch { if (!stop) setStatus('error'); }
    };
    run();
    return () => { stop = true; };
  }, [order_id, session_id]);

  const r = data?.restaurant, meal = data?.meal, qr = data?.qr;

  return (
    <SafeAreaView style={s.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.replace('/dining')} testID="pass-back"><Ionicons name="chevron-back" size={24} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.headerTitle}>Your Meal Pass</Text><View style={{ width: 24 }} />
      </View>

      {status === 'loading' || status === 'pending' ? (
        <View style={s.center} testID="pass-pending">
          <ActivityIndicator color={COLORS.primary} size="large" />
          <Text style={s.dim}>{status === 'pending' ? 'Confirming your payment…' : 'Loading your pass…'}</Text>
        </View>
      ) : status === 'error' ? (
        <View style={s.center}><Text style={s.dim}>Couldn't load this pass.</Text></View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, alignItems: 'center', paddingBottom: 60 }} testID="pass-ready">
          <View style={s.confirm}><Ionicons name="checkmark-circle" size={16} color={COLORS.green} /><Text style={s.confirmText}>Meal confirmed</Text></View>
          <Text style={s.title} testID="pass-restaurant">{r?.name}</Text>
          <View style={s.qrCard}>
            <Text style={s.qrKicker}>SHOW THIS AT THE COUNTER</Text>
            {qr?.qr_token ? <QRCode value={qr.qr_token} size={196} /> : null}
            <Text style={s.mealLine}>{meal?.title || "Chef's selected meal"} · {money(data?.order?.amount_cents)}</Text>
          </View>
          <View style={s.info}>
            <Row icon="location" text={r?.address} />
            {r?.distance_miles != null && <Row icon="navigate" text={`${r.distance_miles} miles away`} />}
            {r?.hours && <Row icon="time" text={r.hours} />}
          </View>
          {r?.lat && r?.lng && (
            <TouchableOpacity style={s.ghost} onPress={() => Linking.openURL(`https://maps.google.com/?q=${r.lat},${r.lng}`)} testID="pass-directions">
              <Ionicons name="navigate" size={16} color={COLORS.textDim} /><Text style={s.ghostText}>Get directions</Text>
            </TouchableOpacity>
          )}
          <Text style={s.dim}>Single-use QR — valid until redeemed.</Text>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

function Row({ icon, text }: any) {
  if (!text) return null;
  return <View style={s.row}><Ionicons name={icon} size={16} color={COLORS.primary} /><Text style={s.rowText}>{text}</Text></View>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  headerTitle: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  dim: { color: COLORS.textMuted, fontSize: FONT.sm, marginTop: 8, textAlign: 'center' },
  confirm: { flexDirection: 'row', gap: 6, alignItems: 'center', marginBottom: 6 },
  confirmText: { color: COLORS.green, fontWeight: '700', fontSize: FONT.xs, letterSpacing: 1.5 },
  title: { fontSize: FONT.hero, fontWeight: '900', color: COLORS.text, textAlign: 'center', marginBottom: SPACING.md },
  qrCard: { backgroundColor: '#fff', borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.xl, padding: SPACING.lg, alignItems: 'center', width: '100%' },
  qrKicker: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5, marginBottom: SPACING.md },
  mealLine: { fontWeight: '900', color: COLORS.text, marginTop: SPACING.md, fontSize: FONT.md },
  info: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md, width: '100%', marginTop: SPACING.md },
  row: { flexDirection: 'row', gap: 10, alignItems: 'center', paddingVertical: 6 },
  rowText: { color: COLORS.text, fontSize: FONT.sm, flex: 1 },
  ghost: { flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', marginTop: SPACING.md, paddingVertical: 12 },
  ghostText: { color: COLORS.textDim, fontWeight: '600' },
});
