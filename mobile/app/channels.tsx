import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../src/contexts/AuthContext';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import { useGateStore } from '../src/stores/gateStore';

const FILTER_LANGS = ['All', 'Hindi', 'Punjabi', 'English', 'Tamil', 'Arabic', 'Malayalam'];
const FILTER_MOODS = ['All', 'Chill', 'Party', 'Romantic', 'Energetic', 'Devotional'];
const FILTER_ACTS = ['All', 'Commute', 'Workout', 'Dinner', 'Late Night', 'Morning'];

export default function ChannelsScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const openGate = useGateStore((s) => s.openGate);
  const [channels, setChannels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filterLang, setFilterLang] = useState('All');
  const [filterMood, setFilterMood] = useState('All');
  const [filterAct, setFilterAct] = useState('All');
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
  }, [user, authLoading]);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/channels');
      setChannels(r.data.channels || []);
    } catch {} finally { setLoading(false); }
  }, []);

  useEffect(() => { if (!authLoading && user) load(); }, [load, authLoading, user]);

  const filtered = channels.filter((c) => {
    if (search && !c.name?.toLowerCase().includes(search.toLowerCase())) return false;
    if (filterLang !== 'All') {
      const langs = (c.languages || c.language_tags || []).map((l: string) => l.toLowerCase());
      if (!langs.includes(filterLang.toLowerCase())) return false;
    }
    if (filterMood !== 'All') {
      const moods = (c.moods || c.mood_tags || []).map((m: string) => m.toLowerCase());
      if (!moods.includes(filterMood.toLowerCase())) return false;
    }
    if (filterAct !== 'All') {
      const acts = (c.activities || c.activity_tags || []).map((a: string) => a.toLowerCase().replace(/_/g, ' '));
      if (!acts.some((a: string) => a.includes(filterAct.toLowerCase()))) return false;
    }
    return true;
  });

  const handleChannelTap = (ch: any) => {
    const access = ch.access || { allowed: true };
    if (access.allowed === false) {
      openGate(access, { slug: ch.slug, name: ch.name });
      return;
    }
    router.push({ pathname: '/(tabs)/radio', params: { channel: ch.slug } });
  };

  if (authLoading || loading) {
    return <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={s.screen} testID="channels-screen">
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} testID="channels-back-btn" style={s.backBtn}>
          <Ionicons name="chevron-back" size={20} color={COLORS.textDim} />
        </TouchableOpacity>
        <Text style={s.headerTitle}>All Channels</Text>
        <View style={{ width: 36 }} />
      </View>

      {/* Search */}
      <View style={s.searchRow}>
        <Ionicons name="search" size={16} color={COLORS.textMuted} />
        <TextInput
          style={s.searchInput}
          placeholder="Search channels..."
          placeholderTextColor={COLORS.textMuted}
          value={search}
          onChangeText={setSearch}
          testID="channels-search-input"
        />
      </View>

      {/* Filter chips */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filterRow} contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 6 }}>
        <Text style={s.filterLabel}>LANG</Text>
        {FILTER_LANGS.map((l) => (
          <TouchableOpacity key={l} style={[s.filterChip, filterLang === l && s.filterChipActive]}
            onPress={() => setFilterLang(l)} testID={`filter-lang-${l.toLowerCase()}`}>
            <Text style={[s.filterChipText, filterLang === l && s.filterChipTextActive]}>{l}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filterRow} contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 6 }}>
        <Text style={s.filterLabel}>MOOD</Text>
        {FILTER_MOODS.map((m) => (
          <TouchableOpacity key={m} style={[s.filterChip, filterMood === m && s.filterChipActive]}
            onPress={() => setFilterMood(m)} testID={`filter-mood-${m.toLowerCase()}`}>
            <Text style={[s.filterChipText, filterMood === m && s.filterChipTextActive]}>{m}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={[s.filterRow, { marginBottom: SPACING.md }]} contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 6 }}>
        <Text style={s.filterLabel}>VIBE</Text>
        {FILTER_ACTS.map((a) => (
          <TouchableOpacity key={a} style={[s.filterChip, filterAct === a && s.filterChipActive]}
            onPress={() => setFilterAct(a)} testID={`filter-act-${a.toLowerCase().replace(/ /g, '-')}`}>
            <Text style={[s.filterChipText, filterAct === a && s.filterChipTextActive]}>{a}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={s.countLabel}>{filtered.length} channel{filtered.length !== 1 ? 's' : ''}</Text>

      {/* Channel Grid */}
      <ScrollView contentContainerStyle={s.grid}>
        {filtered.map((ch) => {
          const access = ch.access || { allowed: true };
          const locked = access.allowed === false;
          const tier = ch.exclusivity_tier || 'free';
          const isPremiumTier = tier === 'premium' || ch.premium_only;
          const isAmbassadorTier = tier?.startsWith('ambassador_');
          const hostsLine = ch.hosts?.length ? ch.hosts.map((h: any) => h.name).join(' × ') : 'Auto DJ';
          const coverColor = ch.cover_color || COLORS.primary;

          return (
            <TouchableOpacity
              key={ch.slug}
              style={[s.card, { borderTopColor: coverColor, borderTopWidth: 3 }]}
              onPress={() => handleChannelTap(ch)}
              activeOpacity={0.7}
              testID={`channel-grid-${ch.slug}`}
            >
              {/* Exclusivity badge */}
              {(isPremiumTier || isAmbassadorTier) && (
                <View style={[s.tierBadge, isPremiumTier && s.tierBadgePremium, isAmbassadorTier && s.tierBadgeAmbassador]}>
                  <Ionicons name={locked ? 'lock-closed' : 'diamond'} size={9} color={isPremiumTier ? COLORS.gold : '#22d3ee'} />
                  <Text style={[s.tierBadgeText, isPremiumTier && { color: COLORS.gold }, isAmbassadorTier && { color: '#22d3ee' }]}>
                    {isPremiumTier ? 'VIP' : tier?.replace('ambassador_', 'L').toUpperCase()}
                  </Text>
                </View>
              )}
              {tier === 'free' && !isPremiumTier && !isAmbassadorTier && (
                <View style={[s.tierBadge, { borderColor: COLORS.green }]}>
                  <Ionicons name="radio" size={9} color={COLORS.green} />
                  <Text style={[s.tierBadgeText, { color: COLORS.green }]}>FREE</Text>
                </View>
              )}

              {/* Channel name */}
              <Text style={s.cardName} numberOfLines={1}>{ch.name}</Text>
              {ch.tagline && <Text style={s.cardTagline} numberOfLines={1}>{ch.tagline}</Text>}

              {/* Language tags */}
              {(ch.languages || ch.language_tags || []).length > 0 && (
                <View style={s.tagRow}>
                  {(ch.languages || ch.language_tags || []).slice(0, 3).map((l: string) => (
                    <View key={l} style={s.tag}>
                      <Text style={s.tagText}>{l}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Mood/genre chips */}
              {(ch.moods || ch.mood_tags || ch.genre_tags || []).length > 0 && (
                <View style={s.tagRow}>
                  {(ch.moods || ch.mood_tags || ch.genre_tags || []).slice(0, 2).map((m: string) => (
                    <View key={m} style={[s.tag, { borderColor: 'rgba(255,45,149,0.3)' }]}>
                      <Text style={[s.tagText, { color: COLORS.primary }]}>{m}</Text>
                    </View>
                  ))}
                </View>
              )}

              {/* Hosts */}
              <Text style={s.cardHosts}>with {hostsLine}</Text>

              {/* Locked overlay */}
              {locked && (
                <View style={s.lockedOverlay}>
                  <Ionicons name={access.upgrade_path === 'earn_badges' ? 'sparkles' : 'lock-closed'} size={14} color="#fff" />
                  <Text style={s.lockedText}>
                    {access.upgrade_path === 'earn_badges' ? 'EARN TO UNLOCK' : 'UPGRADE'}
                  </Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
  },
  backBtn: { padding: 8, borderRadius: RADIUS.sm, backgroundColor: COLORS.card },
  headerTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '900' },
  searchRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    marginHorizontal: SPACING.md, marginBottom: SPACING.sm,
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10,
  },
  searchInput: { flex: 1, color: '#fff', fontSize: FONT.md },
  filterRow: { maxHeight: 40, marginBottom: 4 },
  filterLabel: {
    color: COLORS.textMuted, fontSize: 9, fontWeight: '700', letterSpacing: 1.5,
    alignSelf: 'center', marginRight: 4,
  },
  filterChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  filterChipActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  filterChipText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  filterChipTextActive: { color: '#fff', fontWeight: '700' },
  countLabel: {
    color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2,
    paddingHorizontal: SPACING.md, marginBottom: SPACING.sm,
  },
  grid: {
    flexDirection: 'row', flexWrap: 'wrap', paddingHorizontal: SPACING.md,
    gap: SPACING.sm, paddingBottom: 40,
  },
  card: {
    width: '48%', backgroundColor: COLORS.card, borderRadius: RADIUS.md,
    borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.sm + 2,
    position: 'relative', overflow: 'hidden',
  },
  tierBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 3, alignSelf: 'flex-start',
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.sm,
    borderWidth: 1, borderColor: 'rgba(255,215,0,0.3)', marginBottom: 6,
  },
  tierBadgePremium: { borderColor: 'rgba(255,215,0,0.4)', backgroundColor: 'rgba(255,215,0,0.08)' },
  tierBadgeAmbassador: { borderColor: 'rgba(34,211,238,0.4)', backgroundColor: 'rgba(34,211,238,0.08)' },
  tierBadgeText: { fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  cardName: { color: '#fff', fontSize: FONT.sm, fontWeight: '800', marginBottom: 2 },
  cardTagline: { color: COLORS.textDim, fontSize: 10, marginBottom: 4 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, marginBottom: 4 },
  tag: {
    paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.sm,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.15)',
  },
  tagText: { color: COLORS.textDim, fontSize: 9, fontWeight: '600', letterSpacing: 0.5 },
  cardHosts: { color: COLORS.textMuted, fontSize: 9, fontWeight: '600', marginTop: 4 },
  lockedOverlay: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(10,12,24,0.9)', paddingVertical: 6,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
  },
  lockedText: { color: '#fff', fontSize: 9, fontWeight: '800', letterSpacing: 1 },
});
