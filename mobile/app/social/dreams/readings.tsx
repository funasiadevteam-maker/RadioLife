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
  { key: 'numerology', label: 'Numbers', icon: 'star' },
  { key: 'match', label: 'Match', icon: 'heart' },
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
        <DailyCard />
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

        {kind === 'match' ? <CompatPanel /> : (<>
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

function DailyCard() {
  const [d, setD] = useState<any>(null);
  const [rem, setRem] = useState<any>({ enabled: false, hour: 9 });
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<any>(null);
  const [dl, setDl] = useState(false);
  useEffect(() => {
    api.get('/social/readings/daily').then(({ data }) => setD(data)).catch(() => {});
    api.get('/social/readings/reminders').then(({ data }) => setRem(data)).catch(() => {});
  }, []);
  const toggle = async () => {
    const n = { enabled: !rem.enabled, hour: rem.hour }; setRem(n);
    try { await api.put('/social/readings/reminders', n); } catch (_) {}
  };
  const openDetail = async () => {
    setOpen(true);
    if (!detail) {
      setDl(true);
      try { const { data } = await api.post('/social/readings/daily/detail'); setDetail(data.detail); } catch (_) {} finally { setDl(false); }
    }
  };
  if (!d) return null;
  return (
    <LinearGradient colors={['#1e1b4b', '#4c1d95']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.daily}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="sparkles" size={15} color={D.gold} />
        <Text style={st.dailyTitle}>Today’s reading</Text>
        <Pressable testID="daily-reminder-toggle" onPress={toggle} style={[st.remBtn, rem.enabled && st.remBtnOn]}>
          <Ionicons name="notifications" size={12} color={rem.enabled ? '#a7f3d0' : D.dim} />
          <Text style={[st.remTxt, rem.enabled && { color: '#a7f3d0' }]}>{rem.enabled ? 'Nudge on' : 'Remind me'}</Text>
        </Pressable>
      </View>
      <Text style={st.dailyHead}>{d.basic?.headline}</Text>
      <Text style={st.dailySum}>{d.basic?.summary}</Text>
      <View style={st.dailyChips}>
        <View style={st.dailyChip} testID="daily-card-name"><Text style={st.dailyChipTxt}>🃏 {d.card?.name} · {d.card?.orientation}</Text></View>
        {d.sign && <View style={st.dailyChip}><Text style={st.dailyChipTxt}>{d.sign}</Text></View>}
      </View>
      <Pressable testID={d.detail_locked ? 'daily-unlock' : 'daily-detail'} onPress={openDetail} style={st.dailyBtn}>
        {d.detail_locked
          ? <><Ionicons name="lock-closed" size={14} color={D.gold} /><Text style={st.dailyBtnTxt}>Unlock full daily tarot — Premium</Text></>
          : <><Text style={st.dailyBtnTxt}>Read full daily tarot</Text><Ionicons name="chevron-forward" size={15} color="#fff" /></>}
      </Pressable>
      <Modal visible={open} transparent animationType="slide" onRequestClose={() => setOpen(false)}>
        <View style={st.modalWrap}><View style={st.modalCard} testID="daily-modal">
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <Text style={st.modalTitle}>Your daily tarot</Text>
            <Pressable onPress={() => setOpen(false)}><Ionicons name="close" size={20} color={D.text} /></Pressable>
          </View>
          {d.detail_locked
            ? <View style={{ alignItems: 'center', paddingVertical: 8 }} testID="daily-premium-gate"><Ionicons name="lock-closed" size={26} color={D.gold} /><Text style={st.gateTitle}>Premium daily tarot</Text><Text style={st.gateSub}>{d.upgrade}</Text></View>
            : dl ? <ActivityIndicator color={D.violet} style={{ marginVertical: 24 }} />
            : <ReadingResult r={{ ...d, title: 'Daily tarot', result: detail, cards: [{ name: d.card?.name, orientation: d.card?.orientation, position: 'Today' }] }} />}
        </View></View>
      </Modal>
    </LinearGradient>
  );
}

function CompatPanel() {
  const [cands, setCands] = useState<any[]>([]);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState<any>(null);
  useEffect(() => { api.get('/social/compatibility/candidates').then(({ data }) => setCands(data.items || [])).catch(() => {}); }, []);
  const run = async (uid: string) => {
    setBusy(true); setRes(null);
    try { const { data } = await api.post('/social/compatibility', { target_user_id: uid }); setRes(data); } catch (_) {} finally { setBusy(false); }
  };
  return (
    <View testID="compat-panel">
      <View style={st.card}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 4 }}><Ionicons name="heart" size={15} color="#fb7185" /><Text style={st.dailyTitle}>Dream compatibility</Text></View>
        <Text style={st.compatNote}>A playful match from your shared dream themes & star signs — just for fun.</Text>
        {cands.length === 0
          ? <Text style={st.compatEmpty}>Add a friend first — Match works with your friends list.</Text>
          : cands.map((c) => (
            <Pressable key={c.user_id} testID={`compat-friend-${c.user_id}`} onPress={() => run(c.user_id)} disabled={busy} style={st.friendRow}>
              <View style={st.friendAv}><Text style={st.friendAvTxt}>{(c.name || '?')[0]}</Text></View>
              <Text style={st.friendName}>{c.name}</Text>
              <Ionicons name="heart" size={16} color="#fb7185" />
            </Pressable>
          ))}
      </View>
      {busy && <ActivityIndicator color={D.violet} style={{ marginTop: 20 }} />}
      {res && (
        <LinearGradient colors={['#4c1d95', '#be185d']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.compatRes} testID="compat-result">
          <Text style={st.compatLabel}>{res.label}</Text>
          <Text style={st.compatScore}>{res.score}%</Text>
          <Text style={st.compatHead}>{res.headline}</Text>
          <Text style={st.compatBlurb}>{res.blurb}</Text>
          {res.shared_themes?.length > 0 && <View style={[st.themeWrap, { justifyContent: 'center' }]}>{res.shared_themes.map((t: string, i: number) => <View key={i} style={st.compatTheme}><Text style={st.compatThemeTxt}>{t}</Text></View>)}</View>}
          <Text style={st.compatShared}>{res.shared_note}</Text>
          <Text style={[st.disc, { textAlign: 'center' }]}>{res.disclaimer}</Text>
        </LinearGradient>
      )}
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
  daily: { borderRadius: 22, padding: 16, borderColor: 'rgba(168,85,247,0.25)', borderWidth: 1 },
  dailyTitle: { color: '#fff', fontSize: TFONT.md, fontWeight: '900' },
  remBtn: { marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, height: 30, borderRadius: 15, backgroundColor: 'rgba(255,255,255,0.08)' },
  remBtnOn: { backgroundColor: 'rgba(16,185,129,0.2)' },
  remTxt: { color: D.dim, fontSize: 11, fontWeight: '800' },
  dailyHead: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900', marginTop: 8 },
  dailySum: { color: '#ddd6fe', fontSize: TFONT.sm, lineHeight: 20, marginTop: 4 },
  dailyChips: { flexDirection: 'row', gap: 8, marginTop: 10, flexWrap: 'wrap' },
  dailyChip: { backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 5 },
  dailyChipTxt: { color: '#ede9fe', fontSize: 11, fontWeight: '700' },
  dailyBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, height: 44, borderRadius: 22, marginTop: 12, backgroundColor: 'rgba(255,255,255,0.1)', borderColor: 'rgba(251,191,36,0.3)', borderWidth: 1 },
  dailyBtnTxt: { color: '#fff', fontWeight: '800', fontSize: TFONT.sm },
  modalWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.7)' },
  modalCard: { backgroundColor: '#0d0a24', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '85%', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1 },
  modalTitle: { color: D.text, fontSize: TFONT.lg, fontWeight: '900' },
  gateTitle: { color: D.text, fontSize: TFONT.md, fontWeight: '900', marginTop: 8 },
  gateSub: { color: D.dim, fontSize: TFONT.sm, textAlign: 'center', marginTop: 4 },
  compatNote: { color: D.dim, fontSize: 11, marginBottom: 10 },
  compatEmpty: { color: D.dim, fontSize: TFONT.sm, paddingVertical: 12, textAlign: 'center' },
  friendRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: 'rgba(255,255,255,0.04)', borderColor: 'rgba(255,255,255,0.06)', borderWidth: 1, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 11, marginBottom: 8 },
  friendAv: { width: 36, height: 36, borderRadius: 18, backgroundColor: 'rgba(168,85,247,0.2)', alignItems: 'center', justifyContent: 'center' },
  friendAvTxt: { color: '#ddd6fe', fontWeight: '900' },
  friendName: { flex: 1, color: D.text, fontSize: TFONT.sm, fontWeight: '800' },
  compatRes: { borderRadius: 22, padding: 18, alignItems: 'center', marginTop: 4, borderColor: 'rgba(244,114,182,0.25)', borderWidth: 1 },
  compatLabel: { color: '#fcd34d', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  compatScore: { color: '#fff', fontSize: 44, fontWeight: '900', marginVertical: 2 },
  compatHead: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900', textAlign: 'center' },
  compatBlurb: { color: '#fce7f3', fontSize: TFONT.sm, lineHeight: 20, textAlign: 'center', marginTop: 6 },
  compatTheme: { backgroundColor: 'rgba(255,255,255,0.12)', borderRadius: 12, paddingHorizontal: 10, paddingVertical: 4 },
  compatThemeTxt: { color: '#fff', fontSize: 11, fontWeight: '700' },
  compatShared: { color: '#fbcfe8', fontSize: 11, textAlign: 'center', marginTop: 10 },
});
