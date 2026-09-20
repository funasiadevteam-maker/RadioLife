import React, { useCallback, useEffect, useState } from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator } from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TSPACE, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', text: '#F5F3FF',
  dim: '#a5a0c0', violet: '#a855f7', accent2: '#7c3aed',
};

export default function ClustersScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [clusters, setClusters] = useState<any[] | null>(null);
  const [open, setOpen] = useState<any>(null);      // {theme,label,count}
  const [items, setItems] = useState<any[] | null>(null);
  const [following, setFollowing] = useState(false);

  useEffect(() => {
    api.get('/social/clusters').then(({ data }) => setClusters(data.clusters || [])).catch(() => setClusters([]));
  }, []);

  const openTheme = useCallback(async (c: any) => {
    setOpen(c); setItems(null); setFollowing(!!c.following);
    try { const { data } = await api.get(`/social/clusters/${c.theme}`); setItems(data.items || []); }
    catch (_) { setItems([]); }
  }, []);

  const toggleFollow = useCallback(async () => {
    if (!open) return;
    const next = !following; setFollowing(next);
    try {
      if (next) await api.post(`/social/clusters/${open.theme}/follow`);
      else await api.delete(`/social/clusters/${open.theme}/follow`);
    } catch (_) { setFollowing(!next); }
  }, [open, following]);

  return (
    <View style={[s.root, { paddingTop: insets.top }]}>
      <View style={s.header}>
        <Pressable testID="clusters-back" onPress={() => (open ? setOpen(null) : router.back())} style={s.back}>
          <Ionicons name="chevron-back" size={22} color={D.text} />
        </Pressable>
        <Text style={s.hTitle}>{open ? open.label : 'Dream Clusters'}</Text>
      </View>

      {!open ? (
        clusters === null ? <View style={s.center}><ActivityIndicator color={D.violet} /></View>
          : clusters.length === 0 ? (
            <View style={s.center}><Ionicons name="layers-outline" size={34} color={D.violet} /><Text style={s.emptyT}>No clusters yet</Text><Text style={s.emptyS}>Share public dreams to see people who dreamed the same.</Text></View>
          ) : (
            <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 10 }} showsVerticalScrollIndicator={false} testID="clusters-list">
              <Text style={s.intro}>AI groups public dreams by theme so you can find others who dreamed the same thing.</Text>
              {clusters.map((c) => (
                <Pressable key={c.theme} testID={`cluster-card-${c.theme}`} onPress={() => openTheme(c)} style={s.card}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.cardTitle}>{c.label}</Text>
                    <Text style={s.cardCount}>{c.count} dreamed this</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={18} color={D.dim} />
                </Pressable>
              ))}
            </ScrollView>
          )
      ) : (
        items === null ? <View style={s.center}><ActivityIndicator color={D.violet} /></View>
          : (
            <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 10 }} showsVerticalScrollIndicator={false} testID="cluster-detail">
              <Pressable testID="cluster-follow" onPress={toggleFollow} style={[s.follow, following && s.followOn]}>
                <Ionicons name={following ? 'checkmark' : 'notifications'} size={16} color={following ? '#a7f3d0' : '#fff'} />
                <Text style={[s.followTxt, following && { color: '#a7f3d0' }]}>{following ? 'Following' : 'Follow this cluster'}</Text>
              </Pressable>
              {items.length === 0 ? <Text style={s.emptyS}>No dreams in this cluster yet.</Text> : items.map((d) => (
                <View key={d.dream_id} style={s.card} testID={`cluster-dream-${d.dream_id}`}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.cardTitle} numberOfLines={1}>{d.title || 'Untitled dream'}</Text>
                    <Text style={s.dreamBody} numberOfLines={2}>{d.description}</Text>
                    <Text style={s.dreamMeta}>{d.author?.name || 'Anonymous Dreamer'} · {d.similar_count} similar</Text>
                  </View>
                </View>
              ))}
            </ScrollView>
          )
      )}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: D.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 10 },
  back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  hTitle: { color: D.text, fontSize: TFONT.xl, fontWeight: '900' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 30, gap: 8 },
  emptyT: { color: D.text, fontSize: TFONT.lg, fontWeight: '900', marginTop: 4 },
  emptyS: { color: D.dim, fontSize: TFONT.sm, textAlign: 'center', lineHeight: 20 },
  intro: { color: D.dim, fontSize: TFONT.xs, lineHeight: 18, marginBottom: 2 },
  card: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 18, padding: 14 },
  cardTitle: { color: D.text, fontSize: TFONT.md, fontWeight: '900' },
  cardCount: { color: D.violet, fontSize: TFONT.xs, marginTop: 2 },
  dreamBody: { color: D.dim, fontSize: TFONT.xs, marginTop: 4, lineHeight: 17 },
  dreamMeta: { color: D.violet, fontSize: 11, marginTop: 6 },
  follow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 44, borderRadius: 22, backgroundColor: D.accent2 || '#7c3aed' },
  followOn: { backgroundColor: 'rgba(16,185,129,0.2)' },
  followTxt: { color: '#fff', fontWeight: '900', fontSize: TFONT.sm },
});
