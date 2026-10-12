import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, Modal, Linking, RefreshControl, Share,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { Image as ExpoImage } from 'expo-image';
import { TSPACE, TRADIUS, TFONT } from '../constants/tube';
import { activeTokens } from '../theme/ThemeProvider';
import type { ThemeTokens } from '../theme/tokens';
import api from '../api/client';

const money = (c: number) => `$${((c || 0) / 100).toFixed(2)}`;

function Avatar({ name, url, size = 40 }: any) {
  const t = activeTokens;
  const st = makeStyles(t);
  const initials = (name || '?').split(' ').map((x: string) => x[0]).slice(0, 2).join('').toUpperCase();
  if (url) return <ExpoImage source={{ uri: url }} style={{ width: size, height: size, borderRadius: size / 2 }} />;
  return <LinearGradient colors={['#a855f7', '#ec4899']} style={{ width: size, height: size, borderRadius: size / 2, alignItems: 'center', justifyContent: 'center' }}><Text style={{ color: '#fff', fontWeight: '900', fontSize: size * 0.36 }}>{initials}</Text></LinearGradient>;
}

export function LiveTab() {
  const t = activeTokens;
  const st = makeStyles(t);
  const [shows, setShows] = useState<any[]>([]);
  const [upcoming, setUpcoming] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [open, setOpen] = useState<string | null>(null);
  const [goLive, setGoLive] = useState(false);
  const load = useCallback(async () => {
    try {
      const [live, sched] = await Promise.all([
        api.get('/social/liveshows?status=live'),
        api.get('/social/liveshows?status=scheduled'),
      ]);
      setShows(live.data.items || []);
      setUpcoming(sched.data.items || []);
    } catch (_) {} finally { setLoading(false); setRefreshing(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const toggleRemind = async (s: any) => {
    try {
      const { data } = await api.post(`/social/liveshows/${s.show_id}/remind`, { on: !s.reminded });
      setUpcoming((list) => list.map((x) => x.show_id === s.show_id ? { ...x, reminded: data.reminded } : x));
    } catch (_) {}
  };

  if (open) return <LiveViewer showId={open} onClose={() => { setOpen(null); load(); }} />;

  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 14 }}
      showsVerticalScrollIndicator={false} testID="social-live"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={t.magenta} />}>
      {upcoming[0] ? (
        <Pressable onPress={() => setOpen(upcoming[0].show_id)} testID="live-featured" style={st.featured}>
          {upcoming[0].cover_url
            ? <ExpoImage source={{ uri: upcoming[0].cover_url }} style={StyleSheet.absoluteFill} contentFit="cover" />
            : <LinearGradient colors={['#1e3a8a', '#0e7490']} style={StyleSheet.absoluteFill} />}
          <LinearGradient colors={['rgba(6,8,22,0.15)', 'rgba(6,8,22,0.95)']} style={StyleSheet.absoluteFill} />
          <View style={st.featuredInner}>
            <View style={st.featuredBadge}><Ionicons name="time-outline" size={10} color="#fff" /><Text style={st.liveBadgeTxt}> NEXT LIVE</Text></View>
            <Text style={st.featuredTitle} numberOfLines={2}>{upcoming[0].title}</Text>
            <View style={{ flexDirection: 'row', alignItems: 'center' }}>
              <Text style={st.featuredMeta}>{upcoming[0].business_name} · starts in </Text>
              <CountdownText iso={upcoming[0].scheduled_at} style={[st.featuredMeta, { fontWeight: '900' }]} />
            </View>
            <View style={{ flexDirection: 'row', gap: 8, marginTop: 10 }}>
              <Pressable onPress={() => toggleRemind(upcoming[0])} testID="live-featured-remind" style={[st.remindBtn, upcoming[0].reminded && st.remindOn]}>
                <Ionicons name="notifications" size={12} color={upcoming[0].reminded ? '#67e8f9' : '#cbd5e1'} />
                <Text style={[st.remindTxt, upcoming[0].reminded && { color: '#67e8f9' }]}>{upcoming[0].reminded ? 'Reminding' : 'Remind me'}</Text>
              </Pressable>
              <Pressable onPress={() => openCal(upcoming[0])} testID="live-featured-calendar" style={st.remindBtn}>
                <Ionicons name="calendar-outline" size={12} color="#cbd5e1" />
                <Text style={st.remindTxt}>Add to calendar</Text>
              </Pressable>
            </View>
          </View>
        </Pressable>
      ) : null}
      <Pressable onPress={() => setGoLive(true)} testID="live-golive">
        <LinearGradient colors={['#3a0f52', '#7f1d4a']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={st.golive}>
          <View style={st.goliveIcon}><Ionicons name="videocam" size={24} color="#fff" /></View>
          <View style={{ flex: 1 }}><Text style={st.goliveTitle}>Go Live</Text><Text style={st.goliveSub}>Stream to fans & sell products live</Text></View>
          <View style={st.liveTag}><Text style={st.liveTagTxt}>● LIVE</Text></View>
        </LinearGradient>
      </Pressable>

      {upcoming.length > 0 && (
        <View testID="live-upcoming" style={{ gap: 10 }}>
          <Text style={st.section}>UPCOMING LIVE EVENTS</Text>
          {upcoming.map((s) => (
            <Pressable key={s.show_id} onPress={() => setOpen(s.show_id)} testID={`live-upcoming-${s.show_id}`} style={st.showCard}>
              <LinearGradient colors={['#1e3a8a', '#0e7490']} style={st.showCover}>
                {s.cover_url ? <ExpoImage source={{ uri: s.cover_url }} style={{ width: '100%', height: '100%', opacity: 0.8 }} contentFit="cover" /> : <Ionicons name="videocam" size={28} color="rgba(255,255,255,0.6)" />}
                <View style={st.upcomingBadge}><Ionicons name="time-outline" size={10} color="#fff" /><Text style={st.liveBadgeTxt}> UPCOMING</Text></View>
              </LinearGradient>
              <View style={{ padding: 12 }}>
                <Text style={st.showTitle} numberOfLines={1}>{s.title}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                  <Ionicons name="time-outline" size={11} color={t.electric} />
                  <Text style={st.showMeta}>starts in </Text>
                  <CountdownText iso={s.scheduled_at} style={[st.showMeta, { color: t.electric, fontWeight: '900' }]} />
                </View>
                <Text style={st.showMeta} numberOfLines={1}>{s.business_name} · {s.pinned_products?.length || 0} products</Text>
                <View style={{ flexDirection: 'row', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                  <Pressable onPress={() => toggleRemind(s)} testID={`live-remind-${s.show_id}`} style={[st.remindBtn, s.reminded && st.remindOn]}>
                    <Ionicons name="notifications" size={12} color={s.reminded ? '#67e8f9' : '#cbd5e1'} />
                    <Text style={[st.remindTxt, s.reminded && { color: '#67e8f9' }]}>{s.reminded ? 'Reminding' : 'Remind me'}</Text>
                  </Pressable>
                  <Pressable onPress={() => openCal(s)} testID={`live-calendar-${s.show_id}`} style={st.remindBtn}>
                    <Ionicons name="calendar-outline" size={12} color="#cbd5e1" />
                    <Text style={st.remindTxt}>Add to calendar</Text>
                  </Pressable>
                </View>
              </View>
            </Pressable>
          ))}
        </View>
      )}

      {loading ? <ActivityIndicator color={t.magenta} style={{ marginTop: 30 }} />
        : shows.length === 0 ? <View style={st.empty}><Text style={st.emptyTxt}>No live shows right now — tap Go Live 🎥</Text></View>
          : shows.map((s) => (
            <Pressable key={s.show_id} onPress={() => setOpen(s.show_id)} testID={`live-show-${s.show_id}`} style={st.showCard}>
              <LinearGradient colors={['#4c1d95', '#be185d']} style={st.showCover}>
                {s.cover_url ? <ExpoImage source={{ uri: s.cover_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" /> : <Ionicons name="radio" size={28} color="rgba(255,255,255,0.6)" />}
                <View style={st.liveBadge}><Text style={st.liveBadgeTxt}>● LIVE</Text></View>
                <View style={st.viewerBadge}><Ionicons name="people" size={11} color="#fff" /><Text style={st.viewerTxt}>{s.viewer_count}</Text></View>
              </LinearGradient>
              <View style={{ padding: 12 }}>
                <Text style={st.showTitle} numberOfLines={1}>{s.title}</Text>
                <Text style={st.showMeta} numberOfLines={1}>{s.business_name} · {s.pinned_products?.length || 0} products</Text>
              </View>
            </Pressable>
          ))}
      <GoLiveSheet visible={goLive} onClose={() => setGoLive(false)} onLive={(id: string) => { setGoLive(false); setOpen(id); }} onScheduled={() => { setGoLive(false); load(); }} />
    </ScrollView>
  );
}

function whenText(iso?: string) {
  if (!iso) return 'Scheduled';
  const d = new Date(iso);
  const diff = d.getTime() - Date.now();
  if (diff <= 0) return 'Starting soon';
  const h = Math.floor(diff / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  const when = d.toLocaleString(undefined, { weekday: 'short', hour: 'numeric', minute: '2-digit' });
  return h >= 1 ? `Starts ${when} · in ${h}h` : `Starts ${when} · in ${m}m`;
}

function CountdownText({ iso, style }: { iso?: string; style?: any }) {
  const t = activeTokens;
  const st = makeStyles(t);
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  let diff = iso ? new Date(iso).getTime() - now : 0;
  let txt = 'Scheduled';
  if (iso) {
    if (diff <= 0) txt = 'Starting now…';
    else {
      const d = Math.floor(diff / 86400000); diff %= 86400000;
      const h = Math.floor(diff / 3600000); diff %= 3600000;
      const m = Math.floor(diff / 60000); diff %= 60000;
      const s = Math.floor(diff / 1000);
      const pad = (x: number) => String(x).padStart(2, '0');
      txt = `${d > 0 ? d + 'd ' : ''}${pad(h)}:${pad(m)}:${pad(s)}`;
    }
  }
  return <Text style={style}>{txt}</Text>;
}

function openCal(show: any) {
  const start = new Date(show.scheduled_at);
  const end = new Date(start.getTime() + 3600000);
  const fmt = (d: Date) => d.toISOString().replace(/[-:]/g, '').replace(/\.\d{3}/, '');
  const url = `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(show.title || 'Live show')}&details=${encodeURIComponent((show.business_name || '') + ' — live shopping on FUUSIC')}&dates=${fmt(start)}/${fmt(end)}`;
  Linking.openURL(url).catch(() => {});
}

function GoLiveSheet({ visible, onClose, onLive, onScheduled }: any) {
  const t = activeTokens;
  const st = makeStyles(t);
  const [title, setTitle] = useState('');
  const [biz, setBiz] = useState('');
  const [desc, setDesc] = useState('');
  const [when, setWhen] = useState<number>(0); // hours from now; 0 = now
  const [busy, setBusy] = useState(false);
  const presets = [{ h: 0, l: 'Now' }, { h: 1, l: 'In 1h' }, { h: 3, l: 'In 3h' }, { h: 24, l: 'Tomorrow' }];
  const go = async () => {
    if (title.trim().length < 2) return;
    setBusy(true);
    try {
      const body: any = { title, business_name: biz, description: desc };
      if (when > 0) body.scheduled_at = new Date(Date.now() + when * 3600000).toISOString();
      const { data } = await api.post('/social/liveshows', body);
      setTitle(''); setBiz(''); setDesc(''); setWhen(0);
      if (data.status === 'scheduled') onScheduled?.(); else onLive(data.show_id);
    }
    catch (_) {} finally { setBusy(false); }
  };
  return (
    <Sheet visible={visible} onClose={onClose} title="Go Live" testID="golive-sheet">
      <TextInput value={title} onChangeText={setTitle} placeholder="Show title" placeholderTextColor={t.textMuted} style={st.input} testID="golive-title" />
      <TextInput value={biz} onChangeText={setBiz} placeholder="Business name (optional)" placeholderTextColor={t.textMuted} style={st.input} testID="golive-biz" />
      <TextInput value={desc} onChangeText={setDesc} placeholder="What are you showing?" placeholderTextColor={t.textMuted} style={[st.input, { height: 70, textAlignVertical: 'top' }]} multiline testID="golive-desc" />
      <Text style={[st.section, { marginTop: 14 }]}>WHEN</Text>
      <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }} testID="golive-schedule">
        {presets.map((p) => (
          <Pressable key={p.h} onPress={() => setWhen(p.h)} testID={`golive-when-${p.h}`} style={[st.whenChip, when === p.h && st.whenChipActive]}>
            <Text style={[st.whenChipTxt, when === p.h && { color: '#fff' }]}>{p.l}</Text>
          </Pressable>
        ))}
      </View>
      <Pressable onPress={go} disabled={busy} testID="golive-start" style={{ marginTop: 14 }}>
        <LinearGradient colors={['#a855f7', '#ec4899']} style={st.btn}>{busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name={when > 0 ? 'calendar' : 'videocam'} size={16} color="#fff" /><Text style={st.btnTxt}>{when > 0 ? 'Schedule event' : 'Start streaming'}</Text></>}</LinearGradient>
      </Pressable>
    </Sheet>
  );
}

function LiveViewer({ showId, onClose }: any) {
  const t = activeTokens;
  const st = makeStyles(t);
  const [show, setShow] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [text, setText] = useState('');
  const [pinOpen, setPinOpen] = useState(false);
  const [buying, setBuying] = useState<string | null>(null);
  const [clips, setClips] = useState<any[]>([]);
  const [savingClip, setSavingClip] = useState(false);
  const [cohostOpen, setCohostOpen] = useState(false);
  const lastTs = useRef<string | null>(null);

  const loadShow = useCallback(async () => {
    try { const { data } = await api.get(`/social/liveshows/${showId}`); setShow(data); } catch (_) { onClose(); }
  }, [showId, onClose]);
  const loadClips = useCallback(async () => {
    try { const { data } = await api.get(`/social/liveshows/${showId}/clips`); setClips(data.items || []); } catch (_) {}
  }, [showId]);
  useEffect(() => { loadShow(); loadClips(); }, [loadShow, loadClips]);

  useEffect(() => {
    let stop = false;
    const tick = async () => {
      if (stop) return;
      try {
        const q = lastTs.current ? `?after=${encodeURIComponent(lastTs.current)}` : '';
        const { data } = await api.get(`/social/liveshows/${showId}/messages${q}`);
        if (data.items?.length) {
          setMessages((m) => {
            const have = new Set(m.map((x: any) => x.id));
            const add = data.items.filter((x: any) => !have.has(x.id));
            return add.length ? [...m, ...add] : m;
          });
          lastTs.current = data.items[data.items.length - 1].created_at;
        }
        const { data: hb } = await api.post(`/social/liveshows/${showId}/heartbeat`);
        setShow((s: any) => s ? { ...s, viewer_count: hb.viewer_count } : s);
      } catch (_) {}
    };
    const iv = setInterval(tick, 3000); tick();
    return () => { stop = true; clearInterval(iv); };
  }, [showId]);

  const send = async () => {
    if (!text.trim()) return;
    const t = text.trim(); setText('');
    try { const { data } = await api.post(`/social/liveshows/${showId}/messages`, { text: t }); setMessages((m) => [...m, data]); lastTs.current = data.created_at; } catch (_) {}
  };
  const buy = async (p: any) => {
    setBuying(p.product_id);
    try {
      const base = (process.env.EXPO_PUBLIC_BACKEND_URL || '').replace(/\/$/, '');
      const { data } = await api.post(`/social/liveshows/${showId}/checkout`, { product_id: p.product_id, origin_url: base });
      if (data.checkout_url) Linking.openURL(data.checkout_url);
    } catch (_) {} finally { setBuying(null); }
  };
  const endShow = async () => { try { await api.post(`/social/liveshows/${showId}/end`); onClose(); } catch (_) {} };
  const startShow = async () => { try { await api.post(`/social/liveshows/${showId}/start`); loadShow(); } catch (_) {} };
  const toggleRemind = async () => {
    try { const { data } = await api.post(`/social/liveshows/${showId}/remind`, { on: !show.reminded }); setShow((s: any) => ({ ...s, reminded: data.reminded })); } catch (_) {}
  };
  const unpin = async (pid: string) => { try { await api.delete(`/social/liveshows/${showId}/products/${pid}`); loadShow(); } catch (_) {} };
  const saveHighlight = async () => { setSavingClip(true); try { await api.post(`/social/liveshows/${showId}/clips`, { note: '' }); await loadClips(); } catch (_) {} finally { setSavingClip(false); } };
  const buyClip = async (clip: any, p: any) => {
    setBuying(p.product_id);
    try {
      const base = (process.env.EXPO_PUBLIC_BACKEND_URL || '').replace(/\/$/, '');
      const { data } = await api.post(`/social/liveshows/clips/${clip.clip_id}/checkout`, { product_id: p.product_id, origin_url: base });
      if (data.checkout_url) Linking.openURL(data.checkout_url);
    } catch (_) {} finally { setBuying(null); }
  };
  const shareClip = async (clip: any) => {
    const base = (process.env.EXPO_PUBLIC_BACKEND_URL || '').replace(/\/$/, '');
    try { await Share.share({ message: `${clip.title} — on FUUSIC Live ${base}${clip.share_path}` }); } catch (_) {}
  };

  if (!show) return <View style={st.center}><ActivityIndicator color={t.magenta} /></View>;

  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 16 }} showsVerticalScrollIndicator={false} testID="live-viewer" keyboardShouldPersistTaps="handled">
      <Pressable onPress={onClose} testID="live-back" style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
        <Ionicons name="chevron-back" size={18} color={t.textMuted} /><Text style={{ color: t.textMuted, fontSize: TFONT.sm }}>Back to Live</Text>
      </Pressable>
      <LinearGradient colors={['#4c1d95', '#0d0a24']} style={st.stage}>
        {show.status === 'scheduled'
          ? <View style={st.upcomingBadgeStage} testID="live-upcoming-badge"><Text style={st.liveBadgeTxt}>◷ UPCOMING</Text></View>
          : <View style={st.liveBadge}><Text style={st.liveBadgeTxt}>● LIVE</Text></View>}
        <Avatar name={show.host?.name} url={show.host?.avatar_url} size={64} />
        <Text style={st.stageBiz}>{show.business_name}</Text>
        <Text style={st.stageTitle}>{show.title}</Text>
        {show.status === 'scheduled'
          ? <><CountdownText iso={show.scheduled_at} style={[st.stageMeta, { color: t.electric, fontSize: TFONT.md, fontWeight: '900' }]} />
              <Text style={[st.stageMeta, { fontSize: TFONT.xs }]} testID="live-scheduled-time">{whenText(show.scheduled_at)}</Text></>
          : <Text style={st.stageMeta}>{show.mode === 'live' ? 'Live video stream' : 'Simulated stream (preview)'} · {show.viewer_count} watching</Text>}
        {show.status === 'scheduled' && show.can_manage && (
          <Pressable onPress={startShow} testID="live-start-now" style={{ marginTop: 14 }}>
            <LinearGradient colors={['#a855f7', '#ec4899']} style={st.stageBtn}><Ionicons name="videocam" size={14} color="#fff" /><Text style={st.stageBtnTxt}>Go live now</Text></LinearGradient>
          </Pressable>
        )}
        {show.status === 'scheduled' && !show.can_manage && (
          <Pressable onPress={toggleRemind} testID="live-remind-btn" style={{ marginTop: 14 }}>
            <LinearGradient colors={show.reminded ? ['#0891b2', '#0e7490'] : ['#a855f7', '#ec4899']} style={st.stageBtn}><Ionicons name="notifications" size={14} color="#fff" /><Text style={st.stageBtnTxt}>{show.reminded ? 'Reminding you' : 'Remind me'}</Text></LinearGradient>
          </Pressable>
        )}
        {show.status === 'scheduled' && (
          <Pressable onPress={() => openCal(show)} testID="live-calendar-btn" style={st.calBtn}>
            <Ionicons name="calendar-outline" size={13} color="#cbd5e1" />
            <Text style={st.calTxt}>Add to calendar</Text>
          </Pressable>
        )}
        {show.can_manage && show.status !== 'scheduled' && (
          <View style={{ flexDirection: 'row', gap: 8, marginTop: 12, flexWrap: 'wrap', justifyContent: 'center' }}>
            <Pressable onPress={() => setPinOpen(true)} testID="live-pin-open"><LinearGradient colors={['#a855f7', '#ec4899']} style={st.stageBtn}><Ionicons name="add" size={14} color="#fff" /><Text style={st.stageBtnTxt}>Pin</Text></LinearGradient></Pressable>
            <Pressable onPress={saveHighlight} disabled={savingClip} testID="live-clip" style={st.ghostBtn}>{savingClip ? <ActivityIndicator size="small" color="#fff" /> : <Ionicons name="cut" size={14} color="#fff" />}<Text style={st.stageBtnTxt}>Highlight</Text></Pressable>
            {show.is_host && <Pressable onPress={() => setCohostOpen(true)} testID="live-cohost-open" style={st.ghostBtn}><Ionicons name="person-add" size={14} color="#fff" /><Text style={st.stageBtnTxt}>Co-host</Text></Pressable>}
            {show.is_host && <Pressable onPress={endShow} testID="live-end" style={st.endBtn}><Ionicons name="stop-circle" size={14} color="#fff" /><Text style={st.stageBtnTxt}>End</Text></Pressable>}
          </View>
        )}
      </LinearGradient>

      <View>
        <Text style={st.section}>SHOP THIS SHOW</Text>
        {(!show.pinned_products || show.pinned_products.length === 0)
          ? <Text style={st.dim}>{show.can_manage ? 'Pin a product to sell it live.' : 'No products pinned yet.'}</Text>
          : <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 12 }} testID="live-products">
              {show.pinned_products.map((p: any) => (
                <View key={p.product_id} style={st.product} testID={`live-product-${p.product_id}`}>
                  <View style={st.productImg}>{p.image_url ? <ExpoImage source={{ uri: p.image_url }} style={{ width: '100%', height: '100%' }} contentFit="cover" /> : <Ionicons name="pricetag" size={24} color="#c4b5fd" />}</View>
                  <Text style={st.productTitle} numberOfLines={1}>{p.title}</Text>
                  <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 3 }}>
                    <Text style={st.productPrice}>{money(p.price_cents)}</Text>
                    {p.offer ? <View style={st.offer}><Text style={st.offerTxt}>{p.offer}</Text></View> : null}
                  </View>
                  {show.can_manage
                    ? <Pressable onPress={() => unpin(p.product_id)} testID={`live-unpin-${p.product_id}`} style={st.unpinBtn}><Ionicons name="trash-outline" size={13} color={t.textMuted} /><Text style={st.unpinTxt}>Unpin</Text></Pressable>
                    : <Pressable onPress={() => buy(p)} disabled={buying === p.product_id} testID={`live-buy-${p.product_id}`}><LinearGradient colors={['#a855f7', '#ec4899']} style={st.buyBtn}>{buying === p.product_id ? <ActivityIndicator size="small" color="#fff" /> : <><Ionicons name="bag-handle" size={13} color="#fff" /><Text style={st.buyTxt}>Buy now</Text></>}</LinearGradient></Pressable>}
                </View>
              ))}
            </ScrollView>}
      </View>

      {clips.length > 0 && (
        <View testID="live-clips">
          <Text style={st.section}>HIGHLIGHT CLIPS</Text>
          {clips.map((c) => (
            <View key={c.clip_id} style={st.clipCard} testID={`live-clip-${c.clip_id}`}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
                <LinearGradient colors={['#a855f7', '#ec4899']} style={st.clipIcon}><Ionicons name="sparkles" size={15} color="#fff" /></LinearGradient>
                <View style={{ flex: 1 }}><Text style={st.productTitle} numberOfLines={1}>{c.title}</Text><Text style={st.dim} numberOfLines={1}>{c.caption}</Text></View>
                <Pressable onPress={() => shareClip(c)} testID={`clip-share-${c.clip_id}`} style={st.clipShare}><Ionicons name="share-social" size={16} color="#fff" /></Pressable>
              </View>
              {c.products?.length > 0 && (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, marginTop: 10 }}>
                  {c.products.map((p: any) => (
                    <View key={p.product_id} style={st.clipProduct}>
                      <Text style={st.productTitle} numberOfLines={1}>{p.title}</Text>
                      <Text style={st.productPrice}>{money(p.price_cents)}</Text>
                      <Pressable onPress={() => buyClip(c, p)} disabled={buying === p.product_id} testID={`clip-buy-${p.product_id}`}><LinearGradient colors={['#a855f7', '#ec4899']} style={st.clipBuy}>{buying === p.product_id ? <ActivityIndicator size="small" color="#fff" /> : <Text style={st.buyTxt}>Buy</Text>}</LinearGradient></Pressable>
                    </View>
                  ))}
                </ScrollView>
              )}
            </View>
          ))}
        </View>
      )}

      <View style={st.chatBox} testID="live-chat">
        <Text style={st.section}>LIVE CHAT</Text>
        {messages.length === 0 && <Text style={st.dim}>Say hi to the host 👋</Text>}
        {messages.map((m) => (
          <View key={m.id} style={{ flexDirection: 'row', gap: 8, marginBottom: 8 }}>
            <Avatar name={m.author?.name} url={m.author?.avatar_url} size={26} />
            <Text style={{ flex: 1, color: t.text, fontSize: TFONT.sm }}><Text style={{ fontWeight: '800', color: t.textMuted }}>{m.author?.name} </Text>{m.text}</Text>
          </View>
        ))}
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 6 }}>
          <TextInput value={text} onChangeText={setText} placeholder="Chat with the host…" placeholderTextColor={t.textMuted} style={st.chatInput} testID="live-chat-input" />
          <Pressable onPress={send} testID="live-chat-send"><LinearGradient colors={['#a855f7', '#ec4899']} style={st.chatSend}><Ionicons name="send" size={14} color="#fff" /></LinearGradient></Pressable>
        </View>
      </View>

      <PinProductSheet visible={pinOpen} onClose={() => setPinOpen(false)} onPin={async (body: any) => { try { await api.post(`/social/liveshows/${showId}/products`, body); setPinOpen(false); loadShow(); } catch (_) {} }} />
      <CohostSheet visible={cohostOpen} onClose={() => setCohostOpen(false)} showId={showId} cohosts={show.cohosts || []} onChange={loadShow} />
    </ScrollView>
  );
}

function CohostSheet({ visible, onClose, showId, cohosts, onChange }: any) {
  const t = activeTokens;
  const st = makeStyles(t);
  const [friends, setFriends] = useState<any[]>([]);
  useEffect(() => { if (visible) api.get('/social/friends').then(({ data }) => setFriends(data.friends || [])).catch(() => {}); }, [visible]);
  const coIds = new Set((cohosts || []).map((c: any) => c.user_id));
  const add = async (uid: string) => { try { await api.post(`/social/liveshows/${showId}/cohosts`, { user_id: uid }); onChange(); } catch (_) {} };
  const remove = async (uid: string) => { try { await api.delete(`/social/liveshows/${showId}/cohosts/${uid}`); onChange(); } catch (_) {} };
  return (
    <Sheet visible={visible} onClose={onClose} title="Invite a co-host" testID="cohost-sheet">
      {friends.length === 0 ? <Text style={st.dim}>Add friends first to invite a co-host.</Text> : friends.map((f) => (
        <View key={f.user_id} style={st.coRow}>
          <Avatar name={f.name} url={f.avatar_url} size={34} />
          <Text style={{ flex: 1, color: t.text, fontWeight: '800', fontSize: TFONT.sm }} numberOfLines={1}>{f.name}</Text>
          {coIds.has(f.user_id)
            ? <Pressable onPress={() => remove(f.user_id)} testID={`cohost-remove-${f.user_id}`} style={st.coRemove}><Text style={st.unpinTxt}>Remove</Text></Pressable>
            : <Pressable onPress={() => add(f.user_id)} testID={`cohost-add-${f.user_id}`}><LinearGradient colors={['#a855f7', '#ec4899']} style={st.coAdd}><Text style={st.buyTxt}>Add</Text></LinearGradient></Pressable>}
        </View>
      ))}
    </Sheet>
  );
}

function PinProductSheet({ visible, onClose, onPin }: any) {
  const t = activeTokens;
  const st = makeStyles(t);
  const [title, setTitle] = useState('');
  const [price, setPrice] = useState('');
  const [offer, setOffer] = useState('');
  const [image, setImage] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (title.trim().length < 1) return;
    setBusy(true);
    await onPin({ title, price_cents: Math.round(parseFloat(price || '0') * 100), offer, image_url: image || null });
    setBusy(false); setTitle(''); setPrice(''); setOffer(''); setImage('');
  };
  return (
    <Sheet visible={visible} onClose={onClose} title="Pin a product" testID="pin-product-sheet">
      <TextInput value={title} onChangeText={setTitle} placeholder="Product title" placeholderTextColor={t.textMuted} style={st.input} testID="pin-title" />
      <TextInput value={price} onChangeText={setPrice} placeholder="Price (USD, e.g. 24.99)" keyboardType="decimal-pad" placeholderTextColor={t.textMuted} style={st.input} testID="pin-price" />
      <TextInput value={offer} onChangeText={setOffer} placeholder="Live offer (optional)" placeholderTextColor={t.textMuted} style={st.input} testID="pin-offer" />
      <TextInput value={image} onChangeText={setImage} placeholder="Image URL (optional)" placeholderTextColor={t.textMuted} style={st.input} testID="pin-image" />
      <Pressable onPress={submit} disabled={busy} testID="pin-submit" style={{ marginTop: 10 }}>
        <LinearGradient colors={['#a855f7', '#ec4899']} style={st.btn}>{busy ? <ActivityIndicator color="#fff" /> : <><Ionicons name="add" size={16} color="#fff" /><Text style={st.btnTxt}>Pin to show</Text></>}</LinearGradient>
      </Pressable>
    </Sheet>
  );
}

function Sheet({ visible, onClose, title, testID, children }: any) {
  const t = activeTokens;
  const st = makeStyles(t);
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={st.sheetWrap}><View style={st.sheet} testID={testID}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          <Text style={st.sheetTitle}>{title}</Text>
          <Pressable onPress={onClose} testID="sheet-close"><Ionicons name="close" size={22} color={t.text} /></Pressable>
        </View>
        <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">{children}</ScrollView>
      </View></View>
    </Modal>
  );
}

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 },
  empty: { backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 20, alignItems: 'center' },
  emptyTxt: { color: t.textMuted, fontSize: TFONT.sm, textAlign: 'center' },
  golive: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16, borderRadius: TRADIUS.lg },
  goliveIcon: { width: 54, height: 54, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  goliveTitle: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900' },
  goliveSub: { color: 'rgba(255,255,255,0.75)', fontSize: TFONT.sm, marginTop: 2 },
  liveTag: { backgroundColor: 'rgba(239,68,68,0.3)', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 12 },
  liveTagTxt: { color: '#fecaca', fontSize: 10, fontWeight: '900' },
  showCard: { backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, overflow: 'hidden' },
  showCover: { height: 130, alignItems: 'center', justifyContent: 'center' },
  liveBadge: { position: 'absolute', top: 8, left: 8, backgroundColor: 'rgba(239,68,68,0.85)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  upcomingBadge: { position: 'absolute', top: 8, left: 8, flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(6,182,212,0.85)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  upcomingBadgeStage: { backgroundColor: 'rgba(6,182,212,0.85)', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12 },
  whenChip: { paddingHorizontal: 14, height: 34, borderRadius: 17, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, alignItems: 'center', justifyContent: 'center' },
  whenChipActive: { backgroundColor: t.magenta, borderColor: t.magenta },
  whenChipTxt: { color: t.textMuted, fontSize: TFONT.sm, fontWeight: '800' },
  liveBadgeTxt: { color: '#fff', fontSize: 9, fontWeight: '900' },
  viewerBadge: { position: 'absolute', top: 8, right: 8, flexDirection: 'row', alignItems: 'center', gap: 3, backgroundColor: 'rgba(0,0,0,0.5)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  viewerTxt: { color: '#fff', fontSize: 9, fontWeight: '900' },
  showTitle: { color: t.text, fontSize: TFONT.md, fontWeight: '900' },
  showMeta: { color: t.textMuted, fontSize: TFONT.xs, marginTop: 2 },
  remindBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, alignSelf: 'flex-start', marginTop: 8, paddingHorizontal: 12, height: 30, borderRadius: 15, backgroundColor: 'rgba(255,255,255,0.08)' },
  remindOn: { backgroundColor: 'rgba(34,211,238,0.2)' },
  remindTxt: { color: '#cbd5e1', fontSize: TFONT.xs, fontWeight: '800' },
  calBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10, paddingHorizontal: 14, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.08)' },
  calTxt: { color: '#cbd5e1', fontSize: TFONT.xs, fontWeight: '800' },
  featured: { borderRadius: 24, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(34,211,238,0.3)', minHeight: 172, justifyContent: 'flex-end' },
  featuredInner: { padding: 16 },
  featuredBadge: { flexDirection: 'row', alignItems: 'center', alignSelf: 'flex-start', backgroundColor: 'rgba(6,182,212,0.85)', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10, marginBottom: 8 },
  featuredTitle: { color: '#fff', fontSize: TFONT.xl, fontWeight: '900' },
  featuredMeta: { color: '#a5f3fc', fontSize: TFONT.sm },
  stage: { borderRadius: TRADIUS.lg, alignItems: 'center', padding: 24, borderWidth: 1, borderColor: 'rgba(244,114,182,0.25)' },
  stageBiz: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900', marginTop: 12 },
  stageTitle: { color: '#ddd6fe', fontSize: TFONT.sm, marginTop: 2 },
  stageMeta: { color: t.textMuted, fontSize: TFONT.xs, marginTop: 8 },
  stageBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 36, paddingHorizontal: 14, borderRadius: 18 },
  stageBtnTxt: { color: '#fff', fontSize: TFONT.xs, fontWeight: '900' },
  endBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 36, paddingHorizontal: 14, borderRadius: 18, backgroundColor: 'rgba(239,68,68,0.8)' },
  ghostBtn: { flexDirection: 'row', alignItems: 'center', gap: 5, height: 36, paddingHorizontal: 14, borderRadius: 18, backgroundColor: 'rgba(255,255,255,0.15)' },
  clipCard: { backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 12, marginBottom: 10 },
  clipIcon: { width: 36, height: 36, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  clipShare: { width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.12)', alignItems: 'center', justifyContent: 'center' },
  clipProduct: { width: 130, backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: t.line, borderRadius: 12, padding: 10, gap: 3 },
  clipBuy: { height: 30, borderRadius: 15, alignItems: 'center', justifyContent: 'center', marginTop: 4 },
  coRow: { flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: t.line, borderRadius: 14, paddingHorizontal: 10, paddingVertical: 8, marginBottom: 8 },
  coRemove: { paddingHorizontal: 12, height: 32, borderRadius: 16, backgroundColor: 'rgba(255,255,255,0.06)', alignItems: 'center', justifyContent: 'center' },
  coAdd: { paddingHorizontal: 14, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center' },
  section: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginBottom: 10 },
  dim: { color: t.textMuted, fontSize: TFONT.sm },
  product: { width: 176, backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, overflow: 'hidden', padding: 10 },
  productImg: { height: 96, borderRadius: 10, backgroundColor: 'rgba(168,85,247,0.1)', alignItems: 'center', justifyContent: 'center', overflow: 'hidden', marginBottom: 8 },
  productTitle: { color: t.text, fontSize: TFONT.sm, fontWeight: '800' },
  productPrice: { color: t.text, fontSize: TFONT.md, fontWeight: '900' },
  offer: { backgroundColor: 'rgba(236,72,153,0.2)', paddingHorizontal: 6, paddingVertical: 2, borderRadius: 8 },
  offerTxt: { color: '#f9a8d4', fontSize: 9, fontWeight: '900' },
  buyBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, height: 34, borderRadius: 17, marginTop: 8 },
  buyTxt: { color: '#fff', fontSize: TFONT.xs, fontWeight: '900' },
  unpinBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, height: 34, borderRadius: 17, marginTop: 8, backgroundColor: 'rgba(255,255,255,0.06)' },
  unpinTxt: { color: t.textMuted, fontSize: TFONT.xs, fontWeight: '800' },
  chatBox: { backgroundColor: t.elevated, borderWidth: 1, borderColor: t.line, borderRadius: TRADIUS.lg, padding: 14 },
  chatInput: { flex: 1, backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: t.line, borderRadius: 20, paddingHorizontal: 14, height: 40, color: t.text, fontSize: TFONT.sm },
  chatSend: { width: 40, height: 40, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  sheetWrap: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.7)' },
  sheet: { backgroundColor: '#0b0c16', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '88%', borderWidth: 1, borderColor: t.line },
  sheetTitle: { color: t.text, fontSize: TFONT.lg, fontWeight: '900' },
  input: { backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: t.line, borderRadius: 12, paddingHorizontal: 12, paddingVertical: 11, color: t.text, fontSize: TFONT.sm, marginTop: 8 },
  btn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, height: 46, borderRadius: 23 },
  btnTxt: { color: '#fff', fontSize: TFONT.md, fontWeight: '900' },
});
