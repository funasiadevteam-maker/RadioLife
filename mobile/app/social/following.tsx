// FUUSIC Social V2 — Mobile Following management.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';
import api from '../../src/api/client';
import { AvatarM } from '../(tabs)/social';
import WhoToFollowM from '../../src/social/WhoToFollowM';
import DailyReadingsCardM from '../../src/social/DailyReadingsCardM';

const FILTERS = [
  { key: 'all', label: 'All' }, { key: 'people', label: 'People' },
  { key: 'creators', label: 'Creators' }, { key: 'advisors', label: 'Advisors' },
  { key: 'businesses', label: 'Businesses' }, { key: 'stations', label: 'Stations' },
  { key: 'clubs', label: 'Clubs' },
];

const fireEvent = (event: string, extra: any = {}) =>
  api.post('/social/feed-events', { event, ...extra }).catch(() => {});

export default function FollowingScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get('/social/following'); setData(r.data); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); fireEvent('following_page_view'); }, [load]);

  const groups = useMemo(() => {
    if (!data) return [];
    const map: any = {
      people: ['People', data.people], creators: ['Creators', data.creators],
      advisors: ['Advisors', data.advisors], businesses: ['Businesses', data.businesses],
      stations: ['Stations', data.stations], clubs: ['Clubs', data.clubs],
    };
    const keys = filter === 'all' ? Object.keys(map) : [filter];
    const ql = q.trim().toLowerCase();
    return keys.map((k) => {
      const [label, items] = map[k];
      const f = (items || []).filter((it: any) => !ql || (it.name || '').toLowerCase().includes(ql));
      return { key: k, label, items: f };
    }).filter((g) => g.items.length > 0);
  }, [data, filter, q]);

  const unfollow = async (kind: string, item: any) => {
    const id = item.user_id || item.business_id || item.station_id || item.club_slug;
    setBusy(id);
    try {
      if (['people', 'creators', 'advisors'].includes(kind)) await api.delete(`/social/follow/${item.user_id}`);
      else if (kind === 'businesses') await api.post(`/business/${item.business_id}/unfollow`);
      else if (kind === 'stations') await api.post(`/stations/${item.station_id}/unfollow`);
      else if (kind === 'clubs') await api.post(`/social/clubs/${item.club_slug}/leave`);
      fireEvent('following_unfollow', { item_id: id, item_type: kind });
      await load();
    } catch (_) {} finally { setBusy(null); }
  };

  const total = data?.count || 0;
  return (
    <View style={s.screen} testID="following-screen">
      <View style={[s.header, { paddingTop: insets.top + 8 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Pressable onPress={() => router.back()} testID="following-back"><Ionicons name="chevron-back" size={24} color={TUBE.text} /></Pressable>
          <View>
            <Text style={s.title}>People you follow</Text>
            <Text style={s.sub}>{total} following</Text>
          </View>
        </View>
        <View style={s.search}>
          <Ionicons name="search" size={15} color={TUBE.textMuted} />
          <TextInput value={q} onChangeText={setQ} placeholder="Search who you follow…"
            placeholderTextColor={TUBE.textMuted} style={s.searchInput} testID="following-search" autoCapitalize="none" />
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 10 }}>
          {FILTERS.map((f) => {
            const active = filter === f.key;
            return (
              <Pressable key={f.key} onPress={() => { setFilter(f.key); fireEvent('following_filter', { meta: { filter: f.key } }); }}
                testID={`following-filter-${f.key}`} style={[s.chip, active && s.chipActive]}>
                <Text style={[s.chipTxt, active && { color: '#fff' }]}>{f.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {loading ? (
        <View style={s.center}><ActivityIndicator color={TUBE.magenta} /></View>
      ) : groups.length === 0 ? (
        <ScrollView contentContainerStyle={{ paddingTop: 14, paddingBottom: 130 }} showsVerticalScrollIndicator={false}>
          <WhoToFollowM onFollowed={load} />
          <DailyReadingsCardM />
          <View style={[s.center, { paddingTop: 24 }]}>
            <Ionicons name="people" size={28} color={TUBE.magenta} />
            <Text style={s.emptyTitle}>Build your FUUSIC feed</Text>
            <Text style={s.emptyTxt}>Follow people, businesses, creators and clubs you care about.</Text>
          </View>
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={{ paddingBottom: 130, gap: 20 }}
          showsVerticalScrollIndicator={false} testID="following-list">
          <View style={{ paddingTop: 12 }}><WhoToFollowM onFollowed={load} /></View>
          <DailyReadingsCardM />
          <View style={{ paddingHorizontal: TSPACE.md, gap: 20 }}>
          {groups.map((g) => (
            <View key={g.key}>
              <Text style={s.groupTitle}>{g.label} · {g.items.length}</Text>
              <View style={{ gap: 8 }}>
                {g.items.map((it: any) => {
                  const id = it.user_id || it.business_id || it.station_id || it.club_slug;
                  return (
                    <View key={id} style={s.row} testID={`following-item-${id}`}>
                      <AvatarM name={it.name} url={it.avatar_url} size={44} />
                      <View style={{ flex: 1 }}>
                        <Text style={s.name} numberOfLines={1}>{it.name}</Text>
                        <Text style={s.cat} numberOfLines={1}>{it.category || it.type}</Text>
                      </View>
                      <Pressable onPress={() => unfollow(g.key, it)} disabled={busy === id}
                        testID={`following-unfollow-${id}`} style={s.unfollow}>
                        {busy === id ? <ActivityIndicator color={TUBE.text} size="small" />
                          : <><Ionicons name="person-remove" size={13} color={TUBE.text} /><Text style={s.unfollowTxt}>Unfollow</Text></>}
                      </Pressable>
                    </View>
                  );
                })}
              </View>
            </View>
          ))}
          </View>
        </ScrollView>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: TUBE.bg },
  header: { paddingHorizontal: TSPACE.md, paddingBottom: 4, borderBottomWidth: 1, borderBottomColor: TUBE.line },
  title: { color: TUBE.text, fontSize: TFONT.xl, fontWeight: '900' },
  sub: { color: TUBE.textMuted, fontSize: TFONT.xs },
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: 22, paddingHorizontal: 14, marginTop: 12 },
  searchInput: { flex: 1, color: TUBE.text, fontSize: TFONT.sm, paddingVertical: 10 },
  chip: { paddingHorizontal: 14, height: 34, borderRadius: 17, backgroundColor: TUBE.elevated, alignItems: 'center', justifyContent: 'center' },
  chipActive: { backgroundColor: TUBE.magenta },
  chipTxt: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40, gap: 8 },
  emptyTitle: { color: TUBE.text, fontSize: TFONT.lg, fontWeight: '900' },
  emptyTxt: { color: TUBE.textMuted, fontSize: TFONT.sm, textAlign: 'center', maxWidth: 280 },
  groupTitle: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginBottom: 10, textTransform: 'uppercase' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 12 },
  name: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  cat: { color: TUBE.textMuted, fontSize: TFONT.xs, textTransform: 'capitalize' },
  unfollow: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 34, paddingHorizontal: 12, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.1)' },
  unfollowTxt: { color: TUBE.text, fontSize: TFONT.xs, fontWeight: '800' },
});
