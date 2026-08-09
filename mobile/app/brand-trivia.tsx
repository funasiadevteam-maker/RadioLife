// Phase MKT.1 — Consumer Brand Trivia (mobile): answer sponsored trivia, earn points.
import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  ActivityIndicator, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import { useReward } from '../src/components/RewardOverlay';

interface Q { index: number; q: string; choices: string[]; answered: boolean }
interface Camp { campaign_id: string; sponsor_name?: string; title: string; reward_points: number; questions: Q[] }

export default function BrandTrivia() {
  const router = useRouter();
  const { celebrate } = useReward();
  const [items, setItems] = useState<Camp[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // result[campaign:index] = { correct, answer_index }
  const [result, setResult] = useState<Record<string, { correct: boolean; answer_index: number }>>({});
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const r = await api.get('/brand-trivia/active'); setItems(r.data.items || []); }
    catch { /* unauth */ }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const answer = async (c: Camp, qi: number, ci: number) => {
    const key = `${c.campaign_id}:${qi}`;
    if (busy || result[key]) return;
    setBusy(key);
    try {
      const r = await api.post(`/brand-trivia/${c.campaign_id}/answer`,
        { question_index: qi, choice_index: ci });
      setResult((p) => ({ ...p, [key]: { correct: r.data.correct, answer_index: r.data.answer_index } }));
      if (r.data.correct && r.data.awarded > 0) {
        celebrate({ points: r.data.awarded, title: 'Correct!' });
      }
      await load();
    } catch { /* already answered */ }
    finally { setBusy(null); }
  };

  if (loading) {
    return <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={common.screen}>
      <View style={s.topbar}>
        <TouchableOpacity onPress={() => router.back()} testID="bt-back" style={{ padding: 2 }}>
          <Ionicons name="chevron-back" size={22} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.topTitle}>Brand Trivia</Text>
        <View style={{ width: 22 }} />
      </View>

      <ScrollView contentContainerStyle={{ padding: SPACING.md, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} tintColor={COLORS.primary}
          onRefresh={() => { setRefreshing(true); load(); }} />}
        testID="brand-trivia-root">

        <Text style={s.intro}>Answer sponsored trivia to earn points instantly.</Text>

        {items.length === 0 && (
          <View style={s.card}>
            <Ionicons name="help-circle-outline" size={28} color={COLORS.textMuted} />
            <Text style={s.empty}>No trivia rounds live right now.</Text>
            <Text style={s.dim}>Check back soon — brands add new rounds often.</Text>
          </View>
        )}

        {items.map((c) => (
          <View key={c.campaign_id} style={s.card} testID={`bt-campaign-${c.campaign_id}`}>
            <View style={s.head}>
              <View style={{ flex: 1, minWidth: 0 }}>
                <Text style={s.title} numberOfLines={1}>{c.title}</Text>
                {!!c.sponsor_name && <Text style={s.sponsor}>by {c.sponsor_name}</Text>}
              </View>
              <View style={s.ptsTag}>
                <Ionicons name="cash" size={13} color={COLORS.gold} />
                <Text style={s.ptsText}>+{c.reward_points}</Text>
              </View>
            </View>

            {c.questions.map((qq) => {
              const key = `${c.campaign_id}:${qq.index}`;
              const res = result[key];
              const done = qq.answered || !!res;
              return (
                <View key={qq.index} style={s.qBlock}>
                  <Text style={s.qText}>{qq.q}</Text>
                  {qq.choices.map((ch, ci) => {
                    const isCorrect = res && res.answer_index === ci;
                    const isWrongPick = res && !res.correct && res.answer_index !== ci;
                    return (
                      <TouchableOpacity key={ci} testID={`bt-choice-${c.campaign_id}-${qq.index}-${ci}`}
                        disabled={done}
                        style={[s.choice, isCorrect && s.choiceCorrect, isWrongPick && done && s.choiceDim]}
                        onPress={() => answer(c, qq.index, ci)}>
                        <Text style={[s.choiceText, isCorrect && { color: COLORS.green, fontWeight: '800' }]}>
                          {ch}
                        </Text>
                        {busy === key
                          ? <ActivityIndicator size="small" color={COLORS.primary} />
                          : isCorrect ? <Ionicons name="checkmark-circle" size={18} color={COLORS.green} />
                          : done && qq.answered ? <Ionicons name="checkmark" size={16} color={COLORS.textMuted} />
                          : null}
                      </TouchableOpacity>
                    );
                  })}
                  {done && <Text style={s.doneNote}>Answered</Text>}
                </View>
              );
            })}
          </View>
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  topbar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder, backgroundColor: COLORS.bg,
  },
  topTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  intro: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md, alignItems: 'stretch' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: SPACING.sm },
  title: { color: COLORS.text, fontSize: FONT.md, fontWeight: '900' },
  sponsor: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 1 },
  ptsTag: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: COLORS.gold + '18', paddingHorizontal: 10, paddingVertical: 5, borderRadius: RADIUS.full },
  ptsText: { color: COLORS.gold, fontSize: FONT.sm, fontWeight: '900' },
  qBlock: { marginTop: SPACING.sm },
  qText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700', marginBottom: 8 },
  choice: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 12, marginBottom: 8, borderRadius: RADIUS.md, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  choiceCorrect: { borderColor: COLORS.green, backgroundColor: COLORS.green + '14' },
  choiceDim: { opacity: 0.5 },
  choiceText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600' },
  doneNote: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', marginTop: 2 },
  empty: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '800', marginTop: 8 },
  dim: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600', marginTop: 4 },
});
