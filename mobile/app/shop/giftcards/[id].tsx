// RadioLife Shop — buy a venue gift card (points or card) — mobile.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput, Alert,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useReward } from '../../../src/components/RewardOverlay';

const money = (c: number) => `$${(c / 100).toFixed(0)}`;

export default function ShopGiftCards() {
  const router = useRouter();
  const { celebrate } = useReward();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [product, setProduct] = useState<any>(null);
  const [amount, setAmount] = useState<number | null>(null);
  const [method, setMethod] = useState<'card' | 'points'>('card');
  const [giftOpen, setGiftOpen] = useState(false);
  const [giftEmail, setGiftEmail] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const r = await api.get(`/shop/businesses/${id}/giftcards`);
      setData(r.data);
      const first = (r.data.items || [])[0];
      if (first) { setProduct(first); setAmount((first.denominations_cents || [])[0] || null); }
    } catch { /* ignore */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [id]);

  const ppd = data?.points_per_dollar || 100;
  const pointsCost = amount ? Math.round((amount / 100) * ppd) : 0;
  const canPoints = product?.allow_points && (data?.points_balance || 0) >= pointsCost;

  const buy = async () => {
    if (!product || !amount) return;
    if (giftOpen && !giftEmail.trim().includes('@')) { Alert.alert('Gift', "Enter a valid friend's email to gift."); return; }
    setBusy(true);
    try {
      const r = await api.post('/giftcards/purchase', {
        product_id: product.product_id, amount_cents: amount, method,
        gift_to_email: giftOpen ? giftEmail.trim() : null,
        message: giftOpen ? (message.trim() || null) : null,
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
      });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/giftcards/purchase/${r.data.session_id}/status`);
        if (st.data.status !== 'paid') { setBusy(false); return; }
      }
      celebrate({ title: giftOpen ? 'Gift card sent!' : 'Gift card purchased!', subtitle: giftOpen ? `Sent to ${giftEmail}` : 'Ready in your wallet' });
      router.replace(`/shop/${id}`);
    } catch (e: any) {
      Alert.alert('Purchase failed', e?.response?.data?.detail?.code || 'Try again');
      setBusy(false);
    }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Unavailable.</Text></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="gc-back"><Ionicons name="chevron-back" size={26} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.title} numberOfLines={1}>{data.public_name} Gift Cards</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="gc-root">
        {!data.items?.length && <Text style={{ color: COLORS.textDim, textAlign: 'center', marginTop: 40 }} testID="gc-empty">No gift cards available here yet.</Text>}
        {(data.items || []).map((p: any) => (
          <TouchableOpacity key={p.product_id} testID={`gc-product-${p.product_id}`}
            style={[s.card, product?.product_id === p.product_id && s.cardOn]}
            onPress={() => { setProduct(p); setAmount((p.denominations_cents || [])[0]); }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Ionicons name="gift" size={18} color={COLORS.primary} />
              <Text style={s.cardTitle}>{data.public_name} Gift Card</Text>
            </View>
            <View style={s.chips}>
              {(p.denominations_cents || []).map((d: number) => (
                <TouchableOpacity key={d} testID={`gc-denom-${p.product_id}-${d}`}
                  style={[s.chip, product?.product_id === p.product_id && amount === d && s.chipOn]}
                  onPress={() => { setProduct(p); setAmount(d); }}>
                  <Text style={[s.chipText, product?.product_id === p.product_id && amount === d && s.chipTextOn]}>{money(d)}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </TouchableOpacity>
        ))}

        {product && amount && (
          <View style={s.panel}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <TouchableOpacity testID="gc-method-card" disabled={!product.allow_card}
                style={[s.mBtn, method === 'card' && s.mBtnOn, !product.allow_card && { opacity: 0.4 }]} onPress={() => setMethod('card')}>
                <Ionicons name="card" size={16} color={method === 'card' ? '#fff' : COLORS.text} />
                <Text style={[s.mText, method === 'card' && s.mTextOn]}>Card</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="gc-method-points" disabled={!product.allow_points}
                style={[s.mBtn, method === 'points' && s.mBtnOn, !product.allow_points && { opacity: 0.4 }]} onPress={() => setMethod('points')}>
                <Ionicons name="server" size={16} color={method === 'points' ? '#fff' : COLORS.text} />
                <Text style={[s.mText, method === 'points' && s.mTextOn]}>{pointsCost} pts</Text>
              </TouchableOpacity>
            </View>
            {method === 'points' && !canPoints && <Text style={s.warn}>Not enough BigPoints (you have {data.points_balance}).</Text>}
            <TouchableOpacity style={s.giftToggle} onPress={() => setGiftOpen((v) => !v)} testID="gc-gift-toggle">
              <Ionicons name="gift" size={15} color={giftOpen ? COLORS.primary : COLORS.textMuted} />
              <Text style={[s.giftToggleText, { color: giftOpen ? COLORS.primary : COLORS.textMuted }]}>{giftOpen ? 'Gifting to a friend' : 'Gift this gift card'}</Text>
            </TouchableOpacity>
            {giftOpen && (
              <View style={{ gap: 12 }} testID="gc-gift-fields">
                <TextInput value={giftEmail} onChangeText={setGiftEmail} placeholder="Friend's email" placeholderTextColor={COLORS.textMuted}
                  autoCapitalize="none" keyboardType="email-address" style={s.input} testID="gc-gift-email" />
                <TextInput value={message} onChangeText={setMessage} maxLength={280} placeholder="Optional message" placeholderTextColor={COLORS.textMuted} style={s.input} testID="gc-message" />
              </View>
            )}
            <TouchableOpacity style={[common.btnPrimary, (busy || (method === 'points' && !canPoints)) && { opacity: 0.5 }]}
              disabled={busy || (method === 'points' && !canPoints)} onPress={buy} testID="gc-buy">
              <Ionicons name="gift" size={16} color="#fff" />
              <Text style={common.btnPrimaryText}>{giftOpen ? `Gift ${money(amount)} card` : `Buy ${money(amount)} gift card`}</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: SPACING.md, paddingTop: 10, paddingBottom: 8 },
  title: { color: COLORS.text, fontSize: 20, fontWeight: '900', flex: 1 },
  card: { backgroundColor: COLORS.card, borderWidth: 2, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 16, marginBottom: 12 },
  cardOn: { borderColor: COLORS.primary },
  cardTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  chip: { paddingHorizontal: 16, height: 36, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  chipOn: { backgroundColor: COLORS.primary },
  chipText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  chipTextOn: { color: '#fff' },
  panel: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: 16, gap: 12 },
  mBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg },
  mBtnOn: { backgroundColor: COLORS.primary },
  mText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  mTextOn: { color: '#fff' },
  warn: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '800' },
  giftToggle: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  giftToggleText: { fontSize: FONT.sm, fontWeight: '900' },
  input: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
});
