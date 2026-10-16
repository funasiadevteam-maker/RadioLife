// FUUSIC Social V2 — Mobile My Feed Preferences.
// Per-followed-entity frequency control mirroring services/social_feed modes:
//   All Updates · Daily Highlights · Live Only · Mute
// Backed by GET/PUT /api/social/feed-preferences.
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';
import api from '../../src/api/client';
import { AvatarM } from '../(tabs)/social';

export const FEED_MODES = [
  { key: 'all_updates', label: 'All', full: 'All Updates', icon: 'albums-outline', desc: 'Every post, as it happens' },
  { key: 'daily_highlights', label: 'Daily', full: 'Daily Highlights', icon: 'sparkles-outline', desc: 'Grouped into one daily digest' },
  { key: 'live_only', label: 'Live', full: 'Live Only', icon: 'flash-outline', desc: 'Only when they go live' },
  { key: 'mute', label: 'Mute', full: 'Mute', icon: 'notifications-off-outline', desc: 'Hidden from feed (still followed)' },
];

const GROUPS = [
  { key: 'people', type: 'person', title: 'People', icon: 'people' },
  { key: 'stations', type: 'station', title: 'Stations', icon: 'radio' },
  { key: 'businesses', type: 'business', title: 'Businesses', icon: 'business' },
];

export default function FeedSettingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try { const r = await api.get('/social/feed-preferences'); setData(r.data || {}); }
    catch (_) { setData({ people: [], stations: [], businesses: [] }); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const total = useMemo(
    () => GROUPS.reduce((n, g) => n + ((data?.[g.key] || []).length), 0), [data]);

  const setMode = async (groupKey: string, type: string, entity: any, mode: string) => {
    if (entity.frequency_mode === mode) return;
    const id = entity.actor_id;
    setSaving(`${type}:${id}`);
    setData((d: any) => ({
      ...d,
      [groupKey]: (d[groupKey] || []).map((e: any) =>
        e.actor_id === id ? { ...e, frequency_mode: mode, explicitly_set: true } : e),
    }));
    try { await api.put(`/social/feed-preferences/${type}/${id}`, { frequency_mode: mode }); }
    catch (_) { load(); } finally { setSaving(null); }
  };

  return (
    <View style={s.screen} testID="feed-settings-screen">
      <View style={[s.header, { paddingTop: insets.top + 8 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Pressable onPress={() => router.back()} testID="feed-settings-back">
            <Ionicons name="chevron-back" size={24} color={TUBE.text} />
          </Pressable>
          <View>
            <Text style={s.title}>My Feed Preferences</Text>
            <Text style={s.sub}>Your choices always win over ranking</Text>
          </View>
        </View>
      </View>

      {loading ? (
        <View style={s.center}><ActivityIndicator color={TUBE.magenta} /></View>
      ) : total === 0 ? (
        <View style={[s.center, { paddingTop: 60 }]} testID="feed-settings-empty">
          <Ionicons name="people" size={28} color={TUBE.magenta} />
          <Text style={s.emptyTitle}>Nothing to tune yet</Text>
          <Text style={s.emptyTxt}>Follow people, stations and businesses, then fine-tune how much you see from each.</Text>
        </View>
      ) : (
        <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 22 }}
          showsVerticalScrollIndicator={false} testID="feed-settings-list">
          {GROUPS.map((g) => {
            const items = (data?.[g.key] || []) as any[];
            if (!items.length) return null;
            return (
              <View key={g.key} testID={`feed-settings-group-${g.key}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7, marginBottom: 10 }}>
                  <Ionicons name={g.icon as any} size={15} color={TUBE.magenta} />
                  <Text style={s.groupTitle}>{g.title} · {items.length}</Text>
                </View>
                <View style={{ gap: 10 }}>
                  {items.map((e) => {
                    const mode = e.frequency_mode || 'all_updates';
                    const busy = saving === `${g.type}:${e.actor_id}`;
                    return (
                      <View key={e.actor_id} style={s.card} testID={`feed-settings-row-${g.type}-${e.actor_id}`}>
                        <View style={s.cardHead}>
                          <AvatarM name={e.name} url={e.avatar_url} size={42} />
                          <View style={{ flex: 1 }}>
                            <Text style={s.name} numberOfLines={1}>{e.name}</Text>
                            <Text style={s.cat} numberOfLines={1}>
                              {FEED_MODES.find((m) => m.key === mode)?.desc}
                              {!e.explicitly_set ? '  · default' : ''}
                            </Text>
                          </View>
                          {busy && <ActivityIndicator color={TUBE.magenta} size="small" />}
                        </View>
                        <View style={s.segRow}>
                          {FEED_MODES.map((m) => {
                            const active = m.key === mode;
                            return (
                              <Pressable key={m.key} onPress={() => setMode(g.key, g.type, e, m.key)}
                                testID={`feed-settings-mode-${g.type}-${e.actor_id}-${m.key}`}
                                style={[s.seg, active && s.segActive]}>
                                <Ionicons name={m.icon as any} size={16} color={active ? '#fff' : TUBE.textMuted} />
                                <Text style={[s.segTxt, active && { color: '#fff' }]}>{m.label}</Text>
                              </Pressable>
                            );
                          })}
                        </View>
                      </View>
                    );
                  })}
                </View>
              </View>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: TUBE.bg },
  header: { paddingHorizontal: TSPACE.md, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: TUBE.line },
  title: { color: TUBE.text, fontSize: TFONT.xl, fontWeight: '900' },
  sub: { color: TUBE.textMuted, fontSize: TFONT.xs },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40, gap: 8 },
  emptyTitle: { color: TUBE.text, fontSize: TFONT.lg, fontWeight: '900' },
  emptyTxt: { color: TUBE.textMuted, fontSize: TFONT.sm, textAlign: 'center', maxWidth: 300 },
  groupTitle: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, textTransform: 'uppercase' },
  card: { backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 12 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 11, marginBottom: 11 },
  name: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  cat: { color: TUBE.textMuted, fontSize: TFONT.xs },
  segRow: { flexDirection: 'row', gap: 6 },
  seg: { flex: 1, alignItems: 'center', gap: 3, paddingVertical: 9, borderRadius: 11, borderWidth: 1, borderColor: TUBE.line, backgroundColor: 'transparent' },
  segActive: { backgroundColor: TUBE.magenta, borderColor: TUBE.magenta },
  segTxt: { color: TUBE.textMuted, fontSize: 11, fontWeight: '800' },
});
