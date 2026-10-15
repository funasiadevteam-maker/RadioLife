// FUUSIC Social — mobile "Who to Follow" interest-based suggestions row.
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { TUBE, TSPACE, TFONT } from '../constants/tube';
import api from '../api/client';
import { AvatarM } from '../../app/(tabs)/social';

const followUrl = (s: any) => {
  switch (s.actor_type) {
    case 'station': return `/stations/${s.actor_id}/follow`;
    case 'business': return `/business/${s.actor_id}/follow`;
    case 'club': return `/social/clubs/${s.actor_id}/join`;
    default: return `/social/follow/${s.actor_id}`;
  }
};

const TYPE_ICON: any = {
  person: 'people', creator: 'mic', advisor: 'moon',
  station: 'radio', business: 'storefront', club: 'people-circle',
};

export default function WhoToFollowM({ onFollowed, limit = 10 }: { onFollowed?: () => void; limit?: number }) {
  const [items, setItems] = useState<any[] | null>(null);
  const [state, setState] = useState<Record<string, string | undefined>>({});

  const load = useCallback(async () => {
    try { const r = await api.get('/social/who-to-follow', { params: { limit } }); setItems(r.data?.items || []); }
    catch (_) { setItems([]); }
  }, [limit]);
  useEffect(() => { load(); }, [load]);

  const key = (s: any) => `${s.actor_type}:${s.actor_id}`;

  const follow = async (s: any) => {
    const k = key(s);
    setState((p) => ({ ...p, [k]: 'busy' }));
    try {
      await api.post(followUrl(s), {});
      setState((p) => ({ ...p, [k]: 'following' }));
      onFollowed && onFollowed();
      setTimeout(() => setItems((prev) => (prev || []).filter((x) => key(x) !== k)), 900);
    } catch (_) { setState((p) => ({ ...p, [k]: undefined })); }
  };

  const dismiss = (s: any, action: string) => {
    const k = key(s);
    setItems((prev) => (prev || []).filter((x) => key(x) !== k));
    api.post('/social/suggestions/dismiss', { actor_type: s.actor_type, actor_id: s.actor_id, action }).catch(() => {});
  };

  if (items && items.length === 0) return null;

  return (
    <View testID="who-to-follow" style={{ marginBottom: 6 }}>
      <View style={w.head}>
        <Ionicons name="sparkles" size={15} color={TUBE.magenta} />
        <Text style={w.title}>Who to Follow</Text>
      </View>
      {!items ? (
        <View style={{ height: 150, alignItems: 'center', justifyContent: 'center' }}>
          <ActivityIndicator color={TUBE.magenta} />
        </View>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 10, paddingHorizontal: TSPACE.md, paddingVertical: 4 }}>
          {items.map((s) => {
            const k = key(s); const st = state[k];
            return (
              <View key={k} testID={`wtf-card-${s.actor_type}-${s.actor_id}`} style={w.card}>
                <Pressable onPress={() => dismiss(s, 'hide')} testID={`wtf-hide-${s.actor_id}`} style={w.hide}>
                  <Ionicons name="close" size={13} color={TUBE.textMuted} />
                </Pressable>
                <AvatarM name={s.name} url={s.avatar_url} size={52} />
                <Text style={w.name} numberOfLines={1}>{s.name}</Text>
                <View style={w.catRow}>
                  <Ionicons name={TYPE_ICON[s.actor_type] || 'people'} size={11} color={TUBE.textMuted} />
                  <Text style={w.cat} numberOfLines={1}>{s.category || s.actor_type}</Text>
                </View>
                <Text style={w.reason} numberOfLines={1}>{s.reason}</Text>
                <Pressable onPress={() => follow(s)} disabled={st === 'busy' || st === 'following'}
                  testID={`wtf-follow-${s.actor_id}`}
                  style={[w.followBtn, st === 'following' && { backgroundColor: '#22c55e' }]}>
                  {st === 'busy' ? <ActivityIndicator size="small" color="#fff" />
                    : st === 'following'
                      ? <><Ionicons name="checkmark" size={14} color="#fff" /><Text style={w.followTxt}>Following</Text></>
                      : <><Ionicons name="person-add" size={13} color="#fff" /><Text style={w.followTxt}>Follow</Text></>}
                </Pressable>
                <Pressable onPress={() => dismiss(s, 'not_interested')} testID={`wtf-notinterested-${s.actor_id}`}>
                  <Text style={w.notInterested}>Not interested</Text>
                </Pressable>
              </View>
            );
          })}
        </ScrollView>
      )}
    </View>
  );
}

const w = StyleSheet.create({
  head: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: TSPACE.md, marginBottom: 8 },
  title: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '900' },
  card: { width: 170, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: 16, padding: 14, alignItems: 'center' },
  hide: { position: 'absolute', top: 6, right: 6, width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(255,255,255,0.08)' },
  name: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800', marginTop: 8, maxWidth: '100%' },
  catRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 },
  cat: { color: TUBE.textMuted, fontSize: TFONT.xs, textTransform: 'capitalize', maxWidth: 110 },
  reason: { color: TUBE.magenta, fontSize: 10.5, fontWeight: '700', marginTop: 6, marginBottom: 10, textAlign: 'center' },
  followBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, width: '100%', height: 34, borderRadius: 17, backgroundColor: TUBE.magenta },
  followTxt: { color: '#fff', fontSize: TFONT.xs, fontWeight: '800' },
  notInterested: { color: TUBE.textMuted, fontSize: 11, fontWeight: '600', marginTop: 8 },
});
