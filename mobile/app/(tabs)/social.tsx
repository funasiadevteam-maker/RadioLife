import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, RefreshControl, Image,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { TUBE, TSPACE, TRADIUS, TFONT } from '../../src/constants/tube';
import api from '../../src/api/client';
import { usePlayerStore } from '../../src/stores/usePlayerStore';
import { MomentsTab, PulseTab, GoTogetherSheet, PlayTogetherSheet, ShopTogetherSheet, DiscoverSection } from '../../src/social/together';
import { LiveTab } from '../../src/social/live';

const TABS = [
  { key: 'together', label: 'Together', icon: 'sparkles' },
  { key: 'live', label: 'Live', icon: 'videocam' },
  { key: 'moments', label: 'Moments', icon: 'camera' },
  { key: 'pulse', label: 'Pulse', icon: 'location' },
  { key: 'friends', label: 'Friends', icon: 'people' },
];

export default function SocialScreen() {
  const insets = useSafeAreaInsets();
  const params = useLocalSearchParams<{ tab?: string }>();
  const initialTab = TABS.some((t) => t.key === params.tab) ? String(params.tab) : 'together';
  const [tab, setTab] = useState(initialTab);
  const [home, setHome] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

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
      <View style={[s.header, { paddingTop: insets.top + 10 }]}>
        <Text style={s.title}>Social</Text>
        <Text style={s.sub}>DO THINGS TOGETHER</Text>
        <View style={s.statRow}>
          <Stat icon="radio" n={h.live_experiences || 0} label="Live" tint={TUBE.pink} />
          <Stat icon="headset" n={h.friends_listening || 0} label="Listening" tint={TUBE.electric} />
          <Stat icon="people" n={counts.friends || 0} label="Friends" tint={TUBE.magenta} />
        </View>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 8, paddingVertical: 12 }} testID="social-tabs">
          {TABS.map((t) => {
            const active = tab === t.key;
            const badge = t.key === 'friends' ? (counts.friend_requests || 0) : 0;
            return (
              <Pressable key={t.key} testID={`social-tab-${t.key}`} onPress={() => setTab(t.key)}
                style={[s.chip, active && s.chipActive]}>
                <Ionicons name={t.icon as any} size={15} color={active ? '#fff' : TUBE.textMuted} />
                <Text style={[s.chipTxt, active && { color: '#fff' }]}>{t.label}</Text>
                {badge > 0 && <View style={s.badge}><Text style={s.badgeTxt}>{badge}</Text></View>}
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {loading ? (
        <View style={s.center}><ActivityIndicator color={TUBE.magenta} /></View>
      ) : tab === 'together' ? (
        <TogetherTab home={home} refreshing={refreshing}
          onRefresh={() => { setRefreshing(true); loadHome(); }} />
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

function Stat({ icon, n, label, tint }: any) {
  return (
    <View style={s.stat}>
      <View style={[s.statIcon, { backgroundColor: `${tint}22` }]}>
        <Ionicons name={icon} size={15} color={tint} />
      </View>
      <View>
        <Text style={s.statN}>{n}</Text>
        <Text style={s.statLbl}>{label}</Text>
      </View>
    </View>
  );
}

function TogetherTab({ home, refreshing, onRefresh }: any) {
  const router = useRouter();
  const activeChannelName = usePlayerStore((st) => st.activeChannelName);
  const activeChannelThumb = usePlayerStore((st) => st.activeChannelThumb);
  const activeChannel = usePlayerStore((st) => st.activeChannel);
  const [starting, setStarting] = useState(false);
  const [goOpen, setGoOpen] = useState(false);
  const [playOpen, setPlayOpen] = useState(false);
  const [shopOpen, setShopOpen] = useState(false);

  const startRoom = async () => {
    setStarting(true);
    try {
      const content = {
        id: activeChannel || 'radiolife',
        name: activeChannelName || 'FUUSIC Radio',
        favicon: activeChannelThumb || '',
      };
      const { data } = await api.post('/social/rooms', {
        visibility: 'public', content_type: 'live', content,
      });
      router.push(`/social/room/${data.room_id}` as any);
    } catch (_) {} finally { setStarting(false); }
  };

  const doItems = [
    { key: 'listen', label: 'Listen Together', icon: 'headset', on: startRoom },
    { key: 'play', label: 'Play Together', icon: 'game-controller', on: () => setPlayOpen(true) },
    { key: 'go', label: 'Go Together', icon: 'location', on: () => setGoOpen(true) },
    { key: 'shop', label: 'Shop Together', icon: 'bag-handle', on: () => setShopOpen(true) },
  ];
  const rooms = home?.suggested_rooms || [];
  const friendsNow = home?.friends_now || [];

  return (
    <>
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 20 }}
      showsVerticalScrollIndicator={false} testID="social-together"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={TUBE.magenta} />}>
      <Pressable testID="social-start-room" onPress={startRoom} disabled={starting}>
        <LinearGradient colors={['#2a1148', '#3a0f52']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <View style={s.heroIcon}>
            {starting ? <ActivityIndicator color="#fff" /> : <Ionicons name="headset" size={24} color="#fff" />}
          </View>
          <View style={{ flex: 1 }}>
            <Text style={s.heroTitle}>Listen Together</Text>
            <Text style={s.heroSub} numberOfLines={1}>
              {activeChannelName ? `Invite friends to ${activeChannelName}` : 'Start a room and invite friends'}
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="rgba(255,255,255,0.6)" />
        </LinearGradient>
      </Pressable>

      <Pressable testID="social-open-dreams" onPress={() => router.push('/social/dreams' as any)}>
        <LinearGradient colors={['#1e1b4b', '#6d28d9']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <View style={s.heroIcon}><Ionicons name="moon" size={24} color="#fff" /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.heroTitle}>Dreams & Guidance</Text>
            <Text style={s.heroSub} numberOfLines={2}>
              Share a dream, get an AI reflection, connect with verified advisors
            </Text>
          </View>
          <Ionicons name="chevron-forward" size={20} color="rgba(255,255,255,0.6)" />
        </LinearGradient>
      </Pressable>

      <View>
        <Text style={s.sectionTitle}>DO SOMETHING TOGETHER</Text>
        <View style={s.grid}>
          {doItems.map((d) => (
            <Pressable key={d.key} testID={`social-do-${d.key}`} onPress={d.on} style={s.gridItem}>
              <View style={s.gridIcon}><Ionicons name={d.icon as any} size={20} color={TUBE.magenta} /></View>
              <Text style={s.gridLabel}>{d.label}</Text>
            </Pressable>
          ))}
        </View>
      </View>

      {friendsNow.length > 0 && (
        <View>
          <Text style={s.sectionTitle}>FRIENDS RIGHT NOW</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 10 }}
            testID="social-friends-now">
            {friendsNow.map((f: any) => (
              <Pressable key={f.user_id} style={s.friendNow} onPress={() => router.push(`/social/room/${f.room_id}` as any)}>
                <AvatarM name={f.name} url={f.avatar_url} size={44} />
                <Text style={s.friendNowName} numberOfLines={1}>{(f.name || '').split(' ')[0]}</Text>
                <Text style={s.friendNowCtx} numberOfLines={1}>{f.context || 'Listening'}</Text>
              </Pressable>
            ))}
          </ScrollView>
        </View>
      )}

      <View>
        <Text style={s.sectionTitle}>LIVE LISTENING ROOMS</Text>
        {rooms.length === 0 ? (
          <View style={s.empty}><Text style={s.emptyTxt}>No rooms live right now — start one above 🎧</Text></View>
        ) : rooms.map((r: any) => (
          <Pressable key={r.room_id} testID={`social-room-${r.room_id}`} style={s.roomCard}
            onPress={() => router.push(`/social/room/${r.room_id}` as any)}>
            <View style={s.roomArt}>
              {r.content?.favicon ? <Image source={{ uri: r.content.favicon }} style={{ width: '100%', height: '100%' }} />
                : <Ionicons name="radio" size={22} color={TUBE.magenta} />}
            </View>
            <View style={{ flex: 1 }}>
              <View style={{ flexDirection: 'row', gap: 6, marginBottom: 3 }}>
                <View style={s.liveBadge}><Text style={s.liveBadgeTxt}>● LIVE</Text></View>
                {r.has_friend && <View style={s.friendBadge}><Text style={s.friendBadgeTxt}>FRIEND</Text></View>}
              </View>
              <Text style={s.roomName} numberOfLines={1}>{r.content?.name || r.title}</Text>
              <Text style={s.roomMeta}>{r.participant_count} listening · {r.host_name}</Text>
            </View>
            <Ionicons name="play" size={18} color={TUBE.text} />
          </Pressable>
        ))}
      </View>
    </ScrollView>
    <GoTogetherSheet visible={goOpen} onClose={() => setGoOpen(false)} />
    <PlayTogetherSheet visible={playOpen} onClose={() => setPlayOpen(false)} />
    <ShopTogetherSheet visible={shopOpen} onClose={() => setShopOpen(false)} />
    </>
  );
}

function FriendsTab() {
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
        <Ionicons name="search" size={16} color={TUBE.textMuted} />
        <TextInput value={q} onChangeText={search} placeholder="Find people by name or email"
          placeholderTextColor={TUBE.textMuted} style={s.searchInput} testID="social-friend-search"
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
function TagM({ t }: any) { return <View style={s.tag}><Text style={s.tagTxt}>{t}</Text></View>; }
function BtnM({ icon, label, onPress, tone, tid }: any) {
  return (
    <Pressable onPress={onPress} testID={tid} style={[s.btn, tone && s.btnTone]}>
      <Ionicons name={icon} size={14} color="#fff" />
      {label ? <Text style={s.btnTxt}>{label}</Text> : null}
    </Pressable>
  );
}
function ComingSoon({ tab }: any) {
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

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: TUBE.bg },
  header: { paddingHorizontal: TSPACE.md, paddingBottom: 4, borderBottomWidth: 1, borderBottomColor: TUBE.line, backgroundColor: TUBE.bg },
  title: { color: TUBE.text, fontSize: TFONT.xxl, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800', letterSpacing: 2, marginTop: 2 },
  statRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  stat: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.md, paddingHorizontal: 12, paddingVertical: 8 },
  statIcon: { width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  statN: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '900' },
  statLbl: { color: TUBE.textMuted, fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.5 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, height: 38, borderRadius: 19, backgroundColor: TUBE.elevated },
  chipActive: { backgroundColor: TUBE.magenta },
  chipTxt: { color: TUBE.textMuted, fontSize: TFONT.sm, fontWeight: '800' },
  badge: { minWidth: 18, height: 18, paddingHorizontal: 4, borderRadius: 9, backgroundColor: TUBE.electric, alignItems: 'center', justifyContent: 'center' },
  badgeTxt: { color: '#04121a', fontSize: 10, fontWeight: '900' },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40, gap: 8 },
  hero: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 18, borderRadius: TRADIUS.lg },
  heroIcon: { width: 54, height: 54, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  heroTitle: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900' },
  heroSub: { color: 'rgba(255,255,255,0.75)', fontSize: TFONT.sm, marginTop: 2 },
  sectionTitle: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.5, marginBottom: 10 },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  gridItem: { width: '47%', flexGrow: 1, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 14, alignItems: 'center', gap: 8 },
  gridIcon: { width: 44, height: 44, borderRadius: 12, backgroundColor: 'rgba(168,85,247,0.15)', alignItems: 'center', justifyContent: 'center' },
  gridLabel: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  friendNow: { width: 92, alignItems: 'center', backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 10, gap: 4 },
  friendNowName: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  friendNowCtx: { color: TUBE.electric, fontSize: 10 },
  empty: { backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 20, alignItems: 'center' },
  emptyTxt: { color: TUBE.textMuted, fontSize: TFONT.sm, textAlign: 'center' },
  roomCard: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 12, marginBottom: 10 },
  roomArt: { width: 54, height: 54, borderRadius: 12, overflow: 'hidden', backgroundColor: 'rgba(168,85,247,0.15)', alignItems: 'center', justifyContent: 'center' },
  liveBadge: { backgroundColor: 'rgba(239,68,68,0.2)', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  liveBadgeTxt: { color: '#fca5a5', fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  friendBadge: { backgroundColor: 'rgba(34,211,238,0.2)', paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  friendBadgeTxt: { color: '#67e8f9', fontSize: 9, fontWeight: '900' },
  roomName: { color: TUBE.text, fontSize: TFONT.md, fontWeight: '900' },
  roomMeta: { color: TUBE.textMuted, fontSize: TFONT.xs, marginTop: 1 },
  searchWrap: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, paddingHorizontal: 14, height: 48 },
  searchInput: { flex: 1, color: TUBE.text, fontSize: TFONT.sm },
  personRow: { flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: TUBE.elevated, borderWidth: 1, borderColor: TUBE.line, borderRadius: TRADIUS.lg, padding: 12 },
  personName: { color: TUBE.text, fontSize: TFONT.sm, fontWeight: '800' },
  personCity: { color: TUBE.textMuted, fontSize: TFONT.xs, marginTop: 1 },
  tag: { backgroundColor: 'rgba(255,255,255,0.1)', paddingHorizontal: 12, paddingVertical: 7, borderRadius: 16 },
  tagTxt: { color: TUBE.textMuted, fontSize: TFONT.xs, fontWeight: '800' },
  btn: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 34, paddingHorizontal: 12, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.1)' },
  btnTone: { backgroundColor: TUBE.magenta },
  btnTxt: { color: '#fff', fontSize: TFONT.xs, fontWeight: '800' },
  csIcon: { width: 64, height: 64, borderRadius: 18, backgroundColor: TUBE.magenta, alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  csTitle: { color: TUBE.text, fontSize: TFONT.xl, fontWeight: '900' },
  csBlurb: { color: TUBE.textMuted, fontSize: TFONT.sm, textAlign: 'center', maxWidth: 280 },
  csBadge: { backgroundColor: 'rgba(168,85,247,0.2)', paddingHorizontal: 12, paddingVertical: 6, borderRadius: 16, marginTop: 8 },
  csBadgeTxt: { color: '#d8b4fe', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
});
