import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  View, Text, ScrollView, TouchableOpacity, TextInput, Switch,
  ActivityIndicator, StyleSheet, Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as WebBrowser from 'expo-web-browser';
import { COLORS, SPACING, RADIUS, FONT, common } from '../../../src/constants/theme';
import {
  getChannelSettings, patchChannelSettings,
  getLightningSplits, putLightningSplits,
  getStripeAccount, createStripeAccount, getStripeOnboardingLink,
  getSubscriptionPlan, createSubscriptionPlan, patchSubscriptionPlan,
  getEpisodeMagicClips,
} from '../../../src/api/podcastApi';

const EMPTY_RECIPIENT = () => ({ name: '', type: 'node', address: '', split_pct: 0, fee_pct: 0 });

export default function ChannelSettingsScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [settings, setSettings] = useState<any>(null);
  const [draft, setDraft] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState('');

  // Lightning
  const [lnRecipients, setLnRecipients] = useState<any[]>([]);
  const [lnSaving, setLnSaving] = useState(false);

  // Subscription plan
  const [acct, setAcct] = useState<any>(null);
  const [acctLoaded, setAcctLoaded] = useState(false);
  const [plan, setPlan] = useState<any>(null);
  const [planForm, setPlanForm] = useState({ name: 'Premium', priceDollars: '4.99', trialDays: 7 });
  const [planBusy, setPlanBusy] = useState(false);

  const load = useCallback(async () => {
    if (!id) return;
    try {
      const s = await getChannelSettings(id);
      setSettings(s); setDraft(s);
      const ln = await getLightningSplits(id).catch(() => ({ recipients: [] }));
      setLnRecipients(ln.recipients || []);
      const sa = await getStripeAccount(s.creator_id).catch(() => null);
      setAcct(sa); setAcctLoaded(true);
      const p = await getSubscriptionPlan(id);
      setPlan(p);
    } catch (e: any) { setErr(e?.response?.data?.detail || 'Load failed'); }
    finally { setLoading(false); }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  /* ── Magic Clips ── */
  const dirty = draft && settings && JSON.stringify(settings) !== JSON.stringify(draft);
  const validClips = draft?.magic_clips_per_episode >= 1 && draft?.magic_clips_per_episode <= 15;

  const saveMagicClips = async () => {
    if (!id || !validClips) return;
    setSaving(true); setErr('');
    try {
      const r = await patchChannelSettings(id, {
        magic_clips_enabled: draft.magic_clips_enabled,
        magic_clips_per_episode: Number(draft.magic_clips_per_episode),
      });
      setSettings(r); setDraft(r);
    } catch (e: any) { setErr(e?.response?.data?.detail || 'Save failed'); }
    finally { setSaving(false); }
  };

  /* ── Lightning ── */
  const lnTotal = useMemo(() => lnRecipients.reduce((s, r) => s + (Number(r.split_pct) || 0), 0), [lnRecipients]);
  const lnValid = Math.abs(lnTotal - 100) <= 0.5;
  const lnColor = lnValid ? COLORS.green : COLORS.red;

  const updateLnRow = (i: number, patch: any) =>
    setLnRecipients(lnRecipients.map((r, idx) => idx === i ? { ...r, ...patch } : r));
  const removeLnRow = (i: number) =>
    setLnRecipients(lnRecipients.filter((_, idx) => idx !== i));

  const saveLightning = async () => {
    if (!id || !lnValid) return;
    setLnSaving(true);
    try {
      const r = await putLightningSplits(id, lnRecipients);
      setLnRecipients(r.recipients || lnRecipients);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Save failed'); }
    finally { setLnSaving(false); }
  };

  /* ── Stripe ── */
  const connectStripe = async () => {
    if (!settings?.creator_id) return;
    setPlanBusy(true);
    try {
      await createStripeAccount(settings.creator_id);
      const link = await getStripeOnboardingLink(settings.creator_id);
      if (link?.url) await WebBrowser.openBrowserAsync(link.url);
    } catch (e: any) { Alert.alert('Stripe', e?.response?.data?.detail || 'Failed'); }
    finally { setPlanBusy(false); }
  };

  const doCreatePlan = async () => {
    if (!id) return;
    setPlanBusy(true);
    try {
      const r = await createSubscriptionPlan(id, {
        name: planForm.name,
        price_cents: Math.round(parseFloat(planForm.priceDollars) * 100),
        trial_days: planForm.trialDays,
      });
      setPlan(r);
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed'); }
    finally { setPlanBusy(false); }
  };

  const togglePlanPause = async () => {
    if (!id || !plan) return;
    setPlanBusy(true);
    try { const r = await patchSubscriptionPlan(id, { active: !plan.active }); setPlan(r); }
    catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed'); }
    finally { setPlanBusy(false); }
  };

  if (loading) return (
    <View style={common.center}><ActivityIndicator size="large" color={COLORS.primary} /></View>
  );
  if (err && !draft) return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <View style={{ padding: SPACING.lg }}>
        <Text testID="mobile-ch-settings-err" style={{ color: COLORS.red }}>{err}</Text>
      </View>
    </SafeAreaView>
  );

  return (
    <SafeAreaView style={common.screen} edges={['top']}>
      <ScrollView contentContainerStyle={{ padding: SPACING.lg, paddingBottom: 60 }}>
        {/* Header */}
        <View style={st.headerRow}>
          <TouchableOpacity onPress={() => router.back()} style={{ padding: 4 }}>
            <Ionicons name="arrow-back" size={22} color={COLORS.text} />
          </TouchableOpacity>
          <View>
            <Text style={{ fontSize: 10, color: COLORS.textDim, letterSpacing: 0.5 }}>CHANNEL SETTINGS</Text>
            <Text testID="mobile-ch-settings-title" style={st.title}>{draft?.title || id}</Text>
          </View>
        </View>

        {/* ═══ MAGIC CLIPS ═══ */}
        <View testID="mobile-magic-clips-section" style={common.card}>
          <Text style={st.sectionH}>Magic Clips</Text>
          <View style={st.toggleRow}>
            <Switch testID="mobile-magic-clips-toggle"
              value={!!draft?.magic_clips_enabled}
              onValueChange={v => setDraft({ ...draft, magic_clips_enabled: v })}
              trackColor={{ true: COLORS.orange, false: '#3f3f46' }} />
            <Text style={st.toggleLabel}>Generate magic clips automatically</Text>
          </View>
          <View style={{ marginTop: 10 }}>
            <Text style={common.label}>Clips per episode (1-15)</Text>
            <TextInput testID="mobile-magic-clips-per-episode"
              style={[common.input, { width: 100 }]}
              keyboardType="numeric"
              value={String(draft?.magic_clips_per_episode ?? 5)}
              onChangeText={t => setDraft({ ...draft, magic_clips_per_episode: Number(t) || 0 })}
              editable={!!draft?.magic_clips_enabled} />
            {!validClips && <Text style={st.fieldErr}>Must be between 1 and 15.</Text>}
          </View>
        </View>

        {/* ═══ LIGHTNING SPLITS ═══ */}
        <View testID="mobile-lightning-section" style={[common.card, { marginTop: 12 }]}>
          <Text style={st.sectionH}>Lightning Splits</Text>
          <View style={st.toggleRow}>
            <Switch testID="mobile-lightning-toggle"
              value={!!draft?.lightning_enabled}
              onValueChange={v => setDraft({ ...draft, lightning_enabled: v })}
              trackColor={{ true: COLORS.orange, false: '#3f3f46' }} />
            <Text style={st.toggleLabel}>Enable Lightning splits in RSS feed</Text>
          </View>

          {draft?.lightning_enabled ? (
            <View testID="mobile-lightning-editor" style={{ marginTop: 12 }}>
              <Text style={{ fontSize: FONT.xs, color: COLORS.textDim, marginBottom: 8, lineHeight: 16 }}>
                Recipients listed here are emitted in the RSS feed so Podcasting 2.0 apps can stream sats to them.
              </Text>
              {lnRecipients.map((r, i) => (
                <View key={i} testID={`mobile-lightning-row-${i}`} style={st.lnRow}>
                  <TextInput style={[common.input, st.lnInput]} placeholder="Name"
                    placeholderTextColor={COLORS.textDim}
                    value={r.name} onChangeText={t => updateLnRow(i, { name: t })} />
                  <TextInput style={[common.input, st.lnInputSm]} placeholder="%"
                    placeholderTextColor={COLORS.textDim} keyboardType="numeric"
                    value={String(r.split_pct)} onChangeText={t => updateLnRow(i, { split_pct: Number(t) || 0 })} />
                  <TouchableOpacity testID={`mobile-lightning-delete-${i}`}
                    onPress={() => removeLnRow(i)} style={st.lnDeleteBtn}>
                    <Ionicons name="close" size={14} color={COLORS.red} />
                  </TouchableOpacity>
                </View>
              ))}
              <TouchableOpacity testID="mobile-lightning-add" style={st.addRecipientBtn}
                onPress={() => setLnRecipients([...lnRecipients, EMPTY_RECIPIENT()])}>
                <Text style={st.addRecipientText}>+ Add recipient</Text>
              </TouchableOpacity>
              <View style={st.lnFooter}>
                <View testID="mobile-lightning-total-chip"
                  style={[st.totalChip, { backgroundColor: `${lnColor}22` }]}>
                  <Text style={[st.totalChipText, { color: lnColor }]}>Total: {lnTotal.toFixed(1)}%</Text>
                </View>
                <TouchableOpacity testID="mobile-lightning-save" style={[st.saveBtn, (!lnValid || lnSaving) && st.saveBtnDisabled]}
                  onPress={saveLightning} disabled={!lnValid || lnSaving || lnRecipients.length === 0}>
                  <Text style={st.saveBtnText}>{lnSaving ? 'Saving…' : 'Save splits'}</Text>
                </TouchableOpacity>
              </View>
            </View>
          ) : (
            <Text testID="mobile-lightning-disabled-hint" style={{ fontSize: FONT.xs, color: COLORS.textDim, marginTop: 8, lineHeight: 16 }}>
              When enabled, recipients you list here will be emitted in the channel's RSS feed.
            </Text>
          )}
        </View>

        {/* ═══ SUBSCRIPTION PLAN ═══ */}
        <View testID="mobile-subscription-section" style={[common.card, { marginTop: 12 }]}>
          <Text style={st.sectionH}>Subscription Plan</Text>

          {!acctLoaded && <ActivityIndicator color={COLORS.primary} />}

          {acctLoaded && !acct && (
            <View>
              <Text style={st.hint}>Connect Stripe to start monetizing this channel.</Text>
              <TouchableOpacity testID="mobile-stripe-connect-cta" style={st.saveBtn}
                onPress={connectStripe} disabled={planBusy}>
                <Text style={st.saveBtnText}>{planBusy ? 'Opening…' : 'Connect Stripe to monetize'}</Text>
              </TouchableOpacity>
            </View>
          )}

          {acctLoaded && acct && !acct.charges_enabled && (
            <View>
              <Text style={st.hint}>Complete Stripe onboarding to enable charges.</Text>
              <TouchableOpacity testID="mobile-stripe-complete-cta" style={st.saveBtn}
                onPress={connectStripe} disabled={planBusy}>
                <Text style={st.saveBtnText}>Complete Stripe onboarding</Text>
              </TouchableOpacity>
            </View>
          )}

          {acctLoaded && acct?.charges_enabled && !plan && (
            <View testID="mobile-plan-form">
              <Text style={st.hint}>Create your channel's subscription plan.</Text>
              <View style={{ marginBottom: 8 }}>
                <Text style={common.label}>Plan name</Text>
                <TextInput testID="mobile-plan-name-input" style={common.input}
                  value={planForm.name} onChangeText={t => setPlanForm({ ...planForm, name: t })}
                  placeholderTextColor={COLORS.textDim} />
              </View>
              <View style={{ marginBottom: 8 }}>
                <Text style={common.label}>Price (USD/mo, min $3)</Text>
                <TextInput testID="mobile-plan-price-input" style={[common.input, { width: 120 }]}
                  keyboardType="numeric" value={planForm.priceDollars}
                  onChangeText={t => setPlanForm({ ...planForm, priceDollars: t })}
                  placeholderTextColor={COLORS.textDim} />
              </View>
              <View style={{ marginBottom: 10 }}>
                <Text style={common.label}>Trial days</Text>
                <TextInput testID="mobile-plan-trial-input" style={[common.input, { width: 80 }]}
                  keyboardType="numeric" value={String(planForm.trialDays)}
                  onChangeText={t => setPlanForm({ ...planForm, trialDays: parseInt(t) || 7 })}
                  placeholderTextColor={COLORS.textDim} />
              </View>
              <TouchableOpacity testID="mobile-plan-create-btn" style={st.saveBtn}
                onPress={doCreatePlan} disabled={planBusy}>
                <Text style={st.saveBtnText}>{planBusy ? 'Creating…' : 'Create plan'}</Text>
              </TouchableOpacity>
            </View>
          )}

          {plan && (
            <View testID="mobile-active-plan-summary">
              <Text style={{ fontSize: FONT.md, color: '#e2e8f0' }}>
                <Text style={{ fontWeight: '700' }}>{plan.name}</Text>
                {' · $'}{(plan.price_cents / 100).toFixed(2)}/mo · {plan.trial_days}-day trial · {plan.active ? 'Active' : 'Paused'}
              </Text>
              <TouchableOpacity testID="mobile-plan-toggle-active" style={st.addRecipientBtn}
                onPress={togglePlanPause} disabled={planBusy}>
                <Text style={st.addRecipientText}>{plan.active ? 'Pause plan' : 'Resume plan'}</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Save / Cancel for magic clips */}
        <View style={st.footerRow}>
          <TouchableOpacity testID="mobile-settings-save" style={[st.saveBtn, (!dirty || saving || !validClips) && st.saveBtnDisabled]}
            onPress={saveMagicClips} disabled={!dirty || saving || !validClips}>
            <Text style={st.saveBtnText}>{saving ? 'Saving…' : 'Save clips settings'}</Text>
          </TouchableOpacity>
          <TouchableOpacity testID="mobile-settings-cancel" style={st.cancelBtn}
            onPress={() => setDraft(settings)} disabled={!dirty}>
            <Text style={{ color: COLORS.textDim, fontSize: FONT.sm }}>Cancel</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  headerRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: SPACING.lg },
  title: { fontSize: FONT.xl, fontWeight: '800', color: COLORS.text },
  sectionH: { fontSize: FONT.lg, fontWeight: '700', color: COLORS.text, marginBottom: 12 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 8 },
  toggleLabel: { color: COLORS.text, fontSize: FONT.sm },
  fieldErr: { color: COLORS.red, fontSize: FONT.xs, marginTop: 4 },
  hint: { fontSize: FONT.xs, color: COLORS.textDim, lineHeight: 16, marginBottom: 10 },
  lnRow: { flexDirection: 'row', gap: 6, marginBottom: 6, alignItems: 'center' },
  lnInput: { flex: 1, paddingVertical: 8, paddingHorizontal: 8, fontSize: FONT.xs },
  lnInputSm: { width: 56, paddingVertical: 8, paddingHorizontal: 6, fontSize: FONT.xs, textAlign: 'center' },
  lnDeleteBtn: { padding: 4, borderWidth: 1, borderColor: 'rgba(239,68,68,0.4)', borderRadius: 4, width: 26, height: 26, alignItems: 'center', justifyContent: 'center' },
  addRecipientBtn: { paddingVertical: 6, paddingHorizontal: 12, borderRadius: 6, borderWidth: 1, borderColor: COLORS.cardBorder, alignSelf: 'flex-start', marginTop: 6 },
  addRecipientText: { fontSize: FONT.xs, color: COLORS.textDim, fontWeight: '600' },
  lnFooter: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 12 },
  totalChip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999 },
  totalChipText: { fontSize: FONT.xs, fontWeight: '700', fontVariant: ['tabular-nums'] },
  saveBtn: { backgroundColor: COLORS.orange, paddingVertical: 8, paddingHorizontal: 16, borderRadius: 6, alignSelf: 'flex-start' },
  saveBtnDisabled: { backgroundColor: '#3f3f46' },
  saveBtnText: { fontWeight: '700', color: '#0a0a0c', fontSize: FONT.sm },
  cancelBtn: { paddingVertical: 8, paddingHorizontal: 16, borderRadius: 6, borderWidth: 1, borderColor: COLORS.cardBorder },
  footerRow: { flexDirection: 'row', gap: 8, marginTop: SPACING.lg },
});
