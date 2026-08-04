import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, RefreshControl,
} from 'react-native';
import { useRouter, useFocusEffect } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
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

        {/* Balance card */}
        <View style={st.balanceCard} testID="balance-card">
          <View style={st.balanceTop}>
            <Text style={st.balanceIcon}>₿</Text>
            <View style={{ flex: 1 }}>
              <Text style={st.balanceLabel}>CURRENT BALANCE</Text>
              <Text style={st.balanceAmount} testID="bc-balance">{me?.balance ?? 0}</Text>
            </View>
          </View>
          <View style={st.balanceMeta}>
            <Text style={st.tierBadge} testID="bc-tier">{TIER_ICONS[me?.tier] || '🥉'} {me?.tier_label}</Text>
            <Text style={st.metaItem}>🔥 <Text style={{ color: COLORS.text, fontWeight: '700' }}>{me?.streak_days || 0}</Text>-day streak</Text>
            <Text style={st.metaItem}>Lifetime <Text style={{ color: COLORS.text, fontWeight: '700' }} testID="bc-lifetime">{me?.lifetime_earned || 0}</Text></Text>
          </View>
          {/* Milestone bar */}
          <View style={st.milestoneWrap}>
            <Text style={st.milestoneLabel}>NEXT MILESTONE{me?.next_milestone ? ` — ${me.balance}/${me.next_milestone}` : ''}</Text>
            <View style={st.milestoneBar}>
              <View style={[st.milestoneFill, { width: `${Math.min(100, me?.milestone_progress || 0)}%` }]} />
            </View>
            <Text style={st.milestoneHint}>
              {me?.next_milestone ? `${me.next_milestone - (me.lifetime_earned || 0)} BC to milestone` : 'Max milestone reached!'}
            </Text>
          </View>
        </View>

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

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  loadWrap: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  header: { marginBottom: SPACING.md },
  headerTitle: { fontSize: 24, fontWeight: '900', color: COLORS.text, letterSpacing: -1 },
  headerSub: { fontSize: 12, color: COLORS.textDim, marginTop: 4 },
  /* Balance Card */
  balanceCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  balanceTop: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  balanceIcon: { fontSize: 36, color: COLORS.gold },
  balanceLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', letterSpacing: 1 },
  balanceAmount: { fontSize: 32, fontWeight: '900', color: COLORS.text },
  balanceMeta: { flexDirection: 'row', gap: SPACING.md, marginTop: 10, flexWrap: 'wrap' },
  tierBadge: { fontSize: 12, color: COLORS.gold, fontWeight: '700' },
  metaItem: { fontSize: 12, color: COLORS.textDim },
  milestoneWrap: { marginTop: SPACING.sm },
  milestoneLabel: { fontSize: 9, color: COLORS.textDim, fontWeight: '700', letterSpacing: 1, marginBottom: 4 },
  milestoneBar: { height: 6, backgroundColor: COLORS.surface, borderRadius: 3, overflow: 'hidden' },
  milestoneFill: { height: 6, backgroundColor: COLORS.primary, borderRadius: 3 },
  milestoneHint: { fontSize: 10, color: COLORS.textMuted, marginTop: 4 },
  /* Action Row */
  actionRow: { flexDirection: 'row', gap: 10, marginBottom: SPACING.md },
  actionBtn: { flex: 1, alignItems: 'center', gap: 6, paddingVertical: 14, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 2, elevation: 1 },
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
