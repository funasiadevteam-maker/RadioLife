import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import * as WebBrowser from 'expo-web-browser';
import { Ionicons } from '@expo/vector-icons';
import api, { BACKEND } from '../../src/api/client';
import SafeImage from '../../src/components/SafeImage';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';

const PACKAGES = [
  { id: 'topup_10', label: '$10' },
  { id: 'topup_25', label: '$25' },
  { id: 'topup_50', label: '$50' },
  { id: 'topup_100', label: '$100' },
];

const usd = (cents: number) => `$${((cents || 0) / 100).toFixed(2)}`;

export default function PromoteStation() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [balance, setBalance] = useState(0);
  const [mine, setMine] = useState<any[]>([]);
  const [totals, setTotals] = useState<any>({ impressions: 0, clicks: 0, ctr: 0, spend_cents: 0 });
  const [candidates, setCandidates] = useState<any[]>([]);
  const [selected, setSelected] = useState<any>(null);
  const [model, setModel] = useState<'cpm' | 'cpc'>('cpm');
  const [daily, setDaily] = useState(0);
  const [leaders, setLeaders] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [topupBusy, setTopupBusy] = useState('');

  const load = useCallback(async () => {
    try {
      const [wRes, mRes, dRes, lRes] = await Promise.allSettled([
        api.get('/promoted/wallet'),
        api.get('/promoted/mine'),
        api.get('/radio/discover'),
        api.get('/promoted/leaderboard?days=7'),
      ]);
      if (wRes.status === 'fulfilled') setBalance((wRes.value as any).data?.balance_cents || 0);
      if (mRes.status === 'fulfilled') {
        setMine((mRes.value as any).data?.items || []);
        setTotals((mRes.value as any).data?.totals || {});
      }
      if (lRes.status === 'fulfilled') setLeaders((lRes.value as any).data?.items || []);
      if (dRes.status === 'fulfilled') {
        const rails = (dRes.value as any).data?.rails || [];
        const flat: any[] = [];
        const seen = new Set<string>();
        rails.forEach((r: any) => (r.stations || []).forEach((st: any) => {
          if (st?.id && !seen.has(st.id)) { seen.add(st.id); flat.push(st); }
        }));
        setCandidates(flat.slice(0, 12));
      }
    } finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const topup = async (pkg: string) => {
    setTopupBusy(pkg);
    try {
      const r = await api.post('/promoted/wallet/topup', { package_id: pkg, origin_url: BACKEND });
      if (r.data?.checkout_url) {
        await WebBrowser.openBrowserAsync(r.data.checkout_url);
        // Poll for credit after returning from checkout.
        const sid = r.data.session_id;
        for (let i = 0; i < 5; i++) {
          await new Promise((res) => setTimeout(res, 2000));
          const st = await api.get(`/promoted/wallet/topup/status/${sid}`).catch(() => null);
          if (st?.data?.payment_status === 'paid') { setBalance(st.data.balance_cents || 0); break; }
        }
        load();
      }
    } catch { Alert.alert('Top-up', 'Could not start checkout.'); }
    finally { setTopupBusy(''); }
  };

  const promote = async () => {
    if (!selected) { Alert.alert('Pick a station', 'Select a station to promote first.'); return; }
    setBusy(true);
    try {
      await api.post('/promoted/self-serve', {
        station_id: selected.id,
        sponsor_name: selected.name,
        pricing_model: model,
        cpm_bid_cents: 500,
        cpc_bid_cents: 25,
        daily_budget_cents: daily,
      });
      setSelected(null);
      Alert.alert('Promoted', balance > 0
        ? 'Your station is now promoted and live.'
        : 'Created — top up your wallet to make it live.');
      load();
    } catch { Alert.alert('Error', 'Could not create promotion.'); }
    finally { setBusy(false); }
  };

  const toggle = async (promoId: string) => {
    try { await api.post(`/promoted/${promoId}/toggle`); load(); }
    catch (e: any) { Alert.alert('Cannot activate', e?.response?.data?.detail || 'Top up your wallet first.'); }
  };

  if (loading) return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

  return (
    <SafeAreaView style={common.screen} testID="promote-station-screen">
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}>
        <View style={s.headerRow}>
          <TouchableOpacity onPress={() => router.back()} testID="promote-back"><Ionicons name="arrow-back" size={20} color={COLORS.textDim} /></TouchableOpacity>
          <View style={{ flex: 1, marginLeft: SPACING.md }}>
            <Text style={s.headerLabel}>SPONSORED STATIONS</Text>
            <Text style={s.headerTitle}>Promote a station</Text>
          </View>
        </View>

        {/* Wallet + top-up */}
        <View style={s.walletCard} testID="promo-wallet-card">
          <Text style={s.walletLabel}>AD WALLET BALANCE</Text>
          <Text style={s.walletValue} testID="promo-wallet-balance">{usd(balance)}</Text>
          <View style={s.presetRow}>
            {PACKAGES.map((p) => (
              <TouchableOpacity key={p.id} style={s.presetChip} onPress={() => topup(p.id)}
                disabled={!!topupBusy} testID={`promo-topup-${p.id}`}>
                {topupBusy === p.id ? <ActivityIndicator size="small" color={COLORS.primary} />
                  : <Text style={s.presetText}>{p.label}</Text>}
              </TouchableOpacity>
            ))}
          </View>
        </View>

        {/* Analytics totals */}
        <View style={s.statsRow} testID="promo-analytics-totals">
          <Stat label="Impressions" value={`${totals.impressions || 0}`} icon="eye-outline" />
          <Stat label="Clicks" value={`${totals.clicks || 0}`} icon="finger-print-outline" />
          <Stat label="CTR" value={`${totals.ctr || 0}%`} icon="trending-up-outline" />
          <Stat label="Spend" value={usd(totals.spend_cents)} icon="cash-outline" />
        </View>

        {/* Create promo */}
        <Text style={s.sectionTitle}>Pick a station</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: SPACING.sm, paddingBottom: 4 }}>
          {candidates.map((st) => {
            const sel = selected?.id === st.id;
            return (
              <TouchableOpacity key={st.id} style={[s.candTile, sel && s.candTileSel]} onPress={() => setSelected(st)} testID={`promo-cand-${st.id}`}>
                <SafeImage uri={st.favicon || st.logo_url || st.cover_image_url} fallbackText={st.name} size={68} borderRadius={12} />
                <Text style={s.candName} numberOfLines={1}>{st.name}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>

        <View style={s.modelRow}>
          {(['cpm', 'cpc'] as const).map((m) => (
            <TouchableOpacity key={m} style={[s.modelTab, model === m && s.modelTabActive]} onPress={() => setModel(m)} testID={`promo-model-${m}`}>
              <Text style={[s.modelText, model === m && s.modelTextActive]}>
                {m === 'cpm' ? 'CPM · $5 / 1k views' : 'CPC · $0.25 / click'}
              </Text>
            </TouchableOpacity>
          ))}
        </View>

        <Text style={s.sectionTitle}>Daily budget cap</Text>
        <View style={s.modelRow}>
          {[{ v: 0, l: 'No cap' }, { v: 500, l: '$5/day' }, { v: 1000, l: '$10/day' }, { v: 2500, l: '$25/day' }].map((d) => (
            <TouchableOpacity key={d.v} style={[s.modelTab, daily === d.v && s.modelTabActive]} onPress={() => setDaily(d.v)} testID={`promo-daily-${d.v}`}>
              <Text style={[s.modelText, daily === d.v && s.modelTextActive]}>{d.l}</Text>
            </TouchableOpacity>
          ))}
        </View>

        <TouchableOpacity style={[common.btnPrimary, { marginTop: SPACING.md }, busy && { opacity: 0.5 }]} onPress={promote} disabled={busy} testID="promo-create-btn">
          {busy ? <ActivityIndicator size="small" color="#fff" /> : <Text style={common.btnPrimaryText}>Promote station</Text>}
        </TouchableOpacity>

        {/* This week's leaderboard */}
        {leaders.length > 0 && (
          <>
            <Text style={[s.sectionTitle, { marginTop: SPACING.xl }]}>This week&apos;s top promoted</Text>
            {leaders.map((l, i) => (
              <View key={l.promo_id} style={[common.card, { marginTop: SPACING.sm }]} testID={`promo-leader-${l.promo_id}`}>
                <View style={s.mineRow}>
                  <Text style={s.rank}>{i + 1}</Text>
                  <SafeImage uri={l.logo_url} fallbackText={l.station_name} size={36} borderRadius={9} />
                  <View style={{ flex: 1 }}>
                    <Text style={s.mineName} numberOfLines={1}>{l.station_name}</Text>
                    <Text style={s.mineMeta}>{l.listens} listens · {l.impressions} views</Text>
                  </View>
                  <Ionicons name="trophy" size={18} color={i === 0 ? COLORS.orange : COLORS.textMuted} />
                </View>
              </View>
            ))}
          </>
        )}

        {/* My promotions */}
        <Text style={[s.sectionTitle, { marginTop: SPACING.xl }]}>My promotions</Text>
        {mine.length === 0 ? (
          <View style={common.card}><Text style={{ color: COLORS.textDim, fontSize: FONT.sm }}>No promoted stations yet.</Text></View>
        ) : mine.map((p) => (
          <View key={p.promo_id} style={[common.card, { marginTop: SPACING.sm }]} testID={`promo-mine-${p.promo_id}`}>
            <View style={s.mineRow}>
              <SafeImage uri={p.logo_url} fallbackText={p.station_name} size={40} borderRadius={10} />
              <View style={{ flex: 1 }}>
                <Text style={s.mineName} numberOfLines={1}>{p.station_name}</Text>
                <Text style={s.mineMeta}>{(p.pricing_model || 'cpm').toUpperCase()} · {p.status}</Text>
              </View>
              <TouchableOpacity onPress={() => toggle(p.promo_id)} testID={`promo-toggle-${p.promo_id}`}>
                <Ionicons name={p.active ? 'pause-circle' : 'play-circle'} size={30} color={p.active ? COLORS.orange : COLORS.green} />
              </TouchableOpacity>
            </View>
            <View style={s.mineStats}>
              <Text style={s.mineStat}>{p.impressions} views</Text>
              <Text style={s.mineStat}>{p.clicks} clicks</Text>
              <Text style={s.mineStat}>{p.ctr}% CTR</Text>
              <Text style={s.mineStat}>{usd(p.spend_cents)} spent</Text>
            </View>
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

function Stat({ label, value, icon }: { label: string; value: string; icon: any }) {
  return (
    <View style={s.statCard}>
      <Ionicons name={icon} size={14} color={COLORS.textDim} />
      <Text style={s.statValue}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 90 },
  headerRow: { flexDirection: 'row', alignItems: 'center', marginBottom: SPACING.lg },
  headerLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5 },
  headerTitle: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '800' },
  walletCard: { backgroundColor: COLORS.primary, borderRadius: RADIUS.xl, padding: SPACING.lg },
  walletLabel: { color: 'rgba(255,255,255,0.8)', fontSize: FONT.xs, fontWeight: '800', letterSpacing: 1.5 },
  walletValue: { color: '#fff', fontSize: 34, fontWeight: '900', marginTop: 4 },
  presetRow: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.md },
  presetChip: { flex: 1, alignItems: 'center', paddingVertical: 10, borderRadius: RADIUS.full, backgroundColor: 'rgba(255,255,255,0.9)' },
  presetText: { color: COLORS.primary, fontSize: FONT.sm, fontWeight: '800' },
  statsRow: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.md },
  statCard: { flex: 1, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.lg, padding: SPACING.sm, alignItems: 'center' },
  statValue: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', marginTop: 4 },
  statLabel: { color: COLORS.textMuted, fontSize: 9, fontWeight: '700', marginTop: 2 },
  sectionTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800', marginTop: SPACING.lg, marginBottom: SPACING.sm },
  candTile: { width: 76, alignItems: 'center', padding: 4, borderRadius: 14, borderWidth: 2, borderColor: 'transparent' },
  candTileSel: { borderColor: COLORS.primary, backgroundColor: '#fff7ed' },
  candName: { color: COLORS.text, fontSize: 10, fontWeight: '700', marginTop: 4, textAlign: 'center' },
  modelRow: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.md },
  modelTab: { flex: 1, alignItems: 'center', paddingVertical: 12, borderRadius: RADIUS.lg, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.border },
  modelTabActive: { backgroundColor: '#fff7ed', borderColor: COLORS.primary },
  modelText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '800' },
  modelTextActive: { color: COLORS.primary },
  mineRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm },
  mineName: { color: COLORS.text, fontSize: FONT.md, fontWeight: '700' },
  mineMeta: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  mineStats: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.md, marginTop: SPACING.sm },
  mineStat: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  rank: { color: COLORS.textMuted, fontSize: FONT.md, fontWeight: '900', width: 18, textAlign: 'center' },
});
