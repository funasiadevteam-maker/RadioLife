import React, { useEffect, useState, useMemo, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import api from '../../src/api/client';
import AdBanner from '../../src/components/AdBanner';

const openArticle = (router: any, h: any) => router.push({
  pathname: '/news-article',
  params: {
    headline_id: String(h.headline_id || h.id || ''),
    title: h.headline_text || '',
    summary: h.summary_text || '',
    source_name: h.source_name || '',
    source_url: h.source_url || '',
    image_url: h.image_url || '',
    published_at: h.published_at || '',
    category: h.category || '',
  },
});

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
  const [scope, setScope] = useState<'local' | 'national'>('local');
  const [strip, setStrip] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState('');
  const router = useRouter();

  const load = useCallback(async () => {
    setErr('');
    try {
      const q = new URLSearchParams({ limit: '50', scope });
      if (category) q.set('category', category);
      const [hRes, cRes, bRes] = await Promise.allSettled([
        api.get(`/news/headlines?${q}`),
        api.get('/news/channels'),
        api.get(`/news/headlines/breaking`),
      ]);
      if (hRes.status === 'fulfilled') setHeadlines((hRes.value as any).data?.items || []);
      if (cRes.status === 'fulfilled') setChannels((cRes.value as any).data?.items || []);
      if (bRes.status === 'fulfilled') setBreaking((bRes.value as any).data?.items || []);
    } catch (e: any) {
      setErr(e?.message || 'Failed to load news');
    } finally { setLoading(false); setRefreshing(false); }
  }, [category, scope]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get('/news/local-strip').then((r) => setStrip(r.data)).catch(() => {}); }, []);

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

        {/* FUUSIC Interactive News — voice AI anchor */}
        <TouchableOpacity testID="news-interactive-cta" activeOpacity={0.85}
          onPress={() => router.push('/fun-ai-news')}
          style={s.interactiveCta}>
          <View style={s.interactiveIcon}>
            <Ionicons name="radio" size={20} color="#fff" />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.interactiveTitle}>Interactive News</Text>
            <Text style={s.interactiveSub}>Your News. Your Questions. Your AI Anchor.</Text>
          </View>
          <Ionicons name="chevron-forward" size={18} color="#fff" />
        </TouchableOpacity>


        {/* Local weather + prayer-times strip */}
        {strip && (strip.weather || strip.prayer?.next) && (
          <View style={s.strip} testID="news-local-strip">
            <View style={s.stripSide}>
              <Ionicons name={strip.weather?.is_day ? 'sunny' : 'moon'} size={16} color={COLORS.orange} />
              <Text style={s.stripCity} numberOfLines={1}>{strip.city}</Text>
              {strip.weather && <Text style={s.stripTemp}>{strip.weather.temp_c}° · {strip.weather.label}</Text>}
            </View>
            {strip.prayer?.next && (
              <View style={s.stripSide}>
                <Ionicons name="moon-outline" size={13} color={COLORS.secondary} />
                <Text style={s.stripPrayer}>{strip.prayer.next.name} {strip.prayer.next.time}</Text>
              </View>
            )}
          </View>
        )}

        {/* Local / National scope tabs */}
        <View style={s.scopeRow}>
          {(['local', 'national'] as const).map((sc) => {
            const active = sc === scope;
            return (
              <TouchableOpacity key={sc} testID={`news-scope-${sc}`}
                style={[s.scopeTab, active && s.scopeTabActive]}
                onPress={() => setScope(sc)}>
                <Ionicons name={sc === 'local' ? 'location' : 'globe-outline'} size={14}
                  color={active ? '#fff' : COLORS.textMuted} />
                <Text style={[s.scopeTabText, active && s.scopeTabTextActive]}>
                  {sc === 'local' ? 'Local' : 'National'}
                </Text>
              </TouchableOpacity>
            );
          })}
        </View>

        {/* Breaking Strip */}
        {breaking.length > 0 && (
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.breakingStrip}>
            {breaking.map(b => (
              <TouchableOpacity key={b.headline_id || b.id} testID={`news-breaking-${b.headline_id || b.id}`} style={s.breakingCard}
                activeOpacity={0.85} onPress={() => openArticle(router, b)}>
                <View style={s.breakingBadge}>
                  <View style={s.breakingDot} />
                  <Text style={s.breakingBadgeText}>BREAKING</Text>
                </View>
                <Text style={s.breakingHeadline} numberOfLines={3}>{b.headline_text}</Text>
                {b.summary_text && <Text style={s.breakingSummary} numberOfLines={2}>{b.summary_text}</Text>}
                <Text style={s.breakingSource}>{b.source_name || '—'}</Text>
              </TouchableOpacity>
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
        <AdBanner zone="browse_row" style={{ marginBottom: SPACING.md }} />
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
              <TouchableOpacity key={h.headline_id || h.id} testID={`news-card-${h.headline_id || h.id}`} style={s.headlineCard}
                activeOpacity={0.8} onPress={() => openArticle(router, h)}>
                <View style={s.headlineTop}>
                  {h.is_breaking && <View style={s.breakingDotSmall} />}
                  <Text style={s.headlineText} numberOfLines={3}>{h.headline_text}</Text>
                </View>
                {h.summary_text && <Text style={s.headlineSummary} numberOfLines={2}>{h.summary_text}</Text>}
                <View style={s.headlineMeta}>
                  <Text style={s.headlineSource}>{h.source_name || '—'}</Text>
                  <Text style={s.headlineTime}>
                    {h.published_at ? new Date(h.published_at).toLocaleDateString() : ''}
                  </Text>
                  <View style={{ flex: 1 }} />
                  <Text style={s.readMore}>Read more</Text>
                  <Ionicons name="chevron-forward" size={13} color={COLORS.secondary} />
                </View>
              </TouchableOpacity>
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
  interactiveCta: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.md,
    backgroundColor: '#0E7490', borderRadius: RADIUS.lg,
    padding: SPACING.md, marginBottom: SPACING.md,
  },
  interactiveIcon: {
    width: 40, height: 40, borderRadius: 12, alignItems: 'center',
    justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.18)',
  },
  interactiveTitle: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
  interactiveSub: { color: 'rgba(255,255,255,0.85)', fontSize: FONT.xs, marginTop: 2 },
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
  scopeRow: { flexDirection: 'row', gap: 8, marginBottom: SPACING.md },
  strip: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: COLORS.inputBg, borderRadius: RADIUS.lg, paddingVertical: 10, paddingHorizontal: 14, marginBottom: SPACING.md },
  stripSide: { flexDirection: 'row', alignItems: 'center', gap: 6, flexShrink: 1 },
  stripCity: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  stripTemp: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  stripPrayer: { color: COLORS.secondary, fontSize: FONT.sm, fontWeight: '800' },
  scopeTab: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 8, paddingHorizontal: 16, borderRadius: 999, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.border },
  scopeTabActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  scopeTabText: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '800' },
  scopeTabTextActive: { color: '#fff' },
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
  readMore: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '800' },
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
