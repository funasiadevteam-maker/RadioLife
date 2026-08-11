import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, Share,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS, common } from '../../../src/constants/theme';
import { useTriviaRoom } from '../../../src/stores/useTriviaRoom';
import api from '../../../src/api/client';

export default function TriviaRoomScreen() {
  const { code } = useLocalSearchParams<{ code: string }>();
  const router = useRouter();

  const connect = useTriviaRoom((s) => s.connect);
  const disconnect = useTriviaRoom((s) => s.disconnect);
  const sendAnswer = useTriviaRoom((s) => s.sendAnswer);
  const ws = useTriviaRoom((s) => s.ws);
  const room = useTriviaRoom((s) => s.room);
  const phase = useTriviaRoom((s) => s.phase);
  const question = useTriviaRoom((s) => s.question);
  const deadlineMs = useTriviaRoom((s) => s.deadlineMs);
  const serverSkew = useTriviaRoom((s) => s.serverSkewMs);
  const you = useTriviaRoom((s) => s.you);
  const reveal = useTriviaRoom((s) => s.reveal);
  const leaderboard = useTriviaRoom((s) => s.leaderboard);
  const finalScores = useTriviaRoom((s) => s.finalScores);
  const answersIn = useTriviaRoom((s) => s.answersIn);
  const totalPlayers = useTriviaRoom((s) => s.totalPlayers);
  const connected = useTriviaRoom((s) => s.connected);
  const kicked = useTriviaRoom((s) => s.kicked);
  const error = useTriviaRoom((s) => s.error);
  const announcement = useTriviaRoom((s) => s.announcement);

  const [chosenId, setChosenId] = useState<string | null>(null);
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    if (code) connect(code);
    return () => disconnect();
  }, [code]);

  // Kick handler
  useEffect(() => {
    if (!kicked) return;
    Alert.alert('Removed', "You've been removed from this room");
    router.replace('/(tabs)/trivia');
  }, [kicked]);

  // Error handler
  useEffect(() => {
    if (!error) return;
    if (error.code === 'room_not_found') {
      Alert.alert('Not Found', `No room with code ${code}.`);
      router.replace('/trivia/join');
    } else if (error.code === 'room_in_progress') {
      Alert.alert('In Progress', 'Room is mid-game — wait for next round.');
      router.replace('/(tabs)/trivia');
    }
  }, [error]);

  // Timer
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(t);
  }, []);

  // Reset choice on new question
  useEffect(() => { setChosenId(null); }, [question?.id]);

  const isHost = you?.user_id && room?.host_user_id === you.user_id;
  const remainingMs = deadlineMs ? Math.max(0, deadlineMs - (now - serverSkew)) : 0;
  const phaseTotalMs = phase === 'question' ? 15000 : phase === 'reveal' ? 4000 : phase === 'leaderboard' ? 4000 : 0;
  const timerPct = phaseTotalMs > 0 ? Math.max(0, Math.min(100, (remainingMs / phaseTotalMs) * 100)) : 0;

  const startGame = async () => {
    try {
      await api.post(`/trivia/rooms/${code}/start`);
    } catch (e: any) {
      const d = e?.response?.data?.detail;
      const msg = (d && typeof d === 'object' && d.message) ? d.message : (typeof d === 'string' ? d : 'Failed to start.');
      Alert.alert('Error', msg);
    }
  };

  const shareInvite = async () => {
    try {
      await Share.share({ message: `Join my RadioLife trivia room! Code: ${code}` });
    } catch {}
  };

  const copyCode = async () => {
    try {
      const { default: Clipboard } = await import('expo-clipboard');
      await Clipboard.setStringAsync(code || '');
      Alert.alert('Copied', 'Room code copied!');
    } catch {}
  };

  if (!ws || !room) {
    return (
      <View style={common.center} testID="trivia-room-connecting">
        <ActivityIndicator size="large" color={COLORS.primary} />
        <Text style={{ color: COLORS.textDim, marginTop: 12, fontSize: FONT.sm }}>Joining room…</Text>
      </View>
    );
  }

  return (
    <SafeAreaView style={common.screen} testID="trivia-room">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        {/* Venue announcement banner */}
        {announcement && (
          <TouchableOpacity
            style={st.announcement}
            onPress={() => useTriviaRoom.setState({ announcement: null })}
            testID="trivia-room-announcement"
            activeOpacity={0.8}
          >
            {announcement.emoji && <Text style={{ fontSize: 28 }}>{announcement.emoji}</Text>}
            <View style={{ flex: 1 }}>
              <Text style={st.annFrom}>From {announcement.venue_name || 'the venue'}</Text>
              <Text style={st.annMsg}>{announcement.message}</Text>
            </View>
          </TouchableOpacity>
        )}

        {/* Top strip */}
        <View style={st.topStrip}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={st.roomCode} testID="trivia-room-code">{code}</Text>
            <TouchableOpacity onPress={copyCode} testID="trivia-room-copy" style={st.iconBtn}>
              <Ionicons name="copy-outline" size={14} color={COLORS.textDim} />
            </TouchableOpacity>
            <TouchableOpacity onPress={shareInvite} testID="trivia-room-share" style={st.iconBtn}>
              <Ionicons name="share-outline" size={14} color={COLORS.textDim} />
            </TouchableOpacity>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <View style={[st.connDot, { backgroundColor: connected ? COLORS.green : COLORS.red }]} />
            <Ionicons name="people" size={12} color={COLORS.textDim} />
            <Text style={st.playerCount}>{room.players.length}/{room.max_players}</Text>
          </View>
        </View>

        {/* ── LOBBY ── */}
        {phase === 'lobby' && (
          <View style={common.card} testID="trivia-room-lobby">
            <Text style={common.sectionTitle}>Lobby · waiting to start</Text>
            <Text style={st.lobbyTitle}>
              {room.players.length === 1 ? 'Just you for now.' : 'Players in'}
            </Text>
            <View testID="trivia-room-players" style={{ gap: SPACING.sm, marginVertical: SPACING.md }}>
              {room.players.map((p: any) => (
                <View key={p.user_id} style={st.playerRow} testID={`trivia-room-player-${p.user_id}`}>
                  <View style={st.playerAvatar}>
                    <Text style={st.playerInitial}>{(p.name || '?')[0]}</Text>
                  </View>
                  <Text style={st.playerName}>{p.name}</Text>
                  {p.user_id === room.host_user_id && (
                    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                      <Ionicons name="diamond" size={10} color={COLORS.gold} />
                      <Text style={st.hostLabel}>Host</Text>
                    </View>
                  )}
                  <View style={[st.connDotSmall, { backgroundColor: p.connected ? COLORS.green : COLORS.textDim }]} />
                </View>
              ))}
            </View>
            {isHost ? (
              <>
                <TouchableOpacity
                  style={[common.btnPrimary, room.players.length < 2 && { opacity: 0.5 }]}
                  onPress={startGame}
                  disabled={room.players.length < 2}
                  testID="trivia-room-start"
                >
                  <Text style={common.btnPrimaryText}>Start round</Text>
                  <Ionicons name="chevron-forward" size={14} color="#fff" />
                </TouchableOpacity>
                {room.players.length < 2 && (
                  <Text style={st.hint} testID="trivia-room-start-hint">
                    Need <Text style={{ color: COLORS.primary }}>1 more player</Text> to start.
                  </Text>
                )}
              </>
            ) : (
              <Text style={st.waitText}>Waiting for the host to start…</Text>
            )}
          </View>
        )}

        {/* ── QUESTION / REVEAL ── */}
        {(phase === 'question' || phase === 'reveal') && question && (
          <>
            <View style={st.timerTrack}>
              <View style={[st.timerFill, { width: `${timerPct}%` }]} />
            </View>
            <View style={common.card} testID="trivia-room-question">
              <View style={st.qTopRow}>
                <Text style={st.qLabel}>Q {(room.current_index ?? 0) + 1} / {room.total_questions || 10}</Text>
                <Text style={st.qLabel}>{answersIn}/{totalPlayers || room.players.length} answered</Text>
              </View>
              <Text style={st.prompt} testID="trivia-room-prompt">{question.prompt}</Text>
              <View style={{ gap: SPACING.sm, marginTop: SPACING.md }} testID="trivia-room-choices">
                {question.choices.map((c: any) => {
                  const isChosen = chosenId === c.id;
                  const isCorrect = reveal && (reveal as any).correct_choice_id === c.id;
                  const isWrongPick = reveal && isChosen && !isCorrect;
                  const bg = phase === 'reveal'
                    ? (isCorrect ? 'rgba(74,222,128,0.12)' : isWrongPick ? 'rgba(251,113,133,0.12)' : COLORS.surface)
                    : (isChosen ? 'rgba(59,130,246,0.1)' : COLORS.surface);
                  const border = phase === 'reveal'
                    ? (isCorrect ? COLORS.green : isWrongPick ? COLORS.red : COLORS.surfaceBorder)
                    : (isChosen ? COLORS.secondary : COLORS.surfaceBorder);
                  return (
                    <TouchableOpacity
                      key={c.id}
                      disabled={phase !== 'question' || !!chosenId}
                      onPress={() => { setChosenId(c.id); sendAnswer(question.id, c.id); }}
                      testID={`trivia-room-choice-${c.id}`}
                      style={[st.choiceBtn, { backgroundColor: bg, borderColor: border }]}
                    >
                      <Text style={st.choiceLabel}>{c.id.toUpperCase()}</Text>
                      <Text style={st.choiceText}>{c.text}</Text>
                      {phase === 'reveal' && isCorrect && <Ionicons name="checkmark-circle" size={16} color={COLORS.green} />}
                      {phase === 'reveal' && isWrongPick && <Ionicons name="close-circle" size={16} color={COLORS.red} />}
                    </TouchableOpacity>
                  );
                })}
              </View>
              {chosenId && phase === 'question' && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: SPACING.md }}>
                  <ActivityIndicator size="small" color={COLORS.secondary} />
                  <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }}>You answered. Waiting for others…</Text>
                </View>
              )}
            </View>
          </>
        )}

        {/* ── LEADERBOARD ── */}
        {phase === 'leaderboard' && (
          <View style={common.card} testID="trivia-room-leaderboard">
            <Text style={common.sectionTitle}>Standings</Text>
            {leaderboard.map((p) => (
              <View key={p.user_id} style={st.lbRow} testID={`trivia-room-lb-${p.user_id}`}>
                <Text style={st.lbRank}>#{p.rank}</Text>
                <Text style={st.lbName}>{p.name}</Text>
                <Text style={st.lbScore}>{p.score}</Text>
              </View>
            ))}
          </View>
        )}

        {/* ── FINAL ── */}
        {phase === 'done' && (
          <View style={common.card} testID="trivia-room-final">
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: SPACING.md }}>
              <Ionicons name="trophy" size={14} color={COLORS.gold} />
              <Text style={common.sectionTitle}>Final scoreboard</Text>
            </View>
            {finalScores.map((p) => (
              <View key={p.user_id} style={st.lbRow} testID={`trivia-room-final-${p.user_id}`}>
                <Text style={st.lbRank}>#{p.rank}</Text>
                <Text style={st.lbName}>{p.name}</Text>
                <Text style={st.lbScore}>{p.score}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
                  <Ionicons name="diamond" size={10} color={COLORS.gold} />
                  <Text style={{ fontSize: 11, color: COLORS.gold, fontWeight: '700' }}>+{p.bigcoin_awarded}</Text>
                </View>
              </View>
            ))}
            <TouchableOpacity
              style={[common.btnPrimary, { marginTop: SPACING.md }]}
              onPress={() => router.replace('/(tabs)/trivia')}
              testID="trivia-room-finish-back"
            >
              <Text style={common.btnPrimaryText}>Back to trivia</Text>
              <Ionicons name="chevron-forward" size={14} color="#fff" />
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  announcement: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.md,
    backgroundColor: 'rgba(242,107,42,0.08)', borderWidth: 2, borderColor: COLORS.primary,
    borderRadius: RADIUS.lg, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm,
    marginBottom: SPACING.md,
  },
  annFrom: { fontSize: 10, color: COLORS.primary, fontWeight: '700', letterSpacing: 2, textTransform: 'uppercase' },
  annMsg: { fontSize: 16, fontWeight: '800', color: COLORS.text, marginTop: 2 },
  topStrip: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.md, flexWrap: 'wrap', gap: 8 },
  roomCode: { fontSize: 20, fontWeight: '900', color: COLORS.secondary, letterSpacing: 3 },
  iconBtn: { padding: 8, borderWidth: 1, borderColor: COLORS.surfaceBorder, borderRadius: RADIUS.sm },
  connDot: { width: 8, height: 8, borderRadius: 4 },
  connDotSmall: { width: 6, height: 6, borderRadius: 3, marginLeft: 'auto' },
  playerCount: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', letterSpacing: 2 },
  lobbyTitle: { fontSize: 22, fontWeight: '900', color: COLORS.text },
  playerRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    borderWidth: 1, borderColor: 'rgba(255,255,255,0.06)', borderRadius: RADIUS.md,
    paddingHorizontal: 12, paddingVertical: 10,
  },
  playerAvatar: { width: 28, height: 28, borderRadius: 14, backgroundColor: COLORS.surface, alignItems: 'center', justifyContent: 'center' },
  playerInitial: { fontSize: 12, color: COLORS.textDim },
  playerName: { fontSize: 14, color: COLORS.text, fontWeight: '600' },
  hostLabel: { fontSize: 10, color: COLORS.gold, fontWeight: '700', letterSpacing: 1.5 },
  hint: { fontSize: 12, color: COLORS.textDim, marginTop: SPACING.sm },
  waitText: { fontSize: 13, color: COLORS.textDim },
  timerTrack: { height: 4, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.06)', marginBottom: SPACING.md, overflow: 'hidden' },
  timerFill: { height: '100%', borderRadius: 2, backgroundColor: COLORS.secondary },
  qTopRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: SPACING.sm },
  qLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', letterSpacing: 2 },
  prompt: { fontSize: 22, fontWeight: '900', color: COLORS.text, lineHeight: 28 },
  choiceBtn: { flexDirection: 'row', alignItems: 'center', gap: 12, borderWidth: 1, borderRadius: RADIUS.md, paddingHorizontal: 16, paddingVertical: 14 },
  choiceLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '700', width: 20 },
  choiceText: { flex: 1, fontSize: 14, color: COLORS.text },
  lbRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: 'rgba(255,255,255,0.06)' },
  lbRank: { fontSize: 12, color: COLORS.textDim, fontWeight: '700', width: 30 },
  lbName: { flex: 1, fontSize: 14, color: COLORS.text, fontWeight: '600' },
  lbScore: { fontSize: 16, fontWeight: '800', color: COLORS.secondary },
});
