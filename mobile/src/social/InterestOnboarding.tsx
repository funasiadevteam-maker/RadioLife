// First-run interest onboarding (mobile) — a skippable "Pick a few interests"
// sheet that auto-opens ONCE for brand-new users right after their first
// sign-up, so their first rail suggestions are personalized. Reuses the shared
// GET/PUT /api/social/interests + POST /interests/skip. Renders only when
// needs_onboarding=true.
import React, { useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, Modal, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { TSPACE, TRADIUS, TFONT } from '../constants/tube';
import { activeTokens } from '../theme/ThemeProvider';
import type { ThemeTokens } from '../theme/tokens';
import api from '../api/client';

export default function InterestOnboarding() {
  const t = activeTokens;
  const s = makeStyles(t);
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const [topics, setTopics] = useState<any[]>([]);
  const [sel, setSel] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancel = false;
    api.get('/social/interests')
      .then(({ data }) => {
        if (cancel) return;
        if (data?.needs_onboarding) {
          setTopics(data?.topics || []);
          setSel(data?.selected || []);
          setOpen(true);
        }
      })
      .catch(() => {});
    return () => { cancel = true; };
  }, []);

  const toggle = (id: string) =>
    setSel((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  const save = async () => {
    setBusy(true);
    try { await api.put('/social/interests', { interests: sel }); }
    catch (_) {} finally { setBusy(false); setOpen(false); }
  };

  const skip = async () => {
    setBusy(true);
    try { await api.post('/social/interests/skip', {}); }
    catch (_) {} finally { setBusy(false); setOpen(false); }
  };

  return (
    <Modal visible={open} transparent animationType="slide" onRequestClose={skip}>
      <View style={s.backdrop} testID="interest-onboarding">
        <View style={[s.sheet, { paddingBottom: insets.bottom + TSPACE.lg }]}>
          <View style={s.eyebrowRow}>
            <Ionicons name="sparkles" size={13} color={t.magenta} />
            <Text style={s.eyebrow}>WELCOME TO FUUSIC</Text>
          </View>
          <Text style={s.title}>Pick a few interests</Text>
          <Text style={s.sub}>
            We'll personalize your feed and rail with creators and shows you'll love.
            You can change this anytime.
          </Text>

          <ScrollView style={{ maxHeight: 220 }} showsVerticalScrollIndicator={false}>
            <View style={s.chips}>
              {topics.map((t) => {
                const on = sel.includes(t.id);
                return (
                  <Pressable key={t.id} onPress={() => toggle(t.id)}
                    testID={`onboarding-interest-${t.id}`}
                    style={[s.chip, on && s.chipOn]}>
                    {on && <Ionicons name="checkmark" size={14} color="#fff" />}
                    <Text style={[s.chipText, on && s.chipTextOn]}>{t.label}</Text>
                  </Pressable>
                );
              })}
            </View>
          </ScrollView>

          <View style={s.actions}>
            <Pressable onPress={skip} disabled={busy} testID="onboarding-skip"
              style={s.skipBtn}>
              <Text style={s.skipText}>Skip for now</Text>
            </Pressable>
            <Pressable onPress={save} disabled={busy || sel.length === 0}
              testID="onboarding-save" style={{ flex: 1, opacity: busy || sel.length === 0 ? 0.5 : 1 }}>
              <LinearGradient colors={[t.magenta, t.pink]}
                start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.saveBtn}>
                {busy
                  ? <ActivityIndicator color="#fff" />
                  : <Text style={s.saveText}>
                      Personalize my feed{sel.length ? ` (${sel.length})` : ''}
                    </Text>}
              </LinearGradient>
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', justifyContent: 'flex-end' },
  sheet: {
    backgroundColor: t.elevated, borderTopLeftRadius: TRADIUS.xl,
    borderTopRightRadius: TRADIUS.xl, borderWidth: 1, borderColor: t.line,
    paddingHorizontal: TSPACE.lg, paddingTop: TSPACE.lg,
  },
  eyebrowRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  eyebrow: { color: t.magenta, fontSize: 10, fontWeight: '900', letterSpacing: 1.5 },
  title: { color: t.text, fontSize: TFONT.xxl, fontWeight: '900', marginTop: 4 },
  sub: { color: t.textDim, fontSize: TFONT.sm, marginTop: 4, marginBottom: TSPACE.md, lineHeight: 18 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    flexDirection: 'row', alignItems: 'center', gap: 6, height: 40,
    paddingHorizontal: 16, borderRadius: TRADIUS.full, borderWidth: 1,
    borderColor: t.lineStrong, backgroundColor: t.glass,
  },
  chipOn: { backgroundColor: t.magenta, borderColor: 'transparent' },
  chipText: { color: t.textDim, fontWeight: '700', fontSize: TFONT.sm },
  chipTextOn: { color: '#fff' },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: TSPACE.lg },
  skipBtn: {
    height: 46, paddingHorizontal: 18, borderRadius: TRADIUS.full, borderWidth: 1,
    borderColor: t.lineStrong, alignItems: 'center', justifyContent: 'center',
  },
  skipText: { color: t.textDim, fontWeight: '700', fontSize: TFONT.sm },
  saveBtn: { height: 46, borderRadius: TRADIUS.full, alignItems: 'center', justifyContent: 'center' },
  saveText: { color: '#fff', fontWeight: '900', fontSize: TFONT.md },
});
