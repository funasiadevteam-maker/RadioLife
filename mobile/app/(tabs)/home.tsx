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
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';

const resolveImg = (u?: string | null) =>
  u ? (u.startsWith('http') ? u : `${BACKEND}${u}`) : null;

const CHIPS = [
  { key: 'all', label: 'All', path: null },
  { key: 'radio', label: 'Radio', path: '/(tabs)/listen' },
  { key: 'shop', label: 'Shop & Eat', path: '/(tabs)/shop' },
  { key: 'games', label: 'Play', path: '/(tabs)/games' },
  { key: 'news', label: 'News', path: '/(tabs)/news' },
  { key: 'trivia', label: 'Trivia', path: '/(tabs)/trivia' },
];

export default function HomeScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [channels, setChannels] = useState<any[]>([]);
  const [clips, setClips] = useState<any[]>([]);
  const [venues, setVenues] = useState<any[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [points, setPoints] = useState<number | null>(null);
  const [cityLabel, setCityLabel] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [chip, setChip] = useState('all');
  const [claimCode, setClaimCode] = useState<string | null>(null);

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const load = async () => {
    try {
      const [ch, cl, ve, nw, wl] = await Promise.allSettled([
        api.get('/channels'),
        api.get('/shell/clips', { params: { limit: 10 } }),
        api.get('/shell/venues', { params: { limit: 12 } }),
        api.get('/news/headlines', { params: { limit: 6 } }),
        api.get('/bigcoin/me'),
      ]);
      if (ch.status === 'fulfilled') setChannels((ch.value as any).data?.channels || []);
      if (cl.status === 'fulfilled') setClips((cl.value as any).data?.items || []);
      if (ve.status === 'fulfilled') setVenues((ve.value as any).data?.items || []);
      if (nw.status === 'fulfilled') setNews((nw.value as any).data?.items || []);
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

  const openClip = (c: any) => {
    if (c.sponsored && c.campaign_id) {
      api.post('/shell/clips/claim', { campaign_id: c.campaign_id })
        .then((r) => setClaimCode(r.data?.code || 'CLAIMED'))
        .catch(() => setClaimCode('Try again later'));
      return;
    }
    if (c.business_id) { router.push('/(tabs)/shop'); return; }
    router.push({ pathname: '/(tabs)/radio', params: { channel: c.slug } });
  };

  const onChip = (c: any) => { setChip(c.key); if (c.path) router.push(c.path); };

  if (authLoading || loading) {
    return <View style={s.center}><ActivityIndicator size="large" color={TUBE.electric} /></View>;
  }

  const firstName = user?.name?.split(' ')[0] || '';

  return (
    <View style={s.screen}>
      {/* Sticky header */}
      <View style={[s.header, { paddingTop: insets.top + 8 }]} testID="home-header">
        <Pressable onPress={() => setDrawer(true)} testID="home-menu-btn" style={s.iconBtn} hitSlop={8}>
          <Ionicons name="menu" size={24} color={TUBE.text} />
        </Pressable>
        <View style={s.brandRow}>
          <View style={s.brandDot} />
          <Text style={s.brand}>RadioLife</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <View style={s.pointsPill} testID="home-points-pill">
            <Ionicons name="diamond" size={12} color={TUBE.gold} />
            <Text style={s.pointsText}>{points != null ? points.toLocaleString() : '—'}</Text>
          </View>
          <Pressable onPress={() => router.push('/notifications')} testID="home-notif-btn" style={s.iconBtn} hitSlop={8}>
            <Ionicons name="notifications-outline" size={20} color={TUBE.textDim} />
          </Pressable>
        </View>
      </View>

      {/* Filter chips — single horizontal scroller, no wrap */}
      <View style={s.chipsWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ paddingHorizontal: TSPACE.md, gap: 8 }}>
          {CHIPS.map((c) => {
            const active = chip === c.key;
            return (
              <Pressable key={c.key} testID={`home-chip-${c.key}`} onPress={() => onChip(c)}
                style={[s.chip, active && s.chipActive]}>
                <Text style={[s.chipText, active && s.chipTextActive]}>{c.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      <ScrollView contentContainerStyle={{ paddingBottom: 40 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={TUBE.electric}
          onRefresh={() => { setRefreshing(true); load(); }} />}>

        {/* Greeting */}
        <View style={s.greetWrap}>
          <Text style={s.greet}>Hi{firstName ? `, ${firstName}` : ''} 👋</Text>
          <Text style={s.greetSub}>DIL SE · {(cityLabel || 'YOUR CITY').toUpperCase()} SE</Text>
        </View>

        {claimCode && (
          <Pressable style={s.claimBanner} testID="home-claim-banner" onPress={() => setClaimCode(null)}>
            <Ionicons name="ticket" size={16} color={TUBE.onAccent} />
            <Text style={s.claimText}>Offer claimed · code {claimCode}</Text>
            <Ionicons name="close" size={16} color={TUBE.onAccent} />
          </Pressable>
        )}

        {/* Your stations */}
        {channels.length > 0 && (
          <Shelf title="Your stations" suffix={`${channels.length} LIVE`}
            onSeeAll={() => router.push('/(tabs)/listen')}>
            {channels.slice(0, 12).map((ch) => (
              <Pressable key={ch.slug} testID={`home-station-${ch.slug}`} style={s.stationTile}
                onPress={() => router.push({ pathname: '/(tabs)/radio', params: { channel: ch.slug } })}>
                <Image source={{ uri: resolveImg(ch.cover_image_url || ch.thumbnail_url) || undefined }}
                  style={s.stationImg} contentFit="cover" transition={200} />
                <Text style={s.tileName} numberOfLines={1}>{ch.name}</Text>
                <Text style={s.tileSub} numberOfLines={1}>{ch.vibe || (ch.language_tags || []).join(', ') || 'Live'}</Text>
              </Pressable>
            ))}
          </Shelf>
        )}

        {/* Clips — 9:16 with sponsored first */}
        {clips.length > 0 && (
          <Shelf title="Clips" suffix="RJ MOMENTS">
            {clips.map((c) => (
              <Pressable key={c.id} testID={`home-clip-${c.id}`} style={s.clipCard} onPress={() => openClip(c)}>
                <Image source={{ uri: resolveImg(c.image) || undefined }} style={s.clipImg} contentFit="cover" transition={200} />
                <View style={s.clipOverlay} />
                {c.sponsored && (
                  <View style={s.sponsorBadge} testID={`home-clip-sponsored-${c.id}`}>
                    <Text style={s.sponsorBadgeText}>SPONSORED</Text>
                  </View>
                )}
                <View style={s.clipMeta}>
                  <Text style={s.clipTitle} numberOfLines={2}>{c.title}</Text>
                  <Text style={s.clipChannel} numberOfLines={1}>{c.channel}</Text>
                </View>
              </Pressable>
            ))}
          </Shelf>
        )}

        {/* Eat & earn near you */}
        {venues.length > 0 && (
          <Shelf title="Eat & earn near you"
            suffix={`${venues.length} VENUES${cityLabel ? ' · ' + cityLabel.toUpperCase() : ''}`}
            onSeeAll={() => router.push('/(tabs)/shop')}>
            {venues.slice(0, 10).map((v, idx) => (
              <Pressable key={v.business_id} testID={`home-venue-${v.business_id}`} style={s.venueCard}
                onPress={() => router.push('/(tabs)/shop')}>
                <Image source={{ uri: resolveImg(v.image) || undefined }} style={s.venueImg} contentFit="cover" transition={200} />
                {idx === 0 && v.sponsored && (
                  <View style={s.sponsorBadge}><Text style={s.sponsorBadgeText}>SPONSORED</Text></View>
                )}
                <View style={s.venueBody}>
                  <Text style={s.venueName} numberOfLines={1}>{v.name}</Text>
                  <View style={s.venueRow}>
                    <Text style={s.venueCat} numberOfLines={1}>{v.category_label}</Text>
                    {v.rating ? (
                      <View style={s.ratingChip}>
                        <Ionicons name="star" size={9} color={TUBE.gold} />
                        <Text style={s.ratingText}>{v.rating}</Text>
                      </View>
                    ) : null}
                  </View>
                  {v.earn ? <Text style={s.earnText}>Earn {v.earn} BigPoints</Text> : null}
                </View>
              </Pressable>
            ))}
          </Shelf>
        )}

        {/* Top headlines */}
        {news.length > 0 && (
          <Shelf title="Top headlines" suffix="NEWS" onSeeAll={() => router.push('/(tabs)/news')}>
            {news.slice(0, 6).map((n, idx) => (
              <Pressable key={n.id || idx} testID={`home-news-${idx}`} style={s.newsCard}
                onPress={() => router.push('/(tabs)/news')}>
                {resolveImg(n.image_url) ? (
                  <Image source={{ uri: resolveImg(n.image_url) || undefined }} style={s.newsImg} contentFit="cover" transition={200} />
                ) : <View style={[s.newsImg, { backgroundColor: TUBE.glass }]} />}
                <Text style={s.newsTitle} numberOfLines={3}>{n.headline_text || n.title || n.headline}</Text>
              </Pressable>
            ))}
          </Shelf>
        )}

        {/* Ways to earn CTA */}
        <Pressable style={s.earnCta} testID="home-earn-cta" onPress={() => router.push('/(tabs)/games')}>
          <View style={s.earnIcon}><Ionicons name="sparkles" size={20} color={TUBE.onAccent} /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.earnTitle}>Play & earn BigPoints</Text>
            <Text style={s.earnSub}>Spin, predict and win every day</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color={TUBE.textMuted} />
        </Pressable>
      </ScrollView>

      <TubeDrawer open={drawer} onClose={() => setDrawer(false)} />
    </View>
  );
}

function Shelf({ title, suffix, onSeeAll, children }:
  { title: string; suffix?: string; onSeeAll?: () => void; children: React.ReactNode }) {
  return (
    <View style={s.shelf}>
      <View style={s.shelfHead}>
        <View style={{ flex: 1 }}>
          <Text style={s.shelfTitle}>{title}</Text>
          {!!suffix && <Text style={s.shelfSuffix}>{suffix}</Text>}
        </View>
        {onSeeAll && (
          <Pressable onPress={onSeeAll} hitSlop={8}>
            <Text style={s.seeAll}>See all</Text>
          </Pressable>
        )}
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ paddingHorizontal: TSPACE.md, gap: 12 }}>
        {children}
      </ScrollView>
    </View>
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

  chipsWrap: { paddingVertical: 10, backgroundColor: TUBE.bg, borderBottomWidth: 1, borderBottomColor: TUBE.line },
  chip: {
    height: 34, paddingHorizontal: 14, borderRadius: TRADIUS.full, alignItems: 'center', justifyContent: 'center',
    backgroundColor: TUBE.glass, borderWidth: 1, borderColor: TUBE.line,
  },
  chipActive: { backgroundColor: TUBE.text, borderColor: TUBE.text },
  chipText: { color: TUBE.textDim, fontSize: TFONT.sm, fontWeight: '700' },
  chipTextActive: { color: TUBE.bg, fontWeight: '800' },

  greetWrap: { paddingHorizontal: TSPACE.md, paddingTop: TSPACE.lg, paddingBottom: TSPACE.sm },
  greet: { color: TUBE.text, fontSize: TFONT.xxl, fontWeight: '900', letterSpacing: -0.5 },
  greetSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 3, marginTop: 4 },

  claimBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginHorizontal: TSPACE.md, marginTop: 6,
    paddingHorizontal: 14, paddingVertical: 12, borderRadius: TRADIUS.md, backgroundColor: TUBE.gold,
  },
  claimText: { flex: 1, color: TUBE.onAccent, fontSize: TFONT.sm, fontWeight: '800' },

  shelf: { marginTop: TSPACE.lg },
  shelfHead: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: TSPACE.md, marginBottom: TSPACE.sm },
  shelfTitle: { color: TUBE.text, fontSize: TFONT.lg, fontWeight: '900', letterSpacing: -0.3 },
  shelfSuffix: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 2, marginTop: 2 },
  seeAll: { color: TUBE.electric, fontSize: TFONT.sm, fontWeight: '700' },

  stationTile: { width: 116 },
  stationImg: { width: 116, height: 116, borderRadius: TRADIUS.lg, backgroundColor: TUBE.elevated },
  tileName: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800', marginTop: 6 },
  tileSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 1 },

  clipCard: { width: 132, height: 216, borderRadius: TRADIUS.lg, overflow: 'hidden', backgroundColor: TUBE.elevated },
  clipImg: { ...StyleSheet.absoluteFillObject },
  clipOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.28)' },
  clipMeta: { position: 'absolute', left: 0, right: 0, bottom: 0, padding: 10 },
  clipTitle: { color: '#fff', fontSize: TFONT.sm, fontWeight: '800' },
  clipChannel: { color: 'rgba(255,255,255,0.8)', fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },
  sponsorBadge: {
    position: 'absolute', top: 8, left: 8, backgroundColor: TUBE.gold,
    borderRadius: TRADIUS.full, paddingHorizontal: 8, paddingVertical: 3, zIndex: 2,
  },
  sponsorBadgeText: { color: TUBE.onAccent, fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },

  venueCard: { width: 240, borderRadius: TRADIUS.lg, overflow: 'hidden', backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line },
  venueImg: { width: 240, height: 120, backgroundColor: TUBE.glass },
  venueBody: { padding: 12 },
  venueName: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '800' },
  venueRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 4 },
  venueCat: { color: TUBE.textDim, fontSize: TFONT.xs, fontWeight: '600', flex: 1 },
  ratingChip: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: TUBE.glass, borderRadius: TRADIUS.full, paddingHorizontal: 7, paddingVertical: 2 },
  ratingText: { color: TUBE.text, fontSize: TFONT.xs, fontWeight: '800' },
  earnText: { color: TUBE.green, fontSize: TFONT.xs, fontWeight: '800', marginTop: 6 },

  newsCard: { width: 220 },
  newsImg: { width: 220, height: 124, borderRadius: TRADIUS.md, backgroundColor: TUBE.elevated },
  newsTitle: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '700', marginTop: 8, lineHeight: 18 },

  earnCta: {
    flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: TSPACE.md, marginTop: TSPACE.xl,
    padding: TSPACE.md, borderRadius: TRADIUS.lg, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line,
  },
  earnIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: TUBE.electric, alignItems: 'center', justifyContent: 'center' },
  earnTitle: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '800' },
  earnSub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '600', marginTop: 2 },
});
