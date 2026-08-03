import React, { useState, useEffect, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, Linking, Platform, TextInput,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import { useAuth } from '../src/contexts/AuthContext';
import api from '../src/api/client';

const TIER_BADGE: Record<string, { color: string; icon: string }> = {
  free: { color: '#888892', icon: 'gift-outline' },
  premium: { color: '#fdb756', icon: 'diamond' },
  business: { color: '#a78bfa', icon: 'business' },
};

export default function BillingScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [status, setStatus] = useState<any>(null);
  const [plans, setPlans] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const [s, p] = await Promise.all([
        api.get('/billing/status'),
        api.get('/billing/plans'),
      ]);
      setStatus(s.data);
      setPlans(p.data);
    } catch (e: any) {
      if (e?.response?.status === 401) router.replace('/login');
      else Alert.alert('Error', 'Failed to load billing');
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { if (!authLoading && user) reload(); }, [reload, authLoading, user]);

  const getOriginUrl = () => {
    if (Platform.OS === 'web') {
      try { return window.location.origin; } catch { return 'https://bigfm.dubai'; }
    }
    return 'bigfm://billing/return';
  };

  const subscribePlan = async (slug: string) => {
    setBusy(slug);
    try {
      const r = await api.post('/billing/checkout', {
        plan_slug: slug,
        origin_url: getOriginUrl(),
      });
      if (r.data.url) {
        await Linking.openURL(r.data.url);
      } else {
        Alert.alert('Error', 'No checkout URL returned');
      }
    } catch (e: any) {
      Alert.alert('Error', e?.response?.data?.detail || 'Checkout failed');
    } finally { setBusy(null); }
  };

  const changePlan = (slug: string) => {
    const isFree = status.current_plan_slug === 'free' || !status.current_plan_slug;
    if (isFree) {
      subscribePlan(slug);
      return;
    }
    Alert.alert('Switch Plan', `Switch to ${slug}? Upgrades charge a prorated amount immediately.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Switch', onPress: async () => {
        setBusy(slug);
        try {
          const r = await api.post('/billing/change_plan', { target_plan_slug: slug },
            { headers: { 'Idempotency-Key': `change-${Date.now()}` } });
          if (r.data.action === 'upgrade') Alert.alert('Upgraded!', `Charged ${r.data.currency} ${r.data.net_charge?.toFixed(2)}`);
          else if (r.data.action === 'downgrade_queued') Alert.alert('Scheduled', `Downgrade effective ${new Date(r.data.effective_at).toLocaleDateString()}`);
          else Alert.alert('Done', 'Plan updated');
          reload();
        } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Switch failed'); }
        finally { setBusy(null); }
      }},
    ]);
  };

  const doAction = async (label: string, url: string) => {
    setBusy(label);
    try {
      const r = await api.post(url);
      if (r.data.url) {
        await Linking.openURL(r.data.url);
      } else {
        Alert.alert('Done', `${label} completed`);
        reload();
      }
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || `${label} failed`); }
    finally { setBusy(null); }
  };

  if (authLoading || loading) {
    return <View style={st.center} testID="billing-loading"><ActivityIndicator size="large" color={COLORS.primary} /></View>;
  }
  if (!status || !plans) {
    return (
      <SafeAreaView style={st.screen}>
        <View style={st.center}>
          <Ionicons name="alert-circle" size={32} color={COLORS.textDim} />
          <Text style={st.emptyText}>Could not load billing data.</Text>
          <TouchableOpacity style={st.retryBtn} onPress={reload} testID="billing-retry"><Text style={st.retryText}>Retry</Text></TouchableOpacity>
        </View>
      </SafeAreaView>
    );
  }

  const isPastDue = status.billing_status === 'past_due';
  const cancelScheduled = status.cancel_at_period_end;
  const isPaused = status.paused;
  const tier = status.premium_tier || 'free';
  const badge = TIER_BADGE[tier] || TIER_BADGE.free;
  const isFamilyRoot = status.family?.is_family_root;

  return (
    <SafeAreaView style={st.screen} testID="billing-screen">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        <TouchableOpacity onPress={() => router.back()} style={st.backRow} testID="billing-back-btn">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={st.backText}>back to radio</Text>
        </TouchableOpacity>
        <Text style={st.pageTitle}>Billing & Plans</Text>
        <Text style={st.pageSub}>Manage your subscription, family seats, and payments.</Text>

        {/* Past due banner */}
        {isPastDue && (
          <View style={st.pastDueBanner} testID="past-due-banner">
            <Ionicons name="warning" size={20} color={COLORS.red} />
            <View style={{ flex: 1, marginLeft: 10 }}>
              <Text style={st.pastDueTitle}>Payment failed</Text>
              <Text style={st.pastDueSub}>Update card before {status.grace_period_ends_at ? new Date(status.grace_period_ends_at).toLocaleDateString() : 'deadline'}</Text>
            </View>
            <TouchableOpacity style={st.pastDueBtn} onPress={() => doAction('portal', '/billing/portal')} testID="past-due-update-card-btn">
              <Text style={st.pastDueBtnText}>Update</Text>
            </TouchableOpacity>
          </View>
        )}

        {/* Current Plan Card */}
        <View style={st.planCard} testID="current-plan-card">
          <Ionicons name={badge.icon as any} size={36} color={badge.color} />
          <View style={{ flex: 1, marginLeft: SPACING.md }}>
            <Text style={st.metaLabel}>CURRENT PLAN</Text>
            <Text style={st.planName} testID="current-plan-name">{status.current_plan_display || 'Free'}</Text>
            <View style={st.planMeta}>
              <Text style={[st.tierChip, { color: badge.color }]}>{tier.toUpperCase()}</Text>
              <Text style={st.metaSmall}>
                Status: <Text style={{ color: status.billing_status === 'active' ? COLORS.green : COLORS.orange, fontWeight: '700' }}>{status.billing_status}</Text>
              </Text>
            </View>
            {status.next_invoice_at && (
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4, marginTop: 4 }}>
                <Ionicons name="calendar" size={11} color={COLORS.textDim} />
                <Text style={st.metaSmall}>Renews {new Date(status.next_invoice_at).toLocaleDateString()}</Text>
              </View>
            )}
            {cancelScheduled && <Text style={[st.metaSmall, { color: COLORS.orange, marginTop: 4 }]}>Cancels at period end</Text>}
            {status.pending_plan_change && (
              <Text style={[st.metaSmall, { color: COLORS.orange, marginTop: 4 }]}>
                Downgrade to {status.pending_plan_change.target_plan_slug} on {new Date(status.pending_plan_change.scheduled_at).toLocaleDateString()}
              </Text>
            )}
          </View>
        </View>

        {/* Plans Grid */}
        <Text style={st.sectionLabel}>PLANS</Text>
        {(plans.plans || []).map((p: any) => {
          const isCurrent = p.slug === status.current_plan_slug;
          const pBadge = TIER_BADGE[p.tier] || TIER_BADGE.free;
          return (
            <View key={p.slug} style={[st.planRow, isCurrent && { borderColor: COLORS.gold }]} testID={`plan-${p.slug}`}>
              {p.savings_vs_monthly_pct ? (
                <View style={st.savingsBadge} testID={`plan-${p.slug}-savings`}>
                  <Text style={st.savingsText}>SAVE {p.savings_vs_monthly_pct}%</Text>
                </View>
              ) : null}
              <Ionicons name={pBadge.icon as any} size={22} color={pBadge.color} />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={st.planRowName}>{p.display_name}</Text>
                <Text style={st.planRowPrice}>{p.amount_display}</Text>
                <Text style={st.planRowDesc}>{p.description}</Text>
                <View style={{ marginTop: 6, gap: 3 }}>
                  {p.features?.ad_free && <Text style={st.featureText}>• Ad-free listening</Text>}
                  {p.features?.max_skips_per_hour === -1 ? <Text style={st.featureText}>• Unlimited skips</Text>
                    : p.features?.max_skips_per_hour ? <Text style={st.featureText}>• {p.features.max_skips_per_hour} skips/hour</Text> : null}
                  {p.features?.premium_channels > 0 && <Text style={st.featureText}>• {p.features.premium_channels} VIP channels</Text>}
                  {p.family_seats > 1 && <Text style={st.featureText}>• {p.family_seats} family seats</Text>}
                  {p.features?.bigcoin_2x_weekends && <Text style={st.featureText}>• 2× BigCoin weekends</Text>}
                </View>
              </View>
              <TouchableOpacity
                style={[st.switchBtn, isCurrent && { backgroundColor: COLORS.surface, borderColor: COLORS.green }]}
                onPress={() => !isCurrent && p.purchasable && changePlan(p.slug)}
                disabled={isCurrent || !p.purchasable || busy === p.slug}
                testID={`switch-${p.slug}`}
              >
                {busy === p.slug ? <ActivityIndicator size="small" color="#fff" /> :
                  isCurrent ? <><Ionicons name="checkmark" size={12} color={COLORS.green} /><Text style={[st.switchText, { color: COLORS.green }]}>Current</Text></> :
                  !p.purchasable ? <Text style={st.switchText}>Free</Text> :
                  <Text style={st.switchText}>Switch</Text>}
              </TouchableOpacity>
            </View>
          );
        })}

        {/* Manage */}
        <Text style={st.sectionLabel}>MANAGE</Text>
        <View style={st.manageRow}>
          <TouchableOpacity style={st.manageBtn} onPress={() => doAction('portal', '/billing/portal')}
            disabled={busy === 'portal'} testID="open-portal-btn">
            <Ionicons name="open-outline" size={14} color="#fff" />
            <Text style={st.manageBtnText}>Stripe Portal</Text>
          </TouchableOpacity>
          {status.current_plan_slug !== 'free' && !cancelScheduled && !isPaused && (
            <TouchableOpacity style={[st.manageBtn, { backgroundColor: COLORS.surface }]} onPress={() => doAction('cancel', '/billing/cancel')}
              disabled={busy === 'cancel'} testID="cancel-btn">
              <Ionicons name="close" size={14} color={COLORS.red} />
              <Text style={[st.manageBtnText, { color: COLORS.red }]}>Cancel</Text>
            </TouchableOpacity>
          )}
          {cancelScheduled && (
            <TouchableOpacity style={[st.manageBtn, { backgroundColor: COLORS.green }]} onPress={() => doAction('resume', '/billing/resume')}
              disabled={busy === 'resume'} testID="resume-btn">
              <Ionicons name="checkmark" size={14} color="#0a1a0a" />
              <Text style={[st.manageBtnText, { color: '#0a1a0a' }]}>Undo cancel</Text>
            </TouchableOpacity>
          )}
          {status.current_plan_slug !== 'free' && !isPaused && (
            <TouchableOpacity style={[st.manageBtn, { backgroundColor: COLORS.surface }]} onPress={() => doAction('pause', '/billing/pause')}
              disabled={busy === 'pause'} testID="pause-btn">
              <Ionicons name="pause" size={14} color={COLORS.textDim} />
              <Text style={st.manageBtnText}>Pause</Text>
            </TouchableOpacity>
          )}
          {isPaused && (
            <TouchableOpacity style={st.manageBtn} onPress={() => doAction('unpause', '/billing/unpause')}
              disabled={busy === 'unpause'} testID="unpause-btn">
              <Ionicons name="play" size={14} color="#fff" />
              <Text style={st.manageBtnText}>Resume</Text>
            </TouchableOpacity>
          )}
        </View>

        {/* Family */}
        {isFamilyRoot && <FamilySection family={status.family} onReload={reload} />}

        {/* iOS platform note */}
        {Platform.OS === 'ios' && status.current_plan_slug === 'free' && (
          <View style={st.iosNote} testID="ios-web-fallback">
            <Ionicons name="information-circle" size={16} color={COLORS.secondary} />
            <Text style={st.iosNoteText}>On iOS, subscription management opens in your browser (App Store policy).</Text>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function FamilySection({ family, onReload }: { family: any; onReload: () => void }) {
  const [email, setEmail] = useState('');
  const [inviting, setInviting] = useState(false);

  const invite = async () => {
    if (!email) return;
    setInviting(true);
    try {
      await api.post('/billing/family/invite', { email });
      Alert.alert('Sent', `Invite sent to ${email}`);
      setEmail('');
      onReload();
    } catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Invite failed'); }
    finally { setInviting(false); }
  };

  const remove = (uid: string) => {
    Alert.alert('Remove member?', 'They lose Premium immediately.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: async () => {
        try { await api.post('/billing/family/remove', { user_id: uid }); onReload(); }
        catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Failed'); }
      }},
    ]);
  };

  return (
    <View testID="family-section">
      <Text style={st.sectionLabel}>FAMILY ({family.seats_used}/{family.seats_total} seats)</Text>
      {family.seats_remaining > 0 && (
        <View style={{ flexDirection: 'row', gap: 8, marginBottom: SPACING.md }}>
          <TextInput style={[st.familyInput, { flex: 1 }]} value={email} onChangeText={setEmail}
            placeholder="family@email.com" placeholderTextColor={COLORS.textDim}
            keyboardType="email-address" autoCapitalize="none" testID="family-invite-email" />
          <TouchableOpacity style={st.inviteBtn} onPress={invite} disabled={inviting || !email} testID="family-invite-btn">
            {inviting ? <ActivityIndicator size="small" color="#fff" /> : <><Ionicons name="mail" size={14} color="#fff" /><Text style={{ color: '#fff', fontWeight: '700', fontSize: 12 }}>Invite</Text></>}
          </TouchableOpacity>
        </View>
      )}
      {family.members?.map((m: any) => (
        <View key={m.user_id} style={st.memberRow} testID={`family-member-${m.user_id}`}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: '#fff', fontSize: 13, fontWeight: '600' }}>{m.name || m.email}</Text>
            <Text style={{ color: COLORS.textDim, fontSize: 11 }}>{m.email}</Text>
          </View>
          <TouchableOpacity onPress={() => remove(m.user_id)} testID={`family-remove-${m.user_id}`}>
            <Text style={{ color: COLORS.red, fontSize: 11, fontWeight: '700' }}>Remove</Text>
          </TouchableOpacity>
        </View>
      ))}
      {family.pending_invites?.length > 0 && (
        <Text style={[st.metaLabel, { marginTop: SPACING.md }]}>PENDING INVITES</Text>
      )}
      {family.pending_invites?.map((p: any) => (
        <View key={p.token} style={[st.memberRow, { opacity: 0.6 }]}>
          <View style={{ flex: 1 }}>
            <Text style={{ color: '#fff', fontSize: 12 }}>{p.email}</Text>
            <Text style={{ color: COLORS.textDim, fontSize: 10 }}>Expires {new Date(p.expires_at).toLocaleDateString()}</Text>
          </View>
        </View>
      ))}
    </View>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: COLORS.bg, padding: SPACING.xl },
  scroll: { padding: SPACING.md, paddingBottom: 120 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.sm },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  pageTitle: { color: '#fff', fontSize: 24, fontWeight: '900', letterSpacing: -0.5 },
  pageSub: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.lg },
  emptyText: { color: COLORS.textDim, fontSize: FONT.sm, marginTop: SPACING.sm },
  retryBtn: { marginTop: SPACING.md, paddingHorizontal: 20, paddingVertical: 10, backgroundColor: COLORS.primary, borderRadius: RADIUS.md },
  retryText: { color: '#fff', fontWeight: '700' },
  pastDueBanner: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(251,113,133,0.08)', borderWidth: 1, borderColor: COLORS.red, borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.lg },
  pastDueTitle: { color: COLORS.red, fontSize: 13, fontWeight: '700' },
  pastDueSub: { color: COLORS.textDim, fontSize: 11, marginTop: 2 },
  pastDueBtn: { backgroundColor: COLORS.red, paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.md },
  pastDueBtnText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  planCard: { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.lg, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.lg },
  metaLabel: { color: COLORS.textDim, fontSize: 9, fontWeight: '700', letterSpacing: 2, textTransform: 'uppercase' },
  planName: { color: '#fff', fontSize: 28, fontWeight: '900', marginTop: 2 },
  planMeta: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 8, flexWrap: 'wrap' },
  tierChip: { fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  metaSmall: { color: COLORS.textDim, fontSize: 11 },
  sectionLabel: { color: COLORS.textDim, fontSize: 11, fontWeight: '700', letterSpacing: 2, textTransform: 'uppercase', marginBottom: SPACING.sm, marginTop: SPACING.md },
  planRow: { flexDirection: 'row', alignItems: 'flex-start', backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.sm },
  savingsBadge: { position: 'absolute', top: 8, right: 8, backgroundColor: COLORS.green, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full, zIndex: 1 },
  savingsText: { color: '#0a1a0a', fontSize: 9, fontWeight: '800' },
  planRowName: { color: '#fff', fontSize: 15, fontWeight: '700' },
  planRowPrice: { color: COLORS.gold, fontSize: 13, fontWeight: '800', marginTop: 2 },
  planRowDesc: { color: COLORS.textDim, fontSize: 11, marginTop: 2 },
  featureText: { color: COLORS.textDim, fontSize: 10 },
  switchBtn: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: RADIUS.md, backgroundColor: COLORS.primary, flexDirection: 'row', alignItems: 'center', gap: 4, alignSelf: 'flex-start', marginTop: 4 },
  switchText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  manageRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: SPACING.lg },
  manageBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 14, paddingVertical: 10, borderRadius: RADIUS.md, backgroundColor: COLORS.primary },
  manageBtnText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  familyInput: { backgroundColor: COLORS.inputBg, borderWidth: 1, borderColor: COLORS.inputBorder, borderRadius: RADIUS.md, paddingHorizontal: SPACING.md, paddingVertical: 10, color: '#fff', fontSize: 13 },
  inviteBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: COLORS.primary, paddingHorizontal: 16, borderRadius: RADIUS.md },
  memberRow: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  iosNote: { flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(0,217,255,0.06)', padding: SPACING.md, borderRadius: RADIUS.md, marginTop: SPACING.md },
  iosNoteText: { color: COLORS.textDim, fontSize: 11, flex: 1 },
});
