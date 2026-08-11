import { useEffect, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  ActivityIndicator, StyleSheet,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../src/constants/theme';
import { getCreatorMe, getFunnelSummary, getFunnelDaily } from '../../src/api/podcastApi';

const STAGES = [
  { key: 'visits', label: 'Channel Visits', next: 'plays', color: '#5dd6c2' },
  { key: 'plays', label: 'Episode Plays', next: 'cta_clicks', color: '#7aa5ff' },
  { key: 'cta_clicks', label: 'CTA Clicks', next: 'trials', color: '#f0b95a' },
  { key: 'trials', label: 'Trials Started', next: 'conversions', color: '#d27ad8' },
  { key: 'conversions', label: 'Paid Subs', next: null, color: '#ff8a6b' },
];

function dropoff(curr: number, next: number) {
  if (!curr) return null;
  return Math.round(((curr - next) / curr) * 100);
}

export default function FunnelDashboard() {
  const router = useRouter();
  const [creatorId, setCreatorId] = useState<string | null>(null);
  const [summary, setSummary] = useState<any>(null);
  const [daily, setDaily] = useState<any[]>([]);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        const me = await getCreatorMe();
        const c = me?.creator || me;
        if (c?.id) setCreatorId(c.id);
        else setErr('no_creator_profile');
      } catch (e: any) { setErr(e?.response?.data?.detail || 'load_creator_failed'); }
    })();
  }, []);

  useEffect(() => {
    if (!creatorId) return;
    setLoading(true);
    (async () => {
      try {
        const [s, d] = await Promise.all([
          getFunnelSummary(creatorId, days),
          getFunnelDaily(creatorId, days),
        ]);
        setSummary(s); setDaily(d.series || []);
      } catch (e: any) { setErr(e?.response?.data?.detail || 'load_funnel_failed'); }
      finally { setLoading(false); }
    })();
  }, [creatorId, days]);

  if (err) return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <View style={{ padding: SPACING.lg }}>
        <TouchableOpacity onPress={() => router.back()} style={{ marginBottom: 12 }}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text testID="mobile-funnel-error" style={{ color: '#ff8a6b' }}>Error: {err}</Text>
      </View>
    </SafeAreaView>
  );

  if (loading || !summary) return (
    <View style={common.center}>
      <ActivityIndicator testID="mobile-funnel-loading" size="large" color={COLORS.primary} />
    </View>
  );

  const totals = summary.overall || {};
  const isEmpty = STAGES.every(s => (totals[s.key] || 0) === 0);

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView contentContainerStyle={{ padding: SPACING.lg, paddingBottom: 60 }}>
        {/* Header */}
        <View style={st.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={st.headerLabel}>CONVERSION FUNNEL</Text>
            <Text testID="mobile-funnel-title" style={st.title}>
              Subscription funnel — last {days} days
            </Text>
          </View>
        </View>

        {/* Range toggle */}
        <View testID="mobile-funnel-range-toggle" style={st.rangeRow}>
          {[7, 14, 30].map(n => (
            <TouchableOpacity key={n} testID={`mobile-funnel-range-${n}`}
              style={[st.rangePill, days === n && st.rangePillActive]}
              onPress={() => setDays(n)}>
              <Text style={[st.rangePillText, days === n && st.rangePillTextActive]}>{n}d</Text>
            </TouchableOpacity>
          ))}
        </View>

        {isEmpty ? (
          <View testID="mobile-funnel-empty-state" style={[common.card, { padding: 40, alignItems: 'center' }]}>
            <Ionicons name="trending-up-outline" size={40} color={COLORS.textDim} />
            <Text style={{ fontSize: FONT.lg, fontWeight: '700', color: COLORS.text, marginTop: 12 }}>
              Your first {days} days will appear here
            </Text>
            <Text style={{ fontSize: FONT.sm, color: COLORS.textDim, marginTop: 6, textAlign: 'center', lineHeight: 20 }}>
              As listeners visit your channel, play episodes, and consider subscribing, every step will show up in this funnel.
            </Text>
          </View>
        ) : (
          <>
            {/* Stage cards — horizontal scroll */}
            <ScrollView testID="mobile-funnel-stage-strip" horizontal showsHorizontalScrollIndicator={false}
              style={{ marginBottom: SPACING.lg }}>
              {STAGES.map((stage, i) => {
                const val = totals[stage.key] || 0;
                const nextVal = stage.next ? (totals[stage.next] || 0) : null;
                const drop = nextVal !== null ? dropoff(val, nextVal) : null;
                return (
                  <View key={stage.key} testID={`mobile-funnel-stage-${stage.key}`}
                    style={[st.stageCard, { borderLeftColor: stage.color }]}>
                    <Text style={st.stageLabel}>{stage.label}</Text>
                    <Text testID={`mobile-funnel-stage-${stage.key}-count`} style={st.stageCount}>
                      {val.toLocaleString()}
                    </Text>
                    {drop !== null && (
                      <Text testID={`mobile-funnel-stage-${stage.key}-dropoff`}
                        style={[st.stageDrop, drop > 50 && { color: '#ff8a6b' }]}>
                        ↓ {drop}% dropoff
                      </Text>
                    )}
                  </View>
                );
              })}
            </ScrollView>

            {/* Daily sparkline bars */}
            {daily.length > 0 && (
              <View testID="mobile-funnel-daily" style={common.card}>
                <Text style={common.sectionTitle}>Daily Activity</Text>
                {daily.slice(-10).map((row: any, i: number) => {
                  const maxVal = Math.max(1, ...daily.map((d: any) => d.visits || 0));
                  const barW = Math.max(4, ((row.visits || 0) / maxVal) * 100);
                  return (
                    <View key={row.date || i} style={st.dailyRow}>
                      <Text style={st.dailyDate}>{String(row.date || '').slice(5)}</Text>
                      <View style={st.dailyBarTrack}>
                        <View style={[st.dailyBar, { width: `${barW}%` }]} />
                      </View>
                      <Text style={st.dailyVal}>{row.visits || 0}</Text>
                    </View>
                  );
                })}
              </View>
            )}

            {/* Per-channel table */}
            {(summary.per_channel || []).length > 0 && (
              <View testID="mobile-funnel-channel-table" style={[common.card, { marginTop: 12, padding: 0 }]}>
                <View style={st.tableHeader}>
                  <Text style={[st.th, { flex: 1.5 }]}>Channel</Text>
                  <Text style={st.th}>Visits</Text>
                  <Text style={st.th}>Plays</Text>
                  <Text style={st.th}>Trials</Text>
                  <Text style={st.th}>Paid</Text>
                </View>
                {summary.per_channel.map((r: any) => (
                  <View key={r.channel_id} testID={`mobile-funnel-ch-${r.channel_id}`} style={st.tableRow}>
                    <Text style={[st.td, { flex: 1.5 }]} numberOfLines={1}>{r.channel_name || r.channel_id}</Text>
                    <Text style={st.td}>{r.visits}</Text>
                    <Text style={st.td}>{r.plays}</Text>
                    <Text style={st.td}>{r.trials}</Text>
                    <Text style={st.td}>{r.conversions}</Text>
                  </View>
                ))}
              </View>
            )}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: SPACING.md },
  headerLabel: { fontSize: 10, color: COLORS.textDim, letterSpacing: 0.8 },
  title: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text, marginTop: 2 },
  rangeRow: { flexDirection: 'row', gap: 6, marginBottom: SPACING.lg },
  rangePill: { paddingVertical: 6, paddingHorizontal: 14, borderRadius: 999, backgroundColor: COLORS.card },
  rangePillActive: { backgroundColor: '#2f8fff' },
  rangePillText: { color: COLORS.textDim, fontSize: FONT.sm },
  rangePillTextActive: { color: '#fff', fontWeight: '700' },
  stageCard: {
    width: 150, padding: 14, marginRight: 10, borderRadius: 10,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    borderLeftWidth: 4,
  },
  stageLabel: { fontSize: 10, color: COLORS.textDim, letterSpacing: 0.8, marginBottom: 6 },
  stageCount: { fontSize: 28, fontWeight: '800', color: COLORS.text },
  stageDrop: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 4 },
  dailyRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 },
  dailyDate: { fontSize: 10, color: COLORS.textDim, width: 36, fontVariant: ['tabular-nums'] },
  dailyBarTrack: { flex: 1, height: 6, backgroundColor: 'rgba(255,255,255,0.04)', borderRadius: 3 },
  dailyBar: { height: 6, borderRadius: 3, backgroundColor: '#5dd6c2' },
  dailyVal: { fontSize: 10, color: COLORS.textDim, width: 28, textAlign: 'right', fontVariant: ['tabular-nums'] },
  tableHeader: { flexDirection: 'row', padding: 10, backgroundColor: '#1c1f26', borderTopLeftRadius: RADIUS.lg, borderTopRightRadius: RADIUS.lg },
  th: { flex: 1, fontSize: 9, color: COLORS.textDim, letterSpacing: 0.6, textTransform: 'uppercase' },
  tableRow: { flexDirection: 'row', padding: 10, borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.04)' },
  td: { flex: 1, fontSize: FONT.sm, color: '#cfd6e4' },
});
