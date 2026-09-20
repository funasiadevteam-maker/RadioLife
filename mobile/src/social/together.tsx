import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, Modal, Linking, RefreshControl,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Image as ExpoImage } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../constants/tube';
import api from '../api/client';

const CTX_KINDS = [
  { key: 'listening', label: 'Listening', icon: 'musical-notes' },
  { key: 'eating', label: 'Eating', icon: 'restaurant' },
  { key: 'playing', label: 'Playing', icon: 'game-controller' },
  { key: 'place', label: 'At a place', icon: 'location' },
  { key: 'custom', label: 'Vibing', icon: 'sparkles' },
];
const CTX_ICON: any = Object.fromEntries(CTX_KINDS.map((c) => [c.key, c.icon]));
const ACTIVITIES = [['food', 'Food'], ['coffee', 'Coffee'], ['cinema', 'Cinema'], ['sports', 'Sports'], ['music', 'Live music'], ['hangout', 'Hangout']];

function timeAgo(iso?: string) {
  if (!iso) return '';
  const s = Math.max(1, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function Avatar({ name, url, size = 38 }: any) {
  const initials = (name || '?').split(' ').map((x: string) => x[0]).slice(0, 2).join('').toUpperCase();
  if (url) return <ExpoImage source={{ uri: url }} style={{ width: size, height: size, borderRadius: size / 2 }} />;
  return (
    <LinearGradient colors={['#a855f7', '#ec4899']} style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: '#fff', fontWeight: '900', fontSize: size * 0.36 }}>{initials}</Text>
    </LinearGradient>
  );
}

// ═══════════════════════════ Moments ═══════════════════════════════
export function MomentsTab({ onActivity }: { onActivity?: () => void }) {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/moments'); setItems(data.items || []); }
    catch (_) {} finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 14 }}
      showsVerticalScrollIndicator={false} testID="social-moments" keyboardShouldPersistTaps="handled"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={TUBE.magenta} />}>
      <MomentComposer onPosted={() => { load(); onActivity?.(); }} />
      {loading ? <ActivityIndicator color={TUBE.magenta} style={{ marginTop: 30 }} />
        : items.length === 0 ? <View style={st.empty}><Text style={st.emptyTxt}>No moments yet — share what you’re up to 📸</Text></View>
          : items.map((m) => <MomentCard key={m.moment_id} m={m} onChange={load} />)}
    </ScrollView>
  );
}

function MomentComposer({ onPosted }: any) {
  const [caption, setCaption] = useState('');
  const [media, setMedia] = useState<any>(null);
  const [uploading, setUploading] = useState(false);
  const [posting, setPosting] = useState(false);
  const [ctxKind, setCtxKind] = useState('custom');
  const [ctxLabel, setCtxLabel] = useState('');
  const [vis, setVis] = useState('friends');

  const pick = async () => {
    const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!perm.granted) {
      if (!perm.canAskAgain) Linking.openSettings();
      return;
    }
    const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images', 'videos'], quality: 0.7 });
    if (res.canceled || !res.assets?.length) return;
    const a = res.assets[0];
    setUploading(true);
    try {
      const fd = new FormData();
      const type = a.mimeType || (a.type === 'video' ? 'video/mp4' : 'image/jpeg');
      const name = a.fileName || `upload.${type.split('/')[1] || 'jpg'}`;
      // @ts-ignore RN FormData file shape
      fd.append('file', { uri: a.uri, name, type });
      const { data } = await api.post('/social/media/upload', fd, { headers: { 'Content-Type': 'multipart/form-data' } });
      setMedia({ url: data.url, media_type: data.media_type });
    } catch (_) {} finally { setUploading(false); }
  };

  const post = async () => {
    if (!media && !caption.trim()) return;
    setPosting(true);
    try {
      const label = ctxLabel.trim() || (CTX_KINDS.find((c) => c.key === ctxKind)?.label || '');
      await api.post('/social/moments', {
        caption, visibility: vis, media_url: media?.url, media_type: media?.media_type,
        context: { kind: ctxKind, label },
      });
      setCaption(''); setMedia(null); setCtxLabel(''); setCtxKind('custom');
      onPosted?.();
    } catch (_) {} finally { setPosting(false); }
  };

  return (
    <View style={st.composer} testID="moment-composer">
      <TextInput value={caption} onChangeText={setCaption} placeholder="What’s the moment? What are you listening to?"
        placeholderTextColor={TUBE.textMuted} style={st.captionInput} multiline testID="moment-caption" />
      {media && (
        <View style={st.mediaPreview}>
          {media.media_type === 'photo'
            ? <ExpoImage source={{ uri: media.url }} style={{ width: '100%', height: 180 }} contentFit="cover" />
            : <View style={st.mediaChip}><Ionicons name={media.media_type === 'video' ? 'videocam' : 'mic'} size={16} color="#fff" /><Text style={st.mediaChipTxt}>{media.media_type} attached</Text></View>}
          <Pressable onPress={() => setMedia(null)} style={st.mediaRemove} testID="moment-media-remove"><Ionicons name="close" size={16} color="#fff" /></Pressable>
        </View>
      )}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingVertical: 10 }}>
        {CTX_KINDS.map((c) => {
          const on = ctxKind === c.key;
          return (
            <Pressable key={c.key} onPress={() => setCtxKind(c.key)} testID={`moment-ctx-${c.key}`} style={{ flexShrink: 0 }}>
              {on ? <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.ctxChipA}><Ionicons name={c.icon as any} size={13} color="#fff" /><Text style={st.ctxTxtA}>{c.label}</Text></LinearGradient>
                : <View style={st.ctxChip}><Ionicons name={c.icon as any} size={13} color={TUBE.textMuted} /><Text style={st.ctxTxt}>{c.label}</Text></View>}
            </Pressable>
          );
        })}
      </ScrollView>
      {ctxKind !== 'custom' && (
        <TextInput value={ctxLabel} onChangeText={setCtxLabel} placeholder="Add detail (track, place, game…)"
          placeholderTextColor={TUBE.textMuted} style={st.ctxInput} testID="moment-ctx-label" />
      )}
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 4 }}>
        <Pressable onPress={pick} disabled={uploading} style={st.smallBtn} testID="moment-attach">
          {uploading ? <ActivityIndicator size="small" color={TUBE.text} /> : <Ionicons name="image" size={16} color={TUBE.text} />}
          <Text style={st.smallBtnTxt}>Media</Text>
        </Pressable>
        <Pressable onPress={() => setVis(vis === 'friends' ? 'public' : 'friends')} style={st.smallBtn} testID="moment-visibility">
          <Ionicons name={vis === 'public' ? 'globe' : 'people'} size={16} color={TUBE.text} />
          <Text style={st.smallBtnTxt}>{vis === 'public' ? 'Public' : 'Friends'}</Text>
        </Pressable>
        <Pressable onPress={post} disabled={posting} style={{ marginLeft: 'auto' }} testID="moment-post">
          <LinearGradient colors={['#a855f7', '#ec4899']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.postBtn}>
            {posting ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="send" size={15} color="#fff" />}
            <Text style={st.postTxt}>Share</Text>
          </LinearGradient>
        </Pressable>
      </View>
    </View>
  );
}

function MomentCard({ m, onChange }: any) {
  const [liked, setLiked] = useState(m.liked_by_me);
  const [likes, setLikes] = useState(m.like_count);
  const [showC, setShowC] = useState(false);
  const [comments, setComments] = useState<any[] | null>(null);
  const [ctext, setCtext] = useState('');
  const [trLang, setTrLang] = useState('hi');
  const [trText, setTrText] = useState<string | null>(null);
  const [trBusy, setTrBusy] = useState(false);
  const ctxIcon = CTX_ICON[m.context?.kind] || 'sparkles';

  const translate = async () => {
    if (trText) { setTrText(null); return; }
    setTrBusy(true);
    try { const { data } = await api.post('/social/translate', { text: m.caption, target_lang: trLang }); setTrText(data.translated); }
    catch (_) {} finally { setTrBusy(false); }
  };

  const toggleLike = async () => {
    setLiked((v: boolean) => !v); setLikes((n: number) => n + (liked ? -1 : 1));
    try { const { data } = await api.post(`/social/moments/${m.moment_id}/like`); setLiked(data.liked_by_me); setLikes(data.like_count); } catch (_) {}
  };
  const openComments = async () => {
    setShowC((v) => !v);
    if (comments === null) { try { const { data } = await api.get(`/social/moments/${m.moment_id}/comments`); setComments(data.items || []); } catch (_) { setComments([]); } }
  };
  const addComment = async () => {
    if (!ctext.trim()) return;
    try { const { data } = await api.post(`/social/moments/${m.moment_id}/comments`, { text: ctext.trim() }); setComments((c) => [...(c || []), data]); setCtext(''); } catch (_) {}
  };
  const del = async () => { try { await api.delete(`/social/moments/${m.moment_id}`); onChange?.(); } catch (_) {} };

  return (
    <View style={st.card} testID={`moment-${m.moment_id}`}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <Avatar name={m.author?.name} url={m.author?.avatar_url} size={36} />
        <View style={{ flex: 1 }}>
          <Text style={st.author} numberOfLines={1}>{m.author?.name || 'Listener'}</Text>
          <Text style={st.meta}>{timeAgo(m.created_at)} ago{m.city ? ` · ${m.city}` : ''}</Text>
        </View>
        {m.is_mine && <Pressable onPress={del} testID={`moment-delete-${m.moment_id}`}><Ionicons name="trash-outline" size={16} color={TUBE.textMuted} /></Pressable>}
      </View>
      {m.context?.label ? (
        <View style={st.ctxTag}><Ionicons name={ctxIcon} size={12} color="#d8b4fe" /><Text style={st.ctxTagTxt}>{m.context.label}</Text></View>
      ) : null}
      {m.caption ? <Text style={st.caption}>{trText || m.caption}</Text> : null}
      {m.caption ? (
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 6, flexWrap: 'wrap' }}>
          {['hi', 'ar', 'es', 'fr', 'en'].map((l) => (
            <Pressable key={l} onPress={() => { setTrLang(l); setTrText(null); }} testID={`moment-tr-${l}-${m.moment_id}`}
              style={[st.langChip, trLang === l && st.langChipOn]}>
              <Text style={[st.langChipTxt, trLang === l && { color: '#fff' }]}>{l.toUpperCase()}</Text>
            </Pressable>
          ))}
          <Pressable onPress={translate} disabled={trBusy} testID={`moment-translate-${m.moment_id}`} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
            {trBusy ? <ActivityIndicator size="small" color="#d8b4fe" /> : <Ionicons name="globe-outline" size={13} color="#d8b4fe" />}
            <Text style={st.trTxt}>{trText ? 'Original' : 'Translate'}</Text>
          </Pressable>
        </View>
      ) : null}
      {m.media_url ? (
        m.media_type === 'photo'
          ? <ExpoImage source={{ uri: m.media_url }} style={st.cardMedia} contentFit="cover" />
          : <Pressable onPress={() => Linking.openURL(m.media_url)} style={st.mediaOpen}>
              <Ionicons name={m.media_type === 'video' ? 'play-circle' : 'volume-high'} size={22} color="#fff" />
              <Text style={st.mediaOpenTxt}>Open {m.media_type}</Text>
            </Pressable>
      ) : null}
      <View style={{ flexDirection: 'row', gap: 18, marginTop: 12 }}>
        <Pressable onPress={toggleLike} style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }} testID={`moment-like-${m.moment_id}`}>
          <Ionicons name={liked ? 'heart' : 'heart-outline'} size={18} color={liked ? '#fb7185' : TUBE.textMuted} />
          <Text style={[st.actionTxt, liked && { color: '#fb7185' }]}>{likes}</Text>
        </Pressable>
        <Pressable onPress={openComments} style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }} testID={`moment-comment-${m.moment_id}`}>
          <Ionicons name="chatbubble-outline" size={17} color={TUBE.textMuted} />
          <Text style={st.actionTxt}>{m.comment_count}</Text>
        </Pressable>
      </View>
      {showC && (
        <View style={{ marginTop: 10, gap: 8 }} testID={`moment-comments-${m.moment_id}`}>
          {(comments || []).map((c) => (
            <View key={c.id} style={{ flexDirection: 'row', gap: 8 }}>
              <Avatar name={c.author?.name} url={c.author?.avatar_url} size={26} />
              <View style={st.commentBubble}><Text style={st.commentAuthor}>{c.author?.name}</Text><Text style={st.commentTxt}>{c.text}</Text></View>
            </View>
          ))}
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TextInput value={ctext} onChangeText={setCtext} placeholder="Add a comment…" placeholderTextColor={TUBE.textMuted}
              style={st.commentInput} testID={`moment-comment-input-${m.moment_id}`} />
            <Pressable onPress={addComment}><LinearGradient colors={['#a855f7', '#ec4899']} style={st.commentSend}><Ionicons name="send" size={14} color="#fff" /></LinearGradient></Pressable>
          </View>
        </View>
      )}
    </View>
  );
}

// ═══════════════════════════ Local Pulse ═══════════════════════════
export function PulseTab() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.get('/social/pulse').then(({ data }) => setData(data)).catch(() => setData({})); }, []);
  if (!data) return <View style={st.center}><ActivityIndicator color={TUBE.magenta} /></View>;
  const empty = !(data.moments?.length || data.outings?.length || data.play_sessions?.length);
  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 18 }} showsVerticalScrollIndicator={false} testID="social-pulse">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="location" size={16} color={TUBE.electric} />
        <Text style={st.pulseHead}>{data.city ? `Happening in ${data.city}` : 'Happening near you'}</Text>
      </View>
      {empty && <View style={st.empty}><Text style={st.emptyTxt}>It’s quiet — post a public Moment or plan to light it up 🌆</Text></View>}
      {data.outings?.length > 0 && (<View><Text style={st.sectionTitle}>PLANS NEAR YOU</Text>
        {data.outings.map((o: any) => (
          <View key={o.outing_id} style={st.pulseRow} testID={`pulse-outing-${o.outing_id}`}>
            <View style={[st.pulseIcon, { backgroundColor: 'rgba(34,211,238,0.15)' }]}><Ionicons name="location" size={18} color={TUBE.electric} /></View>
            <View style={{ flex: 1 }}><Text style={st.pulseTitle} numberOfLines={1}>{o.title}</Text>
              <Text style={st.pulseMeta}>{[o.place, o.when_text].filter(Boolean).join(' · ')} · {o.going_count} going</Text></View>
          </View>
        ))}</View>)}
      {data.play_sessions?.length > 0 && (<View><Text style={st.sectionTitle}>PLAYING NOW</Text>
        {data.play_sessions.map((p: any) => (
          <View key={p.session_id} style={st.pulseRow} testID={`pulse-play-${p.session_id}`}>
            <View style={[st.pulseIcon, { backgroundColor: 'rgba(236,72,153,0.15)' }]}><Ionicons name="game-controller" size={18} color={TUBE.pink} /></View>
            <View style={{ flex: 1 }}><Text style={st.pulseTitle} numberOfLines={1}>{p.title}</Text>
              <Text style={st.pulseMeta}>{p.game_label} · {p.player_count} playing</Text></View>
          </View>
        ))}</View>)}
      {data.moments?.length > 0 && (<View><Text style={st.sectionTitle}>PUBLIC MOMENTS</Text>
        {data.moments.map((m: any) => (
          <View key={m.moment_id} style={st.card} testID={`pulse-moment-${m.moment_id}`}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}><Avatar name={m.author?.name} url={m.author?.avatar_url} size={28} />
              <Text style={st.author} numberOfLines={1}>{m.author?.name}</Text><Text style={[st.meta, { marginLeft: 'auto' }]}>{timeAgo(m.created_at)}</Text></View>
            {m.context?.label ? <Text style={{ color: '#d8b4fe', fontSize: TFONT.xs, marginTop: 6 }}>{m.context.label}</Text> : null}
            {m.caption ? <Text style={st.caption} numberOfLines={3}>{m.caption}</Text> : null}
            {m.media_url && m.media_type === 'photo' ? <ExpoImage source={{ uri: m.media_url }} style={[st.cardMedia, { height: 140 }]} contentFit="cover" /> : null}
          </View>
        ))}</View>)}
    </ScrollView>
  );
}

// ═══════════════════════════ Go / Play sheets ══════════════════════
export function GoTogetherSheet({ visible, onClose }: any) {
  const [outings, setOutings] = useState<any[]>([]);
  const [friends, setFriends] = useState<any[]>([]);
  const [title, setTitle] = useState('');
  const [activity, setActivity] = useState('hangout');
  const [place, setPlace] = useState('');
  const [when, setWhen] = useState('');
  const [invitees, setInvitees] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/outings'); setOutings(data.items || []); } catch (_) {}
    try { const { data } = await api.get('/social/friends'); setFriends(data.friends || []); } catch (_) {}
  }, []);
  useEffect(() => { if (visible) load(); }, [visible, load]);
  const create = async () => {
    if (title.trim().length < 2) return;
    setSaving(true);
    try { await api.post('/social/outings', { title, activity, place, when_text: when, invitees, visibility: 'friends' }); setTitle(''); setPlace(''); setWhen(''); setInvitees([]); load(); }
    catch (_) {} finally { setSaving(false); }
  };
  return (
    <Sheet visible={visible} onClose={onClose} title="Go Together" testID="go-together-sheet">
      <TextInput value={title} onChangeText={setTitle} placeholder="What’s the plan?" placeholderTextColor={TUBE.textMuted} style={st.sheetInput} testID="outing-title" />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 6, paddingVertical: 8 }}>
        {ACTIVITIES.map(([k, l]) => {
          const on = activity === k;
          return <Pressable key={k} onPress={() => setActivity(k)} testID={`outing-act-${k}`} style={{ flexShrink: 0 }}>
            {on ? <LinearGradient colors={['#a855f7', '#ec4899']} style={st.ctxChipA}><Text style={st.ctxTxtA}>{l}</Text></LinearGradient> : <View style={st.ctxChip}><Text style={st.ctxTxt}>{l}</Text></View>}
          </Pressable>;
        })}
      </ScrollView>
      <TextInput value={place} onChangeText={setPlace} placeholder="Where? (place / area)" placeholderTextColor={TUBE.textMuted} style={st.sheetInput} testID="outing-place" />
      <TextInput value={when} onChangeText={setWhen} placeholder="When? e.g. Fri 8pm" placeholderTextColor={TUBE.textMuted} style={st.sheetInput} testID="outing-when" />
      {friends.length > 0 && (
        <View style={{ marginTop: 4 }}>
          <Text style={st.sheetLbl}>Invite friends</Text>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            {friends.map((f) => { const on = invitees.includes(f.user_id);
              return <Pressable key={f.user_id} testID={`outing-invite-${f.user_id}`} onPress={() => setInvitees((s) => on ? s.filter((x) => x !== f.user_id) : [...s, f.user_id])}>
                {on ? <LinearGradient colors={['#a855f7', '#ec4899']} style={st.ctxChipA}><Text style={st.ctxTxtA}>{f.name}</Text></LinearGradient> : <View style={st.ctxChip}><Text style={st.ctxTxt}>{f.name}</Text></View>}
              </Pressable>;
            })}
          </View>
        </View>
      )}
      <Pressable onPress={create} disabled={saving} testID="outing-create" style={{ marginTop: 12 }}>
        <LinearGradient colors={['#a855f7', '#ec4899']} style={st.sheetBtn}>{saving ? <ActivityIndicator color="#fff" /> : <><Ionicons name="location" size={16} color="#fff" /><Text style={st.sheetBtnTxt}>Create plan</Text></>}</LinearGradient>
      </Pressable>
      {outings.map((o) => <OutingRow key={o.outing_id} o={o} />)}
    </Sheet>
  );
}

function OutingRow({ o }: any) {
  const [rsvp, setRsvp] = useState(o.my_rsvp);
  const [going, setGoing] = useState(o.going_count);
  const set = async (s: string) => { try { const { data } = await api.post(`/social/outings/${o.outing_id}/rsvp`, { status: s }); setRsvp(data.my_rsvp); setGoing(data.going_count); } catch (_) {} };
  return (
    <View style={[st.card, { marginTop: 10 }]} testID={`outing-${o.outing_id}`}>
      <Text style={st.pulseTitle}>{o.title}</Text>
      <Text style={st.pulseMeta}>{[o.place, o.when_text].filter(Boolean).join(' · ')} · {going} going</Text>
      <View style={{ flexDirection: 'row', gap: 6, marginTop: 8 }}>
        {[['going', 'Going'], ['maybe', 'Maybe'], ['no', 'Can’t']].map(([k, l]) => (
          <Pressable key={k} onPress={() => set(k)} testID={`outing-rsvp-${o.outing_id}-${k}`}>
            {rsvp === k ? <LinearGradient colors={['#a855f7', '#ec4899']} style={st.ctxChipA}><Text style={st.ctxTxtA}>{l}</Text></LinearGradient> : <View style={st.ctxChip}><Text style={st.ctxTxt}>{l}</Text></View>}
          </Pressable>
        ))}
      </View>
    </View>
  );
}

export function PlayTogetherSheet({ visible, onClose }: any) {
  const [games, setGames] = useState<any[]>([]);
  const [sessions, setSessions] = useState<any[]>([]);
  const [game, setGame] = useState('trivia');
  const [title, setTitle] = useState('');
  const [saving, setSaving] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/play/games'); setGames(data.games || []); } catch (_) {}
    try { const { data } = await api.get('/social/play/sessions'); setSessions(data.items || []); } catch (_) {}
  }, []);
  useEffect(() => { if (visible) load(); }, [visible, load]);
  const create = async () => { setSaving(true); try { await api.post('/social/play/sessions', { game_key: game, title }); setTitle(''); load(); } catch (_) {} finally { setSaving(false); } };
  const join = async (sid: string) => { try { await api.post(`/social/play/sessions/${sid}/join`); load(); } catch (_) {} };
  return (
    <Sheet visible={visible} onClose={onClose} title="Play Together" testID="play-together-sheet">
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
        {games.map((g) => (
          <Pressable key={g.key} onPress={() => setGame(g.key)} testID={`play-game-${g.key}`} style={[st.gameCard, game === g.key && st.gameCardA]}>
            <Ionicons name={g.icon as any} size={18} color={TUBE.magenta} /><Text style={st.gameLbl}>{g.label}</Text>
          </Pressable>
        ))}
      </View>
      <TextInput value={title} onChangeText={setTitle} placeholder="Session title (optional)" placeholderTextColor={TUBE.textMuted} style={[st.sheetInput, { marginTop: 10 }]} testID="play-title" />
      <Pressable onPress={create} disabled={saving} testID="play-create" style={{ marginTop: 10 }}>
        <LinearGradient colors={['#a855f7', '#ec4899']} style={st.sheetBtn}>{saving ? <ActivityIndicator color="#fff" /> : <><Ionicons name="game-controller" size={16} color="#fff" /><Text style={st.sheetBtnTxt}>Start session</Text></>}</LinearGradient>
      </Pressable>
      {sessions.map((p) => (
        <View key={p.session_id} style={[st.pulseRow, { marginTop: 10 }]} testID={`play-session-${p.session_id}`}>
          <View style={[st.pulseIcon, { backgroundColor: 'rgba(236,72,153,0.15)' }]}><Ionicons name="game-controller" size={18} color={TUBE.pink} /></View>
          <View style={{ flex: 1 }}><Text style={st.pulseTitle} numberOfLines={1}>{p.title}</Text><Text style={st.pulseMeta}>{p.game_label} · {p.player_count} playing</Text></View>
          {p.joined ? <Text style={{ color: '#86efac', fontSize: TFONT.xs, fontWeight: '800' }}>Joined</Text>
            : <Pressable onPress={() => join(p.session_id)} testID={`play-join-${p.session_id}`}><LinearGradient colors={['#a855f7', '#ec4899']} style={st.joinBtn}><Text style={st.joinTxt}>Join</Text></LinearGradient></Pressable>}
        </View>
      ))}
    </Sheet>
  );
}

export function ShopTogetherSheet({ visible, onClose }: any) {
  const [carts, setCarts] = useState<any[]>([]);
  const [friends, setFriends] = useState<any[]>([]);
  const [active, setActive] = useState<any>(null);
  const [name, setName] = useState('');
  const [members, setMembers] = useState<string[]>([]);
  const [itTitle, setItTitle] = useState('');
  const [itPrice, setItPrice] = useState('');
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/carts'); setCarts(data.items || []); setActive((a: any) => a ? (data.items.find((c: any) => c.cart_id === a.cart_id) || null) : null); } catch (_) {}
    try { const { data } = await api.get('/social/friends'); setFriends(data.friends || []); } catch (_) {}
  }, []);
  useEffect(() => { if (visible) load(); }, [visible, load]);
  const create = async () => { setBusy(true); try { const { data } = await api.post('/social/carts', { name: name || 'Group cart', members }); setActive(data); setName(''); setMembers([]); load(); } catch (_) {} finally { setBusy(false); } };
  const addItem = async () => { if (!itTitle.trim()) return; try { const { data } = await api.post(`/social/carts/${active.cart_id}/items`, { title: itTitle.trim(), price_cents: Math.round(parseFloat(itPrice || '0') * 100), qty: 1 }); setActive(data); setItTitle(''); setItPrice(''); } catch (_) {} };
  const removeItem = async (id: string) => { try { const { data } = await api.delete(`/social/carts/${active.cart_id}/items/${id}`); setActive(data); } catch (_) {} };
  const checkout = async () => { try { const { data } = await api.post(`/social/carts/${active.cart_id}/checkout`, {}); if (data.checkout_url) Linking.openURL(data.checkout_url); } catch (_) {} };
  return (
    <Sheet visible={visible} onClose={onClose} title="Shop Together" testID="shop-together-sheet">
      {!active ? (
        <View style={{ gap: 10 }}>
          <TextInput value={name} onChangeText={setName} placeholder="Cart name (e.g. Iftar groceries)" placeholderTextColor={TUBE.textMuted} style={st.sheetInput} testID="cart-name" />
          {friends.length > 0 ? (
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>
              {friends.map((f) => {
                const on = members.includes(f.user_id);
                return <Pressable key={f.user_id} onPress={() => setMembers((m) => on ? m.filter((x) => x !== f.user_id) : [...m, f.user_id])} testID={`cart-invite-${f.user_id}`}>
                  {on ? <LinearGradient colors={['#a855f7', '#ec4899']} style={st.ctxChipA}><Text style={st.ctxTxtA}>{f.name}</Text></LinearGradient> : <View style={st.ctxChip}><Text style={st.ctxTxt}>{f.name}</Text></View>}
                </Pressable>;
              })}
            </View>
          ) : null}
          <Pressable onPress={create} disabled={busy} testID="cart-create"><LinearGradient colors={['#a855f7', '#ec4899']} style={st.sheetBtn}>{busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="people" size={16} color="#fff" /><Text style={st.sheetBtnTxt}>Create cart</Text></>}</LinearGradient></Pressable>
          {carts.map((c) => (
            <Pressable key={c.cart_id} onPress={() => setActive(c)} testID={`cart-open-${c.cart_id}`} style={st.pulseRow}>
              <View style={[st.pulseIcon, { backgroundColor: 'rgba(168,85,247,0.15)' }]}><Ionicons name="people" size={18} color="#d8b4fe" /></View>
              <View style={{ flex: 1 }}><Text style={st.pulseTitle} numberOfLines={1}>{c.name}</Text><Text style={st.pulseMeta}>{c.item_count} items · {c.members.length} people</Text></View>
              <Ionicons name="chevron-forward" size={16} color={TUBE.textMuted} />
            </Pressable>
          ))}
        </View>
      ) : (
        <View style={{ gap: 10 }} testID="cart-detail">
          <Pressable onPress={() => setActive(null)} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}><Ionicons name="close" size={13} color={TUBE.textMuted} /><Text style={st.trTxt}>All carts</Text></Pressable>
          <Text style={st.sheetTitle}>{active.name}</Text>
          {active.items.length === 0 ? <Text style={st.dim2}>No items yet — add the first one.</Text> : null}
          {active.items.map((it: any) => (
            <View key={it.item_id} style={[st.pulseRow, { gap: 8 }]} testID={`cart-item-${it.item_id}`}>
              <View style={{ flex: 1 }}><Text style={st.pulseTitle} numberOfLines={1}>{it.title}</Text><Text style={st.pulseMeta}>added by {it.added_by_name}</Text></View>
              <Text style={{ color: TUBE.text, fontWeight: '900', fontSize: TFONT.sm }}>${((it.price_cents || 0) / 100).toFixed(2)}</Text>
              <Pressable onPress={() => removeItem(it.item_id)}><Ionicons name="trash-outline" size={15} color={TUBE.textMuted} /></Pressable>
            </View>
          ))}
          <View style={{ flexDirection: 'row', gap: 8, alignItems: 'center' }}>
            <TextInput value={itTitle} onChangeText={setItTitle} placeholder="Item" placeholderTextColor={TUBE.textMuted} style={[st.sheetInput, { flex: 1 }]} testID="cart-item-title" />
            <TextInput value={itPrice} onChangeText={setItPrice} placeholder="$" keyboardType="numeric" placeholderTextColor={TUBE.textMuted} style={[st.sheetInput, { width: 64 }]} testID="cart-item-price" />
            <Pressable onPress={addItem} testID="cart-item-add"><LinearGradient colors={['#a855f7', '#ec4899']} style={st.chatSend2}><Ionicons name="send" size={15} color="#fff" /></LinearGradient></Pressable>
          </View>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
            <Text style={{ color: TUBE.text, fontWeight: '900', fontSize: TFONT.md }}>Total ${((active.total_cents || 0) / 100).toFixed(2)}</Text>
            <Pressable onPress={checkout} testID="cart-checkout"><LinearGradient colors={['#a855f7', '#ec4899']} style={st.joinBtn}><Text style={st.joinTxt}>Checkout</Text></LinearGradient></Pressable>
          </View>
        </View>
      )}
    </Sheet>
  );
}

export function DiscoverSection() {
  const [data, setData] = useState<any>(null);
  useEffect(() => { api.get('/social/discover').then(({ data }) => setData(data)).catch(() => {}); }, []);
  const follow = async (uid: string) => { try { await api.post('/social/friends/request', { user_id: uid }); setData((d: any) => ({ ...d, people: d.people.filter((p: any) => p.user_id !== uid) })); } catch (_) {} };
  if (!data || (!data.people?.length && !data.shows?.length)) return null;
  return (
    <View style={{ marginBottom: 18 }} testID="discover-section">
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 6 }}><Ionicons name="sparkles" size={15} color="#d8b4fe" /><Text style={st.author}>Discover</Text></View>
      {data.headline ? <Text style={[st.pulseMeta, { marginBottom: 10 }]}>{data.headline}</Text> : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}>
        {(data.people || []).map((p: any) => (
          <View key={p.user_id} style={st.discCard} testID={`discover-person-${p.user_id}`}>
            <Avatar name={p.name} url={p.avatar_url} size={48} />
            <Text style={st.discName} numberOfLines={1}>{p.name}</Text>
            <Text style={st.discReason} numberOfLines={1}>{p.reason}</Text>
            <Pressable onPress={() => follow(p.user_id)} testID={`discover-follow-${p.user_id}`} style={{ width: '100%' }}><LinearGradient colors={['#a855f7', '#ec4899']} style={st.discBtn}><Text style={st.joinTxt}>Add</Text></LinearGradient></Pressable>
          </View>
        ))}
      </ScrollView>
    </View>
  );
}


function Sheet({ visible, onClose, title, testID, children }: any) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={st.sheetWrap}>
        <View style={st.sheet} testID={testID}>
          <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
            <Text style={st.sheetTitle}>{title}</Text>
            <Pressable onPress={onClose} testID="sheet-close"><Ionicons name="close" size={22} color={TUBE.text} /></Pressable>
          </View>
          <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">{children}</ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const st = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 },
  empty: { backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 20, alignItems: 'center' },
  emptyTxt: { color: TUBE.textMuted, fontSize: TFONT.sm, textAlign: 'center' },
  composer: { backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 14 },
  captionInput: { color: TUBE.text, fontSize: TFONT.sm, minHeight: 44, textAlignVertical: 'top' },
  mediaPreview: { marginTop: 8, borderRadius: 14, overflow: 'hidden', borderWidth: 1, borderColor: TUBE.line, position: 'relative' },
  mediaChip: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 14, backgroundColor: 'rgba(168,85,247,0.15)' },
  mediaChipTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '700', textTransform: 'capitalize' },
  mediaRemove: { position: 'absolute', top: 8, right: 8, width: 30, height: 30, borderRadius: 15, backgroundColor: 'rgba(0,0,0,0.6)', alignItems: 'center', justifyContent: 'center' },
  ctxChip: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, height: 32, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.05)' },
  ctxChipA: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 12, height: 32, borderRadius: 16 },
  ctxTxt: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800' },
  ctxTxtA: { color: '#fff', fontSize: TFONT.xs, fontWeight: '800' },
  ctxInput: { backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: TUBE.line, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 9, color: TUBE.text, fontSize: TFONT.sm, marginBottom: 6 },
  smallBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 40, paddingHorizontal: 12, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.05)' },
  smallBtnTxt: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  postBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, height: 40, paddingHorizontal: 18, borderRadius: 20 },
  postTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  card: { backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 14 },
  author: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  meta: { color: TUBE.textMuted, fontSize: TFONT.xs, marginTop: 1 },
  ctxTag: { alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 5, marginTop: 10, paddingHorizontal: 10, height: 26, borderRadius: 13, backgroundColor: 'rgba(168,85,247,0.15)' },
  ctxTagTxt: { color: '#d8b4fe', fontSize: TFONT.xs, fontWeight: '800' },
  caption: { color: '#e5e7eb', fontSize: TFONT.sm, marginTop: 8, lineHeight: 20 },
  cardMedia: { width: '100%', height: 220, borderRadius: 14, marginTop: 10, backgroundColor: '#000' },
  mediaOpen: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 56, borderRadius: 14, marginTop: 10, backgroundColor: 'rgba(168,85,247,0.15)' },
  mediaOpenTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '800', textTransform: 'capitalize' },
  actionTxt: { color: TUBE.textMuted, fontSize: TFONT.sm, fontWeight: '800' },
  commentBubble: { flex: 1, backgroundColor: 'rgba(255,255,255,0.05)', borderRadius: 14, paddingHorizontal: 12, paddingVertical: 8 },
  commentAuthor: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800' },
  commentTxt: { color: TUBE.text, fontSize: TFONT.sm, marginTop: 1 },
  commentInput: { flex: 1, backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: TUBE.line, borderRadius: 20, paddingHorizontal: 14, height: 40, color: TUBE.text, fontSize: TFONT.sm },
  commentSend: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  pulseHead: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '900' },
  sectionTitle: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginBottom: 10 },
  pulseRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 12, marginBottom: 8 },
  pulseIcon: { width: 44, height: 44, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  pulseTitle: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '900' },
  pulseMeta: { color: TUBE.textMuted, fontSize: TFONT.xs, marginTop: 1 },
  sheetWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.7)' },
  sheet: { backgroundColor: '#0b0c16', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '88%', borderWidth: 1, borderColor: TUBE.line },
  sheetTitle: { color: TUBE.text, fontSize: TFONT.lg, fontWeight: '900' },
  sheetInput: { backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: TUBE.line, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11, color: TUBE.text, fontSize: TFONT.sm, marginTop: 8 },
  sheetLbl: { color: TUBE.textMuted, fontSize: TFONT.xs, marginBottom: 6 },
  sheetBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 46, borderRadius: 23 },
  sheetBtnTxt: { color: '#fff', fontSize: TFONT.md, fontWeight: '900' },
  gameCard: { width: '47%', flexGrow: 1, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 12, gap: 6 },
  gameCardA: { borderColor: TUBE.magenta, backgroundColor: 'rgba(168,85,247,0.15)' },
  gameLbl: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  joinBtn: { paddingHorizontal: 16, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center' },
  joinTxt: { color: '#fff', fontSize: TFONT.xs, fontWeight: '900' },
  langChip: { paddingHorizontal: 8, height: 24, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.05)', alignItems: 'center', justifyContent: 'center' },
  langChipOn: { backgroundColor: TUBE.magenta },
  langChipTxt: { color: TUBE.textMuted, fontSize: 10, fontWeight: '900' },
  trTxt: { color: '#d8b4fe', fontSize: TFONT.xs, fontWeight: '800' },
  dim2: { color: TUBE.textMuted, fontSize: TFONT.sm },
  chatSend2: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  discCard: { width: 150, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 12, alignItems: 'center', gap: 4 },
  discName: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '900', marginTop: 6 },
  discReason: { color: TUBE.textMuted, fontSize: 10, marginBottom: 4 },
  discBtn: { width: '100%', height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
});
