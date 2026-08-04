import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, Alert, TextInput, Animated,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/contexts/AuthContext';
import api from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

export default function GameScreen() {
  const { campaignId } = useLocalSearchParams<{ campaignId: string }>();
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [campaign, setCampaign] = useState<any>(null);
  const [session, setSession] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [claiming, setClaiming] = useState(false);
  const [walletItem, setWalletItem] = useState<any>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
    if (!campaignId) return;
    (async () => {
      try {
        const r = await api.get(`/games_v2/campaigns/${campaignId}`);
        setCampaign(r.data);
      } catch { Alert.alert('Error', 'Could not load campaign'); router.back(); return; }
      await tryStart({});
    })();
  }, [user, authLoading, campaignId]);

  const tryStart = async (extra: any = {}) => {
    try {
      const s = await api.post(`/games_v2/campaigns/${campaignId}/start`, extra);
      setSession(s.data);
    } catch (e: any) {
      const d = e?.response?.data?.detail;
      const code = e?.response?.status;
      if (code === 423) Alert.alert('Driving mode', 'Turn off driving mode to play');
      else if (d === 'max_per_user_reached') Alert.alert('Limit', 'You\'ve already played this game');
      else Alert.alert('Error', d || 'Could not start game');
      router.back();
    }
  };

  const submitGame = async (payload: any) => {
    if (!session) return;
    setSubmitting(true);
    try {
      const r = await api.post(`/games_v2/sessions/${session.session_id}/submit`, payload);
      setResult(r.data);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Submit failed');
    } finally { setSubmitting(false); }
  };

  const claim = async () => {
    if (!session || !result || result.result !== 'win') return;
    setClaiming(true);
    try {
      const r = await api.post(`/games_v2/sessions/${session.session_id}/claim_to_wallet`);
      setWalletItem(r.data.wallet_item);
      Alert.alert('Saved!', r.data.wallet_item ? 'Saved to wallet' : `${result.bigcoin_earned} BigCoin credited`);
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Claim failed');
    } finally { setClaiming(false); }
  };

  if (authLoading || !user || !campaign) {
    return <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const brand = campaign.brand_colors_json?.primary || COLORS.primary;

  if (!session) {
    return <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const cfg = session.render_config || {};

  return (
    <SafeAreaView style={s.screen} testID="game-player">
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} testID="exit-game-btn">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={s.backText}>exit</Text>
        </TouchableOpacity>
        <View style={{ flex: 1 }}>
          <Text style={s.sponsor}>{campaign.sponsor_name?.toUpperCase()}</Text>
          <Text style={s.gameTitle} numberOfLines={1}>{campaign.title}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={s.content}>
        {/* Game Stage */}
        {cfg.type === 'spin_wheel' && <SpinWheel config={cfg} onSubmit={submitGame} submitting={submitting} result={result} brand={brand} />}
        {cfg.type === 'scratch_card' && <ScratchCard config={cfg} onSubmit={submitGame} submitting={submitting} result={result} brand={brand} />}
        {cfg.type === 'quiz' && <QuizGame config={cfg} onSubmit={submitGame} submitting={submitting} result={result} brand={brand} />}
        {cfg.type === 'mystery_box' && <MysteryBox config={cfg} onSubmit={submitGame} submitting={submitting} result={result} brand={brand} />}
        {cfg.type === 'word_puzzle' && <WordPuzzle config={cfg} onSubmit={submitGame} submitting={submitting} result={result} brand={brand} />}
        {cfg.type === 'slot_machine' && <SlotMachine config={cfg} onSubmit={submitGame} submitting={submitting} result={result} brand={brand} />}
        {cfg.type === 'memory_match' && <MemoryMatch config={cfg} onSubmit={submitGame} submitting={submitting} result={result} brand={brand} />}
        {!['spin_wheel','scratch_card','quiz','mystery_box','word_puzzle','slot_machine','memory_match'].includes(cfg.type) && (
          <View style={s.unsupported}>
            <Ionicons name="game-controller" size={48} color={COLORS.textMuted} />
            <Text style={s.unsupportedText}>Game type: {cfg.type}</Text>
            <TouchableOpacity style={s.playNowBtn} onPress={() => submitGame({})}>
              <Text style={s.playNowText}>Play</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      {/* Result Modal */}
      {result && (
        <View style={s.resultOverlay} testID="result-modal">
          <View style={s.resultCard}>
            {result.result === 'win' ? (
              <>
                <Ionicons name="trophy" size={36} color={COLORS.gold} testID="result-win-icon" />
                <Text style={s.resultTitle} testID="result-headline">You won!</Text>
                {result.prize && <Text style={s.prizeName}>{result.prize.title}</Text>}
                {result.prize?.description && <Text style={s.prizeDesc}>{result.prize.description}</Text>}
                {result.prize?.prize_type === 'bigcoin' && (
                  <Text style={s.bigcoinCredit}><Ionicons name="cash" size={14} color={COLORS.gold} /> {result.bigcoin_earned} BigCoin credited</Text>
                )}
                {!walletItem && result.prize?.prize_type !== 'bigcoin' && (
                  <TouchableOpacity style={[s.claimBtn, { backgroundColor: brand }]} onPress={claim} disabled={claiming} testID="claim-to-wallet-btn">
                    {claiming ? <ActivityIndicator size={14} color="#fff" /> : <Ionicons name="save" size={14} color="#fff" />}
                    <Text style={s.claimText}>Save to wallet</Text>
                  </TouchableOpacity>
                )}
                {walletItem && (
                  <TouchableOpacity style={s.walletBtn} onPress={() => router.push('/(tabs)/wallet')}>
                    <Ionicons name="wallet" size={14} color={COLORS.secondary} />
                    <Text style={s.walletBtnText}>View in Wallet</Text>
                  </TouchableOpacity>
                )}
              </>
            ) : (
              <>
                <Ionicons name="sparkles" size={36} color={COLORS.textMuted} />
                <Text style={s.resultTitle} testID="result-headline">Better luck next time</Text>
                {result.quiz_meta?.score !== undefined && (
                  <Text style={s.quizScore} testID="quiz-score">Score: {result.quiz_meta.score}/{result.quiz_meta.total}</Text>
                )}
              </>
            )}
            <TouchableOpacity style={s.closeResultBtn} onPress={() => router.back()} testID="result-close">
              <Text style={s.closeResultText}>{result.result === 'win' ? 'Done' : 'Browse more games'}</Text>
            </TouchableOpacity>
          </View>
        </View>
      )}
    </SafeAreaView>
  );
}

/* ── SpinWheel ── */
function SpinWheel({ config, onSubmit, submitting, result, brand }: any) {
  const segs = config.segments || [];
  const n = segs.length || 1;
  const rotAnim = useRef(new Animated.Value(0)).current;
  const [spinning, setSpinning] = useState(false);

  useEffect(() => {
    if (result && !spinning) {
      setSpinning(true);
      Animated.timing(rotAnim, { toValue: 360 * 5 + Math.random() * 360, duration: config.spin_duration_ms || 4000, useNativeDriver: true }).start();
    }
  }, [result]);

  const spin = rotAnim.interpolate({ inputRange: [0, 360], outputRange: ['0deg', '360deg'] });

  return (
    <View style={gs.gameWrap} testID="spin-wheel">
      <View style={gs.wheelWrap}>
        <View style={gs.pointer}><Ionicons name="caret-down" size={24} color={brand} /></View>
        <Animated.View style={[gs.wheel, { backgroundColor: brand, transform: [{ rotate: spin }] }]}>
          {segs.map((seg: any, i: number) => (
            <View key={i} style={[gs.wheelSeg, { transform: [{ rotate: `${(i * 360 / n)}deg` }] }]}>
              <Text style={gs.wheelSegText} numberOfLines={1}>{seg.label}</Text>
            </View>
          ))}
          {segs.length === 0 && <Text style={gs.wheelCenter}>SPIN</Text>}
        </Animated.View>
      </View>
      <TouchableOpacity style={[gs.actionBtn, { backgroundColor: brand }]}
        onPress={() => { if (!spinning && !submitting && !result) onSubmit({}); }}
        disabled={submitting || spinning || !!result} testID="spin-go-btn">
        <Text style={gs.actionText}>{submitting || spinning ? 'Spinning...' : 'Tap to spin'}</Text>
      </TouchableOpacity>
    </View>
  );
}

/* ── ScratchCard ── */
function ScratchCard({ config, onSubmit, submitting, result, brand }: any) {
  const threshold = config.scratch_threshold || 0.5;
  const gridSize = 5;
  const total = gridSize * gridSize;
  const [revealed, setRevealed] = useState<boolean[]>(new Array(total).fill(false));
  const [submitted, setSubmitted] = useState(false);

  const scratch = (idx: number) => {
    if (submitted || result) return;
    const next = [...revealed];
    next[idx] = true;
    setRevealed(next);
    const pct = next.filter(Boolean).length / total;
    if (pct >= threshold && !submitted) {
      setSubmitted(true);
      onSubmit({ scratched_pct: pct });
    }
  };
  const pct = revealed.filter(Boolean).length / total;

  return (
    <View style={gs.gameWrap} testID="scratch-card">
      <Text style={gs.instruction}>Tap cells to scratch — reveal {Math.round(threshold * 100)}%</Text>
      <View style={gs.scratchGrid}>
        {revealed.map((r, i) => (
          <TouchableOpacity key={i} style={[gs.scratchCell, r && { backgroundColor: 'transparent', borderColor: brand }]}
            onPress={() => scratch(i)} testID={`scratch-cell-${i}`}>
            {r ? <Ionicons name="checkmark" size={14} color={brand} /> : <Text style={gs.scratchQ}>?</Text>}
          </TouchableOpacity>
        ))}
      </View>
      <View style={gs.progressBar}>
        <View style={[gs.progressFill, { width: `${Math.min(100, pct * 100 / threshold)}%`, backgroundColor: brand }]} />
      </View>
      <Text style={gs.progressLabel}>{Math.round(pct * 100)}% / {Math.round(threshold * 100)}%</Text>
    </View>
  );
}

/* ── Quiz ── */
function QuizGame({ config, onSubmit, submitting, result, brand }: any) {
  const questions = config.questions || [];
  const timePerQ = config.time_per_question_s || 15;
  const minCorrect = config.min_correct_to_win || 1;
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<number[]>([]);
  const [remaining, setRemaining] = useState(timePerQ);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (submitting || result || idx >= questions.length) return;
    setRemaining(timePerQ);
    tickRef.current = setInterval(() => {
      setRemaining((r) => {
        if (r <= 1) { clearInterval(tickRef.current!); submitAnswer(-1); return 0; }
        return r - 1;
      });
    }, 1000);
    return () => { if (tickRef.current) clearInterval(tickRef.current); };
  }, [idx]);

  const submitAnswer = (chosen: number) => {
    if (tickRef.current) clearInterval(tickRef.current);
    const newAnswers = [...answers, chosen];
    setAnswers(newAnswers);
    if (idx + 1 >= questions.length) {
      if (questions.length === 1) onSubmit({ answer_idx: chosen });
      else onSubmit({ answers: newAnswers });
    } else { setIdx(idx + 1); }
  };

  if (submitting || result) {
    return <View style={gs.gameWrap} testID="quiz-submitted"><ActivityIndicator size={24} color={brand} /><Text style={gs.instruction}>Grading...</Text></View>;
  }

  const q = questions[idx] || {};
  return (
    <View style={gs.gameWrap} testID="quiz-stage">
      <View style={gs.quizMeta}>
        <Text style={gs.quizProgress}>Q{idx + 1} / {questions.length}</Text>
        <Text style={[gs.quizTimer, remaining <= 5 && { color: COLORS.orange }]} testID="quiz-timer"><Ionicons name="time" size={11} color={COLORS.textDim} /> {remaining}s</Text>
      </View>
      <View style={gs.timerBar}><View style={[gs.timerFill, { width: `${(remaining / timePerQ) * 100}%`, backgroundColor: brand }]} /></View>
      <Text style={gs.quizPrompt} testID="quiz-prompt">{q.prompt}</Text>
      {(q.options || []).map((opt: string, i: number) => (
        <TouchableOpacity key={i} style={gs.quizOption} onPress={() => submitAnswer(i)} testID={`quiz-option-${i}`}>
          <Text style={gs.optionLetter}>{String.fromCharCode(65 + i)}</Text>
          <Text style={gs.optionText}>{opt}</Text>
        </TouchableOpacity>
      ))}
      <Text style={gs.quizRule}>Need {minCorrect} correct out of {questions.length} to win.</Text>
    </View>
  );
}

/* ── MysteryBox ── */
function MysteryBox({ config, onSubmit, submitting, result, brand }: any) {
  const boxes = config.boxes?.length ? config.boxes : Array.from({ length: config.num_boxes || 3 }, (_, i) => ({ label: `Box ${i + 1}` }));
  const [chosen, setChosen] = useState<number | null>(null);
  const pick = (i: number) => { if (chosen !== null || submitting || result) return; setChosen(i); onSubmit({ box_idx: i }); };
  return (
    <View style={gs.gameWrap} testID="mystery-box">
      <Text style={gs.instruction}>Pick one to reveal your prize</Text>
      <View style={gs.boxGrid}>
        {boxes.map((b: any, i: number) => (
          <TouchableOpacity key={i} style={[gs.box, chosen === i && { borderColor: brand, borderWidth: 2 }, chosen !== null && chosen !== i && { opacity: 0.4 }]}
            onPress={() => pick(i)} disabled={!!submitting || !!result} testID={`mystery-box-${i}`}>
            <Text style={gs.boxQ}>?</Text>
            <Text style={gs.boxLabel}>{b.label}</Text>
          </TouchableOpacity>
        ))}
      </View>
      {chosen !== null && submitting && <Text style={gs.instruction}>Opening Box {chosen + 1}...</Text>}
    </View>
  );
}

/* ── WordPuzzle ── */
function WordPuzzle({ config, onSubmit, submitting, result, brand }: any) {
  const masked = config.masked || '';
  const hint = config.hint || '';
  const [attempt, setAttempt] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const submit = () => { if (submitted || submitting || result || !attempt.trim()) return; setSubmitted(true); onSubmit({ attempted_phrase: attempt.trim().toUpperCase(), strikes_used: 0 }); };
  return (
    <View style={gs.gameWrap} testID="word-puzzle">
      <View style={gs.maskRow}>{masked.split('').map((c: string, i: number) => (
        <View key={i} style={[gs.tile, c === '_' && gs.tileBlank]}><Text style={gs.tileText}>{c === '_' ? '_' : c}</Text></View>
      ))}</View>
      <Text style={gs.hint} testID="word-hint"><Ionicons name="bulb" size={12} color={COLORS.gold} /> {hint || 'No hint'}</Text>
      <TextInput style={gs.wordInput} value={attempt} onChangeText={setAttempt} placeholder="Type your guess" placeholderTextColor={COLORS.textMuted} onSubmitEditing={submit} testID="word-input" />
      <TouchableOpacity style={[gs.actionBtn, { backgroundColor: brand }]} onPress={submit} disabled={submitting || !attempt.trim() || submitted || !!result} testID="word-submit-btn">
        <Text style={gs.actionText}>{submitting ? 'CHECKING...' : 'SOLVE'}</Text>
      </TouchableOpacity>
    </View>
  );
}

/* ── SlotMachine (simplified) ── */
function SlotMachine({ config, onSubmit, submitting, result, brand }: any) {
  const reels = config.reels || [['🎵','🎶','🎤'],['🎵','🎶','🎤'],['🎵','🎶','🎤']];
  const [spinning, setSpinning] = useState(false);
  const pull = () => { if (spinning || submitting || result) return; setSpinning(true); onSubmit({}); };
  return (
    <View style={gs.gameWrap} testID="slot-machine">
      <View style={gs.slotRow}>
        {reels.map((_: any, i: number) => (
          <View key={i} style={gs.slotReel}><Text style={{ fontSize: 32 }}>{spinning ? '?' : (reels[i]?.[0] || '🎵')}</Text></View>
        ))}
      </View>
      <TouchableOpacity style={[gs.actionBtn, { backgroundColor: brand }]} onPress={pull} disabled={submitting || spinning || !!result} testID="slot-pull-btn">
        <Text style={gs.actionText}>{spinning ? 'Spinning...' : 'Pull lever'}</Text>
      </TouchableOpacity>
    </View>
  );
}

/* ── MemoryMatch (simplified) ── */
function MemoryMatch({ config, onSubmit, submitting, result, brand }: any) {
  const deck = config.deck || [];
  const [revealed, setRevealed] = useState<boolean[]>(deck.map(() => false));
  const [matched, setMatched] = useState<boolean[]>(deck.map(() => false));
  const [first, setFirst] = useState<number | null>(null);
  const [pairs, setPairs] = useState(0);
  const startRef = useRef(Date.now());

  const click = (idx: number) => {
    if (revealed[idx] || matched[idx] || result) return;
    const next = [...revealed]; next[idx] = true; setRevealed(next);
    if (first === null) { setFirst(idx); return; }
    if (deck[first]?.match_id === deck[idx]?.match_id) {
      const nm = [...matched]; nm[first] = true; nm[idx] = true; setMatched(nm);
      const np = pairs + 1; setPairs(np);
      if (np >= deck.length / 2) onSubmit({ pairs_found: np, time_spent_sec: (Date.now() - startRef.current) / 1000 });
    } else {
      setTimeout(() => { const r = [...next]; r[first!] = false; r[idx] = false; setRevealed(r); }, 800);
    }
    setFirst(null);
  };

  return (
    <View style={gs.gameWrap} testID="memory-match">
      <Text style={gs.instruction}>Find matching pairs</Text>
      <View style={gs.memGrid}>
        {deck.map((card: any, i: number) => (
          <TouchableOpacity key={i} style={[gs.memCard, (revealed[i] || matched[i]) && { backgroundColor: brand }]}
            onPress={() => click(i)} testID={`mem-card-${i}`}>
            <Text style={gs.memCardText}>{(revealed[i] || matched[i]) ? (card.emoji || card.label || '★') : '?'}</Text>
          </TouchableOpacity>
        ))}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', padding: SPACING.md, gap: 8 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 2, padding: 6, borderRadius: RADIUS.sm, backgroundColor: COLORS.card },
  backText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  sponsor: { color: COLORS.textMuted, fontSize: 10, fontWeight: '700', letterSpacing: 1.5 },
  gameTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900' },
  content: { padding: SPACING.md, paddingBottom: 40 },
  unsupported: { alignItems: 'center', gap: 12, paddingVertical: 40 },
  unsupportedText: { color: COLORS.textDim, fontSize: FONT.sm },
  playNowBtn: { backgroundColor: COLORS.primary, paddingHorizontal: 20, paddingVertical: 10, borderRadius: RADIUS.md },
  playNowText: { color: '#fff', fontWeight: '700' },
  resultOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'center', alignItems: 'center', padding: SPACING.xl },
  resultCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.xl, padding: SPACING.xl, alignItems: 'center', width: '100%', maxWidth: 340 },
  resultTitle: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900', marginTop: SPACING.md, marginBottom: SPACING.sm },
  prizeName: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '700', textAlign: 'center' },
  prizeDesc: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', marginTop: 4 },
  bigcoinCredit: { color: COLORS.gold, fontSize: FONT.md, fontWeight: '700', marginTop: SPACING.sm },
  claimBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingVertical: 14, paddingHorizontal: 24, borderRadius: RADIUS.lg, marginTop: SPACING.lg },
  claimText: { color: '#fff', fontWeight: '700', fontSize: FONT.md },
  walletBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: SPACING.md, paddingVertical: 10, paddingHorizontal: 20, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.secondary },
  walletBtnText: { color: COLORS.secondary, fontWeight: '700', fontSize: FONT.sm },
  quizScore: { color: COLORS.gold, fontSize: FONT.md, fontWeight: '700', letterSpacing: 1, marginTop: 4 },
  closeResultBtn: { marginTop: SPACING.lg, paddingVertical: 12, paddingHorizontal: 20, borderRadius: RADIUS.md, backgroundColor: COLORS.bg },
  closeResultText: { color: COLORS.textDim, fontWeight: '700' },
});

const gs = StyleSheet.create({
  gameWrap: { alignItems: 'center', paddingVertical: SPACING.lg },
  instruction: { color: COLORS.textDim, fontSize: FONT.md, fontWeight: '600', marginBottom: SPACING.md, textAlign: 'center' },
  /* Spin */
  wheelWrap: { width: 220, height: 220, alignItems: 'center', justifyContent: 'center', marginBottom: SPACING.lg },
  pointer: { position: 'absolute', top: -4, zIndex: 10 },
  wheel: { width: 200, height: 200, borderRadius: 100, alignItems: 'center', justifyContent: 'center' },
  wheelSeg: { position: 'absolute', alignItems: 'center' },
  wheelSegText: { color: '#fff', fontSize: 9, fontWeight: '700', letterSpacing: 0.5 },
  wheelCenter: { color: '#fff', fontSize: FONT.xl, fontWeight: '900' },
  /* Scratch */
  scratchGrid: { flexDirection: 'row', flexWrap: 'wrap', width: 250, gap: 4, justifyContent: 'center', marginBottom: SPACING.md },
  scratchCell: { width: 44, height: 44, borderRadius: RADIUS.sm, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  scratchQ: { color: COLORS.textMuted, fontSize: FONT.lg, fontWeight: '800' },
  progressBar: { width: 200, height: 6, backgroundColor: COLORS.cardBorder, borderRadius: 3, overflow: 'hidden' },
  progressFill: { height: 6, borderRadius: 3 },
  progressLabel: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1, marginTop: 4 },
  /* Quiz */
  quizMeta: { flexDirection: 'row', justifyContent: 'space-between', width: '100%', marginBottom: 6 },
  quizProgress: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1 },
  quizTimer: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  timerBar: { width: '100%', height: 4, backgroundColor: COLORS.cardBorder, borderRadius: 2, marginBottom: SPACING.md, overflow: 'hidden' },
  timerFill: { height: 4, borderRadius: 2 },
  quizPrompt: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800', textAlign: 'center', marginBottom: SPACING.lg, lineHeight: 24 },
  quizOption: { flexDirection: 'row', alignItems: 'center', gap: 12, width: '100%', backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, padding: SPACING.md, marginBottom: 8 },
  optionLetter: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '800', width: 24, textAlign: 'center' },
  optionText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  quizRule: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1, marginTop: SPACING.sm },
  /* Mystery */
  boxGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm, justifyContent: 'center' },
  box: { width: 90, height: 90, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  boxQ: { color: COLORS.textMuted, fontSize: 28, fontWeight: '900' },
  boxLabel: { color: COLORS.textDim, fontSize: 10, fontWeight: '600', marginTop: 4 },
  /* Word */
  maskRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 4, justifyContent: 'center', marginBottom: SPACING.md },
  tile: { width: 28, height: 36, borderRadius: 4, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  tileBlank: { borderColor: COLORS.primary },
  tileText: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
  hint: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md },
  wordInput: { width: '100%', backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 14, paddingVertical: 10, color: COLORS.text, fontSize: FONT.md, marginBottom: SPACING.sm, textAlign: 'center' },
  /* Slot */
  slotRow: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.lg },
  slotReel: { width: 70, height: 80, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 2, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  /* Memory */
  memGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, justifyContent: 'center', maxWidth: 320 },
  memCard: { width: 56, height: 56, borderRadius: RADIUS.sm, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, alignItems: 'center', justifyContent: 'center' },
  memCardText: { fontSize: 18, fontWeight: '700', color: '#fff' },
  /* Shared */
  actionBtn: { paddingVertical: 14, paddingHorizontal: 28, borderRadius: RADIUS.lg, marginTop: SPACING.md },
  actionText: { color: '#fff', fontWeight: '800', fontSize: FONT.md, letterSpacing: 0.5 },
});
