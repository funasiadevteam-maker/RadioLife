import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, ScrollView,
  ActivityIndicator, TextInput, FlatList, Alert, KeyboardAvoidingView, Platform,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import * as SecureStore from 'expo-secure-store';
import { useAuth } from '../../src/contexts/AuthContext';
import api, { BACKEND, radioApi } from '../../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';

let createAudioPlayer: any;
try { createAudioPlayer = require('expo-audio').createAudioPlayer; } catch {}

const BACKEND_URL = process.env.EXPO_PUBLIC_BACKEND_URL || '';
const WS_URL = BACKEND_URL.replace(/^https:/, 'wss:').replace(/^http:/, 'ws:');
const TOKEN_KEY = 'bigfm_session_token';
const REACTIONS = ['❤️', '🔥', '👍', '👏', '🎉', '🎶', '🕺', '💃', '🪩', '😍', '😂', '🤩'];

export default function LobbyDetailScreen() {
  const { id: lobbyId } = useLocalSearchParams<{ id: string }>();
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();

  const [lobby, setLobby] = useState<any>(null);
  const [members, setMembers] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [isHost, setIsHost] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [currentSeg, setCurrentSeg] = useState<any>(null);
  const [chatInput, setChatInput] = useState('');
  const [emojiOpen, setEmojiOpen] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [skipVotes, setSkipVotes] = useState({ votes: 0, threshold: 1 });
  const [hostSessionId, setHostSessionId] = useState<string | null>(null);
  const [hostStarting, setHostStarting] = useState(false);
  const [skipBusy, setSkipBusy] = useState(false);
  const [showMembers, setShowMembers] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const playerRef = useRef<any>(null);
  const chatListRef = useRef<FlatList>(null);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
  }, [user, authLoading]);

  /* ── Bootstrap ── */
  useEffect(() => {
    if (!user || !lobbyId) return;
    (async () => {
      try {
        const d = await api.get(`/lobbies/${lobbyId}`);
        setLobby(d.data);
        setMembers(d.data.members_preview || []);
        setMessages(d.data.recent_messages || []);
        setIsHost(d.data.i_am_host);
        const isMember = (d.data.members_preview || []).some((m: any) => m.user_id === user.user_id);
        if (!isMember) {
          const j = await api.post(`/lobbies/${lobbyId}/join`);
          if (j.data.role === 'host') setIsHost(true);
        }
        openWS();
      } catch (e: any) {
        const code = e?.response?.data?.detail;
        if (code === 'invite_required') Alert.alert('Private', 'This lobby is private');
        else if (code === 'lobby_full') Alert.alert('Full', 'Lobby is full');
        else if (e?.response?.status === 404) Alert.alert('Not found', 'Lobby not found');
        else Alert.alert('Error', code || 'Failed to load lobby');
        router.replace('/lobbies');
      }
    })();
    return () => closeWS();
  }, [user, lobbyId]);

  /* ── WebSocket ── */
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retriesRef = useRef(0);

  const openWS = useCallback(async () => {
    if (wsRef.current) return;
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (!token) { router.replace('/login'); return; }
    const url = `${WS_URL}/api/lobbies/ws/${lobbyId}?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => { setWsConnected(true); retriesRef.current = 0; };

    ws.onclose = () => {
      setWsConnected(false);
      wsRef.current = null;
      /* Exponential back-off reconnect (max ~30 s) */
      const delay = Math.min(30000, 1000 * Math.pow(2, retriesRef.current));
      retriesRef.current += 1;
      reconnectRef.current = setTimeout(() => { openWS(); }, delay);
    };

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        /* Handle server auth rejection */
        if (msg.type === 'error' && msg.code === 'unauthorized') {
          ws.close();
          wsRef.current = null;
          router.replace('/login');
          return;
        }
        handleMsg(msg);
      } catch {}
    };

    const ping = setInterval(() => {
      try { if (ws.readyState === 1) ws.send(JSON.stringify({ type: 'ping' })); } catch {}
    }, 25000);
    ws.addEventListener('close', () => clearInterval(ping));
  }, [lobbyId]);

  const closeWS = () => {
    if (reconnectRef.current) { clearTimeout(reconnectRef.current); reconnectRef.current = null; }
    retriesRef.current = 0;
    try { wsRef.current?.close(); } catch {}
    wsRef.current = null;
  };

  const handleMsg = (msg: any) => {
    switch (msg.type) {
      case 'hello':
        if (msg.you?.role === 'host') setIsHost(true);
        if (msg.current_segment?.segment_id) syncSeg(msg.current_segment);
        break;
      case 'chat_message':
        setMessages((m) => [...m, msg].slice(-100));
        break;
      case 'presence_update':
        setLobby((l: any) => l ? { ...l, current_listener_count: msg.current_listener_count ?? l.current_listener_count } : l);
        if (msg.action === 'join' && msg.user) {
          setMembers((mm) => mm.some((x: any) => x.user_id === msg.user.user_id) ? mm : [...mm, msg.user]);
        } else if (['leave', 'kicked', 'ws_disconnect'].includes(msg.action)) {
          setMembers((mm) => mm.filter((x: any) => x.user_id !== msg.user?.user_id));
        }
        break;
      case 'skip_vote_update':
        setSkipVotes({ votes: msg.votes, threshold: msg.threshold });
        break;
      case 'segment_changed':
        syncSeg(msg);
        break;
      case 'channel_changed':
        setLobby((l: any) => l ? { ...l, channel_slug: msg.channel_slug, channel_name: msg.channel_name } : l);
        break;
      case 'host_changed':
        setLobby((l: any) => l ? { ...l, host_user_id: msg.new_host_user_id, host_display_name: msg.new_host_display_name } : l);
        setIsHost(msg.new_host_user_id === user?.user_id);
        break;
      case 'kicked':
        Alert.alert('Removed', 'You were removed from the lobby');
        router.replace('/lobbies');
        break;
      case 'lobby_closed':
        Alert.alert('Ended', 'Lobby ended');
        router.replace('/lobbies');
        break;
    }
  };

  /* ── Audio sync ── */
  const syncSeg = (seg: any) => {
    if (!seg?.segment_url) return;
    setCurrentSeg(seg);
    try { playerRef.current?.release?.(); } catch {}
    if (!createAudioPlayer) return;
    const url = `${BACKEND}${seg.segment_url}`;
    const p = createAudioPlayer(url);
    playerRef.current = p;
    const elapsed = seg.started_at ? Math.max(0, (Date.now() - new Date(seg.started_at).getTime()) / 1000) : 0;
    p.play();
    if (elapsed > 1) {
      try { p.seekTo?.(elapsed); } catch {}
    }
    setPlaying(true);
  };

  /* ── Host: start radio ── */
  const hostStart = async () => {
    if (!isHost || hostSessionId || hostStarting) return;
    setHostStarting(true);
    try {
      const r = await radioApi.post('/radio/start', { channel: lobby.channel_slug });
      setHostSessionId(r.data.session_id);
      const seg = r.data.segment;
      await api.post(`/lobbies/${lobbyId}/announce_segment`, segPayload(seg));
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Could not start');
    } finally { setHostStarting(false); }
  };

  const segPayload = (seg: any) => ({
    segment_id: seg.segment_id, segment_url: seg.segment_url,
    duration_sec: seg.duration_sec, track_title: seg.track_title,
    track_artist: seg.track_artist, rj_voice_name: seg.rj_voice_name,
    rj_start_sec: seg.rj_start_sec, rj_script: seg.rj_script,
    channel_slug: seg.channel_slug, channel_name: seg.channel_name,
  });

  const hostSkip = async () => {
    if (!isHost || !hostSessionId || skipBusy) return;
    setSkipBusy(true);
    try {
      const r = await radioApi.post('/radio/skip', null, { params: { session_id: hostSessionId } });
      await api.post(`/lobbies/${lobbyId}/announce_segment`, segPayload(r.data.segment));
    } catch { Alert.alert('Error', 'Skip failed'); }
    finally { setSkipBusy(false); }
  };

  /* ── Chat / reactions ── */
  const sendChat = () => {
    const text = chatInput.trim();
    if (!text || !wsRef.current || wsRef.current.readyState !== 1) return;
    wsRef.current.send(JSON.stringify({ type: 'chat', text }));
    setChatInput('');
  };
  const sendReaction = (emoji: string) => {
    if (!wsRef.current || wsRef.current.readyState !== 1) return;
    wsRef.current.send(JSON.stringify({ type: 'reaction', emoji }));
    setEmojiOpen(false);
  };
  const castSkipVote = async () => {
    try {
      const r = await api.post(`/lobbies/${lobbyId}/skip_vote`);
      setSkipVotes({ votes: r.data.votes, threshold: r.data.threshold });
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Vote failed');
    }
  };
  const leaveLobby = async () => {
    setLeaving(true);
    try { await api.post(`/lobbies/${lobbyId}/leave`); } catch {}
    closeWS();
    router.replace('/lobbies');
  };
  const closeLobby = async () => {
    Alert.alert('End lobby?', 'This ends the lobby for everyone.', [
      { text: 'Cancel' },
      { text: 'End', style: 'destructive', onPress: async () => {
        try { await api.post(`/lobbies/${lobbyId}/close`); } catch {}
        router.replace('/lobbies');
      }},
    ]);
  };
  const kickMember = (uid: string) => {
    Alert.alert('Remove?', 'Remove this listener?', [
      { text: 'Cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        try { await api.post(`/lobbies/${lobbyId}/kick`, { user_id: uid }); } catch {}
      }},
    ]);
  };

  const togglePlay = () => {
    const p = playerRef.current;
    if (!p) return;
    try {
      if (p.playing) { p.pause(); setPlaying(false); }
      else { p.play(); setPlaying(true); }
    } catch {}
  };

  if (authLoading || !user || !lobby) {
    return <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  return (
    <SafeAreaView style={s.screen} testID="lobby-room">
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity onPress={() => router.push('/lobbies')} style={s.backBtn} testID="lobby-back">
            <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
            <Text style={s.backText}>lobbies</Text>
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text style={s.lobbyTitle} testID="lobby-title" numberOfLines={1}>{lobby.name}</Text>
            <View style={s.metaRow}>
              <Text style={s.metaText}>by <Text style={{ fontWeight: '800' }}>{lobby.host_display_name}</Text></Text>
              <Ionicons name="people" size={11} color={COLORS.textDim} />
              <Text style={s.metaText}>{lobby.current_listener_count}/{lobby.max_listeners}</Text>
              <View style={[s.wsDot, wsConnected && { backgroundColor: COLORS.green }]} />
              <Text style={[s.metaText, wsConnected && { color: COLORS.green }]} testID={wsConnected ? 'ws-status-connected' : 'ws-status-disconnected'}>
                {wsConnected ? 'LIVE' : 'CONNECTING...'}
              </Text>
            </View>
          </View>
          <View style={s.headerActions}>
            <TouchableOpacity onPress={() => setShowMembers(!showMembers)} style={s.iconBtn}>
              <Ionicons name="people" size={16} color={COLORS.textDim} />
            </TouchableOpacity>
            {isHost ? (
              <TouchableOpacity onPress={closeLobby} style={[s.iconBtn, { borderColor: COLORS.orange }]} testID="close-lobby-btn">
                <Ionicons name="close" size={14} color={COLORS.orange} />
              </TouchableOpacity>
            ) : (
              <TouchableOpacity onPress={leaveLobby} disabled={leaving} style={s.iconBtn} testID="leave-lobby-btn">
                <Ionicons name="log-out" size={14} color={COLORS.textDim} />
              </TouchableOpacity>
            )}
          </View>
        </View>

        {/* Now Playing / Start */}
        {!currentSeg ? (
          <View style={s.emptyStage} testID="lobby-stage">
            {isHost ? (
              <>
                <Ionicons name="musical-notes" size={42} color={COLORS.textMuted} />
                <Text style={s.stageTitle}>Ready to start the radio?</Text>
                <TouchableOpacity style={s.goLiveBtn} onPress={hostStart} disabled={hostStarting} testID="host-start-radio-btn">
                  {hostStarting ? <ActivityIndicator size={16} color="#fff" /> : <Ionicons name="play" size={16} color="#fff" />}
                  <Text style={s.goLiveText}>{hostStarting ? 'Starting...' : 'Go live'}</Text>
                </TouchableOpacity>
              </>
            ) : (
              <>
                <ActivityIndicator size={32} color={COLORS.textMuted} />
                <Text style={s.stageTitle}>Waiting for host...</Text>
                <Text style={s.stageSub}>Your host is queueing up the first track.</Text>
              </>
            )}
          </View>
        ) : (
          <View style={s.nowPlaying} testID="lobby-now-playing">
            <View style={s.npBadge}>
              <View style={s.npDot} />
              <Text style={s.npLabel}>ON AIR · {currentSeg.channel_name || lobby.channel_name}</Text>
            </View>
            <Text style={s.npTitle}>{currentSeg.track_title || '—'}</Text>
            <Text style={s.npArtist}>{currentSeg.track_artist || ''}</Text>
            {currentSeg.rj_script && (
              <View style={s.rjBubble} testID="lobby-rj-script">
                <Text style={s.rjTag}>RJ {currentSeg.rj_voice_name?.toUpperCase()}</Text>
                <Text style={s.rjScript} numberOfLines={3}>{currentSeg.rj_script}</Text>
              </View>
            )}
            <View style={s.controlsRow}>
              <TouchableOpacity style={s.ctrlBtn} onPress={togglePlay} testID="lobby-play-btn">
                <Ionicons name={playing ? 'pause' : 'play'} size={16} color="#fff" />
              </TouchableOpacity>
              <TouchableOpacity style={s.skipVoteBtn} onPress={castSkipVote} testID="cast-skip-vote-btn">
                <Ionicons name="play-skip-forward" size={13} color={COLORS.textDim} />
                <Text style={s.skipVoteText}>Vote skip</Text>
                <Text style={s.skipVoteCount}>{skipVotes.votes}/{skipVotes.threshold}</Text>
              </TouchableOpacity>
              {isHost && hostSessionId && (
                <TouchableOpacity style={s.hostSkipBtn} onPress={hostSkip} disabled={skipBusy} testID="host-skip-now-btn">
                  {skipBusy ? <ActivityIndicator size={13} color={COLORS.textDim} /> : <Ionicons name="play-skip-forward" size={13} color={COLORS.secondary} />}
                  <Text style={s.hostSkipText}>Skip (host)</Text>
                </TouchableOpacity>
              )}
            </View>
            {/* Reactions */}
            <View style={s.reactionBar}>
              {REACTIONS.slice(0, 6).map((e) => (
                <TouchableOpacity key={e} style={s.reactionBtn} onPress={() => sendReaction(e)} testID={`react-${e}`}>
                  <Text style={s.reactionEmoji}>{e}</Text>
                </TouchableOpacity>
              ))}
              <TouchableOpacity style={s.reactionBtn} onPress={() => setEmojiOpen(!emojiOpen)} testID="emoji-launcher-btn">
                <Ionicons name="happy" size={16} color={COLORS.textDim} />
              </TouchableOpacity>
            </View>
            {emojiOpen && (
              <View style={s.emojiPalette} testID="emoji-palette">
                {REACTIONS.map((e) => (
                  <TouchableOpacity key={e} style={s.emojiBtn} onPress={() => sendReaction(e)}>
                    <Text style={{ fontSize: 20 }}>{e}</Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
          </View>
        )}

        {/* Members modal */}
        {showMembers && (
          <View style={s.membersPanel} testID="lobby-members-panel">
            <Text style={s.panelTitle}>LISTENERS · {lobby.current_listener_count}</Text>
            <ScrollView>
              {members.map((m: any) => (
                <View key={m.user_id} style={s.memberRow} testID={`member-${m.user_id}`}>
                  <View style={[s.memberDot, { backgroundColor: m.avatar_color || '#888' }]} />
                  <Text style={s.memberName}>{m.display_name}</Text>
                  {m.role === 'host' && (
                    <View style={s.hostTag}><Ionicons name="diamond" size={9} color={COLORS.gold} /><Text style={s.hostTagText}>HOST</Text></View>
                  )}
                  {isHost && m.user_id !== user.user_id && m.role !== 'host' && (
                    <TouchableOpacity onPress={() => kickMember(m.user_id)} testID={`kick-${m.user_id}`} style={s.kickBtn}>
                      <Ionicons name="close" size={10} color={COLORS.orange} />
                    </TouchableOpacity>
                  )}
                </View>
              ))}
            </ScrollView>
          </View>
        )}

        {/* Chat */}
        <View style={s.chatPanel} testID="lobby-chat-panel">
          <Text style={s.panelTitle}>CHAT</Text>
          <FlatList
            ref={chatListRef}
            data={messages}
            keyExtractor={(m, i) => m.message_id || `${i}`}
            renderItem={({ item }) => (
              <View style={s.chatMsg} testID="chat-msg">
                <View style={[s.chatAvatar, { backgroundColor: item.avatar_color || '#888' }]}>
                  <Text style={s.chatAvatarLetter}>{(item.display_name || '?')[0].toUpperCase()}</Text>
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.chatName}>{item.display_name}</Text>
                  <Text style={s.chatText}>{item.text}</Text>
                </View>
              </View>
            )}
            onContentSizeChange={() => chatListRef.current?.scrollToEnd({ animated: true })}
            style={{ flex: 1 }}
            contentContainerStyle={{ paddingBottom: 8 }}
            ListEmptyComponent={<Text style={s.chatEmpty}>say something nice...</Text>}
            testID="chat-messages"
          />
          <View style={s.chatInputRow}>
            <TextInput style={s.chatInput} value={chatInput} onChangeText={setChatInput}
              placeholder={wsConnected ? 'say something...' : 'connecting...'}
              placeholderTextColor={COLORS.textMuted} maxLength={240}
              onSubmitEditing={sendChat} editable={wsConnected}
              testID="chat-input" />
            <TouchableOpacity onPress={sendChat} disabled={!chatInput.trim() || !wsConnected}
              style={[s.sendBtn, (!chatInput.trim() || !wsConnected) && { opacity: 0.4 }]} testID="chat-send-btn">
              <Ionicons name="send" size={14} color="#fff" />
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, gap: 8 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 2, padding: 4 },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  lobbyTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '900' },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  metaText: { color: COLORS.textDim, fontSize: 10, fontWeight: '600' },
  wsDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.textMuted },
  headerActions: { flexDirection: 'row', gap: 6 },
  iconBtn: { padding: 8, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLORS.cardBorder },
  emptyStage: { alignItems: 'center', paddingVertical: 40, gap: 12 },
  stageTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '800' },
  stageSub: { color: COLORS.textDim, fontSize: FONT.sm },
  goLiveBtn: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: COLORS.primary, paddingHorizontal: 20, paddingVertical: 12, borderRadius: RADIUS.lg },
  goLiveText: { color: '#fff', fontWeight: '700' },
  nowPlaying: { padding: SPACING.md, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  npBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 },
  npDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: COLORS.green },
  npLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1.5 },
  npTitle: { color: '#fff', fontSize: FONT.xl, fontWeight: '900', marginBottom: 2 },
  npArtist: { color: COLORS.textDim, fontSize: FONT.md, marginBottom: 8 },
  rjBubble: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.sm, marginBottom: 8, borderWidth: 1, borderColor: COLORS.cardBorder },
  rjTag: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1 },
  rjScript: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 18, marginTop: 4 },
  controlsRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, marginBottom: 8 },
  ctrlBtn: { width: 44, height: 44, borderRadius: 22, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  skipVoteBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 8, borderRadius: RADIUS.md, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder },
  skipVoteText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  skipVoteCount: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700' },
  hostSkipBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 10, paddingVertical: 8, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.secondary },
  hostSkipText: { color: COLORS.secondary, fontSize: FONT.xs, fontWeight: '700' },
  reactionBar: { flexDirection: 'row', gap: 6, marginTop: 4 },
  reactionBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: COLORS.card, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.cardBorder },
  reactionEmoji: { fontSize: 16 },
  emojiPalette: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, padding: SPACING.sm, backgroundColor: COLORS.card, borderRadius: RADIUS.md, marginTop: 6, borderWidth: 1, borderColor: COLORS.cardBorder },
  emojiBtn: { padding: 4 },
  membersPanel: { paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, maxHeight: 150, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  panelTitle: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2, marginBottom: 6 },
  memberRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 4 },
  memberDot: { width: 20, height: 20, borderRadius: 10 },
  memberName: { color: COLORS.textDim, fontSize: FONT.sm, fontWeight: '600', flex: 1 },
  hostTag: { flexDirection: 'row', alignItems: 'center', gap: 3, paddingHorizontal: 6, paddingVertical: 2, borderRadius: RADIUS.sm, backgroundColor: 'rgba(255,215,0,0.1)' },
  hostTagText: { color: COLORS.gold, fontSize: 9, fontWeight: '800', letterSpacing: 1 },
  kickBtn: { padding: 4, borderRadius: RADIUS.sm, borderWidth: 1, borderColor: COLORS.orange },
  chatPanel: { flex: 1, paddingHorizontal: SPACING.md, paddingTop: SPACING.sm },
  chatMsg: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  chatAvatar: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  chatAvatarLetter: { color: '#fff', fontSize: 10, fontWeight: '800' },
  chatName: { color: COLORS.textDim, fontSize: 10, fontWeight: '700' },
  chatText: { color: '#fff', fontSize: FONT.sm, lineHeight: 18 },
  chatEmpty: { color: COLORS.textMuted, fontSize: FONT.sm, fontWeight: '600', textAlign: 'center', paddingVertical: 20 },
  chatInputRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: SPACING.sm },
  chatInput: { flex: 1, backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10, color: '#fff', fontSize: FONT.sm },
  sendBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
});
