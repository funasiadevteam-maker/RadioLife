import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { BACKEND } from '../../src/api/client';
import { SPACING, FONT, RADIUS } from '../../src/constants/theme';
import { useThemeTokens } from '../../src/theme/ThemeProvider';
import type { ThemeTokens } from '../../src/theme/tokens';
import SafeImage from '../../src/components/SafeImage';
import BannerAdSlotV2 from '../../src/components/BannerAdSlotV2';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { useStationsStore } from '../../src/stores/useStationsStore';
import { playImportedStation } from '../../src/services/playStation';
import { useResponsive } from '../../src/hooks/useResponsive';

const resolveImg = (u?: string | null) =>
  u ? (u.startsWith('http') ? u : `${BACKEND}${u}`) : null;

const COUNTRY_NAMES: Record<string, string> = {
  US: 'USA', IN: 'India', AE: 'UAE', GB: 'UK', CA: 'Canada', AU: 'Australia',
  FR: 'France', DE: 'Germany', IT: 'Italy', ES: 'Spain', BR: 'Brazil', MX: 'Mexico',
  PK: 'Pakistan', SA: 'Saudi Arabia', NG: 'Nigeria', ZA: 'S. Africa', JP: 'Japan',
  KR: 'Korea', RU: 'Russia', NL: 'Netherlands', SE: 'Sweden', TR: 'Turkey',
  EG: 'Egypt', ID: 'Indonesia', PH: 'Philippines',
};
const flagOf = (cc?: string) => {
  if (!cc || cc.length !== 2) return '🌐';
  try { return String.fromCodePoint(...[...cc.toUpperCase()].map((c) => 127397 + c.charCodeAt(0))); }
  catch { return '🌐'; }
};

// Weighted rotation — a higher bid earns more slots in the playlist.
function buildWeightedOrder(items: any[]): any[] {
  if (!items.length) return [];
  const weights = items.map((x) => Math.max(1, Math.round((x.bid_cents || 100) / 100)));
  const minW = Math.min(...weights);
  const slots = weights.map((w) => Math.min(6, Math.max(1, Math.round(w / minW))));
  const order: any[] = [];
  const remaining = slots.slice();
  let added = true;
  while (added) {
    added = false;
    for (let i = 0; i < items.length; i++) {
      if (remaining[i] > 0) { order.push(items[i]); remaining[i] -= 1; added = true; }
    }
  }
  return order;
}

function StationTile({ st, onPress }: { st: any; onPress: () => void }) {
  const tk = useThemeTokens();
  const t = makeT(tk);
  const sub = st.country || (st.language ? String(st.language).split(',')[0] : '') || 'Live';
  return (
    <TouchableOpacity style={t.tile} onPress={onPress} testID={`listen-station-${st.id || st.slug}`} activeOpacity={0.85}>
      <SafeImage uri={resolveImg(st.favicon || st.logo_url || st.cover_image_url || st.thumbnail_url)} fallbackText={st.name} size={116} borderRadius={RADIUS.lg} />
      <Text style={t.name} numberOfLines={1}>{st.name}</Text>
      <Text style={t.sub} numberOfLines={1}>{st.tagline || sub}</Text>
    </TouchableOpacity>
  );
}

const makeT = (tk: ThemeTokens) => StyleSheet.create({
  tile: { width: 116 },
  name: { color: tk.text, fontSize: FONT.sm, fontWeight: '700', marginTop: 6 },
  sub: { color: tk.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
});

export default function ListenScreen() {
  const tk = useThemeTokens();
  const t = makeT(tk);
  const s = makeS(tk);
  const router = useRouter();
  const r = useResponsive();
  const { activeChannelName, activeChannelThumb, currentSeg, playing } = usePlayerStore();
  const { recents, load: loadSaved } = useStationsStore();

  const [rails, setRails] = useState<Record<string, any[]>>({});
  const [facets, setFacets] = useState<Record<string, any[]>>({});
  const [aiChannels, setAiChannels] = useState<any[]>([]);
  const [podcasts, setPodcasts] = useState<any[]>([]);
  const [clips, setClips] = useState<any[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [sponsoredList, setSponsoredList] = useState<any[]>([]);
  const [sponsoredIdx, setSponsoredIdx] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [disc, chans, pods, cl, nw] = await Promise.allSettled([
        api.get('/radio/discover'),
        api.get('/channels'),
        api.get('/podcasts/discover'),
        api.get('/shell/clips', { params: { limit: 10 } }),
        api.get('/news/headlines', { params: { limit: 6 } }),
      ]);
      if (disc.status === 'fulfilled') {
        const map: Record<string, any[]> = {};
        const fac: Record<string, any[]> = {};
        (disc.value.data.rails || []).forEach((r: any) => {
          map[r.id] = r.stations || [];
          if (r.facet_chips) fac[r.id] = r.facet_chips;
        });
        setRails(map);
        setFacets(fac);
      }
      if (chans.status === 'fulfilled') setAiChannels(chans.value.data.channels || []);
      if (pods.status === 'fulfilled') setPodcasts(pods.value.data.channels || []);
      if (cl.status === 'fulfilled') setClips((cl.value as any).data?.items || []);
      if (nw.status === 'fulfilled') setNews((nw.value as any).data?.items || []);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadSaved(); loadAll(); }, [loadAll, loadSaved]);

  // Sponsored Play — rotate several promoted stations for airtime.
  useEffect(() => {
    let alive = true;
    api.get('/promoted/stations', { params: { limit: 6 } })
      .then((r) => { if (alive) setSponsoredList(((r.data && r.data.items) || [])); })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

  const rotationOrder = buildWeightedOrder(sponsoredList);
  useEffect(() => {
    if (rotationOrder.length < 2) return;
    const timer = setInterval(() => setSponsoredIdx((i) => i + 1), 7000);
    return () => clearInterval(timer);
  }, [rotationOrder.length]);

  const sponsored = rotationOrder.length ? rotationOrder[sponsoredIdx % rotationOrder.length] : null;

  useEffect(() => {
    if (sponsored?.promo_id) api.post(`/promoted/${sponsored.promo_id}/impression`).catch(() => {});
  }, [sponsored?.promo_id]);

  const playSponsored = () => {
    if (sponsored?.promo_id) api.post(`/promoted/${sponsored.promo_id}/click`).catch(() => {});
    playImportedStation(sponsored, router);
  };

  const continueStation = activeChannelName
    ? { name: activeChannelName, sub: currentSeg?.track_artist || 'Live now', thumb: activeChannelThumb, onPress: () => router.push('/now-playing') }
    : recents[0]
    ? { name: recents[0].name, sub: [recents[0].country, recents[0].language].filter(Boolean).join(' · ') || 'Recently played', thumb: recents[0].favicon || recents[0].logo_url, onPress: () => playImportedStation(recents[0], router) }
    : null;

  const flagship = [...(rails.for_you || []), ...(rails.local || [])].filter((x) => x.is_flagship)
    .filter((x, i, arr) => arr.findIndex((y) => y.id === x.id) === i).slice(0, 10);

  const Rail = ({ id, icon, title, stations, more }: { id: string; icon: any; title: string; stations: any[]; more?: () => void }) =>
    stations && stations.length ? (
      <View testID={`listen-rail-${id}`}>
        <View style={s.sectionHeader}>
          <Ionicons name={icon} size={16} color={tk.primary} />
          <Text style={s.sectionTitle}>{title}</Text>
          {more && <TouchableOpacity onPress={more} testID={`listen-more-${id}`}><Text style={s.more}>Explore more</Text></TouchableOpacity>}
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
          {stations.slice(0, 12).map((st) => <StationTile key={st.id || st.slug} st={st} onPress={() => playImportedStation(st, router)} />)}
        </ScrollView>
      </View>
    ) : null;

  return (
    <SafeAreaView style={s.screen} testID="listen-screen">
      <ScrollView contentContainerStyle={[{ paddingBottom: 110 }, r.feed]}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadAll(); }} tintColor={tk.primary} />}>
        <View style={s.header}>
          <Text style={s.pageTitle}>Listen</Text>
          <Text style={s.pageSub}>Live radio, AI channels & podcasts</Text>
        </View>

        {continueStation && (
          <TouchableOpacity style={s.continueCard} onPress={continueStation.onPress} testID="listen-continue" activeOpacity={0.85}>
            <SafeImage uri={resolveImg(continueStation.thumb)} fallbackText={continueStation.name} size={54} borderRadius={14} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.continueLabel}>CONTINUE LISTENING</Text>
              <Text style={s.continueName} numberOfLines={1}>{continueStation.name}</Text>
              <Text style={s.continueSub} numberOfLines={1}>{continueStation.sub}</Text>
            </View>
            <View style={s.continuePlay}><Ionicons name={playing && activeChannelName ? 'pause' : 'play'} size={20} color="#fff" /></View>
          </TouchableOpacity>
        )}

        {sponsored && (
          <TouchableOpacity style={s.sponsoredCard} onPress={playSponsored} testID="listen-sponsored" activeOpacity={0.85}>
            <SafeImage uri={resolveImg(sponsored.logo_url || sponsored.favicon || sponsored.art)} fallbackText={sponsored.name} size={54} borderRadius={14} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <View style={s.sponsoredBadge}><Text style={s.sponsoredBadgeText}>SPONSORED</Text></View>
              <Text style={s.continueName} numberOfLines={1}>{sponsored.name}</Text>
              <Text style={s.continueSub} numberOfLines={1}>{sponsored.sponsor_name || sponsored.country || 'Live now'}</Text>
            </View>
            <View style={s.continuePlay}><Ionicons name="play" size={20} color="#fff" /></View>
          </TouchableOpacity>
        )}

        {loading ? (
          <View style={s.loadWrap}><ActivityIndicator size="large" color={tk.primary} /></View>
        ) : (
          <>
            {/* For You — personalized top stations */}
            <Rail id="for_you" icon="sparkles" title="Made for you" stations={rails.for_you || []} more={() => router.push('/stations')} />

            {/* Explore by Country — flags */}
            {(facets.countries || []).length > 0 && (
              <View testID="listen-countries">
                <View style={s.sectionHeader}>
                  <Ionicons name="earth" size={16} color={tk.primary} />
                  <Text style={s.sectionTitle}>Explore by Country</Text>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {(facets.countries || []).slice(0, 12).map((c) => (
                    <TouchableOpacity key={c.slug} style={s.countryChip} testID={`listen-country-${c.slug}`}
                      onPress={() => router.push({ pathname: '/stations', params: { country: c.slug } })} activeOpacity={0.85}>
                      <Text style={s.countryFlag}>{flagOf(c.slug)}</Text>
                      <Text style={s.countryLabel} numberOfLines={1}>{COUNTRY_NAMES[c.slug] || c.label}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
            )}

            {/* Browse by Genre — cards */}
            {(facets.genres || []).length > 0 && (
              <View testID="listen-genres">
                <View style={s.sectionHeader}>
                  <Ionicons name="musical-notes" size={16} color={tk.primary} />
                  <Text style={s.sectionTitle}>Browse by Genre</Text>
                </View>
                <View style={s.genreGrid}>
                  {(facets.genres || []).slice(0, 8).map((g) => (
                    <TouchableOpacity key={g.slug} style={s.genreCard} testID={`listen-genre-${g.slug}`}
                      onPress={() => router.push({ pathname: '/stations', params: { category: g.slug } })} activeOpacity={0.85}>
                      <Text style={s.genreCardText} numberOfLines={1}>{g.label}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </View>
            )}

            {/* Purchasable ad slot — v2 rotation (local business banners) */}
            <BannerAdSlotV2 slotKey="inline_mpu_1" pageRoute="/listen" />

            {/* Trending */}
            <Rail id="trending" icon="flame" title="Trending now" stations={rails.trending || []} more={() => router.push('/stations')} />

            {/* AI stations (bigFM AI channels) */}
            {aiChannels.length > 0 && (
              <View testID="listen-rail-ai">
                <View style={s.sectionHeader}>
                  <Ionicons name="radio" size={16} color={tk.primary} />
                  <Text style={s.sectionTitle}>AI stations</Text>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {aiChannels.map((ch) => (
                    <TouchableOpacity key={ch.slug} style={t.tile} onPress={() => router.push({ pathname: '/(tabs)/radio', params: { channel: ch.slug } })} testID={`listen-ai-${ch.slug}`} activeOpacity={0.85}>
                      <SafeImage uri={resolveImg(ch.cover_image_url || ch.thumbnail_url)} fallbackText={ch.name} size={116} borderRadius={RADIUS.lg} />
                      <Text style={t.name} numberOfLines={1}>{ch.name}</Text>
                      <Text style={t.sub} numberOfLines={1}>{ch.tagline || 'AI radio'}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
            )}

            {/* Flagship */}
            <Rail id="flagship" icon="star" title="Flagship stations" stations={flagship} />

            {/* Local live radio (by country) */}
            <Rail id="local" icon="location" title="Local live radio" stations={rails.local || []} more={() => router.push('/stations')} />

            {/* 40k+ CTA */}
            <View style={s.sectionHeader}>
              <Ionicons name="globe" size={16} color={tk.primary} />
              <Text style={s.sectionTitle}>Stations worldwide</Text>
            </View>
            <TouchableOpacity style={s.worldCta} onPress={() => router.push('/stations')} testID="listen-all-stations" activeOpacity={0.85}>
              <View style={s.worldIcon}><Ionicons name="globe-outline" size={22} color="#fff" /></View>
              <View style={{ flex: 1 }}>
                <Text style={s.worldTitle}>Explore live stations worldwide</Text>
                <Text style={s.worldSub}>Search by country, language &amp; genre</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={tk.textMuted} />
            </TouchableOpacity>

            {/* Podcasts — two rows */}
            <View style={s.sectionHeader}>
              <Ionicons name="mic" size={16} color={tk.primary} />
              <Text style={s.sectionTitle}>Podcasts</Text>
              {podcasts.length > 0 && <TouchableOpacity onPress={() => router.push('/podcasts')} testID="listen-more-podcasts"><Text style={s.more}>More podcasts</Text></TouchableOpacity>}
            </View>
            {podcasts.length === 0 ? (
              <View style={s.emptyRail} testID="listen-podcasts-empty">
                <Ionicons name="mic-outline" size={26} color={tk.textMuted} />
                <Text style={s.emptyRailText}>Podcasts are coming soon</Text>
                <Text style={s.emptyRailSub}>Top-listened & AI-recommended shows will appear here.</Text>
              </View>
            ) : (
              <>
                <Text style={s.rowLabel}>Top listened</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {podcasts.slice(0, 10).map((p) => (
                    <TouchableOpacity key={(p.channel_id || p.id) + '-t'} style={t.tile} onPress={() => router.push(`/podcast/channel/${p.channel_id || p.id}`)} activeOpacity={0.85}>
                      <SafeImage uri={resolveImg(p.cover_image_url || p.artwork_url)} fallbackText={p.title || p.name} size={116} borderRadius={RADIUS.lg} />
                      <Text style={t.name} numberOfLines={1}>{p.title || p.name}</Text>
                      <Text style={t.sub} numberOfLines={1}>{p.creator_name || 'Podcast'}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
                <Text style={s.rowLabel}>Recommended for you</Text>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {podcasts.slice(0, 10).map((p) => (
                    <TouchableOpacity key={(p.channel_id || p.id) + '-r'} style={t.tile} onPress={() => router.push(`/podcast/channel/${p.channel_id || p.id}`)} activeOpacity={0.85}>
                      <SafeImage uri={resolveImg(p.cover_image_url || p.artwork_url)} fallbackText={p.title || p.name} size={116} borderRadius={RADIUS.lg} />
                      <Text style={t.name} numberOfLines={1}>{p.title || p.name}</Text>
                      <Text style={t.sub} numberOfLines={1}>{p.creator_name || 'Podcast'}</Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </>
            )}

            {/* Clips — RJ moments (moved off Home) */}
            {clips.length > 0 && (
              <View testID="listen-clips">
                <View style={s.sectionHeader}>
                  <Ionicons name="film" size={16} color={tk.primary} />
                  <Text style={s.sectionTitle}>Clips</Text>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {clips.map((c) => (
                    <TouchableOpacity key={c.id} testID={`listen-clip-${c.id}`} activeOpacity={0.85}
                      style={{ width: 128, height: 210, borderRadius: RADIUS.lg, overflow: 'hidden', backgroundColor: tk.card }}
                      onPress={() => (c.business_id ? router.push('/(tabs)/shop') : router.push('/(tabs)/radio'))}>
                      <SafeImage uri={resolveImg(c.image)} fallbackText={c.title} size={128} borderRadius={0} style={{ position: 'absolute', width: 128, height: 210 }} />
                      <View style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: 9, backgroundColor: 'rgba(0,0,0,0.45)' }}>
                        {c.sponsored && (
                          <View style={{ alignSelf: 'flex-start', backgroundColor: tk.gold, borderRadius: RADIUS.full, paddingHorizontal: 7, paddingVertical: 2, marginBottom: 4 }}>
                            <Text style={{ color: '#0a0a0c', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 }}>SPONSORED</Text>
                          </View>
                        )}
                        <Text style={{ color: '#fff', fontSize: FONT.sm, fontWeight: '800' }} numberOfLines={2}>{c.title}</Text>
                        <Text style={{ color: 'rgba(255,255,255,0.8)', fontSize: FONT.xs, fontWeight: '600', marginTop: 2 }} numberOfLines={1}>{c.channel}</Text>
                      </View>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
            )}

            {/* News — headlines (moved off Home) */}
            {news.length > 0 && (
              <View testID="listen-news">
                <View style={s.sectionHeader}>
                  <Ionicons name="newspaper" size={16} color={tk.primary} />
                  <Text style={s.sectionTitle}>News</Text>
                  <TouchableOpacity onPress={() => router.push('/(tabs)/news')} testID="listen-more-news"><Text style={s.more}>News Radio</Text></TouchableOpacity>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {news.slice(0, 6).map((n, idx) => (
                    <TouchableOpacity key={n.id || idx} testID={`listen-news-${idx}`} activeOpacity={0.85}
                      style={{ width: 220 }} onPress={() => router.push('/(tabs)/news')}>
                      <SafeImage uri={resolveImg(n.image_url)} fallbackText={n.headline_text || n.title || 'News'} size={220} borderRadius={RADIUS.md} style={{ height: 124 }} />
                      <Text style={{ color: tk.text, fontSize: FONT.sm, fontWeight: '700', marginTop: 8, lineHeight: 18 }} numberOfLines={3}>
                        {n.headline_text || n.title || n.headline}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>
              </View>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const makeS = (tk: ThemeTokens) => StyleSheet.create({
  screen: { flex: 1, backgroundColor: tk.bg },
  header: { paddingHorizontal: SPACING.md, paddingTop: SPACING.md, paddingBottom: SPACING.sm },
  pageTitle: { color: tk.text, fontSize: 30, fontWeight: '900' },
  pageSub: { color: tk.textMuted, fontSize: FONT.sm, fontWeight: '600', marginTop: 2 },
  loadWrap: { paddingVertical: 60, alignItems: 'center' },
  continueCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, marginBottom: SPACING.md, padding: SPACING.sm + 2,
    borderRadius: RADIUS.lg, backgroundColor: tk.card, borderWidth: 1, borderColor: tk.cardBorder,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2,
  },
  continueLabel: { color: tk.primary, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  continueName: { color: tk.text, fontSize: FONT.md, fontWeight: '800', marginTop: 2 },
  continueSub: { color: tk.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  continuePlay: { width: 40, height: 40, borderRadius: 20, backgroundColor: tk.primary, alignItems: 'center', justifyContent: 'center' },
  sponsoredCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, marginBottom: SPACING.md, padding: SPACING.sm + 2,
    borderRadius: RADIUS.lg, backgroundColor: tk.card, borderWidth: 1, borderColor: tk.gold,
  },
  sponsoredBadge: { alignSelf: 'flex-start', backgroundColor: tk.gold, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2, marginBottom: 4 },
  sponsoredBadgeText: { color: '#0a0a0c', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: SPACING.md, marginTop: SPACING.md, marginBottom: SPACING.sm },
  sectionTitle: { color: tk.text, fontSize: FONT.lg, fontWeight: '800', flex: 1 },
  more: { color: tk.secondary, fontSize: FONT.sm, fontWeight: '700' },
  railContent: { paddingHorizontal: SPACING.md, gap: SPACING.sm },
  countryChip: { width: 84, alignItems: 'center', gap: 6, paddingVertical: 12, borderRadius: RADIUS.lg, backgroundColor: tk.card, borderWidth: 1, borderColor: tk.cardBorder },
  countryFlag: { fontSize: 28, lineHeight: 32 },
  countryLabel: { color: tk.text, fontSize: FONT.xs, fontWeight: '800', textAlign: 'center', paddingHorizontal: 4 },
  genreGrid: { flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: SPACING.md, gap: 10 },
  genreCard: { width: '48%', height: 60, borderRadius: RADIUS.lg, backgroundColor: tk.primary, justifyContent: 'flex-end', padding: 12 },
  genreCardText: { color: '#fff', fontSize: FONT.md, fontWeight: '900', textTransform: 'capitalize' },
  rowLabel: { color: tk.textDim, fontSize: FONT.sm, fontWeight: '700', paddingHorizontal: SPACING.md, marginTop: SPACING.sm, marginBottom: 6 },
  worldCta: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, padding: SPACING.md, borderRadius: RADIUS.lg,
    backgroundColor: tk.card, borderWidth: 1, borderColor: tk.cardBorder,
  },
  worldIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: tk.secondary, alignItems: 'center', justifyContent: 'center' },
  worldTitle: { color: tk.text, fontSize: FONT.md, fontWeight: '800' },
  worldSub: { color: tk.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  emptyRail: { alignItems: 'center', gap: 4, paddingVertical: 24, marginHorizontal: SPACING.md },
  emptyRailText: { color: tk.text, fontSize: FONT.md, fontWeight: '800' },
  emptyRailSub: { color: tk.textMuted, fontSize: FONT.xs, fontWeight: '600', textAlign: 'center' },
});
