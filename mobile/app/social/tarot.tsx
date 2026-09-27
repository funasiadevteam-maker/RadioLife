// FUUSIC Social V2 — Mobile Tarot (its own category, separate from Dreams).
import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';
import api from '../../src/api/client';

const INTENTS = [
  { key: 'general', label: 'General Reflection', q: '' },
  { key: 'love', label: 'Love', q: 'What should I know about my love life right now?' },
  { key: 'career', label: 'Career', q: 'What guidance is there for my career path?' },
  { key: 'custom', label: 'Custom', q: null },
];

export default function TarotScreen() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [spread, setSpread] = useState('three');
  const [intent, setIntent] = useState('general');
  const [question, setQuestion] = useState('');
  const [drawing, setDrawing] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [saved, setSaved] = useState<any[]>([]);
  const [sharing, setSharing] = useState(false);

  const loadSaved = useCallback(async () => {
    try { const r = await api.get('/social/readings', { params: { kind: 'tarot' } }); setSaved(r.data.items || []); }
    catch (_) {}
  }, []);
  useEffect(() => { loadSaved(); }, [loadSaved]);

  const draw = async () => {
    setDrawing(true); setResult(null);
    const q = intent === 'custom' ? question.trim() : (INTENTS.find((i) => i.key === intent)?.q || '');
    try { const r = await api.post('/social/readings/tarot', { spread, question: q }); setResult(r.data); loadSaved(); }
    catch (_) {} finally { setDrawing(false); }
  };

  const share = async () => {
    if (!result?.reading_id) return;
    setSharing(true);
    try { await api.post(`/social/readings/${result.reading_id}/share`, { public: true }); setResult((r: any) => ({ ...r, public: true })); }
    catch (_) {} finally { setSharing(false); }
  };

  const resultText = typeof result?.result === 'string' ? result.result : (result?.result?.reading || result?.result?.text || '');

  return (
    <View style={s.screen} testID="social-tarot">
      <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingTop: insets.top + 10, paddingBottom: 130, gap: 16 }}
        showsVerticalScrollIndicator={false}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
          <Pressable onPress={() => router.back()} testID="tarot-back"><Ionicons name="chevron-back" size={24} color={TUBE.text} /></Pressable>
          <Text style={{ fontSize: 30 }}>🃏</Text>
          <View>
            <Text style={s.title}>Tarot</Text>
            <Text style={s.sub}>Draw a card, reflect — entertainment only.</Text>
          </View>
        </View>

        <LinearGradient colors={['#1e1b4b', '#3b0764']} style={s.panel}>
          <Text style={s.label}>CHOOSE A SPREAD</Text>
          <View style={{ flexDirection: 'row', gap: 8, marginBottom: 14 }}>
            {[['one', '1 Card'], ['three', '3 Card']].map(([k, l]) => (
              <Pressable key={k} onPress={() => setSpread(k)} testID={`tarot-spread-${k}`}>
                {spread === k ? (
                  <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={s.pill}>
                    <Text style={s.pillActive}>{l}</Text>
                  </LinearGradient>
                ) : <View style={[s.pill, s.pillIdle]}><Text style={s.pillIdleTxt}>{l}</Text></View>}
              </Pressable>
            ))}
          </View>
          <Text style={s.label}>FOCUS</Text>
          <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
            {INTENTS.map((i) => (
              <Pressable key={i.key} onPress={() => setIntent(i.key)} testID={`tarot-intent-${i.key}`}
                style={[s.intent, intent === i.key && s.intentActive]}>
                <Text style={[s.intentTxt, intent === i.key && { color: '#fff' }]}>{i.label}</Text>
              </Pressable>
            ))}
          </View>
          {intent === 'custom' && (
            <TextInput value={question} onChangeText={setQuestion} placeholder="Ask your question…"
              placeholderTextColor={TUBE.textMuted} style={s.qInput} testID="tarot-question" />
          )}
          <Pressable onPress={draw} disabled={drawing} testID="tarot-draw">
            <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={s.draw}>
              {drawing ? <ActivityIndicator color="#fff" /> : <><Ionicons name="sparkles" size={16} color="#fff" /><Text style={s.drawTxt}>Draw cards</Text></>}
            </LinearGradient>
          </Pressable>
        </LinearGradient>

        {result && (
          <View style={s.result} testID="tarot-result">
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10, marginBottom: 12 }}>
              {(result.cards || []).map((c: any, i: number) => (
                <LinearGradient key={i} colors={['#2e1065', '#4c1d95']} style={s.tcard}>
                  <Text style={{ fontSize: 26, marginBottom: 4 }}>🃏</Text>
                  <Text style={s.tpos}>{c.position}</Text>
                  <Text style={s.tname}>{c.name}</Text>
                  <Text style={s.torient}>{c.orientation}</Text>
                </LinearGradient>
              ))}
            </ScrollView>
            <Text style={s.resultTxt}>{resultText}</Text>
            {result.disclaimer ? <Text style={s.disclaimer}>{result.disclaimer}</Text> : null}
            <Pressable onPress={share} disabled={sharing || result.public} testID="tarot-share">
              <View style={[s.share, result.public && { backgroundColor: 'rgba(255,255,255,0.12)' }]}>
                {result.public
                  ? <><Ionicons name="checkmark" size={16} color="#fff" /><Text style={s.shareTxt}>Shared to Social</Text></>
                  : <><Ionicons name="share-social" size={16} color="#fff" /><Text style={s.shareTxt}>Share to Social</Text></>}
              </View>
            </Pressable>
          </View>
        )}

        {saved.length > 0 && (
          <View>
            <Text style={s.savedTitle}>SAVED READINGS</Text>
            <View style={{ gap: 8 }} testID="tarot-saved">
              {saved.map((r) => (
                <View key={r.reading_id} style={s.savedRow}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.savedName}>{r.title || 'Tarot reading'}</Text>
                    <Text style={s.savedSub} numberOfLines={1}>{r.subject}</Text>
                  </View>
                  {r.public && <Text style={s.sharedBadge}>SHARED</Text>}
                </View>
              ))}
            </View>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#0d0a24' },
  title: { color: TUBE.text, fontSize: TFONT.xl, fontWeight: '900' },
  sub: { color: TUBE.textMuted, fontSize: TFONT.xs },
  panel: { borderRadius: 24, padding: 18, borderWidth: 1, borderColor: 'rgba(255,255,255,0.1)' },
  label: { color: '#c4b5fd', fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginBottom: 8 },
  pill: { height: 40, paddingHorizontal: 16, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  pillIdle: { backgroundColor: 'rgba(255,255,255,0.06)' },
  pillActive: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  pillIdleTxt: { color: '#cbd5e1', fontSize: TFONT.sm, fontWeight: '800' },
  intent: { height: 36, paddingHorizontal: 14, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.06)', alignItems: 'center', justifyContent: 'center' },
  intentActive: { backgroundColor: 'rgba(255,255,255,0.2)' },
  intentTxt: { color: '#cbd5e1', fontSize: TFONT.xs, fontWeight: '800' },
  qInput: { backgroundColor: 'rgba(255,255,255,0.06)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderRadius: 16, paddingHorizontal: 14, paddingVertical: 12, color: TUBE.text, fontSize: TFONT.sm, marginBottom: 10 },
  draw: { height: 48, borderRadius: 24, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  drawTxt: { color: '#fff', fontSize: TFONT.md, fontWeight: '900' },
  result: { backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: TUBE.line, borderRadius: 24, padding: 18 },
  tcard: { width: 112, borderRadius: 16, padding: 12, alignItems: 'center', borderWidth: 1, borderColor: 'rgba(167,139,250,0.3)' },
  tpos: { color: '#c4b5fd', fontSize: 10, letterSpacing: 1, textTransform: 'uppercase' },
  tname: { color: '#fff', fontSize: TFONT.xs, fontWeight: '900', marginTop: 2, textAlign: 'center' },
  torient: { color: TUBE.textMuted, fontSize: 10, textTransform: 'capitalize' },
  resultTxt: { color: '#e2e8f0', fontSize: TFONT.sm, lineHeight: 20 },
  disclaimer: { color: TUBE.textMuted, fontSize: 11, marginTop: 10 },
  share: { flexDirection: 'row', alignItems: 'center', gap: 8, height: 42, paddingHorizontal: 18, borderRadius: 21, alignSelf: 'flex-start', marginTop: 14, backgroundColor: TUBE.magenta },
  shareTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '800' },
  savedTitle: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginBottom: 10 },
  savedRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: 'rgba(255,255,255,0.03)', borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 14 },
  savedName: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  savedSub: { color: TUBE.textMuted, fontSize: TFONT.xs, marginTop: 1 },
  sharedBadge: { color: TUBE.electric, fontSize: 10, fontWeight: '900' },
});
