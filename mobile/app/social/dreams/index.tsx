import React, { useCallback, useEffect, useState } from 'react';
import {
  View, Text, Pressable, StyleSheet, ScrollView, TextInput,
  ActivityIndicator, RefreshControl, Modal, Switch,
} from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { LinearGradient } from 'expo-linear-gradient';
import { TSPACE, TRADIUS, TFONT } from '../../../src/constants/tube';
import api from '../../../src/api/client';
import { AvatarM } from '../../(tabs)/social';
import MiniToast from '../../../src/components/MiniToast';

const D = {
  bg: '#0A0818', elevated: 'rgba(255,255,255,0.05)', line: 'rgba(168,85,247,0.18)',
  text: '#F5F3FF', dim: '#a5a0c0', muted: '#6d6a86', violet: '#a855f7',
  magenta: '#c026d3', accent2: '#7c3aed', gold: '#fbbf24', green: '#34d399',
};
const MOOD_TONE: any = {
  Happy: '#fbbf24', Scary: '#f87171', Confusing: '#a78bfa', Peaceful: '#34d399',
  Sad: '#60a5fa', Exciting: '#f472b6', Strange: '#c084fc', Other: '#94a3b8',
};
const TABS = [
  { key: 'dreams', label: 'Dreams', icon: 'moon' },
  { key: 'journal', label: 'Journal', icon: 'book' },
  { key: 'advisors', label: 'Advisors', icon: 'people' },
  { key: 'readings', label: 'Readings', icon: 'star' },
];

export default function DreamsHub() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { tab: tabParam } = useLocalSearchParams<{ tab?: string }>();
  const [tab, setTab] = useState(tabParam || 'dreams');
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [showShare, setShowShare] = useState(false);
  const [toast, setToast] = useState<string | null>(null);

  const loadConfig = useCallback(async () => {
    try { const { data } = await api.get('/social/dreams/config'); setConfig(data); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { loadConfig(); }, [loadConfig]);

  const acceptConsent = async () => {
    try { await api.post('/social/dreams/consent'); setConfig((c: any) => ({ ...c, consent_needed: false })); } catch (_) {}
  };

  return (
    <View style={s.screen} testID="dreams-hub">
      <View style={[s.header, { paddingTop: insets.top + 8 }]}>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Pressable onPress={() => router.back()} testID="dreams-back" hitSlop={10}>
            <Ionicons name="chevron-back" size={24} color={D.text} />
          </Pressable>
          <Ionicons name="moon" size={20} color={D.violet} />
          <Text style={s.title}>Dreams & Guidance</Text>
          <View style={{ flex: 1 }} />
          <AlertsBell />
        </View>
        <Text style={s.sub}>REFLECTION · GUIDANCE · EXPLORATION</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}
          contentContainerStyle={{ gap: 8, paddingVertical: 12 }} testID="dreams-tabs">
          {TABS.map((t) => {
            const active = tab === t.key;
            return (
              <Pressable key={t.key} testID={`dreams-tab-${t.key}`} onPress={() => setTab(t.key)}
                style={[s.chip, active && s.chipActive]}>
                <Ionicons name={t.icon as any} size={14} color={active ? '#fff' : D.dim} />
                <Text style={[s.chipTxt, active && { color: '#fff' }]}>{t.label}</Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false}
        contentContainerStyle={{ gap: 8, paddingHorizontal: TSPACE.md, paddingBottom: 10 }}
        style={{ flexGrow: 0 }} testID="dreams-shortcuts">
        {[
          { key: 'clubs', label: 'Clubs', icon: 'people-circle', route: '/social/dreams/clubs' },
          { key: 'clusters', label: 'Clusters', icon: 'layers', route: '/social/dreams/clusters' },
          { key: 'readings', label: 'AI Readings', icon: 'sparkles', route: '/social/dreams/readings' },
          { key: 'live', label: 'Live Q&A', icon: 'radio', route: '/social/dreams/live' },
          { key: 'studio', label: 'Advisor Studio', icon: 'briefcase', route: '/social/dreams/studio' },
        ].map((f) => (
          <Pressable key={f.key} testID={`dreams-shortcut-${f.key}`} onPress={() => router.push(f.route as any)} style={s.shortcut}>
            <Ionicons name={f.icon as any} size={15} color={D.violet} />
            <Text style={s.shortcutTxt}>{f.label}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {loading ? (
        <View style={s.center}><ActivityIndicator color={D.violet} /></View>
      ) : tab === 'dreams' ? (
        <DreamsTab config={config} onShare={() => setShowShare(true)} />
      ) : tab === 'journal' ? (
        <JournalTab onShare={() => setShowShare(true)} />
      ) : tab === 'advisors' ? (
        <AdvisorsTab config={config} />
      ) : (
        <ReadingsTab />
      )}

      {showShare && (
        <ShareModal config={config} onClose={() => setShowShare(false)}
          onDone={(pts?: number) => { setShowShare(false); setTab('journal'); setToast(pts ? 'Dream shared · +1 point' : 'Dream shared 🌙'); }} />
      )}
      {config?.consent_needed && (
        <ConsentGate config={config} onAccept={acceptConsent} onDecline={() => router.back()} />
      )}
      <MiniToast message={toast} onDone={() => setToast(null)} />
    </View>
  );
}

/* ── Alerts bell ── */
function AlertsBell() {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState<any>({ items: [], unread: 0 });
  const load = useCallback(async () => { try { const { data } = await api.get('/social/alerts'); setData(data); } catch (_) {} }, []);
  useEffect(() => { load(); const t = setInterval(load, 60000); return () => clearInterval(t); }, [load]);
  const openList = async () => { setOpen(true); try { await api.post('/social/alerts/read', {}); setData((d: any) => ({ ...d, unread: 0 })); } catch (_) {} };
  return (
    <>
      <Pressable testID="alerts-bell" onPress={openList} hitSlop={8} style={s.bell}>
        <Ionicons name="notifications" size={20} color={D.text} />
        {data.unread > 0 && <View style={s.bellDot} testID="alerts-badge"><Text style={s.bellDotTxt}>{data.unread}</Text></View>}
      </Pressable>
      {open && (
        <SheetM onClose={() => setOpen(false)} testID="alerts-sheet">
          <Text style={s.modalTitle}>Cluster alerts</Text>
          {(data.items || []).length === 0
            ? <Text style={{ color: D.dim, fontSize: TFONT.sm, paddingVertical: 12, textAlign: 'center' }}>No alerts yet. Follow a dream cluster to get pinged on new dreams.</Text>
            : (data.items || []).map((a: any) => (
              <View key={a.id} testID={`alert-${a.id}`} style={[s.alertRow, !a.read && s.alertUnread]}>
                <Text style={s.alertTitle}>{a.title}</Text>
                <Text style={s.alertMeta}>New in {a.theme_label}</Text>
              </View>
            ))}
        </SheetM>
      )}
    </>
  );
}

/* ── Dreams feed ── */
function DreamsTab({ config, onShare }: any) {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [mood, setMood] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try { const { data } = await api.get(`/social/dreams?scope=discover${mood ? `&mood=${encodeURIComponent(mood)}` : ''}`); setItems(data.items || []); }
    catch (_) {} finally { setLoading(false); setRefreshing(false); }
  }, [mood]);
  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 14 }}
      showsVerticalScrollIndicator={false} testID="dreams-feed"
      refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={D.violet} />}>
      <Pressable testID="dreams-share-cta" onPress={onShare}>
        <LinearGradient colors={['#1e1b4b', '#6d28d9']} start={{ x: 0, y: 0 }} end={{ x: 1, y: 1 }} style={s.hero}>
          <View style={s.heroIcon}><Ionicons name="add" size={24} color="#fff" /></View>
          <View style={{ flex: 1 }}>
            <Text style={s.heroTitle}>Share a dream</Text>
            <Text style={s.heroSub} numberOfLines={2}>With your name or anonymously — find people who dreamed like you.</Text>
          </View>
        </LinearGradient>
      </Pressable>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        <ChipM active={!mood} onPress={() => setMood(null)} label="All moods" />
        {(config?.moods || []).map((m: string) => (
          <ChipM key={m} active={mood === m} tone={MOOD_TONE[m]} onPress={() => setMood(mood === m ? null : m)} label={m} />
        ))}
      </ScrollView>

      {loading ? <ActivityIndicator color={D.violet} style={{ marginTop: 30 }} />
        : items.length === 0 ? <EmptyM>No dreams yet — be the first to share. 🌙</EmptyM>
        : items.map((d) => <DreamCardM key={d.dream_id} d={d} onPress={() => router.push(`/social/dreams/${d.dream_id}` as any)} />)}
    </ScrollView>
  );
}

function DreamCardM({ d, onPress }: any) {
  return (
    <Pressable testID={`dream-card-${d.dream_id}`} onPress={onPress} style={s.card}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {d.author?.anonymous
          ? <View style={s.anonAv}><Ionicons name="eye-off" size={14} color={D.violet} /></View>
          : <AvatarM name={d.author?.name} url={d.author?.avatar_url} size={26} />}
        <Text style={s.cardWho} numberOfLines={1}>{d.author?.name}</Text>
        {d.mood ? <View style={[s.moodPill, { backgroundColor: `${MOOD_TONE[d.mood]}22` }]}><Text style={[s.moodTxt, { color: MOOD_TONE[d.mood] }]}>{d.mood}</Text></View> : null}
      </View>
      {d.title ? <Text style={s.cardTitle}>{d.title}</Text> : null}
      <Text style={s.cardBody} numberOfLines={3}>{d.description}</Text>
      <View style={{ flexDirection: 'row', gap: 14, marginTop: 8 }}>
        <Meta icon="people" text={`${d.similar_count} similar`} />
        <Meta icon="chatbubble" text={`${d.comment_count}`} />
        {d.advisor_response_count > 0 ? <Meta icon="checkmark-circle" text={`${d.advisor_response_count}`} tone={D.violet} /> : null}
        {d.ai_reflection ? <Meta icon="sparkles" text="AI" tone={D.magenta} /> : null}
      </View>
    </Pressable>
  );
}

/* ── Journal ── */
function JournalTab({ onShare }: any) {
  const router = useRouter();
  const [mine, setMine] = useState<any[]>([]);
  const [saved, setSaved] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try {
      const [m, sv] = await Promise.all([api.get('/social/dreams?scope=mine'), api.get('/social/dreams/me/saved')]);
      setMine(m.data.items || []); setSaved(sv.data.items || []);
    } catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  if (loading) return <View style={s.center}><ActivityIndicator color={D.violet} /></View>;
  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 14 }} showsVerticalScrollIndicator={false} testID="dreams-journal">
      <Pressable testID="journal-share-cta" onPress={onShare} style={s.pillBtn}>
        <Ionicons name="add" size={16} color="#fff" /><Text style={s.pillBtnTxt}>New dream</Text>
      </Pressable>
      <Text style={s.sectionTitle}>🔒 YOUR DREAMS ({mine.length})</Text>
      {mine.length === 0 ? <EmptyM>Your journal is private by default.</EmptyM>
        : mine.map((d) => <DreamCardM key={d.dream_id} d={d} onPress={() => router.push(`/social/dreams/${d.dream_id}` as any)} />)}
      {saved.length > 0 && <>
        <Text style={s.sectionTitle}>SAVED</Text>
        {saved.map((d) => <DreamCardM key={d.dream_id} d={d} onPress={() => router.push(`/social/dreams/${d.dream_id}` as any)} />)}
      </>}
    </ScrollView>
  );
}

/* ── Advisors ── */
function AdvisorsTab({ config }: any) {
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [me, setMe] = useState<any>(null);
  const [cat, setCat] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showApply, setShowApply] = useState(false);

  const load = useCallback(async () => {
    try {
      const [a, m] = await Promise.all([api.get(`/social/dreams/advisors${cat ? `?category=${cat}` : ''}`), api.get('/social/dreams/advisors/me')]);
      setData(a.data); setMe(m.data.advisor);
    } catch (_) {} finally { setLoading(false); }
  }, [cat]);
  useEffect(() => { load(); }, [load]);

  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 12 }} showsVerticalScrollIndicator={false} testID="dreams-advisors">
      {me ? (
        <View style={s.mePanel} testID="my-advisor-panel">
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <AvatarM name={me.display_name} url={me.photo_url} size={38} />
            <View style={{ flex: 1 }}><Text style={s.cardTitle}>{me.display_name}</Text>
              <Text style={{ color: D.violet, fontSize: TFONT.xs }}>{me.category_label}</Text></View>
            <View style={[s.statusPill, { backgroundColor: me.status === 'approved' ? 'rgba(52,211,153,0.2)' : 'rgba(251,191,36,0.2)' }]}>
              <Text style={{ color: me.status === 'approved' ? D.green : D.gold, fontSize: 10, fontWeight: '900' }}>{me.status?.toUpperCase()}</Text></View>
          </View>
        </View>
      ) : (
        <Pressable testID="advisor-apply-cta" onPress={() => setShowApply(true)} style={s.card}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <View style={s.anonAv}><Ionicons name="color-wand" size={18} color={D.violet} /></View>
            <View style={{ flex: 1 }}><Text style={s.cardTitle}>Become an advisor</Text>
              <Text style={s.cardBody}>Offer reflections & private readings — verified & reviewed.</Text></View>
          </View>
        </Pressable>
      )}

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        <ChipM active={!cat} onPress={() => setCat(null)} label="All" />
        {(config?.advisor_categories || []).map((c: any) => (
          <ChipM key={c.key} active={cat === c.key} onPress={() => setCat(cat === c.key ? null : c.key)} label={c.label} />
        ))}
      </ScrollView>

      {loading ? <ActivityIndicator color={D.violet} style={{ marginTop: 20 }} />
        : (data?.items || []).length === 0 ? <EmptyM>No advisors in this category yet.</EmptyM>
        : data.items.map((a: any) => (
          <Pressable key={a.advisor_id} testID={`advisor-card-${a.advisor_id}`} onPress={() => router.push(`/social/dreams/advisor/${a.advisor_id}` as any)} style={s.card}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <AvatarM name={a.display_name} url={a.photo_url} size={44} />
              <View style={{ flex: 1 }}><Text style={s.cardTitle}>{a.display_name}</Text>
                <Text style={{ color: D.violet, fontSize: TFONT.xs }}>{a.category_label}</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 2 }}>
                  {a.featured && <View style={{ backgroundColor: 'rgba(251,191,36,0.2)', borderRadius: 8, paddingHorizontal: 6, paddingVertical: 1 }} testID={`advisor-featured-${a.advisor_id}`}><Text style={{ color: '#fcd34d', fontSize: 9, fontWeight: '900' }}>★ FEATURED</Text></View>}
                  <Ionicons name="star" size={11} color={D.gold} /><Text style={s.cardBody}>{a.rating} · {a.review_count}</Text></View>
              </View>
              <BadgesM badges={a.badges} />
            </View>
          </Pressable>
        ))}

      {showApply && <ApplyModal config={config} onClose={() => setShowApply(false)} onDone={() => { setShowApply(false); load(); }} />}
    </ScrollView>
  );
}

/* ── Readings ── */
function ReadingsTab() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const load = useCallback(async () => {
    try { const { data } = await api.get('/social/dreams/bookings'); setItems(data.items || []); }
    catch (_) {} finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);

  const check = async (id: string) => { try { await api.get(`/social/dreams/bookings/${id}/status`); load(); } catch (_) {} };

  if (loading) return <View style={s.center}><ActivityIndicator color={D.violet} /></View>;
  if (items.length === 0) return <View style={s.center} testID="readings-empty"><Text style={s.emptyTxt}>No readings yet — find an advisor and request one.</Text></View>;
  return (
    <ScrollView contentContainerStyle={{ padding: TSPACE.md, paddingBottom: 120, gap: 12 }} showsVerticalScrollIndicator={false} testID="dreams-readings">
      {items.map((b) => (
        <View key={b.booking_id} style={s.card} testID={`reading-${b.booking_id}`}>
          <View style={{ flexDirection: 'row', alignItems: 'center' }}>
            <View style={{ flex: 1 }}><Text style={s.cardTitle}>{b.service_title}</Text>
              <Text style={{ color: D.violet, fontSize: TFONT.xs }}>{b.advisor_name} · {b.advisor_category_label}</Text></View>
            <View style={s.statusPill}><Text style={{ color: D.dim, fontSize: 10, fontWeight: '900' }}>{b.status?.toUpperCase()}</Text></View>
          </View>
          {b.response?.text ? <View style={s.respBox}><Text style={s.respTxt}>{b.response.text}</Text></View> : null}
          {b.payment_status !== 'paid' ? (
            <Pressable onPress={() => check(b.booking_id)} testID={`reading-check-${b.booking_id}`} style={[s.smallBtn, { marginTop: 8 }]}>
              <Text style={s.smallBtnTxt}>Check payment</Text></Pressable>
          ) : null}
        </View>
      ))}
    </ScrollView>
  );
}

/* ── Modals ── */
function ShareModal({ config, onClose, onDone }: any) {
  const [f, setF] = useState<any>({ title: '', description: '', mood: '', tags: [], visibility: 'friends', anonymous: false });
  const [busy, setBusy] = useState(false);
  const toggleTag = (t: string) => setF((x: any) => ({ ...x, tags: x.tags.includes(t) ? x.tags.filter((y: string) => y !== t) : [...x.tags, t].slice(0, 8) }));
  const submit = async () => {
    if (f.description.trim().length < 1) return;
    setBusy(true);
    try { const { data } = await api.post('/social/dreams', { ...f, title: f.title.trim() || undefined, mood: f.mood || undefined }); onDone(data?.points_awarded); }
    catch (_) {} finally { setBusy(false); }
  };
  return (
    <SheetM onClose={onClose} testID="share-modal">
      <Text style={s.modalTitle}>Share a dream</Text>
      <TextInput value={f.title} onChangeText={(t) => setF({ ...f, title: t })} testID="share-title" placeholder="Title (optional)" placeholderTextColor={D.muted} style={s.input} />
      <TextInput value={f.description} onChangeText={(t) => setF({ ...f, description: t })} testID="share-description" placeholder="What happened in your dream?" placeholderTextColor={D.muted} style={[s.input, { height: 90 }]} multiline />
      <Text style={s.fieldLbl}>MOOD</Text>
      <View style={s.wrapRow}>{(config?.moods || []).map((m: string) => <ChipM key={m} active={f.mood === m} tone={MOOD_TONE[m]} onPress={() => setF({ ...f, mood: f.mood === m ? '' : m })} label={m} />)}</View>
      <Text style={s.fieldLbl}>TAGS</Text>
      <View style={s.wrapRow}>{(config?.tags || []).map((t: string) => <ChipM key={t} active={f.tags.includes(t)} onPress={() => toggleTag(t)} label={t} />)}</View>
      <Text style={s.fieldLbl}>VISIBILITY</Text>
      <View style={s.wrapRow}>{['only_me', 'friends', 'public'].map((v) => <ChipM key={v} active={f.visibility === v} onPress={() => setF({ ...f, visibility: v })} label={v === 'only_me' ? 'Only me' : v === 'friends' ? 'Friends' : 'Public'} />)}</View>
      <View style={s.switchRow} testID="share-anon">
        <Ionicons name="eye-off" size={16} color={D.dim} /><Text style={{ color: D.text, flex: 1, fontSize: TFONT.sm }}>Share anonymously</Text>
        <Switch value={f.anonymous} onValueChange={(v) => setF({ ...f, anonymous: v })} testID="share-anon-check" trackColor={{ true: D.violet }} />
      </View>
      <Pressable onPress={submit} disabled={busy} testID="share-submit" style={s.primaryBtn}>
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryBtnTxt}>Share dream</Text>}</Pressable>
    </SheetM>
  );
}

function ApplyModal({ config, onClose, onDone }: any) {
  const [f, setF] = useState<any>({ display_name: '', category: '', bio: '', languages: '', experience_years: '', credentials: '' });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!f.display_name || !f.category || f.bio.trim().length < 10) return;
    setBusy(true);
    try {
      await api.post('/social/dreams/advisors/apply', {
        display_name: f.display_name, category: f.category, bio: f.bio,
        languages: f.languages.split(',').map((x: string) => x.trim()).filter(Boolean),
        experience_years: f.experience_years ? Number(f.experience_years) : undefined,
        credentials: f.credentials || undefined,
      });
      onDone();
    } catch (_) {} finally { setBusy(false); }
  };
  return (
    <SheetM onClose={onClose} testID="apply-modal">
      <Text style={s.modalTitle}>Become an advisor</Text>
      <TextInput value={f.display_name} onChangeText={(t) => setF({ ...f, display_name: t })} testID="apply-name" placeholder="Display name" placeholderTextColor={D.muted} style={s.input} />
      <Text style={s.fieldLbl}>CATEGORY</Text>
      <View style={s.wrapRow}>{(config?.advisor_categories || []).map((c: any) => <ChipM key={c.key} active={f.category === c.key} onPress={() => setF({ ...f, category: c.key })} label={c.label} />)}</View>
      <TextInput value={f.bio} onChangeText={(t) => setF({ ...f, bio: t })} testID="apply-bio" placeholder="Short bio (min 10 chars)" placeholderTextColor={D.muted} style={[s.input, { height: 70 }]} multiline />
      <TextInput value={f.languages} onChangeText={(t) => setF({ ...f, languages: t })} testID="apply-languages" placeholder="Languages (comma separated)" placeholderTextColor={D.muted} style={s.input} />
      <TextInput value={f.experience_years} onChangeText={(t) => setF({ ...f, experience_years: t })} testID="apply-experience" placeholder="Years of experience" placeholderTextColor={D.muted} keyboardType="number-pad" style={s.input} />
      <TextInput value={f.credentials} onChangeText={(t) => setF({ ...f, credentials: t })} testID="apply-credentials" placeholder="Credentials / license (if licensed)" placeholderTextColor={D.muted} style={s.input} />
      <Pressable onPress={submit} disabled={busy} testID="apply-submit" style={s.primaryBtn}>
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={s.primaryBtnTxt}>Submit application</Text>}</Pressable>
    </SheetM>
  );
}

function ConsentGate({ config, onAccept, onDecline }: any) {
  const [ack, setAck] = useState(false);
  return (
    <Modal transparent animationType="fade" testID="consent-gate">
      <View style={s.consentBackdrop}>
        <View style={s.consentCard}>
          <View style={s.consentIcon}><Ionicons name="moon" size={26} color="#fff" /></View>
          <Text style={s.modalTitle}>Welcome to Dreams & Guidance</Text>
          <Text style={s.consentBody}>{config?.disclaimers?.global}</Text>
          <View style={s.switchRow}>
            <Switch value={ack} onValueChange={setAck} testID="consent-check" trackColor={{ true: D.violet }} />
            <Text style={{ color: D.dim, flex: 1, fontSize: TFONT.xs }}>I understand these AI and spiritual readings are for entertainment and reflection, not guaranteed or professional advice.</Text>
          </View>
          <View style={{ flexDirection: 'row', gap: 10, marginTop: 14 }}>
            <Pressable onPress={onDecline} testID="consent-decline" style={[s.smallBtn, { flex: 1 }]}><Text style={s.smallBtnTxt}>Not now</Text></Pressable>
            <Pressable onPress={onAccept} disabled={!ack} testID="consent-accept" style={[s.primaryBtn, { flex: 1, marginTop: 0, opacity: ack ? 1 : 0.4 }]}><Text style={s.primaryBtnTxt}>Enter</Text></Pressable>
          </View>
        </View>
      </View>
    </Modal>
  );
}

/* ── Shared bits ── */
function ChipM({ active, tone, onPress, label }: any) {
  return (
    <Pressable onPress={onPress} style={[s.filterChip, active && (tone ? { backgroundColor: `${tone}33`, borderColor: `${tone}66` } : s.filterChipActive)]}>
      <Text style={[s.filterChipTxt, active && { color: tone || '#fff' }]}>{label}</Text>
    </Pressable>
  );
}
function BadgesM({ badges }: any) {
  const b = badges || {};
  return (
    <View style={{ gap: 3, alignItems: 'flex-end' }}>
      {b.professional_license_verified ? <View style={[s.badge, { backgroundColor: 'rgba(52,211,153,0.2)' }]}><Ionicons name="medkit" size={10} color={D.green} /></View> : null}
      {b.spiritual_approved ? <View style={[s.badge, { backgroundColor: 'rgba(168,85,247,0.2)' }]}><Ionicons name="sparkles" size={10} color={D.violet} /></View> : null}
      {b.identity_verified ? <View style={[s.badge, { backgroundColor: 'rgba(34,211,238,0.2)' }]}><Ionicons name="checkmark-circle" size={10} color="#22d3ee" /></View> : null}
    </View>
  );
}
function Meta({ icon, text, tone }: any) {
  return <View style={{ flexDirection: 'row', alignItems: 'center', gap: 3 }}>
    <Ionicons name={icon} size={12} color={tone || D.muted} /><Text style={{ color: tone || D.muted, fontSize: TFONT.xs }}>{text}</Text></View>;
}
function EmptyM({ children }: any) { return <View style={s.empty}><Text style={s.emptyTxt}>{children}</Text></View>; }
function SheetM({ children, onClose, testID }: any) {
  return (
    <Modal transparent animationType="slide" testID={testID}>
      <Pressable style={s.sheetBackdrop} onPress={onClose} />
      <View style={s.sheet}>
        <Pressable onPress={onClose} testID="modal-close" style={s.sheetClose}><Ionicons name="close" size={18} color={D.text} /></Pressable>
        <ScrollView showsVerticalScrollIndicator={false} keyboardShouldPersistTaps="handled">{children}</ScrollView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  screen: { flex: 1, backgroundColor: D.bg },
  header: { paddingHorizontal: TSPACE.md, paddingBottom: 2, borderBottomWidth: 1, borderBottomColor: D.line, backgroundColor: D.bg },
  title: { color: D.text, fontSize: TFONT.xl, fontWeight: '900' },
  sub: { color: D.muted, fontSize: 9, fontWeight: '800', letterSpacing: 1.5, marginTop: 4, marginLeft: 32 },
  chip: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, height: 36, borderRadius: 18, backgroundColor: D.elevated },
  chipActive: { backgroundColor: D.accent2 },
  chipTxt: { color: D.dim, fontSize: TFONT.sm, fontWeight: '800' },
  shortcut: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, height: 38, borderRadius: 19, backgroundColor: 'rgba(168,85,247,0.12)', borderWidth: 1, borderColor: D.line },
  shortcutTxt: { color: D.text, fontSize: TFONT.sm, fontWeight: '800' },
  bell: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  bellDot: { position: 'absolute', top: 2, right: 2, minWidth: 18, height: 18, paddingHorizontal: 4, borderRadius: 9, backgroundColor: '#f43f5e', alignItems: 'center', justifyContent: 'center' },
  bellDotTxt: { color: '#fff', fontSize: 10, fontWeight: '900' },
  alertRow: { borderRadius: 14, paddingHorizontal: 14, paddingVertical: 11, borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)', backgroundColor: 'rgba(255,255,255,0.02)', marginBottom: 8 },
  alertUnread: { backgroundColor: 'rgba(168,85,247,0.1)', borderColor: 'rgba(168,85,247,0.25)' },
  alertTitle: { color: D.text, fontSize: TFONT.sm, fontWeight: '800' },
  alertMeta: { color: D.violet, fontSize: 11, marginTop: 2 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 40 },
  hero: { flexDirection: 'row', alignItems: 'center', gap: 14, padding: 16, borderRadius: TRADIUS.lg },
  heroIcon: { width: 48, height: 48, borderRadius: 14, backgroundColor: 'rgba(255,255,255,0.15)', alignItems: 'center', justifyContent: 'center' },
  heroTitle: { color: '#fff', fontSize: TFONT.lg, fontWeight: '900' },
  heroSub: { color: 'rgba(233,213,255,0.8)', fontSize: TFONT.xs, marginTop: 2 },
  card: { backgroundColor: D.elevated, borderWidth: 1, borderColor: D.line, borderRadius: TRADIUS.lg, padding: 14 },
  anonAv: { width: 26, height: 26, borderRadius: 13, backgroundColor: 'rgba(168,85,247,0.2)', alignItems: 'center', justifyContent: 'center' },
  cardWho: { color: D.dim, fontSize: TFONT.xs, fontWeight: '700', flex: 1 },
  cardTitle: { color: D.text, fontSize: TFONT.md, fontWeight: '900' },
  cardBody: { color: D.dim, fontSize: TFONT.sm, marginTop: 2 },
  moodPill: { paddingHorizontal: 8, paddingVertical: 2, borderRadius: 8 },
  moodTxt: { fontSize: 9, fontWeight: '900', letterSpacing: 0.5 },
  sectionTitle: { color: D.muted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1.2, marginTop: 4 },
  pillBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', height: 44, paddingHorizontal: 20, borderRadius: 22, backgroundColor: D.accent2 },
  pillBtnTxt: { color: '#fff', fontSize: TFONT.sm, fontWeight: '900' },
  mePanel: { backgroundColor: 'rgba(168,85,247,0.08)', borderWidth: 1, borderColor: 'rgba(168,85,247,0.3)', borderRadius: TRADIUS.lg, padding: 14 },
  statusPill: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 10, backgroundColor: 'rgba(255,255,255,0.1)' },
  badge: { width: 20, height: 20, borderRadius: 10, alignItems: 'center', justifyContent: 'center' },
  respBox: { marginTop: 10, backgroundColor: 'rgba(168,85,247,0.1)', borderWidth: 1, borderColor: 'rgba(168,85,247,0.25)', borderRadius: TRADIUS.md, padding: 12 },
  respTxt: { color: D.text, fontSize: TFONT.sm, lineHeight: 20 },
  empty: { backgroundColor: D.elevated, borderWidth: 1, borderColor: D.line, borderRadius: TRADIUS.lg, padding: 20, alignItems: 'center' },
  emptyTxt: { color: D.muted, fontSize: TFONT.sm, textAlign: 'center' },
  filterChip: { paddingHorizontal: 14, height: 34, borderRadius: 17, borderWidth: 1, borderColor: D.line, backgroundColor: D.elevated, alignItems: 'center', justifyContent: 'center' },
  filterChipActive: { backgroundColor: D.accent2, borderColor: 'transparent' },
  filterChipTxt: { color: D.dim, fontSize: TFONT.xs, fontWeight: '800' },
  smallBtn: { height: 40, paddingHorizontal: 16, borderRadius: 20, backgroundColor: 'rgba(255,255,255,0.1)', alignItems: 'center', justifyContent: 'center' },
  smallBtnTxt: { color: D.text, fontSize: TFONT.xs, fontWeight: '800' },
  primaryBtn: { height: 50, borderRadius: 25, backgroundColor: D.magenta, alignItems: 'center', justifyContent: 'center', marginTop: 14 },
  primaryBtnTxt: { color: '#fff', fontSize: TFONT.md, fontWeight: '900' },
  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)' },
  sheet: { backgroundColor: '#12102b', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 18, maxHeight: '86%' },
  sheetClose: { alignSelf: 'flex-end', width: 34, height: 34, borderRadius: 17, backgroundColor: 'rgba(255,255,255,0.1)', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  modalTitle: { color: D.text, fontSize: TFONT.xl, fontWeight: '900', marginBottom: 12 },
  input: { backgroundColor: 'rgba(255,255,255,0.05)', borderWidth: 1, borderColor: D.line, borderRadius: TRADIUS.md, paddingHorizontal: 14, paddingVertical: 12, color: D.text, fontSize: TFONT.sm, marginBottom: 10 },
  fieldLbl: { color: D.muted, fontSize: TFONT.xs, fontWeight: '900', letterSpacing: 1, marginBottom: 8, marginTop: 2 },
  wrapRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 10 },
  switchRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginVertical: 6 },
  consentBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.75)', alignItems: 'center', justifyContent: 'center', padding: 24 },
  consentCard: { width: '100%', backgroundColor: '#12102b', borderWidth: 1, borderColor: 'rgba(168,85,247,0.3)', borderRadius: 24, padding: 24 },
  consentIcon: { width: 54, height: 54, borderRadius: 16, backgroundColor: D.accent2, alignItems: 'center', justifyContent: 'center', marginBottom: 14 },
  consentBody: { color: D.dim, fontSize: TFONT.sm, lineHeight: 20, marginTop: 6 },
});
