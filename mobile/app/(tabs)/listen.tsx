import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { BACKEND } from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import SafeImage from '../../src/components/SafeImage';
import AdBanner from '../../src/components/AdBanner';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { useStationsStore } from '../../src/stores/useStationsStore';
import { playImportedStation } from '../../src/services/playStation';

const resolveImg = (u?: string | null) =>
  u ? (u.startsWith('http') ? u : `${BACKEND}${u}`) : null;

function StationTile({ st, onPress }: { st: any; onPress: () => void }) {
  const sub = st.country || (st.language ? String(st.language).split(',')[0] : '') || 'Live';
  return (
    <TouchableOpacity style={t.tile} onPress={onPress} testID={`listen-station-${st.id || st.slug}`} activeOpacity={0.85}>
      <SafeImage uri={resolveImg(st.favicon || st.logo_url || st.cover_image_url || st.thumbnail_url)} fallbackText={st.name} size={116} borderRadius={RADIUS.lg} />
      <Text style={t.name} numberOfLines={1}>{st.name}</Text>
      <Text style={t.sub} numberOfLines={1}>{st.tagline || sub}</Text>
    </TouchableOpacity>
  );
}

const t = StyleSheet.create({
  tile: { width: 116 },
  name: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', marginTop: 6 },
  sub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
});

export default function ListenScreen() {
  const router = useRouter();
  const { activeChannelName, activeChannelThumb, currentSeg, playing } = usePlayerStore();
  const { recents, load: loadSaved } = useStationsStore();

  const [rails, setRails] = useState<Record<string, any[]>>({});
  const [aiChannels, setAiChannels] = useState<any[]>([]);
  const [podcasts, setPodcasts] = useState<any[]>([]);
  const [clips, setClips] = useState<any[]>([]);
  const [news, setNews] = useState<any[]>([]);
  const [sponsored, setSponsored] = useState<any>(null);
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
        (disc.value.data.rails || []).forEach((r: any) => { map[r.id] = r.stations || []; });
        setRails(map);
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

  // Sponsored Play — one paid/promoted station pinned near the top.
  useEffect(() => {
    let alive = true;
    api.get('/promoted/stations', { params: { limit: 1 } })
      .then((r) => {
        const sp = ((r.data && r.data.items) || [])[0];
        if (alive && sp) {
          setSponsored(sp);
          if (sp.promo_id) api.post(`/promoted/${sp.promo_id}/impression`).catch(() => {});
        }
      })
      .catch(() => {});
    return () => { alive = false; };
  }, []);

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
          <Ionicons name={icon} size={16} color={COLORS.primary} />
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
      <ScrollView contentContainerStyle={{ paddingBottom: 110 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadAll(); }} tintColor={COLORS.primary} />}>
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
          <View style={s.loadWrap}><ActivityIndicator size="large" color={COLORS.primary} /></View>
        ) : (
          <>
            {/* For You — personalized top stations */}
            <Rail id="for_you" icon="sparkles" title="Made for you" stations={rails.for_you || []} more={() => router.push('/stations')} />

            {/* Purchasable ad slot */}
            <AdBanner zone="browse_row" />

            {/* Trending */}
            <Rail id="trending" icon="flame" title="Trending now" stations={rails.trending || []} more={() => router.push('/stations')} />

            {/* AI stations (bigFM AI channels) */}
            {aiChannels.length > 0 && (
              <View testID="listen-rail-ai">
                <View style={s.sectionHeader}>
                  <Ionicons name="radio" size={16} color={COLORS.primary} />
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
              <Ionicons name="globe" size={16} color={COLORS.primary} />
              <Text style={s.sectionTitle}>Stations worldwide</Text>
            </View>
            <TouchableOpacity style={s.worldCta} onPress={() => router.push('/stations')} testID="listen-all-stations" activeOpacity={0.85}>
              <View style={s.worldIcon}><Ionicons name="globe-outline" size={22} color="#fff" /></View>
              <View style={{ flex: 1 }}>
                <Text style={s.worldTitle}>Explore 40,000+ live stations</Text>
                <Text style={s.worldSub}>Search by country, language & genre</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
            </TouchableOpacity>

            {/* Podcasts — two rows */}
            <View style={s.sectionHeader}>
              <Ionicons name="mic" size={16} color={COLORS.primary} />
              <Text style={s.sectionTitle}>Podcasts</Text>
              {podcasts.length > 0 && <TouchableOpacity onPress={() => router.push('/podcasts')} testID="listen-more-podcasts"><Text style={s.more}>More podcasts</Text></TouchableOpacity>}
            </View>
            {podcasts.length === 0 ? (
              <View style={s.emptyRail} testID="listen-podcasts-empty">
                <Ionicons name="mic-outline" size={26} color={COLORS.textMuted} />
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
                  <Ionicons name="film" size={16} color={COLORS.primary} />
                  <Text style={s.sectionTitle}>Clips</Text>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {clips.map((c) => (
                    <TouchableOpacity key={c.id} testID={`listen-clip-${c.id}`} activeOpacity={0.85}
                      style={{ width: 128, height: 210, borderRadius: RADIUS.lg, overflow: 'hidden', backgroundColor: COLORS.card }}
                      onPress={() => (c.business_id ? router.push('/(tabs)/shop') : router.push('/(tabs)/radio'))}>
                      <SafeImage uri={resolveImg(c.image)} fallbackText={c.title} size={128} borderRadius={0} style={{ position: 'absolute', width: 128, height: 210 }} />
                      <View style={{ position: 'absolute', left: 0, right: 0, bottom: 0, padding: 9, backgroundColor: 'rgba(0,0,0,0.45)' }}>
                        {c.sponsored && (
                          <View style={{ alignSelf: 'flex-start', backgroundColor: COLORS.gold, borderRadius: RADIUS.full, paddingHorizontal: 7, paddingVertical: 2, marginBottom: 4 }}>
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
                  <Ionicons name="newspaper" size={16} color={COLORS.primary} />
                  <Text style={s.sectionTitle}>News</Text>
                  <TouchableOpacity onPress={() => router.push('/(tabs)/news')} testID="listen-more-news"><Text style={s.more}>News Radio</Text></TouchableOpacity>
                </View>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                  {news.slice(0, 6).map((n, idx) => (
                    <TouchableOpacity key={n.id || idx} testID={`listen-news-${idx}`} activeOpacity={0.85}
                      style={{ width: 220 }} onPress={() => router.push('/(tabs)/news')}>
                      <SafeImage uri={resolveImg(n.image_url)} fallbackText={n.headline_text || n.title || 'News'} size={220} borderRadius={RADIUS.md} style={{ height: 124 }} />
                      <Text style={{ color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', marginTop: 8, lineHeight: 18 }} numberOfLines={3}>
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

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { paddingHorizontal: SPACING.md, paddingTop: SPACING.md, paddingBottom: SPACING.sm },
  pageTitle: { color: COLORS.text, fontSize: 30, fontWeight: '900' },
  pageSub: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '600', marginTop: 2 },
  loadWrap: { paddingVertical: 60, alignItems: 'center' },
  continueCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, marginBottom: SPACING.md, padding: SPACING.sm + 2,
    borderRadius: RADIUS.lg, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.05, shadowRadius: 8, elevation: 2,
  },
  continueLabel: { color: COLORS.primary, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  continueName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800', marginTop: 2 },
  continueSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  continuePlay: { width: 40, height: 40, borderRadius: 20, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  sponsoredCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, marginBottom: SPACING.md, padding: SPACING.sm + 2,
    borderRadius: RADIUS.lg, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.gold,
  },
  sponsoredBadge: { alignSelf: 'flex-start', backgroundColor: COLORS.gold, borderRadius: RADIUS.full, paddingHorizontal: 8, paddingVertical: 2, marginBottom: 4 },
  sponsoredBadgeText: { color: '#0a0a0c', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: SPACING.md, marginTop: SPACING.md, marginBottom: SPACING.sm },
  sectionTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800', flex: 1 },
  more: { color: COLORS.secondary, fontSize: FONT.sm, fontWeight: '700' },
  railContent: { paddingHorizontal: SPACING.md, gap: SPACING.sm },
  rowLabel: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700', paddingHorizontal: SPACING.md, marginTop: SPACING.sm, marginBottom: 6 },
  worldCta: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, padding: SPACING.md, borderRadius: RADIUS.lg,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  worldIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: COLORS.secondary, alignItems: 'center', justifyContent: 'center' },
  worldTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  worldSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  emptyRail: { alignItems: 'center', gap: 4, paddingVertical: 24, marginHorizontal: SPACING.md },
  emptyRailText: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  emptyRailSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', textAlign: 'center' },
});
