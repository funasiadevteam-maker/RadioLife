import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, ActivityIndicator,
  RefreshControl, StyleSheet, Alert,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../../src/constants/theme';
import { getChannel, getChannelEpisodes, getChannelSubscriptionStatus } from '../../../src/api/podcastApi';

export default function CreatorChannelDetail() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [channel, setChannel] = useState<any>(null);
  const [episodes, setEpisodes] = useState<any[]>([]);
  const [subStatus, setSubStatus] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const [chRes, eps, ss] = await Promise.all([
        getChannel(id),
        getChannelEpisodes(id, true),
        getChannelSubscriptionStatus(id).catch(() => null),
      ]);
      setChannel(chRes?.channel || chRes);
      setEpisodes(eps);
      setSubStatus(ss);
    } catch (e: any) {
      setErr(e?.response?.data?.detail || e?.message || 'Failed to load channel');
    } finally { setLoading(false); setRefreshing(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  if (err) return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <View style={{ padding: SPACING.lg }}>
        <TouchableOpacity onPress={() => router.back()} style={{ marginBottom: 12 }}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text testID="channel-detail-error" style={{ color: COLORS.red, fontSize: FONT.md }}>{err}</Text>
      </View>
    </SafeAreaView>
  );

  const published = episodes.filter(e => e.publish_status === 'published');
  const drafts = episodes.filter(e => e.publish_status !== 'published');

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView
        contentContainerStyle={{ padding: SPACING.lg, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
      >
        {/* Header */}
        <View style={s.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text testID="channel-detail-title" style={s.title}>{channel?.title || 'Channel'}</Text>
            <Text style={s.subtitle}>
              {channel?.category} · {channel?.language} · {channel?.active ? 'LIVE' : 'pending'}
            </Text>
          </View>
        </View>

        {/* Subscription gating banner */}
        {subStatus && subStatus.subscription_status !== 'active' && (
          <View testID="channel-sub-gating-banner" style={s.subBanner}>
            <Ionicons name="lock-closed-outline" size={18} color={COLORS.orange} />
            <View style={{ flex: 1 }}>
              <Text style={s.subBannerTitle}>Subscription Not Active</Text>
              <Text style={s.subBannerText}>Set up a subscription plan to monetize this channel.</Text>
            </View>
            <TouchableOpacity testID="channel-sub-setup-cta" style={s.subCta}
              onPress={() => router.push(`/creator/channel-settings/${id}`)}>
              <Text style={s.subCtaText}>Set Up</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Quick actions */}
        <View style={s.actionsRow}>
          <TouchableOpacity testID="channel-settings-btn" style={s.actionBtn}
            onPress={() => router.push(`/creator/channel-settings/${id}`)}>
            <Ionicons name="settings-outline" size={16} color="#0a0a0c" />
            <Text style={s.actionBtnText}>Settings</Text>
          </TouchableOpacity>
        </View>

        {/* Published episodes */}
        <Text style={common.sectionTitle}>Published ({published.length})</Text>
        {published.length === 0 && (
          <Text style={s.emptyText}>No published episodes yet.</Text>
        )}
        {published.map(ep => (
          <TouchableOpacity key={ep.id} testID={`episode-row-${ep.id}`}
            style={s.epRow} onPress={() => router.push(`/creator/episode/${ep.id}`)}>
            <View style={s.epIcon}>
              <Ionicons name="play-circle" size={20} color={COLORS.green} />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.epTitle} numberOfLines={2}>{ep.title || 'Untitled'}</Text>
              <Text style={s.epMeta}>
                {ep.published_at ? new Date(ep.published_at).toLocaleDateString() : '—'} · {ep.duration_sec ? `${Math.floor(ep.duration_sec / 60)}m` : '—'}
              </Text>
            </View>
            <Ionicons name="chevron-forward" size={16} color={COLORS.textDim} />
          </TouchableOpacity>
        ))}

        {/* Drafts */}
        {drafts.length > 0 && (
          <>
            <Text style={[common.sectionTitle, { marginTop: SPACING.lg }]}>Drafts ({drafts.length})</Text>
            {drafts.map(ep => (
              <TouchableOpacity key={ep.id} testID={`episode-draft-row-${ep.id}`}
                style={[s.epRow, { borderColor: 'rgba(245,158,11,0.2)' }]}
                onPress={() => router.push(`/creator/episode/${ep.id}`)}>
                <View style={[s.epIcon, { backgroundColor: 'rgba(245,158,11,0.1)' }]}>
                  <Ionicons name="document-text-outline" size={18} color={COLORS.orange} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.epTitle} numberOfLines={2}>{ep.title || 'Untitled draft'}</Text>
                  <Text style={s.epMeta}>
                    Draft · {ep.created_at ? new Date(ep.created_at).toLocaleDateString() : '—'}
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={16} color={COLORS.textDim} />
              </TouchableOpacity>
            ))}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: SPACING.lg },
  title: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  subtitle: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 2 },
  subBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, borderRadius: 10,
    borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)', backgroundColor: 'rgba(245,158,11,0.05)',
    marginBottom: SPACING.lg,
  },
  subBannerTitle: { fontSize: FONT.sm, fontWeight: '700', color: COLORS.orange },
  subBannerText: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 2 },
  subCta: { backgroundColor: COLORS.orange, paddingVertical: 6, paddingHorizontal: 12, borderRadius: 6 },
  subCtaText: { fontWeight: '700', fontSize: FONT.xs, color: '#0a0a0c' },
  actionsRow: { flexDirection: 'row', gap: 10, marginBottom: SPACING.lg },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.orange, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 8 },
  actionBtnText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.sm },
  epRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, marginBottom: 8,
    borderRadius: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  epIcon: {
    width: 36, height: 36, borderRadius: 8, backgroundColor: 'rgba(74,222,128,0.1)',
    alignItems: 'center', justifyContent: 'center',
  },
  epTitle: { fontSize: FONT.md, fontWeight: '600', color: COLORS.text },
  epMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 3 },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', paddingVertical: 20 },
});
