import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, Share, Platform,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../../../src/constants/theme';
import { BACKEND } from '../../../src/api/client';
import axios from 'axios';

const TIER_COLORS: Record<string, string> = {
  bronze: '#b67334', silver: '#cfd6df', gold: '#ffd75e',
  platinum: '#d6f0ff', diamond: '#c4f5ff', unique: '#ff6ec4',
};

export default function PublicPassportScreen() {
  const { userId } = useLocalSearchParams<{ userId: string }>();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!userId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await axios.get(`${BACKEND}/api/passport/${userId}`);
      setData(r.data);
    } catch (e: any) {
      setError(e?.response?.status || 500);
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => { load(); }, [load]);

  const shareProfile = async () => {
    const url = `${BACKEND}/passport/${userId}?ref=${data?.referral_code || ''}`;
    try {
      await Share.share({
        message: `Check out ${data?.display_name}'s profile on BigFM! ${url}`,
        url,
      });
    } catch {
      try {
        const { default: Clipboard } = await import('expo-clipboard');
        await Clipboard.setStringAsync(url);
        Alert.alert('Copied!', 'Profile link copied to clipboard');
      } catch {}
    }
  };

  const copyReferral = async () => {
    const url = `${BACKEND}/?ref=${data?.referral_code || ''}`;
    try {
      const { default: Clipboard } = await import('expo-clipboard');
      await Clipboard.setStringAsync(url);
      Alert.alert('Copied!', 'Referral link copied to clipboard');
    } catch {}
  };

  if (loading) {
    return (
      <View style={st.center} testID="pub-passport-loading">
        <ActivityIndicator size="large" color={COLORS.primary} />
        <Text style={st.loadingText}>Loading profile…</Text>
      </View>
    );
  }

  if (error || !data) {
    return (
      <SafeAreaView style={st.screen} testID="pub-passport-404">
        <View style={st.center}>
          <Ionicons name="alert-circle" size={36} color={COLORS.textDim} />
          <Text style={st.errorTitle}>Profile not available</Text>
          <Text style={st.errorSub}>
            This listener hasn't made their profile public, or the link is invalid.
          </Text>
          <TouchableOpacity style={st.backBtn} onPress={() => router.back()} testID="pub-passport-back">
            <Ionicons name="arrow-back" size={14} color="#fff" />
            <Text style={st.backBtnText}>Go back</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const amb = data.ambassador || {};
  const ls = data.listening_stats || {};
  const badges = data.badges || [];

  // Group badges by category
  const byCat: Record<string, any[]> = {};
  badges.forEach((b: any) => {
    const cat = b.category || 'General';
    if (!byCat[cat]) byCat[cat] = [];
    byCat[cat].push(b);
  });

  return (
    <SafeAreaView style={st.screen} testID="pub-passport-page">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        {/* Back nav */}
        <TouchableOpacity onPress={() => router.back()} style={st.backRow} testID="pub-passport-nav-back">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={st.backRowText}>back</Text>
        </TouchableOpacity>

        {/* Hero Card */}
        <View style={st.heroCard} testID="pub-passport-hero">
          <View style={[st.avatar, { backgroundColor: TIER_COLORS[amb.level_name?.toLowerCase()] || COLORS.primary }]}>
            {data.avatar_url ? (
              <Text style={st.avatarText}>{data.avatar_initial || '?'}</Text>
            ) : (
              <Text style={st.avatarText}>{data.avatar_initial || (data.display_name || '?').charAt(0).toUpperCase()}</Text>
            )}
          </View>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <Text style={st.heroName} testID="pub-passport-name">{data.display_name}</Text>
              {data.is_annual_subscriber && (
                <View style={st.annualBadge}>
                  <Text style={st.annualText}>✨ ANNUAL</Text>
                </View>
              )}
              {data.city_pin && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                  <Ionicons name="location" size={11} color={COLORS.secondary} />
                  <Text style={{ fontSize: 10, color: COLORS.secondary }}>{data.city_pin}</Text>
                </View>
              )}
            </View>
            {data.bio && <Text style={st.heroBio}>{data.bio}</Text>}
            <View style={st.statsRow}>
              {amb.level != null && (
                <View style={st.statItem}>
                  <Text style={st.statNum}>L{amb.level}</Text>
                  <Text style={st.statLabel}>{amb.level_name || 'Listener'}</Text>
                </View>
              )}
              <View style={st.statItem}>
                <Text style={st.statNum}>{data.badges_total ?? badges.length}</Text>
                <Text style={st.statLabel}>badges</Text>
              </View>
              {ls.hours_total != null && (
                <View style={st.statItem}>
                  <Text style={st.statNum}>{ls.hours_total}h</Text>
                  <Text style={st.statLabel}>listened</Text>
                </View>
              )}
              {amb.points != null && (
                <View style={st.statItem}>
                  <Text style={st.statNum}>{amb.points}</Text>
                  <Text style={st.statLabel}>points</Text>
                </View>
              )}
            </View>
          </View>
        </View>

        {/* Referral CTA */}
        {data.referral_code && (
          <View style={st.referCta} testID="pub-passport-refer-cta">
            <View style={{ flex: 1 }}>
              <Text style={st.referTitle}>
                Refer & earn <Text style={{ color: COLORS.gold, fontWeight: '800' }}>100 BigCoin</Text>
              </Text>
              <Text style={st.referSub}>
                Sign up via {data.display_name}'s link — they get 100 BC when you complete onboarding.
              </Text>
            </View>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: SPACING.sm }}>
              <TouchableOpacity style={st.ctaBtn} onPress={copyReferral} testID="pub-passport-copy-ref">
                <Ionicons name="copy" size={12} color="#fff" />
                <Text style={st.ctaBtnText}>Copy</Text>
              </TouchableOpacity>
              <TouchableOpacity style={st.ctaBtnGhost} onPress={shareProfile} testID="pub-passport-share-ref">
                <Ionicons name="share-outline" size={12} color={COLORS.textDim} />
                <Text style={st.ctaGhostText}>Share</Text>
              </TouchableOpacity>
            </View>
          </View>
        )}

        {/* Badge wall by category */}
        {badges.length > 0 ? (
          Object.entries(byCat).map(([cat, items]) => (
            <View key={cat} style={st.section} testID={`pub-passport-cat-${cat}`}>
              <Text style={st.sectionHead}>
                <Ionicons name="trophy" size={12} color={COLORS.gold} /> {cat}
                <Text style={st.sectionCount}> ({items.length})</Text>
              </Text>
              <View style={st.badgeGrid}>
                {items.map((b: any) => (
                  <View key={b.badge_id} style={st.badgeCard} testID={`pub-badge-${b.badge_id}`}>
                    <View style={[st.badgeIcon, { backgroundColor: TIER_COLORS[b.tier] || COLORS.primary }]}>
                      <Text style={st.badgeIconText}>{(b.name || '?').charAt(0).toUpperCase()}</Text>
                    </View>
                    <View style={{ flex: 1, marginLeft: 8 }}>
                      <Text style={st.badgeName}>{b.name}</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                        <Ionicons name="star" size={9} color={COLORS.gold} />
                        <Text style={st.badgePts}>{b.points} pts</Text>
                        <View style={[st.tierChip, { backgroundColor: `${TIER_COLORS[b.tier] || COLORS.textDim}22` }]}>
                          <Text style={[st.tierChipText, { color: TIER_COLORS[b.tier] || COLORS.textDim }]}>{b.tier}</Text>
                        </View>
                      </View>
                      {b.earned_at && (
                        <Text style={st.earnedDate}>Earned {new Date(b.earned_at).toLocaleDateString()}</Text>
                      )}
                    </View>
                    <Ionicons name="sparkles" size={14} color={COLORS.gold} />
                  </View>
                ))}
              </View>
            </View>
          ))
        ) : (
          <View style={st.emptyBox} testID="pub-passport-no-badges">
            <Ionicons name="ribbon" size={28} color={COLORS.textDim} />
            <Text style={st.emptyTitle}>No badges shown</Text>
            <Text style={st.emptySub}>
              {data.display_name} hasn't opted to display badges publicly.
            </Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, backgroundColor: COLORS.bg, justifyContent: 'center', alignItems: 'center', padding: SPACING.xl },
  loadingText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.sm },
  errorTitle: { color: COLORS.text, fontSize: 18, fontWeight: '700', marginTop: SPACING.md },
  errorSub: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 8, textAlign: 'center', lineHeight: 20 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, paddingHorizontal: 20, paddingVertical: 12, borderRadius: RADIUS.md, marginTop: SPACING.lg },
  backBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.sm },
  backRowText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  heroCard: { flexDirection: 'row', gap: SPACING.md, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  avatar: { width: 60, height: 60, borderRadius: 30, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 26, fontWeight: '800', color: '#fff' },
  heroName: { fontSize: 20, fontWeight: '900', color: COLORS.text },
  annualBadge: { backgroundColor: 'rgba(255,215,94,0.12)', borderWidth: 1, borderColor: 'rgba(255,215,94,0.35)', paddingHorizontal: 8, paddingVertical: 2, borderRadius: RADIUS.full },
  annualText: { color: COLORS.gold, fontSize: 9, fontWeight: '800' },
  heroBio: { fontSize: 13, color: COLORS.textDim, marginTop: 4, lineHeight: 18 },
  statsRow: { flexDirection: 'row', gap: SPACING.lg, marginTop: SPACING.sm },
  statItem: { alignItems: 'center' },
  statNum: { fontSize: 18, fontWeight: '800', color: COLORS.text },
  statLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '600', marginTop: 2 },
  referCta: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.md },
  referTitle: { color: COLORS.text, fontSize: 14, fontWeight: '600' },
  referSub: { color: COLORS.textDim, fontSize: 11, marginTop: 4, lineHeight: 16 },
  ctaBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: RADIUS.md },
  ctaBtnText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  ctaBtnGhost: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder, paddingHorizontal: 16, paddingVertical: 10, borderRadius: RADIUS.md },
  ctaGhostText: { color: COLORS.textDim, fontSize: 12, fontWeight: '700' },
  section: { marginBottom: SPACING.lg },
  sectionHead: { fontSize: 13, color: COLORS.textDim, fontWeight: '700', marginBottom: SPACING.sm },
  sectionCount: { fontWeight: '600' },
  badgeGrid: { gap: SPACING.sm },
  badgeCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.sm, borderWidth: 1, borderColor: COLORS.cardBorder },
  badgeIcon: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center' },
  badgeIconText: { color: '#fff', fontSize: 16, fontWeight: '800' },
  badgeName: { color: COLORS.text, fontSize: 13, fontWeight: '700' },
  badgePts: { color: COLORS.textDim, fontSize: 10 },
  tierChip: { paddingHorizontal: 6, paddingVertical: 1, borderRadius: RADIUS.full },
  tierChipText: { fontSize: 9, fontWeight: '700' },
  earnedDate: { color: COLORS.textDim, fontSize: 10, marginTop: 2 },
  emptyBox: { alignItems: 'center', paddingVertical: SPACING.xxl },
  emptyTitle: { color: COLORS.text, fontSize: 16, fontWeight: '700', marginTop: SPACING.sm },
  emptySub: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 4, textAlign: 'center' },
});
