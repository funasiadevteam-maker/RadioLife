import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView,
  ActivityIndicator, Animated,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../constants/theme';
import {
  fetchCampaign, startSession, submitSession, claimToWallet,
  normalizeGameError,
} from '../api/gamesApi';
import type { SubmitResult, GameError } from '../api/gamesApi';
import useBigCoinStore from '../stores/useBigCoinStore';
import RewardModal from './RewardModal';
import { Image as ExpoImage } from 'expo-image';
import { LinearGradient } from 'expo-linear-gradient';
import { gameArtFor } from '../constants/gameArt';
import { gameFx } from '../utils/gameFX';

/* ── Shared quiz engine (Phase 39M.3) ──
   Drives every `tpl_quiz` games_v2 campaign (Music Trivia, Lyric Hunt).
   Replaces the retired Phase 5 `/api/games/trivia|lyric/*` endpoints,
   which now answer 410 Gone.

   Flow:
     POST /games_v2/campaigns/{id}/start
       -> render_config { type:'quiz', time_per_question_s,
                          min_correct_to_win, questions:[{prompt, options, ...}] }
     POST /games_v2/sessions/{sid}/submit
       -> { result, prize, bigcoin_earned, quiz_meta:{correct_idx, chosen_idx, correct} }

   The server never sends `correct_idx` before submit, so correctness is
   only revealed after the answer is posted. */

type QuizQuestion = {
  prompt?: string;
  options?: string[];
  track?: { title?: string; artist?: string } | null;
  song?: string | null;
  artist?: string | null;
  language?: string | null;
};

type Props = {
  campaignId: string;
  headerTitle: string;
  accent?: string;
  icon?: keyof typeof Ionicons.glyphMap;
  testIDPrefix?: string;
};

export default function QuizGame({
  campaignId, headerTitle, accent = '#f59e0b',
  icon = 'musical-notes', testIDPrefix = 'quiz',
}: Props) {
  const router = useRouter();

  const [campaign, setCampaign] = useState<any>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [questions, setQuestions] = useState<QuizQuestion[]>([]);
  const [qIndex, setQIndex] = useState(0);
  const [answers, setAnswers] = useState<number[]>([]);
  const [chosen, setChosen] = useState<number | null>(null);
  const [timeLimit, setTimeLimit] = useState(15);
  const [secsLeft, setSecsLeft] = useState(15);

  const [booting, setBooting] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [showReward, setShowReward] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const [claimed, setClaimed] = useState(false);
  const [error, setError] = useState<GameError | null>(null);
  const [streak, setStreak] = useState(0);
  const [totalEarned, setTotalEarned] = useState(0);

  const addOptimistic = useBigCoinStore((s) => s.addOptimistic);
  const refreshBalance = useBigCoinStore((s) => s.refresh);

  // Guards against a timeout firing after the answer was already sent.
  const answeredRef = useRef(false);
  const barAnim = useRef(new Animated.Value(1)).current;

  const boot = useCallback(async () => {
    setBooting(true);
    setError(null);
    setResult(null);
    setShowReward(false);
    setClaimed(false);
    setChosen(null);
    setAnswers([]);
    setQIndex(0);
    answeredRef.current = false;
    try {
      const c = await fetchCampaign(campaignId).catch(() => null);
      if (c) setCampaign(c);
      const s = await startSession(campaignId);
      setSessionId(s.session_id);
      const rc = s?.render_config || {};
      const qs: QuizQuestion[] = rc.questions || [];
      setQuestions(qs);
      const limit = Number(rc.time_per_question_s) || 15;
      setTimeLimit(limit);
      setSecsLeft(limit);
    } catch (e) {
      setError(normalizeGameError(e));
    } finally {
      setBooting(false);
    }
  }, [campaignId]);

  useEffect(() => { boot(); }, [boot]);

  const finish = useCallback(async (finalAnswers: number[]) => {
    if (!sessionId) return;
    setSubmitting(true);
    try {
      const res = await submitSession(sessionId, {
        // Dynamic single-question campaigns read `answer_idx`; static
        // multi-question ones read `answers`. Send both — the server
        // picks based on the campaign config, never on the payload.
        answer_idx: finalAnswers[0] ?? -1,
        answers: finalAnswers,
      });
      setResult(res);
      setShowReward(true);
      setSessionId(null);
      const correct = res.result === 'win' || res.quiz_meta?.correct === true;
      if (correct) gameFx('win', 'success'); else gameFx('lose', 'light');
      setStreak((p) => (correct ? p + 1 : 0));
      const earned = Number(res.bigcoin_earned) || 0;
      if (earned > 0) {
        setTotalEarned((p) => p + earned);
        addOptimistic(earned);
        refreshBalance();
      }
    } catch (e) {
      setError(normalizeGameError(e));
    } finally {
      setSubmitting(false);
    }
  }, [sessionId, addOptimistic, refreshBalance]);

  const pick = useCallback((idx: number) => {
    if (answeredRef.current || submitting || !sessionId) return;
    answeredRef.current = true;
    setChosen(idx);
    gameFx('reveal', 'light');
    const next = [...answers];
    next[qIndex] = idx;
    setAnswers(next);

    if (qIndex >= questions.length - 1) {
      finish(next);
    } else {
      // Advance to the next question after a brief beat.
      setTimeout(() => {
        setQIndex((i) => i + 1);
        setChosen(null);
        setSecsLeft(timeLimit);
        answeredRef.current = false;
      }, 350);
    }
  }, [answers, qIndex, questions.length, finish, submitting, sessionId, timeLimit]);

  /* Per-question countdown. Running out counts as a wrong answer (-1),
     which the server scores as incorrect. */
  useEffect(() => {
    if (booting || !sessionId || result || showReward) return;
    if (answeredRef.current) return;
    if (secsLeft <= 0) { pick(-1); return; }
    const id = setTimeout(() => setSecsLeft((v) => v - 1), 1000);
    return () => clearTimeout(id);
  }, [secsLeft, booting, sessionId, result, showReward, pick]);

  useEffect(() => {
    Animated.timing(barAnim, {
      toValue: timeLimit > 0 ? Math.max(0, secsLeft) / timeLimit : 0,
      duration: 320,
      useNativeDriver: false,
    }).start();
  }, [secsLeft, timeLimit, barAnim]);

  const handleClaim = async () => {
    if (!result) return;
    setClaiming(true);
    try {
      await claimToWallet(result.session_id);
      setClaimed(true);
      refreshBalance();
    } catch (e) {
      setError(normalizeGameError(e));
    } finally {
      setClaiming(false);
    }
  };

  const Header = (
    <View style={s.topBar}>
      <TouchableOpacity
        onPress={() => router.back()}
        style={s.backBtn}
        testID={`${testIDPrefix}-back-btn`}
      >
        <Ionicons name="chevron-back" size={20} color={COLORS.text} />
      </TouchableOpacity>
      <Text style={s.topTitle}>{headerTitle}</Text>
      <View style={{ width: 32 }} />
    </View>
  );

  if (booting) {
    return (
      <SafeAreaView style={s.screen} testID={`${testIDPrefix}-loading`}>
        {Header}
        <View style={s.centerFill}>
          <ActivityIndicator size="large" color={COLORS.primary} />
          <Text style={s.dimText}>Loading your question…</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (error && !result) {
    return (
      <SafeAreaView style={s.screen} testID={`${testIDPrefix}-error`}>
        {Header}
        <View style={s.body}>
          <View style={s.unavailableCard}>
            <Ionicons name="alert-circle-outline" size={40} color={COLORS.textMuted} />
            <Text style={s.unavailableTitle}>{error.title}</Text>
            <Text style={s.unavailableDesc}>{error.message}</Text>
            {error.retryable && (
              <TouchableOpacity
                style={s.backActionBtn}
                onPress={boot}
                testID={`${testIDPrefix}-retry-btn`}
              >
                <Text style={s.backActionText}>TRY AGAIN</Text>
              </TouchableOpacity>
            )}
            <TouchableOpacity onPress={() => router.back()} testID={`${testIDPrefix}-go-back`}>
              <Text style={s.linkText}>Back to Games</Text>
            </TouchableOpacity>
          </View>
        </View>
      </SafeAreaView>
    );
  }

  const q = questions[qIndex];
  const correctIdx = result?.quiz_meta?.correct_idx;
  const wasCorrect = result?.quiz_meta?.correct === true || result?.result === 'win';
  const revealed = !!result;
  const songLine = q?.track?.title
    ? `${q.track.title}${q.track.artist ? ` — ${q.track.artist}` : ''}`
    : (q?.song ? `${q.song}${q.artist ? ` — ${q.artist}` : ''}` : null);

  return (
    <SafeAreaView style={s.screen} testID={`${testIDPrefix}-screen`}>
      {Header}

      <View style={s.body}>
        {/* Premium AI-art header band */}
        <View style={s.artBanner} testID={`${testIDPrefix}-art`}>
          <ExpoImage source={{ uri: gameArtFor(testIDPrefix, 'trivia') }} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={['rgba(14,8,34,0.9)', 'rgba(14,8,34,0.25)']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={StyleSheet.absoluteFill} />
          <View style={s.artBannerBody}>
            <Text style={s.artEyebrow}>{headerTitle.toUpperCase()}</Text>
            <Text style={s.artTitle}>Answer fast — win bigger</Text>
          </View>
        </View>

        {/* Streak + earnings */}
        <View style={s.metaRow}>
          {streak > 0 && (
            <View style={s.streakBadge} testID={`${testIDPrefix}-streak`}>
              <Ionicons name="flame" size={14} color="#f59e0b" />
              <Text style={s.streakText}>Streak: {streak}</Text>
            </View>
          )}
          {totalEarned > 0 && (
            <View style={s.earnedBadge} testID={`${testIDPrefix}-earned`}>
              <Text style={s.earnedText}>₿ +{totalEarned} this session</Text>
            </View>
          )}
        </View>

        {!q ? (
          <View style={s.unavailableCard} testID={`${testIDPrefix}-empty`}>
            <Ionicons name={icon} size={40} color={COLORS.textMuted} />
            <Text style={s.unavailableTitle}>No question available</Text>
            <Text style={s.unavailableDesc}>
              This game has no questions ready right now. Please check back soon.
            </Text>
            <TouchableOpacity style={s.backActionBtn} onPress={boot} testID={`${testIDPrefix}-empty-retry`}>
              <Text style={s.backActionText}>TRY AGAIN</Text>
            </TouchableOpacity>
          </View>
        ) : (
          <View style={s.questionCard}>
            {/* Timer */}
            {!revealed && (
              <View style={s.timerWrap} testID={`${testIDPrefix}-timer`}>
                <View style={s.timerTrack}>
                  <Animated.View
                    style={[s.timerFill, {
                      backgroundColor: secsLeft <= 5 ? COLORS.red : accent,
                      width: barAnim.interpolate({
                        inputRange: [0, 1], outputRange: ['0%', '100%'],
                      }),
                    }]}
                  />
                </View>
                <Text style={[s.timerText, secsLeft <= 5 && { color: COLORS.red }]}>
                  {Math.max(0, secsLeft)}s
                </Text>
              </View>
            )}

            {questions.length > 1 && (
              <Text style={s.progressText}>
                Question {qIndex + 1} of {questions.length}
              </Text>
            )}

            <View style={[s.iconBubble, { backgroundColor: `${accent}18` }]}>
              <Ionicons name={icon} size={26} color={accent} />
            </View>

            <Text style={s.questionText} testID={`${testIDPrefix}-question`}>
              {q.prompt}
            </Text>

            {!!songLine && (
              <Text style={s.songLine} testID={`${testIDPrefix}-song`}>{songLine}</Text>
            )}

            <View style={s.optionsList}>
              {(q.options || []).map((opt, i) => {
                const isChosen = chosen === i;
                const isCorrect = revealed && correctIdx === i;
                const isWrong = revealed && isChosen && !isCorrect;

                let bg = COLORS.card;
                let border = COLORS.cardBorder;
                if (isCorrect) { bg = '#dcfce7'; border = '#16a34a'; }
                else if (isWrong) { bg = '#fef2f2'; border = '#e11d48'; }
                else if (isChosen && !revealed) { bg = `${accent}18`; border = accent; }

                return (
                  <TouchableOpacity
                    key={`${qIndex}-${i}`}
                    style={[s.optionBtn, { backgroundColor: bg, borderColor: border }]}
                    onPress={() => pick(i)}
                    disabled={revealed || submitting || chosen !== null}
                    activeOpacity={0.85}
                    testID={`${testIDPrefix}-option-${i}`}
                  >
                    <LinearGradient
                      colors={isCorrect ? ['#16a34a', '#16a34a'] : isWrong ? ['#e11d48', '#e11d48'] : [accent, '#ec4899']}
                      start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
                      style={s.optChip}
                    >
                      <Text style={s.optChipTxt}>{String.fromCharCode(65 + i)}</Text>
                    </LinearGradient>
                    <Text style={s.optionText}>{opt}</Text>
                    {isCorrect && <Ionicons name="checkmark-circle" size={18} color="#16a34a" />}
                    {isWrong && <Ionicons name="close-circle" size={18} color="#e11d48" />}
                  </TouchableOpacity>
                );
              })}
            </View>

            {submitting && (
              <View style={s.submittingRow}>
                <ActivityIndicator size="small" color={COLORS.primary} />
                <Text style={s.dimText}>Checking your answer…</Text>
              </View>
            )}

            {revealed && (
              <View style={s.resultSection}>
                <View style={s.resultRow}>
                  <Ionicons
                    name={wasCorrect ? 'checkmark-circle' : 'close-circle'}
                    size={22}
                    color={wasCorrect ? COLORS.green : COLORS.red}
                  />
                  <Text style={wasCorrect ? s.resultCorrect : s.resultWrong}>
                    {wasCorrect
                      ? (totalEarned > 0 ? 'Correct!' : 'Correct!')
                      : 'Not quite'}
                  </Text>
                </View>
                <View style={s.actionRow}>
                  <TouchableOpacity style={s.nextBtn} onPress={boot} testID={`${testIDPrefix}-next-btn`}>
                    <Text style={s.nextBtnText}>NEXT QUESTION</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={s.doneBtn}
                    onPress={() => router.back()}
                    testID={`${testIDPrefix}-done-btn`}
                  >
                    <Text style={s.doneBtnText}>DONE</Text>
                  </TouchableOpacity>
                </View>
              </View>
            )}
          </View>
        )}

        {!!campaign?.description && !revealed && (
          <Text style={s.campaignDesc}>{campaign.description}</Text>
        )}
      </View>

      <RewardModal
        visible={showReward}
        result={result}
        claiming={claiming}
        claimed={claimed}
        onClaim={handleClaim}
        subtitle={
          result && !wasCorrect && typeof correctIdx === 'number'
            ? `Correct answer: ${questions[0]?.options?.[correctIdx] ?? '—'}`
            : null
        }
        onClose={() => setShowReward(false)}
        onPlayAgain={() => { setShowReward(false); boot(); }}
      />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  centerFill: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  dimText: { color: COLORS.textDim, fontSize: FONT.sm },
  topBar: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: SPACING.lg, paddingVertical: SPACING.md,
  },
  backBtn: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  topTitle: { fontSize: FONT.lg, fontWeight: '900', color: COLORS.text },
  body: { flex: 1, padding: SPACING.lg },
  artBanner: { width: '100%', height: 92, borderRadius: RADIUS.lg, overflow: 'hidden', marginBottom: 14, justifyContent: 'flex-end' },
  artBannerBody: { padding: 12 },
  artEyebrow: { color: '#93c5fd', fontSize: FONT.xs, fontWeight: '900', letterSpacing: 1.2 },
  artTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '900', marginTop: 2 },
  optChip: { width: 28, height: 28, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  optChipTxt: { color: '#fff', fontSize: FONT.sm, fontWeight: '900' },
  metaRow: {
    flexDirection: 'row', gap: 8, justifyContent: 'center',
    flexWrap: 'wrap', marginBottom: 12,
  },
  streakBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: '#fef3c7', borderRadius: RADIUS.full,
    paddingHorizontal: 14, paddingVertical: 6,
  },
  streakText: { fontSize: FONT.sm, fontWeight: '700', color: '#92400e' },
  earnedBadge: {
    backgroundColor: '#ecfdf5', borderRadius: RADIUS.full,
    paddingHorizontal: 14, paddingVertical: 6,
  },
  earnedText: { fontSize: FONT.sm, fontWeight: '700', color: '#047857' },

  questionCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.lg, alignItems: 'center',
  },
  timerWrap: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    alignSelf: 'stretch', marginBottom: SPACING.md,
  },
  timerTrack: {
    flex: 1, height: 6, borderRadius: 3,
    backgroundColor: COLORS.inputBg, overflow: 'hidden',
  },
  timerFill: { height: 6, borderRadius: 3 },
  timerText: {
    fontSize: FONT.sm, fontWeight: '800', color: COLORS.textDim,
    minWidth: 32, textAlign: 'right',
  },
  progressText: {
    fontSize: FONT.xs, color: COLORS.textMuted, fontWeight: '700',
    letterSpacing: 1, marginBottom: 8,
  },
  iconBubble: {
    width: 52, height: 52, borderRadius: 16,
    alignItems: 'center', justifyContent: 'center', marginBottom: 12,
  },
  questionText: {
    fontSize: FONT.lg, fontWeight: '800', color: COLORS.text,
    textAlign: 'center', lineHeight: 24,
  },
  songLine: {
    fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center', marginTop: 6,
  },
  optionsList: { width: '100%', gap: 8, marginTop: SPACING.lg },
  optionBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    borderWidth: 1, borderRadius: RADIUS.md,
    padding: SPACING.md, minHeight: 48, gap: 8,
  },
  optionText: { fontSize: FONT.md, fontWeight: '600', color: COLORS.text, flex: 1 },
  submittingRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: SPACING.md,
  },
  resultSection: { width: '100%', marginTop: SPACING.lg, alignItems: 'center' },
  resultRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 },
  resultCorrect: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.green },
  resultWrong: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.red },
  actionRow: { flexDirection: 'row', gap: 10, width: '100%' },
  nextBtn: {
    flex: 1, backgroundColor: COLORS.primary, borderRadius: RADIUS.md,
    paddingVertical: 14, alignItems: 'center',
  },
  nextBtnText: { color: '#fff', fontWeight: '800', fontSize: FONT.sm, letterSpacing: 0.5 },
  doneBtn: {
    flex: 1, backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md,
    paddingVertical: 14, alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  doneBtnText: { color: COLORS.textDim, fontWeight: '700', fontSize: FONT.sm, letterSpacing: 0.5 },
  campaignDesc: {
    fontSize: FONT.xs, color: COLORS.textMuted, textAlign: 'center',
    marginTop: SPACING.lg, lineHeight: 16,
  },
  unavailableCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg,
    borderWidth: 1, borderColor: COLORS.cardBorder,
    padding: SPACING.xl, alignItems: 'center', marginTop: 40,
  },
  unavailableTitle: { fontSize: FONT.xl, fontWeight: '900', color: COLORS.text, marginTop: 12 },
  unavailableDesc: {
    fontSize: FONT.sm, color: COLORS.textDim, textAlign: 'center',
    marginTop: 8, lineHeight: 20,
  },
  backActionBtn: {
    backgroundColor: COLORS.primary, borderRadius: RADIUS.full,
    paddingHorizontal: 24, paddingVertical: 14, marginTop: SPACING.lg,
  },
  backActionText: { color: '#fff', fontWeight: '800', fontSize: FONT.sm, letterSpacing: 0.5 },
  linkText: {
    color: COLORS.primary, fontWeight: '700', fontSize: FONT.sm, marginTop: SPACING.md,
  },
});
