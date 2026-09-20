import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, FlatList, TouchableOpacity,
  ActivityIndicator, StyleSheet,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../src/constants/theme';
import { getGlobalHighlights } from '../../src/api/podcastApi';

export default function HighlightsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async (c: string | null, append: boolean) => {
    if (append) setLoadingMore(true); else setLoading(true);
    try {
      const data = await getGlobalHighlights(20, c);
      const newItems = data.items || [];
      setItems(prev => append ? [...prev, ...newItems] : newItems);
      setCursor(data.next_cursor);
      setHasMore(data.has_more);
    } catch { /* swallow */ }
    finally { setLoading(false); setLoadingMore(false); }
  }, []);

  useEffect(() => { load(null, false); }, [load]);

  const renderItem = ({ item: c }: any) => (
    <View testID={`mobile-highlight-${c.id}`} style={s.card}>
      <View style={{ flex: 1 }}>
        <Text style={s.clipTitle}>{c.title || 'Untitled'}</Text>
        <Text style={s.clipMeta}>
          {((c.end_sec || 0) - (c.start_sec || 0)).toFixed(0)}s · score {(c.score || 0).toFixed(2)}
          {c.channel_title ? ` · ${c.channel_title}` : ''}
        </Text>
        {c.summary ? <Text style={s.clipSummary} numberOfLines={2}>{c.summary}</Text> : null}
      </View>
      <Ionicons name="play-circle-outline" size={28} color={COLORS.secondary} />
    </View>
  );

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity testID="mobile-highlights-back" onPress={() => router.back()} style={s.backBtn}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <View>
          <Text style={s.title}>Highlights</Text>
          <Text style={s.subtitle}>Best moments across FUUSIC channels.</Text>
        </View>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={COLORS.primary} style={{ marginTop: 60 }} />
      ) : items.length === 0 ? (
        <View testID="mobile-highlights-empty" style={s.empty}>
          <Ionicons name="sparkles-outline" size={40} color={COLORS.textDim} />
          <Text style={s.emptyText}>No highlights yet.</Text>
        </View>
      ) : (
        <FlatList
          testID="mobile-highlights-list"
          data={items}
          keyExtractor={i => i.id}
          renderItem={renderItem}
          contentContainerStyle={{ padding: SPACING.lg }}
          onEndReached={() => { if (hasMore && !loadingMore) load(cursor, true); }}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            loadingMore ? <ActivityIndicator color={COLORS.primary} style={{ paddingVertical: 20 }} /> :
            hasMore ? (
              <TouchableOpacity
                testID="mobile-highlights-load-more"
                style={[common.btnGhost, { marginTop: 12 }]}
                onPress={() => load(cursor, true)}
              >
                <Text style={common.btnGhostText}>Load more</Text>
              </TouchableOpacity>
            ) : null
          }
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  backBtn: { padding: 4 },
  title: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  subtitle: { fontSize: FONT.xs, color: COLORS.textDim },
  card: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 12, marginBottom: 8, borderRadius: RADIUS.sm,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  clipTitle: { fontSize: FONT.md, fontWeight: '600', color: COLORS.text },
  clipMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 2 },
  clipSummary: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 4, lineHeight: 16 },
  empty: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  emptyText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.md },
});
