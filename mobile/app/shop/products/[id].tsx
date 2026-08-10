// Consumer ecommerce — browse products & variants, add to multi-venue cart.
import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useProductCart } from '../../../src/stores/useProductCart';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const absUrl = (u?: string | null) => (!u ? null : u.startsWith('http') ? u : `${process.env.EXPO_PUBLIC_BACKEND_URL}${u}`);

export default function Products() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [variantPick, setVariantPick] = useState<Record<string, string>>({});
  const add = useProductCart((st) => st.add);
  const cartCount = useProductCart((st) => Object.values(st.groups).reduce((n, g) => n + g.items.reduce((m, i) => m + i.qty, 0), 0));

  useEffect(() => {
    api.get(`/shop/businesses/${id}/products`).then((r) => {
      setData(r.data);
    }).catch(() => setData(null)).finally(() => setLoading(false));
  }, [id]);

  const priceOf = (p: any, v: any) => (v && v.price_cents > 0 ? v.price_cents : p.price_cents);
  const addToCart = (p: any) => {
    const v = p.variants?.length ? p.variants.find((x: any) => x.label === variantPick[p.product_id]) : null;
    if (p.variants?.length && !v) return;
    add(id!, data.public_name, p, v, data.delivery);
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Shop unavailable.</Text></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="prod-back" style={{ padding: 2 }}><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.topTitle} numberOfLines={1}>{data.public_name}</Text>
        <TouchableOpacity onPress={() => router.push('/shop/product-cart')} testID="prod-cart" style={{ padding: 2 }}>
          <Ionicons name="cart-outline" size={22} color={COLORS.text} />
          {cartCount > 0 && <View style={s.badge}><Text style={s.badgeText}>{cartCount}</Text></View>}
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 120 }} testID="prod-root">
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
                <TouchableOpacity style={[s.addBtn, soldOut && { opacity: 0.4 }]} disabled={soldOut} onPress={() => addToCart(p)} testID={`prod-add-${p.product_id}`}>
                  <Ionicons name="add" size={15} color="#fff" /><Text style={s.addText}>{soldOut ? 'Sold out' : 'Add to cart'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          );
        })}
        {(!data.products || !data.products.length) && <Text style={{ color: COLORS.textDim, marginTop: 20, textAlign: 'center' }}>No products yet.</Text>}
      </ScrollView>

      {cartCount > 0 && (
        <View style={s.footer}>
          <TouchableOpacity style={common.btnPrimary} onPress={() => router.push('/shop/product-cart')} testID="prod-go-cart">
            <Ionicons name="cart" size={16} color="#fff" />
            <Text style={common.btnPrimaryText}>View cart · {cartCount} item{cartCount > 1 ? 's' : ''}</Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  badge: { position: 'absolute', top: -4, right: -6, minWidth: 18, height: 18, borderRadius: 9, paddingHorizontal: 4, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  badgeText: { color: '#fff', fontSize: 10, fontWeight: '900' },
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
});
