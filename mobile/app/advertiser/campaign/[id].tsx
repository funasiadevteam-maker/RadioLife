import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, ActivityIndicator, Alert, RefreshControl,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';

const STATUS_COLORS: Record<string, string> = {
  draft: '#888892', pending_review: COLORS.orange,
  active: COLORS.green, paused: '#facc15',
  rejected: COLORS.red, blocked: COLORS.red,
};

type Tab = 'overview' | 'conversions' | 'pacing';

export default function CampaignDetail() {
  const router = useRouter();
  const { id: cid } = useLocalSearchParams<{ id: string }>();
  const [advId, setAdvId] = useState('');
  const [data, setData] = useState<any>(null);
  const [perf, setPerf] = useState<any>(null);
  const [attribution, setAttribution] = useState<any>(null);
  const [pacing, setPacing] = useState<any>(null);
  const [tab, setTab] = useState<Tab>('overview');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [editWindow, setEditWindow] = useState('');
  const [editingWindow, setEditingWindow] = useState(false);

  const load = useCallback(async (aid: string) => {
    if (!aid || !cid) return;
    try {
      const [r1, r2] = await Promise.all([
        api.get(`/advertiser/${aid}/campaigns/${cid}`),
        api.get(`/advertiser/${aid}/campaigns/${cid}/performance`).catch(() => null),
      ]);
      setData(r1.data);
      if (r2) setPerf(r2.data);
      setEditWindow(String(r1.data?.campaign?.attribution_window_hours || 24));
      // Load attribution & pacing in background
      api.get(`/advertiser/${aid}/campaigns/${cid}/attribution`).then((r) => setAttribution(r.data)).catch(() => {});
      api.get(`/advertiser/${aid}/campaigns/${cid}/pacing`).then((r) => setPacing(r.data)).catch(() => {});
    } catch {
      Alert.alert('Error', 'Could not load campaign');
    } finally { setLoading(false); setRefreshing(false); }
  }, [cid]);

  useEffect(() => {
    (async () => {
      try {
        const r = await api.get('/advertiser/me');
        const items = r.data.items || [];
        if (items.length) {
          const aid = items[0].advertiser_id;
          setAdvId(aid);
          load(aid);
        }
      } catch {}
    })();
  }, [load]);

  const onRefresh = () => { setRefreshing(true); if (advId) load(advId); };

  const patchWindow = async () => {
    const v = parseInt(editWindow);
    if (!v || v < 1 || v > 720) { Alert.alert('Validation', 'Must be 1–720 hours'); return; }
    try {
      await api.patch(`/advertiser/${advId}/campaigns/${cid}`, { attribution_window_hours: v });
      Alert.alert('Saved', `Attribution window updated to ${v}h`);
      setEditingWindow(false);
      load(advId);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Update failed');
    }
  };

  const act = async (action: string) => {
    try {
      await api.post(`/advertiser/${advId}/campaigns/${cid}/${action}`);
      Alert.alert('Done', action);
      load(advId);
    } catch { Alert.alert('Error', `${action} failed`); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.secondary} /></View>;
  if (!data) return null;

  const c = data.campaign;

  return (
    <SafeAreaView style={common.screen} testID="campaign-detail">
      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.secondary} />}
      >
        {/* Back + Header */}
        <TouchableOpacity onPress={() => router.back()} style={common.row} testID="campaign-detail-back">
          <Ionicons name="arrow-back" size={16} color={COLORS.textDim} />
          <Text style={{ color: COLORS.textDim, fontSize: FONT.sm, marginLeft: 4 }}>Back to campaigns</Text>
        </TouchableOpacity>

        <View style={[s.headerRow, { marginTop: SPACING.md }]}>
          <View style={{ flex: 1 }}>
            <Text style={s.title}>{c.name}</Text>
            <Text style={s.meta}>
              Status <Text style={{ color: STATUS_COLORS[c.status] || '#888', fontWeight: '700' }}>{c.status}</Text>
              {' · '}Objective {c.objective} · Budget ${c.budget_total_usd}
            </Text>
          </View>
          {c.status === 'active' && (
            <TouchableOpacity style={common.btnGhost} onPress={() => act('pause')} testID="campaign-pause">
              <Ionicons name="pause" size={14} color={COLORS.textDim} />
            </TouchableOpacity>
          )}
          {c.status === 'paused' && (
            <TouchableOpacity style={common.btnPrimary} onPress={() => act('resume')} testID="campaign-resume">
              <Ionicons name="play" size={14} color="#fff" />
            </TouchableOpacity>
          )}
        </View>

        {/* Tab Bar */}
        <View style={s.tabBar}>
          {(['overview', 'conversions', 'pacing'] as Tab[]).map((t) => (
            <TouchableOpacity key={t} onPress={() => setTab(t)}
              style={[s.tabItem, tab === t && s.tabItemActive]}
              testID={`mobile-campaign-${t}-tab`}>
              <Text style={[s.tabText, tab === t && s.tabTextActive]}>
                {t.charAt(0).toUpperCase() + t.slice(1)}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Overview Tab */}
        {tab === 'overview' && (
          <View testID="campaign-overview-tab">
            {/* KPI row */}
            <View style={s.kpiRow}>
              <KpiCard label="Impressions" value={perf?.totals?.impressions || 0} />
              <KpiCard label="Completes" value={perf?.totals?.completes || 0} />
              <KpiCard label="Saves" value={perf?.totals?.saves || 0} />
              <KpiCard label="Spend" value={`$${(perf?.totals?.spend_usd || 0).toFixed(2)}`} />
            </View>

            {/* Targeting summary */}
            <View style={[common.card, { marginTop: SPACING.md }]}>
              <Text style={common.label}>TARGETING</Text>
              <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }}>
                Market: {c.targeting?.market || '—'}{'\n'}
                Channels: {(c.targeting?.channel_slugs || []).join(', ') || 'All'}{'\n'}
                Dayparts: {(c.targeting?.time_of_day || []).join(', ') || 'All'}
              </Text>
            </View>

            {/* Creatives */}
            <View style={[common.card, { marginTop: SPACING.md }]} testID="campaign-creatives">
              <Text style={common.label}>CREATIVES</Text>
              {(data.creatives || []).length === 0 ? (
                <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }}>No creatives attached</Text>
              ) : (
                (data.creatives || []).map((cr: any) => (
                  <View key={cr.id} style={s.creativeRow}>
                    <Ionicons name="musical-notes" size={16} color={COLORS.secondary} />
                    <View style={{ flex: 1, marginLeft: 8 }}>
                      <Text style={{ color: '#fff', fontSize: FONT.sm }}>{cr.title}</Text>
                      <Text style={{ color: COLORS.textDim, fontSize: FONT.xs }}>
                        {cr.status} · {cr.duration_sec}s
                      </Text>
                    </View>
                  </View>
                ))
              )}
            </View>

            {/* Edit attribution window */}
            <View style={[common.card, { marginTop: SPACING.md }]}>
              <View style={[common.row, { justifyContent: 'space-between' }]}>
                <Text style={common.label}>ATTRIBUTION WINDOW</Text>
                <TouchableOpacity onPress={() => setEditingWindow(!editingWindow)} testID="campaign-edit-window">
                  <Text style={{ color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '700' }}>
                    {editingWindow ? 'Cancel' : 'Edit'}
                  </Text>
                </TouchableOpacity>
              </View>
              {editingWindow ? (
                <View style={[common.row, { gap: SPACING.sm, marginTop: SPACING.sm }]}>
                  <TextInput style={[common.input, { flex: 1 }]} keyboardType="numeric"
                    value={editWindow} onChangeText={setEditWindow}
                    testID="campaign-edit-window-input" />
                  <TouchableOpacity style={common.btnPrimary} onPress={patchWindow} testID="campaign-save-window">
                    <Text style={common.btnPrimaryText}>Save</Text>
                  </TouchableOpacity>
                </View>
              ) : (
                <Text style={{ color: '#fff', fontSize: FONT.lg, fontWeight: '700' }}>
                  {c.attribution_window_hours || 24}h
                </Text>
              )}
            </View>
          </View>
        )}

        {/* Conversions Tab */}
        {tab === 'conversions' && (
          <View testID="mobile-campaign-conversions-tab">
            {!attribution ? (
              <ActivityIndicator size="large" color={COLORS.secondary} style={{ marginTop: SPACING.xl }} />
            ) : (
              <>
                <View style={s.kpiRow}>
                  <KpiCard label="Impressions" value={attribution.impressions} testID="conv-impressions" />
                  <KpiCard label="Coupon saves" value={attribution.coupon_saves} testID="conv-saves" />
                </View>
                <View style={[s.kpiRow, { marginTop: SPACING.sm }]}>
                  <KpiCard label="Redemptions" value={attribution.redemptions} testID="conv-redemptions" />
                  <KpiCard label="Check-ins" value={attribution.checkins} testID="conv-checkins" />
                </View>
                <View style={[s.kpiRow, { marginTop: SPACING.sm }]}>
                  <KpiCard label="Save rate" value={`${((attribution.save_rate || 0) * 100).toFixed(1)}%`} testID="conv-save-rate" />
                  <KpiCard label="Cost / save" value={`$${(attribution.cost_per_save || 0).toFixed(2)}`} testID="conv-cps" />
                </View>
              </>
            )}
          </View>
        )}

        {/* Pacing Tab */}
        {tab === 'pacing' && (
          <View testID="campaign-pacing-tab">
            {!pacing ? (
              <ActivityIndicator size="large" color={COLORS.secondary} style={{ marginTop: SPACING.xl }} />
            ) : (
              <>
                <View style={[common.card, { marginTop: SPACING.md }]}>
                  <Text style={common.label}>PACING STATUS</Text>
                  <Text style={[s.pacingStatus, {
                    color: pacing.status === 'ahead' ? COLORS.orange
                      : pacing.status === 'behind' ? COLORS.red : COLORS.green,
                  }]} testID="pacing-status-pill">
                    {(pacing.status || 'unknown').toUpperCase()}
                  </Text>
                </View>

                <View style={[common.card, { marginTop: SPACING.sm }]}>
                  <Text style={common.label}>SPEND PROGRESS</Text>
                  <View style={s.progressBarBg}>
                    <View style={[s.progressBarFill, { width: `${Math.min(100, (pacing.spend_progress || 0) * 100)}%` }]} />
                  </View>
                  <Text style={s.progressText}>{((pacing.spend_progress || 0) * 100).toFixed(1)}%</Text>
                </View>

                <View style={[common.card, { marginTop: SPACING.sm }]}>
                  <Text style={common.label}>TIME PROGRESS</Text>
                  <View style={s.progressBarBg}>
                    <View style={[s.progressBarFill, { width: `${Math.min(100, (pacing.time_progress || 0) * 100)}%`, backgroundColor: COLORS.orange }]} />
                  </View>
                  <Text style={s.progressText}>{((pacing.time_progress || 0) * 100).toFixed(1)}%</Text>
                </View>

                {pacing.projected_end_date && (
                  <View style={[common.card, { marginTop: SPACING.sm }]}>
                    <Text style={common.label}>PROJECTED END-OF-BUDGET</Text>
                    <Text style={{ color: '#fff', fontSize: FONT.md, fontWeight: '700' }}>
                      {new Date(pacing.projected_end_date).toLocaleDateString()}
                    </Text>
                  </View>
                )}
              </>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function KpiCard({ label, value, testID }: { label: string; value: any; testID?: string }) {
  return (
    <View style={[common.card, { flex: 1 }]} testID={testID}>
      <Text style={common.label}>{label}</Text>
      <Text style={s.kpiValue}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 80 },
  headerRow: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between' },
  title: { color: '#fff', fontSize: FONT.xxl, fontWeight: '800' },
  meta: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 4 },
  tabBar: {
    flexDirection: 'row', marginTop: SPACING.lg, borderBottomWidth: 1,
    borderBottomColor: COLORS.surfaceBorder,
  },
  tabItem: { paddingVertical: SPACING.sm, paddingHorizontal: SPACING.md, marginRight: 4 },
  tabItemActive: { borderBottomWidth: 2, borderBottomColor: COLORS.secondary },
  tabText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  tabTextActive: { color: COLORS.secondary },
  kpiRow: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.md },
  kpiValue: { color: '#fff', fontSize: FONT.xl, fontWeight: '800', marginTop: 4 },
  creativeRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: SPACING.sm, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  pacingStatus: { fontSize: FONT.xxl, fontWeight: '800', marginTop: 4, letterSpacing: 1 },
  progressBarBg: { height: 8, backgroundColor: COLORS.surfaceBorder, borderRadius: 4, marginTop: SPACING.sm },
  progressBarFill: { height: 8, backgroundColor: COLORS.secondary, borderRadius: 4 },
  progressText: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 4 },
});
