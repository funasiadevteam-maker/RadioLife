import React, { useEffect, useState, useMemo, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, RefreshControl, Linking,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import api from '../../src/api/client';

const CATEGORIES: Record<string, string> = {
  '': 'All',
  breaking: 'Breaking', local: 'Local', politics: 'Politics', business: 'Business',
  sports: 'Sports', weather: 'Weather', traffic: 'Traffic', features: 'Features',
  world: 'World', tech: 'Tech', entertainment: 'Entertainment',
};

export default function NewsScreen() {
  const [headlines, setHeadlines] = useState<any[]>([]);
  const [channels, setChannels] = useState<any[]>([]);
  const [breaking, setBreaking] = useState<any[]>([]);
  const [category, setCategory] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    setErr('');
    try {
      const q = new URLSearchParams({ limit: '50' });
      if (category) q.set('category', category);
      const [hRes, cRes, bRes] = await Promise.allSettled([
        api.get(`/news/headlines?${q}`),
        api.get('/news/channels'),
        api.get('/news/headlines/breaking'),
      ]);
      if (hRes.status === 'fulfilled') setHeadlines((hRes.value as any).data?.items || []);
      if (cRes.status === 'fulfilled') setChannels((cRes.value as any).data?.items || []);
      if (bRes.status === 'fulfilled') setBreaking((bRes.value as any).data?.items || []);
    } catch (e: any) {
      setErr(e?.message || 'Failed to load news');
    } finally { setLoading(false); setRefreshing(false); }
  }, [category]);

  useEffect(() => { load(); }, [load]);

  const grouped = useMemo(() => {
    const buckets: Record<string, any[]> = {};
    for (const h of headlines) {
      const c = h.category || 'features';
      (buckets[c] = buckets[c] || []).push(h);
    }
    return Object.entries(buckets).sort((a, b) => b[1].length - a[1].length);
  }, [headlines]);

  const catKeys = Object.keys(CATEGORIES);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView
        contentContainerStyle={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
      >
        <Text testID="news-title" style={s.title}>News</Text>
        <Text style={s.subtitle}>Breaking headlines & local stories</Text>

        {/* Breaking Strip */}
        {breaking.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.breakingStrip}>
            {breaking.map(b => (
              <View key={b.headline_id || b.id} testID={`news-breaking-${b.headline_id || b.id}`} style={s.breakingCard}>
                <View style={s.breakingBadge}>
                  <View style={s.breakingDot} />
                  <Text style={s.breakingBadgeText}>BREAKING</Text>
                </View>
                <Text style={s.breakingHeadline} numberOfLines={3}>{b.headline_text}</Text>
                {b.summary_text && <Text style={s.breakingSummary} numberOfLines={2}>{b.summary_text}</Text>}
                <Text style={s.breakingSource}>{b.source_name || '—'}</Text>
              </View>
            ))}
          </ScrollView>
        )}

        {/* Category chips */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipRow}>
          {catKeys.map(k => {
            const active = k === category;
            return (
              <TouchableOpacity key={k} testID={`news-cat-${k || 'all'}`}
                style={[common.pill, active && common.pillActive]}
                onPress={() => setCategory(k)}>
                <Text style={[common.pillText, active && common.pillTextActive]}>{CATEGORIES[k]}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        {/* Error */}
        {err ? <Text testID="news-error" style={{ color: COLORS.red, padding: SPACING.md }}>{err}</Text> : null}

        {/* Headlines by category */}
        {grouped.length === 0 && !err && (
          <View testID="news-empty" style={s.emptyWrap}>
            <Ionicons name="newspaper-outline" size={40} color={COLORS.textMuted} />
            <Text style={s.emptyText}>No headlines right now.</Text>
          </View>
        )}

        {grouped.map(([cat, items]) => (
          <View key={cat} testID={`news-group-${cat}`} style={s.group}>
            <Text style={s.groupTitle}>{(CATEGORIES[cat] || cat).toUpperCase()}</Text>
            {items.map(h => (
              <View key={h.headline_id || h.id} testID={`news-card-${h.headline_id || h.id}`} style={s.headlineCard}>
                <View style={s.headlineTop}>
                  {h.is_breaking && <View style={s.breakingDotSmall} />}
                  <Text style={s.headlineText} numberOfLines={3}>{h.headline_text}</Text>
                </View>
                {h.summary_text && <Text style={s.headlineSummary} numberOfLines={2}>{h.summary_text}</Text>}
                <View style={s.headlineMeta}>
                  <Text style={s.headlineSource}>{h.source_name || '—'}</Text>
                  {h.source_url && (
                    <TouchableOpacity onPress={() => Linking.openURL(h.source_url)} testID={`news-link-${h.headline_id || h.id}`}>
                      <Ionicons name="open-outline" size={12} color={COLORS.secondary} />
                    </TouchableOpacity>
                  )}
                  <Text style={s.headlineTime}>
                    {h.published_at ? new Date(h.published_at).toLocaleDateString() : ''}
                  </Text>
                </View>
              </View>
            ))}
          </View>
        ))}

        {/* News Channels */}
        {channels.length > 0 && (
          <View style={s.channelSection}>
            <Text style={common.sectionTitle}>NEWS CHANNELS</Text>
            {channels.map(ch => (
              <View key={ch.channel_id || ch.id} testID={`news-channel-${ch.channel_id || ch.id}`} style={s.channelCard}>
                <View style={s.channelIcon}>
                  <Ionicons name="radio" size={18} color={COLORS.secondary} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.channelName}>{ch.name}</Text>
                  <Text style={s.channelTag}>{ch.tagline || ch.city || '—'}</Text>
                </View>
                {ch.live && <View style={s.liveBadge}><Text style={s.liveText}>LIVE</Text></View>}
              </View>
            ))}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 40 },
  title: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900' },
  subtitle: { color: COLORS.textDim, fontSize: FONT.md, marginBottom: SPACING.md },
  breakingStrip: { marginBottom: SPACING.md },
  breakingCard: {
    width: 260, padding: SPACING.md, borderRadius: RADIUS.lg,
    backgroundColor: 'rgba(251,113,133,0.08)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.25)',
    marginRight: 10,
  },
  breakingBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 },
  breakingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.red },
  breakingBadgeText: { color: COLORS.red, fontSize: 9, fontWeight: '800', letterSpacing: 2 },
  breakingHeadline: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700', marginBottom: 4 },
  breakingSummary: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 18, marginBottom: 6 },
  breakingSource: { color: COLORS.textMuted, fontSize: FONT.xs },
  chipRow: { marginBottom: SPACING.md, flexGrow: 0 },
  emptyWrap: { alignItems: 'center', paddingVertical: 40 },
  emptyText: { color: COLORS.textMuted, fontSize: FONT.md, marginTop: 8 },
  group: { marginBottom: SPACING.lg },
  groupTitle: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2, marginBottom: SPACING.sm },
  headlineCard: {
    padding: SPACING.md, borderRadius: RADIUS.md,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: 8,
  },
  headlineTop: { flexDirection: 'row', alignItems: 'flex-start', gap: 8 },
  breakingDotSmall: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.red, marginTop: 6 },
  headlineText: { color: COLORS.text, fontSize: FONT.md, fontWeight: '600', flex: 1 },
  headlineSummary: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 18, marginTop: 6 },
  headlineMeta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 },
  headlineSource: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  headlineTime: { color: COLORS.textMuted, fontSize: FONT.xs },
  channelSection: { marginTop: SPACING.sm },
  channelCard: {
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: SPACING.md,
    borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1,
    borderColor: COLORS.cardBorder, marginBottom: 8,
  },
  channelIcon: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: 'rgba(59,130,246,0.1)',
    alignItems: 'center', justifyContent: 'center',
  },
  channelName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  channelTag: { color: COLORS.textMuted, fontSize: FONT.xs, marginTop: 2 },
  liveBadge: { backgroundColor: 'rgba(74,222,128,0.15)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6 },
  liveText: { color: COLORS.green, fontSize: 9, fontWeight: '800', letterSpacing: 1.5 },
});
