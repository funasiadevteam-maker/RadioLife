import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput, ActivityIndicator, Switch,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as WebBrowser from 'expo-web-browser';
import { TSPACE, TRADIUS, TFONT } from '../../../../src/constants/tube';
import api from '../../../../src/api/client';
import { AvatarM } from '../../../(tabs)/social';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', line: 'rgba(168,85,247,0.18)',
  text: '#F5F3FF', dim: '#a5a0c0', muted: '#6d6a86', violet: '#a855f7',
  magenta: '#c026d3', accent2: '#7c3aed', gold: '#fbbf24', green: '#34d399',
};

export default function AdvisorDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [a, setA] = useState<any>(null);
  const [question, setQuestion] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/social/dreams/advisors/${id}`); setA(data); }
    catch (_) { router.back(); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const book = async (svc: any) => {
    if (a.disclaimer && !accepted) { setNote('Please accept the advisor terms first.'); return; }
    setBusy(true); setNote('');
    try {
      const { data } = await api.post('/social/dreams/bookings/checkout', {
        advisor_id: id, service_id: svc.service_id, question: question.trim() || undefined,
        origin_url: 'https://radiolife.app',
      });
      if (data.checkout_url) { await WebBrowser.openBrowserAsync(data.checkout_url); setNote('Complete payment, then open My Readings.'); }
      else setNote('Booked! See it under My Readings.');
    } catch (e: any) { setNote(e?.response?.data?.detail?.code || "Couldn't book"); } finally { setBusy(false); }
  };

  if (!a) return <View style={[s.screen, s.center]}><ActivityIndicator color={D.violet} /></View>;
  const b = a.badges || {};
  return (
    <View style={s.screen} testID="advisor-detail">
      <View style={[s.topbar, { paddingTop: insets.top + 6 }]}>
        <Pressable onPress={() => router.back()} testID="advisor-back" hitSlop={10}><Ionicons name="chevron-back" size={24} color={D.text} /></Pressable>
        <Text style={s.topbarTitle}>Advisor</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 60, gap: 14 }} showsVerticalScrollIndicator={false}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <AvatarM name={a.display_name} url={a.photo_url} size={56} />
          <View style={{ flex: 1 }}>
            <Text style={s.name}>{a.display_name}</Text>
            <Text style={{ color: D.violet, fontSize: TFONT.xs }}>{a.category_label}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 }}>
              <Ionicons name="star" size={12} color={D.gold} /><Text style={s.dim}>{a.rating} · {a.review_count} reviews</Text></View>
          </View>
        </View>
        <View style={s.wrapRow}>
          {b.professional_license_verified ? <Badge icon="medkit" color={D.green} label="Licensed" /> : null}
          {b.spiritual_approved ? <Badge icon="sparkles" color={D.violet} label="Spiritual Approved" /> : null}
          {b.identity_verified ? <Badge icon="checkmark-circle" color="#22d3ee" label="Identity Verified" /> : null}
        </View>
        <Text style={s.body}>{a.bio}</Text>

        <Text style={s.sectionTitle}>PRIVATE READINGS</Text>
        {a.disclaimer ? (
          <View style={s.termsRow} testID="advisor-terms">
            <Switch value={accepted} onValueChange={setAccepted} testID="advisor-terms-check" trackColor={{ true: D.violet }} />
            <Text style={s.termsTxt}>{a.disclaimer} I understand.</Text>
          </View>
        ) : null}
        <TextInput value={question} onChangeText={setQuestion} testID="advisor-question-input" placeholder="Optional — what to focus on?" placeholderTextColor={D.muted} style={s.input} />
        {(a.services || []).length === 0 ? <Text style={s.dim}>No paid readings listed yet.</Text>
          : a.services.map((svc: any) => (
            <View key={svc.service_id} style={s.svc} testID={`advisor-service-${svc.service_id}`}>
              <View style={{ flex: 1 }}>
                <Text style={s.svcTitle}>{svc.title}</Text>
                <Text style={s.dim}>{svc.duration_min}m · {svc.delivery.replace('_', ' ')}{svc.delivery_hours ? ` · in ${svc.delivery_hours}h` : ''}</Text>
              </View>
              <Pressable onPress={() => book(svc)} disabled={busy} testID={`advisor-book-${svc.service_id}`} style={s.bookBtn}>
                {busy ? <ActivityIndicator color="#fff" size="small" /> : <Text style={s.bookBtnTxt}>{svc.price_cents > 0 ? `$${(svc.price_cents / 100).toFixed(0)}` : 'Free'}</Text>}</Pressable>
            </View>
          ))}
        {note ? <Text style={s.note}>{note}</Text> : null}

        {(a.reviews || []).length > 0 && <>
          <Text style={s.sectionTitle}>REVIEWS</Text>
          {a.reviews.map((r: any, i: number) => (
            <View key={i} style={s.review}>
              <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                <Text style={s.reviewWho}>{r.user_name}</Text>
                <View style={{ flexDirection: 'row', marginLeft: 'auto' }}>{Array.from({ length: r.rating }).map((_, j) => <Ionicons key={j} name="star" size={12} color={D.gold} />)}</View>
              </View>
              {r.comment ? <Text style={s.dim}>{r.comment}</Text> : null}
            </View>
          ))}
        </>}
      </ScrollView>
    </View>
  );
}

function Badge({ icon, color, label }: any) {
  return <View style={[s.badge, { backgroundColor: `${color}22` }]}><Ionicons name={icon} size={11} color={color} /><Text style={[s.badgeTxt, { color }]}>{label}</Text></View>;
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: D.bg },
  center: { alignItems: 'center', justifyContent: 'center' },
  topbar: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: TSPACE.md, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: D.line },
  topbarTitle: { color: D.text, fontSize: TFONT.lg, fontWeight: '900' },
  name: { color: D.text, fontSize: TFONT.lg, fontWeight: '900' },
  dim: { color: D.dim, fontSize: TFONT.xs },
  body: { color: D.text, fontSize: TFONT.sm, lineHeight: 21 },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  badge: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  badgeTxt: { fontSize: 10, fontWeight: '900' },
  sectionTitle: { color: D.muted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginTop: 4 },
  termsRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  termsTxt: { color: D.dim, fontSize: TFONT.xs, flex: 1, lineHeight: 17 },
  input: { backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: D.line, borderRadius: TRADIUS.md, paddingHorizontal: 14, paddingVertical: 12, color: D.text, fontSize: TFONT.sm },
  svc: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: D.elevated, borderWidth: 1, borderColor: D.line, borderRadius: TRADIUS.md, padding: 12 },
  svcTitle: { color: D.text, fontSize: TFONT.sm, fontWeight: '800' },
  bookBtn: { minWidth: 64, height: 42, paddingHorizontal: 14, borderRadius: 21, backgroundColor: D.magenta, alignItems: 'center', justifyContent: 'center' },
  bookBtnTxt: { color: '#fff', fontSize: TFONT.md, fontWeight: '900' },
  note: { color: D.violet, fontSize: TFONT.xs },
  review: { backgroundColor: D.elevated, borderWidth: 1, borderColor: D.line, borderRadius: TRADIUS.md, padding: 12 },
  reviewWho: { color: D.text, fontSize: TFONT.xs, fontWeight: '800' },
});
