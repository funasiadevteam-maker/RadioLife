// Consumer restaurant menu — add items to cart (Marketplace Phase B).
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useCartStore } from '../../../src/stores/useCartStore';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;

export default function BusinessMenu() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const cart = useCartStore();

  const load = useCallback(async () => {
    try { const r = await api.get(`/shop/businesses/${id}/menu`); setData(r.data); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const qtyFor = (itemId: string) =>
    cart.businessId === id ? (cart.items.find((i) => i.item_id === itemId)?.qty || 0) : 0;

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (!data) return <View style={common.center}><Text style={{ color: COLORS.textDim }}>Menu unavailable.</Text></View>;

  const count = cart.count();
  const sameBiz = cart.businessId === id;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="menu-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle} numberOfLines={1}>{data.public_name}</Text>
        <TouchableOpacity onPress={() => router.push('/shop/orders')} testID="menu-orders">
          <Ionicons name="receipt-outline" size={20} color={COLORS.text} />
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 120 }} testID="menu-root">
        {!!data.cover_url && <Image source={{ uri: data.cover_url }} style={s.cover} contentFit="cover" transition={200} />}
        <View style={{ padding: SPACING.md }}>
          <View style={s.earnBadge}>
            <Text style={s.earnGlyph}>₿</Text>
            <Text style={s.earnText}>Earn {data.default_bigpoints} BigPoints</Text>
            {data.happy_hour && (
              <View style={s.hhPill} testID="menu-happy-hour">
                <Ionicons name="flash" size={11} color="#fff" />
                <Text style={s.hhText}>{data.points_multiplier}X Happy Hour</Text>
              </View>
            )}
          </View>

          {(data.sections || []).map((sec: any) => (
            <View key={sec.title} style={{ marginTop: SPACING.lg }}>
              <Text style={s.secTitle}>{sec.title}</Text>
              {sec.items.map((it: any) => {
                const q = qtyFor(it.item_id);
                return (
                  <View key={it.item_id} style={s.itemRow} testID={`menu-item-${it.item_id}`}>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.itemName}>{it.name}</Text>
                      {!!it.description && <Text style={s.itemDesc} numberOfLines={2}>{it.description}</Text>}
                      <Text style={s.itemPrice}>{money(it.price_cents)}</Text>
                    </View>
                    {q > 0 && sameBiz ? (
                      <View style={s.stepper}>
                        <TouchableOpacity onPress={() => cart.dec(it.item_id)} testID={`menu-dec-${it.item_id}`} style={s.stepBtn}>
                          <Ionicons name="remove" size={18} color={COLORS.primary} />
                        </TouchableOpacity>
                        <Text style={s.stepQty}>{q}</Text>
                        <TouchableOpacity onPress={() => cart.inc(it.item_id)} testID={`menu-inc-${it.item_id}`} style={s.stepBtn}>
                          <Ionicons name="add" size={18} color={COLORS.primary} />
                        </TouchableOpacity>
                      </View>
                    ) : (
                      <TouchableOpacity style={s.addBtn} testID={`menu-add-${it.item_id}`}
                        onPress={() => cart.add(id!, data.public_name, {
                          item_id: it.item_id, name: it.name, price_cents: it.price_cents })}>
                        <Ionicons name="add" size={18} color="#fff" />
                      </TouchableOpacity>
                    )}
                  </View>
                );
              })}
            </View>
          ))}
          {(!data.sections || data.sections.length === 0) && (
            <Text style={{ color: COLORS.textDim, marginTop: 24, textAlign: 'center' }}>
              This restaurant hasn&apos;t published a menu yet.
            </Text>
          )}
        </View>
      </ScrollView>

      {count > 0 && (
        <View style={s.footer}>
          <TouchableOpacity style={common.btnPrimary} testID="menu-view-cart"
            onPress={() => router.push('/shop/cart')}>
            <Ionicons name="cart" size={16} color="#fff" />
            <Text style={common.btnPrimaryText}>
              View Cart ({count}) · {money(cart.subtotal())}
            </Text>
          </TouchableOpacity>
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { flex: 1, color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  cover: { width: '100%', height: 160, backgroundColor: COLORS.inputBg },
  earnBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap', alignSelf: 'flex-start', backgroundColor: COLORS.gold + '1f', paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.full },
  earnGlyph: { color: COLORS.gold, fontSize: 15, fontWeight: '900' },
  earnText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  hhPill: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: COLORS.primary, paddingHorizontal: 8, paddingVertical: 4, borderRadius: RADIUS.full },
  hhText: { color: '#fff', fontSize: FONT.xs, fontWeight: '900' },
  secTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 8 },
  itemRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  itemName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  itemDesc: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2, lineHeight: 16 },
  itemPrice: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900', marginTop: 4 },
  addBtn: { width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.full, paddingHorizontal: 6, paddingVertical: 4 },
  stepBtn: { width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  stepQty: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', minWidth: 16, textAlign: 'center' },
  footer: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
});
