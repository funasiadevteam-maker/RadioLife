import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, Modal, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { TSPACE, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', line: 'rgba(168,85,247,0.18)',
  text: '#F5F3FF', dim: '#a5a0c0', violet: '#a855f7', magenta: '#c026d3',
  accent2: '#7c3aed', gold: '#fbbf24',
};
const KINDS = [
  { key: 'horoscope', label: 'Horoscope', icon: 'sunny' },
  { key: 'tarot', label: 'Tarot', icon: 'sparkles' },
  { key: 'numerology', label: 'Numerology', icon: 'star' },
];

export default function AiReadingsScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [kind, setKind] = useState('horoscope');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<any[]>([]);
  const [dob, setDob] = useState('');
  const [timeframe, setTimeframe] = useState('today');
  const [question, setQuestion] = useState('');
  const [spread, setSpread] = useState('three');
  const [name, setName] = useState('');

  const loadHistory = useCallback(async () => {
    try { const { data } = await api.get('/social/readings'); setHistory(data.items || []); } catch (_) {}
  }, []);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const run = async () => {
    setBusy(true); setResult(null);
    try {
      let data;
      if (kind === 'horoscope') { if (!dob) { setBusy(false); return; } ({ data } = await api.post('/social/readings/horoscope', { dob, timeframe })); }
      else if (kind === 'tarot') { ({ data } = await api.post('/social/readings/tarot', { question, spread })); }
      else { if (!dob) { setBusy(false); return; } ({ data } = await api.post('/social/readings/numerology', { full_name: name, dob })); }
      setResult(data); loadHistory();
    } catch (_) {} finally { setBusy(false); }
  };

  return (
    <View style={[st.root, { paddingTop: insets.top }]}>
      <View style={st.header}>
        <Pressable testID="readings-back" onPress={() => router.back()} style={st.back}><Ionicons name="chevron-back" size={22} color={D.text} /></Pressable>
        <Text style={st.hTitle}>AI Readings</Text>
      </View>
      <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 140, gap: 14 }} showsVerticalScrollIndicator={false} testID="ai-readings">
        <View style={st.notice}><Text style={st.noticeTxt}>✦ AI-GENERATED · for entertainment & reflection only — not advice, not a guaranteed prediction.</Text></View>

        <View style={st.kindRow}>
          {KINDS.map((k) => {
            const active = kind === k.key;
            return (
              <Pressable key={k.key} testID={`reading-kind-${k.key}`} onPress={() => { setKind(k.key); setResult(null); }} style={{ flex: 1 }}>
                {active
                  ? <LinearGradient colors={[D.accent2, D.magenta]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.kindActive}><Ionicons name={k.icon as any} size={15} color="#fff" /><Text style={st.kindTxtA}>{k.label}</Text></LinearGradient>
                  : <View style={st.kind}><Ionicons name={k.icon as any} size={15} color={D.dim} /><Text style={st.kindTxt}>{k.label}</Text></View>}
              </Pressable>
            );
          })}
        </View>

        <View style={st.card}>
          {kind === 'horoscope' && (<>
            <Text style={st.lbl}>Your birth date (YYYY-MM-DD)</Text>
            <TextInput value={dob} onChangeText={setDob} placeholder="1990-07-15" placeholderTextColor={D.dim} testID="horo-dob" style={st.input} />
            <View style={st.segRow}>{['today', 'week', 'month'].map((t) => (
              <Pressable key={t} testID={`horo-tf-${t}`} onPress={() => setTimeframe(t)} style={[st.seg, timeframe === t && st.segA]}><Text style={[st.segTxt, timeframe === t && { color: '#fff' }]}>{t[0].toUpperCase() + t.slice(1)}</Text></Pressable>
            ))}</View>
          </>)}
          {kind === 'tarot' && (<>
            <Text style={st.lbl}>Your question (optional)</Text>
            <TextInput value={question} onChangeText={setQuestion} placeholder="What should I focus on?" placeholderTextColor={D.dim} testID="tarot-q" style={st.input} />
            <View style={st.segRow}>{[['one', '1 card'], ['three', '3 cards']].map(([k, l]) => (
              <Pressable key={k} testID={`tarot-spread-${k}`} onPress={() => setSpread(k)} style={[st.seg, spread === k && st.segA]}><Text style={[st.segTxt, spread === k && { color: '#fff' }]}>{l}</Text></Pressable>
            ))}</View>
          </>)}
          {kind === 'numerology' && (<>
            <Text style={st.lbl}>Full name (optional)</Text>
            <TextInput value={name} onChangeText={setName} placeholder="Your full name" placeholderTextColor={D.dim} testID="num-name" style={st.input} />
            <Text style={st.lbl}>Your birth date (YYYY-MM-DD)</Text>
            <TextInput value={dob} onChangeText={setDob} placeholder="1990-07-15" placeholderTextColor={D.dim} testID="num-dob" style={st.input} />
          </>)}
          <Pressable testID="reading-generate" onPress={run} disabled={busy}>
            <LinearGradient colors={[D.accent2, D.magenta]} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.genBtn}>
              {busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="sparkles" size={17} color="#fff" /><Text style={st.genTxt}>Generate reading</Text></>}
            </LinearGradient>
          </Pressable>
        </View>

        {result && <ReadingResult r={result} />}

        {history.length > 0 && (<>
          <Text style={st.section}>YOUR READINGS</Text>
          {history.map((r) => (
            <Pressable key={r.reading_id} testID={`reading-hist-${r.reading_id}`} onPress={() => setResult(r)} style={st.histRow}>
              <Ionicons name="star" size={15} color={D.violet} />
              <View style={{ flex: 1 }}><Text style={st.histTitle} numberOfLines={1}>{r.title}</Text><Text style={st.histSub}>{r.type}</Text></View>
              <Ionicons name="chevron-forward" size={16} color={D.dim} />
            </Pressable>
          ))}
        </>)}
      </ScrollView>
    </View>
  );
}

function ReadingResult({ r }: any) {
  const res = r.result || {};
  return (
    <View style={st.card} testID="reading-result">
      <Text style={st.resLabel}>{r.label}</Text>
      <Text style={st.resHead}>{res.headline || r.title}</Text>
      {r.cards && (
        <View style={st.cardsWrap}>
          {r.cards.map((c: any, i: number) => (
            <View key={i} style={st.tcard} testID={`tarot-card-${i}`}><Text style={st.tcardName}>{c.name}</Text><Text style={st.tcardMeta}>{c.orientation} · {c.position}</Text></View>
          ))}
        </View>
      )}
      {res.life_path !== undefined && <Text style={st.lifePath}>Life Path {res.life_path} — {res.life_path_meaning}</Text>}
      <Text style={st.resBody}>{res.summary}</Text>
      {Array.isArray(res.themes) && <View style={st.themeWrap}>{res.themes.map((t: string, i: number) => <View key={i} style={st.theme}><Text style={st.themeTxt}>{t}</Text></View>)}</View>}
      {Array.isArray(res.guidance) && res.guidance.map((g: string, i: number) => <Text key={i} style={st.guide}>• {g}</Text>)}
      {res.affirmation && <View style={st.affirm}><Text style={st.affirmTxt}>“{res.affirmation}”</Text></View>}
      <Text style={st.disc}>{r.disclaimer}</Text>
    </View>
  );
}

const st = StyleSheet.create({
  root: { flex: 1, backgroundColor: D.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 10 },
  back: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  hTitle: { color: D.text, fontSize: TFONT.xl, fontWeight: '900' },
  notice: { backgroundColor: 'rgba(251,191,36,0.10)', borderColor: 'rgba(251,191,36,0.22)', borderWidth: 1, borderRadius: 16, padding: 12 },
  noticeTxt: { color: '#fcd34d', fontSize: TFONT.xs, lineHeight: 17 },
  kindRow: { flexDirection: 'row', gap: 8 },
  kind: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 22, backgroundColor: D.elevated },
  kindActive: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 22 },
  kindTxt: { color: D.dim, fontSize: TFONT.sm, fontWeight: '800' },
  kindTxtA: { color: '#fff', fontSize: TFONT.sm, fontWeight: '800' },
  card: { backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 22, padding: 16 },
  lbl: { color: D.dim, fontSize: TFONT.xs, marginBottom: 6, marginTop: 4 },
  input: { backgroundColor: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11, color: D.text, fontSize: TFONT.sm, marginBottom: 8 },
  segRow: { flexDirection: 'row', gap: 8 },
  seg: { flex: 1, height: 40, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.05)', alignItems: 'center', justifyContent: 'center' },
  segA: { backgroundColor: D.accent2 },
  segTxt: { color: D.dim, fontSize: TFONT.sm, fontWeight: '800' },
  genBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 46, borderRadius: 23, marginTop: 14 },
  genTxt: { color: '#fff', fontWeight: '900', fontSize: TFONT.md },
  section: { color: D.dim, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 1, marginTop: 6 },
  histRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: D.elevated, borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 12 },
  histTitle: { color: D.text, fontSize: TFONT.sm, fontWeight: '800' },
  histSub: { color: D.dim, fontSize: TFONT.xs, textTransform: 'capitalize' },
  resLabel: { color: '#fcd34d', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  resHead: { color: D.text, fontSize: TFONT.xl, fontWeight: '900', marginTop: 4 },
  cardsWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginVertical: 10 },
  tcard: { backgroundColor: 'rgba(168,85,247,0.10)', borderColor: 'rgba(168,85,247,0.2)', borderWidth: 1, borderRadius: 12, paddingHorizontal: 10, paddingVertical: 6 },
  tcardName: { color: '#ddd6fe', fontSize: TFONT.xs, fontWeight: '800' },
  tcardMeta: { color: D.dim, fontSize: 10 },
  lifePath: { color: '#ddd6fe', fontSize: TFONT.sm, fontWeight: '800', marginVertical: 6 },
  resBody: { color: '#d6d3e8', fontSize: TFONT.sm, lineHeight: 21, marginTop: 6 },
  themeWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 10 },
  theme: { backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  themeTxt: { color: '#cbd5e1', fontSize: 11 },
  guide: { color: '#d6d3e8', fontSize: TFONT.sm, marginTop: 6 },
  affirm: { backgroundColor: 'rgba(168,85,247,0.10)', borderColor: 'rgba(168,85,247,0.2)', borderWidth: 1, borderRadius: 16, padding: 12, marginTop: 12 },
  affirmTxt: { color: '#ede9fe', fontSize: TFONT.sm, fontStyle: 'italic' },
  disc: { color: D.dim, fontSize: 11, marginTop: 10 },
});
