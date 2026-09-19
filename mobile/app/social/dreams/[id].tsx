import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TSPACE, TRADIUS, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';
import { AvatarM } from '../../(tabs)/social';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', line: 'rgba(168,85,247,0.18)',
  text: '#F5F3FF', dim: '#a5a0c0', muted: '#6d6a86', violet: '#a855f7',
  magenta: '#c026d3', accent2: '#7c3aed', gold: '#fbbf24', amber: '#fbbf24',
};
const MOOD_TONE: any = {
  Happy: '#fbbf24', Scary: '#f87171', Confusing: '#a78bfa', Peaceful: '#34d399',
  Sad: '#60a5fa', Exciting: '#f472b6', Strange: '#c084fc', Other: '#94a3b8',
};

export default function DreamDetail() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [d, setD] = useState<any>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [reflecting, setReflecting] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/social/dreams/${id}`); setD(data); }
    catch (_) { router.back(); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  const act = async (fn: () => Promise<any>) => { try { await fn(); await load(); } catch (_) {} };
  const reflect = async () => {
    setReflecting(true);
    try { const { data } = await api.post(`/social/dreams/${id}/reflect`); setD((x: any) => ({ ...x, ai_reflection: data.ai_reflection })); }
    catch (_) {} finally { setReflecting(false); }
  };
  const send = async () => {
    if (comment.trim().length < 1) return;
    setBusy(true);
    try { await api.post(`/social/dreams/${id}/comments`, { text: comment.trim() }); setComment(''); await load(); }
    catch (_) {} finally { setBusy(false); }
  };
  const report = async () => { await act(() => api.post(`/social/dreams/${id}/report`, { reason: 'Reported from mobile' })); };

  if (!d) return <View style={[s.screen, s.center]}><ActivityIndicator color={D.violet} /></View>;
  const ref = d.ai_reflection;
  return (
    <View style={s.screen} testID="dream-detail">
      <View style={[s.topbar, { paddingTop: insets.top + 6 }]}>
        <Pressable onPress={() => router.back()} testID="dream-back" hitSlop={10}><Ionicons name="chevron-back" size={24} color={D.text} /></Pressable>
        <Text style={s.topbarTitle}>Dream</Text>
      </View>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={80}>
        <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 40, gap: 14 }} showsVerticalScrollIndicator={false}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            {d.author?.anonymous ? <View style={s.anonAv}><Ionicons name="eye-off" size={16} color={D.violet} /></View>
              : <AvatarM name={d.author?.name} url={d.author?.avatar_url} size={34} />}
            <View style={{ flex: 1 }}><Text style={s.who}>{d.author?.name}</Text>
              {d.mood ? <Text style={{ color: MOOD_TONE[d.mood], fontSize: TFONT.xs }}>{d.mood}</Text> : null}</View>
          </View>
          {d.title ? <Text style={s.title}>{d.title}</Text> : null}
          <Text style={s.body}>{d.description}</Text>
          {d.tags?.length > 0 ? <View style={s.wrapRow}>{d.tags.map((t: string) => <View key={t} style={s.tag}><Text style={s.tagTxt}>{t}</Text></View>)}</View> : null}

          <View style={s.wrapRow}>
            <ActBtn active={d.my_similar} icon="people" testID="dream-similar-btn" onPress={() => act(() => api.post(`/social/dreams/${id}/similar`))} label={`${d.my_similar ? 'You dreamed this' : 'Similar dream'} (${d.similar_count})`} />
            <ActBtn active={d.saved} icon="bookmark" testID="dream-save-btn" onPress={() => act(() => d.saved ? api.delete(`/social/dreams/${id}/save`) : api.post(`/social/dreams/${id}/save`))} label={d.saved ? 'Saved' : 'Save'} />
            <ActBtn icon="flag" testID="dream-report-btn" onPress={report} label="Report" />
          </View>

          {/* AI reflection */}
          <View style={s.aiBlock} testID="dream-ai-block">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 8 }}>
              <Ionicons name="sparkles" size={16} color={D.magenta} /><Text style={s.aiTitle}>Explore with AI</Text></View>
            {!ref ? (
              <Pressable onPress={reflect} disabled={reflecting} testID="dream-reflect-btn" style={s.aiBtn}>
                {reflecting ? <ActivityIndicator color="#fff" /> : <><Ionicons name="color-wand" size={16} color="#fff" /><Text style={s.aiBtnTxt}>Reflect on this dream</Text></>}</Pressable>
            ) : (
              <View style={{ gap: 6 }} testID="dream-ai-reflection">
                <Text style={s.aiHeader}>{ref.header}</Text>
                {(ref.symbolic_readings || []).map((x: string, i: number) => <Text key={i} style={s.aiLine}>• {x}</Text>)}
                {(ref.questions_to_consider || []).length > 0 ? <Text style={s.aiSub}>QUESTIONS TO CONSIDER</Text> : null}
                {(ref.questions_to_consider || []).map((q: string, i: number) => <Text key={i} style={s.aiLine}>— {q}</Text>)}
                {ref.gentle_note ? <Text style={s.aiNote}>{ref.gentle_note}</Text> : null}
                {ref.safety_note ? <Text style={s.aiSafety}>⚠ {ref.safety_note}</Text> : null}
              </View>
            )}
          </View>

          {/* Comments */}
          <Text style={s.sectionTitle}>COMMENTS ({d.comment_count})</Text>
          {(d.comments || []).length === 0 ? <Text style={s.muted}>No comments yet — say something supportive.</Text>
            : (d.comments || []).map((c: any) => (
              <View key={c.id} style={s.comment} testID={`dream-comment-${c.id}`}>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                  <Text style={s.commentWho}>{c.name}</Text>
                  {c.is_advisor ? <View style={s.advBadge}><Ionicons name="checkmark-circle" size={10} color={D.violet} /><Text style={s.advBadgeTxt}>{c.advisor_category_label}</Text></View> : null}
                </View>
                <Text style={s.commentTxt}>{c.text}</Text>
              </View>
            ))}
        </ScrollView>
        <View style={[s.composer, { paddingBottom: insets.bottom + 8 }]}>
          <TextInput value={comment} onChangeText={setComment} testID="dream-comment-input" placeholder="Add a supportive comment…" placeholderTextColor={D.muted} style={s.composerInput} />
          <Pressable onPress={send} disabled={busy} testID="dream-comment-send" style={s.sendBtn}>
            {busy ? <ActivityIndicator color="#fff" size="small" /> : <Ionicons name="send" size={18} color="#fff" />}</Pressable>
        </View>
      </KeyboardAvoidingView>
    </View>
  );
}

function ActBtn({ active, icon, onPress, label, testID }: any) {
  return (
    <Pressable onPress={onPress} testID={testID} style={[s.actBtn, active && s.actBtnActive]}>
      <Ionicons name={icon} size={14} color={active ? D.violet : D.dim} />
      <Text style={[s.actBtnTxt, active && { color: D.violet }]}>{label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: D.bg },
  center: { alignItems: 'center', justifyContent: 'center' },
  topbar: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: TSPACE.md, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: D.line },
  topbarTitle: { color: D.text, fontSize: TFONT.lg, fontWeight: '900' },
  who: { color: D.text, fontSize: TFONT.sm, fontWeight: '800' },
  title: { color: D.text, fontSize: TFONT.xl, fontWeight: '900' },
  body: { color: D.text, fontSize: TFONT.md, lineHeight: 22 },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tag: { backgroundColor: 'rgba(255,255,255,0.05)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10 },
  tagTxt: { color: D.dim, fontSize: TFONT.xs },
  anonAv: { width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(168,85,247,0.2)', alignItems: 'center', justifyContent: 'center' },
  actBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 36, paddingHorizontal: 12, borderRadius: 18, borderWidth: 1, borderColor: D.line, backgroundColor: D.elevated },
  actBtnActive: { backgroundColor: 'rgba(168,85,247,0.2)', borderColor: 'rgba(168,85,247,0.4)' },
  actBtnTxt: { color: D.dim, fontSize: TFONT.xs, fontWeight: '800' },
  aiBlock: { backgroundColor: 'rgba(192,38,211,0.07)', borderWidth: 1, borderColor: 'rgba(192,38,211,0.25)', borderRadius: TRADIUS.lg, padding: 14 },
  aiTitle: { color: D.text, fontSize: TFONT.md, fontWeight: '900' },
  aiBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 44, borderRadius: 22, backgroundColor: D.magenta },
  aiBtnTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  aiHeader: { color: 'rgba(240,171,252,0.9)', fontSize: TFONT.xs, fontStyle: 'italic' },
  aiLine: { color: D.text, fontSize: TFONT.sm, lineHeight: 20 },
  aiSub: { color: D.muted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1, marginTop: 4 },
  aiNote: { color: D.dim, fontSize: TFONT.xs, marginTop: 4 },
  aiSafety: { color: D.amber, fontSize: TFONT.xs, marginTop: 4 },
  sectionTitle: { color: D.muted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginTop: 4 },
  muted: { color: D.muted, fontSize: TFONT.sm },
  comment: { backgroundColor: D.elevated, borderWidth: 1, borderColor: D.line, borderRadius: TRADIUS.md, padding: 12 },
  commentWho: { color: D.text, fontSize: TFONT.xs, fontWeight: '800' },
  commentTxt: { color: D.dim, fontSize: TFONT.sm, marginTop: 3 },
  advBadge: { flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: 'rgba(168,85,247,0.2)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 },
  advBadgeTxt: { color: D.violet, fontSize: 9, fontWeight: '900' },
  composer: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: TSPACE.md, paddingTop: 8, borderTopWidth: 1, borderTopColor: D.line, backgroundColor: D.bg },
  composerInput: { flex: 1, backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: D.line, borderRadius: 22, paddingHorizontal: 16, paddingVertical: 11, color: D.text, fontSize: TFONT.sm },
  sendBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: D.magenta, alignItems: 'center', justifyContent: 'center' },
});
