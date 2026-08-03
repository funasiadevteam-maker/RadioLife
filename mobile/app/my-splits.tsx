import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView,
  SafeAreaView, ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { useAuth } from '../src/contexts/AuthContext';
import SafeImage from '../src/components/SafeImage';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';

const STATUS_COLORS: Record<string, string> = {
  pending: COLORS.orange,
  paid: COLORS.green,
  expired: COLORS.red,
  cancelled: COLORS.textMuted,
};
const STATUS_LABELS: Record<string, string> = {
  pending: 'Pending',
  paid: 'Paid',
  partially_paid: 'Partial',
  expired: 'Expired',
  cancelled: 'Cancelled',
};
const FILTERS = ['all', 'pending', 'paid', 'expired'];

export default function MySplitsScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [splits, setSplits] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState('all');

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const load = useCallback(async () => {
    try {
      const q = filter === 'all' ? '' : `?status=${filter}`;
      const r = await api.get(`/scan-to-pay/splits/mine${q}`);
      setSplits(r.data.items || r.data.splits || []);
    } catch {}
    finally { setLoading(false); setRefreshing(false); }
  }, [filter]);

  useEffect(() => { if (!authLoading && user) load(); }, [authLoading, user, load]);

  if (authLoading || loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView
        contentContainerStyle={s.scroll}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
      >
        <View style={s.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={s.title} testID="my-splits-title">My Splits</Text>
        </View>

        {/* Filter chips */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: SPACING.md }}>
          {FILTERS.map(f => (
            <TouchableOpacity key={f} style={[common.pill, filter === f && common.pillActive, { marginRight: 8 }]}
              onPress={() => { setFilter(f); setLoading(true); }} testID={`splits-filter-${f}`}>
              <Text style={[common.pillText, filter === f && common.pillTextActive]}>
                {f === 'all' ? 'All' : STATUS_LABELS[f] || f}
              </Text>
            </TouchableOpacity>
          ))}
        </ScrollView>

        {/* Empty */}
        {splits.length === 0 && (
          <View style={s.emptyWrap} testID="splits-empty">
            <Ionicons name="people-outline" size={40} color={COLORS.textMuted} />
            <Text style={s.emptyTitle}>No splits yet</Text>
            <Text style={s.emptyText}>Start one from a scan-to-pay confirmation.</Text>
          </View>
        )}

        {/* List */}
        {splits.map((sp, i) => {
          const statusColor = STATUS_COLORS[sp.status] || COLORS.textMuted;
          const paidShares = (sp.shares || []).filter((sh: any) => sh.status === 'paid').length;
          const totalShares = (sp.shares || []).length;
          return (
            <TouchableOpacity key={sp.split_id || i} style={s.splitCard}
              testID={`split-card-${sp.split_id || i}`}
              onPress={() => { /* expand inline or navigate */ }}>
              <View style={s.splitTop}>
                <SafeImage uri={sp.merchant?.logo_url} fallbackText={sp.merchant_name || 'M'} size={40} borderRadius={10} />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={s.splitMerchant}>{sp.merchant_name || 'Merchant'}</Text>
                  <Text style={s.splitAmount}>AED {((sp.total_cents || 0) / 100).toFixed(2)}</Text>
                </View>
                <View style={[s.statusPill, { borderColor: statusColor + '40', backgroundColor: statusColor + '10' }]}>
                  <View style={[s.statusDot, { backgroundColor: statusColor }]} />
                  <Text style={[s.statusText, { color: statusColor }]}>{STATUS_LABELS[sp.status] || sp.status}</Text>
                </View>
              </View>
              {/* Shares */}
              {totalShares > 0 && (
                <View style={s.sharesRow}>
                  <Text style={s.sharesLabel}>{paidShares}/{totalShares} paid</Text>
                  <View style={s.sharesBar}>
                    <View style={[s.sharesFill, { width: `${(paidShares / totalShares) * 100}%` }]} />
                  </View>
                </View>
              )}
              {/* Participant list */}
              {(sp.shares || []).map((sh: any, j: number) => (
                <View key={j} style={s.shareRow}>
                  <Ionicons name={sh.status === 'paid' ? 'checkmark-circle' : 'ellipse-outline'}
                    size={14} color={sh.status === 'paid' ? COLORS.green : COLORS.textMuted} />
                  <Text style={s.shareName}>{sh.label || sh.user_name || `Payer ${j+1}`}</Text>
                  <Text style={s.shareAmt}>AED {((sh.amount_cents || 0) / 100).toFixed(2)}</Text>
                </View>
              ))}
              <Text style={s.splitDate}>
                {sp.created_at ? new Date(sp.created_at).toLocaleDateString() : ''}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 60 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: SPACING.lg },
  title: { fontSize: FONT.xxl, fontWeight: '900', color: COLORS.text },
  emptyWrap: { alignItems: 'center', paddingVertical: 60, gap: 8 },
  emptyTitle: { fontSize: FONT.lg, fontWeight: '700', color: COLORS.text },
  emptyText: { fontSize: FONT.md, color: COLORS.textDim },
  splitCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md,
    borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: 10,
    shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.04, shadowRadius: 3, elevation: 1,
  },
  splitTop: { flexDirection: 'row', alignItems: 'center' },
  splitMerchant: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  splitAmount: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 1 },
  statusPill: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full, borderWidth: 1 },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  statusText: { fontSize: 10, fontWeight: '700', textTransform: 'uppercase' },
  sharesRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12, gap: 8 },
  sharesLabel: { fontSize: FONT.xs, color: COLORS.textMuted, width: 60 },
  sharesBar: { flex: 1, height: 4, borderRadius: 2, backgroundColor: COLORS.inputBg },
  sharesFill: { height: 4, borderRadius: 2, backgroundColor: COLORS.green },
  shareRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4, marginTop: 4 },
  shareName: { flex: 1, fontSize: FONT.sm, color: COLORS.text },
  shareAmt: { fontSize: FONT.sm, color: COLORS.textDim, fontWeight: '600' },
  splitDate: { fontSize: FONT.xs, color: COLORS.textMuted, marginTop: 8 },
});
