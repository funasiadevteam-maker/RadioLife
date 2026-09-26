// Bar Skin Editor (mobile) — owner themes the wheel: accent colours, logo URL,
// signature-drink prizes. PUT /api/bar-games/{id}/skin (owner/admin only).
import React, { useCallback, useState } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView, TextInput, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useRouter, useLocalSearchParams, useFocusEffect, Stack } from 'expo-router';
import api from '../../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../../src/constants/theme';

const SWATCHES = ['#22d3ee', '#a855f7', '#ec4899', '#f59e0b', '#34d399', '#f472b6', '#3b82f6', '#ef4444'];

export default function BarSkinEditor() {
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id: string }>();
  const [accent, setAccent] = useState('#22d3ee');
  const [accent2, setAccent2] = useState('#f472b6');
  const [logo, setLogo] = useState('');
  const [segments, setSegments] = useState<any[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/bar-games/${id}`);
      const t = data.config?.theme || {};
      setAccent(t.accent || '#22d3ee'); setAccent2(t.accent2 || '#f472b6'); setLogo(t.logo_url || '');
      setSegments((data.config?.segments || []).map((x: any) => ({ label: x.label, emoji: x.emoji, win: x.win, weight: x.weight || 8 })));
    } catch (_) {} finally { setLoaded(true); }
  }, [id]);
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const update = (i: number, patch: any) => setSegments((l) => l.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const addSeg = () => setSegments((l) => [...l, { label: 'New prize', emoji: '🍹', win: true, weight: 8 }]);
  const delSeg = (i: number) => setSegments((l) => l.filter((_, j) => j !== i));

  const save = async () => {
    if (segments.length < 3) return;
    setBusy(true);
    try {
      await api.put(`/bar-games/${id}/skin`, { accent, accent2, logo_url: logo || null, segments });
      router.back();
    } catch (_) {} finally { setBusy(false); }
  };

  const Swatches = ({ value, onPick }: any) => (
    <View style={s.swatchRow}>
      {SWATCHES.map((c) => (
        <TouchableOpacity key={c} onPress={() => onPick(c)} style={[s.swatch, { backgroundColor: c }, value === c && s.swatchOn]} />
      ))}
    </View>
  );

  return (
    <SafeAreaView style={s.screen} testID="bar-skin-screen">
      <Stack.Screen options={{ headerShown: false }} />
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.back} testID="skin-back"><Ionicons name="chevron-back" size={22} color={COLORS.text} /></TouchableOpacity>
        <Text style={s.hTitle}>Customize your wheel</Text>
      </View>

      {!loaded ? <ActivityIndicator color={COLORS.primary} style={{ marginTop: 40 }} /> : (
        <ScrollView contentContainerStyle={{ padding: SPACING.md, gap: 16, paddingBottom: 40 }}>
          <View style={[s.preview, { borderColor: accent }]}>
            <View style={{ flexDirection: 'row', gap: 8 }}>
              <View style={[s.dot, { backgroundColor: accent }]} />
              <View style={[s.dot, { backgroundColor: accent2 }]} />
            </View>
            <Text style={s.previewTxt}>Live preview</Text>
          </View>

          <View>
            <Text style={s.lbl}>Accent</Text>
            <Swatches value={accent} onPick={setAccent} />
          </View>
          <View>
            <Text style={s.lbl}>Accent 2</Text>
            <Swatches value={accent2} onPick={setAccent2} />
          </View>

          <View>
            <Text style={s.lbl}>Logo URL (optional)</Text>
            <TextInput value={logo} onChangeText={setLogo} placeholder="https://…" placeholderTextColor={COLORS.textMuted}
              style={s.input} autoCapitalize="none" testID="skin-logo" />
          </View>

          <Text style={s.lbl}>Prizes ({segments.length})</Text>
          {segments.map((sg, i) => (
            <View key={i} style={s.segRow} testID={`skin-seg-${i}`}>
              <TextInput value={sg.emoji} onChangeText={(v) => update(i, { emoji: v })} maxLength={4} style={s.emoji} />
              <TextInput value={sg.label} onChangeText={(v) => update(i, { label: v })} style={s.segLabel} />
              <TouchableOpacity onPress={() => update(i, { win: !sg.win })} style={[s.winTag, { backgroundColor: sg.win ? 'rgba(22,163,74,0.15)' : COLORS.inputBg }]}>
                <Text style={{ color: sg.win ? COLORS.green : COLORS.textMuted, fontWeight: '900', fontSize: 10 }}>{sg.win ? 'WIN' : 'LOSE'}</Text>
              </TouchableOpacity>
              <TouchableOpacity onPress={() => delSeg(i)}><Ionicons name="trash-outline" size={18} color={COLORS.textMuted} /></TouchableOpacity>
            </View>
          ))}
          <TouchableOpacity onPress={addSeg} style={s.addBtn} testID="skin-add-seg">
            <Ionicons name="add" size={16} color={COLORS.text} /><Text style={s.addTxt}>Add prize</Text>
          </TouchableOpacity>

          <TouchableOpacity onPress={save} disabled={busy} style={[s.save, { backgroundColor: accent }]} testID="bar-skin-save">
            {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.saveTxt}>Save wheel</Text>}
          </TouchableOpacity>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: SPACING.md, paddingTop: SPACING.sm, paddingBottom: SPACING.sm },
  back: { width: 38, height: 38, borderRadius: 19, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.cardBorder },
  hTitle: { color: COLORS.text, fontSize: FONT.xl, fontWeight: '900' },
  preview: { borderWidth: 2, borderRadius: RADIUS.lg, padding: 16, alignItems: 'center', gap: 8, backgroundColor: COLORS.card },
  dot: { width: 26, height: 26, borderRadius: 13 },
  previewTxt: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  lbl: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '900', marginBottom: 8 },
  swatchRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  swatch: { width: 34, height: 34, borderRadius: 17, borderWidth: 2, borderColor: 'transparent' },
  swatchOn: { borderColor: COLORS.text },
  input: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.inputBorder, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.sm },
  segRow: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.card, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, padding: 8 },
  emoji: { width: 40, textAlign: 'center', backgroundColor: COLORS.inputBg, borderRadius: 8, paddingVertical: 8, fontSize: 16 },
  segLabel: { flex: 1, minWidth: 0, backgroundColor: COLORS.inputBg, borderRadius: 8, paddingHorizontal: 10, paddingVertical: 8, color: COLORS.text, fontSize: FONT.sm },
  winTag: { paddingHorizontal: 8, paddingVertical: 6, borderRadius: 8 },
  addBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', paddingHorizontal: 14, height: 38, borderRadius: 19, backgroundColor: COLORS.inputBg },
  addTxt: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800' },
  save: { height: 50, borderRadius: 25, alignItems: 'center', justifyContent: 'center', marginTop: 8 },
  saveTxt: { color: '#fff', fontSize: FONT.md, fontWeight: '900' },
});
