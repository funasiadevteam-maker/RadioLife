import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, KeyboardAvoidingView, Platform, Image, Share,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';
import { AvatarM } from '../../(tabs)/social';

const REACTIONS = ['❤️', '🔥', '😂', '👏', '🎉'];

export default function ListenRoomMobile() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [room, setRoom] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [participants, setParticipants] = useState<any[]>([]);
  const [challenge, setChallenge] = useState<any>(null);
  const [text, setText] = useState('');
  const [error, setError] = useState(false);
  const sinceRef = useRef<string | null>(null);
  const scRef = useRef<ScrollView>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await api.post(`/social/rooms/${id}/join`);
        if (!alive) return;
        setRoom(data); setMessages(data.messages || []); setParticipants(data.participants || []);
      } catch (_) { if (alive) setError(true); }
    })();
    return () => { alive = false; api.post(`/social/rooms/${id}/leave`).catch(() => {}); };
  }, [id]);

  const beat = useCallback(async () => {
    try {
      const url = sinceRef.current
        ? `/social/rooms/${id}/heartbeat?since=${encodeURIComponent(sinceRef.current)}`
        : `/social/rooms/${id}/heartbeat`;
      const { data } = await api.post(url);
      sinceRef.current = data.server_time;
      setParticipants(data.participants || []);
      if (data.challenge) setChallenge(data.challenge);
      if (data.messages?.length) {
        setMessages((prev) => {
          const seen = new Set(prev.map((m: any) => m.id));
          return [...prev, ...data.messages.filter((m: any) => !seen.has(m.id))];
        });
      }
      if (data.active === false) router.replace('/(tabs)/social');
    } catch (_) {}
  }, [id, router]);

  useEffect(() => { const t = setInterval(beat, 2500); beat(); return () => clearInterval(t); }, [beat]);
  useEffect(() => { scRef.current?.scrollToEnd({ animated: true }); }, [messages]);

  const send = async () => {
    const t = text.trim(); if (!t) return; setText('');
    try { const { data } = await api.post(`/social/rooms/${id}/messages`, { text: t });
      setMessages((p) => p.some((m) => m.id === data.id) ? p : [...p, data]); } catch (_) {}
  };
  const react = async (e: string) => { try { await api.post(`/social/rooms/${id}/reactions`, { emoji: e }); } catch (_) {} };
  const invite = async () => { try { await Share.share({ message: `Join my FUUSIC listening room: ${(process.env.EXPO_PUBLIC_BACKEND_URL || '').replace(/\/$/, '')}/social/room/${id}` }); } catch (_) {} };
  const leave = () => router.replace('/(tabs)/social');

  if (error) return (
    <View style={s.center}><Text style={s.muted}>This room isn't available.</Text>
      <Pressable onPress={leave} style={s.backBtn}><Text style={s.backTxt}>Back to Social</Text></Pressable></View>
  );
  if (!room) return <View style={s.center}><ActivityIndicator color={TUBE.magenta} /></View>;

  return (
    <KeyboardAvoidingView style={s.screen} behavior={Platform.OS === 'ios' ? 'padding' : undefined} testID="listen-room">
      <View style={[s.header, { paddingTop: insets.top + 8 }]}>
        <Pressable onPress={leave} testID="listen-room-back" style={s.hIconBtn}><Ionicons name="arrow-back" size={22} color={TUBE.text} /></Pressable>
        <View style={s.hArt}>
          {room.content?.favicon ? <Image source={{ uri: room.content.favicon }} style={{ width: '100%', height: '100%' }} />
            : <Ionicons name="radio" size={20} color={TUBE.magenta} />}
        </View>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <View style={s.liveBadge}><Text style={s.liveBadgeTxt}>● LIVE</Text></View>
            <Text style={s.count}><Ionicons name="people" size={11} color={TUBE.textMuted} /> <Text testID="listen-room-count">{participants.length}</Text></Text>
          </View>
          <Text style={s.hTitle} numberOfLines={1}>{room.content?.name || room.title}</Text>
        </View>
        <Pressable onPress={invite} testID="listen-room-invite" style={s.hIconBtn}><Ionicons name="share-social" size={18} color={TUBE.text} /></Pressable>
        <Pressable onPress={leave} testID="listen-room-leave" style={s.hIconBtn}><Ionicons name="exit-outline" size={18} color={TUBE.text} /></Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ maxHeight: 78, flexGrow: 0 }}
        contentContainerStyle={s.partRow} testID="listen-room-participants">
        {participants.map((p) => (
          <View key={p.user_id} style={s.part}>
            <AvatarM name={p.name} url={p.avatar_url} size={44} />
            <Text style={s.partName} numberOfLines={1}>{p.role === 'host' ? '🎙 ' : ''}{(p.name || '').split(' ')[0]}</Text>
          </View>
        ))}
      </ScrollView>

      {challenge && (
        <View style={s.challenge} testID="listen-room-challenge">
          <Ionicons name="trophy" size={15} color="#fbbf24" />
          <View style={{ flex: 1 }}>
            <Text style={s.challengeTxt}>
              {challenge.awarded ? 'Challenge complete — BigPoints earned! 🎉' : `Listen with a friend: ${challenge.minutes}/${challenge.target} min`}
            </Text>
            <View style={s.pBar}><View style={[s.pFill, { width: `${Math.min(100, (challenge.minutes / challenge.target) * 100)}%` }]} /></View>
          </View>
          {challenge.awarded ? <Text style={s.challengePts}>+{challenge.reward_points}</Text> : null}
        </View>
      )}

      <ScrollView ref={scRef} style={{ flex: 1 }} contentContainerStyle={{ padding: TSPACE.md, gap: 10 }} testID="listen-room-chat">
        {messages.length === 0 && <Text style={s.emptyChat}>Say hi 👋 and vibe together.</Text>}
        {messages.map((m) => (
          <View key={m.id} style={s.msg}>
            <AvatarM name={m.name} url={m.avatar_url} size={30} />
            <View style={{ flex: 1 }}>
              <Text style={s.msgName}>{m.name}</Text>
              <Text style={s.msgTxt}>{m.text}</Text>
            </View>
          </View>
        ))}
      </ScrollView>

      <View style={[s.footer, { paddingBottom: insets.bottom + 8 }]}>
        <View style={s.reactRow} testID="listen-room-reactions">
          {REACTIONS.map((e) => (
            <Pressable key={e} onPress={() => react(e)} testID={`listen-room-react-${e}`} style={s.reactBtn}>
              <Text style={{ fontSize: 18 }}>{e}</Text>
            </Pressable>
          ))}
        </View>
        <View style={s.composer}>
          <TextInput value={text} onChangeText={setText} placeholder="Message the room…" placeholderTextColor={TUBE.textMuted}
            style={s.input} testID="listen-room-input" onSubmitEditing={send} returnKeyType="send" />
          <Pressable onPress={send} testID="listen-room-send" style={s.sendBtn}><Ionicons name="send" size={17} color="#fff" /></Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: TUBE.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: TUBE.bg, gap: 12 },
  muted: { color: TUBE.textMuted },
  backBtn: { paddingHorizontal: 16, paddingVertical: 10, borderRadius: 20, backgroundColor: TUBE.elevated },
  backTxt: { color: TUBE.text, fontWeight: '800' },
  header: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: TSPACE.md, paddingBottom: 10, borderBottomWidth: 1, borderBottomColor: TUBE.line },
  hIconBtn: { padding: 6 },
  hArt: { width: 44, height: 44, borderRadius: 12, overflow: 'hidden', backgroundColor: 'rgba(168,85,247,0.15)', alignItems: 'center', justifyContent: 'center' },
  liveBadge: { backgroundColor: 'rgba(239,68,68,0.2)', paddingHorizontal: 7, paddingVertical: 2, borderRadius: 7 },
  liveBadgeTxt: { color: '#fca5a5', fontSize: 9, fontWeight: '900' },
  count: { color: TUBE.textMuted, fontSize: TFONT.xs },
  hTitle: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '900', marginTop: 2 },
  partRow: { gap: 12, paddingHorizontal: TSPACE.md, paddingVertical: 12 },
  part: { width: 56, alignItems: 'center', gap: 4 },
  partName: { color: TUBE.textMuted, fontSize: 10, maxWidth: 54 },
  challenge: { flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: TSPACE.md, marginBottom: 4, padding: 10, borderRadius: TRADIUS.md, backgroundColor: 'rgba(251,191,36,0.1)', borderWidth: 1, borderColor: 'rgba(251,191,36,0.2)' },
  challengeTxt: { color: '#fde68a', fontSize: 11, fontWeight: '700' },
  pBar: { height: 5, borderRadius: 3, backgroundColor: 'rgba(255,255,255,0.1)', marginTop: 5, overflow: 'hidden' },
  pFill: { height: '100%', backgroundColor: '#fbbf24', borderRadius: 3 },
  challengePts: { color: '#fbbf24', fontWeight: '900' },
  emptyChat: { color: TUBE.textMuted, textAlign: 'center', paddingVertical: 30, fontSize: TFONT.sm },
  msg: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' },
  msgName: { color: TUBE.textMuted, fontSize: 11, fontWeight: '700' },
  msgTxt: { color: TUBE.text, fontSize: TFONT.sm, marginTop: 1 },
  footer: { borderTopWidth: 1, borderTopColor: TUBE.line, paddingHorizontal: TSPACE.md, paddingTop: 10, backgroundColor: TUBE.bg },
  reactRow: { flexDirection: 'row', gap: 8, marginBottom: 10 },
  reactBtn: { width: 40, height: 40, borderRadius: 20, backgroundColor: TUBE.elevated, alignItems: 'center', justifyContent: 'center' },
  composer: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  input: { flex: 1, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: 24, paddingHorizontal: 16, paddingVertical: 12, color: TUBE.text, fontSize: TFONT.sm },
  sendBtn: { width: 46, height: 46, borderRadius: 23, backgroundColor: TUBE.magenta, alignItems: 'center', justifyContent: 'center' },
});
