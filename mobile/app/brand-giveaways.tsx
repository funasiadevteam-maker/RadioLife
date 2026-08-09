// Phase MKT.2 — Consumer Prize Giveaways — mobile.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

interface Giveaway {
  campaign_id: string; sponsor_name?: string; title: string; prize_desc?: string;
  num_winners: number; entries_count: number; entered: boolean;
}

export default function BrandGiveaways() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [items, setItems] = useState<Giveaway[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const r = await api.get('/brand-giveaways/active'); setItems(r.data.items || []); }
    catch { /* unauth */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const enter = async (g: Giveaway) => {
    if (busy || g.entered) return;
    setBusy(g.campaign_id);
    try {
      const r = await api.post(`/brand-giveaways/${g.campaign_id}/enter`);
      if (r.data.awarded > 0) celebrate({ points: r.data.awarded, title: "You're entered!" });
      await load();
    } catch { await load(); }
    finally { setBusy(null); }
  };

  if (loading) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="gv-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Giveaways</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}
        testID="brand-giveaways-root">
        <Text style={s.intro}>Enter to win prizes from local brands.</Text>

        {items.length === 0 && (
          <View style={s.card}>
            <Ionicons name="gift-outline" size={28} color={COLORS.textMuted} />
            <Text style={s.empty}>No giveaways live right now.</Text>
            <Text style={s.dim}>New prizes drop regularly — check back soon.</Text>
          </View>
        )}

        {items.map((g) => (
          <View key={g.campaign_id} style={s.card} testID={`gv-campaign-${g.campaign_id}`}>
            <View style={s.head}>
              <View style={s.gIcon}><Ionicons name="gift" size={22} color={COLORS.primary} /></View>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.title} numberOfLines={1}>{g.title}</Text>
                {!!g.sponsor_name && <Text style={s.sponsor}>by {g.sponsor_name}</Text>}
              </View>
            </View>
            {!!g.prize_desc && <Text style={s.prize}>🏆 {g.prize_desc}</Text>}
            <Text style={s.meta}>{g.entries_count} entered · {g.num_winners} winner{g.num_winners > 1 ? 's' : ''}</Text>

            {g.entered ? (
              <View style={s.entered} testID={`gv-entered-${g.campaign_id}`}>
                <Ionicons name="checkmark-circle" size={18} color={COLORS.green} />
                <Text style={s.enteredText}>You&apos;re entered — good luck!</Text>
              </View>
            ) : (
              <TouchableOpacity style={s.enterBtn} onPress={() => enter(g)}
                disabled={busy === g.campaign_id} testID={`gv-enter-${g.campaign_id}`} activeOpacity={0.85}>
                {busy === g.campaign_id ? <ActivityIndicator color="#fff" />
                  : <><Ionicons name="ticket" size={16} color="#fff" /><Text style={s.enterText}>Enter giveaway</Text></>}
              </TouchableOpacity>
            )}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg,
  },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md, alignItems: 'stretch' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: SPACING.sm },
  gIcon: { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.primary + '18', alignItems: 'center', justifyContent: 'center' },
  title: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  sponsor: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  prize: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', marginBottom: 4 },
  meta: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginBottom: SPACING.sm },
  enterBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: COLORS.primary, paddingVertical: 13, borderRadius: RADIUS.md },
  enterText: { color: '#fff', fontSize: FONT.sm, fontWeight: '800' },
  entered: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.green + '14', borderWidth: 1, borderColor: COLORS.green + '55' },
  enteredText: { color: COLORS.green, fontSize: FONT.sm, fontWeight: '800' },
  empty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 8 },
  dim: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 4 },
});
