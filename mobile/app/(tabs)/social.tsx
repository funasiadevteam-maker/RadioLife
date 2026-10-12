import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, RefreshControl, Image, Modal,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';
import { useThemeTokens } from '../../src/theme/ThemeProvider';
import type { ThemeTokens } from '../../src/theme/tokens';
import api from '../../src/api/client';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { MomentsTab, PulseTab, GoTogetherSheet, PlayTogetherSheet, ShopTogetherSheet, DiscoverSection } from '../../src/social/together';
import { LiveTab } from '../../src/social/live';
import SocialWall from '../../src/social/wall';
import InterestOnboarding from '../../src/social/InterestOnboarding';
import { playImportedStation } from '../../src/services/playStation';

const TABS = [
  { key: 'together', label: 'Home', icon: 'sparkles' },
  { key: 'live', label: 'Live', icon: 'videocam' },
  { key: 'moments', label: 'Moments', icon: 'camera' },
  { key: 'pulse', label: 'Nearby', icon: 'location' },
  { key: 'friends', label: 'Friends', icon: 'people' },
  { key: 'dreams', label: 'Dreams', icon: 'moon' },
  { key: 'tarot', label: 'Tarot', icon: 'sparkles' },
];

export default function SocialScreen() {
  const insets = useSafeAreaInsets();
  const t = useThemeTokens();
  const s = makeStyles(t);
  const params = useLocalSearchParams<{ tab?: string }>();
  const initialTab = TABS.some((t) => t.key === params.tab) ? String(params.tab) : 'together';
  const [tab, setTab] = useState(initialTab);
  const [home, setHome] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const router = useRouter();

  useEffect(() => {
    if (params.tab && TABS.some((t) => t.key === params.tab)) setTab(String(params.tab));
  }, [params.tab]);

  const loadHome = useCallback(async () => {
    try { const { data } = await api.get('/social/home'); setHome(data); }
    catch (_) {} finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { loadHome(); }, [loadHome]);

  const counts = home?.counts || {};
  const h = home?.happening_now || {};

  return (
    <View style={s.screen} testID="social-screen">
      <InterestOnboarding />
      <View style={[s.header, { paddingTop: insets.top + 10 }]}>
        <Text style={s.title}>Social</Text>
        <Text style={s.sub}>DO THINGS TOGETHER</Text>
        <View style={s.statRow}>
          <Stat icon="radio" n={h.live_experiences || 0} label="Live" tint={t.pink} />
          <Stat icon="headset" n={h.friends_listening || 0} label="Listening" tint={t.electric} />
          <Stat icon="people" n={counts.friends || 0} label="Friends" tint={t.magenta} />
          <Stat icon="person-add" n={counts.following || 0} label="Following" tint="#38bdf8"
            onPress={() => router.push('/social/following' as any)} testID="social-stat-following" />
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 8, paddingVertical: 12 }} testID="social-tabs">
          {TABS.map((t) => {
            const active = tab === t.key;
            const badge = t.key === 'friends' ? (counts.friend_requests || 0) : 0;
            const onPress = () => {
              if (t.key === 'dreams') router.push('/social/dreams' as any);
              else if (t.key === 'tarot') router.push('/social/tarot' as any);
              else setTab(t.key);
            };
            return (
              <Pressable key={t.key} testID={`social-tab-${t.key}`} onPress={onPress}
                style={[s.chip, active && s.chipActive]}>
                <Ionicons name={t.icon as any} size={15} color={active ? '#fff' : t.textMuted} />
                <Text style={[s.chipTxt, active && { color: '#fff' }]}>{t.label}</Text>
                {badge > 0 && <View style={s.badge}><Text style={s.badgeTxt}>{badge}</Text></View>}
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {loading ? (
        <View style={s.center}><ActivityIndicator color={t.magenta} /></View>
      ) : tab === 'together' ? (
        <TogetherTab home={home} onNavigateTab={setTab} />
      ) : tab === 'friends' ? (
        <FriendsTab />
      ) : tab === 'moments' ? (
        <MomentsTab />
      ) : tab === 'pulse' ? (
        <PulseTab />
      ) : tab === 'live' ? (
        <LiveTab />
      ) : (
        <ComingSoon tab={tab} />
      )}
    </View>
  );
}

function Stat({ icon, n, label, tint, onPress, testID }: any) {
  const t = useThemeTokens();
  const s = makeStyles(t);
  const Wrap: any = onPress ? Pressable : View;
  return (
    <Wrap style={s.stat} onPress={onPress} testID={testID}>
      <View style={[s.statIcon, { backgroundColor: `${tint}22` }]}>
        <Ionicons name={icon} size={15} color={tint} />
      </View>
      <View>
        <Text style={s.statN}>{n}</Text>
        <Text style={s.statLbl}>{label}</Text>
      </View>
    </Wrap>
  );
}

function TogetherTab({ home, onNavigateTab }: any) {
  const router = useRouter();
  const t = useThemeTokens();
  const s = makeStyles(t);
  const activeChannelName = usePlayerStore((st) => st.activeChannelName);
  const activeChannelThumb = usePlayerStore((st) => st.activeChannelThumb);
  const activeChannel = usePlayerStore((st) => st.activeChannel);
  const [starting, setStarting] = useState(false);
  const [pickOpen, setPickOpen] = useState(false);
  const [goOpen, setGoOpen] = useState(false);
  const [playOpen, setPlayOpen] = useState(false);
  const [shopOpen, setShopOpen] = useState(false);

  const createRoom = async (content: any) => {
    setStarting(true);
    try {
      const { data } = await api.post('/social/rooms', {
        visibility: 'public', content_type: 'live', content,
      });
      router.push(`/social/room/${data.room_id}` as any);
    } catch (_) {} finally { setStarting(false); }
  };

  const startRoom = async () => {
    if (!activeChannel) { setPickOpen(true); return; }
    createRoom({
      id: activeChannel || 'radiolife',
      name: activeChannelName || 'FUUSIC Radio',
      favicon: activeChannelThumb || '',
    });
  };

  const pickAndStart = async (st: any) => {
    setPickOpen(false);
    const ok = await playImportedStation(st, router);
    if (!ok) return;
    createRoom({ id: st.id, name: st.name, favicon: st.favicon || st.logo_url || '' });
  };

  const actions = [
    { key: 'listen', label: 'Listen Together', blurb: 'Tune in with friends', icon: 'headset', grad: ['#a855f7', '#ec4899'], on: startRoom },
    { key: 'dreams', label: 'Dreams', blurb: 'Share or explore', icon: 'moon', grad: ['#7c3aed', '#c026d3'], on: () => router.push('/social/dreams' as any) },
    { key: 'tarot', label: 'Tarot', blurb: 'Draw a card', emoji: '🃏', grad: ['#6d28d9', '#db2777'], on: () => router.push('/social/tarot' as any) },
    { key: 'play', label: 'Play Together', blurb: 'Games with friends', icon: 'game-controller', grad: ['#2563eb', '#7c3aed'], on: () => setPlayOpen(true) },
    { key: 'go', label: 'Go Together', blurb: 'Plan an outing', icon: 'location', grad: ['#0891b2', '#2563eb'], on: () => setGoOpen(true) },
    { key: 'shop', label: 'Shop Together', blurb: 'Share a cart', icon: 'bag-handle', grad: ['#db2777', '#f59e0b'], on: () => setShopOpen(true) },
  ];

  return (
    <>
      <SocialWall actions={actions} onNavigateTab={onNavigateTab}
        onOpenFollowing={() => router.push('/social/following' as any)} />
      {starting && (
        <View style={s.startingPill}>
          <ActivityIndicator color="#fff" size="small" />
          <Text style={s.startingTxt}>Starting room…</Text>
        </View>
      )}
      <GoTogetherSheet visible={goOpen} onClose={() => setGoOpen(false)} />
      <PlayTogetherSheet visible={playOpen} onClose={() => setPlayOpen(false)} />
      <ShopTogetherSheet visible={shopOpen} onClose={() => setShopOpen(false)} />
      <StationPickSheet visible={pickOpen} onClose={() => setPickOpen(false)} onPick={pickAndStart} />
    </>
  );
}

function StationPickSheet({ visible, onClose, onPick }: any) {
  const t = useThemeTokens();
  const ps = makePs(t);
  const [q, setQ] = useState('');
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  useEffect(() => {
    if (!visible) return;
    let alive = true; setLoading(true);
    const t = setTimeout(async () => {
      try { const r = await api.get('/radio/browse', { params: { q: q || undefined, source: 'all', limit: 24 } }); if (alive) setItems(r.data?.items || []); }
      catch (_) {} finally { if (alive) setLoading(false); }
    }, 250);
    return () => { alive = false; clearTimeout(t); };
  }, [q, visible]);
  const pick = async (st: any) => { setBusyId(st.id); await onPick(st); setBusyId(null); };
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={ps.wrap}>
        <View style={ps.card} testID="listen-station-pick">
          <View style={ps.head}>
            <Text style={ps.title}>Pick a station to listen together</Text>
            <Pressable onPress={onClose} testID="listen-station-close"><Ionicons name="close" size={22} color={t.text} /></Pressable>
          </View>
          <Text style={ps.sub}>We'll start playing it and open a room you can share with friends.</Text>
          <View style={ps.search}>
            <Ionicons name="search" size={15} color={t.textMuted} />
            <TextInput value={q} onChangeText={setQ} placeholder="Search stations…" placeholderTextColor={t.textMuted} style={ps.input} testID="listen-station-search" />
          </View>
          {loading ? <ActivityIndicator color={t.magenta} style={{ marginVertical: 30 }} />
            : <ScrollView style={{ maxHeight: 380 }} testID="listen-station-list" showsVerticalScrollIndicator={false}>
                {items.length === 0 ? <Text style={ps.empty}>No stations found.</Text>
                  : items.map((st) => (
                    <Pressable key={st.id} testID={`listen-station-${st.id}`} onPress={() => pick(st)} disabled={!!busyId} style={ps.row}>
                      <Image source={{ uri: st.favicon || st.logo_url || undefined }} style={ps.fav} />
                      <View style={{ flex: 1 }}>
                        <Text style={ps.name} numberOfLines={1}>{st.name}</Text>
                        <Text style={ps.meta} numberOfLines={1}>{[st.country, st.language].filter(Boolean).join(' · ') || st.source}</Text>
                      </View>
                      {busyId === st.id ? <ActivityIndicator color={t.magenta} /> : <Ionicons name="play" size={18} color={t.text} />}
                    </Pressable>
                  ))}
              </ScrollView>}
        </View>
      </View>
    </Modal>
  );
}

const makePs = (t: ThemeTokens) => StyleSheet.create({
  wrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.7)' },
  card: { backgroundColor: t.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '85%', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 },
  title: { color: t.text, fontSize: TFONT.lg, fontWeight: '900', flex: 1 },
  sub: { color: t.textMuted, fontSize: TFONT.xs, marginBottom: 12 },
  search: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(255,255,255,0.05)', borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, borderRadius: 22, paddingHorizontal: 14, marginBottom: 10 },
  input: { flex: 1, color: t.text, fontSize: TFONT.sm, paddingVertical: 10 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 8, paddingHorizontal: 4 },
  fav: { width: 44, height: 44, borderRadius: 12, backgroundColor: 'rgba(168,85,247,0.2)' },
  name: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  meta: { color: t.textMuted, fontSize: TFONT.xs },
  empty: { color: t.textMuted, fontSize: TFONT.sm, textAlign: 'center', paddingVertical: 30 },
});

function FriendsTab() {
  const t = useThemeTokens();
  const s = makeStyles(t);
  const [q, setQ] = useState('');
  const [results, setResults] = useState<any[]>([]);
  const [data, setData] = useState<any>(null);
  const tRef = useRef<any>(null);

  const load = useCallback(async () => {
    try { const r = await api.get('/social/friends'); setData(r.data); } catch (_) {}
  }, []);
  useEffect(() => { load(); }, [load]);

  const search = (val: string) => {
    setQ(val);
    if (tRef.current) clearTimeout(tRef.current);
    if (val.trim().length < 2) { setResults([]); return; }
    tRef.current = setTimeout(async () => {
      try { const r = await api.get(`/social/users/search?q=${encodeURIComponent(val.trim())}`); setResults(r.data.items || []); }
      catch (_) {}
    }, 350);
  };
  const act = async (fn: () => Promise<any>) => { try { await fn(); await load(); if (q) search(q); } catch (_) {} };

  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 18 }}
      showsVerticalScrollIndicator={false} testID="social-friends" keyboardShouldPersistTaps="handled">
      <DiscoverSection />
      <View style={s.searchWrap}>
        <Ionicons name="search" size={16} color={t.textMuted} />
        <TextInput value={q} onChangeText={search} placeholder="Find people by name or email"
          placeholderTextColor={t.textMuted} style={s.searchInput} testID="social-friend-search"
          autoCapitalize="none" />
      </View>

      {results.length > 0 && (
        <View style={{ gap: 8 }} testID="social-search-results">
          <Text style={s.sectionTitle}>SEARCH RESULTS</Text>
          {results.map((u) => (
            <PersonRow key={u.user_id} u={u} right={
              u.relationship === 'friend' ? <TagM t="Friend" />
                : u.relationship === 'pending' ? <TagM t="Requested" />
                : <BtnM tid={`social-add-${u.user_id}`} icon="person-add" label="Add" tone
                        onPress={() => act(() => api.post('/social/friends/request', { user_id: u.user_id }))} />} />
          ))}
        </View>
      )}

      {data?.incoming?.length > 0 && (
        <View style={{ gap: 8 }} testID="social-incoming">
          <Text style={s.sectionTitle}>FRIEND REQUESTS</Text>
          {data.incoming.map((u: any) => (
            <PersonRow key={u.user_id} u={u} right={
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <BtnM tid={`social-accept-${u.user_id}`} icon="checkmark" label="Accept" tone
                          onPress={() => act(() => api.post(`/social/friends/${u.user_id}/accept`))} />
                <BtnM tid={`social-decline-${u.user_id}`} icon="close"
                          onPress={() => act(() => api.post(`/social/friends/${u.user_id}/decline`))} />
              </View>} />
          ))}
        </View>
      )}

      <View style={{ gap: 8 }}>
        <Text style={s.sectionTitle}>YOUR FRIENDS {data?.counts?.friends ? `(${data.counts.friends})` : ''}</Text>
        {(!data?.friends || data.friends.length === 0) ? (
          <View style={s.empty}><Text style={s.emptyTxt}>No friends yet — search above to connect.</Text></View>
        ) : data.friends.map((u: any) => (
          <PersonRow key={u.user_id} u={u} right={
            <BtnM tid={`social-remove-${u.user_id}`} icon="close"
                      onPress={() => act(() => api.delete(`/social/friends/${u.user_id}`))} />} />
        ))}
      </View>
    </ScrollView>
  );
}

function PersonRow({ u, right }: any) {
  const t = useThemeTokens();
  const s = makeStyles(t);
  return (
    <View style={s.personRow}>
      <AvatarM name={u.name} url={u.avatar_url} size={40} />
      <View style={{ flex: 1 }}>
        <Text style={s.personName} numberOfLines={1}>{u.name}</Text>
        {u.city ? <Text style={s.personCity}>{u.city}</Text> : null}
      </View>
      {right}
    </View>
  );
}

export function AvatarM({ name, url, size = 40 }: any) {
  const initials = (name || '?').split(' ').map((x: string) => x[0]).slice(0, 2).join('').toUpperCase();
  if (url) return <Image source={{ uri: url }} style={{ width: size, height: size, borderRadius: size / 2 }} />;
  return (
    <LinearGradient colors={['#a855f7', '#ec4899']} style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center' }}>
      <Text style={{ color: '#fff', fontWeight: '900', fontSize: size * 0.36 }}>{initials}</Text>
    </LinearGradient>
  );
}
function TagM({ t }: any) {
  const s = makeStyles(useThemeTokens());
  return <View style={s.tag}><Text style={s.tagTxt}>{t}</Text></View>;
}
function BtnM({ icon, label, onPress, tone, tid }: any) {
  const t = useThemeTokens();
  const s = makeStyles(t);
  return (
    <Pressable onPress={onPress} testID={tid} style={[s.btn, tone && s.btnTone]}>
      <Ionicons name={icon} size={14} color="#fff" />
      {label ? <Text style={s.btnTxt}>{label}</Text> : null}
    </Pressable>
  );
}
function ComingSoon({ tab }: any) {
  const t = useThemeTokens();
  const s = makeStyles(t);
  const map: any = {
    live: { icon: 'videocam', title: 'FUUSIC Live', blurb: 'Live video commerce from local businesses — going live soon.' },
    moments: { icon: 'camera', title: 'Moments', blurb: "Share what you're listening to and doing — with context." },
    clubs: { icon: 'people-circle', title: 'Clubs', blurb: 'Communities around what you love — coming soon.' },
  };
  const m = map[tab];
  return (
    <View style={s.center} testID="social-coming-soon">
      <View style={s.csIcon}><Ionicons name={m.icon} size={28} color="#fff" /></View>
      <Text style={s.csTitle}>{m.title}</Text>
      <Text style={s.csBlurb}>{m.blurb}</Text>
      <View style={s.csBadge}><Text style={s.csBadgeTxt}>COMING SOON</Text></View>
    </View>
  );
}

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  screen: { flex: 1, backgroundColor: t.bg },
  header: { paddingHorizontal: TSPACE.md, paddingBottom: 4, borderBottomWidth: 1, borderBottomColor: t.line, backgroundColor: t.bg },
  title: { color: t.text, fontSize: TFONT.xxl, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 2, marginTop: 2 },
  statRow: { flexDirection: 'row', gap: 10, marginTop: 12, flexWrap: 'wrap' },
  stat: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.md, paddingHorizontal: 12, paddingVertical: 8 },
  statIcon: { width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  statN: { color: t.text, fontSize: TFONT.md, fontWeight: '900' },
  statLbl: { color: t.textMuted, fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, height: 38, borderRadius: 19, backgroundColor: t.elevated },
  chipActive: { backgroundColor: t.magenta },
  chipTxt: { color: t.textMuted, fontSize: TFONT.sm, fontWeight: '800' },
  badge: { minWidth: 18, height: 18, paddingHorizontal: 4, borderRadius: 9, backgroundColor: t.electric, alignItems: 'center', justifyContent: 'center' },
  badgeTxt: { color: '#04121a', fontSize: 10, fontWeight: '900' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40, gap: 8 },
  hero: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 18, borderRadius: TRADIUS.lg },
  heroIcon: { width: 54, height: 54, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  heroTitle: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900' },
  heroSub: { color: 'rgba(255,255,255,0.75)', fontSize: TFONT.sm, marginTop: 2 },
  sectionTitle: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.5, marginBottom: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  gridItem: { width: '47%', flexGrow: 1, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 14, alignItems: 'center', gap: 8 },
  gridIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: 'rgba(168,85,247,0.15)', alignItems: 'center', justifyContent: 'center' },
  gridLabel: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  friendNow: { width: 92, alignItems: 'center', backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 10, gap: 4 },
  friendNowName: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  friendNowCtx: { color: t.electric, fontSize: 10 },
  empty: { backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 20, alignItems: 'center' },
  emptyTxt: { color: t.textMuted, fontSize: TFONT.sm, textAlign: 'center' },
  roomCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 12, marginBottom: 10 },
  roomArt: { width: 54, height: 54, borderRadius: 12, overflow: 'hidden', backgroundColor: 'rgba(168,85,247,0.15)', alignItems: 'center', justifyContent: 'center' },
  liveBadge: { backgroundColor: 'rgba(239,68,68,0.2)', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  liveBadgeTxt: { color: '#fca5a5', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  friendBadge: { backgroundColor: 'rgba(34,211,238,0.2)', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  friendBadgeTxt: { color: '#67e8f9', fontSize: 9, fontWeight: '900' },
  roomName: { color: t.text, fontSize: TFONT.md, fontWeight: '900' },
  roomMeta: { color: t.textMuted, fontSize: TFONT.xs, marginTop: 1 },
  searchWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, paddingHorizontal: 14, height: 48 },
  searchInput: { flex: 1, color: t.text, fontSize: TFONT.sm },
  personRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 12 },
  personName: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  personCity: { color: t.textMuted, fontSize: TFONT.xs, marginTop: 1 },
  tag: { backgroundColor: 'rgba(255,255,255,0.1)', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 16 },
  tagTxt: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '800' },
  btn: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 34, paddingHorizontal: 12, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.1)' },
  btnTone: { backgroundColor: t.magenta },
  btnTxt: { color: '#fff', fontSize: TFONT.xs, fontWeight: '800' },
  csIcon: { width: 64, height: 64, borderRadius: 18, backgroundColor: t.magenta, alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  csTitle: { color: t.text, fontSize: TFONT.xl, fontWeight: '900' },
  csBlurb: { color: t.textMuted, fontSize: TFONT.sm, textAlign: 'center', maxWidth: 280 },
  csBadge: { backgroundColor: 'rgba(168,85,247,0.2)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, marginTop: 8 },
  csBadgeTxt: { color: '#d8b4fe', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  startingPill: { position: 'absolute', bottom: 96, alignSelf: 'center', flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(0,0,0,0.85)', borderColor: t.line, borderWidth: 1, borderRadius: 22, paddingHorizontal: 16, paddingVertical: 10 },
  startingTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '700' },
});
