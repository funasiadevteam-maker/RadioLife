// Cart & Pickup Checkout — gift-card auto-apply + Stripe (Marketplace Phase B).
import React, { useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView, ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import { useCartStore } from '../../src/stores/useCartStore';
import { useReward } from '../../src/components/RewardOverlay';
import SavedCardPicker from '../../src/components/SavedCardPicker';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const COUPON_ERR: Record<string, string> = {
  invalid_coupon: "Not valid for this shop.", expired: "This coupon has expired.",
  not_started: "Not active yet.", min_spend_not_met: "Minimum spend not met.",
  usage_exceeded: "Usage limit reached.", already_used: "You've already used this.",
};

export default function Cart() {
  const router = useRouter();
  const cart = useCartStore();
  const { celebrate } = useReward();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useGift, setUseGift] = useState(true);
  const [usePoints, setUsePoints] = useState(false);
  const [quote, setQuote] = useState<any>(null);
  const [payCard, setPayCard] = useState<string | null>(null);
  const [coupon, setCoupon] = useState('');
  const [couponInput, setCouponInput] = useState('');

  const subtotal = cart.subtotal();

  const refresh = React.useCallback(async (gift: boolean, pts: boolean, cpn: string = coupon) => {
    if (!cart.businessId || !cart.items.length) return;
    try {
      const r = await api.post('/shop/orders/quote', {
        business_id: cart.businessId,
        items: cart.items.map((i) => ({ item_id: i.item_id, qty: i.qty })),
        use_gift_card: gift,
        redeem_points: pts ? 10 ** 9 : 0, // server caps to max redeemable
        coupon_code: cpn || undefined,
      });
      setQuote(r.data);
    } catch { /* keep last quote */ }
  }, [cart.businessId, cart.items, coupon]);

  React.useEffect(() => { refresh(useGift, usePoints); }, [useGift, usePoints, refresh]);

  const applyCoupon = () => {
    const c = couponInput.trim().toUpperCase();
    setCoupon(c); refresh(useGift, usePoints, c);
  };

  const total = quote ? quote.total_cents : subtotal;

  const checkout = async () => {
    if (!cart.businessId || !cart.items.length) return;
    setBusy(true); setError(null);
    try {
      const r = await api.post('/shop/orders/checkout', {
        business_id: cart.businessId,
        items: cart.items.map((i) => ({ item_id: i.item_id, qty: i.qty })),
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
        use_gift_card: useGift,
        redeem_points: usePoints && quote ? quote.max_redeemable_points : 0,
        coupon_code: coupon || undefined,
        payment_method_id: payCard || undefined,
      });
      const orderId = r.data.order_id;
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/shop/orders/${orderId}/status`);
        if (st.data.payment_status === 'paid') {
          cart.clear();
          celebrate({ points: 0, title: 'Order placed! 🎉' });
          router.replace('/shop/orders');
          return;
        }
        setError('Payment not completed. Your order is saved as pending.');
      } else {
        cart.clear();
        celebrate({ points: 0, title: 'Order placed! 🎉' });
        router.replace('/shop/orders');
        return;
      }
    } catch (e: any) {
      setError(e?.response?.data?.detail?.code || 'Checkout failed');
    } finally { setBusy(false); }
  };

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="cart-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Your Cart</Text>
        <View style={{ width: 22 }} />
      </View>

      {!cart.items.length ? (
        <View style={common.center} testID="cart-empty">
          <Ionicons name="cart-outline" size={48} color={COLORS.textMuted} />
          <Text style={{ color: COLORS.textDim, marginTop: 12, fontWeight: '700' }}>Your cart is empty.</Text>
          <TouchableOpacity style={[common.btnGhost, { marginTop: 16, paddingHorizontal: 24 }]}
            onPress={() => router.replace('/shop')} testID="cart-browse">
            <Text style={common.btnGhostText}>Browse the Shop</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <>
          <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 200 }} testID="cart-root">
            <Text style={s.biz}>{cart.businessName}</Text>
            {cart.items.map((i) => (
              <View key={i.item_id} style={s.row} testID={`cart-item-${i.item_id}`}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.name}>{i.name}</Text>
                  <Text style={s.price}>{money(i.price_cents)}</Text>
                </View>
                <View style={s.stepper}>
                  <TouchableOpacity onPress={() => cart.dec(i.item_id)} testID={`cart-dec-${i.item_id}`} style={s.stepBtn}>
                    <Ionicons name="remove" size={18} color={COLORS.primary} />
                  </TouchableOpacity>
                  <Text style={s.qty}>{i.qty}</Text>
                  <TouchableOpacity onPress={() => cart.inc(i.item_id)} testID={`cart-inc-${i.item_id}`} style={s.stepBtn}>
                    <Ionicons name="add" size={18} color={COLORS.primary} />
                  </TouchableOpacity>
                </View>
              </View>
            ))}

            {quote && quote.gift_available_cents > 0 && (
              <TouchableOpacity style={s.optRow} testID="cart-giftcard-toggle" onPress={() => setUseGift((v) => !v)}>
                <View style={[s.check, useGift && s.checkOn]}>{useGift && <Ionicons name="checkmark" size={14} color="#fff" />}</View>
                <Ionicons name="gift" size={16} color={COLORS.green} />
                <Text style={s.optText}>Apply gift card · {money(quote.gift_available_cents)} available</Text>
                <Text style={s.optDiscount}>−{money(quote.gift_applied_cents)}</Text>
              </TouchableOpacity>
            )}
            {quote && quote.points_balance > 0 && (
              <TouchableOpacity style={s.optRow} testID="cart-points-toggle"
                onPress={() => setUsePoints((v) => !v)} disabled={quote.max_redeemable_points <= 0 && !usePoints}>
                <View style={[s.check, usePoints && s.checkOn]}>{usePoints && <Ionicons name="checkmark" size={14} color="#fff" />}</View>
                <Ionicons name="server" size={16} color={COLORS.primary} />
                <Text style={s.optText}>Use BigPoints · balance {quote.points_balance}</Text>
                <Text style={s.optDiscount}>−{money(quote.points_discount_cents)}</Text>
              </TouchableOpacity>
            )}
            <View style={s.couponRow} testID="cart-coupon">
              <TextInput style={s.couponInput} value={couponInput} onChangeText={setCouponInput}
                autoCapitalize="characters" placeholder="Coupon code" placeholderTextColor={COLORS.textMuted}
                testID="cart-coupon-input" />
              <TouchableOpacity style={s.couponBtn} onPress={applyCoupon} testID="cart-coupon-apply">
                <Ionicons name="pricetag" size={14} color="#fff" />
                <Text style={s.couponBtnText}>Apply</Text>
              </TouchableOpacity>
            </View>
            {quote && quote.coupon_discount_cents > 0 && (
              <Text style={s.couponOk} testID="cart-coupon-applied">{quote.coupon_code} applied · −{money(quote.coupon_discount_cents)}</Text>
            )}
            {quote && quote.coupon_error && !!coupon && (
              <Text style={s.couponErr} testID="cart-coupon-error">{COUPON_ERR[quote.coupon_error] || 'Coupon not valid'}</Text>
            )}
            {total > 0 && <SavedCardPicker selected={payCard} onSelect={setPayCard} />}
            {!!error && <Text style={s.error} testID="cart-error">{error}</Text>}
          </ScrollView>

          <View style={s.footer}>
            <View style={s.sumRow}>
              <Text style={s.sumLabel}>Total to pay</Text>
              <Text style={s.sumValue} testID="cart-total">{money(total)}</Text>
            </View>
            <TouchableOpacity style={[common.btnPrimary, busy && { opacity: 0.6 }]} disabled={busy}
              onPress={checkout} testID="cart-checkout">
              {busy ? <ActivityIndicator color="#fff" />
                : <><Ionicons name={total > 0 ? 'card' : 'checkmark-circle'} size={16} color="#fff" />
                  <Text style={common.btnPrimaryText}>{total > 0 ? `Pay by card · ${money(total)}` : 'Place order'}</Text></>}
            </TouchableOpacity>
          </View>
        </>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  biz: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: SPACING.md },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  name: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  price: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900', marginTop: 4 },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.full, paddingHorizontal: 6, paddingVertical: 4 },
  stepBtn: { width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center' },
  qty: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', minWidth: 16, textAlign: 'center' },
  giftNote: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.green + '12', borderRadius: RADIUS.md, padding: 12, marginTop: 12 },
  giftText: { flex: 1, color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  optRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginTop: 10 },
  check: { width: 20, height: 20, borderRadius: 6, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  checkOn: { backgroundColor: COLORS.green },
  optText: { flex: 1, color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  optDiscount: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  error: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '700', marginTop: 12 },
  couponRow: { flexDirection: 'row', gap: 8, marginTop: 10 },
  couponInput: { flex: 1, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  couponBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: COLORS.text, borderRadius: RADIUS.md, paddingHorizontal: 14, justifyContent: 'center' },
  couponBtnText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  couponOk: { color: COLORS.green, fontSize: FONT.xs, fontWeight: '900', marginTop: 6 },
  couponErr: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '800', marginTop: 6 },
  footer: { position: 'absolute', bottom: 0, left: 0, right: 0, padding: SPACING.md, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  sumRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 },
  sumLabel: { color: COLORS.textDim, fontSize: FONT.md, fontWeight: '700' },
  sumValue: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
});
