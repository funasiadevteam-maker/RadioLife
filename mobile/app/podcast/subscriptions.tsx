import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity,
  ActivityIndicator, RefreshControl, StyleSheet, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../src/constants/theme';
import {
  getListenerSubscriptions, cancelSubscription, resumeSubscription,
} from '../../src/api/podcastApi';

const statusColor: Record<string, string> = {
  trialing: COLORS.orange,
  active: COLORS.green,
  past_due: COLORS.red,
  canceled: COLORS.textDim,
};

export default function ListenerSubscriptionsScreen() {
  const router = useRouter();
  const [subs, setSubs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await getListenerSubscriptions();
      setSubs(data);
    } catch (e: any) {
      Alert.alert('Error', e?.message || 'Could not load subscriptions');
    } finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const onCancel = async (id: string) => {
    setBusyId(id);
    try {
      await cancelSubscription(id);
      await load();
    } catch (e: any) {
      Alert.alert('Cancel', e?.response?.data?.detail || 'Failed');
    } finally { setBusyId(null); }
  };

  const onResume = async (id: string) => {
    setBusyId(id);
    try {
      await resumeSubscription(id);
      await load();
    } catch (e: any) {
      Alert.alert('Resume', e?.response?.data?.detail || 'Failed');
    } finally { setBusyId(null); }
  };

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity testID="mobile-subs-back" onPress={() => router.back()} style={s.backBtn}>
          <Ionicons name="arrow-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.title}>Your Subscriptions</Text>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color={COLORS.primary} style={{ marginTop: 60 }} />
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: SPACING.lg }}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
        >
          {subs.length === 0 ? (
            <View testID="mobile-subs-empty" style={s.empty}>
              <Ionicons name="heart-dislike-outline" size={40} color={COLORS.textDim} />
              <Text style={s.emptyText}>No active subscriptions yet.</Text>
              <TouchableOpacity
                style={[common.btnGhost, { marginTop: SPACING.md }]}
                onPress={() => router.push('/(tabs)/podcasts')}
              >
                <Text style={common.btnGhostText}>Browse Podcasts</Text>
              </TouchableOpacity>
            </View>
          ) : subs.map(sub => (
            <View key={sub.id} testID={`mobile-listener-sub-row-${sub.id}`} style={s.row}>
              <View style={{ flex: 1 }}>
                <Text style={s.channelName}>Channel {sub.channel_id}</Text>
                <View style={s.statusRow}>
                  <Text style={s.statusLabel}>Status: </Text>
                  <Text testID={`mobile-sub-status-${sub.id}`} style={[s.statusValue, { color: statusColor[sub.status] || COLORS.textDim }]}>
                    {sub.status}
                  </Text>
                  {sub.cancel_at_period_end && (
                    <Text style={s.cancelNote}> · cancels at period end</Text>
                  )}
                </View>
                {sub.trial_end && (
                  <Text style={s.trialEnd}>Trial ends: {new Date(sub.trial_end).toLocaleDateString()}</Text>
                )}
              </View>
              <View>
                {sub.cancel_at_period_end ? (
                  <TouchableOpacity
                    testID={`mobile-listener-sub-resume-${sub.id}`}
                    style={[s.actionBtn, { borderColor: COLORS.green }]}
                    onPress={() => onResume(sub.id)}
                    disabled={busyId === sub.id}
                  >
                    <Text style={[s.actionText, { color: COLORS.green }]}>
                      {busyId === sub.id ? '…' : 'Resume'}
                    </Text>
                  </TouchableOpacity>
                ) : (
                  <TouchableOpacity
                    testID={`mobile-listener-sub-cancel-${sub.id}`}
                    style={[s.actionBtn, { borderColor: COLORS.red }]}
                    onPress={() => onCancel(sub.id)}
                    disabled={busyId === sub.id}
                  >
                    <Text style={[s.actionText, { color: COLORS.red }]}>
                      {busyId === sub.id ? '…' : 'Cancel'}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>
            </View>
          ))}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md },
  backBtn: { padding: 4 },
  title: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  row: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    padding: 14, marginBottom: 10, borderRadius: RADIUS.md,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  channelName: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  statusRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  statusLabel: { fontSize: FONT.sm, color: COLORS.textDim },
  statusValue: { fontSize: FONT.sm, fontWeight: '700' },
  cancelNote: { fontSize: FONT.xs, color: COLORS.textDim },
  trialEnd: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 2 },
  actionBtn: {
    paddingHorizontal: 14, paddingVertical: 6, borderRadius: 6,
    borderWidth: 1, backgroundColor: 'transparent',
  },
  actionText: { fontWeight: '700', fontSize: FONT.sm },
  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.md },
});
