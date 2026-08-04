import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, Alert, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Ionicons } from '@expo/vector-icons';
import api, { BACKEND } from '../../src/api/client';
import { useAuth } from '../../src/contexts/AuthContext';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const STATUS_COLORS: Record<string, string> = {
  draft: '#888892', pending_review: COLORS.orange,
  active: COLORS.green, paused: '#facc15',
  rejected: COLORS.red, blocked: COLORS.red,
};

export default function AdvertiserHome() {
  const router = useRouter();
  const { user } = useAuth();
  const [adv, setAdv] = useState<any>(null);
  const [campaigns, setCampaigns] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [topupAmount, setTopupAmount] = useState('100');
  const [topupBusy, setTopupBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const r = await api.get('/advertiser/me');
      const items = r.data.items || [];
      if (items.length === 0) {
        router.replace('/advertiser/onboard');
        return;
      }
      const a = items[0];
      setAdv(a);
      const r2 = await api.get(`/advertiser/${a.advertiser_id}/campaigns`);
      setCampaigns(r2.data.items || []);
    } catch {
      Alert.alert('Error', 'Could not load advertiser data');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [router]);

  useEffect(() => { load(); }, [load]);

  const onRefresh = () => { setRefreshing(true); load(); };

  const topup = async () => {
    if (!adv) return;
    setTopupBusy(true);
    try {
      const r = await api.post(`/advertiser/${adv.advertiser_id}/topup`, {
        amount_usd: parseFloat(topupAmount) || 100,
      });
      if (r.data.mocked) {
        Alert.alert('Top-up', `Mocked top-up: $${topupAmount} credited (no Stripe key)`);
        setTimeout(load, 800);
      } else if (r.data.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        setTimeout(load, 2000);
      }
    } catch {
      Alert.alert('Error', 'Top-up failed');
    } finally {
      setTopupBusy(false);
    }
  };

  if (loading) {
    return (
      <View style={common.center}><ActivityIndicator size="large" color={COLORS.secondary} /></View>
    );
  }

  if (!adv) return null;
  const activeCampaigns = campaigns.filter((c) => c.status === 'active');

  return (
    <SafeAreaView style={common.screen} testID="advertiser-home">
      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={COLORS.secondary} />}
      >
        {/* Header */}
        <View style={s.headerRow}>
          <TouchableOpacity onPress={() => router.back()} testID="advertiser-home-back">
            <Ionicons name="arrow-back" size={20} color={COLORS.textDim} />
          </TouchableOpacity>
          <View style={{ flex: 1, marginLeft: SPACING.md }}>
            <Text style={s.headerLabel}>ADVERTISER</Text>
            <Text style={s.headerTitle}>{adv.name}</Text>
          </View>
        </View>

        {/* Stats Row */}
        <View style={s.statsRow} testID="advertiser-stats">
          <StatCard icon="wallet-outline" label="Balance" value={`$${(adv.account_balance_usd || 0).toFixed(2)}`} color={COLORS.secondary} />
          <StatCard icon="sparkles" label="Active" value={`${activeCampaigns.length}`} color={COLORS.primary} />
        </View>

        {/* Top-up Card */}
        <View style={[common.card, { marginTop: SPACING.md }]} testID="advertiser-topup-card">
          <Text style={s.cardTitle}>Top up ad wallet</Text>
          <View style={s.presetRow}>
            {[50, 100, 250, 500].map((v) => (
              <TouchableOpacity
                key={v}
                style={[s.presetChip, topupAmount === String(v) && s.presetChipActive]}
                onPress={() => setTopupAmount(String(v))}
                testID={`topup-preset-${v}`}
              >
                <Text style={[s.presetText, topupAmount === String(v) && s.presetTextActive]}>${v}</Text>
              </TouchableOpacity>
            ))}
          </View>
          <View style={s.topupRow}>
            <TextInput
              style={[common.input, { flex: 1 }]}
              keyboardType="numeric"
              value={topupAmount}
              onChangeText={setTopupAmount}
              placeholderTextColor={COLORS.textMuted}
              testID="topup-amount-input"
            />
            <TouchableOpacity
              style={[common.btnPrimary, { paddingHorizontal: SPACING.lg }, topupBusy && { opacity: 0.5 }]}
              onPress={topup}
              disabled={topupBusy}
              testID="mobile-advertiser-topup-btn"
            >
              {topupBusy ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={common.btnPrimaryText}>Top up</Text>
              )}
            </TouchableOpacity>
          </View>
        </View>

        {/* Campaigns list */}
        <View style={s.sectionHeader}>
          <Text style={s.sectionTitle}>Campaigns</Text>
          <TouchableOpacity
            style={common.btnPrimary}
            onPress={() => router.push('/advertiser/campaign/new')}
            testID="mobile-advertiser-new-campaign"
          >
            <Ionicons name="add" size={16} color="#fff" />
            <Text style={common.btnPrimaryText}>New campaign</Text>
          </TouchableOpacity>
        </View>

        {campaigns.length === 0 ? (
          <View style={common.card} testID="campaigns-empty">
            <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }}>
              No campaigns yet — create your first one.
            </Text>
          </View>
        ) : (
          campaigns.map((c) => (
            <TouchableOpacity
              key={c.id}
              style={[common.card, { marginTop: SPACING.sm }]}
              onPress={() => router.push(`/advertiser/campaign/${c.id}`)}
              testID={`campaign-row-${c.id}`}
            >
              <View style={s.campaignRow}>
                <View style={{ flex: 1 }}>
                  <Text style={s.campaignName} numberOfLines={1}>{c.name}</Text>
                  <Text style={s.campaignMeta} numberOfLines={1}>
                    {c.objective} · Budget ${c.budget_total_usd} · Spend ${(c.spend_usd || 0).toFixed(2)}
                  </Text>
                </View>
                <Text style={[s.statusPill, { color: STATUS_COLORS[c.status] || '#888' }]} testID={`campaign-status-${c.status}`}>
                  {c.status?.toUpperCase()}
                </Text>
              </View>
              {/* Spend bar */}
              <View style={s.barBg}>
                <View style={[s.barFill, {
                  width: `${Math.min(100, ((c.spend_usd || 0) / (c.budget_total_usd || 1)) * 100)}%`,
                }]} />
              </View>
            </TouchableOpacity>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function StatCard({ icon, label, value, color }: { icon: string; label: string; value: string; color: string }) {
  return (
    <View style={[common.card, { flex: 1 }]}>
      <View style={common.row}>
        <Ionicons name={icon as any} size={12} color={COLORS.textDim} />
        <Text style={[common.label, { marginBottom: 0, marginLeft: 4 }]}>{label}</Text>
      </View>
      <Text style={[s.statValue, { color }]}>{value}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 80 },
  headerRow: { flexDirection: 'row', alignItems: 'center', marginBottom: SPACING.lg },
  headerLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5, textTransform: 'uppercase' },
  headerTitle: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '800' },
  statsRow: { flexDirection: 'row', gap: SPACING.sm },
  statValue: { fontSize: FONT.xxl, fontWeight: '800', marginTop: SPACING.xs },
  cardTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '700', marginBottom: SPACING.sm },
  presetRow: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.sm },
  presetChip: {
    paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.surfaceBorder,
  },
  presetChipActive: { borderColor: COLORS.secondary, backgroundColor: 'rgba(0,217,255,0.08)' },
  presetText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  presetTextActive: { color: COLORS.secondary },
  topupRow: { flexDirection: 'row', gap: SPACING.sm, alignItems: 'center' },
  sectionHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: SPACING.xl, marginBottom: SPACING.md },
  sectionTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '800' },
  campaignRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm },
  campaignName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  campaignMeta: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  statusPill: { fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1 },
  barBg: { height: 4, backgroundColor: COLORS.surfaceBorder, borderRadius: 2, marginTop: SPACING.sm },
  barFill: { height: 4, backgroundColor: COLORS.secondary, borderRadius: 2 },
});
