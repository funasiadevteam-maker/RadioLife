/* Companion Memory controls — mobile.
 * Opt-out toggle (ON by default) + per-category chips the listener can add to
 * or delete: favourite genres, favourite stations, disliked genres, languages
 * and interests. Fun AI honours these approved preferences in every voice
 * session. Self-hides for signed-out users (the memory API needs auth). */
import React, { useEffect, useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet, Switch, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';

const ACCENT = '#0E7490';

const CATS: { k: string; label: string; ph: string }[] = [
  { k: 'genres', label: 'Favourite genres', ph: 'e.g. Bollywood' },
  { k: 'stations', label: 'Favourite stations', ph: 'e.g. Big 106.2' },
  { k: 'disliked', label: 'Disliked genres', ph: 'e.g. Heavy metal' },
  { k: 'languages', label: 'Languages', ph: 'e.g. Hindi' },
  { k: 'interests', label: 'Interests', ph: 'e.g. Cricket' },
];

const slug = (s: string) => String(s).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '');

function AddRow({ kind, ph, onAdd }: { kind: string; ph: string; onAdd: (k: string, v: string) => void }) {
  const [val, setVal] = useState('');
  const submit = () => { const v = val.trim(); if (!v) return; onAdd(kind, v); setVal(''); };
  return (
    <View style={st.addRow}>
      <TextInput testID={`fai-memory-input-${kind}`} value={val} onChangeText={setVal}
        placeholder={ph} placeholderTextColor={COLORS.textMuted} maxLength={60}
        style={st.input} onSubmitEditing={submit} returnKeyType="done" />
      <TouchableOpacity testID={`fai-memory-add-${kind}`} style={st.addBtn} onPress={submit}>
        <Ionicons name="add" size={16} color="#fff" />
      </TouchableOpacity>
    </View>
  );
}

export default function FunAiMemory({ embedded = false }: { embedded?: boolean }) {
  const [mem, setMem] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get('/fun-ai/memory').then(({ data }) => setMem(data)).catch(() => setMem(null));
  }, []);

  if (mem === null) {
    return embedded ? null : (
      <View style={st.loading}><ActivityIndicator color={ACCENT} /></View>
    );
  }

  const toggle = async (next: boolean) => {
    setMem((m: any) => ({ ...m, enabled: next }));
    try { const { data } = await api.put('/fun-ai/memory', { enabled: next }); setMem(data); }
    catch { setMem((m: any) => ({ ...m, enabled: !next })); }
  };
  const addItem = async (kind: string, value: string) => {
    try { const { data } = await api.post('/fun-ai/memory', { kind, value }); setMem(data); } catch { /* noop */ }
  };
  const removeItem = async (kind: string, value: string) => {
    try { const { data } = await api.post('/fun-ai/memory/remove', { kind, value }); setMem(data); } catch { /* noop */ }
  };
  const clearAll = async () => {
    setBusy(true);
    try { const { data } = await api.post('/fun-ai/memory/clear', {}); setMem(data); }
    catch { /* noop */ } finally { setBusy(false); }
  };

  const total = CATS.reduce((n, c) => n + (mem[c.k]?.length || 0), 0);

  return (
    <View testID="fai-memory-panel" style={embedded ? st.embedded : st.card}>
      <View style={st.headerRow}>
        <View style={st.icon}><Ionicons name="sparkles" size={16} color={ACCENT} /></View>
        <View style={{ flex: 1 }}>
          <Text style={st.title}>Companion Memory</Text>
          <Text style={st.sub}>
            {mem.enabled ? (total ? `${total} saved — Fun AI remembers these` : 'On — add what Fun AI should remember')
                         : "Off — Fun AI won't use your saved preferences"}
          </Text>
        </View>
        <Switch testID="fai-memory-toggle" value={!!mem.enabled} onValueChange={toggle}
          trackColor={{ false: '#CBD5E1', true: ACCENT }} thumbColor="#fff" />
      </View>

      <View style={{ opacity: mem.enabled ? 1 : 0.5, marginTop: SPACING.md }}
        pointerEvents={mem.enabled ? 'auto' : 'none'}>
        {CATS.map((cat) => (
          <View key={cat.k} style={{ marginBottom: SPACING.md }}>
            <Text style={st.catLabel}>{cat.label.toUpperCase()}</Text>
            <View style={st.chipWrap}>
              {(mem[cat.k] || []).length === 0 && <Text style={st.emptyTxt}>Nothing saved yet</Text>}
              {(mem[cat.k] || []).map((v: string) => (
                <View key={v} testID={`fai-memory-chip-${cat.k}-${slug(v)}`} style={st.chip}>
                  <Text style={st.chipText}>{v}</Text>
                  <TouchableOpacity testID={`fai-memory-remove-${cat.k}-${slug(v)}`}
                    onPress={() => removeItem(cat.k, v)} hitSlop={8}>
                    <Ionicons name="close" size={14} color={COLORS.textDim} />
                  </TouchableOpacity>
                </View>
              ))}
            </View>
            <AddRow kind={cat.k} ph={cat.ph} onAdd={addItem} />
          </View>
        ))}

        {total > 0 && (
          <TouchableOpacity testID="fai-memory-clear" style={st.clearBtn} onPress={clearAll} disabled={busy}>
            {busy ? <ActivityIndicator size="small" color={COLORS.red} /> : (
              <><Ionicons name="trash-outline" size={14} color={COLORS.red} />
                <Text style={st.clearText}>Clear everything Fun AI remembers</Text></>
            )}
          </TouchableOpacity>
        )}
      </View>
    </View>
  );
}

const st = StyleSheet.create({
  loading: { padding: SPACING.lg, alignItems: 'center' },
  card: {
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    borderRadius: RADIUS.lg, padding: SPACING.lg,
  },
  embedded: {
    backgroundColor: 'rgba(14,116,144,0.04)', borderWidth: 1, borderColor: COLORS.cardBorder,
    borderRadius: RADIUS.lg, padding: SPACING.md, marginTop: SPACING.lg,
  },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm },
  icon: {
    width: 32, height: 32, borderRadius: 9, alignItems: 'center', justifyContent: 'center',
    backgroundColor: 'rgba(14,116,144,0.12)',
  },
  title: { color: COLORS.text, fontSize: FONT.md, fontWeight: '800' },
  sub: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  catLabel: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1, marginBottom: 6 },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  emptyTxt: { color: COLORS.textMuted, fontSize: FONT.xs, fontStyle: 'italic' },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.card,
    borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: 999,
    paddingHorizontal: 12, paddingVertical: 7,
  },
  chipText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '600' },
  addRow: { flexDirection: 'row', gap: 6, marginTop: 8 },
  input: {
    flex: 1, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 9, color: COLORS.text, fontSize: FONT.sm,
  },
  addBtn: { backgroundColor: ACCENT, borderRadius: RADIUS.md, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center' },
  clearBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, alignSelf: 'flex-start',
    borderWidth: 1, borderColor: 'rgba(225,29,72,0.4)', borderRadius: RADIUS.md,
    paddingHorizontal: 14, paddingVertical: 10,
  },
  clearText: { color: COLORS.red, fontSize: FONT.xs, fontWeight: '700' },
});
