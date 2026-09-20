// FUUSIC Shop — venue memberships: subscribe + claim benefits (mobile).
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, Alert, TextInput,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useReward } from '../../../src/components/RewardOverlay';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const periodLabel = (p: string) => (p === 'day' ? '/ day' : p === 'week' ? '/ week' : '/ month');

export default function ShopMemberships() {
  const router = useRouter();
  const { celebrate } = useReward();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [pick, setPick] = useState<Record<string, string>>({});
  const [giftOpen, setGiftOpen] = useState<Record<string, boolean>>({});
  const [giftEmail, setGiftEmail] = useState<Record<string, string>>({});
  const [giftMsg, setGiftMsg] = useState<Record<string, string>>({});

  const load = async () => {
    try { const r = await api.get(`/shop/businesses/${id}/memberships`); setData(r.data); }
    catch { setData(null); } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]);

  const subscribe = async (planId: string, gift?: { email: string; message: string } | null) => {
    if (gift && !(gift.email || '').includes('@')) { Alert.alert('Gift', "Enter a valid friend's email to gift."); return; }
    setBusy(true);
    try {
      const body: any = { plan_id: planId, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL };
      if (gift?.email) { body.gift_to_email = gift.email.trim(); body.message = gift.message || ''; }
      const r = await api.post('/shop/memberships/subscribe', body);
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/shop/memberships/subscribe/${r.data.session_id}/status`);
        if (st.data.status !== 'active') { setBusy(false); return; }
      }
      celebrate({ title: gift?.email ? 'Membership gifted!' : 'Welcome, member!',
                  subtitle: gift?.email ? `Sent to ${gift.email}` : 'Your benefits are ready' });
      load(); setBusy(false);
    } catch (e: any) { Alert.alert('Subscription failed', e?.response?.data?.detail?.code || 'Try again'); setBusy(false); }
  };

  const claim = async (b: any) => {
    const eid = b.entitlement_id || b.benefit_id;
    const option = b.options?.length ? pick[eid] : null;
    if (b.options?.length && !option) { Alert.alert('Choose an option first'); return; }
    try {
      await api.post(`/shop/memberships/${data.mine.membership_id}/claim`, { entitlement_id: eid, option });
      celebrate({ title: 'Claimed!', subtitle: b.label + (option ? ` · ${option}` : '') });
      load();
    } catch (e: any) { Alert.alert('Claim failed', e?.response?.data?.detail?.code || 'Try again'); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Unavailable.</Text></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="mem-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title} numberOfLines={1}>{data.public_name} Memberships</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="mem-root">
        {data.mine && (
          <View style={s.mine} testID="mem-mine">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="ribbon" size={18} color={COLORS.gold} />
              <Text style={s.mineTitle}>You&apos;re a {data.mine.plan_name} member</Text>
            </View>
            {(data.mine.benefits || []).map((b: any) => {
              const eid = b.entitlement_id || b.benefit_id;
              return (
              <View key={eid} style={s.benefit} testID={`mem-benefit-${eid}`}>
                <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                  <Text style={s.benefitLabel}>{b.label}</Text>
                  <Text style={s.benefitMeta}>{b.remaining}/{b.qty} left {periodLabel(b.period)}</Text>
                </View>
                {b.options?.length > 0 && (
                  <View style={s.chips}>
                    {b.options.map((o: string) => (
                      <TouchableOpacity key={o} testID={`mem-option-${eid}-${o}`}
                        style={[s.chip, pick[eid] === o && s.chipOn]}
                        onPress={() => setPick((m) => ({ ...m, [eid]: o }))}>
                        <Text style={[s.chipText, pick[eid] === o && s.chipTextOn]}>{o}</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
                <TouchableOpacity style={[s.claimBtn, b.remaining <= 0 && { opacity: 0.4 }]} disabled={b.remaining <= 0}
                  onPress={() => claim(b)} testID={`mem-claim-${eid}`}>
                  <Text style={s.claimText}>{b.remaining <= 0 ? 'Claimed for this period' : 'Claim now'}</Text>
                </TouchableOpacity>
              </View>
              );
            })}
          </View>
        )}

        {!data.items?.length && !data.mine && <Text style={{ color: COLORS.textDim, textAlign: 'center', marginTop: 40 }} testID="mem-empty">No memberships offered here yet.</Text>}

        {(data.items || []).map((p: any) => {
          const isMine = data.mine && data.mine.plan_id === p.plan_id;
          const isGift = !!giftOpen[p.plan_id];
          const gift = isGift ? { email: giftEmail[p.plan_id] || '', message: giftMsg[p.plan_id] || '' } : null;
          return (
            <View key={p.plan_id} style={s.card} testID={`mem-plan-${p.plan_id}`}>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Text style={s.planName}>{p.name}</Text>
                <Text style={s.planPrice}>{money(p.price_cents)}<Text style={s.planPer}>{periodLabel(p.interval)}</Text></Text>
              </View>
              {!!p.description && <Text style={s.planDesc}>{p.description}</Text>}
              <View style={{ marginTop: 8, gap: 4 }}>
                {(p.entitlements || []).map((e: any) => (
                  <View key={e.entitlement_id || e.benefit_id} style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                    <Ionicons name="checkmark-circle" size={14} color={COLORS.green} />
                    <Text style={s.entText}>{e.qty}× {e.label}{e.options?.length ? ` (choose)` : ''} {periodLabel(e.period)}</Text>
                  </View>
                ))}
              </View>

              <TouchableOpacity style={s.giftToggle} onPress={() => setGiftOpen((st) => ({ ...st, [p.plan_id]: !st[p.plan_id] }))}
                testID={`mem-gift-toggle-${p.plan_id}`}>
                <Ionicons name="gift" size={15} color={isGift ? COLORS.primary : COLORS.textMuted} />
                <Text style={[s.giftToggleText, { color: isGift ? COLORS.primary : COLORS.textMuted }]}>{isGift ? 'Gifting to a friend' : 'Gift this membership'}</Text>
              </TouchableOpacity>
              {isGift && (
                <View style={{ marginTop: 8, gap: 8 }} testID={`mem-gift-fields-${p.plan_id}`}>
                  <TextInput style={s.giftInput} placeholder="Friend's email" placeholderTextColor={COLORS.textMuted}
                    autoCapitalize="none" keyboardType="email-address" value={giftEmail[p.plan_id] || ''}
                    onChangeText={(v) => setGiftEmail((st) => ({ ...st, [p.plan_id]: v }))} testID={`mem-gift-email-${p.plan_id}`} />
                  <TextInput style={s.giftInput} placeholder="Optional message" placeholderTextColor={COLORS.textMuted}
                    maxLength={280} value={giftMsg[p.plan_id] || ''}
                    onChangeText={(v) => setGiftMsg((st) => ({ ...st, [p.plan_id]: v }))} testID={`mem-gift-message-${p.plan_id}`} />
                </View>
              )}

              <TouchableOpacity style={[common.btnPrimary, { marginTop: 12 }, (busy || (isMine && !isGift)) && { opacity: 0.5 }]}
                disabled={busy || (isMine && !isGift)} onPress={() => subscribe(p.plan_id, gift)} testID={`mem-subscribe-${p.plan_id}`}>
                <Ionicons name={isGift ? 'gift' : 'star'} size={16} color="#fff" />
                <Text style={common.btnPrimaryText}>{isGift ? `Gift · ${money(p.price_cents)}${periodLabel(p.interval)}` : isMine ? 'Active member' : `Join · ${money(p.price_cents)}${periodLabel(p.interval)}`}</Text>
              </TouchableOpacity>
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
  mine: { borderWidth: 2, borderColor: COLORS.gold, backgroundColor: COLORS.gold + '14', borderRadius: RADIUS.lg, padding: 14, marginBottom: 16, gap: 10 },
  mineTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  benefit: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: 12 },
  benefitLabel: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  benefitMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8 },
  chip: { paddingHorizontal: 12, height: 32, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  chipOn: { backgroundColor: COLORS.primary },
  chipText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '900' },
  chipTextOn: { color: '#fff' },
  claimBtn: { marginTop: 10, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 9, alignItems: 'center' },
  claimText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 16, marginBottom: 12 },
  planName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  planPrice: { color: COLORS.primary, fontSize: FONT.md, fontWeight: '900' },
  planPer: { color: COLORS.textMuted, fontSize: FONT.xs },
  planDesc: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 4 },
  giftToggle: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12 },
  giftToggleText: { fontSize: FONT.sm, fontWeight: '900' },
  giftInput: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  entText: { color: COLORS.textDim, fontSize: FONT.sm },
});
