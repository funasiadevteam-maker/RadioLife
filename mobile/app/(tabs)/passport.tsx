import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, TextInput, Alert, Switch, Modal, Share, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
import { useAuth } from '../../src/contexts/AuthContext';
import api, { BACKEND } from '../../src/api/client';

const TIER_COLORS: Record<string, string> = {
  bronze: '#b67334', silver: '#cfd6df', gold: '#ffd75e', platinum: '#d6f0ff', diamond: '#c4f5ff', unique: '#ff6ec4',
};

export default function PassportScreen() {
  const { user, loading: authLoading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<any>(null);
  const [catalog, setCatalog] = useState<any[]>([]);
  const [celebrations, setCelebrations] = useState<any[]>([]);
  const [tab, setTab] = useState('badges');
  const [loading, setLoading] = useState(true);

  useEffect(() => { if (authLoading) return; if (!user) router.replace('/login'); }, [user, authLoading]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [me, cat, cel] = await Promise.all([
        api.get('/passport/me'),
        api.get('/passport/badges/catalog'),
        api.get('/passport/me/celebrations').catch(() => ({ data: { items: [] } })),
      ]);
      setData(me.data);
      setCatalog(cat.data.items || []);
      setCelebrations(cel.data.items || []);
    } catch { Alert.alert('Error', 'Could not load passport'); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { if (!authLoading && user) load(); }, [load, authLoading, user]);

  const dismissCelebration = async () => {
    const levels = celebrations.map((c: any) => c.to_level);
    setCelebrations([]);
    try { await api.post('/passport/me/celebrations/ack', { levels }); } catch {}
  };

  if (loading || !data) {
    return <View style={st.loadingWrap} testID="psp-loading"><ActivityIndicator size="large" color={COLORS.primary} /><Text style={st.loadingText}>Loading passport…</Text></View>;
  }

  const a = data.ambassador || {};
  const ls = data.listening_stats || {};

  return (
    <SafeAreaView style={st.container} testID="psp-page">
      {/* Level-up celebration modal */}
      {celebrations.length > 0 && (
        <Modal transparent animationType="fade" testID="psp-celebration-modal">
          <View style={st.celebOverlay}>
            <View style={st.celebCard}>
              <Ionicons name="sparkles" size={40} color={COLORS.gold} />
              <Text style={st.celebEye}>You leveled up to</Text>
              <Text style={st.celebLevel}>
                L{celebrations[celebrations.length - 1].to_level} · {celebrations[celebrations.length - 1].rewards?.chip?.replace(/_chip$/, '').replace(/_/g, ' ')}
              </Text>
              <View style={st.celebRewards}>
                {celebrations.flatMap((c: any) => Object.entries(c.rewards || {}).filter(([k]) => !k.includes('chip')).map(([k, v]) => (
                  <View key={`${c.to_level}-${k}`} style={st.celebRewardRow} testID={`psp-celeb-reward-${k}`}>
                    <Ionicons name={k === 'bigcoin' ? 'star' : k === 'premium_days' ? 'diamond' : 'musical-notes'} size={14} color={COLORS.gold} />
                    <Text style={st.celebRewardText}>
                      {k === 'bigcoin' ? `+${v} BigCoin` : k === 'premium_days' ? `${v} days Premium` : k === 'exclusive_channel' ? `Exclusive channel (${c.rewards.exclusive_channel_days}d)` : k === 'vip_lobby_host_chip' ? 'VIP host chip' : String(k)}
                    </Text>
                  </View>
                )))}
              </View>
              <TouchableOpacity style={st.celebBtn} onPress={dismissCelebration} testID="psp-celeb-continue">
                <Text style={st.celebBtnText}>Continue</Text>
              </TouchableOpacity>
            </View>
          </View>
        </Modal>
      )}

      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        {/* Hero Card */}
        <View style={st.heroCard} testID="psp-hero">
          <View style={[st.avatar, { backgroundColor: TIER_COLORS[a.level_name?.toLowerCase()] || COLORS.primary }]}>
            <Text style={st.avatarText}>{(data.settings?.display_name || '?').trim().charAt(0).toUpperCase()}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <Text style={st.heroName}>{data.settings?.display_name}</Text>
              {data.settings?.city_pin && (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 2 }}>
                  <Ionicons name="location" size={11} color={COLORS.secondary} />
                  <Text style={{ fontSize: 10, color: COLORS.secondary }}>{data.settings.city_pin}</Text>
                </View>
              )}
            </View>
            {data.settings?.bio && <Text style={st.heroBio}>{data.settings.bio}</Text>}
            <View style={st.statsRow}>
              <View style={st.statItem}><Text style={st.statNum}>{a.level || 1}</Text><Text style={st.statLabel}>{a.level_name || 'Listener'}</Text></View>
              <View style={st.statItem}><Text style={st.statNum}>{data.badges_total}</Text><Text style={st.statLabel}>badges</Text></View>
              <View style={st.statItem}><Text style={st.statNum}>{data.badges_total_points}</Text><Text style={st.statLabel}>points</Text></View>
              <View style={st.statItem}><Text style={st.statNum}>{ls.hours_total ?? 0}h</Text><Text style={st.statLabel}>listened</Text></View>
            </View>
            {a.next_level_threshold != null && (
              <View style={{ marginTop: SPACING.sm }}>
                <View style={st.progressBar}><View style={[st.progressFill, { width: `${a.progress_to_next_pct ?? 0}%` }]} /></View>
                <Text style={st.progressLabel}>{a.points} / {a.next_level_threshold} pts → {a.next_level_name}</Text>
              </View>
            )}
          </View>
        </View>

        {/* Leaderboard CTA */}
        <TouchableOpacity style={st.leaderboardCta} onPress={() => router.push('/leaderboard')} testID="psp-leaderboard-btn">
          <Ionicons name="trophy" size={16} color={COLORS.gold} />
          <View style={{ flex: 1, marginLeft: 10 }}>
            <Text style={st.leaderCta}>City Leaderboard</Text>
            <Text style={st.leaderSub}>See top ambassadors in your city</Text>
          </View>
          <Ionicons name="chevron-forward" size={16} color={COLORS.textDim} />
        </TouchableOpacity>

        {/* Tabs */}
        <View style={st.tabs} testID="psp-tabs">
          {['badges', 'stats', 'referrals', 'settings'].map(t => (
            <TouchableOpacity key={t} style={[st.tab, tab === t && st.tabActive]} onPress={() => setTab(t)} testID={`psp-tab-${t}`}>
              <Text style={[st.tabText, tab === t && st.tabTextActive]}>{t}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {tab === 'badges' && <BadgesSection data={data} catalog={catalog} />}
        {tab === 'stats' && <StatsSection data={data} />}
        {tab === 'referrals' && <ReferralsSection data={data} />}
        {tab === 'settings' && <SettingsSection data={data} onUpdate={load} />}
      </ScrollView>
    </SafeAreaView>
  );
}

/* ─── Badges ──────────────────────────────────────────── */
function BadgesSection({ data, catalog }: any) {
  const [selectedBadge, setSelectedBadge] = useState<any>(null);
  const earnedByCat = data.badges_by_category || {};
  const earnedIds = useMemo(() => {
    const s = new Set<string>();
    Object.values(earnedByCat).forEach((arr: any) => arr.forEach((b: any) => s.add(b.badge_id)));
    return s;
  }, [earnedByCat]);
  const inProg = data.badges_in_progress || [];
  const inProgIds = useMemo(() => new Set(inProg.map((b: any) => b.badge_id)), [inProg]);
  const locked = (catalog || []).filter((b: any) => !earnedIds.has(b.badge_id) && !inProgIds.has(b.badge_id));

  if (data.badges_total === 0 && inProg.length === 0) {
    return (
      <View style={st.emptyBox} testID="psp-badges-empty">
        <Ionicons name="trophy" size={28} color={COLORS.textDim} />
        <Text style={st.emptyTitle}>No badges yet.</Text>
        <Text style={st.emptySub}>Listen, host a lobby, win a game, or claim an offer to start earning.</Text>
      </View>
    );
  }

  const shareBadge = async (b: any) => {
    try { await Share.share({ message: `I earned the "${b.name}" badge on BigFM! 🏆` }); } catch {}
  };

  return (
    <View testID="psp-badges-tab">
      {/* Badge detail modal */}
      <Modal visible={!!selectedBadge} transparent animationType="fade" onRequestClose={() => setSelectedBadge(null)}>
        <TouchableOpacity style={st.modalOverlay} activeOpacity={1} onPress={() => setSelectedBadge(null)}>
          <View style={st.modalCard}>
            <View style={[st.modalBadgeIcon, { backgroundColor: TIER_COLORS[selectedBadge?.tier] || COLORS.primary }]}>
              <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>{(selectedBadge?.name || '?')[0]}</Text>
            </View>
            <Text style={st.modalBadgeName}>{selectedBadge?.name}</Text>
            <Text style={st.modalBadgeTier}>{selectedBadge?.tier} · {selectedBadge?.points} pts</Text>
            <Text style={st.modalBadgeDesc}>{selectedBadge?.description}</Text>
            {selectedBadge?.earned_at && <Text style={st.modalBadgeDate}>Earned {new Date(selectedBadge.earned_at).toLocaleDateString()}</Text>}
            <TouchableOpacity style={st.shareBtn} onPress={() => shareBadge(selectedBadge)} testID="psp-badge-share">
              <Ionicons name="share-outline" size={14} color="#fff" />
              <Text style={{ color: '#fff', fontWeight: '700', fontSize: 12 }}>Share</Text>
            </TouchableOpacity>
          </View>
        </TouchableOpacity>
      </Modal>

      {Object.entries(earnedByCat).map(([cat, items]: [string, any]) => (
        <View key={cat} style={st.section} testID={`psp-earned-${cat}`}>
          <Text style={st.sectionHead}><Ionicons name="trophy" size={12} color={COLORS.gold} /> Earned · {cat} ({items.length})</Text>
          <View style={st.badgeGrid}>
            {items.map((b: any) => (
              <TouchableOpacity key={b.badge_id} style={st.badgeCard} onPress={() => setSelectedBadge(b)} testID={`psp-badge-${b.badge_id}`}>
                <View style={[st.badgeTierDot, { backgroundColor: TIER_COLORS[b.tier] || COLORS.textDim }]} />
                <Text style={st.badgeCardName}>{b.name}</Text>
                <Text style={st.badgeCardPts}><Ionicons name="star" size={9} color={COLORS.gold} /> {b.points} pts · {b.tier}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>
      ))}
      {inProg.length > 0 && (
        <View style={st.section} testID="psp-in-progress">
          <Text style={st.sectionHead}><Ionicons name="sparkles" size={12} color={COLORS.secondary} /> In progress ({inProg.length})</Text>
          {inProg.map((b: any) => (
            <View key={b.badge_id} style={st.progressCard}>
              <Text style={st.badgeCardName}>{b.name}</Text>
              <View style={st.progressBar}><View style={[st.progressFill, { width: `${b.pct || 0}%` }]} /></View>
              <Text style={st.progressLabel}>{b.current_value}/{b.target_value} · {b.pct}%</Text>
            </View>
          ))}
        </View>
      )}
      {locked.length > 0 && (
        <View style={st.section} testID="psp-locked">
          <Text style={st.sectionHead}><Ionicons name="lock-closed" size={12} color={COLORS.textDim} /> Locked ({locked.length})</Text>
          <View style={st.badgeGrid}>
            {locked.slice(0, 24).map((b: any) => (
              <View key={b.badge_id} style={[st.badgeCard, { opacity: 0.35 }]}>
                <Text style={st.badgeCardName}>{b.name}</Text>
                <Text style={st.badgeCardPts}>{b.criteria_summary}</Text>
              </View>
            ))}
          </View>
        </View>
      )}
    </View>
  );
}

/* ─── Stats ──────────────────────────────────────────── */
function StatsSection({ data }: any) {
  const ls = data.listening_stats || {};
  const feed = data.recent_feed || [];
  return (
    <View testID="psp-stats-tab">
      <View style={st.statGrid}>
        {[
          { icon: 'time', label: 'minutes today', value: ls.minutes_today ?? 0 },
          { icon: 'hourglass', label: 'lifetime', value: `${ls.hours_total ?? 0}h` },
          { icon: 'ribbon', label: 'badges', value: data.badges_total },
          { icon: 'trophy', label: 'level', value: (data.ambassador || {}).level || 1 },
        ].map((s, i) => (
          <View key={i} style={st.statCard}>
            <Ionicons name={s.icon as any} size={16} color={COLORS.secondary} />
            <Text style={st.statCardNum}>{s.value}</Text>
            <Text style={st.statCardLabel}>{s.label}</Text>
          </View>
        ))}
      </View>
      <View style={st.section}>
        <Text style={st.sectionHead}>Recent badge feed</Text>
        {feed.length === 0 && <Text style={st.emptySub}>No badges earned yet.</Text>}
        {feed.map((f: any, i: number) => (
          <View key={i} style={st.feedRow}>
            <View style={[st.badgeTierDot, { backgroundColor: TIER_COLORS[f.tier] || COLORS.textDim }]} />
            <Text style={{ color: COLORS.text, fontSize: 13, flex: 1 }}>{f.name}</Text>
            <Text style={{ color: COLORS.textDim, fontSize: 11 }}>{new Date(f.earned_at).toLocaleDateString()}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}

/* ─── Referrals ──────────────────────────────────────── */
function ReferralsSection({ data }: any) {
  const stats = data.referral_stats || { funnel: {}, recent: [] };
  const refCode = data.referral_code || '—';
  const shareUrl = `${BACKEND}/?ref=${refCode}`;

  const copyRef = async () => {
    try {
      const { default: Clipboard } = await import('expo-clipboard');
      await Clipboard.setStringAsync(shareUrl);
      Alert.alert('Copied!', 'Referral link copied to clipboard');
    } catch { Alert.alert('Error', 'Could not copy'); }
  };

  const shareRef = async () => {
    try { await Share.share({ message: `Join me on BigFM! ${shareUrl}`, url: shareUrl }); }
    catch { copyRef(); }
  };

  return (
    <View testID="psp-referrals-tab">
      <View style={st.section}>
        <Text style={st.sectionHead}><Ionicons name="share-social" size={12} color={COLORS.primary} /> Your referral link</Text>
        <View style={st.refCodeBox} testID="psp-ref-link"><Text style={st.refCode}>{refCode}</Text></View>
        <View style={{ flexDirection: 'row', gap: 8, marginTop: SPACING.sm }}>
          <TouchableOpacity style={[st.refBtn, { flex: 1 }]} onPress={copyRef} testID="psp-copy-ref">
            <Ionicons name="copy" size={12} color="#fff" /><Text style={st.refBtnText}>Copy</Text>
          </TouchableOpacity>
          <TouchableOpacity style={[st.refBtn, { flex: 1, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder }]} onPress={shareRef} testID="psp-share-ref">
            <Ionicons name="share-outline" size={12} color={COLORS.textDim} /><Text style={[st.refBtnText, { color: COLORS.textDim }]}>Share</Text>
          </TouchableOpacity>
        </View>
      </View>
      <View style={st.section}>
        <Text style={st.sectionHead}><Ionicons name="trophy" size={12} color={COLORS.gold} /> Attribution funnel</Text>
        <View style={st.funnelRow} testID="psp-funnel">
          <View style={st.funnelStep}><Text style={st.funnelNum}>{stats.funnel?.clicked || 0}</Text><Text style={st.funnelLabel}>clicked</Text></View>
          <Ionicons name="chevron-forward" size={14} color={COLORS.textDim} />
          <View style={st.funnelStep}><Text style={st.funnelNum}>{stats.funnel?.signed_up || 0}</Text><Text style={st.funnelLabel}>signed up</Text></View>
          <Ionicons name="chevron-forward" size={14} color={COLORS.textDim} />
          <View style={[st.funnelStep, { backgroundColor: 'rgba(59,130,246,0.1)' }]}><Text style={[st.funnelNum, { color: COLORS.secondary }]}>{stats.funnel?.engaged || 0}</Text><Text style={st.funnelLabel}>engaged</Text></View>
        </View>
        <Text style={[st.emptySub, { marginTop: 8 }]}>{stats.conversion_to_engaged_pct ?? 0}% engaged conversion</Text>
      </View>
      {(stats.recent || []).length > 0 && (
        <View style={st.section}>
          <Text style={st.sectionHead}>Recent activity</Text>
          {stats.recent.map((r: any, i: number) => (
            <View key={i} style={st.feedRow}>
              <View style={[st.statusChip, r.status === 'engaged' && { backgroundColor: 'rgba(59,130,246,0.15)' }]}>
                <Text style={[st.statusText, r.status === 'engaged' && { color: COLORS.secondary }]}>{r.status}</Text>
              </View>
              <Text style={{ color: COLORS.textDim, fontSize: 11, flex: 1 }}>{r.landing_path}</Text>
              <Text style={{ color: COLORS.textDim, fontSize: 10 }}>{new Date(r.landing_at).toLocaleDateString()}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}

/* ─── Settings ──────────────────────────────────────── */
function SettingsSection({ data, onUpdate }: any) {
  const [draft, setDraft] = useState(data.settings || {});
  const [saving, setSaving] = useState(false);
  useEffect(() => setDraft(data.settings || {}), [data.settings]);

  const save = async () => {
    setSaving(true);
    try { await api.patch('/passport/me/settings', draft); Alert.alert('Saved', 'Settings updated'); onUpdate(); }
    catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };

  return (
    <View testID="psp-settings-tab">
      <View style={st.section}>
        <Text style={st.sectionHead}>Profile</Text>
        <Text style={st.fieldLabel}>Display name</Text>
        <TextInput style={st.fieldInput} value={draft.display_name || ''} onChangeText={v => setDraft({ ...draft, display_name: v })} placeholderTextColor={COLORS.textDim} testID="psp-display-name" />
        <Text style={st.fieldLabel}>Bio</Text>
        <TextInput style={[st.fieldInput, { height: 80 }]} value={draft.bio || ''} onChangeText={v => setDraft({ ...draft, bio: v })} multiline placeholderTextColor={COLORS.textDim} testID="psp-bio" />
        <Text style={st.fieldLabel}>City pin</Text>
        <TextInput style={st.fieldInput} value={draft.city_pin || ''} onChangeText={v => setDraft({ ...draft, city_pin: v })} placeholder="Dubai, Frisco TX…" placeholderTextColor={COLORS.textDim} testID="psp-city-pin" />
      </View>
      <View style={st.section}>
        <Text style={st.sectionHead}>Privacy</Text>
        {[
          { key: 'is_public', label: 'Public profile' },
          { key: 'show_badges_publicly', label: 'Show badges publicly' },
          { key: 'show_listening_stats_publicly', label: 'Show listening stats' },
          { key: 'show_leaderboard_position_publicly', label: 'Show leaderboard position' },
          { key: 'show_ambassador_level_publicly', label: 'Show ambassador level' },
        ].map(item => (
          <View key={item.key} style={st.privRow}>
            <Text style={st.privLabel}>{item.label}</Text>
            <Switch value={!!draft[item.key]} onValueChange={v => setDraft({ ...draft, [item.key]: v })} trackColor={{ false: '#333', true: COLORS.primary }} thumbColor="#fff" testID={`psp-toggle-${item.key}`} />
          </View>
        ))}
      </View>
      <TouchableOpacity style={st.saveBtn} onPress={save} disabled={saving} testID="psp-save-settings">
        {saving ? <ActivityIndicator size="small" color="#fff" /> : <Text style={st.saveBtnText}>Save settings</Text>}
      </TouchableOpacity>
    </View>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  loadingWrap: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  loadingText: { color: COLORS.textDim, marginTop: 12, fontSize: FONT.sm },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  heroCard: { flexDirection: 'row', gap: SPACING.md, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.sm },
  avatar: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  avatarText: { fontSize: 24, fontWeight: '800', color: '#fff' },
  heroName: { fontSize: 18, fontWeight: '800', color: COLORS.text },
  heroBio: { fontSize: 12, color: COLORS.textDim, marginTop: 4, lineHeight: 18 },
  statsRow: { flexDirection: 'row', gap: SPACING.md, marginTop: SPACING.sm },
  statItem: { alignItems: 'center' },
  statNum: { fontSize: 16, fontWeight: '800', color: COLORS.text },
  statLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '600' },
  progressBar: { height: 4, backgroundColor: 'rgba(255,255,255,0.08)', borderRadius: 2 },
  progressFill: { height: 4, backgroundColor: COLORS.secondary, borderRadius: 2 },
  progressLabel: { fontSize: 10, color: COLORS.textDim, marginTop: 4 },
  leaderboardCta: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(255,215,0,0.06)', borderWidth: 1, borderColor: 'rgba(255,215,0,0.2)', borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.md },
  leaderCta: { color: COLORS.text, fontSize: FONT.sm, fontWeight: '700' },
  leaderSub: { color: COLORS.textDim, fontSize: FONT.xs, marginTop: 2 },
  tabs: { flexDirection: 'row', gap: 4, marginBottom: SPACING.md },
  tab: { flex: 1, paddingVertical: 10, alignItems: 'center', borderRadius: RADIUS.md, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  tabActive: { borderColor: COLORS.primary, backgroundColor: 'rgba(242,107,42,0.08)' },
  tabText: { fontSize: 12, color: COLORS.textDim, fontWeight: '600', textTransform: 'capitalize' },
  tabTextActive: { color: COLORS.primary },
  section: { marginBottom: SPACING.lg },
  sectionHead: { fontSize: 12, color: COLORS.textDim, fontWeight: '700', letterSpacing: 0.5, marginBottom: SPACING.sm },
  badgeGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  badgeCard: { width: '47%', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.sm, borderWidth: 1, borderColor: COLORS.cardBorder },
  badgeTierDot: { width: 8, height: 8, borderRadius: 4, marginBottom: 4 },
  badgeCardName: { fontSize: 12, fontWeight: '700', color: COLORS.text, marginBottom: 4 },
  badgeCardPts: { fontSize: 10, color: COLORS.textDim },
  progressCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.cardBorder },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm, marginBottom: SPACING.md },
  statCard: { width: '47%', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.md, alignItems: 'center', borderWidth: 1, borderColor: COLORS.cardBorder },
  statCardNum: { fontSize: 24, fontWeight: '800', color: COLORS.text, marginTop: 4 },
  statCardLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '600', marginTop: 4 },
  feedRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  refCodeBox: { backgroundColor: 'rgba(255,255,255,0.06)', padding: SPACING.md, borderRadius: RADIUS.md, alignItems: 'center' },
  refCode: { fontSize: 18, fontWeight: '800', color: COLORS.text, letterSpacing: 3 },
  refBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: RADIUS.md, backgroundColor: COLORS.primary },
  refBtnText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  funnelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm },
  funnelStep: { alignItems: 'center', padding: SPACING.md, borderRadius: RADIUS.md, backgroundColor: COLORS.surface, minWidth: 70 },
  funnelNum: { fontSize: 20, fontWeight: '800', color: COLORS.text },
  funnelLabel: { fontSize: 10, color: COLORS.textDim, fontWeight: '600', marginTop: 4 },
  statusChip: { paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full, backgroundColor: COLORS.surface },
  statusText: { fontSize: 10, fontWeight: '700', color: COLORS.textDim },
  fieldLabel: { fontSize: 11, color: COLORS.textDim, fontWeight: '600', marginBottom: 4, marginTop: SPACING.sm },
  fieldInput: { backgroundColor: COLORS.inputBg, borderRadius: RADIUS.md, paddingHorizontal: SPACING.md, paddingVertical: 12, color: COLORS.text, fontSize: 14, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  privRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  privLabel: { fontSize: 13, color: COLORS.text },
  saveBtn: { backgroundColor: COLORS.primary, paddingVertical: 14, borderRadius: RADIUS.md, alignItems: 'center', marginTop: SPACING.md },
  saveBtnText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  emptyBox: { alignItems: 'center', paddingVertical: SPACING.xxl },
  emptyTitle: { color: COLORS.text, fontSize: 16, fontWeight: '700', marginTop: SPACING.sm },
  emptySub: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: 4, textAlign: 'center' },
  shareBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, paddingHorizontal: 16, paddingVertical: 10, borderRadius: RADIUS.md, marginTop: SPACING.md },
  celebOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'center', alignItems: 'center', padding: SPACING.xl },
  celebCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.xl, padding: SPACING.xl, alignItems: 'center', borderWidth: 1, borderColor: COLORS.gold, width: '100%', maxWidth: 340 },
  celebEye: { color: COLORS.textDim, fontSize: 12, fontWeight: '600', marginTop: SPACING.md },
  celebLevel: { color: COLORS.gold, fontSize: 22, fontWeight: '900', marginTop: 4, textAlign: 'center' },
  celebRewards: { marginTop: SPACING.md, gap: 8, width: '100%' },
  celebRewardRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  celebRewardText: { color: COLORS.text, fontSize: 13 },
  celebBtn: { backgroundColor: COLORS.primary, paddingVertical: 14, paddingHorizontal: 40, borderRadius: RADIUS.md, marginTop: SPACING.lg },
  celebBtnText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: SPACING.xl },
  modalCard: { backgroundColor: COLORS.card, borderRadius: RADIUS.xl, padding: SPACING.xl, alignItems: 'center', borderWidth: 1, borderColor: COLORS.cardBorder, width: '100%', maxWidth: 320 },
  modalBadgeIcon: { width: 48, height: 48, borderRadius: 24, alignItems: 'center', justifyContent: 'center' },
  modalBadgeName: { color: COLORS.text, fontSize: 18, fontWeight: '800', marginTop: SPACING.sm },
  modalBadgeTier: { color: COLORS.textDim, fontSize: 12, marginTop: 4 },
  modalBadgeDesc: { color: COLORS.textDim, fontSize: 13, textAlign: 'center', marginTop: SPACING.sm, lineHeight: 20 },
  modalBadgeDate: { color: COLORS.secondary, fontSize: 11, marginTop: 8 },
});
