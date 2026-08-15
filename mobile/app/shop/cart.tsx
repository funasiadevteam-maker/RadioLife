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
import { useSavedForLater } from '../../src/stores/useSavedForLater';
import { useReward } from '../../src/components/RewardOverlay';
import SavedCardPicker from '../../src/components/SavedCardPicker';
import DeliveryAddressCard from '../../src/components/DeliveryAddressCard';

const money = (c: number) => `$${(c / 100).toFixed(2)}`;
const PICKUP_TIMES: [string, string][] = [['now', 'Now (~15 min)'], ['+15', 'In 15 min'], ['+30', 'In 30 min'], ['+45', 'In 45 min']];
const COUPON_ERR: Record<string, string> = {
  invalid_coupon: "Not valid for this shop.", expired: "This coupon has expired.",
  not_started: "Not active yet.", min_spend_not_met: "Minimum spend not met.",
  usage_exceeded: "Usage limit reached.", already_used: "You've already used this.",
  entitlement_exhausted: "Membership perk used up for now.", outside_time_window: "Perk unavailable at this time.",
  entitlement_not_eligible: "Membership doesn't cover an item.", entitlement_not_stackable: "Can't combine membership with a coupon.",
  upcharge_exceeds_cap: "Upgrades exceed what the membership covers.",
};
const cartItemsPayload = (items: any[]) => items.map((i) => ({
  item_id: i.item_id, qty: i.qty,
  selected_option_ids: i.selected_option_ids || [],
  note: i.note || undefined,
  apply_entitlement_id: i.apply_entitlement_id || undefined,
}));

export default function Cart() {
  const router = useRouter();
  const cart = useCartStore();
  const saved = useSavedForLater();
  const { celebrate } = useReward();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [useGift, setUseGift] = useState(true);
  const [usePoints, setUsePoints] = useState(false);
  const [quote, setQuote] = useState<any>(null);
  const [payCard, setPayCard] = useState<string | null>(null);
  const [coupon, setCoupon] = useState('');
  const [couponInput, setCouponInput] = useState('');
  const [bizRef, setBizRef] = useState<{ id: string; name: string } | null>(null);
  const [undoSnap, setUndoSnap] = useState<{ id: string | null; name: string | null; items: any[] } | null>(null);

  const subtotal = cart.subtotal();
  const savedBiz = cart.businessId || bizRef?.id || '';
  const savedList = saved.listFor(savedBiz);

  const refresh = React.useCallback(async (gift: boolean, pts: boolean, cpn: string = coupon) => {
    if (!cart.businessId || !cart.items.length) return;
    try {
      const r = await api.post('/shop/orders/quote', {
        business_id: cart.businessId,
        items: cartItemsPayload(cart.items),
        use_gift_card: gift,
        redeem_points: pts ? 10 ** 9 : 0, // server caps to max redeemable
        coupon_code: cpn || undefined,
        fulfillment: cart.fulfillment || 'pickup',
        pickup_time: cart.pickupTime || 'now',
        delivery_address: cart.fulfillment === 'delivery' ? cart.deliveryAddress || undefined : undefined,
      });
      setQuote(r.data);
    } catch { /* keep last quote */ }
  }, [cart.businessId, cart.items, coupon, cart.fulfillment, cart.pickupTime, cart.deliveryAddress]);

  React.useEffect(() => { refresh(useGift, usePoints); }, [useGift, usePoints, refresh]);

  // Remember the business even after the cart empties, so the saved-for-later
  // shelf stays reachable.
  React.useEffect(() => {
    if (cart.businessId) setBizRef({ id: cart.businessId, name: cart.businessName || '' });
  }, [cart.businessId, cart.businessName]);

  const saveForLater = (i: any) => {
    if (!savedBiz) return;
    saved.save(savedBiz, {
      key: `m:${i.line_id}`, kind: 'menu', item_id: i.item_id, name: i.name, price_cents: i.price_cents,
      selected_option_ids: i.selected_option_ids || [], option_summary: i.option_summary || null, note: i.note || null,
    });
    cart.remove(i.line_id);
  };
  const moveToCart = (e: any) => {
    cart.addLine(savedBiz, bizRef?.name || cart.businessName || '', {
      item_id: e.item_id, name: e.name, price_cents: e.price_cents,
      selected_option_ids: e.selected_option_ids, option_summary: e.option_summary, note: e.note,
    });
    saved.remove(savedBiz, e.key);
  };
  const clearCart = () => {
    if (!cart.items.length) return;
    setUndoSnap({ id: cart.businessId, name: cart.businessName, items: cart.items });
    cart.clear();
  };
  const undoClear = () => {
    if (!undoSnap) return;
    cart.restore(undoSnap.id, undoSnap.name, undoSnap.items);
    setUndoSnap(null);
  };

  // If the shop doesn't deliver, snap back to pickup.
  React.useEffect(() => {
    if (quote && quote.delivery_available === false && cart.fulfillment === 'delivery') {
      cart.setFulfillment('pickup');
    }
  }, [quote, cart.fulfillment]);

  const applyCoupon = () => {
    const c = couponInput.trim().toUpperCase();
    setCoupon(c); refresh(useGift, usePoints, c);
  };

  const total = quote ? quote.total_cents : subtotal;
  const needsAddress = cart.fulfillment === 'delivery' && !cart.deliveryAddress;

  const savedShelfEl = savedList.length > 0 ? (
    <View style={s.savedShelf} testID="cart-saved-shelf">
      <Text style={s.savedTitle}>Saved for later</Text>
      {savedList.map((e) => (
        <View key={e.key} style={s.savedRow} testID={`cart-saved-${e.key}`}>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={s.savedName} numberOfLines={1}>{e.name}</Text>
            <Text style={s.savedPrice}>{money(e.price_cents)}</Text>
          </View>
          <TouchableOpacity onPress={() => moveToCart(e)} testID={`cart-saved-add-${e.key}`} style={s.savedAdd}>
            <Ionicons name="add" size={14} color={COLORS.primary} /><Text style={s.savedAddText}>Move to cart</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={() => saved.remove(savedBiz, e.key)} testID={`cart-saved-remove-${e.key}`} style={{ paddingLeft: 8 }}>
            <Ionicons name="trash-outline" size={16} color={COLORS.red} />
          </TouchableOpacity>
        </View>
      ))}
    </View>
  ) : null;

  const checkout = async () => {
    if (!cart.businessId || !cart.items.length) return;
    if (needsAddress) { setError('Add a delivery address first.'); return; }
    setBusy(true); setError(null);
    try {
      const r = await api.post('/shop/orders/checkout', {
        business_id: cart.businessId,
        items: cartItemsPayload(cart.items),
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
        use_gift_card: useGift,
        redeem_points: usePoints && quote ? quote.max_redeemable_points : 0,
        coupon_code: coupon || undefined,
        payment_method_id: payCard || undefined,
        fulfillment: cart.fulfillment || 'pickup',
        pickup_time: cart.pickupTime || 'now',
        delivery_address: cart.fulfillment === 'delivery' ? cart.deliveryAddress || undefined : undefined,
      });
      const orderId = r.data.order_id;
      if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        const st = await api.get(`/shop/orders/${orderId}/status`);
        if (st.data.payment_status === 'paid') {
          cart.clear();
          celebrate({ points: 0, title: 'Order placed! 🎉' });
          router.replace(`/shop/order/${orderId}` as any);
          return;
        }
        setError('Payment not completed. Your order is saved as pending.');
      } else {
        cart.clear();
        celebrate({ points: 0, title: 'Order placed! 🎉' });
        router.replace(`/shop/order/${orderId}` as any);
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
        {cart.items.length ? (
          <TouchableOpacity onPress={clearCart} testID="cart-clear"><Ionicons name="trash-outline" size={20} color={COLORS.red} /></TouchableOpacity>
        ) : <View style={{ width: 22 }} />}
      </View>

      {undoSnap && (
        <View style={s.undoBanner} testID="cart-undo-banner">
          <Text style={s.undoText}>Cart cleared</Text>
          <TouchableOpacity onPress={undoClear} testID="cart-undo"><Text style={s.undoBtn}>Undo</Text></TouchableOpacity>
        </View>
      )}

      {!cart.items.length ? (
        <ScrollView contentContainerStyle={{ padding: SPACING.md }} testID="cart-root-empty">
          <View style={{ alignItems: 'center', paddingVertical: 40 }} testID="cart-empty">
            <Ionicons name="cart-outline" size={48} color={COLORS.textMuted} />
            <Text style={{ color: COLORS.textDim, marginTop: 12, fontWeight: '700' }}>Your cart is empty.</Text>
            <TouchableOpacity style={[common.btnGhost, { marginTop: 16, paddingHorizontal: 24 }]}
              onPress={() => router.replace('/shop')} testID="cart-browse">
              <Text style={common.btnGhostText}>Browse the Shop</Text>
            </TouchableOpacity>
          </View>
          {savedShelfEl}
        </ScrollView>
      ) : (
        <>
          <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 200 }} testID="cart-root">
            <Text style={s.biz}>{cart.businessName}</Text>

            {/* Pickup context */}
            <View style={s.pickupCard} testID="cart-pickup">
              <View style={s.fulRow}>
                <TouchableOpacity style={[s.fulBtn, (cart.fulfillment || 'pickup') === 'pickup' && s.fulBtnOn]} onPress={() => cart.setFulfillment('pickup')} testID="cart-fulfillment-pickup">
                  <Text style={[s.fulText, (cart.fulfillment || 'pickup') === 'pickup' && s.fulTextOn]}>Pickup</Text>
                </TouchableOpacity>
                {quote?.delivery_available !== false && (
                  <TouchableOpacity style={[s.fulBtn, cart.fulfillment === 'delivery' && s.fulBtnOn]} onPress={() => cart.setFulfillment('delivery')} testID="cart-fulfillment-delivery">
                    <Text style={[s.fulText, cart.fulfillment === 'delivery' && s.fulTextOn]}>Delivery</Text>
                  </TouchableOpacity>
                )}
              </View>
              <Text style={s.pickupLabel}>{cart.fulfillment === 'delivery' ? 'Deliver' : 'Pick up'} time</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
                {PICKUP_TIMES.map(([v, l]) => (
                  <TouchableOpacity key={v} onPress={() => cart.setPickupTime(v)} style={[s.timePill, (cart.pickupTime || 'now') === v && s.timePillOn]} testID={`cart-pickup-${v}`}>
                    <Text style={[s.timePillText, (cart.pickupTime || 'now') === v && { color: '#fff' }]}>{l}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
              {!!quote?.eta_label && (
                <View style={s.etaRow} testID="cart-eta">
                  <Ionicons name="time-outline" size={14} color={COLORS.primary} />
                  <Text style={s.etaText}>{cart.fulfillment === 'delivery' ? `Arrives in ${quote.eta_label}` : quote.eta_label}</Text>
                </View>
              )}
            </View>

            {cart.fulfillment === 'delivery' && (
              <DeliveryAddressCard value={cart.deliveryAddress} onChange={cart.setDeliveryAddress} />
            )}

            {cart.items.map((i) => (
              <View key={i.line_id} style={s.row} testID={`cart-item-${i.item_id}`}>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={s.name}>{i.name}</Text>
                  {!!i.option_summary && <Text style={s.opts}>{i.option_summary}</Text>}
                  {!!i.entitlement_label && <Text style={s.entLine}>♛ {i.entitlement_label}</Text>}
                  {!!i.note && <Text style={s.noteLine} testID={`cart-note-${i.item_id}`}>“{i.note}”</Text>}
                  <Text style={s.price}>{money(i.price_cents)}</Text>
                </View>
                <View style={s.rowActions}>
                  <TouchableOpacity onPress={() => saveForLater(i)} testID={`cart-save-${i.item_id}`} style={s.bookmarkBtn}>
                    <Ionicons name="bookmark-outline" size={16} color={COLORS.primary} />
                  </TouchableOpacity>
                  <View style={s.stepper}>
                    <TouchableOpacity onPress={() => cart.dec(i.line_id)} testID={`cart-dec-${i.item_id}`} style={s.stepBtn}>
                      <Ionicons name="remove" size={18} color={COLORS.primary} />
                    </TouchableOpacity>
                    <Text style={s.qty}>{i.qty}</Text>
                    <TouchableOpacity onPress={() => cart.inc(i.line_id)} testID={`cart-inc-${i.item_id}`} style={s.stepBtn}>
                      <Ionicons name="add" size={18} color={COLORS.primary} />
                    </TouchableOpacity>
                  </View>
                </View>
              </View>
            ))}

            {savedShelfEl}

            {quote && quote.combo_discount_cents > 0 && (
              <View style={s.comboRow} testID="cart-combo-discount">
                <Ionicons name="fast-food" size={15} color={COLORS.green} />
                <Text style={s.comboText}>{quote.combo_label || 'Meal combo'}</Text>
                <Text style={s.comboVal}>−{money(quote.combo_discount_cents)}</Text>
              </View>
            )}

            {quote && quote.entitlement_discount_cents > 0 && (
              <View style={s.entDiscRow} testID="cart-entitlement-discount">
                <Ionicons name="ribbon" size={15} color={COLORS.primary} />
                <Text style={s.entDiscText}>Membership</Text>
                <Text style={s.entDiscVal}>−{money(quote.entitlement_discount_cents)}</Text>
              </View>
            )}

            {quote && quote.join_nudge && (
              <TouchableOpacity style={s.nudge} testID="cart-join-nudge"
                onPress={() => router.push(`/shop/memberships/${cart.businessId}` as any)}>
                <Ionicons name="ribbon" size={18} color={COLORS.primary} />
                <View style={{ flex: 1 }}>
                  <Text style={s.nudgeTitle}>Join {quote.join_nudge.plan_name} &amp; save {money(quote.join_nudge.potential_savings_cents)}</Text>
                  <Text style={s.nudgeSub}>Your {quote.join_nudge.item_name} could be free · {money(quote.join_nudge.price_cents)}/{quote.join_nudge.interval}</Text>
                </View>
                <Text style={s.nudgeCta}>Join →</Text>
              </TouchableOpacity>
            )}

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
            {quote && (quote.service_fee_cents > 0 || (cart.fulfillment === 'delivery' && quote.delivery_fee_cents > 0) || quote.tax_cents > 0) && (
              <View style={s.feeBlock} testID="cart-fees">
                <View style={s.feeRow}>
                  <Text style={s.feeLabel}>Subtotal</Text>
                  <Text style={s.feeVal}>{money(quote.subtotal_cents)}</Text>
                </View>
                {quote.service_fee_cents > 0 && (
                  <View style={s.feeRow} testID="cart-service-fee">
                    <Text style={s.feeLabel}>Service fee</Text>
                    <Text style={s.feeVal}>{money(quote.service_fee_cents)}</Text>
                  </View>
                )}
                {cart.fulfillment === 'delivery' && quote.delivery_fee_cents > 0 && (
                  <View style={s.feeRow} testID="cart-delivery-fee">
                    <Text style={s.feeLabel}>Delivery fee</Text>
                    <Text style={s.feeVal}>{money(quote.delivery_fee_cents)}</Text>
                  </View>
                )}
                {quote.tax_cents > 0 && (
                  <View style={s.feeRow} testID="cart-tax">
                    <Text style={s.feeLabel}>{quote.tax_label || 'Tax'}{quote.tax_rate_percent ? ` (${quote.tax_rate_percent}%)` : ''}</Text>
                    <Text style={s.feeVal}>{money(quote.tax_cents)}</Text>
                  </View>
                )}
              </View>
            )}
            {total > 0 && <SavedCardPicker selected={payCard} onSelect={setPayCard} />}
            {!!error && <Text style={s.error} testID="cart-error">{COUPON_ERR[error] || error}</Text>}
          </ScrollView>

          <View style={s.footer}>
            <View style={s.sumRow}>
              <Text style={s.sumLabel}>Total to pay</Text>
              <Text style={s.sumValue} testID="cart-total">{money(total)}</Text>
            </View>
            <TouchableOpacity style={[common.btnPrimary, (busy || needsAddress) && { opacity: 0.6 }]} disabled={busy || needsAddress}
              onPress={checkout} testID="cart-checkout">
              {busy ? <ActivityIndicator color="#fff" />
                : <><Ionicons name={needsAddress ? 'location' : (total > 0 ? 'card' : 'checkmark-circle')} size={16} color="#fff" />
                  <Text style={common.btnPrimaryText}>{needsAddress ? 'Add delivery address' : (total > 0 ? `Pay by card · ${money(total)}` : 'Place order')}</Text></>}
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
  pickupCard: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 12 },
  fulRow: { flexDirection: 'row', gap: 6, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, padding: 4 },
  fulBtn: { flex: 1, paddingVertical: 8, borderRadius: RADIUS.full, alignItems: 'center' },
  fulBtnOn: { backgroundColor: COLORS.card },
  fulText: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '900' },
  fulTextOn: { color: COLORS.text },
  pickupLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '900', letterSpacing: 0.5, textTransform: 'uppercase', marginTop: 12, marginBottom: 8 },
  timePill: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.cardBorder, flexShrink: 0 },
  timePillOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  timePillText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800' },
  etaRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 },
  etaText: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900' },
  feeBlock: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginTop: 10, gap: 6 },
  feeRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  feeLabel: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  feeVal: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: 12, marginBottom: 8 },
  name: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  opts: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  entLine: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900', marginTop: 2 },
  noteLine: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700', fontStyle: 'italic', marginTop: 2 },
  rowActions: { alignItems: 'flex-end', gap: 8 },
  bookmarkBtn: { width: 30, height: 30, borderRadius: 15, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  comboRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.green + '14', borderRadius: RADIUS.md, padding: 12, marginTop: 10 },
  comboText: { flex: 1, color: COLORS.green, fontSize: FONT.sm, fontWeight: '900' },
  comboVal: { color: COLORS.green, fontSize: FONT.sm, fontWeight: '900' },
  savedShelf: { marginTop: 12, borderTopWidth: 1, borderTopColor: COLORS.surfaceBorder, paddingTop: 12 },
  savedTitle: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '900', marginBottom: 8 },
  savedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  savedName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  savedPrice: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  savedAdd: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  savedAddText: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900' },
  undoBanner: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.text, marginHorizontal: SPACING.md, marginTop: 10, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 10 },
  undoText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800' },
  undoBtn: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  price: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900', marginTop: 4 },
  entDiscRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary + '12', borderRadius: RADIUS.md, padding: 12, marginTop: 10 },
  entDiscText: { flex: 1, color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  entDiscVal: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '900' },
  nudge: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: COLORS.primary + '12', borderWidth: 1, borderColor: COLORS.primary + '44', borderRadius: RADIUS.md, padding: 12, marginTop: 10 },
  nudgeTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  nudgeSub: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  nudgeCta: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '900' },
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
