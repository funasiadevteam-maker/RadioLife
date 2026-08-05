import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TextInput, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl, StyleSheet, Image,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../src/constants/theme';
import { discoverChannels } from '../../src/api/podcastApi';

const CATEGORIES = [
  '', 'business', 'food_local', 'movies_culture', 'real_estate',
  'health_wellness', 'legal_finance', 'events_community', 'news_commentary',
  'comedy', 'true_crime', 'devotional', 'sports', 'tech', 'education', 'other',
];

export default function PodcastsTab() {
  const router = useRouter();
  const [channels, setChannels] = useState<any[]>([]);
  const [q, setQ] = useState('');
  const [cat, setCat] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await discoverChannels(q || undefined, cat || undefined);
      setChannels(data);
    } catch { setChannels([]); }
    finally { setLoading(false); setRefreshing(false); }
  }, [q, cat]);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: SPACING.lg }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.primary} />}
      >
        <Text testID="podcasts-title" style={s.title}>Podcasts</Text>
        <Text style={s.subtitle}>On-demand shows from RadioLife creators.</Text>

        {/* Search */}
        <View style={s.searchRow}>
          <View style={s.searchBox}>
            <Ionicons name="search" size={16} color={COLORS.textDim} />
            <TextInput
              testID="mobile-podcasts-search"
              placeholder="Search podcasts…"
              placeholderTextColor={COLORS.textDim}
              value={q}
              onChangeText={setQ}
              style={s.searchInput}
              returnKeyType="search"
            />
          </View>
        </View>

        {/* Category pills */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.catScroll}>
          {CATEGORIES.map(c => (
            <TouchableOpacity
              key={c || '__all'}
              testID={`mobile-podcasts-cat-${c || 'all'}`}
              style={[common.pill, cat === c && common.pillActive]}
              onPress={() => setCat(c)}
            >
              <Text style={[common.pillText, cat === c && common.pillTextActive]}>
                {c ? c.replace(/_/g, ' ') : 'All'}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Channel grid */}
        {loading ? (
          <ActivityIndicator size="large" color={COLORS.primary} style={{ marginTop: 40 }} />
        ) : channels.length === 0 ? (
          <View style={s.empty}>
            <Ionicons name="mic-off-outline" size={40} color={COLORS.textDim} />
            <Text style={s.emptyText}>No podcasts found.</Text>
          </View>
        ) : (
          <View testID="mobile-podcasts-grid" style={s.grid}>
            {channels.map(ch => (
              <TouchableOpacity
                key={ch.id}
                testID={`mobile-podcast-card-${ch.slug || ch.id}`}
                style={s.card}
                onPress={() => router.push(`/podcast/channel/${ch.id}`)}
                activeOpacity={0.7}
              >
                {ch.cover_image_url ? (
                  <Image source={{ uri: ch.cover_image_url }} style={s.cover} />
                ) : (
                  <View style={[s.cover, s.coverPlaceholder]}>
                    <Ionicons name="mic" size={28} color={COLORS.textDim} />
                  </View>
                )}
                <Text style={s.cardTitle} numberOfLines={1}>{ch.title}</Text>
                <Text style={s.cardMeta} numberOfLines={1}>
                  {ch.category ? ch.category.replace(/_/g, ' ') : ''} · {ch.follower_count || 0} followers
                </Text>
              </TouchableOpacity>
            ))}
          </View>
        )}

        {/* Links */}
        <View style={s.linksRow}>
          <TouchableOpacity
            testID="mobile-podcasts-highlights-link"
            style={common.btnGhost}
            onPress={() => router.push('/podcast/highlights')}
          >
            <Ionicons name="sparkles-outline" size={16} color={COLORS.textDim} />
            <Text style={common.btnGhostText}>Browse Highlights</Text>
          </TouchableOpacity>
          <TouchableOpacity
            testID="mobile-podcasts-subs-link"
            style={common.btnGhost}
            onPress={() => router.push('/podcast/subscriptions')}
          >
            <Ionicons name="heart-outline" size={16} color={COLORS.textDim} />
            <Text style={common.btnGhostText}>My Subscriptions</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  title: { fontSize: FONT.xxl, fontWeight: '800', color: COLORS.text, marginBottom: 4 },
  subtitle: { fontSize: FONT.sm, color: COLORS.textDim, marginBottom: SPACING.lg },
  searchRow: { marginBottom: SPACING.md },
  searchBox: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10,
  },
  searchInput: { flex: 1, color: COLORS.text, fontSize: FONT.md, padding: 0 },
  catScroll: { marginBottom: SPACING.lg, flexGrow: 0 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 12 },
  card: {
    width: '47%' as any, backgroundColor: COLORS.surface,
    borderWidth: 1, borderColor: COLORS.surfaceBorder,
    borderRadius: RADIUS.md, padding: 10, marginBottom: 4,
  },
  cover: { width: '100%', aspectRatio: 1, borderRadius: RADIUS.sm, marginBottom: 8 },
  coverPlaceholder: {
    backgroundColor: COLORS.card, justifyContent: 'center', alignItems: 'center',
  },
  cardTitle: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  cardMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 2 },
  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.md },
  linksRow: { flexDirection: 'row', gap: 12, marginTop: SPACING.xl, marginBottom: SPACING.xxl },
});
