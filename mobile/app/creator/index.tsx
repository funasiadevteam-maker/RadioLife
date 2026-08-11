import { useEffect, useState, useCallback } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, Modal,
  ActivityIndicator, RefreshControl, StyleSheet, Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as WebBrowser from 'expo-web-browser';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../src/constants/theme';
import {
  getCreatorMe, applyAsCreator, getCreatorChannels, createChannel,
  getNudgeStatus, pauseNudges, getFunnelSummary,
} from '../../src/api/podcastApi';

export default function CreatorDashboard() {
  const router = useRouter();
  const [creator, setCreator] = useState<any>(null);
  const [channels, setChannels] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [showApply, setShowApply] = useState(false);
  const [showNewCh, setShowNewCh] = useState(false);
  const [nudge, setNudge] = useState<any>(null);
  const [nudgeBusy, setNudgeBusy] = useState(false);
  const [funnel, setFunnel] = useState<any>(null);
  const load = useCallback(async () => {
    try {
      const me = await getCreatorMe();
      const c = me?.creator || me;
      setCreator(c);
      if (c?.application_status === 'approved') {
        const chs = await getCreatorChannels(c.id);
        setChannels(chs);
        const ns = await getNudgeStatus(c.id);
        setNudge(ns);
        const fs = await getFunnelSummary(c.id).catch(() => null);
        setFunnel(fs);
      }
    } catch { setCreator(null); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const doPauseNudge = async () => {
    if (!creator?.id) return;
    setNudgeBusy(true);
    try { await pauseNudges(creator.id); await load(); }
    finally { setNudgeBusy(false); }
  };

  if (loading) return (
    <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
  );

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView
        contentContainerStyle={{ padding: SPACING.lg, paddingBottom: 60 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); load(); }} tintColor={COLORS.primary} />}
      >
        {/* Header */}
        <View style={s.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <View style={{ flex: 1 }}>
            <Text testID="mobile-creator-title" style={s.title}>Creator Studio</Text>
            <Text style={s.subtitle}>Manage your podcast channels, episodes, and distribution.</Text>
          </View>
        </View>

        {/* Nudge banner */}
        {nudge?.qualifies && (
          <View testID="mobile-nudge-banner" style={s.nudgeBanner}>
            <View style={{ flex: 1 }}>
              <Text style={s.nudgeLabel}>GET STARTED</Text>
              <Text style={s.nudgeText}>
                {nudge.banner_message || 'Record your first episode to start building your audience'}
              </Text>
            </View>
            <TouchableOpacity testID="mobile-nudge-record-cta" style={s.nudgeCta}
              onPress={() => WebBrowser.openBrowserAsync(
                `${process.env.EXPO_PUBLIC_BACKEND_URL?.replace('/api', '')}/creator/studio/new`
              )}>
              <Text style={s.nudgeCtaText}>Record →</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="mobile-nudge-pause" style={s.nudgePause}
              onPress={doPauseNudge} disabled={nudgeBusy}>
              <Text style={s.nudgePauseText}>{nudgeBusy ? '…' : 'Pause'}</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Not a creator */}
        {!creator && (
          <View testID="mobile-creator-apply-cta" style={s.applyCta}>
            <Ionicons name="mic-outline" size={40} color={COLORS.textDim} />
            <Text style={s.applyText}>Start creating podcasts on RadioLife.</Text>
            <TouchableOpacity style={s.applyBtn} onPress={() => setShowApply(true)}>
              <Text style={s.applyBtnText}>Apply to become a creator</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Pending */}
        {creator?.application_status === 'pending' && (
          <View testID="mobile-creator-pending" style={[s.statusCard, { borderColor: 'rgba(245,158,11,0.3)' }]}>
            <Ionicons name="hourglass-outline" size={20} color={COLORS.orange} />
            <Text style={[s.statusText, { color: COLORS.orange }]}>
              Your application is being reviewed. We&apos;ll email {creator.contact_email} when approved.
            </Text>
          </View>
        )}

        {/* Rejected */}
        {creator?.application_status === 'rejected' && (
          <View testID="mobile-creator-rejected" style={[s.statusCard, { borderColor: 'rgba(239,68,68,0.3)' }]}>
            <Ionicons name="close-circle-outline" size={20} color={COLORS.red} />
            <Text style={[s.statusText, { color: COLORS.red }]}>
              Application not approved. {creator.rejection_reason || ''}
            </Text>
          </View>
        )}

        {/* Approved — tabs */}
        {creator?.application_status === 'approved' && (
          <>
            {/* Quick actions */}
            <View style={s.actionsRow}>
              <TouchableOpacity testID="mobile-creator-new-channel" style={s.actionBtn}
                onPress={() => setShowNewCh(true)}>
                <Ionicons name="add-circle" size={18} color="#0a0a0c" />
                <Text style={s.actionBtnText}>New Channel</Text>
              </TouchableOpacity>
              <TouchableOpacity testID="mobile-creator-funnel-link" style={[s.actionBtn, s.actionBtnGhost]}
                onPress={() => router.push('/creator/funnel')}>
                <Ionicons name="analytics-outline" size={16} color={COLORS.textDim} />
                <Text style={s.actionBtnGhostText}>Funnel</Text>
              </TouchableOpacity>
            </View>

            {/* Funnel Summary Card */}
            {funnel?.stages && (
              <TouchableOpacity testID="mobile-funnel-summary-card" style={s.funnelCard}
                onPress={() => router.push('/creator/funnel')}>
                <View style={s.funnelHeader}>
                  <Text style={s.funnelTitle}>Conversion Funnel (7d)</Text>
                  <Ionicons name="chevron-forward" size={14} color={COLORS.textDim} />
                </View>
                <View style={s.funnelStages}>
                  {(funnel.stages || []).slice(0, 4).map((st: any, i: number) => (
                    <View key={st.name || i} style={s.funnelStage}>
                      <Text style={s.funnelStageCount}>{st.count ?? 0}</Text>
                      <Text style={s.funnelStageName} numberOfLines={1}>{st.name || `Stage ${i+1}`}</Text>
                    </View>
                  ))}
                </View>
              </TouchableOpacity>
            )}

            {/* Channels */}
            <Text style={common.sectionTitle}>Your Channels ({channels.length})</Text>
            {channels.length === 0 && (
              <Text style={s.emptyText}>No channels yet. Create one to start podcasting.</Text>
            )}
            {channels.map(ch => (
              <TouchableOpacity key={ch.id} testID={`mobile-creator-channel-${ch.id}`}
                style={s.channelRow}
                onPress={() => router.push(`/creator/channel/${ch.id}`)}>
                <View style={{ flex: 1 }}>
                  <Text style={s.channelTitle}>{ch.title}</Text>
                  <Text style={s.channelMeta}>
                    {ch.category} · {ch.language} · {ch.active ? 'LIVE' : 'pending review'}
                  </Text>
                </View>
                <TouchableOpacity testID={`mobile-channel-settings-link-${ch.id}`}
                  style={s.settingsBtn}
                  onPress={() => router.push(`/creator/channel-settings/${ch.id}`)}>
                  <Text style={s.settingsBtnText}>Settings</Text>
                </TouchableOpacity>
              </TouchableOpacity>
            ))}
          </>
        )}
      </ScrollView>

      {/* Apply Modal */}
      <ApplyModal visible={showApply} onClose={() => setShowApply(false)} onDone={load} />

      {/* New Channel Modal */}
      <NewChannelModal visible={showNewCh} creatorId={creator?.id}
        onClose={() => setShowNewCh(false)} onDone={load} />
    </SafeAreaView>
  );
}

function ApplyModal({ visible, onClose, onDone }: any) {
  const [form, setForm] = useState({ display_name: '', bio: '', contact_email: '', market: 'dubai' });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await applyAsCreator(form); onClose(); onDone(); }
    catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };
  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={s.modalOverlay}>
        <View testID="mobile-creator-apply-modal" style={s.modalContent}>
          <Text style={s.modalTitle}>Apply to become a creator</Text>
          {['display_name', 'contact_email', 'bio'].map(k => (
            <View key={k} style={{ marginBottom: 10 }}>
              <Text style={common.label}>{k.replace(/_/g, ' ')}</Text>
              <TextInput testID={`mobile-creator-apply-${k}`} style={common.input}
                value={(form as any)[k]}
                onChangeText={t => setForm({ ...form, [k]: t })}
                placeholderTextColor={COLORS.textDim} />
            </View>
          ))}
          <TouchableOpacity testID="mobile-creator-apply-submit" style={s.submitBtn}
            onPress={submit} disabled={busy}>
            <Text style={s.submitBtnText}>{busy ? 'Submitting…' : 'Submit application'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onClose} style={{ marginTop: 12, alignItems: 'center' }}>
            <Text style={{ color: COLORS.textDim }}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

function NewChannelModal({ visible, creatorId, onClose, onDone }: any) {
  const [form, setForm] = useState({ title: '', description: '', category: 'tech', language: 'en', script_preference: 'auto' });
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (!creatorId) return;
    setBusy(true);
    try { await createChannel(creatorId, form); onClose(); onDone(); }
    catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed'); }
    finally { setBusy(false); }
  };
  return (
    <Modal visible={visible} animationType="slide" transparent>
      <View style={s.modalOverlay}>
        <View testID="mobile-creator-new-channel-modal" style={s.modalContent}>
          <Text style={s.modalTitle}>New Channel</Text>
          <View style={{ marginBottom: 10 }}>
            <Text style={common.label}>Title</Text>
            <TextInput testID="mobile-channel-form-title" style={common.input}
              value={form.title} onChangeText={t => setForm({ ...form, title: t })}
              placeholder="Channel title" placeholderTextColor={COLORS.textDim} />
          </View>
          <View style={{ marginBottom: 10 }}>
            <Text style={common.label}>Description</Text>
            <TextInput testID="mobile-channel-form-desc" style={[common.input, { minHeight: 60 }]}
              value={form.description} onChangeText={t => setForm({ ...form, description: t })}
              multiline placeholder="Description" placeholderTextColor={COLORS.textDim} />
          </View>
          <TouchableOpacity testID="mobile-channel-form-submit" style={s.submitBtn}
            onPress={submit} disabled={busy}>
            <Text style={s.submitBtnText}>{busy ? 'Creating…' : 'Create'}</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={onClose} style={{ marginTop: 12, alignItems: 'center' }}>
            <Text style={{ color: COLORS.textDim }}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, marginBottom: SPACING.lg },
  title: { fontSize: FONT.xxl, fontWeight: '800', color: COLORS.text },
  subtitle: { fontSize: FONT.sm, color: COLORS.textDim, marginTop: 2 },
  nudgeBanner: {
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, borderRadius: 12,
    borderWidth: 1, borderColor: 'rgba(245,158,11,0.5)', backgroundColor: '#1c1b35',
    marginBottom: SPACING.lg,
  },
  nudgeLabel: { fontSize: 10, color: '#fbbf24', letterSpacing: 0.6, marginBottom: 4 },
  nudgeText: { fontSize: FONT.sm, color: '#fbf3da', lineHeight: 20 },
  nudgeCta: { backgroundColor: COLORS.orange, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 8 },
  nudgeCtaText: { fontWeight: '700', fontSize: FONT.sm, color: '#0a0a0c' },
  nudgePause: { padding: 6, borderWidth: 1, borderColor: '#2a2d35', borderRadius: 6 },
  nudgePauseText: { fontSize: 10, color: COLORS.textDim },
  applyCta: { alignItems: 'center', paddingVertical: 40 },
  applyText: { color: COLORS.textDim, marginTop: 12, marginBottom: SPACING.md, fontSize: FONT.md },
  applyBtn: { backgroundColor: COLORS.orange, paddingVertical: 10, paddingHorizontal: 18, borderRadius: 8 },
  applyBtnText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.md },
  statusCard: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 14, borderRadius: 10, borderWidth: 1, marginBottom: SPACING.lg },
  statusText: { flex: 1, fontSize: FONT.sm, lineHeight: 18 },
  actionsRow: { flexDirection: 'row', gap: 10, marginBottom: SPACING.lg },
  actionBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.orange, paddingVertical: 8, paddingHorizontal: 14, borderRadius: 8 },
  actionBtnText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.sm },
  actionBtnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: COLORS.cardBorder },
  actionBtnGhostText: { fontWeight: '600', color: COLORS.textDim, fontSize: FONT.sm },
  channelRow: {
    flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14, marginBottom: 8,
    borderRadius: 10, backgroundColor: COLORS.card, borderWidth: 1, borderColor: COLORS.cardBorder,
  },
  channelTitle: { fontSize: FONT.md, fontWeight: '700', color: COLORS.text },
  channelMeta: { fontSize: FONT.xs, color: COLORS.textDim, marginTop: 3 },
  settingsBtn: { paddingVertical: 4, paddingHorizontal: 10, borderRadius: 6, borderWidth: 1, borderColor: 'rgba(245,158,11,0.3)' },
  settingsBtnText: { fontSize: FONT.xs, color: COLORS.orange },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, textAlign: 'center', paddingVertical: 20 },
  funnelCard: {
    backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md,
    borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.lg,
  },
  funnelHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  funnelTitle: { fontSize: FONT.sm, fontWeight: '700', color: COLORS.textDim, letterSpacing: 0.5 },
  funnelStages: { flexDirection: 'row', justifyContent: 'space-around' },
  funnelStage: { alignItems: 'center', flex: 1 },
  funnelStageCount: { fontSize: FONT.lg, fontWeight: '800', color: COLORS.text },
  funnelStageName: { fontSize: 9, color: COLORS.textDim, marginTop: 2, textTransform: 'uppercase' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center' },
  modalContent: { backgroundColor: '#13131a', padding: 22, borderRadius: 14, width: '90%', maxWidth: 440 },
  modalTitle: { fontSize: FONT.lg, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.md },
  submitBtn: { backgroundColor: COLORS.orange, paddingVertical: 10, borderRadius: 8, alignItems: 'center' },
  submitBtnText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.md },
});
