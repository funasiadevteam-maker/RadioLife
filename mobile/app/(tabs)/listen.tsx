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
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { useStationsStore } from '../../src/stores/useStationsStore';
import { playImportedStation } from '../../src/services/playStation';

const resolveImg = (u?: string | null) =>
  u ? (u.startsWith('http') ? u : `${BACKEND}${u}`) : null;

export default function ListenScreen() {
  const router = useRouter();
  const { activeChannelName, activeChannelThumb, currentSeg, playing } = usePlayerStore();
  const { recents, load: loadSaved } = useStationsStore();

  const [flagships, setFlagships] = useState<any[]>([]);
  const [aiChannels, setAiChannels] = useState<any[]>([]);
  const [podcasts, setPodcasts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const loadAll = useCallback(async () => {
    try {
      const [flag, chans, pods] = await Promise.allSettled([
        api.get('/radio/browse', { params: { source: 'imported', limit: 20 } }),
        api.get('/channels'),
        api.get('/podcasts/discover'),
      ]);
      if (flag.status === 'fulfilled') {
        const items = (flag.value.data.items || []) as any[];
        const flags = items.filter((s) => s.is_flagship);
        setFlagships((flags.length ? flags : items).slice(0, 10));
      }
      if (chans.status === 'fulfilled') setAiChannels(chans.value.data.channels || []);
      if (pods.status === 'fulfilled') setPodcasts(pods.value.data.channels || []);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadSaved(); loadAll(); }, [loadAll, loadSaved]);

  // What to show in "Continue listening"
  const continueStation = activeChannelName
    ? { name: activeChannelName, sub: currentSeg?.track_artist || 'Live', thumb: activeChannelThumb, onPress: () => router.push('/now-playing') }
    : recents[0]
    ? { name: recents[0].name, sub: [recents[0].country, recents[0].language].filter(Boolean).join(' · ') || 'Recently played', thumb: recents[0].favicon || recents[0].logo_url, onPress: () => playImportedStation(recents[0], router) }
    : null;

  return (
    <SafeAreaView style={s.screen} testID="listen-screen">
      <ScrollView
        contentContainerStyle={{ paddingBottom: 110 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); loadAll(); }} tintColor={COLORS.primary} />}
      >
        {/* Header */}
        <View style={s.header}>
          <Text style={s.pageTitle}>Listen</Text>
          <Text style={s.pageSub}>Live radio, AI channels & podcasts</Text>
        </View>

        {/* Continue listening */}
        {continueStation && (
          <TouchableOpacity style={s.continueCard} onPress={continueStation.onPress} testID="listen-continue" activeOpacity={0.85}>
            <SafeImage uri={resolveImg(continueStation.thumb)} fallbackText={continueStation.name} size={54} borderRadius={14} />
            <View style={{ flex: 1, minWidth: 0 }}>
              <Text style={s.continueLabel}>CONTINUE LISTENING</Text>
              <Text style={s.continueName} numberOfLines={1}>{continueStation.name}</Text>
              <Text style={s.continueSub} numberOfLines={1}>{continueStation.sub}</Text>
            </View>
            <View style={s.continuePlay}>
              <Ionicons name={playing && activeChannelName ? 'pause' : 'play'} size={20} color="#fff" />
            </View>
          </TouchableOpacity>
        )}

        {loading ? (
          <View style={s.loadWrap}><ActivityIndicator size="large" color={COLORS.primary} /></View>
        ) : (
          <>
            {/* Flagship stations */}
            <SectionHeader icon="star" title="Flagship stations" />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
              {flagships.map((st) => (
                <TouchableOpacity key={st.id} style={s.tile} onPress={() => playImportedStation(st, router)} testID={`listen-flagship-${st.id}`} activeOpacity={0.85}>
                  <SafeImage uri={st.favicon || st.logo_url} fallbackText={st.name} size={110} borderRadius={RADIUS.lg} />
                  <Text style={s.tileName} numberOfLines={1}>{st.name}</Text>
                  <Text style={s.tileSub} numberOfLines={1}>{st.country || 'Live'}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* AI stations */}
            <SectionHeader icon="sparkles" title="AI stations" />
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
              {aiChannels.map((ch) => (
                <TouchableOpacity key={ch.slug} style={s.tile} onPress={() => router.push({ pathname: '/(tabs)/radio', params: { channel: ch.slug } })} testID={`listen-ai-${ch.slug}`} activeOpacity={0.85}>
                  <SafeImage uri={resolveImg(ch.cover_image_url || ch.thumbnail_url)} fallbackText={ch.name} size={110} borderRadius={RADIUS.lg} />
                  <Text style={s.tileName} numberOfLines={1}>{ch.name}</Text>
                  <Text style={s.tileSub} numberOfLines={1}>{ch.tagline || 'AI radio'}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>

            {/* 40k+ stations CTA */}
            <SectionHeader icon="globe" title="Stations worldwide" />
            <TouchableOpacity style={s.worldCta} onPress={() => router.push('/stations')} testID="listen-all-stations" activeOpacity={0.85}>
              <View style={s.worldIcon}><Ionicons name="globe-outline" size={22} color="#fff" /></View>
              <View style={{ flex: 1 }}>
                <Text style={s.worldTitle}>Explore 40,000+ live stations</Text>
                <Text style={s.worldSub}>Search by country, language & genre</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={COLORS.textMuted} />
            </TouchableOpacity>

            {/* Podcasts */}
            <SectionHeader icon="mic" title="Podcasts" />
            {podcasts.length === 0 ? (
              <View style={s.emptyRail} testID="listen-podcasts-empty">
                <Ionicons name="mic-outline" size={26} color={COLORS.textMuted} />
                <Text style={s.emptyRailText}>No podcasts yet — check back soon.</Text>
              </View>
            ) : (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.railContent}>
                {podcasts.map((p) => (
                  <TouchableOpacity key={p.channel_id || p.id} style={s.tile} onPress={() => router.push(`/podcast/channel/${p.channel_id || p.id}`)} testID={`listen-podcast-${p.channel_id || p.id}`} activeOpacity={0.85}>
                    <SafeImage uri={resolveImg(p.cover_image_url || p.artwork_url)} fallbackText={p.title || p.name} size={110} borderRadius={RADIUS.lg} />
                    <Text style={s.tileName} numberOfLines={1}>{p.title || p.name}</Text>
                    <Text style={s.tileSub} numberOfLines={1}>{p.creator_name || 'Podcast'}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const SectionHeader = ({ icon, title }: { icon: any; title: string }) => (
  <View style={s.sectionHeader}>
    <Ionicons name={icon} size={16} color={COLORS.primary} />
    <Text style={s.sectionTitle}>{title}</Text>
  </View>
);

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
    shadowColor: COLORS.cardShadow, shadowOffset: { width: 0, height: 2 }, shadowOpacity: 1, shadowRadius: 8, elevation: 2,
  },
  continueLabel: { color: COLORS.primary, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  continueName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800', marginTop: 2 },
  continueSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  continuePlay: { width: 40, height: 40, borderRadius: 20, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: SPACING.md, marginTop: SPACING.md, marginBottom: SPACING.sm },
  sectionTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800' },
  railContent: { paddingHorizontal: SPACING.md, gap: SPACING.sm },
  tile: { width: 110 },
  tileName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', marginTop: 6 },
  tileSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  worldCta: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    marginHorizontal: SPACING.md, padding: SPACING.md, borderRadius: RADIUS.lg,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  worldIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: COLORS.secondary, alignItems: 'center', justifyContent: 'center' },
  worldTitle: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  worldSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  emptyRail: { alignItems: 'center', gap: 6, paddingVertical: 24, marginHorizontal: SPACING.md },
  emptyRailText: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '600' },
});
