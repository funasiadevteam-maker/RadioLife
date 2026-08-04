import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, Share,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../src/constants/theme';
import api, { BACKEND } from '../../src/api/client';

const PER_Q_TIMEOUT_SEC = 30;

export default function TriviaPlayScreen() {
  const router = useRouter();
  const { cat } = useLocalSearchParams<{ cat: string }>();

  const [session, setSession] = useState<any>(null);
  const [qIndex, setQIndex] = useState(0);
  const [reveal, setReveal] = useState<any>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const [score, setScore] = useState(0);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [finished, setFinished] = useState<any>(null);
  const [now, setNow] = useState(Date.now());
  const qStartRef = useRef(Date.now());

  // Start session
  useEffect(() => {
    if (!cat) { router.replace('/(tabs)/trivia'); return; }
    let cancelled = false;
    (async () => {
      try {
        const r = await api.post('/trivia/sessions/start', { category_id: cat, difficulty: 2 });
        if (cancelled) return;
        setSession(r.data);
        qStartRef.current = Date.now();
      } catch (e: any) {
        Alert.alert('Error', e?.response?.data?.detail || 'Failed to start trivia.');
        router.replace('/(tabs)/trivia');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [cat]);

  // Countdown timer
  useEffect(() => {
    if (!session || reveal || finished) return;
    const t = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(t);
  }, [session, reveal, finished, qIndex]);

  const currentQ = useMemo(() => session?.questions?.[qIndex] || null, [session, qIndex]);
  const elapsedSec = (now - qStartRef.current) / 1000;
  const remainingSec = Math.max(0, PER_Q_TIMEOUT_SEC - elapsedSec);
  const timeoutPct = Math.min(100, (elapsedSec / PER_Q_TIMEOUT_SEC) * 100);

  const onChoose = async (choiceId: string) => {
    if (!currentQ || reveal || submitting) return;
    setSubmitting(true);
    setChosen(choiceId);
    try {
      const r = await api.post(`/trivia/sessions/${session.session_id}/answer`, {
        question_id: currentQ.id,
        choice_id: choiceId,
      });
      setReveal(r.data);
      setScore(r.data.running_score);
    } catch (e: any) {
      if (e?.response?.status === 408) {
        setReveal({ correct: false, correct_choice_id: null, points_awarded: 0, running_score: score, timed_out: true });
      } else {
        setChosen(null);
      }
    } finally {
      setSubmitting(false);
    }
  };

  const onNext = async () => {
    if (!session) return;
    const nextIdx = qIndex + 1;
    if (nextIdx >= session.questions.length) {
      try {
        const r = await api.post(`/trivia/sessions/${session.session_id}/finish`);
        setFinished(r.data);
      } catch {}
      return;
    }
    setQIndex(nextIdx);
    setChosen(null);
    setReveal(null);
    qStartRef.current = Date.now();
  };

  const shareScore = async () => {
    try {
      await Share.share({
        message: `I scored ${finished.final_score} on BigFM Trivia! Can you beat me?`,
      });
    } catch {}
  };

  // Final screen
  if (finished) {
    return (
      <SafeAreaView style={common.screen} testID="trivia-final">
        <ScrollView contentContainerStyle={s.centered}>
          <View style={[common.card, { alignItems: 'center', gap: SPACING.md }]}>
            <View style={s.liveChip}>
              <View style={s.liveDot} />
              <Text style={s.liveText}>SESSION COMPLETE</Text>
            </View>
            <Text style={s.finalScore} testID="trivia-final-score">{finished.final_score}</Text>
            <Text style={s.finalSub}>{finished.correct} / {finished.total} correct</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }} testID="trivia-final-bc">
              <Ionicons name="diamond" size={16} color={COLORS.gold} />
              <Text style={s.finalBc}>+{finished.bigcoin_awarded} BigCoin awarded</Text>
            </View>
            <View style={{ flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.md }}>
              <TouchableOpacity style={common.btnPrimary} onPress={() => router.replace('/(tabs)/trivia')} testID="trivia-final-again">
                <Ionicons name="refresh" size={14} color="#fff" />
                <Text style={common.btnPrimaryText}>Play again</Text>
              </TouchableOpacity>
              <TouchableOpacity style={common.btnGhost} onPress={shareScore} testID="trivia-final-share">
                <Ionicons name="share-outline" size={14} color={COLORS.textDim} />
                <Text style={common.btnGhostText}>Share</Text>
              </TouchableOpacity>
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    );
  }

  // Loading
  if (loading || !session || !currentQ) {
    return (
      <View style={common.center} testID="trivia-loading">
        <ActivityIndicator size="large" color={COLORS.primary} />
        <Text style={s.loadingText}>Warming up the question bank…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={common.screen} testID="trivia-play">
      <ScrollView contentContainerStyle={s.scroll}>
        {/* Back */}
        <TouchableOpacity onPress={() => router.back()} style={s.backRow}>
          <Ionicons name="chevron-back" size={16} color={COLORS.textDim} />
          <Text style={s.backText}>Trivia</Text>
        </TouchableOpacity>

        {/* Top bar */}
        <View style={s.topBar}>
          <Text style={s.topLabel} testID="trivia-progress">Q {qIndex + 1} / {session.questions.length}</Text>
          <Text style={[s.topLabel, { color: COLORS.secondary }]} testID="trivia-score">Score · {score}</Text>
        </View>

        {/* Timer bar */}
        <View style={s.timerTrack} testID="trivia-timer-bar">
          <View style={[s.timerFill, {
            width: `${Math.max(0, 100 - timeoutPct)}%`,
            backgroundColor: remainingSec < 5 ? COLORS.primary : COLORS.secondary,
          }]} />
        </View>

        {/* Question card */}
        <View style={common.card}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: SPACING.sm }}>
            <Ionicons name="bulb" size={12} color={COLORS.textDim} />
            <Text style={s.catLabel}>{currentQ.category || 'trivia'} · diff {currentQ.difficulty}</Text>
          </View>
          <Text style={s.prompt} testID="trivia-prompt">{currentQ.prompt}</Text>

          <View style={{ gap: SPACING.sm, marginTop: SPACING.md }} testID="trivia-choices">
            {currentQ.choices.map((c: any) => {
              const isChosen = chosen === c.id;
              const isCorrect = reveal?.correct_choice_id === c.id;
              const isWrongPick = reveal && isChosen && !reveal.correct;
              const bg = reveal
                ? (isCorrect ? 'rgba(74,222,128,0.12)' : isWrongPick ? 'rgba(251,113,133,0.12)' : COLORS.surface)
                : (isChosen ? 'rgba(59,130,246,0.1)' : COLORS.surface);
              const border = reveal
                ? (isCorrect ? COLORS.green : isWrongPick ? COLORS.red : COLORS.surfaceBorder)
                : (isChosen ? COLORS.secondary : COLORS.surfaceBorder);

              return (
                <TouchableOpacity
                  key={c.id}
                  disabled={!!reveal || submitting}
                  onPress={() => onChoose(c.id)}
                  testID={`trivia-choice-${c.id}`}
                  style={[s.choiceBtn, { backgroundColor: bg, borderColor: border }]}
                  activeOpacity={0.7}
                >
                  <Text style={s.choiceLabel}>{c.id.toUpperCase()}</Text>
                  <Text style={s.choiceText}>{c.text}</Text>
                  {reveal && isCorrect && <Ionicons name="checkmark-circle" size={16} color={COLORS.green} />}
                  {reveal && isWrongPick && <Ionicons name="close-circle" size={16} color={COLORS.red} />}
                </TouchableOpacity>
              );
            })}
          </View>

          {/* "Waiting" hint after submit */}
          {chosen && !reveal && (
            <View style={s.waitingRow}>
              <ActivityIndicator size="small" color={COLORS.secondary} />
              <Text style={s.waitingText}>You answered. Waiting…</Text>
            </View>
          )}

          {/* Reveal bar */}
          {reveal && (
            <View style={s.revealBar} testID="trivia-reveal">
              <View style={{ flex: 1 }}>
                {reveal.timed_out ? (
                  <Text style={[s.revealText, { color: COLORS.primary }]}>Time up — no points.</Text>
                ) : reveal.correct ? (
                  <Text style={[s.revealText, { color: COLORS.green }]}>
                    Correct! +{reveal.points_awarded} pts
                    {reveal.points_awarded > 100 ? ' ✨ speed bonus' : ''}
                  </Text>
                ) : (
                  <Text style={[s.revealText, { color: COLORS.primary }]}>
                    Not quite — answer was {reveal.correct_choice_id?.toUpperCase()}.
                  </Text>
                )}
              </View>
              <TouchableOpacity style={s.nextBtn} onPress={onNext} testID="trivia-next">
                <Text style={s.nextBtnText}>
                  {qIndex + 1 >= session.questions.length ? 'Finish' : 'Next'}
                </Text>
                <Ionicons name="chevron-forward" size={14} color="#fff" />
              </TouchableOpacity>
            </View>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  centered: { padding: SPACING.lg, justifyContent: 'center', flex: 1 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.md },
  backText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600' },
  loadingText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.sm },
  liveChip: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  liveDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.green },
  liveText: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', letterSpacing: 2 },
  topBar: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: SPACING.sm },
  topLabel: { fontSize: 10, fontWeight: '700', color: COLORS.textDim, letterSpacing: 2 },
  timerTrack: { height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.06)', marginBottom: SPACING.md, overflow: 'hidden' },
  timerFill: { height: '100%', borderRadius: 2 },
  catLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', letterSpacing: 1.5 },
  prompt: { fontSize: 22, fontWeight: '900', color: COLORS.text, lineHeight: 28 },
  choiceBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 12,
    borderWidth: 1, borderRadius: RADIUS.md, paddingHorizontal: 16, paddingVertical: 14,
  },
  choiceLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', width: 20 },
  choiceText: { flex: 1, fontSize: 14, color: COLORS.text },
  waitingRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: SPACING.md },
  waitingText: { color: COLORS.textDim, fontSize: FONT.sm },
  revealBar: {
    flexDirection: 'row', alignItems: 'center', marginTop: SPACING.md,
    borderTopWidth: 1, borderTopColor: 'rgba(255,255,255,0.06)', paddingTop: SPACING.md,
  },
  revealText: { fontSize: 14, fontWeight: '800' },
  nextBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: COLORS.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: RADIUS.md,
  },
  nextBtnText: { color: '#fff', fontWeight: '700', fontSize: FONT.sm },
  finalScore: { fontSize: 56, fontWeight: '900', color: COLORS.secondary },
  finalSub: { fontSize: 14, color: COLORS.textDim },
  finalBc: { fontSize: 16, fontWeight: '700', color: COLORS.gold },
});
