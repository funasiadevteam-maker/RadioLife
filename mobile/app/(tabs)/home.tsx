import React, { useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Image } from 'expo-image';
import { useAuth } from '../../src/contexts/AuthContext';
import api, { BACKEND } from '../../src/api/client';
import TubeDrawer from '../../src/components/TubeDrawer';
import AdBanner from '../../src/components/AdBanner';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { playImportedStation } from '../../src/services/playStation';

const resolveImg = (u?: string | null) =>
  u ? (u.startsWith('http') ? u : `${BACKEND}${u}`) : null;

const SCOPE_CHIPS = [
  { key: 'foryou', label: 'For You' },
  { key: 'live', label: 'Live' },
  { key: 'trending', label: 'Trending' },
];

const fireEvent = (event: string, extra: Record<string, any> = {}) => {
  api.post('/shell/home-events', { event, surface: 'mobile', ...extra }).catch(() => {});
};

export default function HomeScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { activeChannelName, activeChannelThumb, currentSeg, playing } = usePlayerStore();

  const [home, setHome] = useState<any>(null);
  const [points, setPoints] = useState<number | null>(null);
  const [cityLabel, setCityLabel] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [chip, setChip] = useState('foryou');

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const load = async () => {
    try {
      const [hm, wl] = await Promise.allSettled([
        api.get('/shell/home'),
        api.get('/bigcoin/me'),
      ]);
      if (hm.status === 'fulfilled') setHome((hm.value as any).data || {});
      if (wl.status === 'fulfilled') setPoints((wl.value as any).data?.balance ?? null);
    } catch { /* ignore */ }
    finally { setLoading(false); setRefreshing(false); }
  };

  useEffect(() => { if (!authLoading && user) load(); }, [authLoading, user]);

  useEffect(() => {
    if (!user) return;
    api.get('/geo/resolve_city').then((r) => {
      const c = r.data?.city;
      if (c && String(c).toLowerCase() !== 'global') setCityLabel(String(c));
    }).catch(() => {});
  }, [user]);

  if (authLoading || loading) {
    return <View style={s.center}><ActivityIndicator size="large" color={TUBE.electric} /></View>;
  }

  const firstName = user?.name?.split(' ')[0] || '';
  const hasSession = !!activeChannelName;
  const forYouRaw: any[] = home?.for_you || [];
  const liveNow: any[] = home?.live_now || [];
  const nativeOffer = home?.native_offer;
  const perMin = home?.listening_reward?.points_per_min ?? 1;
  const isPremium = !!home?.is_premium;
  const diningMember = !!home?.dining?.member;

  const forYou = chip === 'live'
    ? forYouRaw.filter((x) => x.live)
    : chip === 'trending'
      ? [...forYouRaw].sort((a, b) => (b.live ? 1 : 0) - (a.live ? 1 : 0) || (b.listeners || 0) - (a.listeners || 0))
      : forYouRaw;

  const playCard = (c: any) => {
    playImportedStation({ id: c.id, name: c.name, favicon: c.art }, router);
  };
  const playSponsored = (c: any) => {
    fireEvent('sponsored_station_start', { station_id: c.id, business_id: c.sponsor_business_id });
    playCard(c);
  };
  const openNativeOffer = () => {
    if (!nativeOffer) return;
    fireEvent('native_offer_click', {
      campaign_id: nativeOffer.campaign_id, business_id: nativeOffer.business_id, kind: nativeOffer.kind });
    if (nativeOffer.business_id) router.push(`/store/${nativeOffer.business_id}`);
    else router.push('/(tabs)/shop');
  };

  return (
    <View style={s.screen}>
      {/* Sticky header */}
      <View style={[s.header, { paddingTop: insets.top + 8 }]} testID="home-header">
        <Pressable onPress={() => setDrawer(true)} testID="home-menu-btn" style={s.iconBtn} hitSlop={8}>
          <Ionicons name="menu" size={24} color={TUBE.text} />
        </Pressable>
        <View style={s.brandRow}>
          <View style={s.brandDot} />
          <Text style={s.brand}>FUUSIC</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Pressable style={s.pointsPill} testID="home-points-pill" onPress={() => router.push('/(tabs)/wallet')} hitSlop={6}>
            <Ionicons name="diamond" size={12} color={TUBE.gold} />
            <Text style={s.pointsText}>{points != null ? points.toLocaleString() : '—'}</Text>
          </Pressable>
          <Pressable onPress={() => router.push('/notifications')} testID="home-notif-btn" style={s.iconBtn} hitSlop={8}>
            <Ionicons name="notifications-outline" size={20} color={TUBE.textDim} />
          </Pressable>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={TUBE.electric}
          onRefresh={() => { setRefreshing(true); load(); }} />}>

        {/* Greeting */}
        <View style={s.greetWrap}>
          <Text style={s.greetSub}>{new Date().getHours() < 12 ? 'GOOD MORNING' : new Date().getHours() < 18 ? 'GOOD AFTERNOON' : 'GOOD EVENING'}</Text>
          <Text style={s.greet}>Hi{firstName ? `, ${firstName}` : ''} — ready to listen?</Text>
        </View>

        {/* A · Continue Listening / Start My Radio */}
        {hasSession ? (
          <Pressable style={s.continueCard} testID="home-continue" onPress={() => router.push('/now-playing')}>
            <Image source={{ uri: resolveImg(activeChannelThumb) || undefined }} style={s.continueImg} contentFit="cover" transition={200} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.continueLabel}>{playing ? 'NOW PLAYING' : 'PAUSED'}</Text>
              <Text style={s.continueName} numberOfLines={1}>{activeChannelName}</Text>
              <Text style={s.continueSub} numberOfLines={1}>{currentSeg?.track_artist || 'AI radio'}</Text>
            </View>
            <View style={s.continuePlay}><Ionicons name={playing ? 'pause' : 'play'} size={22} color={TUBE.onAccent} /></View>
          </Pressable>
        ) : (
          <Pressable style={s.startCard} testID="home-start" onPress={() => router.push('/(tabs)/radio')}>
            <View style={{ flex: 1 }}>
              <Text style={s.startKicker}>YOUR RADIO, ONE TAP AWAY</Text>
              <Text style={s.startTitle}>Start My Radio</Text>
              <Text style={s.startSub}>AI-personalized radio built around what you love</Text>
            </View>
            <View style={s.startPlay}><Ionicons name="play" size={26} color={TUBE.onAccent} /></View>
          </Pressable>
        )}

        {/* B · For You */}
        <View style={s.shelf}>
          <View style={s.shelfHead}>
            <View style={{ flex: 1 }}>
              <Text style={s.shelfTitle}>For You</Text>
              <Text style={s.shelfSuffix}>AI RADIO · LIVE RADIO · PODCASTS</Text>
            </View>
            <Pressable onPress={() => router.push('/(tabs)/listen')} hitSlop={8}>
              <Text style={s.seeAll}>See all</Text>
            </Pressable>
          </View>
          <View style={s.scopeRow}>
            {SCOPE_CHIPS.map((c) => {
              const active = chip === c.key;
              return (
                <Pressable key={c.key} testID={`home-scope-${c.key}`} onPress={() => setChip(c.key)}
                  style={[s.scopeChip, active && s.scopeChipActive]}>
                  <Text style={[s.scopeChipText, active && s.scopeChipTextActive]}>{c.label}</Text>
                </Pressable>
              );
            })}
          </View>
          {forYou.length === 0 ? (
            <Text style={s.emptyRail}>Start listening and your picks will appear here.</Text>
          ) : (
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: TSPACE.md, gap: 12 }}>
              {forYou.map((st) => (
                <Pressable key={st.slug || st.id} testID={`home-foryou-${st.slug || st.id}`} style={s.stationTile}
                  onPress={() => playCard(st)}>
                  <Image source={{ uri: resolveImg(st.art) || undefined }} style={s.stationImg} contentFit="cover" transition={200} />
                  {st.live && <View style={s.liveBadge}><Text style={s.liveBadgeText}>LIVE</Text></View>}
                  <Text style={s.tileName} numberOfLines={1}>{st.name}</Text>
                  <Text style={s.tileSub} numberOfLines={1}>{st.city || 'Radio'}</Text>
                </Pressable>
              ))}
            </ScrollView>
          )}
        </View>

        {/* C · Live Right Now — one labelled sponsored slot */}
        {liveNow.length > 0 && (
          <View style={s.shelf}>
            <View style={s.shelfHead}>
              <Text style={s.shelfTitle}>Live right now</Text>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: TSPACE.md, gap: 12 }}>
              {liveNow.map((st) => (
                <Pressable key={`${st.slug || st.id}-${st.sponsored ? 'sp' : 'org'}`}
                  testID={st.sponsored ? 'home-live-sponsored' : `home-live-${st.slug || st.id}`}
                  style={s.stationTile}
                  onPress={() => (st.sponsored ? playSponsored(st) : playCard(st))}>
                  <Image source={{ uri: resolveImg(st.art) || undefined }} style={s.stationImg} contentFit="cover" transition={200} />
                  {st.sponsored
                    ? <View style={s.sponsorBadge}><Text style={s.sponsorBadgeText}>SPONSORED</Text></View>
                    : st.live && <View style={s.liveBadge}><Text style={s.liveBadgeText}>LIVE</Text></View>}
                  <Text style={s.tileName} numberOfLines={1}>{st.name}</Text>
                  <Text style={s.tileSub} numberOfLines={1}>{st.city || 'Radio'}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        )}

        {/* D · Listening Reward */}
        <Pressable style={s.rewardCard} testID="home-reward" onPress={() => router.push('/(tabs)/wallet')}>
          <View style={s.rewardIcon}><Ionicons name="diamond" size={18} color={TUBE.gold} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.rewardTitle}>Earn +{perMin} BigPoint{perMin === 1 ? '' : 's'} every minute you listen</Text>
            <Text style={s.rewardSub}>Your BigPoints stack up in the background</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={TUBE.gold} />
        </Pressable>

        {/* E · Do More While You Listen */}
        <View style={s.shelf}>
          <View style={s.shelfHead}><Text style={s.shelfTitle}>Do more while you listen</Text></View>
          <View style={s.doMoreRow}>
            <DoMore icon="storefront" label="Shop & Eat" sub="Deals near you" onPress={() => router.push('/(tabs)/shop')} testID="home-domore-shop" />
            <DoMore icon="game-controller" label="Play & Win" sub="Games · trivia" onPress={() => router.push('/(tabs)/games')} testID="home-domore-play" />
            <DoMore icon="people" label="Social" sub="Community" onPress={() => router.push('/(tabs)/social')} testID="home-domore-social" />
          </View>
        </View>

        {/* F · Native sponsored card */}
        {nativeOffer && (
          <NativeOffer offer={nativeOffer} onPress={openNativeOffer} />
        )}

        {/* G · Contextual Dining Club */}
        <Pressable style={diningMember ? s.diningMember : s.diningPromo} testID="home-dining"
          onPress={() => router.push('/dining')}>
          <View style={s.diningIcon}><Ionicons name="restaurant" size={18} color={TUBE.electric} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.diningTitle}>{diningMember ? 'Your Dining Club' : 'FUUSIC Dining Club'}</Text>
            <Text style={s.diningSub}>{diningMember ? "Pick this week's meals · spin for tonight" : 'Spin the wheel · $9.99 meals near you'}</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={TUBE.textMuted} />
        </Pressable>

        {/* H · Display ad — Free listeners only */}
        {!isPremium && (
          <View style={{ marginTop: TSPACE.lg }} testID="home-display-ad">
            <AdBanner zone="browse_row" />
          </View>
        )}
      </ScrollView>

      <TubeDrawer open={drawer} onClose={() => setDrawer(false)} />
    </View>
  );
}

function DoMore({ icon, label, sub, onPress, testID }:
  { icon: any; label: string; sub: string; onPress: () => void; testID: string }) {
  return (
    <Pressable style={s.doMoreCard} onPress={onPress} testID={testID}>
      <View style={s.doMoreIcon}><Ionicons name={icon} size={18} color={TUBE.electric} /></View>
      <Text style={s.doMoreLabel} numberOfLines={1}>{label}</Text>
      <Text style={s.doMoreSub} numberOfLines={1}>{sub}</Text>
    </Pressable>
  );
}

function NativeOffer({ offer, onPress }: { offer: any; onPress: () => void }) {
  useEffect(() => {
    fireEvent('native_offer_impression', {
      campaign_id: offer.campaign_id, business_id: offer.business_id, kind: offer.kind });
  }, [offer]);
  return (
    <Pressable style={s.nativeCard} testID="home-native-offer" onPress={onPress}>
      <Image source={{ uri: resolveImg(offer.image) || undefined }} style={s.nativeImg} contentFit="cover" transition={200} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <View style={s.nativeBadge}><Text style={s.nativeBadgeText}>SPONSORED</Text></View>
        <Text style={s.nativeTitle} numberOfLines={1}>{offer.title}</Text>
        <Text style={s.nativeSub} numberOfLines={1}>{offer.subtitle}</Text>
      </View>
      <View style={s.nativeCta}><Text style={s.nativeCtaText}>{offer.cta || 'View'}</Text></View>
    </Pressable>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: TUBE.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: TUBE.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: TSPACE.md, paddingBottom: 10, backgroundColor: TUBE.bg,
    borderBottomWidth: 1, borderBottomColor: TUBE.line,
  },
  iconBtn: { padding: 4 },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  brandDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: TUBE.electric },
  brand: { color: TUBE.text, fontSize: TFONT.lg, fontWeight: '900', letterSpacing: -0.3 },
  pointsPill: {
    flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, height: 30,
    borderRadius: TRADIUS.full, backgroundColor: TUBE.glass, borderWidth: 1, borderColor: TUBE.line,
  },
  pointsText: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },

  greetWrap: { paddingHorizontal: TSPACE.md, paddingTop: TSPACE.lg, paddingBottom: TSPACE.sm },
  greetSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 3, marginBottom: 4 },
  greet: { color: TUBE.text, fontSize: TFONT.xxl, fontWeight: '900', letterSpacing: -0.5 },

  continueCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: 6,
    padding: TSPACE.sm + 2, borderRadius: TRADIUS.lg, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line,
  },
  continueImg: { width: 64, height: 64, borderRadius: TRADIUS.md, backgroundColor: TUBE.glass },
  continueLabel: { color: TUBE.electric, fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  continueName: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '800', marginTop: 2 },
  continueSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },
  continuePlay: { width: 46, height: 46, borderRadius: 23, backgroundColor: TUBE.electric, alignItems: 'center', justifyContent: 'center' },

  startCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: 6,
    padding: TSPACE.md, borderRadius: TRADIUS.xl, backgroundColor: TUBE.magenta,
  },
  startKicker: { color: 'rgba(255,255,255,0.85)', fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  startTitle: { color: '#fff', fontSize: TFONT.xl, fontWeight: '900', marginTop: 2 },
  startSub: { color: 'rgba(255,255,255,0.9)', fontSize: TFONT.xs, fontWeight: '600', marginTop: 3 },
  startPlay: { width: 52, height: 52, borderRadius: 26, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center' },

  shelf: { marginTop: TSPACE.lg },
  shelfHead: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: TSPACE.md, marginBottom: TSPACE.sm },
  shelfTitle: { color: TUBE.text, fontSize: TFONT.lg, fontWeight: '900', letterSpacing: -0.3 },
  shelfSuffix: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 2, marginTop: 2 },
  seeAll: { color: TUBE.electric, fontSize: TFONT.sm, fontWeight: '700' },
  emptyRail: { color: TUBE.textMuted, fontSize: TFONT.sm, paddingHorizontal: TSPACE.md, paddingVertical: 12 },

  scopeRow: { flexDirection: 'row', gap: 8, paddingHorizontal: TSPACE.md, marginBottom: TSPACE.sm },
  scopeChip: { height: 32, paddingHorizontal: 14, borderRadius: TRADIUS.full, alignItems: 'center', justifyContent: 'center', backgroundColor: TUBE.glass, borderWidth: 1, borderColor: TUBE.line },
  scopeChipActive: { backgroundColor: TUBE.text, borderColor: TUBE.text },
  scopeChipText: { color: TUBE.textDim, fontSize: TFONT.sm, fontWeight: '700' },
  scopeChipTextActive: { color: TUBE.bg, fontWeight: '800' },

  stationTile: { width: 116 },
  stationImg: { width: 116, height: 116, borderRadius: TRADIUS.lg, backgroundColor: TUBE.elevated },
  tileName: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800', marginTop: 6 },
  tileSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },
  liveBadge: { position: 'absolute', top: 8, left: 8, backgroundColor: TUBE.live, borderRadius: TRADIUS.full, paddingHorizontal: 7, paddingVertical: 2 },
  liveBadgeText: { color: '#fff', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  sponsorBadge: { position: 'absolute', top: 8, left: 8, backgroundColor: TUBE.gold, borderRadius: TRADIUS.full, paddingHorizontal: 7, paddingVertical: 2 },
  sponsorBadgeText: { color: TUBE.onAccent, fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },

  rewardCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: 'rgba(245,158,11,0.06)', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)',
  },
  rewardIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(245,158,11,0.15)', alignItems: 'center', justifyContent: 'center' },
  rewardTitle: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  rewardSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },

  doMoreRow: { flexDirection: 'row', gap: 10, paddingHorizontal: TSPACE.md },
  doMoreCard: { flex: 1, padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line },
  doMoreIcon: { width: 38, height: 38, borderRadius: 11, backgroundColor: 'rgba(34,211,238,0.15)', alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  doMoreLabel: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  doMoreSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },

  nativeCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.sm + 2, borderRadius: TRADIUS.lg, backgroundColor: 'rgba(245,158,11,0.05)', borderWidth: 1, borderColor: 'rgba(245,158,11,0.25)',
  },
  nativeImg: { width: 64, height: 64, borderRadius: TRADIUS.md, backgroundColor: TUBE.glass },
  nativeBadge: { alignSelf: 'flex-start', backgroundColor: 'rgba(245,158,11,0.16)', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  nativeBadgeText: { color: TUBE.gold, fontSize: 8, fontWeight: '900', letterSpacing: 1 },
  nativeTitle: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '800', marginTop: 4 },
  nativeSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },
  nativeCta: { backgroundColor: TUBE.gold, borderRadius: TRADIUS.full, paddingHorizontal: 14, paddingVertical: 8 },
  nativeCtaText: { color: TUBE.onAccent, fontSize: TFONT.xs, fontWeight: '900' },

  diningMember: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: 'rgba(34,211,238,0.06)', borderWidth: 1, borderColor: 'rgba(34,211,238,0.3)',
  },
  diningPromo: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line,
  },
  diningIcon: { width: 40, height: 40, borderRadius: 11, backgroundColor: 'rgba(34,211,238,0.12)', alignItems: 'center', justifyContent: 'center' },
  diningTitle: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '800' },
  diningSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },
});
