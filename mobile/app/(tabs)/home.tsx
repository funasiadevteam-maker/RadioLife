import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/contexts/AuthContext';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { useStationsStore } from '../../src/stores/useStationsStore';
import { playImportedStation } from '../../src/services/playStation';
import AdBanner from '../../src/components/AdBanner';
import api, { BACKEND } from '../../src/api/client';

const resolveImg = (u?: string | null) =>
  u ? (u.startsWith('http') ? u : `${BACKEND}${u}`) : null;
import SafeImage from '../../src/components/SafeImage';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

export default function HomeScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [channels, setChannels] = useState<any[]>([]);
  const [breaking, setBreaking] = useState<any[]>([]);
  const [wallet, setWallet] = useState<any>(null);
  const [deals, setDeals] = useState<any[]>([]);
  const [topStations, setTopStations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const { activeChannelName, activeChannelThumb, currentSeg } = usePlayerStore();
  const { recents, load: loadSaved } = useStationsStore();

  useEffect(() => { loadSaved(); }, [loadSaved]);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!authLoading && !user) router.replace('/login');
  }, [user, authLoading]);

  const load = async () => {
    try {
      const [chRes, brRes, wRes, dRes, dscRes] = await Promise.allSettled([
        api.get('/channels'),
        api.get('/news/headlines/breaking'),
        api.get('/bigcoin/me'),
        api.get('/commerce/offers/feed'),
        api.get('/radio/discover'),
      ]);
      if (chRes.status === 'fulfilled') setChannels((chRes.value as any).data?.channels || []);
      if (brRes.status === 'fulfilled') setBreaking((brRes.value as any).data?.items || []);
      if (wRes.status === 'fulfilled') setWallet((wRes.value as any).data);
      if (dRes.status === 'fulfilled') setDeals((dRes.value as any).data?.items || []);
      if (dscRes.status === 'fulfilled') {
        const rails = (dscRes.value as any).data?.rails || [];
        const railMap: Record<string, any[]> = {};
        rails.forEach((r: any) => { railMap[r.id] = r.stations || []; });
        setTopStations((railMap.trending?.length ? railMap.trending : railMap.for_you) || []);
      }
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
  };

  useEffect(() => { if (!authLoading && user) load(); }, [authLoading, user]);

  if (authLoading || loading) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const featured = channels.slice(0, 6);
  const firstName = user?.name?.split(' ')[0] || '';

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView
        contentContainerStyle={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
      >
        {/* Brand Header */}
        <View style={s.header} testID="home-header">
          <View style={s.brandRow}>
            <View style={s.dot} />
            <Text style={s.brand}>BigFM</Text>
          </View>
          <TouchableOpacity onPress={() => router.push('/notifications')} testID="home-notif-btn" style={s.iconBtn}>
            <Ionicons name="notifications-outline" size={20} color={COLORS.textDim} />
          </TouchableOpacity>
        </View>

        {/* Hero Card */}
        <View style={s.hero} testID="home-hero">
          <Text style={s.heroGreet}>Welcome back{firstName ? `, ${firstName}` : ''} 👋</Text>
          <Text style={s.heroTag}>DIL SE · DUBAI SE</Text>
          <TouchableOpacity style={s.heroBtn} onPress={() => router.push('/(tabs)/listen')} testID="home-listen-cta">
            <Ionicons name="radio" size={18} color="#fff" />
            <Text style={s.heroBtnText}>{activeChannelName ? 'Now Playing' : 'Start Listening'}</Text>
          </TouchableOpacity>
        </View>

        {/* Breaking News Banner */}
        {breaking.length > 0 && (
          <TouchableOpacity style={s.breakingBanner} testID="home-breaking-banner" onPress={() => router.push('/(tabs)/news')}>
            <View style={s.breakingDot} />
            <View style={{ flex: 1 }}>
              <Text style={s.breakingLabel}>BREAKING</Text>
              <Text style={s.breakingText} numberOfLines={2}>{breaking[0].headline_text}</Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={COLORS.red} />
          </TouchableOpacity>
        )}

        {/* Wallet Summary */}
        {wallet && (
          <TouchableOpacity style={s.walletCard} testID="home-wallet-card" onPress={() => router.push('/(tabs)/wallet')}>
            <View>
              <Text style={s.walletLabel}>BIGCOIN BALANCE</Text>
              <Text style={s.walletAmt}>{wallet.balance?.toLocaleString() || '0'}</Text>
            </View>
            <View style={s.walletMeta}>
              <Text style={s.walletTier}>{(wallet.tier || 'bronze').toUpperCase()}</Text>
              <Ionicons name="chevron-forward" size={14} color={COLORS.textMuted} />
            </View>
          </TouchableOpacity>
        )}

        {/* Continue Listening */}
        {(() => {
          const cont = activeChannelName
            ? { name: activeChannelName, sub: currentSeg?.track_artist || 'Live now', thumb: activeChannelThumb, onPress: () => router.push('/now-playing') }
            : recents[0]
            ? { name: recents[0].name, sub: [recents[0].country, recents[0].language].filter(Boolean).join(' · ') || 'Recently played', thumb: recents[0].favicon || recents[0].logo_url, onPress: () => playImportedStation(recents[0], router) }
            : null;
          if (!cont) return null;
          return (
            <TouchableOpacity style={s.continueCard} testID="home-continue" onPress={cont.onPress} activeOpacity={0.85}>
              <SafeImage uri={resolveImg(cont.thumb)} fallbackText={cont.name} size={48} borderRadius={12} />
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.continueLabel}>CONTINUE LISTENING</Text>
                <Text style={s.continueName} numberOfLines={1}>{cont.name}</Text>
                <Text style={s.continueSub} numberOfLines={1}>{cont.sub}</Text>
              </View>
              <View style={s.continuePlay}><Ionicons name="play" size={18} color="#fff" /></View>
            </TouchableOpacity>
          );
        })()}

        {/* Featured Stations */}
        <Text style={[common.sectionTitle, { marginTop: SPACING.lg, paddingHorizontal: SPACING.md }]}>FEATURED STATIONS</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: SPACING.md }}>
          {featured.map(ch => (
            <TouchableOpacity key={ch.slug} testID={`home-station-${ch.slug}`}
              style={s.stationCard}
              onPress={() => router.push({ pathname: '/(tabs)/radio', params: { channel: ch.slug } })}>
              <SafeImage
                uri={resolveImg(ch.cover_image_url || ch.thumbnail_url)}
                fallbackText={ch.name || ch.slug}
                size={52}
                borderRadius={14}
              />
              <Text style={s.stationName} numberOfLines={1}>{ch.name}</Text>
              <Text style={s.stationSub} numberOfLines={1}>{(ch.language_tags || []).join(', ') || ch.vibe || '—'}</Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* All Stations CTA — the full 40k+ imported library */}
        <TouchableOpacity style={s.allStationsCta} testID="home-all-stations-cta"
          onPress={() => router.push('/stations')}>
          <View style={s.allStationsIcon}>
            <Ionicons name="globe" size={20} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.allStationsTitle}>Explore 40,000+ live stations</Text>
            <Text style={s.allStationsSub}>Search radio from around the world</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
        </TouchableOpacity>

        {/* Nearby Deals rail */}
        {deals.length > 0 && (
          <>
            <View style={s.dealsHead}>
              <Text style={[common.sectionTitle, { marginTop: 0, paddingHorizontal: 0 }]}>NEARBY DEALS</Text>
              <TouchableOpacity onPress={() => router.push('/coupons')} testID="home-deals-seeall">
                <Text style={s.seeAll}>See all</Text>
              </TouchableOpacity>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: SPACING.sm }}>
              {deals.slice(0, 6).map((o) => (
                <TouchableOpacity key={o.offer_id} style={s.dealCard} onPress={() => router.push(`/offer/${o.offer_id}`)} testID={`home-deal-${o.offer_id}`} activeOpacity={0.85}>
                  <View style={s.dealDiscount}>
                    <Text style={s.dealDiscountText}>
                      {o.value_amount != null ? (o.offer_type === 'percent_off' ? `${o.value_amount}% OFF` : `${o.value_amount} ${o.value_currency || 'AED'} OFF`) : 'DEAL'}
                    </Text>
                  </View>
                  <Text style={s.dealTitle} numberOfLines={2}>{o.title}</Text>
                  {o.end_at ? <Text style={s.dealMeta}>exp {new Date(o.end_at).toLocaleDateString()}</Text> : null}
                </TouchableOpacity>
              ))}
            </ScrollView>
          </>
        )}

        {/* Quick Links — 6 icons in one line */}
        <Text style={[common.sectionTitle, { marginTop: SPACING.lg, paddingHorizontal: SPACING.md }]}>EXPLORE</Text>
        <View style={s.exploreRow}>
          <QuickLink icon="newspaper" label="News" color={COLORS.red} onPress={() => router.push('/(tabs)/news')} testID="home-quick-news" />
          <QuickLink icon="mic" label="Podcasts" color={COLORS.secondary} onPress={() => router.push('/(tabs)/podcasts')} testID="home-quick-podcasts" />
          <QuickLink icon="pricetag" label="Deals" color={COLORS.green} onPress={() => router.push('/coupons')} testID="home-quick-deals" />
          <QuickLink icon="game-controller" label="Games" color={COLORS.orange} onPress={() => router.push('/(tabs)/games')} testID="home-quick-games" />
          <QuickLink icon="grid" label="Channels" color={COLORS.purple} onPress={() => router.push('/channels')} testID="home-quick-channels" />
          <QuickLink icon="ribbon" label="Passport" color={COLORS.gold} onPress={() => router.push('/(tabs)/passport')} testID="home-quick-passport" />
        </View>

        <TouchableOpacity style={s.seeAll} testID="home-see-all-channels" onPress={() => router.push('/channels')}>
          <Text style={s.seeAllText}>Browse all channels</Text>
          <Ionicons name="chevron-forward" size={14} color={COLORS.secondary} />
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function QuickLink({ icon, label, color, onPress, testID }: { icon: any; label: string; color: string; onPress: () => void; testID: string }) {
  return (
    <TouchableOpacity style={s.qlItem} onPress={onPress} testID={testID}>
      <View style={[s.qlIcon, { backgroundColor: color + '14' }]}>
        <Ionicons name={icon} size={20} color={color} />
      </View>
      <Text style={s.qlLabel}>{label}</Text>
    </TouchableOpacity>
  );
}

const s = StyleSheet.create({
  scroll: { paddingBottom: 40 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: SPACING.md, paddingTop: SPACING.lg },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  dot: { width: 10, height: 10, borderRadius: 5, backgroundColor: COLORS.primary },
  brand: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  iconBtn: { padding: 8, borderRadius: RADIUS.sm, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder },
  hero: {
    marginHorizontal: SPACING.md, padding: SPACING.xl, borderRadius: RADIUS.xl,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.06, shadowRadius: 8, elevation: 3,
  },
  heroGreet: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900', marginBottom: 4 },
  heroTag: { color: COLORS.textMuted, fontSize: FONT.xs, letterSpacing: 3, fontWeight: '700', marginBottom: SPACING.lg },
  heroBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: COLORS.primary, paddingVertical: 14, borderRadius: RADIUS.lg,
  },
  heroBtnText: { color: '#fff', fontWeight: '800', fontSize: FONT.md },
  breakingBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    marginHorizontal: SPACING.md, padding: 14, borderRadius: RADIUS.md,
    backgroundColor: '#fef2f2', borderWidth: 1, borderColor: '#fecaca',
    marginBottom: SPACING.md,
  },
  breakingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.red },
  breakingLabel: { color: COLORS.red, fontSize: 9, fontWeight: '800', letterSpacing: 2 },
  breakingText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600', marginTop: 2 },
  walletCard: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    marginHorizontal: SPACING.md, padding: SPACING.md, borderRadius: RADIUS.lg,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    marginBottom: SPACING.sm,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 4, elevation: 2,
  },
  walletLabel: { color: COLORS.textMuted, fontSize: 9, fontWeight: '700', letterSpacing: 2 },
  walletAmt: { color: COLORS.gold, fontSize: FONT.xl, fontWeight: '900', marginTop: 2 },
  walletMeta: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  walletTier: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1.5 },
  continueCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, marginTop: SPACING.sm, padding: SPACING.sm + 2,
    borderRadius: RADIUS.lg, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 4, elevation: 2,
  },
  continueLabel: { color: COLORS.primary, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  continueName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800', marginTop: 2 },
  continueSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  continuePlay: { width: 38, height: 38, borderRadius: 19, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  dealsHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: SPACING.md, marginTop: SPACING.lg, marginBottom: SPACING.sm },
  seeAll: { color: COLORS.secondary, fontSize: FONT.sm, fontWeight: '700' },
  dealCard: { width: 160, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md },
  dealDiscount: { alignSelf: 'flex-start', backgroundColor: COLORS.primary, borderRadius: RADIUS.sm, paddingHorizontal: 8, paddingVertical: 4, marginBottom: 8 },
  dealDiscountText: { color: '#fff', fontSize: FONT.xs, fontWeight: '900' },
  dealTitle: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', lineHeight: 18 },
  dealMeta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 4 },
  stationCard: {
    width: 120, padding: SPACING.md, borderRadius: RADIUS.lg,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    marginRight: 10, alignItems: 'center',
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 3, elevation: 1,
  },
  stationName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', textAlign: 'center', marginTop: 8 },
  stationSub: { color: COLORS.textMuted, fontSize: 9, marginTop: 2, textAlign: 'center' },
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', marginHorizontal: SPACING.md, marginBottom: SPACING.lg },
  exploreRow: { flexDirection: 'row', justifyContent: 'space-between', paddingHorizontal: SPACING.sm, marginBottom: SPACING.lg },
  qlItem: { flex: 1, alignItems: 'center', paddingVertical: SPACING.sm },
  qlIcon: { width: 46, height: 46, borderRadius: 14, alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  qlLabel: { color: COLORS.textDim, fontSize: 10, fontWeight: '700' },
  topStationTile: { width: 92 },
  topStationName: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '700', marginTop: 5 },
  topStationSub: { color: COLORS.textMuted, fontSize: 10, fontWeight: '600', marginTop: 1 },
  seeAll: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    paddingVertical: 10, marginHorizontal: SPACING.md,
  },
  seeAllText: { color: COLORS.secondary, fontSize: FONT.sm, fontWeight: '700' },
  allStationsCta: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, marginTop: SPACING.lg, padding: SPACING.md,
    borderRadius: RADIUS.lg, backgroundColor: COLORS.card,
    borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  allStationsIcon: {
    width: 44, height: 44, borderRadius: 12, backgroundColor: COLORS.secondary,
    alignItems: 'center', justifyContent: 'center',
  },
  allStationsTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  allStationsSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
});
