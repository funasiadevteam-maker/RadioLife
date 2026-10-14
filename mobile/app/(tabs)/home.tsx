import React, { useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator,
  RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Image } from 'expo-image';
import Animated, { FadeInDown, LinearTransition } from 'react-native-reanimated';
import { useAuth } from '../../src/contexts/AuthContext';
import api, { BACKEND } from '../../src/api/client';
import TubeDrawer from '../../src/components/TubeDrawer';
import BannerAdSlotV2 from '../../src/components/BannerAdSlotV2';
import { TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';
import { useAppTheme, useThemeTokens } from '../../src/theme/ThemeProvider';
import type { ThemeTokens } from '../../src/theme/tokens';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { useFeaturePrefs } from '../../src/stores/useFeaturePrefs';
import { playImportedStation } from '../../src/services/playStation';

const resolveImg = (u?: string | null) =>
  u ? (u.startsWith('http') ? u : `${BACKEND}${u}`) : null;

const SCOPE_CHIPS = [
  { key: 'foryou', label: 'For You' },
  { key: 'live', label: 'Live' },
  { key: 'trending', label: 'Trending' },
];

// Fallback verb when a social-wall item has no title/text of its own.
const FEED_VERB: Record<string, string> = {
  LISTEN_ROOM: 'is listening live — join the room',
  LIVE_VIDEO: 'is live right now',
  BUSINESS_LIVE: 'is live right now',
  EVENT: 'has an upcoming experience',
  TAROT_SHARE: 'shared a tarot reading',
  DREAM: 'shared a dream',
  CLUB_POST: 'posted in a club',
  MOMENT: 'shared a moment',
  STATION_ACTIVITY: 'posted a new update',
};

const fireEvent = (event: string, extra: Record<string, any> = {}) => {
  api.post('/shell/home-events', { event, surface: 'mobile', ...extra }).catch(() => {});
};

// Your FUUSIC World — ecosystem pillars, Social first & featured. Order +
// visibility are personalized per user via /api/social/features.
const FUUSIC_WORLD = [
  { key: 'social', label: 'Social', icon: 'people', to: '/(tabs)/social', bg: '#14b8a6', featured: true },
  { key: 'listen', label: 'Listen', icon: 'headset', to: '/(tabs)/listen', bg: '#a855f7' },
  { key: 'live', label: 'Live', icon: 'radio', to: '/(tabs)/social?tab=live', bg: '#f43f5e' },
  { key: 'shop', label: 'Shop', icon: 'storefront', to: '/(tabs)/shop', bg: '#ec4899' },
  { key: 'play', label: 'Play', icon: 'game-controller', to: '/(tabs)/games', bg: '#8b5cf6' },
  { key: 'dining', label: 'Dining', icon: 'restaurant', to: '/dining', bg: '#fb923c' },
  { key: 'earn', label: 'Earn', icon: 'diamond', to: '/(tabs)/wallet', bg: '#f59e0b' },
  { key: 'explore', label: 'Explore', icon: 'compass', to: '/(tabs)/social', bg: '#06b6d4' },
];
const WORLD_MAP = Object.fromEntries(FUUSIC_WORLD.map((p) => [p.key, p]));

export default function HomeScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { activeChannelName, activeChannelThumb, currentSeg, playing } = usePlayerStore();
  const { t, theme, cycle } = useAppTheme();
  const s = makeStyles(t);
  const featEnabled = useFeaturePrefs((st) => st.enabled);
  const featBootstrap = useFeaturePrefs((st) => st.bootstrap);
  useEffect(() => { featBootstrap(); }, [featBootstrap]);
  const worldPills = (featEnabled && featEnabled.length)
    ? featEnabled.map((k) => WORLD_MAP[k]).filter(Boolean)
    : FUUSIC_WORLD;

  const [home, setHome] = useState<any>(null);
  const [socialHome, setSocialHome] = useState<any>(null);
  const [feed, setFeed] = useState<any[]>([]);
  const [nearby, setNearby] = useState<any[]>([]);
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
      const [hm, wl, sh] = await Promise.allSettled([
        api.get('/shell/home'),
        api.get('/bigcoin/me'),
        api.get('/social/home'),
      ]);
      if (hm.status === 'fulfilled') setHome((hm.value as any).data || {});
      if (wl.status === 'fulfilled') setPoints((wl.value as any).data?.balance ?? null);
      if (sh.status === 'fulfilled') setSocialHome((sh.value as any).data || null);
      // Social wall preview — lead the home with real activity from your
      // circle; fall back to For-You discovery when Following is still empty.
      try {
        let fr = await api.get('/social/feed-v2', { params: { mode: 'following', limit: 4 } });
        let items = fr.data?.items || [];
        if (!items.length) {
          fr = await api.get('/social/feed-v2', { params: { mode: 'for_you', limit: 4 } });
          items = fr.data?.items || [];
        }
        setFeed(items);
      } catch { /* ignore */ }
      // Near you now — friends who just checked in / paid at a place you follow.
      try {
        const nr = await api.get('/social/friends-nearby');
        setNearby(nr.data?.items || []);
      } catch { /* ignore */ }
    } catch { /* ignore */ }
    finally { setLoading(false); setRefreshing(false); }
  };

  useEffect(() => { if (!authLoading && user) load(); }, [authLoading, user]);

  // Poll social so friends-live cards appear the moment friends go live.
  // Also quietly refresh the social wall + 'near you now' so new activity
  // slides in without a manual pull-down.
  useEffect(() => {
    if (!user) return undefined;
    const iv = setInterval(() => {
      api.get('/social/home').then((r) => setSocialHome(r.data || null)).catch(() => {});
      api.get('/social/feed-v2', { params: { mode: 'following', limit: 4 } })
        .then((r) => { const it = r.data?.items || []; if (it.length) setFeed(it); })
        .catch(() => {});
      api.get('/social/friends-nearby')
        .then((r) => setNearby(r.data?.items || []))
        .catch(() => {});
    }, 25000);
    return () => clearInterval(iv);
  }, [user]);

  useEffect(() => {
    if (!user) return;
    api.get('/geo/resolve_city').then((r) => {
      const c = r.data?.city;
      if (c && String(c).toLowerCase() !== 'global') setCityLabel(String(c));
    }).catch(() => {});
  }, [user]);

  if (authLoading || loading) {
    return <View style={s.center}><ActivityIndicator size="large" color={t.electric} /></View>;
  }

  const firstName = user?.name?.split(' ')[0] || '';
  const hasSession = !!activeChannelName;
  const forYouRaw: any[] = (Array.isArray(home?.mixed_for_you) && home.mixed_for_you.length)
    ? home.mixed_for_you
    : (home?.for_you || []);
  const liveNow: any[] = home?.live_now || [];
  const nativeOffer = home?.native_offer;
  const perMin = home?.listening_reward?.points_per_min ?? 1;
  const isPremium = !!home?.is_premium;
  const diningMember = !!home?.dining?.member;

  const happening = socialHome?.happening_now || {};
  const friendsActive = Number(happening.friends_online || happening.friends_listening || 0);
  const liveExp = Number(happening.live_experiences || 0);
  const socialReqs = Number(socialHome?.counts?.friend_requests || 0);
  const socialActive = friendsActive > 0 || liveExp > 0 || socialReqs > 0;
  const friendsNow: any[] = Array.isArray(socialHome?.friends_now) ? socialHome.friends_now : [];

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

  const openFeedItem = (it: any) => {
    fireEvent('home_feed_open', { item_id: it.id, item_type: it.type });
    const tgt = it.cta?.target;
    switch (it.cta?.action) {
      case 'open_room': router.push(`/social/room/${tgt}` as any); break;
      case 'open_live': router.push('/(tabs)/social?tab=live' as any); break;
      case 'open_dream': router.push('/social/dreams' as any); break;
      case 'open_tarot': router.push('/social/tarot' as any); break;
      case 'open_station': router.push('/stations' as any); break;
      default: router.push('/(tabs)/social' as any); break;
    }
  };

  return (
    <View style={s.screen}>
      {/* Sticky header */}
      <View style={[s.header, { paddingTop: insets.top + 8 }]} testID="home-header">
        <Pressable onPress={() => setDrawer(true)} testID="home-menu-btn" style={s.iconBtn} hitSlop={8}>
          <Ionicons name="menu" size={24} color={t.text} />
        </Pressable>
        <View style={s.brandRow}>
          <View style={s.brandDot} />
          <Text style={s.brand}>FUUSIC</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Pressable style={s.pointsPill} testID="home-points-pill" onPress={() => router.push('/(tabs)/wallet')} hitSlop={6}>
            <Ionicons name="diamond" size={12} color={t.gold} />
            <Text style={s.pointsText}>{points != null ? points.toLocaleString() : '—'}</Text>
          </Pressable>
          <Pressable onPress={() => router.push('/notifications')} testID="home-notif-btn" style={s.iconBtn} hitSlop={8}>
            <Ionicons name="notifications-outline" size={20} color={t.textDim} />
          </Pressable>
          <Pressable onPress={cycle} testID="home-appearance-btn" style={s.iconBtn} hitSlop={8}>
            <Ionicons name={theme === 'dark' ? 'sunny-outline' : 'moon-outline'} size={20} color={t.textDim} />
          </Pressable>
        </View>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={t.electric}
          onRefresh={() => { setRefreshing(true); load(); }} />}>

        {/* Greeting */}
        <View style={s.greetWrap}>
          <Text style={s.greetSub}>{new Date().getHours() < 12 ? 'GOOD MORNING' : new Date().getHours() < 18 ? 'GOOD AFTERNOON' : 'GOOD EVENING'}</Text>
          <Text style={s.greet}>Hi{firstName ? `, ${firstName}` : ''} — everything you love, together.</Text>
        </View>

        {/* SOCIAL-FIRST: lead the home with your live social wall — real
            activity from the people, stations & places you follow. */}
        {feed.length > 0 && (
          <View style={s.shelf}>
            <View style={s.shelfHead}>
              <View style={{ flex: 1 }}>
                <Text style={s.shelfTitle}>Your Social Wall</Text>
                <Text style={s.shelfSuffix}>FROM PEOPLE & PLACES YOU FOLLOW</Text>
              </View>
              <Pressable onPress={() => { fireEvent('home_feed_see_all'); router.push('/(tabs)/social'); }} hitSlop={8}>
                <Text style={s.seeAll}>See all</Text>
              </Pressable>
            </View>
            <View style={{ paddingHorizontal: TSPACE.md, gap: 10 }}>
              {feed.slice(0, 3).map((it, i) => (
                <Animated.View key={it.id || i}
                  entering={FadeInDown.duration(350).springify()}
                  layout={LinearTransition.springify()}>
                  <Pressable testID={`home-feed-${i}`} style={s.feedCard} onPress={() => openFeedItem(it)}>
                    <View style={s.feedAvatarWrap}>
                      {it.actor?.avatar_url
                        ? <Image source={{ uri: resolveImg(it.actor.avatar_url) || undefined }} style={s.feedAvatar} contentFit="cover" transition={150} />
                        : <View style={[s.feedAvatar, s.feedAvatarFallback]}><Text style={s.feedInitial}>{(it.actor?.name || '?').slice(0, 1).toUpperCase()}</Text></View>}
                      {it.meta?.live && <View style={s.feedLiveDot} />}
                    </View>
                    <View style={{ flex: 1, minWidth: 0 }}>
                      <View style={s.feedTopRow}>
                        <Text style={s.feedActor} numberOfLines={1}>{it.actor?.name || 'Someone'}</Text>
                        {it.meta?.live && <View style={s.feedLivePill}><Text style={s.feedLivePillTxt}>LIVE</Text></View>}
                      </View>
                      <Text style={s.feedText} numberOfLines={2}>
                        {it.title || it.text || FEED_VERB[it.type] || 'shared an update'}
                      </Text>
                    </View>
                    {it.media_url
                      ? <Image source={{ uri: resolveImg(it.media_url) || undefined }} style={s.feedThumb} contentFit="cover" transition={150} />
                      : <View style={s.feedCta}><Text style={s.feedCtaTxt}>{it.cta?.label || 'Open'}</Text></View>}
                  </Pressable>
                </Animated.View>
              ))}
            </View>
          </View>
        )}

        {/* Near you now — friends who just checked in / paid at a place you
            follow. Real check-in signals only; hidden when there are none. */}
        {nearby.length > 0 && (
          <View style={s.shelf}>
            <View style={s.shelfHead}>
              <View style={{ flex: 1 }}>
                <Text style={s.shelfTitle}>Near you now</Text>
                <Text style={s.shelfSuffix}>FRIENDS AT PLACES YOU FOLLOW</Text>
              </View>
            </View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: TSPACE.md, gap: 12 }}>
              {nearby.map((n, i) => (
                <Animated.View key={`${n.user_id}-${n.business_id}`}
                  entering={FadeInDown.duration(350).springify()}
                  layout={LinearTransition.springify()}>
                  <Pressable testID={`home-nearby-${i}`} style={s.nearbyCard}
                    onPress={() => { fireEvent('home_nearby_click', { business_id: n.business_id }); router.push(`/store/${n.business_id}` as any); }}>
                    <View style={s.nearbyMedia}>
                      {n.business_logo
                        ? <Image source={{ uri: resolveImg(n.business_logo) || undefined }} style={s.nearbyLogo} contentFit="cover" transition={150} />
                        : <View style={[s.nearbyLogo, s.nearbyLogoFallback]}><Ionicons name="storefront" size={20} color={t.electric} /></View>}
                      <View style={s.nearbyAvatarWrap}>
                        {n.avatar_url
                          ? <Image source={{ uri: resolveImg(n.avatar_url) || undefined }} style={s.nearbyAvatar} contentFit="cover" transition={150} />
                          : <View style={[s.nearbyAvatar, s.nearbyAvatarFallback]}><Text style={s.nearbyInitial}>{(n.name || '?').slice(0, 1).toUpperCase()}</Text></View>}
                      </View>
                    </View>
                    <Text style={s.nearbyName} numberOfLines={1}>{n.name}</Text>
                    <Text style={s.nearbyCtx} numberOfLines={1}>{n.activity === 'paid' ? 'paid at' : 'checked in at'}</Text>
                    <Text style={s.nearbyBiz} numberOfLines={1}>{n.business_name}</Text>
                  </Pressable>
                </Animated.View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* What's Happening Now — Social bridge (real data / honest empty) */}
        {socialActive ? (
          <Pressable style={s.socialCard} testID="home-social-happening"
            onPress={() => { fireEvent('home_whats_happening_click'); router.push('/(tabs)/social'); }}>
            <View style={s.socialIcon}><Ionicons name="people" size={20} color="#fff" /></View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.socialLabel}>WHAT&apos;S HAPPENING NOW</Text>
              <Text style={s.socialTitle} numberOfLines={1}>
                {friendsActive > 0
                  ? `${friendsActive} friend${friendsActive === 1 ? '' : 's'} active right now`
                  : `${liveExp} live experience${liveExp === 1 ? '' : 's'} happening`}
              </Text>
              <Text style={s.socialSub} numberOfLines={1}>
                {socialReqs > 0 ? `${socialReqs} friend request${socialReqs === 1 ? '' : 's'} · ` : ''}Do something together
              </Text>
            </View>
            <View style={s.socialCta}><Text style={s.socialCtaText}>Join</Text></View>
          </Pressable>
        ) : (
          <Pressable style={s.socialCard} testID="home-social-discover"
            onPress={() => { fireEvent('home_whats_happening_click'); router.push('/(tabs)/social'); }}>
            <View style={s.socialIcon}><Ionicons name="people" size={20} color="#fff" /></View>
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.socialLabel}>SOCIAL</Text>
              <Text style={s.socialTitle} numberOfLines={1}>Do things together</Text>
              <Text style={s.socialSub} numberOfLines={1}>Listen together, join clubs & share Moments</Text>
            </View>
            <View style={s.socialCta}><Text style={s.socialCtaText}>Explore</Text></View>
          </Pressable>
        )}

        {/* Friends live now — real avatars + join listening room */}
        {friendsNow.length > 0 && (
          <View style={s.shelf}>
            <View style={s.shelfHead}><Text style={s.shelfTitle}>Friends live now</Text></View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ paddingHorizontal: TSPACE.md, gap: 12 }}>
              {friendsNow.slice(0, 8).map((f, i) => (
                <Pressable key={f.user_id || i} testID={`home-friend-live-${i}`} style={s.friendCard}
                  onPress={() => { fireEvent('home_whats_happening_click', { kind: 'friend' }); router.push((f.room_id ? `/social/room/${f.room_id}` : '/(tabs)/social') as any); }}>
                  <View style={s.friendAvatarWrap}>
                    {f.avatar_url
                      ? <Image source={{ uri: resolveImg(f.avatar_url) || undefined }} style={s.friendAvatar} contentFit="cover" transition={150} />
                      : <View style={[s.friendAvatar, s.friendAvatarFallback]}><Text style={s.friendInitial}>{(f.name || '?').slice(0, 1).toUpperCase()}</Text></View>}
                    <View style={s.friendLiveDot} />
                  </View>
                  <Text style={s.friendName} numberOfLines={1}>{f.name || 'Friend'}</Text>
                  <Text style={s.friendCtx} numberOfLines={1}>{f.context ? `to ${f.context}` : 'listening'}</Text>
                </Pressable>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Your FUUSIC World — the whole ecosystem, Social first */}
        <View style={s.worldWrap}>
          <Text style={s.worldHead}>Your FUUSIC World</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false}
            contentContainerStyle={{ paddingHorizontal: TSPACE.md, gap: 10 }}>
            {worldPills.map((p) => (
              <Pressable key={p.key} testID={`home-pillar-${p.key}`} style={[s.pill, p.featured && s.pillFeatured]}
                onPress={() => { fireEvent(`home_${p.key}_click`); router.push(p.to as any); }}>
                <View style={[s.pillIcon, { backgroundColor: p.bg }]}>
                  <Ionicons name={p.icon as any} size={16} color={p.featured ? t.onAccent : '#fff'} />
                </View>
                <Text style={[s.pillLabel, p.featured && s.pillLabelFeatured]}>{p.label}</Text>
              </Pressable>
            ))}
          </ScrollView>
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
            <View style={s.continuePlay}><Ionicons name={playing ? 'pause' : 'play'} size={22} color={t.onAccent} /></View>
          </Pressable>
        ) : (
          <Pressable style={s.startCard} testID="home-start" onPress={() => router.push('/(tabs)/radio')}>
            <View style={{ flex: 1 }}>
              <Text style={s.startKicker}>YOUR RADIO, ONE TAP AWAY</Text>
              <Text style={s.startTitle}>Start My Radio</Text>
              <Text style={s.startSub}>AI-personalized radio built around what you love</Text>
            </View>
            <View style={s.startPlay}><Ionicons name="play" size={26} color={t.onAccent} /></View>
          </Pressable>
        )}

        {/* B · For You */}
        <View style={s.shelf}>
          <View style={s.shelfHead}>
            <View style={{ flex: 1 }}>
              <Text style={s.shelfTitle}>For You</Text>
              <Text style={s.shelfSuffix}>STATIONS · MOMENTS · LIVE · PLAY</Text>
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
              {forYou.map((st, i) => {
                const isStation = !st.type || st.type === 'station';
                const img = st.art || st.image;
                const nm = st.name || st.title;
                const sub = st.city || st.subtitle || 'Radio';
                return (
                  <Pressable key={st.id || st.slug || i} testID={`home-foryou-${st.id || st.slug || i}`} style={s.stationTile}
                    onPress={() => {
                      if (isStation) { playCard({ id: st.id, name: nm, art: img }); }
                      else { fireEvent('home_pillar_click', { kind: st.type }); router.push(st.to as any); }
                    }}>
                    <Image source={{ uri: resolveImg(img) || undefined }} style={s.stationImg} contentFit="cover" transition={200} />
                    {st.type && !isStation && !st.live
                      ? <View style={s.typeBadge}><Text style={s.typeBadgeText}>{(st.badge || st.type).toUpperCase()}</Text></View>
                      : st.live ? <View style={s.liveBadge}><Text style={s.liveBadgeText}>LIVE</Text></View> : null}
                    <Text style={s.tileName} numberOfLines={1}>{nm}</Text>
                    <Text style={s.tileSub} numberOfLines={1}>{sub}</Text>
                  </Pressable>
                );
              })}
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
          <View style={s.rewardIcon}><Ionicons name="diamond" size={18} color={t.gold} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.rewardTitle}>Earn +{perMin} BigPoint{perMin === 1 ? '' : 's'} every minute you listen</Text>
            <Text style={s.rewardSub}>Your BigPoints stack up in the background</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={t.gold} />
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
          <View style={s.diningIcon}><Ionicons name="restaurant" size={18} color={t.electric} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.diningTitle}>{diningMember ? 'Your Dining Club' : 'FUUSIC Dining Club'}</Text>
            <Text style={s.diningSub}>{diningMember ? "Pick this week's meals · spin for tonight" : 'Spin the wheel · $9.99 meals near you'}</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={t.textMuted} />
        </Pressable>

        {/* H · Display ad — Free listeners only */}
        {!isPremium && (
          <View style={{ marginTop: TSPACE.lg }} testID="home-display-ad">
            <BannerAdSlotV2 slotKey="inline_mpu_1" pageRoute="/home" />
          </View>
        )}
      </ScrollView>

      <TubeDrawer open={drawer} onClose={() => setDrawer(false)} />
    </View>
  );
}

function DoMore({ icon, label, sub, onPress, testID }:
  { icon: any; label: string; sub: string; onPress: () => void; testID: string }) {
  const t = useThemeTokens();
  const s = makeStyles(t);
  return (
    <Pressable style={s.doMoreCard} onPress={onPress} testID={testID}>
      <View style={s.doMoreIcon}><Ionicons name={icon} size={18} color={t.electric} /></View>
      <Text style={s.doMoreLabel} numberOfLines={1}>{label}</Text>
      <Text style={s.doMoreSub} numberOfLines={1}>{sub}</Text>
    </Pressable>
  );
}

function NativeOffer({ offer, onPress }: { offer: any; onPress: () => void }) {
  const t = useThemeTokens();
  const s = makeStyles(t);
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

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: t.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: TSPACE.md, paddingBottom: 10, backgroundColor: t.bg,
    borderBottomWidth: 1, borderBottomColor: t.line,
  },
  iconBtn: { padding: 4 },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  brandDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: t.electric },
  brand: { color: t.text, fontSize: TFONT.lg, fontWeight: '900', letterSpacing: -0.3 },
  pointsPill: {
    flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, height: 30,
    borderRadius: TRADIUS.full, backgroundColor: t.glass, borderWidth: 1, borderColor: t.line,
  },
  pointsText: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },

  greetWrap: { paddingHorizontal: TSPACE.md, paddingTop: TSPACE.lg, paddingBottom: TSPACE.sm },
  greetSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 3, marginBottom: 4 },
  greet: { color: t.text, fontSize: TFONT.xxl, fontWeight: '900', letterSpacing: -0.5 },

  worldWrap: { marginTop: 4, marginBottom: 6 },
  worldHead: { color: t.text, fontSize: TFONT.lg, fontWeight: '900', letterSpacing: -0.3, paddingHorizontal: TSPACE.md, marginBottom: TSPACE.sm },
  pill: {
    alignItems: 'center', gap: 6, paddingVertical: 10, paddingHorizontal: 12, minWidth: 74,
    borderRadius: TRADIUS.lg, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line,
  },
  pillFeatured: { backgroundColor: 'rgba(20,184,166,0.12)', borderColor: 'rgba(20,184,166,0.5)' },
  pillIcon: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  pillLabel: { color: t.textDim, fontSize: TFONT.xs, fontWeight: '800' },
  pillLabelFeatured: { color: t.text },

  socialCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: 8,
    padding: TSPACE.md, borderRadius: TRADIUS.lg,
    backgroundColor: 'rgba(20,184,166,0.08)', borderWidth: 1, borderColor: 'rgba(20,184,166,0.35)',
  },
  socialIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: '#14b8a6' },
  socialLabel: { color: '#5eead4', fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  socialTitle: { color: t.text, fontSize: TFONT.md, fontWeight: '800', marginTop: 2 },
  socialSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },
  socialCta: { backgroundColor: '#14b8a6', borderRadius: TRADIUS.full, paddingHorizontal: 14, paddingVertical: 8 },
  socialCtaText: { color: t.onAccent, fontSize: TFONT.xs, fontWeight: '900' },

  continueCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: 6,
    padding: TSPACE.sm + 2, borderRadius: TRADIUS.lg, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line,
  },
  continueImg: { width: 64, height: 64, borderRadius: TRADIUS.md, backgroundColor: t.glass },
  continueLabel: { color: t.electric, fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  continueName: { color: t.text, fontSize: TFONT.md, fontWeight: '800', marginTop: 2 },
  continueSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },
  continuePlay: { width: 46, height: 46, borderRadius: 23, backgroundColor: t.electric, alignItems: 'center', justifyContent: 'center' },

  startCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: 6,
    padding: TSPACE.md, borderRadius: TRADIUS.xl, backgroundColor: t.magenta,
  },
  startKicker: { color: 'rgba(255,255,255,0.85)', fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  startTitle: { color: '#fff', fontSize: TFONT.xl, fontWeight: '900', marginTop: 2 },
  startSub: { color: 'rgba(255,255,255,0.9)', fontSize: TFONT.xs, fontWeight: '600', marginTop: 3 },
  startPlay: { width: 52, height: 52, borderRadius: 26, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center' },

  shelf: { marginTop: TSPACE.lg },
  shelfHead: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: TSPACE.md, marginBottom: TSPACE.sm },
  shelfTitle: { color: t.text, fontSize: TFONT.lg, fontWeight: '900', letterSpacing: -0.3 },
  shelfSuffix: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 2, marginTop: 2 },
  seeAll: { color: t.electric, fontSize: TFONT.sm, fontWeight: '700' },
  emptyRail: { color: t.textMuted, fontSize: TFONT.sm, paddingHorizontal: TSPACE.md, paddingVertical: 12 },

  scopeRow: { flexDirection: 'row', gap: 8, paddingHorizontal: TSPACE.md, marginBottom: TSPACE.sm },
  scopeChip: { height: 32, paddingHorizontal: 14, borderRadius: TRADIUS.full, alignItems: 'center', justifyContent: 'center', backgroundColor: t.glass, borderWidth: 1, borderColor: t.line },
  scopeChipActive: { backgroundColor: t.text, borderColor: t.text },
  scopeChipText: { color: t.textDim, fontSize: TFONT.sm, fontWeight: '700' },
  scopeChipTextActive: { color: t.bg, fontWeight: '800' },

  stationTile: { width: 116 },
  stationImg: { width: 116, height: 116, borderRadius: TRADIUS.lg, backgroundColor: t.elevated },
  tileName: { color: t.text, fontSize: TFONT.sm, fontWeight: '800', marginTop: 6 },
  tileSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },
  liveBadge: { position: 'absolute', top: 8, left: 8, backgroundColor: t.live, borderRadius: TRADIUS.full, paddingHorizontal: 7, paddingVertical: 2 },
  liveBadgeText: { color: '#fff', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  typeBadge: { position: 'absolute', top: 8, left: 8, backgroundColor: 'rgba(124,58,237,0.92)', borderRadius: TRADIUS.full, paddingHorizontal: 7, paddingVertical: 2 },
  typeBadgeText: { color: '#fff', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },

  friendCard: { width: 96, alignItems: 'center' },
  friendAvatarWrap: { width: 72, height: 72, marginBottom: 6 },
  friendAvatar: { width: 72, height: 72, borderRadius: 36, backgroundColor: t.elevated, borderWidth: 2, borderColor: '#14b8a6' },
  friendAvatarFallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: '#14b8a6' },
  friendInitial: { color: '#fff', fontSize: TFONT.xl, fontWeight: '900' },
  friendLiveDot: { position: 'absolute', bottom: 2, right: 6, width: 14, height: 14, borderRadius: 7, backgroundColor: t.live, borderWidth: 2, borderColor: t.bg },
  friendName: { color: t.text, fontSize: TFONT.sm, fontWeight: '800', textAlign: 'center' },
  friendCtx: { color: '#5eead4', fontSize: TFONT.xs, fontWeight: '600', textAlign: 'center' },
  sponsorBadge: { position: 'absolute', top: 8, left: 8, backgroundColor: t.gold, borderRadius: TRADIUS.full, paddingHorizontal: 7, paddingVertical: 2 },
  sponsorBadgeText: { color: t.onAccent, fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },

  feedCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: TSPACE.sm + 2, borderRadius: TRADIUS.lg,
    backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line,
  },
  feedAvatarWrap: { width: 46, height: 46 },
  feedAvatar: { width: 46, height: 46, borderRadius: 23, backgroundColor: t.glass },
  feedAvatarFallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: t.brand },
  feedInitial: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900' },
  feedLiveDot: { position: 'absolute', bottom: 0, right: 0, width: 13, height: 13, borderRadius: 7, backgroundColor: t.live, borderWidth: 2, borderColor: t.elevated },
  feedTopRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  feedActor: { color: t.text, fontSize: TFONT.sm, fontWeight: '800', flexShrink: 1 },
  feedLivePill: { backgroundColor: t.live, borderRadius: TRADIUS.full, paddingHorizontal: 6, paddingVertical: 1 },
  feedLivePillTxt: { color: '#fff', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  feedText: { color: t.textDim, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },
  feedThumb: { width: 52, height: 52, borderRadius: TRADIUS.md, backgroundColor: t.glass },
  feedCta: { backgroundColor: t.brand, borderRadius: TRADIUS.full, paddingHorizontal: 14, paddingVertical: 8 },
  feedCtaTxt: { color: t.onAccent, fontSize: TFONT.xs, fontWeight: '900' },

  nearbyCard: { width: 128, padding: TSPACE.sm, borderRadius: TRADIUS.lg, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line },
  nearbyMedia: { width: 64, height: 64, marginBottom: 8 },
  nearbyLogo: { width: 64, height: 64, borderRadius: TRADIUS.md, backgroundColor: t.glass },
  nearbyLogoFallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(34,211,238,0.12)' },
  nearbyAvatarWrap: { position: 'absolute', bottom: -4, right: -4 },
  nearbyAvatar: { width: 30, height: 30, borderRadius: 15, borderWidth: 2, borderColor: t.elevated, backgroundColor: t.glass },
  nearbyAvatarFallback: { alignItems: 'center', justifyContent: 'center', backgroundColor: t.brand },
  nearbyInitial: { color: '#fff', fontSize: TFONT.xs, fontWeight: '900' },
  nearbyName: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  nearbyCtx: { color: t.textMuted, fontSize: 10, fontWeight: '700', marginTop: 1 },
  nearbyBiz: { color: t.electric, fontSize: TFONT.xs, fontWeight: '700', marginTop: 1 },

  rewardCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: 'rgba(245,158,11,0.06)', borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)',
  },
  rewardIcon: { width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(245,158,11,0.15)', alignItems: 'center', justifyContent: 'center' },
  rewardTitle: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  rewardSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },

  doMoreRow: { flexDirection: 'row', gap: 10, paddingHorizontal: TSPACE.md },
  doMoreCard: { flex: 1, padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line },
  doMoreIcon: { width: 38, height: 38, borderRadius: 11, backgroundColor: 'rgba(34,211,238,0.15)', alignItems: 'center', justifyContent: 'center', marginBottom: 8 },
  doMoreLabel: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  doMoreSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },

  nativeCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.sm + 2, borderRadius: TRADIUS.lg, backgroundColor: 'rgba(245,158,11,0.05)', borderWidth: 1, borderColor: 'rgba(245,158,11,0.25)',
  },
  nativeImg: { width: 64, height: 64, borderRadius: TRADIUS.md, backgroundColor: t.glass },
  nativeBadge: { alignSelf: 'flex-start', backgroundColor: 'rgba(245,158,11,0.16)', borderRadius: 4, paddingHorizontal: 6, paddingVertical: 2 },
  nativeBadgeText: { color: t.gold, fontSize: 8, fontWeight: '900', letterSpacing: 1 },
  nativeTitle: { color: t.text, fontSize: TFONT.md, fontWeight: '800', marginTop: 4 },
  nativeSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },
  nativeCta: { backgroundColor: t.gold, borderRadius: TRADIUS.full, paddingHorizontal: 14, paddingVertical: 8 },
  nativeCtaText: { color: t.onAccent, fontSize: TFONT.xs, fontWeight: '900' },

  diningMember: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: 'rgba(34,211,238,0.06)', borderWidth: 1, borderColor: 'rgba(34,211,238,0.3)',
  },
  diningPromo: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.lg,
    padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line,
  },
  diningIcon: { width: 40, height: 40, borderRadius: 11, backgroundColor: 'rgba(34,211,238,0.12)', alignItems: 'center', justifyContent: 'center' },
  diningTitle: { color: t.text, fontSize: TFONT.md, fontWeight: '800' },
  diningSub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },
});
