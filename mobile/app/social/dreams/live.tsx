import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, Modal,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { TSPACE, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', text: '#F5F3FF', dim: '#a5a0c0',
  violet: '#a855f7', magenta: '#c026d3', accent2: '#7c3aed', rose: '#fb7185',
};

export default function LiveScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [status, setStatus] = useState('live');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState<string | null>(null);
  const [showHost, setShowHost] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try { const { data } = await api.get(`/social/live/sessions?status=${status}`); setItems(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, [status]);
  useEffect(() => { load(); }, [load]);

  return (
    <View style={[s.root, { paddingTop: insets.top }]}>
      <View style={s.header}>
        <Pressable testID="live-back" onPress={() => (open ? setOpen(null) : router.back())} style={s.back}><Ionicons name="chevron-back" size={22} color={D.text} /></Pressable>
        <Text style={s.hTitle}>{open ? 'Live Q&A' : 'Live Dream Q&A'}</Text>
        {!open && <Pressable testID="live-host-cta" onPress={() => setShowHost(true)} style={s.hostBtn}><Ionicons name="videocam" size={15} color="#fff" /><Text style={s.hostTxt}>Host</Text></Pressable>}
      </View>

      {open ? <LiveRoom sessionId={open} onBack={() => { setOpen(null); load(); }} />
        : (
          <>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingHorizontal: TSPACE.md, paddingBottom: 6 }} style={{ flexGrow: 0 }}>
              {[['live', 'Live now'], ['upcoming', 'Upcoming'], ['past', 'Past']].map(([k, l]) => (
                <Pressable key={k} testID={`live-filter-${k}`} onPress={() => setStatus(k)} style={[s.filter, status === k && s.filterA]}><Text style={[s.filterTxt, status === k && { color: '#fff' }]}>{l}</Text></Pressable>
              ))}
            </ScrollView>
            {loading ? <View style={s.center}><ActivityIndicator color={D.violet} /></View>
              : items.length === 0 ? <Text style={s.empty}>No live sessions right now.{'\n'}Verified advisors can host live dream Q&A.</Text>
                : <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 12 }} showsVerticalScrollIndicator={false} testID="live-list">
                    {items.map((it) => (
                      <Pressable key={it.session_id} testID={`live-card-${it.session_id}`} onPress={() => setOpen(it.session_id)} style={s.sessCard}>
                        <LinearGradient colors={[D.accent2, D.magenta]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.sessIcon}><Ionicons name={it.mode === 'video' ? 'videocam' : 'radio'} size={22} color="#fff" /></LinearGradient>
                        <View style={{ flex: 1 }}>
                          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
                            {it.status === 'live' && <View style={s.livePill}><Text style={s.livePillTxt}>● LIVE</Text></View>}
                            {it.featured && <View style={{ backgroundColor: 'rgba(251,191,36,0.2)', borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 }} testID={`live-featured-${it.session_id}`}><Text style={{ color: '#fcd34d', fontSize: 9, fontWeight: '900' }}>★ FEATURED</Text></View>}
                            <Text style={s.sessTitle} numberOfLines={1}>{it.title}</Text>
                          </View>
                          <Text style={s.sessSub} numberOfLines={1}>{it.advisor_name} · {it.advisor_category_label}</Text>
                          <Text style={s.sessMeta}>{it.viewer_count} watching · {it.question_count} questions</Text>
                        </View>
                      </Pressable>
                    ))}
                  </ScrollView>}
          </>
        )}
      {showHost && <HostModal onClose={() => setShowHost(false)} onDone={(id: string) => { setShowHost(false); setStatus('live'); setOpen(id); }} />}
    </View>
  );
}

function LiveRoom({ sessionId, onBack }: any) {
  const [d, setD] = useState<any>(null);
  const [q, setQ] = useState('');
  const load = useCallback(async () => { try { const { data } = await api.get(`/social/live/sessions/${sessionId}`); setD(data); } catch (_) {} }, [sessionId]);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  if (!d) return <View style={s.center}><ActivityIndicator color={D.violet} /></View>;
  const ask = async () => { if (!q.trim()) return; try { await api.post(`/social/live/sessions/${sessionId}/questions`, { text: q }); setQ(''); load(); } catch (_) {} };
  const answer = async (qid: string) => { try { await api.post(`/social/live/questions/${qid}/answer`); load(); } catch (_) {} };
  const end = async () => { try { await api.post(`/social/live/sessions/${sessionId}/end`); onBack(); } catch (_) {} };
  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 130, gap: 12 }} showsVerticalScrollIndicator={false} testID="live-room">
      <View style={s.roomHead}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <LinearGradient colors={[D.accent2, D.magenta]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.sessIcon}><Ionicons name={d.mode === 'video' ? 'videocam' : 'radio'} size={22} color="#fff" /></LinearGradient>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>{d.status === 'live' && <View style={s.livePill}><Text style={s.livePillTxt}>● LIVE</Text></View>}<Text style={s.sessTitle} numberOfLines={1}>{d.title}</Text></View>
            <Text style={s.sessSub}>{d.advisor_name} · {d.advisor_category_label}</Text>
          </View>
        </View>
        <View style={s.roomNote}><Text style={s.roomNoteTxt}>{d.status !== 'live' ? 'This session has ended.' : d.join_token ? `🎧 You're connected to the ${d.mode} room. Full ${d.mode} plays in the app; ask questions below.` : 'Ask your questions below — the advisor answers live.'}</Text></View>
        {d.is_host && d.status === 'live' && <Pressable testID="live-end" onPress={end} style={s.endBtn}><Text style={s.endTxt}>End session</Text></Pressable>}
      </View>

      <Text style={s.section}>QUESTIONS ({d.questions?.length || 0})</Text>
      {d.status === 'live' && (
        <View style={{ flexDirection: 'row', gap: 8 }}>
          <TextInput value={q} onChangeText={setQ} placeholder="Ask about your dream…" placeholderTextColor={D.dim} testID="live-question-input" style={s.qInput} />
          <Pressable testID="live-question-send" onPress={ask} style={s.qSend}><Ionicons name="send" size={17} color="#fff" /></Pressable>
        </View>
      )}
      {(d.questions || []).map((qq: any) => (
        <View key={qq.id} style={s.qCard} testID={`live-q-${qq.id}`}>
          <Text style={s.qTxt}><Text style={{ color: '#ddd6fe', fontWeight: '800' }}>{qq.name}</Text> · {qq.text}</Text>
          {qq.answered ? <Text style={s.answered}>Answered</Text> : d.is_host && <Pressable testID={`live-answer-${qq.id}`} onPress={() => answer(qq.id)}><Text style={s.answerBtn}>Mark answered</Text></Pressable>}
        </View>
      ))}
    </ScrollView>
  );
}

function HostModal({ onClose, onDone }: any) {
  const [title, setTitle] = useState('');
  const [desc, setDesc] = useState('');
  const [mode, setMode] = useState('audio');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');
  const submit = async () => { if (!title.trim()) return; setBusy(true); setErr(''); try { const { data } = await api.post('/social/live/sessions', { title, description: desc, mode }); onDone(data.session_id); } catch (e: any) { setErr(e?.response?.status === 403 ? 'Only verified advisors can host.' : 'Couldn\'t start.'); } finally { setBusy(false); } };
  return (
    <Modal transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.modalWrap} onPress={onClose}>
        <Pressable style={s.modal} onPress={(e) => e.stopPropagation()}>
          <Text style={s.modalTitle}>Host a live dream Q&A</Text>
          <TextInput value={title} onChangeText={setTitle} placeholder="Session title" placeholderTextColor={D.dim} testID="host-title" style={s.input} />
          <TextInput value={desc} onChangeText={setDesc} placeholder="What's this about?" placeholderTextColor={D.dim} testID="host-desc" multiline style={[s.input, { height: 80, textAlignVertical: 'top' }]} />
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
            {[['audio', 'Audio', 'radio'], ['video', 'Video', 'videocam']].map(([k, l, ic]) => (
              <Pressable key={k} testID={`host-mode-${k}`} onPress={() => setMode(k)} style={[s.modeBtn, mode === k && s.modeBtnA]}><Ionicons name={ic as any} size={15} color={mode === k ? '#fff' : D.dim} /><Text style={[s.modeTxt, mode === k && { color: '#fff' }]}>{l}</Text></Pressable>
            ))}
          </View>
          <Text style={s.hint}>Full live audio/video plays in the RadioLife app. The question queue works everywhere.</Text>
          {err ? <Text style={s.err}>{err}</Text> : null}
          <Pressable testID="host-submit" onPress={submit} disabled={busy} style={[s.btnPrimary, { marginTop: 12 }]}><Text style={s.btnPrimaryTxt}>{busy ? 'Starting…' : 'Go live'}</Text></Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: D.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', paddingVertical: 40 },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 10 },
  back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  hTitle: { color: D.text, fontSize: TFONT.xl, fontWeight: '900', flex: 1 },
  hostBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, backgroundColor: D.accent2, height: 34, paddingHorizontal: 14, borderRadius: 17 },
  hostTxt: { color: '#fff', fontWeight: '900', fontSize: TFONT.xs },
  filter: { height: 34, paddingHorizontal: 16, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.05)', alignItems: 'center', justifyContent: 'center' },
  filterA: { backgroundColor: D.accent2 },
  filterTxt: { color: D.dim, fontSize: TFONT.xs, fontWeight: '800' },
  empty: { color: D.dim, textAlign: 'center', marginTop: 40, lineHeight: 20 },
  sessCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 22, padding: 14 },
  sessIcon: { width: 46, height: 46, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  sessTitle: { color: D.text, fontSize: TFONT.md, fontWeight: '900', flexShrink: 1 },
  sessSub: { color: D.dim, fontSize: TFONT.xs, marginTop: 2 },
  sessMeta: { color: '#6d6a86', fontSize: 11, marginTop: 2 },
  livePill: { backgroundColor: 'rgba(251,113,133,0.2)', borderRadius: 10, paddingHorizontal: 8, paddingVertical: 2 },
  livePillTxt: { color: D.rose, fontSize: 10, fontWeight: '900' },
  roomHead: { backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 22, padding: 16 },
  roomNote: { backgroundColor: 'rgba(168,85,247,0.10)', borderColor: 'rgba(168,85,247,0.2)', borderWidth: 1, borderRadius: 16, padding: 12, marginTop: 12 },
  roomNoteTxt: { color: '#ede9fe', fontSize: TFONT.sm, lineHeight: 20 },
  endBtn: { backgroundColor: 'rgba(251,113,133,0.2)', height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center', marginTop: 12 },
  endTxt: { color: D.rose, fontWeight: '900', fontSize: TFONT.sm },
  section: { color: D.dim, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 1 },
  qInput: { flex: 1, backgroundColor: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderRadius: 22, paddingHorizontal: 16, color: D.text, fontSize: TFONT.sm, height: 44 },
  qSend: { width: 44, height: 44, borderRadius: 22, backgroundColor: D.accent2, alignItems: 'center', justifyContent: 'center' },
  qCard: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 16, padding: 12 },
  qTxt: { color: '#d6d3e8', fontSize: TFONT.sm, flex: 1 },
  answered: { color: '#6ee7b7', fontSize: 10, fontWeight: '900' },
  answerBtn: { color: D.violet, fontSize: 11, fontWeight: '900' },
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modal: { backgroundColor: '#0d0a24', borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 18, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  modalTitle: { color: D.text, fontSize: TFONT.lg, fontWeight: '900', marginBottom: 12 },
  input: { backgroundColor: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11, color: D.text, fontSize: TFONT.sm, marginBottom: 8 },
  modeBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.05)' },
  modeBtnA: { backgroundColor: D.accent2 },
  modeTxt: { color: D.dim, fontSize: TFONT.sm, fontWeight: '800' },
  hint: { color: '#6d6a86', fontSize: 11, marginBottom: 4 },
  err: { color: D.rose, fontSize: TFONT.xs, marginTop: 4 },
  btnPrimary: { backgroundColor: D.accent2, height: 46, borderRadius: 23, alignItems: 'center', justifyContent: 'center' },
  btnPrimaryTxt: { color: '#fff', fontWeight: '900', fontSize: TFONT.md },
});
