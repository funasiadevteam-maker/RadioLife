import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, SafeAreaView, FlatList,
  ActivityIndicator, RefreshControl, Modal, TextInput, Switch, ScrollView, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../src/contexts/AuthContext';
import api from '../src/api/client';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import { useGateStore } from '../src/stores/gateStore';

const MOODS = ['chill', 'party', 'romantic', 'uplifting', 'groove', 'intense'];

export default function LobbiesScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const openGate = useGateStore((s) => s.openGate);

  const [items, setItems] = useState<any[]>([]);
  const [channels, setChannels] = useState<any[]>([]);
  const [caps, setCaps] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filterChannel, setFilterChannel] = useState('');
  const [filterMood, setFilterMood] = useState('');
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    if (authLoading) return;
    if (!user) { router.replace('/login'); return; }
  }, [user, authLoading]);

  useEffect(() => {
    (async () => {
      try {
        const [c, h] = await Promise.all([
          api.get('/channels'),
          api.get('/lobbies/host_caps'),
        ]);
        setChannels(c.data.channels || []);
        setCaps(h.data);
      } catch {}
    })();
  }, []);

  const reload = useCallback(async () => {
    try {
      const params: any = {};
      if (filterChannel) params.channel = filterChannel;
      if (filterMood) params.mood = filterMood;
      const r = await api.get('/lobbies/list', { params });
      setItems(r.data.items || []);
    } catch {
      Alert.alert('Error', 'Failed to load lobbies');
    } finally { setLoading(false); setRefreshing(false); }
  }, [filterChannel, filterMood]);

  useEffect(() => { if (!authLoading && user) reload(); }, [reload, authLoading, user]);
  useEffect(() => {
    const id = setInterval(reload, 15000);
    return () => clearInterval(id);
  }, [reload]);

  const totalListeners = items.reduce((s, l) => s + (l.current_listener_count || 0), 0);

  const handleJoin = async (lobby: any) => {
    try {
      await api.post(`/lobbies/${lobby.lobby_id}/join`);
      router.push(`/lobby/${lobby.lobby_id}`);
    } catch (e: any) {
      const d = e?.response?.data?.detail;
      if (d === 'free_daily_join_cap_reached') {
        Alert.alert('Limit', 'Daily join limit reached — go Premium for unlimited lobbies');
      } else if (d === 'lobby_full') {
        Alert.alert('Full', 'This lobby is full');
      } else {
        Alert.alert('Error', d || 'Could not join');
      }
    }
  };

  if (authLoading || !user) {
    return <View style={s.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }

  const renderLobby = ({ item }: { item: any }) => {
    const pct = Math.min(100, (item.current_listener_count / item.max_listeners) * 100);
    return (
      <View style={s.card} testID={`lobby-card-${item.lobby_id}`}>
        <View style={s.cardTop}>
          <View style={[s.avatar, { backgroundColor: item.host_avatar_color || COLORS.primary }]}>
            <Text style={s.avatarLetter}>{(item.host_display_name || '?')[0].toUpperCase()}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.cardName} testID="lobby-card-name">{item.name}</Text>
            <Text style={s.cardHost}>
              hosted by <Text style={{ fontWeight: '800' }}>{item.host_display_name}</Text>
              {item.city ? ` · ${item.city}` : ''}
            </Text>
          </View>
        </View>
        {item.description ? <Text style={s.cardDesc} numberOfLines={2}>{item.description}</Text> : null}
        <View style={s.tagRow}>
          <View style={[s.tag, { borderColor: COLORS.secondary }]}>
            <Ionicons name="musical-note" size={10} color={COLORS.secondary} />
            <Text style={[s.tagText, { color: COLORS.secondary }]}>{item.channel_name || item.channel_slug}</Text>
          </View>
          {item.mood ? (
            <View style={s.tag}><Text style={s.tagText}>{item.mood}</Text></View>
          ) : null}
          {item.is_event ? (
            <View style={[s.tag, { borderColor: COLORS.orange }]}>
              <Ionicons name="flash" size={10} color={COLORS.orange} />
              <Text style={[s.tagText, { color: COLORS.orange }]}>EVENT</Text>
            </View>
          ) : null}
        </View>
        <View style={s.progressRow}>
          <View style={s.progressTrack}>
            <View style={[s.progressFill, { width: `${pct}%` }]} />
          </View>
          <Text style={s.progressLabel}>
            <Ionicons name="people" size={10} color={COLORS.textDim} /> {item.current_listener_count}/{item.max_listeners}
          </Text>
        </View>
        <TouchableOpacity style={s.joinBtn} onPress={() => handleJoin(item)}
          testID={`join-${item.lobby_id}`} activeOpacity={0.7}>
          <Ionicons name="radio" size={14} color="#fff" />
          <Text style={s.joinText}>Join lobby</Text>
        </TouchableOpacity>
      </View>
    );
  };

  return (
    <SafeAreaView style={s.screen} testID="lobbies-page">
      {/* Header */}
      <View style={s.header}>
        <View style={{ flex: 1 }}>
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn} testID="back-to-radio">
            <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
            <Text style={s.backText}>back to radio</Text>
          </TouchableOpacity>
          <Text style={s.title}>Lobbies</Text>
          <Text style={s.sub}>Listen with friends. Synced playback · live chat · majority skip-vote.</Text>
        </View>
        <TouchableOpacity style={s.hostBtn} onPress={() => setShowCreate(true)} testID="host-lobby-btn">
          <Ionicons name="add" size={14} color="#fff" />
          <Text style={s.hostBtnText}>Host a lobby</Text>
        </TouchableOpacity>
      </View>

      {/* Filters */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filterRow}
        contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 6 }}>
        <TouchableOpacity style={[s.filterChip, !filterChannel && s.filterActive]}
          onPress={() => setFilterChannel('')} testID="filter-channel-all">
          <Text style={[s.filterText, !filterChannel && s.filterTextActive]}>All channels</Text>
        </TouchableOpacity>
        {channels.slice(0, 6).map((c) => (
          <TouchableOpacity key={c.slug}
            style={[s.filterChip, filterChannel === c.slug && s.filterActive]}
            onPress={() => setFilterChannel(filterChannel === c.slug ? '' : c.slug)}
            testID={`filter-channel-${c.slug}`}>
            <Text style={[s.filterText, filterChannel === c.slug && s.filterTextActive]}>
              {c.name}
            </Text>
          </TouchableOpacity>
        ))}
      </ScrollView>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.filterRow}
        contentContainerStyle={{ paddingHorizontal: SPACING.md, gap: 6 }}>
        <TouchableOpacity style={[s.filterChip, !filterMood && s.filterActive]}
          onPress={() => setFilterMood('')} testID="filter-mood-all">
          <Text style={[s.filterText, !filterMood && s.filterTextActive]}>All moods</Text>
        </TouchableOpacity>
        {MOODS.map((m) => (
          <TouchableOpacity key={m}
            style={[s.filterChip, filterMood === m && s.filterActive]}
            onPress={() => setFilterMood(filterMood === m ? '' : m)}
            testID={`filter-mood-${m}`}>
            <Text style={[s.filterText, filterMood === m && s.filterTextActive]}>{m}</Text>
          </TouchableOpacity>
        ))}
      </ScrollView>

      <Text style={s.countLabel} testID="lobbies-count">
        {items.length} LIVE · {totalListeners} LISTENING
      </Text>

      {/* List */}
      <FlatList
        data={items}
        keyExtractor={(i) => i.lobby_id}
        renderItem={renderLobby}
        contentContainerStyle={{ paddingHorizontal: SPACING.md, paddingBottom: 40 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); reload(); }}
          tintColor={COLORS.primary} />}
        ListEmptyComponent={
          loading ? (
            <View style={s.empty}><ActivityIndicator size="large" color={COLORS.primary} /></View>
          ) : (
            <View style={s.empty} testID="lobbies-empty">
              <Ionicons name="people" size={36} color={COLORS.textMuted} />
              <Text style={s.emptyTitle}>No live lobbies yet</Text>
              <Text style={s.emptySub}>Be the first to host one — your friends can drop in with a single tap.</Text>
              <TouchableOpacity style={s.hostBtn} onPress={() => setShowCreate(true)} testID="empty-host-btn">
                <Ionicons name="add" size={14} color="#fff" />
                <Text style={s.hostBtnText}>Host a lobby</Text>
              </TouchableOpacity>
            </View>
          )
        }
      />

      {/* Create Modal */}
      {showCreate && (
        <CreateLobbyModal
          channels={channels} caps={caps}
          isPremium={!!user.is_premium}
          onClose={() => setShowCreate(false)}
          onCreated={(id: string) => { setShowCreate(false); router.push(`/lobby/${id}`); }}
          onGate={(payload: any, ch: any) => {
            setShowCreate(false);
            setTimeout(() => openGate(payload, ch ? { slug: ch.slug, name: ch.name } : undefined), 150);
          }}
        />
      )}
    </SafeAreaView>
  );
}

/* ── Create Lobby Modal ── */
function CreateLobbyModal({ channels, caps, isPremium, onClose, onCreated, onGate }: any) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [channelSlug, setChannelSlug] = useState(channels[0]?.slug || '');
  const [mood, setMood] = useState('');
  const [isPublic, setIsPublic] = useState(true);
  const [maxListeners, setMaxListeners] = useState(String(caps?.max_listeners || 50));
  const [busy, setBusy] = useState(false);
  const [showChPicker, setShowChPicker] = useState(false);

  const chObj = useMemo(() => channels.find((c: any) => c.slug === channelSlug), [channelSlug, channels]);
  const locked = chObj?.premium_only && !isPremium;

  const submit = async () => {
    if (!name.trim()) return Alert.alert('Error', 'Lobby name required');
    setBusy(true);
    try {
      const r = await api.post('/lobbies/create', {
        name, description, channel_slug: channelSlug,
        mood: mood || null, is_public: isPublic,
        max_listeners: Number(maxListeners),
      });
      onCreated(r.data.lobby_id);
    } catch (e: any) {
      const status = e?.response?.status;
      const body = e?.response?.data;
      /* 403 from backend → close this modal first, then fire gate */
      if (status === 403 && body) {
        const payload = (typeof body.detail === 'object' && body.detail) ? body.detail : body;
        if (payload.code || payload.gating_message || payload.required_tier) {
          onGate(payload, chObj);
          return;
        }
      }
      /* Client-side fallback when backend returns non-403 for premium channel */
      if (locked) {
        onGate({
          code: 'channel_gated',
          required_tier: chObj?.exclusivity_tier || 'premium',
          current_tier: 'free',
          upgrade_path: chObj?.exclusivity_tier === 'premium' ? 'premium' : 'earn_badges',
          message: `${chObj?.name || 'This channel'} is exclusive. Upgrade to host a lobby on this channel.`,
        }, chObj);
        return;
      }
      const d = typeof body?.detail === 'string' ? body.detail : body?.detail?.message || 'Could not create lobby';
      if (typeof d === 'string' && d.startsWith('already_hosting:')) {
        onCreated(d.split(':')[1]);
        return;
      }
      Alert.alert('Error', d);
    } finally { setBusy(false); }
  };

  return (
    <Modal transparent animationType="slide" onRequestClose={onClose} testID="create-modal">
      <View style={s.modalBackdrop}>
        <View style={s.modalSheet}>
          <Text style={s.modalTitle}>Host a lobby</Text>
          <Text style={s.modalSub}>
            {isPremium
              ? `You're Premium — up to ${caps?.premium_host_max_listeners ?? 200} listeners.`
              : `Free hosts cap at ${caps?.free_host_max_listeners ?? 50} listeners.`}
          </Text>

          <Text style={s.fieldLabel}>Name</Text>
          <TextInput style={s.input} value={name} onChangeText={setName}
            placeholder="Friday night vibes" placeholderTextColor={COLORS.textMuted}
            maxLength={60} testID="lobby-name-input" />

          <Text style={s.fieldLabel}>Description (optional)</Text>
          <TextInput style={s.input} value={description} onChangeText={setDescription}
            placeholder="bring your karak chai" placeholderTextColor={COLORS.textMuted}
            maxLength={200} testID="lobby-desc-input" />

          <View style={s.row}>
            <View style={{ flex: 1 }}>
              <Text style={s.fieldLabel}>Channel</Text>
              <TouchableOpacity style={s.select} onPress={() => setShowChPicker(!showChPicker)}
                testID="lobby-channel-select">
                <Text style={s.selectText} numberOfLines={1}>{chObj?.name || 'Select'}</Text>
                <Ionicons name="chevron-down" size={12} color={COLORS.textDim} />
              </TouchableOpacity>
              {locked && (
                <View style={s.lockRow}>
                  <Ionicons name="lock-closed" size={9} color={COLORS.gold} />
                  <Text style={s.lockText}>Premium only</Text>
                </View>
              )}
            </View>
            <View style={{ flex: 1 }}>
              <Text style={s.fieldLabel}>Mood</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={{ flexDirection: 'row', gap: 4 }}>
                  {MOODS.map((m) => (
                    <TouchableOpacity key={m}
                      style={[s.moodChip, mood === m && { backgroundColor: COLORS.primary, borderColor: COLORS.primary }]}
                      onPress={() => setMood(mood === m ? '' : m)} testID={`lobby-mood-${m}`}>
                      <Text style={[s.moodChipText, mood === m && { color: '#fff' }]}>{m}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>
            </View>
          </View>

          {showChPicker && (
            <ScrollView style={s.pickerList}>
              {channels.map((c: any) => (
                <TouchableOpacity key={c.slug} style={s.pickerItem}
                  onPress={() => { setChannelSlug(c.slug); setShowChPicker(false); }}>
                  <Text style={s.pickerText}>{c.name}{c.premium_only ? ' · VIP' : ''}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}

          <View style={[s.row, { alignItems: 'center', marginTop: SPACING.sm }]}>
            <Text style={s.fieldLabel}>Public</Text>
            <Switch value={isPublic} onValueChange={setIsPublic}
              trackColor={{ false: COLORS.cardBorder, true: COLORS.primary }}
              testID="lobby-public-toggle" />
          </View>

          <View style={s.modalActions}>
            <TouchableOpacity onPress={onClose} style={s.cancelBtn} testID="cancel-create-btn">
              <Text style={s.cancelText}>Cancel</Text>
            </TouchableOpacity>
            <Pressable onPress={submit}
              style={[s.submitBtn, (busy || !name.trim()) && { opacity: 0.5 }]}
              disabled={busy || !name.trim()} testID="submit-create-btn">
              {busy ? <ActivityIndicator size={14} color="#fff" /> : (
                <>
                  <Text style={s.submitText}>Go live</Text>
                  <Ionicons name="radio" size={13} color="#fff" />
                </>
              )}
            </Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg },
  header: { flexDirection: 'row', padding: SPACING.md, paddingTop: SPACING.lg, gap: SPACING.md },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 4 },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  title: { color: '#fff', fontSize: 28, fontWeight: '900' },
  sub: { color: COLORS.textDim, fontSize: FONT.sm, lineHeight: 18, marginTop: 4 },
  hostBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: COLORS.primary, paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: RADIUS.md, alignSelf: 'flex-start',
  },
  hostBtnText: { color: '#fff', fontWeight: '700', fontSize: FONT.sm },
  filterRow: { maxHeight: 36, marginBottom: 4 },
  filterChip: {
    paddingHorizontal: 12, paddingVertical: 6, borderRadius: RADIUS.full,
    backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  filterActive: { backgroundColor: COLORS.primary, borderColor: COLORS.primary },
  filterText: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  filterTextActive: { color: '#fff', fontWeight: '700' },
  countLabel: {
    color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 2,
    paddingHorizontal: SPACING.md, marginVertical: SPACING.sm,
  },
  card: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.md, borderWidth: 1,
    borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.sm,
  },
  cardTop: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, marginBottom: 8 },
  avatar: {
    width: 36, height: 36, borderRadius: 18, alignItems: 'center', justifyContent: 'center',
  },
  avatarLetter: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
  cardName: { color: '#fff', fontSize: FONT.md, fontWeight: '800' },
  cardHost: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '600' },
  cardDesc: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: 8, lineHeight: 18 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginBottom: 8 },
  tag: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.sm,
    borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  tagText: { color: COLORS.textDim, fontSize: 10, fontWeight: '600', letterSpacing: 0.5 },
  progressRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 10 },
  progressTrack: { flex: 1, height: 4, backgroundColor: COLORS.cardBorder, borderRadius: 2 },
  progressFill: { height: 4, backgroundColor: COLORS.primary, borderRadius: 2 },
  progressLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700' },
  joinBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: COLORS.primary, paddingVertical: 10, borderRadius: RADIUS.md,
  },
  joinText: { color: '#fff', fontWeight: '700', fontSize: FONT.sm },
  empty: { alignItems: 'center', paddingVertical: 60, gap: 12 },
  emptyTitle: { color: '#fff', fontSize: FONT.lg, fontWeight: '800' },
  emptySub: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', lineHeight: 20, paddingHorizontal: 20 },
  /* Modal */
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: COLORS.card, borderTopLeftRadius: RADIUS.xl, borderTopRightRadius: RADIUS.xl,
    padding: SPACING.xl, maxHeight: '85%',
  },
  modalTitle: { color: '#fff', fontSize: FONT.xl, fontWeight: '900', marginBottom: 4 },
  modalSub: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.md, lineHeight: 18 },
  fieldLabel: { color: COLORS.textDim, fontSize: FONT.xs, fontWeight: '700', letterSpacing: 1, marginBottom: 4, marginTop: 8 },
  input: {
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10,
    color: '#fff', fontSize: FONT.sm,
  },
  row: { flexDirection: 'row', gap: SPACING.sm },
  select: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder,
    borderRadius: RADIUS.md, paddingHorizontal: 12, paddingVertical: 10,
  },
  selectText: { color: '#fff', fontSize: FONT.sm, flex: 1 },
  lockRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 },
  lockText: { color: COLORS.gold, fontSize: FONT.xs, fontWeight: '700' },
  moodChip: {
    paddingHorizontal: 10, paddingVertical: 6, borderRadius: RADIUS.full,
    borderWidth: 1, borderColor: COLORS.cardBorder, marginTop: 4,
  },
  moodChipText: { color: COLORS.textDim, fontSize: 10, fontWeight: '600' },
  pickerList: { maxHeight: 150, backgroundColor: COLORS.bg, borderRadius: RADIUS.md, marginTop: 4, padding: 4 },
  pickerItem: { paddingVertical: 8, paddingHorizontal: 12, borderBottomWidth: 1, borderBottomColor: COLORS.cardBorder },
  pickerText: { color: '#fff', fontSize: FONT.sm },
  modalActions: { flexDirection: 'row', gap: SPACING.sm, marginTop: SPACING.lg },
  cancelBtn: { flex: 1, paddingVertical: 12, alignItems: 'center', borderRadius: RADIUS.md, backgroundColor: COLORS.bg },
  cancelText: { color: COLORS.textDim, fontWeight: '700' },
  submitBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: COLORS.primary,
  },
  submitText: { color: '#fff', fontWeight: '700' },
});
