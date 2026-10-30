/* FUUSIC Interactive News — mobile (listen-only in preview).
 *
 * Mirrors the web Interactive News: six program modes, a verified news
 * program you Press-Play through, Follow This Story, and the sponsor
 * acknowledgement. The live "Talk to Fun AI" voice anchor needs native
 * microphone streaming to Grok, which only runs in a published app build
 * (not Expo Go / web preview) — so here it opens an explainer and the news
 * program stays fully usable. See src/fun-ai/grokVoiceNative.ts to enable it.
 */
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, StyleSheet, ActivityIndicator,
  SafeAreaView, Modal, TextInput, Linking, RefreshControl,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { Image } from 'expo-image';
import { COLORS, SPACING, FONT, RADIUS, common } from '../src/constants/theme';
import api, { BACKEND } from '../src/api/client';
import { useGrokVoiceNative, nativeVoiceSupported } from '../src/fun-ai/grokVoiceNative';
import FunAiMemory from '../src/fun-ai/FunAiMemory';
import * as Speech from 'expo-speech';

let createAudioPlayer: any;
try { createAudioPlayer = require('expo-audio').createAudioPlayer; } catch (_e) { /* native only */ }

const ACCENT = '#0E7490';
const FALLBACK_MODES = [
  { id: 'morning_briefing', label: 'Morning Briefing' },
  { id: 'news_in_2', label: 'News in 2 Minutes' },
  { id: 'continuous', label: 'Continuous News' },
  { id: 'deep_dive', label: 'Deep Dive', topic_required: true },
  { id: 'local', label: 'Local News' },
  { id: 'global', label: 'Global News' },
];

const absUrl = (u?: string) => (!u ? '' : u.startsWith('http') ? u : `${BACKEND}${u}`);

export default function FunAiNewsScreen() {
  const router = useRouter();
  const [modes, setModes] = useState<any[]>(FALLBACK_MODES);
  const [mode, setMode] = useState('morning_briefing');
  const [appliedTopic, setAppliedTopic] = useState('');
  const [topicInput, setTopicInput] = useState('');
  const [program, setProgram] = useState<any[]>([]);
  const [modeLabel, setModeLabel] = useState('Morning Briefing');
  const [anchorHint, setAnchorHint] = useState('');
  const [sponsor, setSponsor] = useState<any>(null);
  const [follows, setFollows] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [empty, setEmpty] = useState<string | null>(null);
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [voiceOpen, setVoiceOpen] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [personalities, setPersonalities] = useState<any[]>([]);
  const [personality, setPersonality] = useState('friendly');

  // Sponsor breaks — disclosed ad spots woven into the news program.
  const [breaks, setBreaks] = useState<any[]>([]);
  const [activeBreak, setActiveBreak] = useState<any>(null);
  const playedBreaksRef = useRef<Set<string>>(new Set());
  const afterBreakRef = useRef<null | (() => void)>(null);
  const breakPlayerRef = useRef<any>(null);

  const playerRef = useRef<any>(null);
  const loadIdRef = useRef(0);

  useEffect(() => {
    api.get('/fun-ai/config').then(({ data }) => {
      if (data?.modes?.length) setModes(data.modes);
    }).catch(() => {});
    api.get('/fun-ai/preferences').then(({ data }) => {
      setPersonalities(data?.personalities || []);
      if (data?.personality) setPersonality(data.personality);
    }).catch(() => {});
  }, []);

  const pickPersonality = (id: string) => {
    setPersonality(id);
    api.put('/fun-ai/preferences', { personality: id }).catch(() => {});
  };

  const stopPlayer = useCallback(() => {
    try { playerRef.current?.pause?.(); } catch (_e) { /* noop */ }
    try { playerRef.current?.release?.(); } catch (_e) { /* noop */ }
    playerRef.current = null;
    setPlaying(false);
  }, []);

  const load = useCallback((m: string, topic: string) => {
    const myId = ++loadIdRef.current;
    setLoading(true); setEmpty(null); stopPlayer();
    let tries = 0;
    const run = async () => {
      try {
        const { data } = await api.get('/fun-ai/news/briefing',
          { params: { mode: m, topic: topic || undefined } });
        if (myId !== loadIdRef.current) return;
        setSponsor(data?.sponsor || null);
        setModeLabel(data?.mode_label || m);
        setAnchorHint(data?.anchor_hint || '');
        if (data?.topic && m === 'deep_dive') setTopicInput(data.topic);
        if (data?.program?.length) {
          setProgram(data.program); setIdx(0); setEmpty(null); setLoading(false);
          setBreaks(data?.breaks || []);
          playedBreaksRef.current = new Set();
          afterBreakRef.current = null;
          setActiveBreak(null);
          return;
        }
        setProgram([]);
        if (tries === 0) api.post('/news_radio/trigger-batch', null, { params: { top_n: 8 } }).catch(() => {});
        tries += 1;
        if (tries <= 5) {
          setEmpty("Preparing today's news program…"); setLoading(false);
          setTimeout(() => { if (myId === loadIdRef.current) run(); }, 5000);
        } else { setEmpty(data?.retry_hint || 'No news available right now.'); setLoading(false); }
      } catch (_e) {
        if (myId === loadIdRef.current) { setEmpty('Could not load the news program.'); setLoading(false); }
      }
    };
    run();
  }, [stopPlayer]);

  useEffect(() => { load(mode, appliedTopic); }, [mode, appliedTopic, load]);

  const loadFollows = useCallback(() => {
    api.get('/fun-ai/follows').then(({ data }) => setFollows(data?.follows || [])).catch(() => {});
  }, []);
  useEffect(() => { loadFollows(); }, [loadFollows]);

  useEffect(() => () => { stopPlayer(); }, [stopPlayer]);

  const current = program[idx];
  const isDeepDive = mode === 'deep_dive';
  const norm = (sv: string) => (sv || '').trim().toLowerCase();
  const currentFollow = current && follows.find((f) => norm(f.topic) === norm(current.title));

  const selectMode = (id: string) => {
    if (id === mode) return;
    setMode(id);
    if (id !== 'deep_dive') setAppliedTopic('');
  };

  // ── Sponsor break orchestration ──────────────────────────────────────
  const findBreak = useCallback((pred: (b: any) => boolean) =>
    breaks.find((b) => !playedBreaksRef.current.has(String(b.id)) && pred(b)), [breaks]);

  const stopBreakAudio = useCallback(() => {
    try { breakPlayerRef.current?.pause?.(); breakPlayerRef.current?.release?.(); } catch (_e) { /* noop */ }
    breakPlayerRef.current = null;
    try { Speech.stop(); } catch (_e) { /* noop */ }
  }, []);

  const finishBreak = useCallback(() => {
    stopBreakAudio();
    const after = afterBreakRef.current; afterBreakRef.current = null;
    setActiveBreak(null);
    if (after) after();
  }, [stopBreakAudio]);

  const startBreak = useCallback((b: any, after?: () => void) => {
    playedBreaksRef.current.add(String(b.id));
    afterBreakRef.current = after || null;
    setActiveBreak(b);
    api.post('/fun-ai/news/break-event', {
      break_id: String(b.id), kind: 'impression', placement: b.placement,
      sponsored_read_id: b.sponsored_read_id || undefined,
    }).catch(() => {});
    if (b.audio_url && createAudioPlayer) {
      try {
        const p = createAudioPlayer(absUrl(b.audio_url));
        p.addListener?.('playbackStatusUpdate', (s: any) => { if (s?.didJustFinish) finishBreak(); });
        breakPlayerRef.current = p;
        p.play();
      } catch (_e) { finishBreak(); }
    } else {
      try {
        Speech.stop();
        Speech.speak(b.text || '', { onDone: () => finishBreak(), onError: () => finishBreak() });
      } catch (_e) { finishBreak(); }
    }
  }, [finishBreak]);

  const playSegment = useCallback(() => {
    if (!current?.audio_url || !createAudioPlayer) { setPlaying(false); return; }
    try {
      if (!playerRef.current) playerRef.current = createAudioPlayer(absUrl(current.audio_url));
      playerRef.current.play(); setPlaying(true);
    } catch (_e) { setPlaying(false); }
  }, [current]);

  const togglePlay = () => {
    if (activeBreak) { finishBreak(); return; }
    if (playing) { try { playerRef.current?.pause?.(); } catch (_e) { /* noop */ } setPlaying(false); return; }
    if (idx === 0) {
      const opening = findBreak((b) => b.placement === 'opening');
      if (opening) { startBreak(opening, () => playSegment()); return; }
    }
    playSegment();
  };

  const closingPending = breaks.some((b) => b.placement === 'closing' && !playedBreaksRef.current.has(String(b.id)));
  const atLast = idx >= program.length - 1;

  const next = () => {
    if (activeBreak) { finishBreak(); return; }
    stopPlayer();
    const k = idx;
    if (k < program.length - 1) {
      const mid = findBreak((b) => b.placement === 'mid' && b.after_index === k);
      if (mid) { startBreak(mid, () => setIdx(k + 1)); return; }
      setIdx(k + 1); return;
    }
    const closing = findBreak((b) => b.placement === 'closing');
    if (closing) { startBreak(closing); }
  };

  useEffect(() => () => { stopBreakAudio(); }, [stopBreakAudio]);
  useEffect(() => { if (!activeBreak) stopBreakAudio(); }, [activeBreak, stopBreakAudio]);

  const toggleFollow = async () => {
    if (!current) return;
    try {
      if (currentFollow) await api.delete(`/fun-ai/follows/${currentFollow.id}`);
      else await api.post('/fun-ai/follows', { topic: current.title, title: current.title });
    } catch (_e) { /* noop */ }
    loadFollows();
  };
  const removeFollow = async (id: string) => {
    try { await api.delete(`/fun-ai/follows/${id}`); } catch (_e) { /* noop */ }
    loadFollows();
  };
  const openFollow = (topic: string) => { setTopicInput(topic); setMode('deep_dive'); setAppliedTopic(topic); };

  // Native live-voice anchor (only runs in a published app build; web = stub).
  const voice = useGrokVoiceNative({ onToolEvent: (name: string) => { if (name === 'follow_story') loadFollows(); } });
  const voiceSupported = nativeVoiceSupported();
  const voiceActive = voice.status !== 'idle' && voice.status !== 'unsupported';
  const VLABEL: Record<string, string> = {
    authorizing: 'Starting…', connecting: 'Connecting…', ready: 'Listening — ask anything',
    listening: 'Listening…', thinking: 'Thinking…', speaking: 'Fun AI is speaking…',
    error: 'Voice error — tap Stop and try again',
  };
  const onTalk = () => {
    if (voiceSupported) voice.start({ surface: 'news', mode, topic: isDeepDive ? appliedTopic : undefined });
    else setVoiceOpen(true);
  };

  return (
    <SafeAreaView style={common.screen}>
      <ScrollView contentContainerStyle={st.scroll}
        refreshControl={<RefreshControl refreshing={refreshing}
          onRefresh={() => { setRefreshing(true); load(mode, appliedTopic); loadFollows(); setTimeout(() => setRefreshing(false), 800); }}
          tintColor={ACCENT} />}>

        <View style={st.headerRow}>
          <TouchableOpacity testID="fai-back" onPress={() => router.back()} hitSlop={10}>
            <Ionicons name="chevron-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text testID="fai-title" style={st.title}>Interactive News</Text>
            <Text style={st.subtitle}>Your News. Your Questions. Your AI Anchor.</Text>
          </View>
        </View>

        {/* Program modes — single-row horizontal scroller */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={st.chipRow} testID="fai-modes">
          {modes.map((m) => {
            const on = m.id === mode;
            return (
              <TouchableOpacity key={m.id} testID={`fai-mode-${m.id}`} onPress={() => selectMode(m.id)}
                style={[st.chip, on && st.chipOn]}>
                <Text style={[st.chipText, on && st.chipTextOn]}>{m.label}</Text>
              </TouchableOpacity>
            );
          })}
        </ScrollView>
        {!!anchorHint && <Text style={st.hint}>{anchorHint}</Text>}

        {isDeepDive && (
          <View style={st.deepRow}>
            <TextInput testID="fai-deepdive-topic" value={topicInput} onChangeText={setTopicInput}
              placeholder="Topic to go deep on" placeholderTextColor={COLORS.textMuted}
              style={st.input} onSubmitEditing={() => setAppliedTopic(topicInput.trim())} />
            <TouchableOpacity testID="fai-deepdive-go" style={st.goBtn}
              onPress={() => setAppliedTopic(topicInput.trim())}>
              <Ionicons name="search" size={16} color="#fff" />
            </TouchableOpacity>
          </View>
        )}

        {sponsor?.enabled && !!sponsor?.sponsor_name && (
          <View testID="fai-sponsor" style={st.sponsor}>
            <Ionicons name="megaphone-outline" size={15} color={ACCENT} />
            <Text style={st.sponsorText}>
              <Text style={st.sponsorTag}>SPONSORED  </Text>
              {sponsor.opening_line || `FUUSIC Interactive News is sponsored by ${sponsor.sponsor_name}.`}
            </Text>
          </View>
        )}

        {follows.length > 0 && (
          <View testID="fai-following" style={{ marginBottom: SPACING.md }}>
            <Text style={st.sectionLabel}>FOLLOWING</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.chipRow}>
              {follows.map((f) => (
                <View key={f.id} testID={`fai-follow-${f.id}`} style={st.followChip}>
                  <TouchableOpacity onPress={() => openFollow(f.topic)} style={{ maxWidth: 180 }}>
                    <Text numberOfLines={1} style={st.followChipText}>{f.title}</Text>
                  </TouchableOpacity>
                  <TouchableOpacity testID={`fai-follow-remove-${f.id}`} onPress={() => removeFollow(f.id)} hitSlop={8}>
                    <Ionicons name="close" size={14} color={COLORS.textDim} />
                  </TouchableOpacity>
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Player card */}
        <View style={st.card}>
          {loading && !program.length ? (
            <ActivityIndicator color={ACCENT} style={{ padding: SPACING.lg }} />
          ) : empty ? (
            <Text testID="fai-empty" style={st.empty}>{empty}</Text>
          ) : activeBreak ? (
            <View testID="fai-break">
              <Text style={st.breakTag}>
                <Ionicons name="megaphone" size={12} color={ACCENT} />  {(activeBreak.label || 'Sponsored').toUpperCase()}
              </Text>
              <Text style={st.breakDisclosure}>{activeBreak.disclosure || 'A word from our sponsor'}</Text>
              <Text testID="fai-break-text" style={st.breakText}>{activeBreak.text}</Text>
              <View style={st.breakFooter}>
                <View style={st.breakHint}>
                  <Ionicons name="volume-high-outline" size={14} color={ACCENT} />
                  <Text style={st.breakHintText}>Sponsor break — your news resumes right after.</Text>
                </View>
                <TouchableOpacity testID="fai-break-skip" style={st.nextBtn} onPress={finishBreak}>
                  <Text style={st.nextText}>Skip ▸</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : current ? (
            <>
              <Text style={st.nowTag}>{modeLabel.toUpperCase()} · {idx + 1} OF {program.length}</Text>
              {!!current.image_url && (
                <Image source={{ uri: absUrl(current.image_url) }} style={st.hero} contentFit="cover" transition={200} />
              )}
              <Text testID="fai-segment" style={st.segTitle}>{current.title}</Text>
              <Text style={st.segSummary}>{current.summary}</Text>
              <View style={st.metaRow}>
                <Text style={st.metaText}>{current.source_name}</Text>
                <Text style={st.metaText}>~{current.duration_estimate_sec}s</Text>
                {!!current.url && (
                  <TouchableOpacity testID="fai-source" onPress={() => Linking.openURL(current.url)}>
                    <Text style={[st.metaText, { color: ACCENT }]}>View source ↗</Text>
                  </TouchableOpacity>
                )}
              </View>

              <View style={st.playRow}>
                <TouchableOpacity testID="fai-play" onPress={togglePlay}
                  disabled={!current.audio_url} style={[st.playBtn, !current.audio_url && { opacity: 0.5 }]}>
                  <Ionicons name={playing ? 'pause' : 'play'} size={18} color="#fff" />
                  <Text style={st.playBtnText}>{playing ? 'Pause' : current.audio_url ? 'Play news' : 'Audio warming up'}</Text>
                </TouchableOpacity>
                <TouchableOpacity testID="fai-next" onPress={next}
                  disabled={atLast && !closingPending}
                  style={[st.nextBtn, atLast && !closingPending && { opacity: 0.4 }]}>
                  <Text style={st.nextText}>{atLast ? 'Finish ▸' : 'Next →'}</Text>
                </TouchableOpacity>
              </View>

              <TouchableOpacity testID="fai-follow-toggle" onPress={toggleFollow} style={st.followBtn}>
                <Ionicons name={currentFollow ? 'bookmark' : 'bookmark-outline'} size={16}
                  color={currentFollow ? ACCENT : COLORS.textDim} />
                <Text style={[st.followBtnText, currentFollow && { color: ACCENT }]}>
                  {currentFollow ? 'Following this story' : 'Follow this story'}
                </Text>
              </TouchableOpacity>
            </>
          ) : null}
        </View>

        {/* Talk to Fun AI — native-build voice anchor */}
        {personalities.length > 0 && (
          <View testID="fai-rj-row" style={{ marginTop: SPACING.lg }}>
            <Text style={st.sectionLabel}>RJ PERSONALITY</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={st.chipRow}>
              {personalities.map((p) => {
                const on = p.id === personality;
                return (
                  <TouchableOpacity key={p.id} testID={`fai-rj-${p.id}`} onPress={() => pickPersonality(p.id)}
                    style={[st.chip, on && st.chipOn]}>
                    <Text style={[st.chipText, on && st.chipTextOn]}>{p.label}</Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>
        )}
        <TouchableOpacity testID="fai-talk-btn" style={st.talkBtn} onPress={onTalk}>
          <Ionicons name="mic" size={18} color="#fff" />
          <Text style={st.talkBtnText}>Talk to Fun AI about {modeLabel}</Text>
        </TouchableOpacity>
        <Text style={st.talkNote}>Voice is an AI assistant. News is read from verified sources.</Text>

        <FunAiMemory embedded />
      </ScrollView>

      {/* Voice explainer (live voice runs in the published app build) */}
      <Modal visible={voiceOpen} transparent animationType="slide" onRequestClose={() => setVoiceOpen(false)}>
        <View style={st.modalWrap}>
          <View testID="fai-voice-sheet" style={st.sheet}>
            <View style={st.sheetHandle} />
            <View style={st.sheetIcon}><Ionicons name="mic" size={26} color={ACCENT} /></View>
            <Text style={st.sheetTitle}>Talk to Fun AI</Text>
            <Text style={st.sheetBody}>
              The live voice anchor — ask questions, interrupt any time, follow stories by voice — runs
              in the FUUSIC app. It needs microphone streaming that isn't available in the preview.
              It unlocks once this build is published to your phone.
            </Text>
            <Text style={st.sheetBody}>Meanwhile, press Play above to listen to today's verified news program.</Text>
            <TouchableOpacity testID="fai-voice-close" style={st.sheetBtn} onPress={() => setVoiceOpen(false)}>
              <Text style={st.sheetBtnText}>Got it</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Live voice overlay (native build only) */}
      <Modal visible={voiceActive} transparent animationType="slide" onRequestClose={() => voice.stop()}>
        <View style={st.modalWrap}>
          <View testID="fai-voice-live" style={st.sheet}>
            <View style={st.sheetHandle} />
            <View style={st.sheetIcon}><Ionicons name="mic" size={26} color={ACCENT} /></View>
            <Text style={st.sheetTitle}>Fun AI</Text>
            <Text style={st.sheetBody}>{VLABEL[voice.status] || 'Fun AI'}</Text>
            <ScrollView style={{ maxHeight: 200, alignSelf: 'stretch' }}>
              {voice.transcript.map((t: any, i: number) => (
                <Text key={i} style={{ color: t.role === 'you' ? COLORS.text : ACCENT, fontSize: FONT.sm, marginBottom: 6, lineHeight: 20 }}>
                  <Text style={{ fontWeight: '800' }}>{t.role === 'you' ? 'You: ' : 'Fun AI: '}</Text>{t.text}
                </Text>
              ))}
            </ScrollView>
            <TouchableOpacity testID="fai-voice-stop" style={st.sheetBtn} onPress={() => voice.stop()}>
              <Text style={st.sheetBtnText}>Stop</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  scroll: { padding: SPACING.lg, paddingBottom: 48 },
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, marginBottom: SPACING.md },
  title: { color: COLORS.text, fontSize: FONT.xxl, fontWeight: '900' },
  subtitle: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 2 },
  chipRow: { gap: SPACING.sm, paddingVertical: 2 },
  chip: {
    flexShrink: 0, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999,
    borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.card,
  },
  chipOn: { backgroundColor: ACCENT, borderColor: ACCENT },
  chipText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  chipTextOn: { color: '#fff' },
  hint: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: SPACING.sm, marginBottom: SPACING.sm, lineHeight: 18 },
  deepRow: { flexDirection: 'row', gap: SPACING.sm, marginBottom: SPACING.md },
  input: {
    flex: 1, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: COLORS.text, fontSize: FONT.md,
  },
  goBtn: { backgroundColor: ACCENT, borderRadius: RADIUS.md, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' },
  sponsor: {
    flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, marginBottom: SPACING.md,
    backgroundColor: 'rgba(14,116,144,0.08)', borderWidth: 1, borderColor: 'rgba(14,116,144,0.25)',
    borderStyle: 'dashed', borderRadius: RADIUS.md, padding: SPACING.md,
  },
  sponsorText: { flex: 1, color: COLORS.text, fontSize: FONT.xs, lineHeight: 17 },
  sponsorTag: { color: COLORS.textMuted, fontWeight: '800', fontSize: 10 },
  sectionLabel: { color: COLORS.textMuted, fontSize: 10, fontWeight: '800', letterSpacing: 1, marginBottom: 6 },
  followChip: {
    flexShrink: 0, flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
    borderRadius: 999, paddingHorizontal: 12, paddingVertical: 7,
  },
  followChipText: { color: COLORS.text, fontSize: FONT.xs, fontWeight: '600' },
  card: { backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.lg },
  empty: { color: '#B45309', backgroundColor: 'rgba(245,158,11,0.10)', padding: SPACING.md, borderRadius: RADIUS.md, fontSize: FONT.sm },
  breakTag: { color: ACCENT, fontSize: 10, fontWeight: '800', letterSpacing: 1.5, marginBottom: 8 },
  breakDisclosure: { color: COLORS.textDim, fontSize: FONT.xs, marginBottom: 10 },
  breakText: { color: COLORS.text, fontSize: FONT.lg, lineHeight: 24, marginBottom: 16 },
  breakFooter: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  breakHint: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 6 },
  breakHintText: { color: COLORS.textDim, fontSize: FONT.xs, flex: 1 },
  nowTag: { color: ACCENT, fontSize: 11, fontWeight: '800', letterSpacing: 1, marginBottom: 8 },
  hero: { width: '100%', height: 150, borderRadius: RADIUS.md, marginBottom: 10, backgroundColor: COLORS.cardBorder },
  segTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '800', lineHeight: 24, marginBottom: 8 },
  segSummary: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 21, marginBottom: 10 },
  metaRow: { flexDirection: 'row', alignItems: 'center', flexWrap: 'wrap', gap: 12, marginBottom: 14 },
  metaText: { color: COLORS.textMuted, fontSize: FONT.xs, fontVariant: ['tabular-nums'] },
  playRow: { flexDirection: 'row', gap: SPACING.sm },
  playBtn: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: ACCENT, borderRadius: RADIUS.md, paddingVertical: 12 },
  playBtnText: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
  nextBtn: { paddingHorizontal: 18, justifyContent: 'center', borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.cardBorder, backgroundColor: COLORS.card },
  nextText: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  followBtn: { marginTop: 10, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderWidth: 1, borderColor: COLORS.cardBorder, borderRadius: RADIUS.md, paddingVertical: 11, backgroundColor: COLORS.bg },
  followBtnText: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '700' },
  talkBtn: { marginTop: SPACING.lg, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, backgroundColor: ACCENT, borderRadius: RADIUS.lg, paddingVertical: 15 },
  talkBtnText: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
  talkNote: { color: COLORS.textMuted, fontSize: FONT.xs, textAlign: 'center', marginTop: 8 },
  modalWrap: { flex: 1, backgroundColor: 'rgba(0,0,0,0.45)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.card, borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: SPACING.lg, paddingBottom: 32, alignItems: 'center' },
  sheetHandle: { width: 44, height: 5, borderRadius: 3, backgroundColor: COLORS.cardBorder, marginBottom: SPACING.md },
  sheetIcon: { width: 54, height: 54, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(14,116,144,0.12)', marginBottom: SPACING.md },
  sheetTitle: { color: COLORS.text, fontSize: FONT.lg, fontWeight: '900', marginBottom: 8 },
  sheetBody: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 21, textAlign: 'center', marginBottom: SPACING.sm },
  sheetBtn: { marginTop: SPACING.sm, backgroundColor: ACCENT, borderRadius: RADIUS.md, paddingVertical: 13, paddingHorizontal: 40 },
  sheetBtnText: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
});
