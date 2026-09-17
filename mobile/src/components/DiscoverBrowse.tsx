/**
 * DiscoverBrowse — interactive "Discover more" radio widget (mobile parity of
 * web RadioHome BrowseTeaser). Auto top-played imported stations + language /
 * genre / country filters + search + sort toggle + favourites + recently
 * played + LIVE / HOT badges. Mounted on the Radio tab and the Home tab.
 */
import React, { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, TextInput, ActivityIndicator, Animated,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../api/client';
import SafeImage from './SafeImage';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import { useStationsStore, SavedStation } from '../stores/useStationsStore';
import { usePlayerStore } from '../stores/usePlayerStore';
import { playImportedStation } from '../services/playStation';

const FILTERS_KEY = 'bigfm_discover_filters';
const CARD = 128;

const GENRE_COLORS: Record<string, string> = {
  pop: '#EC4899', news: '#3B82F6', rock: '#EF4444', bollywood: '#F59E0B',
  talk: '#8B5CF6', jazz: '#14B8A6', classical: '#A16207', edm: '#06B6D4',
  hindi: '#F97316', sports: '#16A34A', devotional: '#7C3AED', country: '#CA8A04',
  electronic: '#06B6D4', dance: '#DB2777', oldies: '#0EA5E9',
};
const genreColor = (slug: string) => GENRE_COLORS[slug] || COLORS.primary;

const COUNTRY_NAMES: Record<string, string> = {
  US: 'USA', GB: 'UK', DE: 'Germany', FR: 'France', IN: 'India', IT: 'Italy',
  ES: 'Spain', RU: 'Russia', MX: 'Mexico', TR: 'Turkey', CH: 'Switzerland',
  GR: 'Greece', NL: 'Netherlands', RO: 'Romania', PL: 'Poland', AE: 'UAE',
  CA: 'Canada', AU: 'Australia', BR: 'Brazil', PK: 'Pakistan', SA: 'Saudi Arabia',
  EG: 'Egypt', JP: 'Japan', CN: 'China', KR: 'Korea', PT: 'Portugal',
  SE: 'Sweden', NO: 'Norway', DK: 'Denmark', BE: 'Belgium', AT: 'Austria',
  IE: 'Ireland', UA: 'Ukraine', ID: 'Indonesia', PH: 'Philippines', TH: 'Thailand',
  ZA: 'South Africa', NG: 'Nigeria', AR: 'Argentina', CO: 'Colombia',
};
const countryName = (cc: string) => COUNTRY_NAMES[cc] || cc;
function flagEmoji(cc: string) {
  if (!cc || !/^[A-Za-z]{2}$/.test(cc)) return '';
  const base = 0x1f1e6;
  const up = cc.toUpperCase();
  return String.fromCodePoint(base + up.charCodeAt(0) - 65, base + up.charCodeAt(1) - 65);
}

type Chip = { slug: string; label: string; count?: number };
type Station = SavedStation;

const LANG_GROUPS: { key: string; label: string }[] = [
  { key: '', label: 'All' },
  { key: 'english', label: 'English' },
  { key: 'hindi', label: 'Hindi' },
  { key: 'indian', label: 'Indian Languages' },
  { key: 'news', label: 'News' },
];

function PulseDot({ color = '#fff' }: { color?: string }) {
  const a = useRef(new Animated.Value(0.4)).current;
  useEffect(() => {
    const loop = Animated.loop(Animated.sequence([
      Animated.timing(a, { toValue: 1, duration: 700, useNativeDriver: true }),
      Animated.timing(a, { toValue: 0.4, duration: 700, useNativeDriver: true }),
    ]));
    loop.start();
    return () => loop.stop();
  }, [a]);
  return <Animated.View style={{ width: 5, height: 5, borderRadius: 3, backgroundColor: color, opacity: a }} />;
}

function Filter({ active, label, onPress, testID, dotColor }: { active: boolean; label: string; onPress: () => void; testID: string; dotColor?: string }) {
  return (
    <TouchableOpacity style={[c.chip, active && c.chipActive]} onPress={onPress} testID={testID} activeOpacity={0.8}>
      {dotColor ? <View style={[c.genreDot, { backgroundColor: dotColor }]} /> : null}
      <Text style={[c.chipText, active && c.chipTextActive]} numberOfLines={1}>{label}</Text>
    </TouchableOpacity>
  );
}

function StationCard({ st, showHot, isFav, isNowPlaying, onPlay, onToggleFav, prefix }:
  { st: Station; showHot?: boolean; isFav: boolean; isNowPlaying?: boolean; onPlay: () => void; onToggleFav: () => void; prefix: string }) {
  const sub = st.country || (st.language ? String(st.language).split(' ')[0] : '') || 'Live';
  return (
    <TouchableOpacity style={c.card} onPress={onPlay} testID={`${prefix}-card-${st.id}`} activeOpacity={0.85}>
      <View style={c.thumbWrap}>
        <SafeImage uri={st.favicon || st.logo_url} fallbackText={st.name} size={CARD} borderRadius={RADIUS.lg} />
        {isNowPlaying ? (
          <View style={[c.liveBadge, c.playingBadge]} testID={`${prefix}-playing-${st.id}`}>
            <PulseDot />
            <Text style={c.liveText}>PLAYING</Text>
          </View>
        ) : (
          <View style={c.liveBadge} testID={`${prefix}-live-${st.id}`}>
            <View style={c.liveDot} />
            <Text style={c.liveText}>LIVE</Text>
          </View>
        )}
        {showHot && (
          <View style={c.hotBadge} testID={`${prefix}-hot-${st.id}`}>
            <Text style={c.hotText}>🔥 HOT</Text>
          </View>
        )}
        <TouchableOpacity
          style={c.favBtn}
          onPress={(e) => { e.stopPropagation?.(); onToggleFav(); }}
          hitSlop={{ top: 8, bottom: 8, left: 8, right: 8 }}
          testID={`${prefix}-fav-${st.id}`}
        >
          <Ionicons name={isFav ? 'heart' : 'heart-outline'} size={15} color={isFav ? COLORS.red : '#fff'} />
        </TouchableOpacity>
      </View>
      <Text style={c.cardName} numberOfLines={1}>{st.name}</Text>
      <Text style={c.cardSub} numberOfLines={1}>{sub}</Text>
    </TouchableOpacity>
  );
}

export default function DiscoverBrowse({ prefix = 'radio-browse' }: { prefix?: string }) {
  const router = useRouter();
  const { favorites, recents, load, toggleFavorite } = useStationsStore();
  const activeChannel = usePlayerStore((s) => s.activeChannel);
  const playing = usePlayerStore((s) => s.playing);

  const [genres, setGenres] = useState<Chip[]>([]);
  const [countries, setCountries] = useState<Chip[]>([]);
  const [langGroup, setLangGroup] = useState('');
  const [genre, setGenre] = useState('');
  const [country, setCountry] = useState('');
  const [sort, setSort] = useState('popular');
  const [qInput, setQInput] = useState('');
  const [q, setQ] = useState('');
  const [items, setItems] = useState<Station[] | null>(null);
  const [loading, setLoading] = useState(true);
  const restored = useRef(false);

  const favIds = useMemo(() => new Set(favorites.map((f) => f.id)), [favorites]);

  useEffect(() => { load(); }, [load]);

  // Restore remembered filters (search intentionally not persisted).
  useEffect(() => {
    (async () => {
      try {
        const raw = await AsyncStorage.getItem(FILTERS_KEY);
        if (raw) {
          const s = JSON.parse(raw);
          if (s.langGroup) setLangGroup(s.langGroup);
          if (s.genre) setGenre(s.genre);
          if (s.country) setCountry(s.country);
          if (s.sort) setSort(s.sort);
        }
      } catch { /* ignore */ }
      restored.current = true;
    })();
  }, []);

  // Load filter facets once.
  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get('/radio/discover');
        const rails: Record<string, any> = {};
        (data?.rails || []).forEach((r: any) => { rails[r.id] = r; });
        setGenres((rails.genres?.facet_chips || []).slice(0, 12));
        setCountries((rails.countries?.facet_chips || []).slice(0, 20));
      } catch { /* filters optional */ }
    })();
  }, []);

  // Debounce the search box.
  useEffect(() => {
    const t = setTimeout(() => setQ(qInput.trim()), 350);
    return () => clearTimeout(t);
  }, [qInput]);

  // Persist filter choices.
  useEffect(() => {
    if (!restored.current) return;
    AsyncStorage.setItem(FILTERS_KEY, JSON.stringify({ langGroup, genre, country, sort })).catch(() => {});
  }, [langGroup, genre, country, sort]);

  // Fetch top-played stations whenever a filter / search / sort changes.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const params: any = { source: 'imported', limit: 24, sort };
        if (langGroup) params.lang_group = langGroup;
        if (genre) params.category = genre;
        if (country) params.country = country;
        if (q) params.q = q;
        const { data } = await api.get('/radio/browse', { params });
        if (!cancelled) setItems(data.items || []);
      } catch { if (!cancelled) setItems([]); }
      finally { if (!cancelled) setLoading(false); }
    })();
    return () => { cancelled = true; };
  }, [langGroup, genre, country, q, sort]);

  const play = useCallback((st: Station) => { playImportedStation(st, router); }, [router]);
  const toFav = (st: Station) => toggleFavorite({
    id: st.id, name: st.name, favicon: st.favicon, logo_url: st.logo_url,
    country: st.country, language: st.language, source: st.source, is_flagship: st.is_flagship,
  });

  return (
    <View style={c.section} testID={`${prefix}-teaser`}>
      <View style={c.head}>
        <View style={{ flex: 1 }}>
          <Text style={c.title}>Discover more</Text>
          <Text style={c.subtitle}>50,000+ stations · every language, every mood</Text>
        </View>
        <TouchableOpacity onPress={() => router.push('/stations')} testID={`${prefix}-cta-top`} style={c.seeAll}>
          <Text style={c.seeAllText}>See all</Text>
          <Ionicons name="chevron-forward" size={13} color={COLORS.primary} />
        </TouchableOpacity>
      </View>

      {/* Recently played */}
      {recents.length > 0 && (
        <View testID={`${prefix}-recent`}>
          <Text style={c.railLabel}>Recently played</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={c.rail}>
            {recents.slice(0, 12).map((st) => (
              <StationCard key={`rec-${st.id}`} st={st} isFav={favIds.has(st.id)} isNowPlaying={playing && activeChannel === st.id} onPlay={() => play(st)} onToggleFav={() => toFav(st)} prefix={prefix} />
            ))}
          </ScrollView>
        </View>
      )}

      {/* Favourites */}
      {favorites.length > 0 && (
        <View testID={`${prefix}-favorites`}>
          <Text style={c.railLabel}>Your favourites ❤</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={c.rail}>
            {favorites.slice(0, 20).map((st) => (
              <StationCard key={`fav-${st.id}`} st={st} isFav isNowPlaying={playing && activeChannel === st.id} onPlay={() => play(st)} onToggleFav={() => toFav(st)} prefix={prefix} />
            ))}
          </ScrollView>
        </View>
      )}

      {/* Search */}
      <View style={c.searchRow}>
        <Ionicons name="search" size={16} color={COLORS.textMuted} />
        <TextInput
          style={c.searchInput}
          placeholder="Search stations by name…"
          placeholderTextColor={COLORS.textMuted}
          value={qInput}
          onChangeText={setQInput}
          autoCorrect={false}
          testID={`${prefix}-search`}
        />
        {qInput.length > 0 && (
          <TouchableOpacity onPress={() => setQInput('')} testID={`${prefix}-search-clear`}>
            <Ionicons name="close-circle" size={16} color={COLORS.textMuted} />
          </TouchableOpacity>
        )}
      </View>

      {/* Language group filter — English · Hindi · Indian · News */}
      <View style={c.filterLine}>
        <View style={c.filterIcon}><Ionicons name="language" size={13} color={COLORS.primary} /></View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={c.chipRow} testID={`${prefix}-lang-chips`}>
          {LANG_GROUPS.map((g) => (
            <Filter key={g.key || 'all'} active={langGroup === g.key} label={g.label} onPress={() => setLangGroup(g.key)} testID={`${prefix}-lang-${g.key || 'all'}`} />
          ))}
        </ScrollView>
      </View>

      {/* Genre filter */}
      {genres.length > 0 && (
        <View style={c.filterLine}>
          <View style={c.filterIcon}><Ionicons name="musical-notes" size={13} color={COLORS.primary} /></View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={c.chipRow} testID={`${prefix}-genre-chips`}>
            <Filter active={!genre} label="All" onPress={() => setGenre('')} testID={`${prefix}-genre-all`} />
            {genres.map((g) => (
              <Filter key={g.slug} active={genre === g.slug} label={g.label} dotColor={genreColor(g.slug)} onPress={() => setGenre(g.slug)} testID={`${prefix}-genre-${g.slug}`} />
            ))}
          </ScrollView>
        </View>
      )}

      {/* Country filter */}
      {countries.length > 0 && (
        <View style={c.filterLine}>
          <View style={c.filterIcon}><Ionicons name="earth" size={13} color={COLORS.primary} /></View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={c.chipRow} testID={`${prefix}-country-chips`}>
            <Filter active={!country} label="All" onPress={() => setCountry('')} testID={`${prefix}-country-all`} />
            {countries.map((ct) => (
              <Filter key={ct.slug} active={country === ct.slug} label={`${flagEmoji(ct.slug)} ${countryName(ct.slug)}`} onPress={() => setCountry(ct.slug)} testID={`${prefix}-country-${ct.slug}`} />
            ))}
          </ScrollView>
        </View>
      )}

      {/* Sort */}
      <View style={c.filterLine}>
        <View style={c.filterIcon}><Ionicons name="swap-vertical" size={13} color={COLORS.primary} /></View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={c.chipRow} testID={`${prefix}-sort`}>
          {([['popular', 'Popular'], ['az', 'A–Z'], ['newest', 'Newest']] as const).map(([val, label]) => (
            <Filter key={val} active={sort === val} label={label} onPress={() => setSort(val)} testID={`${prefix}-sort-${val}`} />
          ))}
        </ScrollView>
      </View>

      {/* Results */}
      {loading && items === null ? (
        <View style={c.loadWrap}><ActivityIndicator color={COLORS.primary} /></View>
      ) : (items || []).length === 0 ? (
        <View style={c.empty} testID={`${prefix}-empty`}>
          <Ionicons name="radio-outline" size={26} color={COLORS.textMuted} />
          <Text style={c.emptyText}>No stations match these filters. Try clearing one.</Text>
        </View>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={[c.rail, loading && { opacity: 0.5 }]} testID={`${prefix}-scroll`}>
          {(items || []).map((st, idx) => (
            <StationCard key={st.id} st={st} showHot={idx < 3 && !q} isFav={favIds.has(st.id)} isNowPlaying={playing && activeChannel === st.id} onPlay={() => play(st)} onToggleFav={() => toFav(st)} prefix={prefix} />
          ))}
        </ScrollView>
      )}

      <TouchableOpacity style={c.browseAll} onPress={() => router.push('/stations')} testID={`${prefix}-cta`} activeOpacity={0.85}>
        <Ionicons name="globe" size={16} color="#fff" />
        <Text style={c.browseAllText}>Browse all 50,000+ stations</Text>
      </TouchableOpacity>
    </View>
  );
}

const c = StyleSheet.create({
  section: { marginTop: SPACING.lg },
  head: { flexDirection: 'row', alignItems: 'flex-end', paddingHorizontal: SPACING.md, marginBottom: SPACING.sm },
  title: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  subtitle: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 2 },
  seeAll: { flexDirection: 'row', alignItems: 'center', gap: 2 },
  seeAllText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  railLabel: { color: COLORS.textDim, fontSize: 10, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase', paddingHorizontal: SPACING.md, marginTop: SPACING.sm, marginBottom: 6 },
  rail: { paddingHorizontal: SPACING.md, gap: SPACING.sm, paddingBottom: 4 },
  card: { width: CARD },
  thumbWrap: { width: CARD, height: CARD, position: 'relative' },
  liveBadge: { position: 'absolute', top: 6, left: 6, flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: 'rgba(225,29,72,0.95)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full },
  playingBadge: { backgroundColor: 'rgba(5,150,105,0.95)' },
  liveDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: '#fff' },
  liveText: { color: '#fff', fontSize: 8, fontWeight: '900', letterSpacing: 0.5 },
  hotBadge: { position: 'absolute', top: 6, right: 6, backgroundColor: COLORS.gold, paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.full },
  hotText: { color: COLORS.text, fontSize: 8, fontWeight: '900' },
  favBtn: { position: 'absolute', bottom: 6, right: 6, width: 26, height: 26, borderRadius: 13, backgroundColor: 'rgba(0,0,0,0.5)', alignItems: 'center', justifyContent: 'center' },
  cardName: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', marginTop: 6 },
  cardSub: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  searchRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginHorizontal: SPACING.md, marginTop: SPACING.md, marginBottom: SPACING.sm,
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10,
  },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.md },
  filterLine: { flexDirection: 'row', alignItems: 'center', marginBottom: SPACING.sm, paddingLeft: SPACING.md },
  filterIcon: { width: 26, height: 26, borderRadius: 13, backgroundColor: '#fff2e6', alignItems: 'center', justifyContent: 'center', marginRight: 8 },
  chipRow: { gap: 6, alignItems: 'center', paddingRight: SPACING.md },
  chip: { flexShrink: 0, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, paddingVertical: 7, borderRadius: RADIUS.full, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  chipActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  genreDot: { width: 8, height: 8, borderRadius: 4, marginRight: 6 },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  chipTextActive: { color: '#fff' },
  loadWrap: { paddingVertical: 40, alignItems: 'center' },
  empty: { alignItems: 'center', gap: 6, paddingVertical: 30, paddingHorizontal: SPACING.lg },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', textAlign: 'center' },
  browseAll: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    marginHorizontal: SPACING.md, marginTop: SPACING.md, paddingVertical: 14,
    borderRadius: RADIUS.full, backgroundColor: COLORS.primary,
  },
  browseAllText: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
});
