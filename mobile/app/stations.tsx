import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, TextInput, FlatList, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { BACKEND } from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import SafeImage from '../src/components/SafeImage';
import { usePlayerStore } from '../src/stores/usePlayerStore';
import { registerPlayer, releaseCurrent } from '../src/services/audioController';
import { updateNowPlaying } from '../src/services/nativePlayerBridge';

import { useStationsStore } from '../src/stores/useStationsStore';

let createAudioPlayer: any;
try {
  const mod = require('expo-audio');
  createAudioPlayer = mod.createAudioPlayer;
} catch {}

const LANGS = ['All', 'hindi', 'english', 'arabic', 'urdu', 'punjabi', 'tamil', 'malayalam'];
const GENRES = ['All', 'bollywood', 'punjabi', 'hindi', 'news', 'talk', 'sports', 'devotional', 'pop', 'rock', 'edm', 'classical', 'jazz'];
const COUNTRIES: { label: string; value: string }[] = [
  { label: 'All', value: 'All' },
  { label: 'UAE', value: 'AE' },
  { label: 'India', value: 'IN' },
  { label: 'USA', value: 'US' },
  { label: 'UK', value: 'GB' },
  { label: 'Pakistan', value: 'PK' },
  { label: 'Saudi', value: 'SA' },
  { label: 'Germany', value: 'DE' },
];
const MODES = [
  { id: 'browse', label: 'Browse', icon: 'globe-outline' },
  { id: 'favorites', label: 'Favorites', icon: 'heart-outline' },
  { id: 'recent', label: 'Recent', icon: 'time-outline' },
] as const;
const PAGE_SIZE = 30;

type Station = {
  id: string;
  name: string;
  favicon?: string | null;
  logo_url?: string | null;
  country?: string | null;
  language?: string | null;
  source?: string;
  is_flagship?: boolean;
  stream_url?: string | null;
};

export default function StationsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<Station[]>([]);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [lang, setLang] = useState('All');
  const [country, setCountry] = useState('All');
  const [genre, setGenre] = useState('All');
  const [mode, setMode] = useState<'browse' | 'favorites' | 'recent'>('browse');
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failed, setFailed] = useState(false);
  const [nowPlayingId, setNowPlayingId] = useState<string | null>(null);
  const [promoted, setPromoted] = useState<any[]>([]);

  const { setActiveChannel, setCurrentSeg, setPlaying, setSession } = usePlayerStore();
  const { favorites, recents, load: loadSaved, isFavorite, toggleFavorite, addRecent } = useStationsStore();

  useEffect(() => { loadSaved(); }, [loadSaved]);

  // Sponsored / promoted stations pinned to the top of Browse.
  useEffect(() => {
    api.get('/promoted/stations?limit=6').then((r) => {
      const items = r.data?.items || [];
      setPromoted(items);
      items.forEach((p: any) => {
        if (p.promo_id) api.post(`/promoted/${p.promo_id}/impression`).catch(() => {});
      });
    }).catch(() => {});
  }, []);

  // Debounce the search box
  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 400);
    return () => clearTimeout(t);
  }, [query]);

  const fetchPage = useCallback(async (pg: number, replace: boolean) => {
    try {
      if (replace) setLoading(true); else setLoadingMore(true);
      const params: any = { source: 'imported', page: pg, limit: PAGE_SIZE };
      if (debounced) params.q = debounced;
      if (lang !== 'All') params.language = lang;
      if (country !== 'All') params.country = country;
      if (genre !== 'All') params.category = genre;
      const r = await api.get('/radio/browse', { params });
      const next = (r.data.items || []) as Station[];
      setTotal(r.data.total || 0);
      setItems((prev) => (replace ? next : [...prev, ...next]));
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, [debounced, lang, country, genre]);

  // Reload when search/lang changes
  useEffect(() => { setPage(1); fetchPage(1, true); }, [fetchPage]);

  const loadMore = () => {
    if (loadingMore || loading || items.length >= total) return;
    const nextPage = page + 1;
    setPage(nextPage);
    fetchPage(nextPage, false);
  };

  const playStation = async (st: Station) => {
    if (!createAudioPlayer) {
      Alert.alert('Audio', 'Audio module not available in this preview.');
      return;
    }
    try {
      const r = await api.post(`/radio/play/${st.id}`);
      const data = r.data || {};
      const streamUrl = data.stream_url || st.stream_url;
      if (data.mode === 'ai' && data.channel_slug) {
        router.push({ pathname: '/(tabs)/radio', params: { channel: data.channel_slug } });
        return;
      }
      if (!streamUrl) {
        Alert.alert('Unavailable', 'This station has no playable stream right now.');
        return;
      }
      releaseCurrent();
      // A direct live stream is NOT an AI radio session — clear session id
      // so the Radio screen's skip/segment logic stays dormant.
      setSession(null);
      const player = createAudioPlayer(streamUrl);
      registerPlayer(player);
      player.play();
      const subtitle = [data.country || st.country, data.language || st.language]
        .filter(Boolean).join(' · ') || 'Live radio';
      setActiveChannel(st.id, data.name || st.name, st.favicon || st.logo_url || null);
      setCurrentSeg({
        segment_id: st.id,
        segment_url: '',
        track_title: data.name || st.name,
        track_artist: subtitle,
        channel_name: data.name || st.name,
      });
      setPlaying(true);
      setNowPlayingId(st.id);
      addRecent({
        id: st.id, name: data.name || st.name, favicon: st.favicon, logo_url: st.logo_url,
        country: st.country, language: st.language, source: st.source, is_flagship: st.is_flagship,
      });
      updateNowPlaying(streamUrl, data.name || st.name, subtitle, data.name || st.name, null);
    } catch {
      Alert.alert('Error', 'Could not play this station. Try another.');
    }
  };

  const renderItem = ({ item }: { item: Station }) => {
    const isPlaying = nowPlayingId === item.id;
    const fav = isFavorite(item.id);
    const subtitle = [item.country, item.language].filter(Boolean).join(' · ');
    return (
      <TouchableOpacity
        style={[s.row, isPlaying && s.rowActive]}
        onPress={() => playStation(item)}
        activeOpacity={0.8}
        testID={`station-row-${item.id}`}
      >
        <SafeImage uri={item.favicon || item.logo_url} fallbackText={item.name} size={46} borderRadius={10} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <View style={s.nameRow}>
            <Text style={s.stationName} numberOfLines={1}>{item.name}</Text>
            {item.is_flagship ? (
              <View style={s.flagBadge}><Text style={s.flagBadgeText}>FLAGSHIP</Text></View>
            ) : null}
          </View>
          {!!subtitle && <Text style={s.stationSub} numberOfLines={1}>{subtitle}</Text>}
        </View>
        <TouchableOpacity
          onPress={(e) => { e.stopPropagation?.(); toggleFavorite({
            id: item.id, name: item.name, favicon: item.favicon, logo_url: item.logo_url,
            country: item.country, language: item.language, source: item.source, is_flagship: item.is_flagship,
          }); }}
          style={s.heartBtn}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          testID={`station-fav-${item.id}`}
        >
          <Ionicons name={fav ? 'heart' : 'heart-outline'} size={20} color={fav ? COLORS.red : COLORS.textMuted} />
        </TouchableOpacity>
        <View style={[s.playCircle, isPlaying && s.playCircleActive]}>
          <Ionicons name={isPlaying ? 'volume-high' : 'play'} size={16} color="#fff" />
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView style={s.screen} testID="stations-screen">
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="stations-back-btn" style={s.backBtn}>
          <Ionicons name="chevron-back" size={20} color={COLORS.textDim} />
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.headerTitle}>All Stations</Text>
          <Text style={s.headerSub}>
            {mode === 'favorites' ? `${favorites.length} favorite${favorites.length !== 1 ? 's' : ''}`
              : mode === 'recent' ? `${recents.length} recently played`
              : total > 0 ? `${total.toLocaleString()} live stations worldwide` : 'Browse live radio worldwide'}
          </Text>
        </View>
      </View>

      {/* Mode: Browse / Favorites / Recent */}
      <View style={s.segRow}>
        {MODES.map((m) => (
          <TouchableOpacity key={m.id} style={[s.seg, mode === m.id && s.segActive]}
            onPress={() => setMode(m.id)} testID={`stations-mode-${m.id}`}>
            <Ionicons name={m.icon as any} size={15} color={mode === m.id ? '#fff' : COLORS.textDim} />
            <Text style={[s.segText, mode === m.id && s.segTextActive]}>{m.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {mode === 'browse' && (
        <>
          {/* Search */}
          <View style={s.searchRow}>
            <Ionicons name="search" size={16} color={COLORS.textMuted} />
            <TextInput
              style={s.searchInput}
              placeholder="Search stations, cities, genres..."
              placeholderTextColor={COLORS.textMuted}
              value={query}
              onChangeText={setQuery}
              autoCorrect={false}
              testID="stations-search-input"
            />
            {query.length > 0 && (
              <TouchableOpacity onPress={() => setQuery('')} testID="stations-search-clear">
                <Ionicons name="close-circle" size={16} color={COLORS.textMuted} />
              </TouchableOpacity>
            )}
          </View>

          {/* Country filter */}
          <View style={s.filterLine}>
            <View style={s.filterIcon}><Ionicons name="earth" size={13} color={COLORS.primary} /></View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 6, alignItems: 'center', paddingRight: SPACING.md }}>
              {COUNTRIES.map((c) => (
                <TouchableOpacity key={c.value} style={[s.chip, country === c.value && s.chipActive]}
                  onPress={() => setCountry(c.value)} testID={`stations-country-${c.label.toLowerCase()}`}>
                  <Text style={[s.chipText, country === c.value && s.chipTextActive]}>{c.label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          {/* Language filter */}
          <View style={s.filterLine}>
            <View style={s.filterIcon}><Ionicons name="language" size={13} color={COLORS.primary} /></View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 6, alignItems: 'center', paddingRight: SPACING.md }}>
              {LANGS.map((l) => (
                <TouchableOpacity key={l} style={[s.chip, lang === l && s.chipActive]}
                  onPress={() => setLang(l)} testID={`stations-lang-${l.toLowerCase()}`}>
                  <Text style={[s.chipText, lang === l && s.chipTextActive]}>
                    {l === 'All' ? 'All' : l.charAt(0).toUpperCase() + l.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>

          {/* Genre filter */}
          <View style={s.filterLine}>
            <View style={s.filterIcon}><Ionicons name="musical-notes" size={13} color={COLORS.primary} /></View>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}
              contentContainerStyle={{ gap: 6, alignItems: 'center', paddingRight: SPACING.md }}>
              {GENRES.map((g) => (
                <TouchableOpacity key={g} style={[s.chip, genre === g && s.chipActive]}
                  onPress={() => setGenre(g)} testID={`stations-genre-${g.toLowerCase()}`}>
                  <Text style={[s.chipText, genre === g && s.chipTextActive]}>
                    {g === 'All' ? 'All' : g.charAt(0).toUpperCase() + g.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </>
      )}

      {/* List */}
      {mode === 'browse' && loading ? (
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : (
        <FlatList
          data={mode === 'favorites' ? favorites : mode === 'recent' ? recents : items}
          extraData={`${nowPlayingId}-${favorites.length}-${mode}`}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          ListHeaderComponent={mode === 'browse' && promoted.length > 0 ? (
            <View style={s.promoWrap} testID="stations-promoted">
              <Text style={s.promoLabel}>SPONSORED STATIONS</Text>
              {promoted.map((p) => (
                <TouchableOpacity key={p.id} style={s.promoCard} testID={`stations-promo-${p.id}`} activeOpacity={0.85}
                  onPress={() => { if (p.promo_id) api.post(`/promoted/${p.promo_id}/click`).catch(() => {}); playStation(p); }}>
                  <SafeImage uri={p.favicon || p.logo_url} fallbackText={p.name} size={44} borderRadius={10} />
                  <View style={{ flex: 1, minWidth: 0 }}>
                    <Text style={s.stationName} numberOfLines={1}>{p.name}</Text>
                    <View style={s.promoTag}>
                      <Ionicons name="megaphone" size={9} color={COLORS.textMuted} />
                      <Text style={s.promoTagText}>Sponsored</Text>
                    </View>
                  </View>
                  <Ionicons name="play-circle" size={26} color={COLORS.primary} />
                </TouchableOpacity>
              ))}
            </View>
          ) : null}
          contentContainerStyle={{ paddingHorizontal: SPACING.md, paddingBottom: 100, paddingTop: SPACING.xs }}
          onEndReached={mode === 'browse' ? loadMore : undefined}
          onEndReachedThreshold={0.5}
          ListEmptyComponent={
            <View style={s.empty} testID="stations-empty">
              <Ionicons name={
                failed ? 'cloud-offline-outline'
                : mode === 'favorites' ? 'heart-outline'
                : mode === 'recent' ? 'time-outline' : 'radio-outline'
              } size={40} color={COLORS.textMuted} />
              <Text style={s.emptyTitle}>{
                failed ? "Couldn't load stations"
                : mode === 'favorites' ? 'No favorites yet'
                : mode === 'recent' ? 'Nothing played yet'
                : 'No stations found'
              }</Text>
              <Text style={s.emptySub}>{
                failed ? 'Check your connection and try again.'
                : mode === 'favorites' ? 'Tap the heart on any station to save it here.'
                : mode === 'recent' ? 'Stations you play will show up here.'
                : 'Try a different search, country or language.'
              }</Text>
            </View>
          }
          ListFooterComponent={
            mode !== 'browse' ? null
            : loadingMore ? (
              <View style={{ paddingVertical: SPACING.lg }}>
                <ActivityIndicator size="small" color={COLORS.primary} />
              </View>
            ) : items.length > 0 && items.length < total ? (
              <TouchableOpacity style={s.loadMore} onPress={loadMore} testID="stations-load-more">
                <Text style={s.loadMoreText}>Load more</Text>
              </TouchableOpacity>
            ) : null
          }
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: SPACING.md, paddingTop: SPACING.md, paddingBottom: SPACING.sm,
  },
  backBtn: { padding: 8, borderRadius: RADIUS.sm, backgroundColor: COLORS.card },
  headerTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  headerSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  segRow: {
    flexDirection: 'row', gap: 6, marginHorizontal: SPACING.md, marginBottom: SPACING.sm,
    backgroundColor: COLORS.inputBg, borderRadius: RADIUS.full, padding: 4,
  },
  seg: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5,
    paddingVertical: 8, borderRadius: RADIUS.full,
  },
  segActive: { backgroundColor: COLORS.primary },
  segText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  segTextActive: { color: '#fff' },
  heartBtn: { padding: 6 },
  searchRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginHorizontal: SPACING.md, marginBottom: SPACING.sm,
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10,
  },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.md },
  filterRow: { maxHeight: 48, marginBottom: SPACING.sm },
  filterLine: { flexDirection: 'row', alignItems: 'center', marginBottom: SPACING.sm, paddingLeft: SPACING.md },
  filterIcon: { width: 26, height: 26, borderRadius: 13, backgroundColor: '#fff2e6', alignItems: 'center', justifyContent: 'center', marginRight: 8 },
  chip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  chipActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  chipTextActive: { color: '#fff', fontWeight: '700' },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.sm + 2, marginBottom: 8,
  },
  rowActive: { borderColor: COLORS.primary, borderWidth: 2 },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  stationName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700', flexShrink: 1 },
  stationSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  flagBadge: {
    backgroundColor: '#fef3c7', borderRadius: RADIUS.sm,
    paddingHorizontal: 6, paddingVertical: 1,
  },
  flagBadgeText: { color: COLORS.gold, fontSize: 8, fontWeight: '800', letterSpacing: 0.5 },
  playCircle: {
    width: 34, height: 34, borderRadius: 17, backgroundColor: COLORS.textMuted,
    alignItems: 'center', justifyContent: 'center',
  },
  playCircleActive: { backgroundColor: COLORS.primary },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 10 },
  emptyTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800' },
  emptySub: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', paddingHorizontal: 30 },
  loadMore: {
    alignItems: 'center', paddingVertical: 12, marginTop: 4,
    borderRadius: RADIUS.md, backgroundColor: COLORS.card,
    borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  loadMoreText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '700' },
  promoWrap: { marginBottom: SPACING.sm },
  promoLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '800', letterSpacing: 2, marginBottom: 8 },
  promoCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    backgroundColor: '#fff7ed', borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: '#fed7aa',
    padding: SPACING.sm + 2, marginBottom: 8,
  },
  promoTag: { flexDirection: 'row', alignItems: 'center', gap: 3, marginTop: 3, alignSelf: 'flex-start', backgroundColor: COLORS.inputBg, borderRadius: RADIUS.sm, paddingHorizontal: 6, paddingVertical: 2 },
  promoTagText: { color: COLORS.textMuted, fontSize: 8, fontWeight: '800', letterSpacing: 0.5, textTransform: 'uppercase' },
});
