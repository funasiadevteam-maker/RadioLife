import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, RefreshControl, LayoutAnimation, Platform, UIManager, Animated,
  Modal, TextInput,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import AdBanner from '../../src/components/AdBanner';
import api from '../../src/api/client';
import { useAuth } from '../../src/contexts/AuthContext';
import useBigCoinStore from '../../src/stores/useBigCoinStore';

const TABS = [
  { id: 'overview', label: 'Overview', icon: 'wallet' as const },
  { id: 'balance', label: 'Activity', icon: 'list' as const },
  { id: 'rewards', label: 'Rewards', icon: 'gift' as const },
  { id: 'badges', label: 'Badges', icon: 'ribbon' as const },
  { id: 'refer', label: 'Refer', icon: 'share-social' as const },
];
const TIER_ICONS: Record<string, string> = { bronze: '🥉', silver: '🥈', gold: '🥇', platinum: '💎' };
function prettySource(s: string) {
  const m: Record<string, string> = {
    listening: '🎧 Listening', onboarding: '🎉 Welcome bonus', streak: '🔥 Streak',
    streak_milestone: '🏆 Streak milestone', low_skip_bonus: '🎵 No-skip',
    referral: '✉️ Referral', ad_click: '📣 Ad click', ad_save: '🎟️ Coupon saved',
    ad_redemption: '✅ Coupon redeemed', game_win: '🎮 Game win', redemption: '🛍️ Redeemed',
    admin_adjust: '⚙️ Admin', ambassador_level_up: '⭐ Ambassador',
  };
  return m[s] || s;
}

function fmtBal(c: number, cur?: string) {
  const amt = ((c || 0) / 100).toFixed(2);
  return (!cur || cur === 'USD') ? `$${amt}` : `${cur} ${amt}`;
}

function MyGiftCards() {
  const [cards, setCards] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  useEffect(() => {
    let alive = true;
    api.get('/wallet/me')
      .then((r) => { if (alive) setCards(r.data?.gift_cards || []); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);
  const applySpend = (remaining: number, status: string) => {
    setCards((prev) => prev.map((c) => c.gift_card_id === selected?.gift_card_id
      ? { ...c, current_balance_cents: remaining, status: status || c.status } : c));
  };
  if (!cards.length) return null;
  return (
    <View style={st.gcSection} testID="wallet-giftcards">
      <Text style={st.gcHeading}>My Gift Cards</Text>
      {cards.map((g) => (
        <TouchableOpacity key={g.code} style={st.gcCard} testID="wallet-giftcard-row"
          activeOpacity={0.85} onPress={() => setSelected(g)}>
          <LinearGradient colors={['#F59E0B', '#EC4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.gcArt}>
            <Ionicons name="gift" size={22} color="#fff" />
          </LinearGradient>
          <View style={{ flex: 1, minWidth: 0 }}>
            <Text style={st.gcName} numberOfLines={1}>{g.merchant_name || 'Gift card'}</Text>
            <Text style={st.gcCode} testID="wallet-giftcard-code">{g.code}</Text>
            <Text style={st.gcTapHint}>Tap to spend →</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={st.gcBalance} testID="wallet-giftcard-balance">{fmtBal(g.current_balance_cents, g.currency)}</Text>
            <Text style={st.gcBalanceLabel}>balance</Text>
          </View>
        </TouchableOpacity>
      ))}
      <GiftCardSpendModal card={selected} onClose={() => setSelected(null)} onSpent={applySpend} />
    </View>
  );
}

function GiftCardSpendModal({ card, onClose, onSpent }: { card: any; onClose: () => void; onSpent: (remaining: number, status: string) => void }) {
  const [amt, setAmt] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { setAmt(''); setResult(null); setErr(null); }, [card]);
  if (!card) return null;
  const ccy = card.currency || 'USD';
  const balance = result ? result.remaining_cents : card.current_balance_cents;
  const depleted = card.status === 'depleted' || (balance || 0) <= 0;
  const spend = async () => {
    const cents = Math.round(parseFloat(amt || '0') * 100);
    if (!cents || cents <= 0) { setErr('Enter an amount to spend'); return; }
    setBusy(true); setErr(null);
    try {
      const { data } = await api.post('/games/gift-card/spend', { code: card.code, amount_cents: cents });
      setResult(data);
      setAmt('');
      onSpent(data.remaining_cents, data.status);
    } catch (e: any) {
      const c = e?.response?.data?.detail?.code || e?.response?.data?.code;
      setErr(c === 'depleted' ? 'Card is empty'
        : c === 'not_your_card' ? "This isn't your card"
        : c === 'card_not_found' ? 'Card not found' : 'Spend failed');
    } finally { setBusy(false); }
  };
  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <TouchableOpacity style={st.gcModalOverlay} activeOpacity={1} onPress={onClose}>
        <TouchableOpacity activeOpacity={1} style={st.gcModalCard} testID="wallet-gc-spend-modal">
          <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled"
            contentContainerStyle={{ gap: SPACING.sm }}>
          <View style={st.gcModalHead}>
            <View style={{ flex: 1 }}>
              <Text style={st.gcModalTitle}>{card.merchant_name || 'Gift card'}</Text>
              <Text style={st.gcModalCode}>{card.code}</Text>
            </View>
            <TouchableOpacity onPress={onClose} testID="wallet-gc-spend-close" style={{ padding: 4 }}>
              <Ionicons name="close" size={22} color={COLORS.textMuted} />
            </TouchableOpacity>
          </View>

          <View style={st.gcModalBalanceBox}>
            <Text style={st.gcModalBalanceLabel}>BALANCE</Text>
            <Text style={st.gcModalBalance} testID="wallet-gc-spend-balance">{fmtBal(balance, ccy)}</Text>
          </View>

          {depleted ? (
            <Text style={st.gcModalDepleted} testID="wallet-gc-spend-depleted">This gift card has no balance left.</Text>
          ) : (
            <>
              <Text style={st.gcModalInputLabel}>SPEND AT THE COUNTER</Text>
              <View style={st.gcModalInputRow}>
                <View style={st.gcModalInputWrap}>
                  <Text style={st.gcModalCurrency}>{ccy === 'USD' ? '$' : ccy}</Text>
                  <TextInput
                    value={amt}
                    onChangeText={setAmt}
                    placeholder="0.00"
                    placeholderTextColor={COLORS.textMuted}
                    keyboardType="decimal-pad"
                    style={st.gcModalInput}
                    testID="wallet-gc-spend-amount"
                  />
                </View>
                <TouchableOpacity style={st.gcModalSpendBtn} onPress={spend} disabled={busy} testID="wallet-gc-spend-btn">
                  {busy ? <ActivityIndicator color="#fff" size="small" /> : <Text style={st.gcModalSpendTxt}>Spend</Text>}
                </TouchableOpacity>
              </View>
              <Text style={st.gcModalHint}>We charge up to what's left on the card.</Text>
            </>
          )}

          {err && <Text style={st.gcModalErr} testID="wallet-gc-spend-err">{err}</Text>}

          {result && (
            <View style={st.gcModalResult} testID="wallet-gc-spend-result">
              <Ionicons name="checkmark-circle" size={16} color={COLORS.green} />
              <Text style={st.gcModalResultTxt}>
                Charged {fmtBal(result.charged_cents, ccy)} · {fmtBal(result.remaining_cents, ccy)} left
                {result.shortfall_cents > 0 ? ` · ${fmtBal(result.shortfall_cents, ccy)} still owed` : ''}
              </Text>
            </View>
          )}
          </ScrollView>
        </TouchableOpacity>
      </TouchableOpacity>
    </Modal>
  );
}

export default function WalletScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [tab, setTab] = useState('overview');
  const [me, setMe] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const reloadMe = useCallback(async () => {
    try {
      const r = await api.get('/bigcoin/me');
      setMe(r.data);
      // Keep the shared BigCoin store (Games hub chip, reward modals) in sync.
      useBigCoinStore.setState({
        balance: Number(r.data?.balance) || 0,
        lifetime: Number(r.data?.lifetime_earned) || 0,
        tier: r.data?.tier ?? null,
        tierLabel: r.data?.tier_label ?? null,
        streakDays: Number(r.data?.streak_days) || 0,
        loaded: true,
      });
    }
    catch (e: any) { if (e?.response?.status === 401) router.replace('/login'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (!authLoading && user) reloadMe(); }, [reloadMe, authLoading, user]);

  /* Re-read the balance every time the tab regains focus so a BigCoin win
     from the Games tab shows up immediately (tabs stay mounted, so a
     plain mount effect is not enough). */
  useFocusEffect(
    useCallback(() => {
      if (!authLoading && user) reloadMe();
    }, [authLoading, user, reloadMe]),
  );
  const onRefresh = async () => { setRefreshing(true); await reloadMe(); setRefreshing(false); };

  if (authLoading || loading) return <View style={st.loadWrap} testID="wallet-loading"><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={st.container} testID="wallet-screen">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}>
        <View style={st.header}>
          <Text style={st.headerTitle}>BigCoin Wallet</Text>
          <Text style={st.headerSub}>Earn by listening · Spend on rewards · Refer friends</Text>
        </View>

        {/* Points hero card */}
        <LinearGradient
          colors={['#F26B2A', '#F59E0B']}
          start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
          style={st.pointsCard} testID="balance-card"
        >
          <View style={st.pointsTop}>
            <View style={{ flex: 1 }}>
              <Text style={st.pointsLabel}>TOTAL BIGCOIN BALANCE</Text>
              <View style={st.pointsAmountRow}>
                <Text style={st.pointsGlyph}>₿</Text>
                <Text style={st.pointsAmount} testID="bc-balance">{me?.balance ?? 0}</Text>
              </View>
            </View>
            <View style={st.tierPill} testID="bc-tier">
              <Text style={st.tierPillText}>{TIER_ICONS[me?.tier] || '🥉'} {me?.tier_label || me?.tier || 'Bronze'}</Text>
            </View>
          </View>
          <View style={st.pointsMetaRow}>
            <Text style={st.pointsMeta}>🔥 {me?.streak_days || 0}-day streak</Text>
            <Text style={st.pointsMeta} testID="bc-lifetime">Lifetime {me?.lifetime_earned || 0} BC</Text>
          </View>
          {me?.next_milestone ? (
            <View style={st.pointsProgressWrap}>
              <View style={st.pointsProgressBar}>
                <View style={[st.pointsProgressFill, { width: `${Math.min(100, me?.milestone_progress || 0)}%` }]} />
              </View>
              <Text style={st.pointsProgressHint}>
                {(() => {
                  const TIERS = [{ name: 'Silver', min: 500 }, { name: 'Gold', min: 2500 }, { name: 'Platinum', min: 10000 }];
                  const life = me.lifetime_earned || 0;
                  const nt = TIERS.find(t => t.min > life);
                  return nt ? `${nt.min - life} BC to ${nt.name}` : 'Platinum tier — top rank reached 🎉';
                })()}
              </Text>
            </View>
          ) : null}
        </LinearGradient>

        {/* Sponsored banner */}
        <AdBanner zone="wallet" />

        {/* Gift Inbox — gifts received */}
        <GiftInbox router={router} />

        {/* My Gift Cards — won in games */}
        <MyGiftCards />

        {/* Action Buttons */}
        <View style={st.actionRow}>
          <TouchableOpacity style={st.actionBtn} onPress={() => router.push('/scan-to-pay')} testID="wallet-scan-to-pay-btn">
            <View style={st.actionIcon}>
              <Ionicons name="qr-code" size={20} color={COLORS.primary} />
            </View>
            <Text style={st.actionLabel}>Scan to Pay</Text>
          </TouchableOpacity>
          <TouchableOpacity style={st.actionBtn} onPress={() => router.push('/my-splits')} testID="wallet-my-splits-btn">
            <View style={st.actionIcon}>
              <Ionicons name="people" size={20} color={COLORS.secondary} />
            </View>
            <Text style={st.actionLabel}>My Splits</Text>
          </TouchableOpacity>
          <TouchableOpacity style={st.actionBtn} onPress={() => router.push('/coupons')} testID="wallet-deals-btn">
            <View style={st.actionIcon}>
              <Ionicons name="pricetag" size={20} color={COLORS.green} />
            </View>
            <Text style={st.actionLabel}>Deals</Text>
          </TouchableOpacity>
          <TouchableOpacity style={st.actionBtn} onPress={() => router.push('/giftcards')} testID="wallet-giftcards-btn">
            <View style={st.actionIcon}>
              <Ionicons name="gift" size={20} color={COLORS.gold} />
            </View>
            <Text style={st.actionLabel}>Gift Cards</Text>
          </TouchableOpacity>
          <TouchableOpacity style={st.actionBtn} onPress={() => router.push('/bookings')} testID="wallet-bookings-btn">
            <View style={st.actionIcon}>
              <Ionicons name="calendar" size={20} color={COLORS.primary} />
            </View>
            <Text style={st.actionLabel}>Bookings</Text>
          </TouchableOpacity>
          <TouchableOpacity style={st.actionBtn} onPress={() => router.push('/bigcoin-topup')} testID="wallet-topup-btn">
            <View style={st.actionIcon}>
              <Ionicons name="add-circle" size={20} color={COLORS.gold} />
            </View>
            <Text style={st.actionLabel}>Top Up</Text>
          </TouchableOpacity>
        </View>

        {/* Tabs */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: SPACING.md }}>
          <View style={st.tabs} testID="wallet-tabs">
            {TABS.map(t => (
              <TouchableOpacity key={t.id} style={[st.tab, tab === t.id && st.tabActive]}
                onPress={() => setTab(t.id)} testID={`tab-${t.id}`}>
                <Ionicons name={t.icon} size={13} color={tab === t.id ? COLORS.primary : COLORS.textDim} />
                <Text style={[st.tabText, tab === t.id && st.tabTextActive]}>{t.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>

        {tab === 'overview' && <OverviewTab me={me} router={router} />}
        {tab === 'balance' && <BalanceTab />}
        {tab === 'rewards' && <RewardsTab me={me} onRedeemed={reloadMe} />}
        {tab === 'badges' && <BadgesTab />}
        {tab === 'refer' && <ReferTab me={me} />}
      </ScrollView>
    </SafeAreaView>
  );
}

/* ── Overview (Coupons + Wallet Items + Redemption History) ── */
function OverviewTab({ me, router }: { me: any; router: any }) {
  const [coupons, setCoupons] = useState<any[]>([]);
  const [walletItems, setWalletItems] = useState<any[]>([]);
  const [redemptions, setRedemptions] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const [c, w, r] = await Promise.all([
          api.get('/commerce/coupons/me').catch(() => ({ data: { items: [] } })),
          api.get('/wallet/items').catch(() => ({ data: { items: [] } })),
          api.get('/bigcoin/redemptions').catch(() => ({ data: { items: [] } })),
        ]);
        setCoupons(c.data.items || []);
        setWalletItems(w.data.items || []);
        setRedemptions(r.data.items || []);
      } catch {}
      finally { setLoading(false); }
    })();
  }, []);

  if (loading) return <ActivityIndicator size="small" color={COLORS.primary} />;

  return (
    <View testID="tab-overview-content">
      {/* Saved Coupons */}
      <Text style={st.sectionTitle}>Saved Coupons</Text>
      {coupons.length === 0 ? (
        <View style={st.emptyCard} testID="coupons-empty">
          <Ionicons name="pricetag" size={24} color={COLORS.textDim} />
          <Text style={st.emptyText}>No coupons yet. Browse local offers to claim.</Text>
        </View>
      ) : coupons.slice(0, 5).map(c => {
        const cId = c.coupon_id || c.id;
        const isActive = c.status === 'claimed';
        const isRedeemed = c.status === 'redeemed';
        const isExpired = c.status === 'expired';
        const remainMin = c.expires_at ? Math.max(0, Math.floor((new Date(c.expires_at).getTime() - Date.now()) / 60000)) : null;
        return (
          <TouchableOpacity key={cId} style={st.couponRow}
            onPress={() => router.push(`/coupon/${cId}`)} testID={`coupon-row-${cId}`}
            activeOpacity={0.7}>
            <Ionicons name="qr-code" size={20} color={isActive ? COLORS.green : isRedeemed ? COLORS.purple : COLORS.textDim} />
            <View style={{ flex: 1, marginLeft: 10 }}>
              {c.business_name ? <Text style={st.couponBiz}>{c.business_name}</Text> : null}
              <Text style={st.couponCode}>{c.offer_title || c.redemption_code}</Text>
              <Text style={st.couponMeta}>
                {c.claim_source?.replace(/_/g, ' ')}
                {' · '}
                {isActive ? (remainMin != null ? `${remainMin}m left` : 'Active')
                  : isRedeemed ? 'Redeemed'
                  : isExpired ? 'Expired'
                  : c.status}
                {c.expires_at && isActive ? ` · exp ${new Date(c.expires_at).toLocaleDateString()}` : ''}
              </Text>
            </View>
            <View style={st.couponStatusBadge}>
              {isActive && <View style={[st.statusDot, { backgroundColor: COLORS.green }]} />}
              {isRedeemed && <View style={[st.statusDot, { backgroundColor: COLORS.purple }]} />}
              {isExpired && <View style={[st.statusDot, { backgroundColor: COLORS.red }]} />}
              <Ionicons name="chevron-forward" size={14} color={COLORS.textDim} />
            </View>
          </TouchableOpacity>
        );
      })}

      {/* Browse Local Offers CTA */}
      <TouchableOpacity style={st.browseOffersCta} onPress={() => router.push('/coupons')}
        testID="browse-local-offers-btn" activeOpacity={0.7}>
        <Ionicons name="storefront" size={18} color={COLORS.primary} />
        <View style={{ flex: 1, marginLeft: 10 }}>
          <Text style={st.browseOffersTitle}>Browse Local Offers</Text>
          <Text style={st.browseOffersSub}>Deals from businesses near you — claim & redeem in-store</Text>
        </View>
        <Ionicons name="chevron-forward" size={16} color={COLORS.primary} />
      </TouchableOpacity>

      {/* Tickets / Wallet Items */}
      <Text style={[st.sectionTitle, { marginTop: SPACING.lg }]}>Tickets & Passes</Text>
      {walletItems.length === 0 ? (
        <View style={st.emptyCard} testID="tickets-empty">
          <Ionicons name="ticket" size={24} color={COLORS.textDim} />
          <Text style={st.emptyText}>No tickets or passes yet.</Text>
        </View>
      ) : walletItems.slice(0, 5).map(w => (
        <View key={w.wallet_item_id} style={st.walletItemRow} testID={`wallet-item-${w.wallet_item_id}`}>
          <Ionicons name={w.status === 'redeemed' ? 'checkmark-circle' : 'ticket'} size={16}
            color={w.status === 'redeemed' ? COLORS.purple : COLORS.gold} />
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={st.walletItemTitle}>{w.title}</Text>
            <Text style={st.walletItemMeta}>{w.value_amount} {w.value_unit} · {w.status}{w.redeemed_at ? ` · ${new Date(w.redeemed_at).toLocaleDateString()}` : ''}</Text>
          </View>
          {w.qr_token && <Ionicons name="qr-code" size={14} color={COLORS.textDim} />}
        </View>
      ))}

      {/* Redemption History */}
      <Text style={[st.sectionTitle, { marginTop: SPACING.lg }]}>Redemption History</Text>
      {redemptions.length === 0 ? (
        <View style={st.emptyCard} testID="redemptions-empty">
          <Ionicons name="gift" size={24} color={COLORS.textDim} />
          <Text style={st.emptyText}>No redemptions yet.</Text>
        </View>
      ) : redemptions.slice(0, 10).map(r => (
        <View key={r.redemption_id} style={st.redemptionRow} testID={`redemption-${r.redemption_id}`}>
          <View style={{ flex: 1 }}>
            <Text style={st.redemptionName}>{r.reward_name}</Text>
            <Text style={st.redemptionMeta}>{r.reward_type} · {new Date(r.redeemed_at).toLocaleDateString()}</Text>
          </View>
          <Text style={st.redemptionCost}>-{r.cost_paid} BC</Text>
        </View>
      ))}
    </View>
  );
}

/* ── Balance / Activity Tab ── */
function BalanceTab() {
  const [txns, setTxns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    (async () => {
      try { const r = await api.get('/bigcoin/transactions?limit=50'); setTxns(r.data.items || []); }
      catch {} finally { setLoading(false); }
    })();
  }, []);
  return (
    <View testID="tab-balance-content">
      <Text style={st.sectionTitle}>Recent Activity</Text>
      {loading && <ActivityIndicator size="small" color={COLORS.primary} />}
      {!loading && txns.length === 0 && <Text style={st.emptyText}>No transactions yet. Start listening to earn BigCoin!</Text>}
      {txns.map(t => (
        <View key={t.id} style={st.txnRow} testID={`txn-${t.id}`}>
          <View style={{ flex: 1 }}>
            <Text style={st.txnSource}>{prettySource(t.source)}</Text>
            <Text style={st.txnDate}>{new Date(t.created_at).toLocaleString()}</Text>
          </View>
          <View style={{ alignItems: 'flex-end' }}>
            <Text style={[st.txnAmount, { color: t.amount > 0 ? COLORS.green : COLORS.red }]}>
              {t.amount > 0 ? '+' : ''}{t.amount} BC
            </Text>
            <Text style={st.txnDate}>→ {t.balance_after}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

/* ── Rewards Tab ── */
function RewardsTab({ me, onRedeemed }: { me: any; onRedeemed: () => void }) {
  const [rewards, setRewards] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [redeeming, setRedeeming] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const r = await api.get('/bigcoin/rewards'); setRewards(r.data.items || []); }
    catch {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const redeem = (id: string, name: string, cost: number) => {
    if ((me?.balance || 0) < cost) return Alert.alert('Not enough', 'You need more BigCoin');
    Alert.alert('Confirm', `Redeem "${name}" for ${cost} BC?`, [
      { text: 'Cancel' },
      { text: 'Redeem', onPress: async () => {
        setRedeeming(id);
        try { await api.post(`/bigcoin/redeem/${id}`); Alert.alert('Success', `Redeemed: ${name}`); onRedeemed(); load(); }
        catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed'); }
        finally { setRedeeming(null); }
      }},
    ]);
  };

  if (loading) return <ActivityIndicator size="small" color={COLORS.primary} />;
  return (
    <View testID="tab-rewards-content">
      {rewards.map(r => {
        const can = (me?.balance || 0) >= r.cost_bigcoin;
        const out = r.stock_left !== null && r.stock_left <= 0;
        return (
          <View key={r.reward_id} style={st.rewardCard} testID={`reward-${r.reward_id}`}>
            <Text style={st.rewardCost}><Ionicons name="wallet" size={11} color={COLORS.gold} /> {r.cost_bigcoin} BC</Text>
            <Text style={st.rewardName}>{r.name}</Text>
            <Text style={st.rewardDesc}>{r.description}</Text>
            {r.stock_left !== null && <Text style={[st.stockText, out && { color: COLORS.red }]}>{out ? 'SOLD OUT' : `${r.stock_left} left`}</Text>}
            <TouchableOpacity style={[st.rewardBtn, (!can || out) && { opacity: 0.4 }]}
              onPress={() => redeem(r.reward_id, r.name, r.cost_bigcoin)}
              disabled={!can || out || redeeming === r.reward_id} testID={`redeem-${r.reward_id}`}>
              {redeeming === r.reward_id ? <ActivityIndicator size="small" color="#fff" /> :
                <Text style={st.rewardBtnText}>{can ? 'Redeem' : `Need ${r.cost_bigcoin - (me?.balance || 0)} more`}</Text>}
            </TouchableOpacity>
          </View>
        );
      })}
    </View>
  );
}

/* ── Badges Tab ── */
function BadgesTab() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { (async () => { try { const r = await api.get('/bigcoin/badges'); setData(r.data); } catch {} })(); }, []);
  if (!data) return <ActivityIndicator size="small" color={COLORS.primary} />;
  return (
    <View testID="tab-badges-content">
      <Text style={st.sectionTitle}>Unlocked <Text style={{ color: COLORS.text }}>{data.unlocked_count}</Text> of {data.total}</Text>
      <View style={st.badgeGrid}>
        {(data.items || []).map((b: any) => (
          <View key={b.badge_id} style={[st.badgeCard, !b.unlocked && { opacity: 0.35 }]} testID={`badge-${b.slug}`}>
            <Text style={st.badgeIcon}>{b.icon || '🏅'}</Text>
            <Text style={st.badgeName}>{b.name}</Text>
            <Text style={st.badgeDesc}>{b.description}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ── Refer Tab ── */
function ReferTab({ me }: { me: any }) {
  const [data, setData] = useState<any>(null);
  const code = me?.referrer_code;
  useEffect(() => { (async () => { try { const r = await api.get('/bigcoin/referrals'); setData(r.data); } catch {} })(); }, []);
  return (
    <View testID="tab-refer-content">
      <View style={st.referCard}>
        <Text style={st.referText}>Share this code. When a friend signs up + completes onboarding:</Text>
        <Text style={st.referReward}>You earn +100 BigCoin</Text>
        <View style={st.referCodeBox} testID="referrer-code">
          <Text style={st.referCode}>{code || '—'}</Text>
        </View>
        {data && (
          <View style={st.referStats}>
            <View style={st.referStat} testID="refer-stat-invited">
              <Text style={st.referStatNum}>{data.total_invited}</Text>
              <Text style={st.referStatLabel}>INVITED</Text>
            </View>
            <View style={st.referStat} testID="refer-stat-completed">
              <Text style={[st.referStatNum, { color: COLORS.green }]}>{data.completed}</Text>
              <Text style={st.referStatLabel}>COMPLETED</Text>
            </View>
            <View style={st.referStat} testID="refer-stat-earned">
              <Text style={[st.referStatNum, { color: COLORS.gold }]}>{data.bigcoin_earned}</Text>
              <Text style={st.referStatLabel}>BC EARNED</Text>
            </View>
          </View>
        )}
      </View>
    </View>
  );
}

/* ── Gift Inbox — gifts received (packages, memberships, gift cards) ── */
if (Platform.OS === 'android' && UIManager.setLayoutAnimationEnabledExperimental) {
  UIManager.setLayoutAnimationEnabledExperimental(true);
}
const GIFT_ICON: Record<string, any> = { giftcard: 'card', package: 'cube', membership: 'star' };

function WrappedGift({ g, onOpen }: { g: any; onOpen: () => void }) {
  const wob = React.useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(wob, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.timing(wob, { toValue: -1, duration: 700, useNativeDriver: true }),
      Animated.timing(wob, { toValue: 0, duration: 500, useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [wob]);
  const rotate = wob.interpolate({ inputRange: [-1, 1], outputRange: ['-8deg', '8deg'] });
  return (
    <TouchableOpacity style={st.giftWrapped} activeOpacity={0.8} onPress={onOpen} testID={`gift-wrapped-${g.id}`}>
      <Animated.Text style={{ fontSize: 26, transform: [{ rotate }] }}>🎁</Animated.Text>
      <View style={{ flex: 1, marginLeft: 10 }}>
        <Text style={st.giftTitle}>A gift from {g.from_name}</Text>
        <Text style={st.giftUnwrap}>✨ Tap to unwrap</Text>
      </View>
    </TouchableOpacity>
  );
}

function RevealedGift({ g, router }: { g: any; router: any }) {
  const pop = React.useRef(new Animated.Value(0.9)).current;
  useEffect(() => {
    Animated.spring(pop, { toValue: 1, friction: 5, tension: 140, useNativeDriver: true }).start();
  }, [pop]);
  return (
    <Animated.View style={{ transform: [{ scale: pop }] }}>
      <TouchableOpacity style={st.giftRow} activeOpacity={0.75}
        onPress={() => router.push(g.route)} testID={`gift-item-${g.id}`}>
        <Ionicons name={GIFT_ICON[g.kind] || 'gift'} size={20} color={COLORS.primary} />
        <View style={{ flex: 1, marginLeft: 10 }}>
          <Text style={st.giftTitle}>{g.title}</Text>
          {!!g.subtitle && <Text style={st.giftSub}>{g.subtitle}</Text>}
          <Text style={st.giftFrom}>From {g.from_name}</Text>
          {!!g.message && <Text style={st.giftMsg}>“{g.message}”</Text>}
        </View>
        <Ionicons name="chevron-forward" size={16} color={COLORS.primary} />
      </TouchableOpacity>
    </Animated.View>
  );
}

function GiftInbox({ router }: { router: any }) {
  const [items, setItems] = useState<any[]>([]);
  const [open, setOpen] = useState<Record<string, boolean>>({});
  useEffect(() => {
    (async () => {
      try { const r = await api.get('/shop/gifts/received'); setItems(r.data?.items || []); }
      catch { setItems([]); }
    })();
  }, []);
  if (!items.length) return null;
  const unwrap = (key: string) => {
    LayoutAnimation.configureNext(LayoutAnimation.Presets.easeInEaseOut);
    setOpen((s) => ({ ...s, [key]: true }));
  };
  return (
    <View style={st.giftInbox} testID="gift-inbox">
      <View style={st.giftInboxHead}>
        <Ionicons name="gift" size={16} color={COLORS.primary} />
        <Text style={st.giftInboxTitle}>Gifts received</Text>
        <View style={st.giftInboxBadge}><Text style={st.giftInboxBadgeText} testID="gift-inbox-count">{items.length}</Text></View>
      </View>
      {items.map((g: any) => {
        const key = `${g.kind}-${g.id}`;
        return open[key]
          ? <RevealedGift key={key} g={g} router={router} />
          : <WrappedGift key={key} g={g} onOpen={() => unwrap(key)} />;
      })}
    </View>
  );
}

const st = StyleSheet.create({
  gcSection: { marginHorizontal: SPACING.md, marginBottom: SPACING.md, gap: 8 },
  gcHeading: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900', marginBottom: 2 },
  gcCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.gold, padding: SPACING.sm + 2 },
  gcArt: { width: 46, height: 46, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  gcName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  gcCode: { color: COLORS.textMuted, fontSize: FONT.xs, fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace', letterSpacing: 1, marginTop: 2 },
  gcBalance: { color: COLORS.gold, fontSize: FONT.md, fontWeight: '900' },
  gcBalanceLabel: { color: COLORS.textMuted, fontSize: 9, textTransform: 'uppercase', letterSpacing: 1 },
  gcTapHint: { color: COLORS.primary, fontSize: 10, fontWeight: '700', marginTop: 3 },
  gcModalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  gcModalCard: { backgroundColor: COLORS.bg, borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: SPACING.lg, paddingBottom: SPACING.xl, gap: SPACING.sm, maxHeight: '85%' },
  gcModalHead: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  gcModalTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  gcModalCode: { color: COLORS.textMuted, fontSize: FONT.xs, fontFamily: Platform.OS === 'ios' ? 'Courier' : 'monospace', letterSpacing: 1, marginTop: 3 },
  gcModalBalanceBox: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.gold, padding: SPACING.md, alignItems: 'center' },
  gcModalBalanceLabel: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.5 },
  gcModalBalance: { color: COLORS.gold, fontSize: 30, fontWeight: '900', marginTop: 2 },
  gcModalDepleted: { color: COLORS.textMuted, fontSize: FONT.sm, textAlign: 'center', paddingVertical: SPACING.md },
  gcModalInputLabel: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1.5, marginTop: 6 },
  gcModalInputRow: { flexDirection: 'row', gap: 8 },
  gcModalInputWrap: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, paddingHorizontal: 14 },
  gcModalCurrency: { color: COLORS.textMuted, fontSize: FONT.md, fontWeight: '900' },
  gcModalInput: { flex: 1, color: COLORS.text, fontSize: FONT.md, fontWeight: '800', paddingVertical: 12 },
  gcModalSpendBtn: { paddingHorizontal: 24, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  gcModalSpendTxt: { color: '#fff', fontWeight: '900', fontSize: FONT.md },
  gcModalHint: { color: COLORS.textMuted, fontSize: FONT.xs },
  gcModalErr: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '700', textAlign: 'center' },
  gcModalResult: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(22,163,74,0.1)', borderRadius: RADIUS.md, padding: 12 },
  gcModalResultTxt: { color: COLORS.green, fontSize: FONT.sm, fontWeight: '700', flex: 1 },
  container: { flex: 1, backgroundColor: COLORS.bg },
  loadWrap: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  /* Gift Inbox */
  giftInbox: { backgroundColor: 'rgba(242,107,42,0.08)', borderWidth: 1, borderColor: 'rgba(242,107,42,0.3)', borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  giftInboxHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: SPACING.sm },
  giftInboxTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  giftInboxBadge: { backgroundColor: COLORS.primary, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 1 },
  giftInboxBadgeText: { color: '#fff', fontSize: FONT.xs, fontWeight: '900' },
  giftRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.sm, marginTop: 6, borderWidth: 1, borderColor: COLORS.cardBorder },
  giftWrapped: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(242,107,42,0.14)', borderRadius: RADIUS.md, padding: SPACING.sm, marginTop: 6, borderWidth: 1, borderStyle: 'dashed', borderColor: 'rgba(242,107,42,0.55)' },
  giftUnwrap: { color: '#fdba74', fontSize: FONT.xs, fontWeight: '800', marginTop: 2 },
  giftTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900' },
  giftSub: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 1 },
  giftFrom: { color: COLORS.primary, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  giftMsg: { color: COLORS.textDim, fontSize: FONT.xs, fontStyle: 'italic', marginTop: 3 },
  header: { marginBottom: SPACING.md },
  headerTitle: { fontSize: 24, fontWeight: '900', color: COLORS.text, letterSpacing: -1 },
  headerSub: { fontSize: 12, color: COLORS.textDim, marginTop: 4 },
  /* Balance Card */
  pointsCard: { borderRadius: RADIUS.xl, padding: SPACING.lg, marginBottom: SPACING.md, shadowColor: '#F26B2A', shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.28, shadowRadius: 14, elevation: 6 },
  pointsTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  pointsLabel: { fontSize: 10, color: 'rgba(255,255,255,0.85)', fontWeight: '800', letterSpacing: 1 },
  pointsAmountRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, marginTop: 4 },
  pointsGlyph: { fontSize: 26, fontWeight: '900', color: '#fff', marginBottom: 3 },
  pointsAmount: { fontSize: 42, fontWeight: '900', color: '#fff', lineHeight: 46 },
  tierPill: { backgroundColor: 'rgba(255,255,255,0.22)', borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 6 },
  tierPillText: { color: '#fff', fontSize: 12, fontWeight: '800' },
  pointsMetaRow: { flexDirection: 'row', gap: SPACING.md, marginTop: 10 },
  pointsMeta: { fontSize: 12, color: 'rgba(255,255,255,0.92)', fontWeight: '600' },
  pointsProgressWrap: { marginTop: SPACING.md },
  pointsProgressBar: { height: 7, backgroundColor: 'rgba(255,255,255,0.28)', borderRadius: 4, overflow: 'hidden' },
  pointsProgressFill: { height: 7, backgroundColor: '#fff', borderRadius: 4 },
  pointsProgressHint: { fontSize: 11, color: 'rgba(255,255,255,0.92)', fontWeight: '600', marginTop: 5 },
  /* Action Row */
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: SPACING.md },
  actionBtn: { flexBasis: '30%', flexGrow: 1, alignItems: 'center', gap: 6, paddingVertical: 14, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 2, elevation: 1 },
  actionIcon: { width: 36, height: 36, borderRadius: 10, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  actionLabel: { fontSize: 11, fontWeight: '700', color: COLORS.text },
  /* Tabs */
  tabs: { flexDirection: 'row', gap: 4 },
  tab: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 14, paddingVertical: 10, borderRadius: RADIUS.md, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  tabActive: { borderColor: COLORS.primary, backgroundColor: 'rgba(242,107,42,0.08)' },
  tabText: { fontSize: 11, color: COLORS.textDim, fontWeight: '600' },
  tabTextActive: { color: COLORS.primary },
  /* Shared */
  sectionTitle: { fontSize: 12, color: COLORS.textDim, fontWeight: '700', letterSpacing: 1.5, textTransform: 'uppercase', marginBottom: SPACING.sm },
  emptyText: { color: COLORS.textDim, textAlign: 'center', fontSize: 13, marginTop: 6 },
  emptyCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.lg, alignItems: 'center', borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.sm },
  /* Coupons */
  couponRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, padding: SPACING.sm, borderRadius: RADIUS.md, marginBottom: 6, borderWidth: 1, borderColor: COLORS.cardBorder },
  couponBiz: { color: COLORS.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 0.5, textTransform: 'uppercase' },
  couponCode: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', letterSpacing: 1 },
  couponMeta: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  couponStatusBadge: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  browseOffersCta: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(242,107,42,0.06)', borderWidth: 1, borderColor: 'rgba(242,107,42,0.2)', borderRadius: RADIUS.lg, padding: SPACING.md, marginTop: SPACING.sm, marginBottom: SPACING.sm },
  browseOffersTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  browseOffersSub: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  /* Wallet Items */
  walletItemRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, padding: SPACING.sm, borderRadius: RADIUS.md, marginBottom: 6, borderWidth: 1, borderColor: COLORS.cardBorder },
  walletItemTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  walletItemMeta: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  /* Redemptions */
  redemptionRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  redemptionName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600' },
  redemptionMeta: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  redemptionCost: { color: COLORS.red, fontSize: FONT.sm, fontWeight: '700' },
  /* Transactions */
  txnRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  txnSource: { fontSize: 13, color: COLORS.text, fontWeight: '600' },
  txnDate: { fontSize: 11, color: COLORS.textDim, marginTop: 2 },
  txnAmount: { fontSize: 14, fontWeight: '800' },
  /* Rewards */
  rewardCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.cardBorder },
  rewardCost: { fontSize: 12, color: COLORS.gold, fontWeight: '700', marginBottom: 8 },
  rewardName: { fontSize: 16, fontWeight: '700', color: COLORS.text, marginBottom: 4 },
  rewardDesc: { fontSize: 12, color: COLORS.textDim, marginBottom: SPACING.sm },
  stockText: { fontSize: 10, color: COLORS.textDim, marginBottom: 6 },
  rewardBtn: { backgroundColor: COLORS.primary, paddingVertical: 10, borderRadius: RADIUS.md, alignItems: 'center' },
  rewardBtnText: { color: '#fff', fontSize: 13, fontWeight: '700' },
  /* Badges */
  badgeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  badgeCard: { width: '47%', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder },
  badgeIcon: { fontSize: 24, marginBottom: 6 },
  badgeName: { fontSize: 12, fontWeight: '700', color: COLORS.text, marginBottom: 4 },
  badgeDesc: { fontSize: 10, color: COLORS.textDim, lineHeight: 14 },
  /* Refer */
  referCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.lg, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center' },
  referText: { fontSize: 13, color: COLORS.textDim, textAlign: 'center', lineHeight: 20 },
  referReward: { fontSize: 20, fontWeight: '800', color: COLORS.gold, marginVertical: SPACING.sm },
  referCodeBox: { backgroundColor: 'rgba(255,255,255,0.06)', paddingHorizontal: SPACING.lg, paddingVertical: SPACING.sm, borderRadius: RADIUS.md, marginBottom: SPACING.md },
  referCode: { fontSize: 18, fontWeight: '800', color: COLORS.text, letterSpacing: 3 },
  referStats: { flexDirection: 'row', gap: SPACING.xl, marginTop: SPACING.md },
  referStat: { alignItems: 'center' },
  referStatNum: { fontSize: 22, fontWeight: '800', color: COLORS.text },
  referStatLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', letterSpacing: 1, marginTop: 4 },
});
