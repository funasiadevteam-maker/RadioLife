// Multi-merchant Shop cart — splits into one order per venue at checkout (Marketplace Phase E).
import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useProductCart } from '../../src/stores/useProductCart';
import { useReward } from '../../src/components/RewardOverlay';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;

export default function ProductCart() {
  const router = useRouter();
  const { groups, inc, dec, setFulfillment, setAddress, removeGroup, clear } = useProductCart();
  const { celebrate } = useReward();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const entries = Object.entries(groups);
  const grand = entries.reduce((s, [, g]) => s + g.items.reduce((m, i) => m + i.price_cents * i.qty, 0), 0);

  const checkout = async () => {
    const payload = entries.map(([bizId, g]) => ({
      business_id: bizId,
      fulfillment: g.fulfillment,
      address: g.fulfillment === 'delivery' ? (g.address || '').trim() : null,
      items: g.items.map((i) => ({ product_id: i.product_id, variant_label: i.variant_label, qty: i.qty })),
    }));
    if (payload.some((p) => p.fulfillment === 'delivery' && !p.address)) {
      setError('Add a delivery address for each delivery order.'); return;
    }
    setBusy(true); setError(null);
    try {
      const r = await api.post('/shop/cart/checkout', {
        groups: payload, use_gift_card: true, origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
      });
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        clear();
        celebrate({ points: 0, title: 'Order placed! 🎉' });
        router.replace('/shop/product-orders');
        return;
      }
      // Fully covered by gift card(s).
      clear();
      celebrate({ points: 0, title: 'Order placed with gift card! 🎉' });
      router.replace('/shop/product-orders');
    } catch (e: any) {
      setError(e?.response?.data?.detail?.code || 'Checkout failed');
    } finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="pcart-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Your Cart</Text>
        <View style={{ width: 22 }} />
      </View>

      {!entries.length ? (
        <View style={common.center} testID="pcart-empty">
          <Ionicons name="cart-outline" size={48} color={COLORS.textMuted} />
          <Text style={{ color: COLORS.textDim, marginTop: 12, fontWeight: '700' }}>Your cart is empty.</Text>
          <TouchableOpacity style={[common.btnGhost, { marginTop: 16, paddingHorizontal: 24 }]}
            onPress={() => router.replace('/shop')} testID="pcart-browse">
            <Text style={common.btnGhostText}>Browse the Shop</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <>
          <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 200 }} testID="pcart-root">
            {entries.map(([bizId, g]) => {
              const sub = g.items.reduce((m, i) => m + i.price_cents * i.qty, 0);
              const cfg = g.delivery_cfg || {};
              return (
                <View key={bizId} style={s.group} testID={`pcart-group-${bizId}`}>
                  <View style={s.groupHead}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1, minWidth: 0 }}>
                      <Ionicons name="storefront" size={15} color={COLORS.primary} />
                      <Text style={s.bizName} numberOfLines={1}>{g.business_name}</Text>
                    </View>
                    <TouchableOpacity onPress={() => removeGroup(bizId)} testID={`pcart-remove-group-${bizId}`}>
                      <Ionicons name="trash-outline" size={18} color={COLORS.red} />
                    </TouchableOpacity>
                  </View>

                  {g.items.map((i) => (
                    <View key={i.key} style={s.itemRow} testID={`pcart-item-${bizId}-${i.key}`}>
                      <Text style={s.itemName} numberOfLines={1}>{i.name}{i.variant_label ? ` (${i.variant_label})` : ''}</Text>
                      <View style={s.stepper}>
                        <TouchableOpacity onPress={() => dec(bizId, i.key)} testID={`pcart-dec-${bizId}-${i.key}`} style={s.stepBtn}>
                          <Ionicons name="remove" size={16} color={COLORS.primary} />
                        </TouchableOpacity>
                        <Text style={s.qty}>{i.qty}</Text>
                        <TouchableOpacity onPress={() => inc(bizId, i.key)} testID={`pcart-inc-${bizId}-${i.key}`} style={s.stepBtn}>
                          <Ionicons name="add" size={16} color={COLORS.primary} />
                        </TouchableOpacity>
                        <Text style={s.itemPrice}>{money(i.price_cents * i.qty)}</Text>
                      </View>
                    </View>
                  ))}

                  <View style={s.fulRow}>
                    {cfg.pickup !== false && (
                      <TouchableOpacity onPress={() => setFulfillment(bizId, 'pickup')} style={[s.fulBtn, g.fulfillment === 'pickup' && s.fulBtnOn]} testID={`pcart-pickup-${bizId}`}>
                        <Text style={[s.fulText, g.fulfillment === 'pickup' && { color: '#fff' }]}>Pickup</Text>
                      </TouchableOpacity>
                    )}
                    {cfg.delivery && (
                      <TouchableOpacity onPress={() => setFulfillment(bizId, 'delivery')} style={[s.fulBtn, g.fulfillment === 'delivery' && s.fulBtnOn]} testID={`pcart-delivery-${bizId}`}>
                        <Text style={[s.fulText, g.fulfillment === 'delivery' && { color: '#fff' }]}>Delivery</Text>
                      </TouchableOpacity>
                    )}
                  </View>
                  {g.fulfillment === 'delivery' && (
                    <TextInput style={s.addr} value={g.address} onChangeText={(t) => setAddress(bizId, t)}
                      placeholder="Delivery address" placeholderTextColor={COLORS.textMuted} testID={`pcart-address-${bizId}`} />
                  )}
                  <Text style={s.sub}>Subtotal {money(sub)}</Text>
                </View>
              );
            })}
            {!!error && <Text style={s.error} testID="pcart-error">{error}</Text>}
          </ScrollView>

          <View style={s.footer}>
            <TouchableOpacity style={[common.btnPrimary, busy && { opacity: 0.6 }]} disabled={busy} onPress={checkout} testID="pcart-checkout">
              {busy ? <ActivityIndicator color="#fff" />
                : <><Ionicons name="lock-closed" size={16} color="#fff" />
                  <Text style={common.btnPrimaryText}>Checkout {entries.length > 1 ? `${entries.length} venues · ` : ''}{money(grand)}</Text></>}
            </TouchableOpacity>
            <Text style={s.note}>Gift cards auto-apply per venue · one order per venue</Text>
          </View>
        </>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  group: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 12 },
  groupHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  bizName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  itemRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 6 },
  itemName: { flex: 1, minWidth: 0, color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  stepBtn: { width: 26, height: 26, borderRadius: 13, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  qty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', minWidth: 14, textAlign: 'center' },
  itemPrice: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', minWidth: 56, textAlign: 'right' },
  fulRow: { flexDirection: 'row', gap: 8, marginTop: 8 },
  fulBtn: { flex: 1, alignItems: 'center', paddingVertical: 9, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder },
  fulBtnOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  fulText: { color: COLORS.text, fontWeight: '800', fontSize: FONT.sm },
  addr: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, marginTop: 8 },
  sub: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '900', textAlign: 'right', marginTop: 8 },
  error: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '700', marginTop: 4 },
  footer: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  note: { textAlign: 'center', color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 8 },
});
