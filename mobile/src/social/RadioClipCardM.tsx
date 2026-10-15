// FUUSIC — mobile radio clip card (station highlight / listener clip) + Clip & Share modal.
import React, { useMemo, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, Modal, TextInput, ActivityIndicator, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useAudioPlayer } from 'expo-audio';
import api from '../api/client';

const WAVE = [30, 55, 80, 45, 90, 60, 35, 70, 95, 50, 65, 40, 85, 55, 75, 45, 60, 88, 42, 68];

export function RadioClipCardM({ item, t, onClip }: any) {
  const meta = item.meta || {};
  const player = useAudioPlayer(item.media_url ? { uri: item.media_url } : null);
  const [playing, setPlaying] = useState(false);
  const toggle = () => {
    try {
      if (playing) { player.pause(); setPlaying(false); }
      else { player.seekTo(0); player.play(); setPlaying(true); }
    } catch (_) {}
  };
  const isStation = meta.clip_kind === 'station_highlight';
  const dur = meta.duration_sec || 30;
  return (
    <View style={[s.clip, { backgroundColor: t.surfaceAlt || t.surface, borderColor: t.border }]} testID="radio-clip-card">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Pressable onPress={toggle} testID="rc-play"
          style={{ width: 44, height: 44, borderRadius: 999, overflow: 'hidden' }}>
          <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }}
            style={{ flex: 1, alignItems: 'center', justifyContent: 'center' }}>
            <Ionicons name={playing ? 'pause' : 'play'} size={20} color="#fff" />
          </LinearGradient>
        </Pressable>
        <View style={{ flex: 1 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5, marginBottom: 5 }}>
            <Ionicons name="radio" size={12} color={t.magenta} />
            <Text numberOfLines={1} style={{ color: t.textMuted, fontSize: 12, fontWeight: '700', flex: 1 }}>
              {meta.station_name}{meta.show_name ? ` · ${meta.show_name}` : ''}
            </Text>
          </View>
          <View style={{ flexDirection: 'row', alignItems: 'flex-end', gap: 2, height: 20 }}>
            {WAVE.map((h, i) => (
              <View key={i} style={{ flex: 1, height: `${h}%`, backgroundColor: t.magenta, opacity: 0.5, borderRadius: 2 }} />
            ))}
          </View>
        </View>
        <Text style={{ color: t.textMuted, fontSize: 11, fontWeight: '800' }}>0:{String(dur).padStart(2, '0')}</Text>
      </View>
      {isStation && meta.station_id ? (
        <Pressable onPress={onClip} testID="rc-clipshare"
          style={{ marginTop: 10, borderWidth: 1.5, borderColor: t.magenta, borderRadius: 11, paddingVertical: 9, alignItems: 'center', flexDirection: 'row', justifyContent: 'center', gap: 6 }}>
          <Ionicons name="cut" size={15} color={t.magenta} />
          <Text style={{ color: t.magenta, fontWeight: '800', fontSize: 13 }}>Clip & Share</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

export function ClipShareModalM({ visible, station, t, onClose, onPosted }: any) {
  const [start, setStart] = useState(0);
  const [comment, setComment] = useState('');
  const [vis, setVis] = useState('public');
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [elig, setElig] = useState<any>(null);
  const idem = useRef(`clip_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`);
  const previewPlayer = useAudioPlayer(elig?.buffer_audio_url ? { uri: elig.buffer_audio_url } : null);

  React.useEffect(() => {
    if (!visible || !station?.id) return;
    setDone(false); setComment(''); setStart(0);
    api.get(`/stations/${station.id}/clip-eligibility`)
      .then((r) => setElig(r.data)).catch(() => setElig({ allowed: false, reason: "Couldn't check clip permission." }));
  }, [visible, station?.id]);

  const share = async () => {
    setBusy(true);
    try {
      await api.post('/radio/clips/share', {
        station_id: station.id, start_offset: start, duration_seconds: 30,
        comment: comment.trim(), visibility: vis, idempotency_key: idem.current,
      });
      setDone(true);
      setTimeout(() => { onPosted?.(); onClose?.(); }, 800);
    } catch (_) {} finally { setBusy(false); }
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={s.backdrop}>
        <View style={[s.sheet, { backgroundColor: t.surface }]} testID="clipshare-modal-m">
          <View style={s.sheetHead}>
            <Text style={{ color: t.text, fontWeight: '900', fontSize: 16 }}>Clip a Moment</Text>
            <Pressable onPress={onClose} testID="clipshare-close-m"><Ionicons name="close" size={22} color={t.textMuted} /></Pressable>
          </View>
          {done ? (
            <View style={{ padding: 36, alignItems: 'center' }}>
              <Ionicons name="checkmark-circle" size={48} color={t.magenta} />
              <Text style={{ color: t.text, fontWeight: '800', fontSize: 16, marginTop: 10 }}>Clip shared to your wall!</Text>
            </View>
          ) : !elig ? (
            <View style={{ padding: 36, alignItems: 'center' }}><ActivityIndicator color={t.magenta} /></View>
          ) : !elig.allowed ? (
            <View style={{ padding: 18 }}>
              <Text style={{ color: t.textMuted, fontSize: 14, marginBottom: 14 }}>{elig.reason}</Text>
              <Pressable onPress={onClose} style={s.primaryBtn}><Text style={s.primaryTxt}>Share the Station instead</Text></Pressable>
            </View>
          ) : (
            <View style={{ padding: 18, gap: 12 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
                {station?.logo ? <Image source={{ uri: station.logo }} style={{ width: 38, height: 38, borderRadius: 9 }} /> : null}
                <Text style={{ color: t.text, fontWeight: '800', fontSize: 14 }}>{station?.name}</Text>
              </View>
              <Text style={{ color: t.textMuted, fontSize: 12 }}>Start at {Math.floor(start / 60)}:{String(Math.floor(start % 60)).padStart(2, '0')} · 30s window</Text>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <Pressable onPress={() => setStart((v) => Math.max(0, v - 15))} style={s.stepBtn}><Ionicons name="remove" size={18} color={t.text} /></Pressable>
                <Pressable onPress={() => setStart((v) => Math.min((elig.buffer_seconds || 300) - 30, v + 15))} style={s.stepBtn}><Ionicons name="add" size={18} color={t.text} /></Pressable>
                <Pressable testID="clipshare-preview-m" onPress={() => { try { previewPlayer.seekTo(start); previewPlayer.play(); } catch (_) {} }} style={[s.stepBtn, { flex: 1, flexDirection: 'row', gap: 6 }]}>
                  <Ionicons name="play" size={16} color={t.magenta} /><Text style={{ color: t.text, fontWeight: '700' }}>Preview</Text>
                </Pressable>
              </View>
              <TextInput value={comment} onChangeText={setComment} testID="clipshare-comment-m"
                placeholder="Add your comment…" placeholderTextColor={t.textMuted} multiline
                style={{ color: t.text, borderWidth: 1, borderColor: t.border, borderRadius: 12, padding: 12, minHeight: 64, textAlignVertical: 'top' }} />
              <Pressable onPress={() => setVis(vis === 'public' ? 'friends' : 'public')} style={s.visBtn}>
                <Ionicons name={vis === 'public' ? 'globe' : 'people'} size={15} color={t.magenta} />
                <Text style={{ color: t.text, fontWeight: '700' }}>{vis === 'public' ? 'Public' : 'Friends'}</Text>
              </Pressable>
              <Pressable onPress={share} disabled={busy} testID="clipshare-submit-m" style={[s.primaryBtn, busy && { opacity: 0.6 }]}>
                {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryTxt}>Share to My Wall</Text>}
              </Pressable>
            </View>
          )}
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  clip: { marginHorizontal: 14, marginBottom: 8, borderRadius: 14, borderWidth: 1, padding: 12 },
  backdrop: { flex: 1, backgroundColor: 'rgba(8,11,22,.6)', justifyContent: 'flex-end' },
  sheet: { borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingBottom: 30 },
  sheetHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: '#8883' },
  stepBtn: { backgroundColor: '#8882', borderRadius: 11, paddingVertical: 10, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center' },
  visBtn: { flexDirection: 'row', alignItems: 'center', gap: 7, backgroundColor: '#8882', alignSelf: 'flex-start', paddingVertical: 8, paddingHorizontal: 14, borderRadius: 999 },
  primaryBtn: { backgroundColor: '#a855f7', borderRadius: 999, paddingVertical: 13, alignItems: 'center' },
  primaryTxt: { color: '#fff', fontWeight: '800', fontSize: 15 },
});
