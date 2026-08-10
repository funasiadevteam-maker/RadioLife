// Consumer ecommerce — browse products, variants, cart & delivery checkout.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import * as WebBrowser from 'expo-web-browser';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useReward } from '../../../src/components/RewardOverlay';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const absUrl = (u?: string | null) => (!u ? null : u.startsWith('http') ? u : `${process.env.EXPO_PUBLIC_BACKEND_URL}${u}`);
const keyOf = (pid: string, v?: string | null) => (v ? `${pid}::${v}` : pid);

export default function Products() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { celebrate } = useReward();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [cart, setCart] = useState<Record<string, { product: any; variant: any; qty: number }>>({});
  const [fulfillment, setFulfillment] = useState('pickup');
  const [address, setAddress] = useState('');
  const [busy, setBusy] = useState(false);
  const [variantPick, setVariantPick] = useState<Record<string, string>>({});

  useEffect(() => {
    api.get(`/shop/businesses/${id}/products`).then((r) => {
      setData(r.data);
      setFulfillment(r.data.delivery?.pickup ? 'pickup' : (r.data.delivery?.delivery ? 'delivery' : 'pickup'));
    }).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const priceOf = (p: any, v: any) => (v && v.price_cents > 0 ? v.price_cents : p.price_cents);
  const add = (p: any) => {
    const v = p.variants?.length ? p.variants.find((x: any) => x.label === variantPick[p.product_id]) : null;
    if (p.variants?.length && !v) return;
    const k = keyOf(p.product_id, v?.label);
    setCart((c) => ({ ...c, [k]: { product: p, variant: v, qty: (c[k]?.qty || 0) + 1 } }));
  };
  const dec = (k: string) => setCart((c) => {
    const q = (c[k]?.qty || 0) - 1; const n = { ...c };
    if (q <= 0) delete n[k]; else n[k] = { ...c[k], qty: q };
    return n;
  });

  const entries = Object.entries(cart);
  const subtotal = entries.reduce((s, [, it]) => s + priceOf(it.product, it.variant) * it.qty, 0);
  const dcfg = data?.delivery || {};
  const deliveryFee = fulfillment === 'delivery'
    ? (dcfg.free_over_cents > 0 && subtotal >= dcfg.free_over_cents ? 0 : (dcfg.fee_cents || 0)) : 0;

  const checkout = async () => {
    if (!entries.length) return;
    if (fulfillment === 'delivery' && !address.trim()) return;
    setBusy(true);
    try {
      const r = await api.post('/shop/product-orders/checkout', {
        business_id: id,
        items: entries.map(([, it]) => ({ product_id: it.product.product_id, variant_label: it.variant?.label || null, qty: it.qty })),
        fulfillment, address: fulfillment === 'delivery' ? address.trim() : null,
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL, use_gift_card: true,
      });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/shop/product-orders/${r.data.order_id}/status`);
        if (st.data.payment_status === 'paid') { celebrate({ points: 0, title: 'Order placed! 🎉' }); router.replace('/shop/product-orders'); return; }
      } else { celebrate({ points: 0, title: 'Order placed! 🎉' }); router.replace('/shop/product-orders'); return; }
    } catch { /* ignore */ } finally { setBusy(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Shop unavailable.</Text></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="prod-back" style={{ padding: 2 }}><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle} numberOfLines={1}>{data.public_name}</Text>
        <TouchableOpacity onPress={() => router.push('/shop/product-orders')} testID="prod-orders"><Ionicons name="cube-outline" size={20} color={COLORS.text} /></TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 220 }} testID="prod-root">
        {(data.products || []).map((p: any) => {
          const v = p.variants?.length ? p.variants.find((x: any) => x.label === variantPick[p.product_id]) : null;
          const soldOut = p.variants?.length ? p.variants.every((x: any) => x.stock <= 0) : p.stock <= 0;
          return (
            <View key={p.product_id} style={s.card} testID={`prod-${p.product_id}`}>
              {absUrl(p.image_url) && <Image source={{ uri: absUrl(p.image_url)! }} style={s.img} contentFit="cover" transition={150} />}
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.name}>{p.name}</Text>
                {!!p.description && <Text style={s.desc} numberOfLines={2}>{p.description}</Text>}
                <Text style={s.price}>{money(priceOf(p, v))}</Text>
                {p.variants?.length > 0 && (
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, marginTop: 6 }}>
                    {p.variants.map((vr: any) => (
                      <TouchableOpacity key={vr.label} disabled={vr.stock <= 0}
                        onPress={() => setVariantPick((m) => ({ ...m, [p.product_id]: vr.label }))}
                        style={[s.vchip, variantPick[p.product_id] === vr.label && s.vchipOn, vr.stock <= 0 && { opacity: 0.4 }]}
                        testID={`prod-variant-${p.product_id}-${vr.label}`}>
                        <Text style={[s.vchipText, variantPick[p.product_id] === vr.label && { color: '#fff' }]}>{vr.label}</Text>
                      </TouchableOpacity>
                    ))}
                  </ScrollView>
                )}
                <TouchableOpacity style={[s.addBtn, soldOut && { opacity: 0.4 }]} disabled={soldOut} onPress={() => add(p)} testID={`prod-add-${p.product_id}`}>
                  <Ionicons name="add" size={15} color="#fff" /><Text style={s.addText}>{soldOut ? 'Sold out' : 'Add'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        })}
        {(!data.products || !data.products.length) && <Text style={{ color: COLORS.textDim, marginTop: 20, textAlign: 'center' }}>No products yet.</Text>}
      </ScrollView>

      {entries.length > 0 && (
        <View style={s.footer}>
          <View style={s.fulRow}>
            {dcfg.pickup && <TouchableOpacity onPress={() => setFulfillment('pickup')} style={[s.fulBtn, fulfillment === 'pickup' && s.fulBtnOn]} testID="prod-pickup"><Text style={[s.fulText, fulfillment === 'pickup' && { color: '#fff' }]}>Pickup</Text></TouchableOpacity>}
            {dcfg.delivery && <TouchableOpacity onPress={() => setFulfillment('delivery')} style={[s.fulBtn, fulfillment === 'delivery' && s.fulBtnOn]} testID="prod-delivery"><Text style={[s.fulText, fulfillment === 'delivery' && { color: '#fff' }]}>Delivery{deliveryFee > 0 ? ` +${money(deliveryFee)}` : ' Free'}</Text></TouchableOpacity>}
          </View>
          {fulfillment === 'delivery' && (
            <TextInput style={s.addr} value={address} onChangeText={setAddress} placeholder="Delivery address" placeholderTextColor={COLORS.textMuted} testID="prod-address" />
          )}
          <TouchableOpacity style={[common.btnPrimary, busy && { opacity: 0.6 }]} disabled={busy} onPress={checkout} testID="prod-checkout">
            {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="bag-check" size={16} color="#fff" /><Text style={common.btnPrimaryText}>Checkout · {money(subtotal + deliveryFee)}</Text></>}
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  card: { flexDirection: 'row', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 10 },
  img: { width: 72, height: 72, borderRadius: RADIUS.sm, backgroundColor: COLORS.inputBg },
  name: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  desc: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  price: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900', marginTop: 4 },
  vchip: { paddingHorizontal: 12, height: 30, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  vchipOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  vchipText: { color: COLORS.text, fontWeight: '800', fontSize: FONT.xs },
  addBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4, backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingVertical: 8, marginTop: 10, alignSelf: 'flex-start', paddingHorizontal: 18 },
  addText: { color: '#fff', fontWeight: '900', fontSize: FONT.sm },
  footer: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  fulRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  fulBtn: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  fulBtnOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  fulText: { color: COLORS.text, fontWeight: '800', fontSize: FONT.sm },
  addr: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, marginBottom: 10 },
});
