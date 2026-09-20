import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, Modal, Switch,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TSPACE, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';
import MiniToast from '../../../src/components/MiniToast';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', line: 'rgba(168,85,247,0.18)',
  text: '#F5F3FF', dim: '#a5a0c0', violet: '#a855f7', magenta: '#c026d3', accent2: '#7c3aed',
};

export default function ClubsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [clubs, setClubs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/clubs'); setClubs(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <View style={[s.root, { paddingTop: insets.top }]}>
      <View style={s.header}>
        <Pressable testID="clubs-back" onPress={() => (open ? setOpen(null) : router.back())} style={s.back}><Ionicons name="chevron-back" size={22} color={D.text} /></Pressable>
        <Text style={s.hTitle}>{open ? 'Club' : 'Dream Clubs'}</Text>
      </View>
      {loading ? <View style={s.center}><ActivityIndicator color={D.violet} /></View>
        : open ? <ClubDetail slug={open} onChanged={load} />
          : (
            <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 12 }} showsVerticalScrollIndicator={false} testID="clubs-list">
              {clubs.map((c) => (
                <Pressable key={c.slug} testID={`club-card-${c.slug}`} onPress={() => setOpen(c.slug)} style={s.clubCard}>
                  <View style={[s.clubIcon, { backgroundColor: `${c.color}22` }]}><Ionicons name="people-circle" size={24} color={c.color} /></View>
                  <View style={{ flex: 1 }}>
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                      <Text style={s.clubName}>{c.name}</Text>
                      {c.is_member && <View style={s.joinedPill}><Text style={s.joinedTxt}>Joined</Text></View>}
                    </View>
                    <Text style={s.clubDesc} numberOfLines={1}>{c.description}</Text>
                    <Text style={s.clubMeta}>{c.member_count} members · {c.dream_count} dreams</Text>
                  </View>
                </Pressable>
              ))}
            </ScrollView>
          )}
    </View>
  );
}

function ClubDetail({ slug, onChanged }: any) {
  const [data, setData] = useState<any>(null);
  const [showPost, setShowPost] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const load = useCallback(async () => { try { const { data } = await api.get(`/social/clubs/${slug}`); setData(data); } catch (_) {} }, [slug]);
  useEffect(() => { load(); }, [load]);
  if (!data) return <View style={s.center}><ActivityIndicator color={D.violet} /></View>;
  const toggle = async () => { try { await api.post(`/social/clubs/${slug}/${data.is_member ? 'leave' : 'join'}`); load(); onChanged?.(); } catch (_) {} };
  return (
    <>
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 12 }} showsVerticalScrollIndicator={false} testID="club-detail">
      <View style={[s.detailCard, { borderColor: `${data.color}44` }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
          <View style={[s.clubIcon, { backgroundColor: `${data.color}22`, width: 52, height: 52 }]}><Ionicons name="people-circle" size={28} color={data.color} /></View>
          <View style={{ flex: 1 }}><Text style={s.detailTitle}>{data.name}</Text><Text style={s.clubDesc}>{data.description}</Text><Text style={s.clubMeta}>{data.member_count} members · {data.dream_count} dreams</Text></View>
        </View>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: 14 }}>
          <Pressable testID="club-join-toggle" onPress={toggle} style={[s.btn, data.is_member ? s.btnGhost : s.btnPrimary]}><Text style={data.is_member ? s.btnGhostTxt : s.btnPrimaryTxt}>{data.is_member ? 'Leave' : 'Join club'}</Text></Pressable>
          <Pressable testID="club-post-cta" onPress={() => setShowPost(true)} style={[s.btn, s.btnPrimary, { flex: 1 }]}><Ionicons name="add" size={16} color="#fff" /><Text style={s.btnPrimaryTxt}>Share a dream</Text></Pressable>
        </View>
      </View>
      {(data.dreams || []).length === 0
        ? <Text style={s.empty}>No dreams yet — be the first. 🌙</Text>
        : data.dreams.map((d: any) => (
          <View key={d.dream_id} style={s.dreamCard} testID={`club-dream-${d.dream_id}`}>
            {d.title ? <Text style={s.dreamTitle}>{d.title}</Text> : null}
            <Text style={s.dreamBody}>{d.description}</Text>
            <Text style={s.dreamMeta}>{d.author?.name} · {d.mood || 'Dream'}</Text>
          </View>
        ))}
      {showPost && <PostModal slug={slug} onClose={() => setShowPost(false)} onDone={(pts?: number) => { setShowPost(false); load(); onChanged?.(); setToast(pts ? 'Shared to club · +1 point' : 'Shared to club'); }} />}
    </ScrollView>
    <MiniToast message={toast} onDone={() => setToast(null)} />
    </>
  );
}

function PostModal({ slug, onClose, onDone }: any) {
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [anon, setAnon] = useState(false);
  const [busy, setBusy] = useState(false);
  const submit = async () => { if (!desc.trim()) return; setBusy(true); try { const { data } = await api.post(`/social/clubs/${slug}/dreams`, { title, description: desc, anonymous: anon }); onDone(data?.points_awarded); } catch (_) {} finally { setBusy(false); } };
  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.modalWrap} onPress={onClose}>
        <Pressable style={s.modal} onPress={(e) => e.stopPropagation()}>
          <Text style={s.modalTitle}>Share a dream to this club</Text>
          <TextInput value={title} onChangeText={setTitle} placeholder="Title (optional)" placeholderTextColor={D.dim} testID="club-post-title" style={s.input} />
          <TextInput value={desc} onChangeText={setDesc} placeholder="Describe your dream…" placeholderTextColor={D.dim} testID="club-post-desc" multiline style={[s.input, { height: 110, textAlignVertical: 'top' }]} />
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 10 }}>
            <Switch value={anon} onValueChange={setAnon} testID="club-post-anon" />
            <Text style={{ color: D.dim, fontSize: TFONT.sm }}>Share anonymously</Text>
          </View>
          <Pressable testID="club-post-submit" onPress={submit} disabled={busy} style={[s.btn, s.btnPrimary, { marginTop: 14 }]}><Text style={s.btnPrimaryTxt}>{busy ? 'Sharing…' : 'Share dream'}</Text></Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: D.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 10 },
  back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  hTitle: { color: D.text, fontSize: TFONT.xl, fontWeight: '900' },
  clubCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 22, padding: 14 },
  clubIcon: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  clubName: { color: D.text, fontSize: TFONT.md, fontWeight: '900' },
  clubDesc: { color: D.dim, fontSize: TFONT.xs, marginTop: 2 },
  clubMeta: { color: '#6d6a86', fontSize: 11, marginTop: 2 },
  joinedPill: { backgroundColor: 'rgba(168,85,247,0.2)', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  joinedTxt: { color: '#ddd6fe', fontSize: 10, fontWeight: '800' },
  detailCard: { backgroundColor: D.elevated, borderWidth: 1, borderRadius: 22, padding: 16 },
  detailTitle: { color: D.text, fontSize: TFONT.lg, fontWeight: '900' },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 42, borderRadius: 21, paddingHorizontal: 18 },
  btnPrimary: { backgroundColor: D.accent2 },
  btnPrimaryTxt: { color: '#fff', fontWeight: '900', fontSize: TFONT.sm },
  btnGhost: { backgroundColor: 'rgba(255,255,255,0.06)' },
  btnGhostTxt: { color: '#cbd5e1', fontWeight: '900', fontSize: TFONT.sm },
  empty: { color: D.dim, textAlign: 'center', marginTop: 30 },
  dreamCard: { backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 18, padding: 14 },
  dreamTitle: { color: D.text, fontSize: TFONT.md, fontWeight: '900', marginBottom: 4 },
  dreamBody: { color: '#d6d3e8', fontSize: TFONT.sm, lineHeight: 20 },
  dreamMeta: { color: '#6d6a86', fontSize: 11, marginTop: 8 },
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modal: { backgroundColor: '#0d0a24', borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 18, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  modalTitle: { color: D.text, fontSize: TFONT.lg, fontWeight: '900', marginBottom: 12 },
  input: { backgroundColor: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11, color: D.text, fontSize: TFONT.sm, marginBottom: 8 },
});
