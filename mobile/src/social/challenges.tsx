// FUUSIC Arena — Play-With-Friends challenges + weekly score leaderboard (mobile).
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Image as ExpoImage } from 'expo-image';
import { TSPACE, TRADIUS, TFONT } from '../constants/tube';
import { useThemeTokens } from '../theme/ThemeProvider';
import type { ThemeTokens } from '../theme/tokens';
import api from '../api/client';
import MiniToast from '../components/MiniToast';

const GAME_ICON: any = { trivia: 'help-circle', quiz: 'film' };

function Avatar({ name, url, size = 36 }: any) {
  const initials = (name || '?').split(' ').map((x: string) => x[0]).slice(0, 2).join('').toUpperCase();
  if (url) return <ExpoImage source={{ uri: url }} style={{ width: size, height: size, borderRadius: size / 2 }} />;
  return (
    <LinearGradient colors={['#a855f7', '#ec4899']}
      style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: '#fff', fontWeight: '900', fontSize: size * 0.36 }}>{initials}</Text>
    </LinearGradient>
  );
}

export function ChallengesTab() {
  const t = useThemeTokens();
  const s = makeStyles(t);
  const [sub, setSub] = useState<'challenges' | 'leaderboard'>('challenges');
  const [toast, setToast] = useState<string | null>(null);
  return (
    <View style={{ flex: 1 }} testID="arena-tab">
      <View style={s.subTabRow}>
        <SubTab t={t} active={sub === 'challenges'} onPress={() => setSub('challenges')}
          icon="flash" label="Challenges" testID="arena-subtab-challenges" />
        <SubTab t={t} active={sub === 'leaderboard'} onPress={() => setSub('leaderboard')}
          icon="trophy" label="Leaderboard" testID="arena-subtab-leaderboard" />
      </View>
      {sub === 'challenges'
        ? <ChallengesList t={t} notify={setToast} />
        : <ScoreLeaderboard t={t} />}
      <MiniToast message={toast} onDone={() => setToast(null)} />
    </View>
  );
}

function SubTab({ t, active, onPress, icon, label, testID }: any) {
  const s = makeStyles(t);
  return (
    <Pressable onPress={onPress} testID={testID} style={[s.subTab, active && s.subTabOn]}>
      <Ionicons name={icon} size={15} color={active ? '#fff' : t.textDim} />
      <Text style={[s.subTabTxt, { color: active ? '#fff' : t.textDim }]}>{label}</Text>
    </Pressable>
  );
}

/* ─────────────────────── Challenges list ─────────────────────── */
function ChallengesList({ t, notify }: any) {
  const s = makeStyles(t);
  const [data, setData] = useState<any>({ invites: [], active: [], completed: [] });
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [playCid, setPlayCid] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const { data } = await api.get('/arena/challenges'); setData(data); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const act = async (cid: string, action: string) => {
    try { await api.post(`/arena/challenges/${cid}/${action}`); load(); }
    catch (_) { notify('Could not update challenge'); }
  };

  if (loading) return <View style={s.center}><ActivityIndicator color={t.magenta} /></View>;

  const empty = !data.invites.length && !data.active.length && !data.completed.length;
  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 140, gap: 16 }}
      showsVerticalScrollIndicator={false} testID="arena-challenges">
      <Pressable onPress={() => setCreateOpen(true)} testID="arena-new-challenge-btn">
        <LinearGradient colors={['#9333EA', '#EC4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={s.cta}>
          <Ionicons name="add" size={18} color="#fff" />
          <Text style={s.ctaTxt}>Challenge a friend</Text>
        </LinearGradient>
      </Pressable>

      {empty && (
        <View style={[s.card, { alignItems: 'center', paddingVertical: 36 }]} testID="arena-empty">
          <Ionicons name="flash" size={32} color={t.magenta} />
          <Text style={[s.cardTitle, { marginTop: 10 }]}>No challenges yet</Text>
          <Text style={s.sub}>Challenge a friend to a quiz and climb the leaderboard.</Text>
        </View>
      )}

      {data.invites.length > 0 && (
        <Section t={t} title="Invitations" count={data.invites.length}>
          {data.invites.map((c: any) => (
            <InviteCard key={c.id} t={t} c={c}
              onAccept={() => act(c.id, 'accept')} onDecline={() => act(c.id, 'decline')} />
          ))}
        </Section>
      )}

      {data.active.length > 0 && (
        <Section t={t} title="Active" count={data.active.length}>
          {data.active.map((c: any) => (
            <ActiveCard key={c.id} t={t} c={c} onPlay={() => setPlayCid(c.id)} />
          ))}
        </Section>
      )}

      {data.completed.length > 0 && (
        <Section t={t} title="Results" count={data.completed.length}>
          {data.completed.map((c: any) => <CompletedCard key={c.id} t={t} c={c} />)}
        </Section>
      )}

      {createOpen && (
        <CreateChallengeSheet t={t} notify={notify}
          onClose={() => setCreateOpen(false)}
          onCreated={() => { setCreateOpen(false); load(); }} />
      )}
      {playCid && (
        <QuizRunner t={t} cid={playCid} notify={notify}
          onClose={() => { setPlayCid(null); load(); }} />
      )}
    </ScrollView>
  );
}

function Section({ t, title, count, children }: any) {
  const s = makeStyles(t);
  return (
    <View style={{ gap: 10 }}>
      <Text style={s.sectionTitle}>{title} · {count}</Text>
      <View style={{ gap: 10 }}>{children}</View>
    </View>
  );
}

function GameBadge({ t, gameKey }: any) {
  return (
    <LinearGradient colors={['rgba(147,51,234,0.35)', 'rgba(236,72,153,0.35)']}
      style={{ width: 42, height: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center' }}>
      <Ionicons name={GAME_ICON[gameKey] || 'help-circle'} size={19} color={t.magenta} />
    </LinearGradient>
  );
}

function InviteCard({ t, c, onAccept, onDecline }: any) {
  const s = makeStyles(t);
  return (
    <View style={[s.card, s.row]} testID={`arena-invite-${c.id}`}>
      <GameBadge t={t} gameKey={c.game_key} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.cardTitle} numberOfLines={1}>{c.title}</Text>
        <Text style={s.sub} numberOfLines={1}>{c.host?.name} challenged you · {c.prize_points} pts</Text>
      </View>
      <Pressable onPress={onDecline} testID={`arena-decline-${c.id}`} style={s.iconBtn}>
        <Ionicons name="close" size={16} color={t.textDim} />
      </Pressable>
      <Pressable onPress={onAccept} testID={`arena-accept-${c.id}`}>
        <LinearGradient colors={['#9333EA', '#EC4899']} style={s.pill}>
          <Text style={s.pillTxt}>Accept</Text>
        </LinearGradient>
      </Pressable>
    </View>
  );
}

function ActiveCard({ t, c, onPlay }: any) {
  const s = makeStyles(t);
  const canPlay = c.i_joined && !c.i_submitted;
  return (
    <View style={[s.card, s.row]} testID={`arena-active-${c.id}`}>
      <GameBadge t={t} gameKey={c.game_key} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={s.cardTitle} numberOfLines={1}>{c.title}</Text>
        <Text style={s.sub} numberOfLines={1}>
          {c.participants.length} playing · {c.mode === 'group' ? 'Group' : 'Head-to-head'} · {c.prize_points} pts
        </Text>
      </View>
      {canPlay ? (
        <Pressable onPress={onPlay} testID={`arena-play-${c.id}`}>
          <LinearGradient colors={['#9333EA', '#EC4899']} style={[s.pill, s.row, { gap: 5 }]}>
            <Ionicons name="flash" size={14} color="#fff" />
            <Text style={s.pillTxt}>Play</Text>
          </LinearGradient>
        </Pressable>
      ) : (
        <View style={[s.row, { gap: 5 }]} testID={`arena-waiting-${c.id}`}>
          <Ionicons name="time" size={14} color={t.gold} />
          <Text style={{ color: t.gold, fontWeight: '800', fontSize: TFONT.sm }}>Waiting</Text>
        </View>
      )}
    </View>
  );
}

function CompletedCard({ t, c }: any) {
  const s = makeStyles(t);
  return (
    <View style={s.card} testID={`arena-completed-${c.id}`}>
      <View style={s.row}>
        <GameBadge t={t} gameKey={c.game_key} />
        <View style={{ flex: 1, minWidth: 0 }}>
          <Text style={s.cardTitle} numberOfLines={1}>{c.title}</Text>
          <Text style={{ fontSize: TFONT.sm, fontWeight: '800', color: c.i_won ? t.green : t.textDim }}>
            {c.i_won ? `You won · +${c.prize_points} pts` : `${c.winner?.name || 'Someone'} won`}
          </Text>
        </View>
        {c.i_won && <Ionicons name="trophy" size={20} color={t.gold} />}
      </View>
      {Array.isArray(c.scoreboard) && (
        <View style={{ marginTop: 12, gap: 8 }}>
          {c.scoreboard.map((b: any, i: number) => (
            <View key={i} style={[s.row, { gap: 8 }]} testID={`arena-score-row-${c.id}-${i}`}>
              <Text style={{ width: 18, color: t.textMuted, fontWeight: '900' }}>{i + 1}</Text>
              <Avatar name={b.user?.name} url={b.user?.avatar_url} size={24} />
              <Text style={{ flex: 1, color: t.text, fontWeight: '600' }} numberOfLines={1}>{b.user?.name}</Text>
              <Text style={{ color: t.text, fontWeight: '900' }}>{b.score}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

/* ─────────────────────── Create sheet ─────────────────────── */
function CreateChallengeSheet({ t, onClose, onCreated, notify }: any) {
  const s = makeStyles(t);
  const [games, setGames] = useState<any[]>([]);
  const [friends, setFriends] = useState<any[]>([]);
  const [gameKey, setGameKey] = useState('trivia');
  const [mode, setMode] = useState<'h2h' | 'group'>('h2h');
  const [picked, setPicked] = useState<string[]>([]);
  const [prize, setPrize] = useState('100');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get('/arena/games').then(({ data }) => setGames(data.games || [])).catch(() => {});
    api.get('/social/friends').then(({ data }) => setFriends(data.friends || [])).catch(() => {});
  }, []);

  const toggleFriend = (uid: string) => setPicked((p) => {
    if (p.includes(uid)) return p.filter((x) => x !== uid);
    if (mode === 'h2h') return [uid];
    return [...p, uid];
  });

  const create = async () => {
    if (mode === 'h2h' && picked.length !== 1) return notify('Pick one friend');
    if (mode === 'group' && picked.length < 2) return notify('Pick at least two friends');
    setSaving(true);
    try {
      await api.post('/arena/challenges', { game_key: gameKey, mode, invitees: picked, prize: Number(prize) || 100 });
      notify('Challenge sent!');
      onCreated();
    } catch (e: any) {
      notify(e?.response?.data?.detail?.code || 'Could not create challenge');
    } finally { setSaving(false); }
  };

  return (
    <Modal visible transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.backdrop} onPress={onClose} />
      <View style={s.sheet} testID="arena-create-modal">
        <View style={[s.row, { justifyContent: 'space-between', marginBottom: 16 }]}>
          <Text style={s.sheetTitle}>New challenge</Text>
          <Pressable onPress={onClose} testID="arena-create-close"><Ionicons name="close" size={22} color={t.textDim} /></Pressable>
        </View>
        <ScrollView showsVerticalScrollIndicator={false} style={{ maxHeight: 460 }}>
          <Text style={s.label}>GAME</Text>
          <View style={[s.row, { gap: 8, marginBottom: 16 }]}>
            {games.map((g) => {
              const on = gameKey === g.key;
              return (
                <Pressable key={g.key} onPress={() => setGameKey(g.key)} testID={`arena-create-game-${g.key}`}
                  style={[s.pickBox, on && s.pickBoxOn, { flex: 1 }]}>
                  <Ionicons name={GAME_ICON[g.key] || 'help-circle'} size={18} color={t.magenta} />
                  <Text style={[s.pickTxt, { color: t.text }]} numberOfLines={1}>{g.label}</Text>
                </Pressable>
              );
            })}
          </View>

          <Text style={s.label}>MODE</Text>
          <View style={[s.row, { gap: 8, marginBottom: 16 }]}>
            {[['h2h', 'Head-to-head'], ['group', 'Group']].map(([k, l]) => (
              <Pressable key={k} onPress={() => { setMode(k as any); setPicked([]); }} testID={`arena-create-mode-${k}`}
                style={[s.modeBtn, mode === k && s.pickBoxOn]}>
                <Text style={[s.pickTxt, { color: mode === k ? t.text : t.textDim }]}>{l}</Text>
              </Pressable>
            ))}
          </View>

          <Text style={s.label}>{mode === 'h2h' ? 'PICK A FRIEND' : 'PICK FRIENDS (2+)'}</Text>
          <View style={{ gap: 6, marginBottom: 16 }}>
            {friends.length === 0 && <Text style={s.sub}>Add friends first to challenge them.</Text>}
            {friends.map((f) => {
              const on = picked.includes(f.user_id);
              return (
                <Pressable key={f.user_id} onPress={() => toggleFriend(f.user_id)} testID={`arena-create-friend-${f.user_id}`}
                  style={[s.friendRow, on && s.pickBoxOn]}>
                  <Avatar name={f.name} url={f.avatar_url} size={32} />
                  <Text style={{ flex: 1, color: t.text, fontWeight: '700' }} numberOfLines={1}>{f.name}</Text>
                  {on && <Ionicons name="checkmark" size={18} color={t.magenta} />}
                </Pressable>
              );
            })}
          </View>

          <View style={[s.row, { justifyContent: 'space-between', marginBottom: 16 }]}>
            <Text style={{ color: t.text, fontWeight: '700' }}>Prize (BigPoints)</Text>
            <TextInput value={prize} onChangeText={setPrize} keyboardType="number-pad"
              testID="arena-create-prize" style={s.prizeInput} />
          </View>
        </ScrollView>

        <Pressable onPress={create} disabled={saving} testID="arena-create-submit">
          <LinearGradient colors={['#9333EA', '#EC4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }}
            style={[s.cta, saving && { opacity: 0.5 }]}>
            <Text style={s.ctaTxt}>{saving ? 'Sending…' : 'Send challenge'}</Text>
          </LinearGradient>
        </Pressable>
      </View>
    </Modal>
  );
}

/* ─────────────────────── Quiz runner ─────────────────────── */
function QuizRunner({ t, cid, onClose, notify }: any) {
  const s = makeStyles(t);
  const [q, setQ] = useState<any>(null);
  const [idx, setIdx] = useState(0);
  const [answers, setAnswers] = useState<number[]>([]);
  const [result, setResult] = useState<any>(null);
  const [submitting, setSubmitting] = useState(false);
  const startRef = useRef(Date.now());

  useEffect(() => {
    api.get(`/arena/challenges/${cid}/quiz`)
      .then(({ data }) => { setQ(data); startRef.current = Date.now(); })
      .catch(() => { notify('Could not load quiz'); onClose(); });
  }, [cid]);

  const choose = async (choiceIdx: number) => {
    const next = [...answers, choiceIdx];
    setAnswers(next);
    if (idx + 1 < q.questions.length) { setIdx(idx + 1); return; }
    setSubmitting(true);
    try {
      const { data } = await api.post(`/arena/challenges/${cid}/submit`,
        { answers: next, time_ms: Date.now() - startRef.current });
      setResult(data);
    } catch (e) { notify('Could not submit'); onClose(); }
    finally { setSubmitting(false); }
  };

  return (
    <Modal visible transparent animationType="fade" onRequestClose={onClose}>
      <View style={s.quizWrap} testID="arena-quiz">
        <View style={s.quizCard}>
          {!q && <View style={{ paddingVertical: 60 }}><ActivityIndicator color={t.magenta} /></View>}

          {q && !result && (
            <>
              <View style={[s.row, { justifyContent: 'space-between', marginBottom: 14 }]}>
                <Text style={{ color: t.magenta, fontWeight: '900', fontSize: TFONT.xs, letterSpacing: 1 }}>
                  {(q.game_label || '').toUpperCase()}
                </Text>
                <Text style={{ color: t.textDim, fontWeight: '700', fontSize: TFONT.sm }}>{idx + 1} / {q.questions.length}</Text>
              </View>
              <View style={s.progressTrack}>
                <View style={[s.progressFill, { width: `${(idx / q.questions.length) * 100}%` }]} />
              </View>
              <Text style={s.quizPrompt} testID="arena-quiz-prompt">{q.questions[idx].prompt}</Text>
              <View style={{ gap: 10 }}>
                {q.questions[idx].choices.map((ch: string, i: number) => (
                  <Pressable key={i} disabled={submitting} onPress={() => choose(i)} testID={`arena-quiz-choice-${i}`}
                    style={s.choice}>
                    <Text style={{ color: t.text, fontWeight: '700' }}>{ch}</Text>
                  </Pressable>
                ))}
              </View>
            </>
          )}

          {result && (
            <View style={{ alignItems: 'center', paddingVertical: 8 }} testID="arena-quiz-result">
              <Ionicons name="trophy" size={40} color={t.gold} />
              <Text style={{ color: t.text, fontWeight: '900', fontSize: 32, marginTop: 8 }}>{result.score}</Text>
              <Text style={s.sub}>{result.correct} / {result.total} correct</Text>
              <Text style={{ fontWeight: '900', marginVertical: 14, color: result.finalized ? (result.challenge?.i_won ? t.green : t.textDim) : t.gold, textAlign: 'center' }}>
                {result.finalized
                  ? (result.challenge?.i_won ? `🏆 You won +${result.challenge.prize_points} pts!` : `${result.challenge?.winner?.name || 'Your rival'} took this one.`)
                  : 'Waiting for your opponent to play…'}
              </Text>
              <Pressable onPress={onClose} testID="arena-quiz-close" style={{ width: '100%' }}>
                <LinearGradient colors={['#9333EA', '#EC4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={s.cta}>
                  <Text style={s.ctaTxt}>Done</Text>
                </LinearGradient>
              </Pressable>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

/* ─────────────────────── Leaderboard ─────────────────────── */
function ScoreLeaderboard({ t }: any) {
  const s = makeStyles(t);
  const [scope, setScope] = useState<'global' | 'friends'>('global');
  const [gameKey, setGameKey] = useState('all');
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/arena/leaderboard', { params: { scope, game_key: gameKey } });
      setData(data);
    } catch (_) {} finally { setLoading(false); }
  }, [scope, gameKey]);
  useEffect(() => { load(); }, [load]);

  const GAMES = [['all', 'All games'], ['trivia', 'Trivia'], ['quiz', 'Movie']];

  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 140, gap: 14 }}
      showsVerticalScrollIndicator={false} testID="arena-leaderboard">
      <View style={[s.row, { gap: 8 }]}>
        {[['global', 'Global'], ['friends', 'Friends']].map(([k, l]) => (
          <Pressable key={k} onPress={() => setScope(k as any)} testID={`arena-lb-scope-${k}`} style={{ flex: 1 }}>
            {scope === k ? (
              <LinearGradient colors={['#9333EA', '#EC4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 0 }} style={s.scopeBtn}>
                <Text style={[s.scopeTxt, { color: '#fff' }]}>{l}</Text>
              </LinearGradient>
            ) : (
              <View style={[s.scopeBtn, { backgroundColor: t.surface }]}>
                <Text style={[s.scopeTxt, { color: t.textDim }]}>{l}</Text>
              </View>
            )}
          </Pressable>
        ))}
      </View>
      <View style={[s.row, { gap: 6, flexWrap: 'wrap' }]}>
        {GAMES.map(([k, l]) => (
          <Pressable key={k} onPress={() => setGameKey(k)} testID={`arena-lb-game-${k}`}
            style={[s.chip, { backgroundColor: gameKey === k ? t.magenta : t.surface }]}>
            <Text style={{ color: gameKey === k ? '#fff' : t.textDim, fontWeight: '800', fontSize: TFONT.xs }}>{l}</Text>
          </Pressable>
        ))}
      </View>

      {loading && <View style={s.center}><ActivityIndicator color={t.magenta} /></View>}

      {!loading && data && (
        <>
          {data.items.length === 0 && (
            <View style={[s.card, { alignItems: 'center', paddingVertical: 34 }]} testID="arena-lb-empty">
              <Ionicons name="trophy" size={28} color={t.magenta} />
              <Text style={[s.cardTitle, { marginTop: 8 }]}>No scores this week yet</Text>
              <Text style={s.sub}>Play a challenge to get on the board.</Text>
            </View>
          )}
          {data.items.length > 0 && (
            <View style={[s.card, { padding: 6 }]}>
              {data.items.map((it: any) => <LbRow key={it.rank} t={t} it={it} />)}
            </View>
          )}
          {data.me && !data.items.some((i: any) => i.is_me) && (
            <View style={[s.card, { padding: 6 }]} testID="arena-lb-me">
              <LbRow t={t} it={data.me} />
            </View>
          )}
          <Text style={{ textAlign: 'center', color: t.textMuted, fontSize: TFONT.xs }}>Week {data.week} · resets Monday</Text>
        </>
      )}
    </ScrollView>
  );
}

function LbRow({ t, it }: any) {
  const s = makeStyles(t);
  const medal = it.rank <= 3;
  return (
    <View style={[s.lbRow, it.is_me && { backgroundColor: 'rgba(147,51,234,0.14)' }]} testID={`arena-lb-row-${it.rank}`}>
      <Text style={{ width: 26, textAlign: 'center', fontWeight: '900', color: medal ? t.gold : t.textMuted }}>{it.rank}</Text>
      <Avatar name={it.user?.name} url={it.user?.avatar_url} size={34} />
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={{ color: t.text, fontWeight: '700' }} numberOfLines={1}>{it.user?.name || 'Player'}{it.is_me ? ' (You)' : ''}</Text>
        <Text style={{ color: t.textMuted, fontSize: TFONT.xs }}>{it.plays} play{it.plays === 1 ? '' : 's'}</Text>
      </View>
      <Text style={{ color: t.magenta, fontWeight: '900' }}>{it.score}</Text>
    </View>
  );
}

function makeStyles(t: ThemeTokens) {
  return StyleSheet.create({
    subTabRow: { flexDirection: 'row', gap: 8, paddingHorizontal: TSPACE.md, paddingTop: TSPACE.sm, paddingBottom: 4 },
    subTab: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 9, borderRadius: TRADIUS.full, backgroundColor: t.surface },
    subTabOn: { backgroundColor: t.magenta },
    subTabTxt: { fontWeight: '800', fontSize: TFONT.sm },
    center: { paddingVertical: 50, alignItems: 'center' },
    cta: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, paddingVertical: 14, borderRadius: TRADIUS.lg },
    ctaTxt: { color: '#fff', fontWeight: '900', fontSize: TFONT.md },
    card: { backgroundColor: t.card, borderWidth: 1, borderColor: t.cardBorder, borderRadius: TRADIUS.xl, padding: 14 },
    row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
    cardTitle: { color: t.text, fontWeight: '900', fontSize: TFONT.md },
    sub: { color: t.textDim, fontSize: TFONT.sm, marginTop: 2, textAlign: 'center' },
    sectionTitle: { color: t.textMuted, fontWeight: '900', fontSize: TFONT.xs, letterSpacing: 1.2, textTransform: 'uppercase' },
    iconBtn: { width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: t.surface },
    pill: { paddingHorizontal: 16, paddingVertical: 9, borderRadius: TRADIUS.full, alignItems: 'center', justifyContent: 'center' },
    pillTxt: { color: '#fff', fontWeight: '800', fontSize: TFONT.sm },
    backdrop: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(0,0,0,0.6)' },
    sheet: { position: 'absolute', left: 0, right: 0, bottom: 0, backgroundColor: t.elevated, borderTopLeftRadius: 26, borderTopRightRadius: 26, padding: 20, paddingBottom: 34 },
    sheetTitle: { color: t.text, fontWeight: '900', fontSize: TFONT.xl },
    label: { color: t.textMuted, fontWeight: '900', fontSize: TFONT.xs, letterSpacing: 1.2, marginBottom: 8 },
    pickBox: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 12, borderRadius: TRADIUS.lg, borderWidth: 1, borderColor: t.cardBorder, backgroundColor: t.surface },
    pickBoxOn: { borderColor: t.magenta, backgroundColor: 'rgba(147,51,234,0.14)' },
    pickTxt: { fontWeight: '800', fontSize: TFONT.sm },
    modeBtn: { flex: 1, alignItems: 'center', paddingVertical: 11, borderRadius: TRADIUS.lg, borderWidth: 1, borderColor: t.cardBorder, backgroundColor: t.surface },
    friendRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 10, borderRadius: TRADIUS.lg, borderWidth: 1, borderColor: t.cardBorder, backgroundColor: t.surface },
    prizeInput: { width: 92, borderRadius: TRADIUS.md, backgroundColor: t.inputBg, borderWidth: 1, borderColor: t.inputBorder, paddingHorizontal: 12, paddingVertical: 8, color: t.text, textAlign: 'right', fontWeight: '800' },
    quizWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', alignItems: 'center', justifyContent: 'center', padding: 20 },
    quizCard: { width: '100%', maxWidth: 440, backgroundColor: t.elevated, borderRadius: 26, padding: 20 },
    progressTrack: { height: 4, borderRadius: 2, backgroundColor: t.surface, marginBottom: 18, overflow: 'hidden' },
    progressFill: { height: 4, backgroundColor: t.magenta },
    quizPrompt: { color: t.text, fontWeight: '900', fontSize: TFONT.lg, marginBottom: 18 },
    choice: { padding: 14, borderRadius: TRADIUS.lg, borderWidth: 1, borderColor: t.cardBorder, backgroundColor: t.surface },
    scopeBtn: { paddingVertical: 10, borderRadius: TRADIUS.full, alignItems: 'center' },
    scopeTxt: { fontWeight: '800', fontSize: TFONT.sm },
    chip: { paddingHorizontal: 14, paddingVertical: 7, borderRadius: TRADIUS.full },
    lbRow: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, borderRadius: TRADIUS.lg },
  });
}

export default ChallengesTab;
