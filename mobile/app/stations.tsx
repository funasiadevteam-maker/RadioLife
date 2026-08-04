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

let createAudioPlayer: any;
try {
  const mod = require('expo-audio');
  createAudioPlayer = mod.createAudioPlayer;
} catch {}

const LANGS = ['All', 'hindi', 'english', 'arabic', 'urdu', 'punjabi', 'tamil', 'malayalam'];
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
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [failed, setFailed] = useState(false);
  const [nowPlayingId, setNowPlayingId] = useState<string | null>(null);

  const { setActiveChannel, setCurrentSeg, setPlaying, setSession } = usePlayerStore();

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
  }, [debounced, lang]);

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
      updateNowPlaying(streamUrl, data.name || st.name, subtitle, data.name || st.name, null);
    } catch {
      Alert.alert('Error', 'Could not play this station. Try another.');
    }
  };

  const renderItem = ({ item }: { item: Station }) => {
    const isPlaying = nowPlayingId === item.id;
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
            {total > 0 ? `${total.toLocaleString()} live stations worldwide` : 'Browse live radio worldwide'}
          </Text>
        </View>
      </View>

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

      {/* Language filter */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filterRow}
        contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 6, alignItems: 'center' }}>
        {LANGS.map((l) => (
          <TouchableOpacity key={l} style={[s.chip, lang === l && s.chipActive]}
            onPress={() => setLang(l)} testID={`stations-lang-${l.toLowerCase()}`}>
            <Text style={[s.chipText, lang === l && s.chipTextActive]}>
              {l === 'All' ? 'All' : l.charAt(0).toUpperCase() + l.slice(1)}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* List */}
      {loading ? (
        <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(i) => i.id}
          renderItem={renderItem}
          contentContainerStyle={{ paddingHorizontal: SPACING.md, paddingBottom: 100 }}
          onEndReached={loadMore}
          onEndReachedThreshold={0.5}
          ListEmptyComponent={
            <View style={s.empty} testID="stations-empty">
              <Ionicons name={failed ? 'cloud-offline-outline' : 'radio-outline'} size={40} color={COLORS.textMuted} />
              <Text style={s.emptyTitle}>{failed ? "Couldn't load stations" : 'No stations found'}</Text>
              <Text style={s.emptySub}>{failed ? 'Check your connection and try again.' : 'Try a different search or language.'}</Text>
            </View>
          }
          ListFooterComponent={
            loadingMore ? (
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
  searchRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginHorizontal: SPACING.md, marginBottom: SPACING.sm,
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10,
  },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.md },
  filterRow: { maxHeight: 48, marginBottom: SPACING.sm },
  chip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  chipActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  chipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
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
});
