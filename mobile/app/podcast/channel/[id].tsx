import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, Image,
  ActivityIndicator, RefreshControl, StyleSheet, Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as WebBrowser from 'expo-web-browser';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../../src/constants/theme';
import { getChannel, getChannelHighlights, subscribe } from '../../../src/api/podcastApi';

function formatDuration(sec: number | undefined) {
  if (!sec) return '';
  const m = Math.floor(sec / 60);
  return m > 0 ? `${m} min` : `${sec}s`;
}

export default function ChannelDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [channel, setChannel] = useState<any>(null);
  const [episodes, setEpisodes] = useState<any[]>([]);
  const [followers, setFollowers] = useState(0);
  const [highlights, setHighlights] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [subBusy, setSubBusy] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [chData, clips] = await Promise.all([
        getChannel(id),
        getChannelHighlights(id),
      ]);
      setChannel(chData.channel);
      setEpisodes(chData.episodes || []);
      setFollowers(chData.followers || 0);
      setHighlights(clips);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not load channel');
    } finally { setLoading(false); setRefreshing(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  const onSubscribe = async () => {
    if (!id) return;
    setSubBusy(true);
    try {
      const data = await subscribe(id);
      if (data?.checkout_url) {
        await WebBrowser.openBrowserAsync(data.checkout_url);
      }
    } catch (e: any) {
      Alert.alert('Subscribe', e?.response?.data?.detail || 'Failed');
    } finally { setSubBusy(false); }
  };

  if (loading) return (
    <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
  );

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView
        contentContainerStyle={{ paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
      >
        {/* Back */}
        <TouchableOpacity testID="mobile-channel-back" onPress={() => router.back()} style={s.backBtn}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>

        {/* Header */}
        <View testID="mobile-channel-header" style={s.header}>
          {channel?.cover_image_url ? (
            <Image source={{ uri: channel.cover_image_url }} style={s.coverImg} />
          ) : (
            <View style={[s.coverImg, s.coverPlaceholder]}>
              <Ionicons name="mic" size={40} color={COLORS.textDim} />
            </View>
          )}
          <Text testID="mobile-channel-title" style={s.title}>{channel?.title}</Text>
          <Text style={s.meta}>{followers} followers · {channel?.category?.replace(/_/g, ' ')}</Text>
          {channel?.description ? (
            <Text style={s.desc} numberOfLines={4}>{channel.description}</Text>
          ) : null}

          <TouchableOpacity
            testID="mobile-channel-subscribe-btn"
            style={common.btnPrimary}
            onPress={onSubscribe}
            disabled={subBusy}
          >
            <Ionicons name="heart" size={16} color="#fff" />
            <Text style={common.btnPrimaryText}>{subBusy ? 'Opening…' : 'Subscribe'}</Text>
          </TouchableOpacity>
        </View>

        {/* Highlights carousel */}
        {highlights.length > 0 && (
          <View testID="mobile-channel-highlights-carousel" style={s.section}>
            <Text style={common.sectionTitle}>Recent clips</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {highlights.map(c => (
                <View key={c.id} testID={`mobile-carousel-clip-${c.id}`} style={s.clipCard}>
                  <Text style={s.clipTitle} numberOfLines={1}>{c.title || 'Untitled'}</Text>
                  <Text style={s.clipMeta}>
                    {((c.end_sec || 0) - (c.start_sec || 0)).toFixed(0)}s · score {(c.score || 0).toFixed(2)}
                  </Text>
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Episodes list */}
        <View testID="mobile-channel-episodes" style={s.section}>
          <Text style={common.sectionTitle}>Episodes ({episodes.length})</Text>
          {episodes.length === 0 ? (
            <Text style={s.emptyText}>No episodes yet.</Text>
          ) : episodes.map(ep => (
            <TouchableOpacity
              key={ep.id}
              testID={`mobile-episode-row-${ep.id}`}
              style={s.epRow}
              onPress={() => router.push(`/podcast/episode/${ep.id}`)}
              activeOpacity={0.7}
            >
              <View style={{ flex: 1 }}>
                <Text style={s.epTitle} numberOfLines={1}>{ep.title}</Text>
                <View style={s.epMetaRow}>
                  {ep.is_bonus && <View style={s.badge}><Text style={s.badgeText}>BONUS</Text></View>}
                  {ep.release_for_subscribers_at && <View style={[s.badge, s.badgeEarly]}><Text style={s.badgeText}>EARLY</Text></View>}
                  <Text style={s.epMeta}>{formatDuration(ep.duration_sec)}</Text>
                </View>
              </View>
              <Ionicons name="play-circle" size={28} color={COLORS.primary} />
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  backBtn: { padding: SPACING.lg },
  header: { paddingHorizontal: SPACING.lg, alignItems: 'center', marginBottom: SPACING.lg },
  coverImg: { width: 140, height: 140, borderRadius: RADIUS.lg, marginBottom: SPACING.md },
  coverPlaceholder: { backgroundColor: COLORS.card, justifyContent: 'center', alignItems: 'center' },
  title: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text, textAlign: 'center', marginBottom: 4 },
  meta: { fontSize: FONT.sm, color: COLORS.textDim, marginBottom: 8 },
  desc: { fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center', marginBottom: SPACING.md, lineHeight: 20 },
  section: { paddingHorizontal: SPACING.lg, marginTop: SPACING.lg },
  clipCard: {
    width: 180, padding: 10, borderRadius: RADIUS.sm, marginRight: 8,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  clipTitle: { fontSize: FONT.sm, fontWeight: '600', color: COLORS.text },
  clipMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 2 },
  epRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 12, marginBottom: 8, borderRadius: RADIUS.sm,
    backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder,
  },
  epTitle: { fontSize: FONT.md, fontWeight: '600', color: COLORS.text },
  epMetaRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 4 },
  badge: {
    backgroundColor: COLORS.orange, paddingHorizontal: 6, paddingVertical: 2,
    borderRadius: 4,
  },
  badgeEarly: { backgroundColor: COLORS.purple },
  badgeText: { fontSize: 9, fontWeight: '800', color: '#000', letterSpacing: 0.5 },
  epMeta: { fontSize: FONT.xs, color: COLORS.textDim },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', paddingVertical: 20 },
});
