// Gift Card Market — buy or gift local venue gift cards with points or card.
import React, { useEffect, useState, useRef, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, Animated,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as WebBrowser from 'expo-web-browser';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

interface Product {
  product_id: string; sponsor_name: string; category: string;
  denominations_cents: number[]; points_per_dollar: number;
  allow_points: boolean; allow_card: boolean;
}
interface Card {
  card_id: string; code: string; sponsor_name?: string;
  amount_cents: number; balance_cents: number; status: string;
  gifted_to_email?: string | null; revealed?: boolean;
  thanks_sent?: boolean; received_gift?: boolean; message?: string | null;
}

const CAT_ICON: Record<string, string> = {
  cafe: 'cafe', restaurant: 'restaurant', wellness: 'flower', retail: 'bag-handle',
};
const money = (c: number) => `$${(c / 100).toFixed(0)}`;

export default function GiftCards() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [tab, setTab] = useState<'shop' | 'mine'>('shop');
  const [products, setProducts] = useState<Product[]>([]);
  const [balance, setBalance] = useState(0);
  const [ppd, setPpd] = useState(100);
  const [mine, setMine] = useState<Card[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // per-card selection state
  const [openId, setOpenId] = useState<string | null>(null);
  const [amount, setAmount] = useState<number>(0);
  const [method, setMethod] = useState<'points' | 'card'>('points');
  const [giftEmail, setGiftEmail] = useState('');
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const [cat, m] = await Promise.all([
        api.get('/giftcards/catalog'),
        api.get('/giftcards/mine').catch(() => ({ data: { items: [] } })),
      ]);
      setProducts(cat.data.items || []);
      setBalance(cat.data.points_balance || 0);
      setPpd(cat.data.points_per_dollar || 100);
      setMine(m.data.items || []);
    } catch { /* unauth */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const openBuy = (p: Product) => {
    setOpenId(p.product_id);
    setAmount(p.denominations_cents[0] || 0);
    setMethod(p.allow_points ? 'points' : 'card');
    setGiftEmail(''); setMessage('');
  };

  const pointsCost = Math.round((amount / 100) * ppd);
  const canAfford = balance >= pointsCost;

  const buy = async (p: Product) => {
    if (!amount) return;
    if (method === 'points' && !canAfford) return;
    setBusy(true);
    try {
      const r = await api.post('/giftcards/purchase', {
        product_id: p.product_id,
        amount_cents: amount,
        method,
        gift_to_email: giftEmail.trim() || null,
        message: message.trim() || null,
        origin_url: process.env.EXPO_PUBLIC_BACKEND_URL,
      });
      if (r.data.method === 'card' && r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
      } else if (r.data.method === 'points') {
        celebrate({
          points: 0,
          title: giftEmail.trim()
            ? `Gift card sent to ${giftEmail.trim()}!`
            : `${money(amount)} gift card added!`,
        });
      }
      setOpenId(null);
      await load();
    } catch (e: any) {
      const code = e?.response?.data?.detail?.code;
      celebrate({ points: 0, title: code === 'insufficient_points' ? 'Not enough BigCoin' : 'Purchase failed' });
    } finally { setBusy(false); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="gc-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Gift Cards</Text>
        <View style={s.balPill}>
          <Text style={s.balGlyph}>₿</Text>
          <Text style={s.balText} testID="gc-balance">{balance}</Text>
        </View>
      </View>

      <View style={s.tabs}>
        <TouchableOpacity style={[s.tab, tab === 'shop' && s.tabOn]} onPress={() => setTab('shop')} testID="gc-tab-shop">
          <Text style={[s.tabText, tab === 'shop' && s.tabTextOn]}>Shop</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[s.tab, tab === 'mine' && s.tabOn]} onPress={() => setTab('mine')} testID="gc-tab-mine">
          <Text style={[s.tabText, tab === 'mine' && s.tabTextOn]}>My Cards{mine.length ? ` (${mine.length})` : ''}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}
        testID="giftcards-root">

        {tab === 'shop' && (
          <>
            <Text style={s.intro}>Buy or gift a local venue gift card with BigCoin or your card.</Text>
            {products.map((p) => {
              const open = openId === p.product_id;
              return (
                <View key={p.product_id} style={s.card} testID={`gc-product-${p.product_id}`}>
                  <View style={s.head}>
                    <View style={s.vIcon}>
                      <Ionicons name={(CAT_ICON[p.category] || 'gift') as any} size={20} color={COLORS.primary} />
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <Text style={s.title} numberOfLines={1}>{p.sponsor_name}</Text>
                      <Text style={s.sub}>{p.category}</Text>
                    </View>
                  </View>

                  {!open ? (
                    <TouchableOpacity style={s.bookBtn} onPress={() => openBuy(p)} testID={`gc-open-${p.product_id}`}>
                      <Ionicons name="gift-outline" size={16} color={COLORS.primary} />
                      <Text style={s.bookText}>Buy or gift</Text>
                    </TouchableOpacity>
                  ) : (
                    <View>
                      <Text style={s.label}>AMOUNT</Text>
                      <View style={s.slotRow}>
                        {p.denominations_cents.map((d) => (
                          <TouchableOpacity key={d} testID={`gc-amt-${p.product_id}-${d}`}
                            style={[s.slot, amount === d && s.slotOn]} onPress={() => setAmount(d)}>
                            <Text style={[s.slotText, amount === d && s.slotTextOn]}>{money(d)}</Text>
                          </TouchableOpacity>
                        ))}
                      </View>

                      <Text style={s.label}>PAY WITH</Text>
                      <View style={s.slotRow}>
                        {p.allow_points && (
                          <TouchableOpacity testID={`gc-method-points-${p.product_id}`}
                            style={[s.slot, method === 'points' && s.slotOn]} onPress={() => setMethod('points')}>
                            <Text style={[s.slotText, method === 'points' && s.slotTextOn]}>₿ {pointsCost} BigCoin</Text>
                          </TouchableOpacity>
                        )}
                        {p.allow_card && (
                          <TouchableOpacity testID={`gc-method-card-${p.product_id}`}
                            style={[s.slot, method === 'card' && s.slotOn]} onPress={() => setMethod('card')}>
                            <Text style={[s.slotText, method === 'card' && s.slotTextOn]}>Card {money(amount)}</Text>
                          </TouchableOpacity>
                        )}
                      </View>
                      {method === 'points' && !canAfford && (
                        <TouchableOpacity style={s.topupNudge}
                          onPress={() => router.push({ pathname: '/bigcoin-topup', params: { needed: String(pointsCost - balance) } })}
                          testID={`gc-topup-${p.product_id}`}>
                          <Ionicons name="add-circle" size={16} color={COLORS.primary} />
                          <Text style={s.topupText}>Need {pointsCost - balance} more — buy BigCoin</Text>
                          <Ionicons name="chevron-forward" size={14} color={COLORS.primary} />
                        </TouchableOpacity>
                      )}

                      <Text style={s.label}>GIFT TO (OPTIONAL)</Text>
                      <TextInput style={s.input} value={giftEmail} onChangeText={setGiftEmail}
                        keyboardType="email-address" autoCapitalize="none"
                        placeholder="friend@email.com — leave blank to keep it"
                        placeholderTextColor={COLORS.textMuted} testID={`gc-email-${p.product_id}`} />
                      {!!giftEmail.trim() && (
                        <TextInput style={[s.input, { marginTop: 8 }]} value={message} onChangeText={setMessage}
                          placeholder="Add a message" placeholderTextColor={COLORS.textMuted}
                          testID={`gc-msg-${p.product_id}`} />
                      )}

                      <TouchableOpacity
                        style={[common.btnPrimary, { marginTop: 12 }, (method === 'points' && !canAfford) && { opacity: 0.5 }]}
                        onPress={() => buy(p)} disabled={busy || (method === 'points' && !canAfford)}
                        testID={`gc-buy-${p.product_id}`}>
                        {busy ? <ActivityIndicator color="#fff" />
                          : <><Ionicons name="card" size={16} color="#fff" />
                            <Text style={common.btnPrimaryText}>
                              {method === 'points' ? `Redeem ${pointsCost} BigCoin` : `Pay ${money(amount)}`}
                            </Text></>}
                      </TouchableOpacity>
                    </View>
                  )}
                </View>
              );
            })}
          </>
        )}

        {tab === 'mine' && (
          <>
            {mine.length === 0 && (
              <View style={s.card}>
                <Ionicons name="gift-outline" size={28} color={COLORS.textMuted} />
                <Text style={s.empty}>No gift cards yet. Buy one from the Shop tab.</Text>
              </View>
            )}
            {mine.map((c) => (
              <GiftCardRow key={c.card_id} card={c} onReveal={load} onThanks={load} />
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function GiftCardRow({ card, onReveal, onThanks }: {
  card: Card; onReveal: () => void; onThanks: () => void;
}) {
  const [revealed, setRevealed] = useState(!!card.revealed);
  const [thanksSent, setThanksSent] = useState(!!card.thanks_sent);
  const [busy, setBusy] = useState(false);
  const cover = useRef(new Animated.Value(revealed ? 0 : 1)).current;
  const isGift = !!card.received_gift;

  // Redeem state — balance ticks down with an animation.
  const [balance, setBalance] = useState(card.balance_cents);
  const [displayBal, setDisplayBal] = useState(card.balance_cents);
  const [status, setStatus] = useState(card.status);
  const [redeemOpen, setRedeemOpen] = useState(false);
  const [amount, setAmount] = useState('');
  const animBal = useRef(new Animated.Value(card.balance_cents)).current;

  const scratch = async () => {
    if (busy) return;
    setBusy(true);
    Animated.timing(cover, { toValue: 0, duration: 550, useNativeDriver: true }).start();
    try { await api.post(`/giftcards/${card.card_id}/reveal`); setRevealed(true); onReveal(); }
    catch { /* ignore */ }
    finally { setBusy(false); }
  };

  const sendThanks = async () => {
    setBusy(true);
    try { await api.post(`/giftcards/${card.card_id}/thanks`, { message: 'Thank you so much for the gift!' }); setThanksSent(true); onThanks(); }
    catch { /* ignore */ }
    finally { setBusy(false); }
  };

  const redeem = async () => {
    const cents = Math.round(parseFloat(amount || '0') * 100);
    if (!cents || cents > balance) return;
    setBusy(true);
    try {
      const r = await api.post(`/giftcards/${card.card_id}/redeem`, { amount_cents: cents });
      const nb = r.data.balance_cents ?? (balance - cents);
      // Tick the balance down.
      const id = animBal.addListener(({ value }) => setDisplayBal(Math.round(value)));
      Animated.timing(animBal, { toValue: nb, duration: 700, useNativeDriver: false })
        .start(() => { animBal.removeListener(id); setDisplayBal(nb); });
      setBalance(nb);
      setStatus(r.data.status || (nb > 0 ? 'active' : 'spent'));
      setRedeemOpen(false); setAmount('');
    } catch { /* ignore */ }
    finally { setBusy(false); }
  };

  return (
    <View style={s.card} testID={`gc-mine-${card.card_id}`}>
      <View style={s.head}>
        <View style={s.vIcon}><Ionicons name="gift" size={20} color={COLORS.primary} /></View>
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.title} numberOfLines={1}>{card.sponsor_name || 'Gift Card'}</Text>
          <Text style={s.sub}>{revealed ? card.code : (isGift ? 'A gift for you!' : card.code)}</Text>
        </View>
        <Text style={[s.bal, displayBal === 0 && { color: COLORS.textMuted }]} testID={`gc-balance-${card.card_id}`}>
          {money(displayBal)}
        </Text>
      </View>

      {isGift && !revealed ? (
        <View style={s.scratchWrap}>
          {!!card.message && <Text style={s.giftMsg}>“{card.message}”</Text>}
          <Animated.View style={[s.scratchCover, { opacity: cover }]} pointerEvents="none">
            <Ionicons name="sparkles" size={20} color="#fff" />
            <Text style={s.scratchText}>Tap to scratch &amp; reveal</Text>
          </Animated.View>
          <TouchableOpacity style={s.scratchHit} onPress={scratch}
            disabled={busy} testID={`gc-scratch-${card.card_id}`} />
        </View>
      ) : (
        <>
          <Text style={s.mineMeta}>
            {money(card.amount_cents)} value · {status}
            {card.gifted_to_email ? ` · gifted to ${card.gifted_to_email}` : ''}
          </Text>

          {redeemOpen ? (
            <View>
              <Text style={s.label}>SPEND AT CHECKOUT ($)</Text>
              <View style={s.redeemRow}>
                <TextInput style={[s.input, { flex: 1 }]} value={amount} onChangeText={setAmount}
                  keyboardType="decimal-pad" placeholder={`up to ${money(balance)}`}
                  placeholderTextColor={COLORS.textMuted} testID={`gc-redeem-amt-${card.card_id}`} />
                <TouchableOpacity style={s.redeemConfirm} onPress={redeem}
                  disabled={busy} testID={`gc-redeem-confirm-${card.card_id}`}>
                  {busy ? <ActivityIndicator color="#fff" />
                    : <Text style={s.redeemConfirmText}>Redeem</Text>}
                </TouchableOpacity>
              </View>
              <TouchableOpacity onPress={() => { setRedeemOpen(false); setAmount(''); }} style={{ alignSelf: 'center', marginTop: 8, padding: 4 }}>
                <Text style={s.linkText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <View style={s.mineActions}>
              {balance > 0 && (
                <TouchableOpacity style={s.redeemBtn} onPress={() => setRedeemOpen(true)}
                  testID={`gc-redeem-${card.card_id}`}>
                  <Ionicons name="cart-outline" size={15} color="#fff" />
                  <Text style={s.redeemText}>Redeem</Text>
                </TouchableOpacity>
              )}
              {isGift && (
                thanksSent ? (
                  <View style={s.thanksDone} testID={`gc-thanks-done-${card.card_id}`}>
                    <Ionicons name="heart" size={14} color={COLORS.primary} />
                    <Text style={s.thanksDoneText}>Thanks sent</Text>
                  </View>
                ) : (
                  <TouchableOpacity style={s.thanksBtn} onPress={sendThanks} disabled={busy}
                    testID={`gc-thanks-${card.card_id}`}>
                    <Ionicons name="heart-outline" size={15} color={COLORS.primary} />
                    <Text style={s.thanksText}>Send thanks</Text>
                  </TouchableOpacity>
                )
              )}
            </View>
          )}
        </>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  topbar: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  balPill: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '22', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  balGlyph: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  balText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  tabs: { flexDirection: 'row', gap: 8, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm },
  tab: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  tabOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  tabText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '800' },
  tabTextOn: { color: '#fff' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: SPACING.sm },
  vIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  title: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  sub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1, textTransform: 'capitalize' },
  bal: { color: COLORS.green, fontSize: FONT.md, fontWeight: '900' },
  mineMeta: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  label: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.2, marginTop: SPACING.sm, marginBottom: 6 },
  slotRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  slot: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  slotOn: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  slotText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  slotTextOn: { color: '#fff' },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.surfaceBorder, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  bookBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 12, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10' },
  bookText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  warn: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700', marginTop: 6 },
  topupNudge: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 8, paddingVertical: 8, paddingHorizontal: 10, borderRadius: RADIUS.md, backgroundColor: COLORS.primary + '10', borderWidth: 1, borderColor: COLORS.primary + '44' },
  topupText: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800', flex: 1 },
  scratchWrap: { marginTop: 4, borderRadius: RADIUS.md, overflow: 'hidden', minHeight: 56, justifyContent: 'center', backgroundColor: COLORS.inputBg },
  giftMsg: { color: COLORS.textDim, fontSize: FONT.sm, fontStyle: 'italic', padding: 12 },
  scratchCover: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary },
  scratchText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  scratchHit: { position: 'absolute', left: 0, right: 0, top: 0, bottom: 0 },
  thanksBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', marginTop: 10, paddingVertical: 8, paddingHorizontal: 14, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.primary, backgroundColor: COLORS.primary + '10' },
  thanksText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  thanksDone: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  thanksDoneText: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '800' },
  mineActions: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 10, flexWrap: 'wrap' },
  redeemBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 9, paddingHorizontal: 16, borderRadius: RADIUS.full, backgroundColor: COLORS.primary },
  redeemText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800' },
  redeemRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  redeemConfirm: { backgroundColor: COLORS.primary, paddingHorizontal: 18, paddingVertical: 12, borderRadius: RADIUS.md, minWidth: 84, alignItems: 'center' },
  redeemConfirmText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  linkText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  empty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 8 },
});
