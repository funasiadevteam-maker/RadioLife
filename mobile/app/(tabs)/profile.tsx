import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, Switch, Modal, Pressable,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/contexts/AuthContext';
import { BRAND } from '../../src/config/brand';
import { SPACING, FONT, RADIUS } from '../../src/constants/theme';
import type { ThemeTokens } from '../../src/theme/tokens';
import { useAppTheme, useThemeTokens } from '../../src/theme/ThemeProvider';
import AccentSwatches from '../../src/theme/AccentSwatches';
import ChipGrid from '../../src/components/ChipGrid';
import FunAsiaFooter from '../../src/components/FunAsiaFooter';
import api from '../../src/api/client';
import { getCreatorMe } from '../../src/api/podcastApi';

const LANGUAGES = ['hindi', 'punjabi', 'english', 'bollywood', 'tamil', 'arabic', 'malayalam', 'telugu'];
const GENRES = ['bollywood', 'hip_hop', 'pop', 'electronic', 'retro', 'indie', 'sufi', 'ghazal', 'devotional', 'rock', 'punjabi_pop', 'arabic_pop'];
const ERAS = ['80s', '90s', '2000s', '2010s', '2020s'];
const MOODS = ['energetic', 'chill', 'romantic', 'party', 'uplifting', 'melancholy', 'devotional', 'nostalgic'];
const ACTIVITIES = ['morning_commute', 'workday_focus', 'lunch_break', 'evening_commute', 'dinner', 'late_night_drive', 'workout', 'party', 'devotional_time'];
const DUBAI_AREAS = ['Karama', 'Bur Dubai', 'Deira', 'Al Nahda', 'JLT', 'Business Bay', 'Downtown', 'Marina', 'Sharjah', 'Other'];
const MARKETS = [
  { key: 'dubai', label: 'Dubai', country: 'United Arab Emirates' },
  { key: 'new_york', label: 'New York', country: 'United States' },
  { key: 'london', label: 'London', country: 'United Kingdom' },
  { key: 'mumbai', label: 'Mumbai', country: 'India' },
  { key: 'los_angeles', label: 'Los Angeles', country: 'United States' },
  { key: 'dfw', label: 'Dallas', country: 'United States' },
];
const MARKET_LABEL: Record<string, string> = MARKETS.reduce((a, m) => ({ ...a, [m.key]: m.label }), {});

const hourLabel = (h: number) => {
  const ap = h < 12 ? 'AM' : 'PM';
  const hr = h % 12 === 0 ? 12 : h % 12;
  return `${hr}:00 ${ap}`;
};
const HOSTS = [
  { id: 'auto', label: 'Auto (smart routing)' },
  { id: 'veer_dubai', label: 'Veer — late-night charm' },
  { id: 'monika_dubai', label: 'Monika — warm & natural' },
  { id: 'dj_dubai', label: 'DJ Charlie — club energy' },
];

export default function ProfileScreen() {
  const { user, refresh, logout } = useAuth();
  const router = useRouter();
  const { mode: apprMode, setMode: setAppr, schedule, setSchedule, t } = useAppTheme();
  const st = makeStyles(t);
  const cst = makeCst(t);
  const [pv, setPv] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [section, setSection] = useState<'menu' | 'prefs'>('menu');
  const [creatorStatus, setCreatorStatus] = useState<string | null>(null);
  const [market, setMarket] = useState<string | null>(null);
  const [cityLabel, setCityLabel] = useState<string>('');
  const [cityOpen, setCityOpen] = useState(false);
  const [cityBusy, setCityBusy] = useState<string | null>(null);

  useEffect(() => {
    if (user?.preference_vector) setPv({ ...user.preference_vector });
    // Check creator approval status for gating
    getCreatorMe().then(me => {
      const c = me?.creator || me;
      if (c?.application_status) setCreatorStatus(c.application_status);
    }).catch(() => setCreatorStatus(null));
    api.get('/geo/me').then(({ data }) => {
      setMarket(data?.market || null);
      setCityLabel(data?.city || MARKET_LABEL[data?.market] || '');
    }).catch(() => {});
  }, [user]);

  const pickCity = async (key: string) => {
    if (cityBusy) return;
    setCityBusy(key);
    try {
      await api.patch('/users/me/market', { market: key });
      setMarket(key);
      setCityLabel(MARKET_LABEL[key] || key);
      setCityOpen(false);
      Alert.alert('City updated', `You're now browsing ${MARKET_LABEL[key] || key}. Local stations, news and offers will update.`);
    } catch (_) {
      Alert.alert('Error', "Couldn't switch city. Please try again.");
    } finally { setCityBusy(null); }
  };

  if (!user) return null;
  if (!pv) return <View style={st.loadingWrap}><ActivityIndicator size="large" color={t.primary} /></View>;

  const toggle = (key: string) => (id: string) => {
    setPv((p: any) => {
      const arr = p[key] || [];
      return { ...p, [key]: arr.includes(id) ? arr.filter((x: string) => x !== id) : [...arr, id] };
    });
  };

  const save = async () => {
    if (saving) return;
    if (pv.languages.length < 1) return Alert.alert('Validation', 'Pick at least 1 language');
    if (pv.genres.length < 2) return Alert.alert('Validation', 'Pick at least 2 genres');
    setSaving(true);
    try { await api.post('/users/preferences', pv); await refresh(); Alert.alert('Saved', 'Preferences updated'); }
    catch (e: any) { Alert.alert('Error', e?.response?.data?.detail || 'Could not save'); }
    finally { setSaving(false); }
  };

  const redoOnboarding = async () => {
    setResetting(true);
    try { await api.post('/users/onboarding/reset'); await refresh(); router.replace('/onboarding'); }
    catch { Alert.alert('Error', 'Could not reset'); }
    finally { setResetting(false); }
  };

  const doLogout = async () => { await logout(); router.replace('/login'); };

  const confirmDelete = () => {
    Alert.alert(
      'Delete Account',
      'This will permanently delete your account and all data. This cannot be undone.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete', style: 'destructive', onPress: async () => {
          try { await api.post('/users/delete_account'); await logout(); router.replace('/login'); }
          catch { Alert.alert('Error', 'Could not delete account. Contact support.'); }
        }},
      ]
    );
  };

  if (section === 'menu') {
    return (
      <SafeAreaView style={st.container} testID="profile-page">
        <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
          {/* User card */}
          <View style={st.idCard} testID="profile-id-card">
            <View style={st.profileAvatar}><Text style={st.profileInitials}>{(user.name || '?')[0].toUpperCase()}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={st.profileName} testID="profile-name">{user.name}</Text>
              <Text style={st.profileEmail} testID="profile-email">{user.email}</Text>
              <View style={st.tagRow}>
                <View style={st.profileTag}><Text style={st.profileTagText}>{user.auth_provider?.toUpperCase()}</Text></View>
                {user.role === 'admin' && (
                  <View style={[st.profileTag, { borderColor: t.secondary }]} testID="profile-admin-tag">
                    <Ionicons name="shield" size={10} color={t.secondary} />
                    <Text style={[st.profileTagText, { color: t.secondary }]}>ADMIN</Text>
                  </View>
                )}
                {user.is_premium && (
                  <View style={[st.profileTag, { borderColor: t.gold }]} testID="profile-vip-tag">
                    <Ionicons name="diamond" size={10} color={t.gold} />
                    <Text style={[st.profileTagText, { color: t.gold }]}>VIP</Text>
                  </View>
                )}
              </View>
            </View>
          </View>

          {/* Menu Items */}
          <Text style={st.menuLabel}>ACCOUNT</Text>
          <MenuItem icon="person-outline" label="Edit Preferences" sub="Languages, genres, moods, RJ personality"
            onPress={() => setSection('prefs')} testID="menu-edit-prefs" />
          <MenuItem icon="sparkles-outline" label="Companion Memory" sub="What Fun AI remembers about your taste"
            onPress={() => router.push('/fun-ai-memory')} testID="menu-fun-ai-memory" />
          <MenuItem icon="grid-outline" label="Personalize Home" sub="Choose & reorder the features on your Home"
            onPress={() => router.push('/personalize')} testID="menu-personalize" />
          <MenuItem icon="location-outline" label="Switch City" sub={cityLabel ? `Currently: ${cityLabel}` : 'Change your local market'}
            onPress={() => setCityOpen(true)} testID="menu-switch-city" />
          <MenuItem icon="card-outline" label="Billing & Plans" sub="Manage subscription, upgrade, payment"
            onPress={() => router.push('/billing')} testID="menu-billing" />
          <MenuItem icon="notifications-outline" label="Notifications" sub="Push notification preferences"
            onPress={() => router.push('/notifications')}
            testID="menu-notifications" />

          <Text style={[st.menuLabel, { marginTop: SPACING.lg }]}>APPEARANCE</Text>
          <View style={st.apprRow} testID="profile-appearance">
            {(['light', 'dark', 'system'] as const).map((m) => {
              const active = apprMode === m;
              const ic = m === 'light' ? 'sunny-outline' : m === 'dark' ? 'moon-outline' : 'phone-portrait-outline';
              const lbl = m === 'light' ? 'Light' : m === 'dark' ? 'Dark' : 'System';
              return (
                <TouchableOpacity key={m} testID={`appearance-${m}`} activeOpacity={0.85}
                  onPress={() => setAppr(m)} style={[st.apprChip, active && st.apprChipActive]}>
                  <Ionicons name={ic as any} size={18} color={active ? t.onAccent : t.textDim} />
                  <Text style={[st.apprChipText, active && { color: t.onAccent }]}>{lbl}</Text>
                </TouchableOpacity>
              );
            })}
          </View>

          <Text style={st.apprSubLabel}>Accent colour</Text>
          <AccentSwatches size={36} />

          <View style={st.schedCard}>
            <View style={st.schedHeader}>
              <Ionicons name="time-outline" size={18} color={t.brand} />
              <View style={{ flex: 1 }}>
                <Text style={st.schedTitle}>Scheduled Dark</Text>
                <Text style={st.schedSub}>Auto dark at night, light in the morning</Text>
              </View>
              <Switch testID="schedule-toggle" value={schedule.enabled}
                onValueChange={(v) => setSchedule({ enabled: v })}
                trackColor={{ false: t.lineStrong, true: t.brand }} thumbColor="#fff" />
            </View>
            {schedule.enabled && (
              <View style={st.schedRows} testID="schedule-times">
                {([
                  { label: 'Dark from', key: 'dark_hour' as const, idp: 'dark' },
                  { label: 'Light from', key: 'light_hour' as const, idp: 'light' },
                ]).map((row) => (
                  <View key={row.key} style={st.schedRow}>
                    <Text style={st.schedRowLabel}>{row.label}</Text>
                    <View style={st.stepper}>
                      <TouchableOpacity testID={`schedule-${row.idp}-dec`} hitSlop={8}
                        onPress={() => setSchedule({ [row.key]: (schedule[row.key] + 23) % 24 } as any)}>
                        <Ionicons name="chevron-back" size={18} color={t.text} />
                      </TouchableOpacity>
                      <Text testID={`schedule-${row.idp}-hour`} style={st.stepperVal}>{hourLabel(schedule[row.key])}</Text>
                      <TouchableOpacity testID={`schedule-${row.idp}-inc`} hitSlop={8}
                        onPress={() => setSchedule({ [row.key]: (schedule[row.key] + 1) % 24 } as any)}>
                        <Ionicons name="chevron-forward" size={18} color={t.text} />
                      </TouchableOpacity>
                    </View>
                  </View>
                ))}
              </View>
            )}
          </View>

          <Text style={[st.menuLabel, { marginTop: SPACING.lg }]}>GENERAL</Text>
          <MenuItem icon="megaphone-outline" label="Advertise on FUUSIC" sub="Create ads, manage campaigns"
            onPress={() => router.push('/advertiser')}
            testID="menu-advertiser" />
          <MenuItem icon="radio-outline" label="Sponsor a station" sub="Promote a station · CPM/CPC bids"
            onPress={() => router.push('/advertiser/promote-station')}
            testID="menu-sponsor-station" />
          <MenuItem icon="sparkles-outline" label="Scan & Earn" sub="AI-decided points per dollar spent"
            onPress={() => router.push('/scan-earn')}
            testID="menu-scan-earn" />
          <MenuItem icon="qr-code-outline" label="Redeem & Loyalty" sub="Business: redeem coupons · loyalty tier"
            onPress={() => router.push('/merchant/redeem')}
            testID="menu-merchant-redeem" />
          <MenuItem icon="storefront-outline" label="Get More Customers" sub="Marketplace: launch trivia & coupon campaigns"
            onPress={() => router.push('/merchant/marketplace')}
            testID="menu-merchant-marketplace" />
          <MenuItem icon="flash-outline" label="Sponsor a Bonus" sub="Run a points multiplier at your venue"
            onPress={() => router.push('/merchant/bonuses')}
            testID="menu-merchant-bonuses" />
          <MenuItem icon="cash-outline" label="Payouts & Earnings" sub="Get paid via Stripe · view your earnings"
            onPress={() => router.push('/payouts')}
            testID="menu-payouts" />
          {creatorStatus === 'approved' && (
            <MenuItem icon="mic-outline" label="Creator Studio" sub="Manage channels, episodes, distribution"
              onPress={() => router.push('/creator')}
              testID="menu-creator-studio" />
          )}
          <MenuItem icon="refresh" label="Re-do Onboarding" sub="Reset preferences and restart setup"
            onPress={redoOnboarding} loading={resetting} testID="redo-onboarding-btn" />
          <MenuItem icon="help-circle-outline" label="Help & Support" sub="FAQ, contact support"
            onPress={() => Alert.alert('Help', `Email: ${BRAND.supportEmail}`)} testID="menu-help" />
          <MenuItem icon="information-circle-outline" label="About FUUSIC" sub="Version 1.0.0 · Phase 11.5"
            onPress={() => Alert.alert('FUUSIC', `${BRAND.tagline}\n\nEverything you love — audio, friends, local businesses, games, rewards and live experiences — together.\n\nVersion 1.0.0`)} testID="menu-about" />

          <Text style={[st.menuLabel, { marginTop: SPACING.lg }]}>DANGER ZONE</Text>
          <MenuItem icon="log-out" label="Sign Out" color={t.orange}
            onPress={doLogout} testID="signout-btn" />
          <MenuItem icon="trash-outline" label="Delete Account" sub="Permanently delete all data" color={t.red}
            onPress={confirmDelete} testID="menu-delete-account" />
          <FunAsiaFooter />
        </ScrollView>

        <Modal visible={cityOpen} transparent animationType="slide" onRequestClose={() => setCityOpen(false)}>
          <Pressable style={cst.backdrop} onPress={() => setCityOpen(false)} testID="city-modal-backdrop">
            <Pressable style={cst.sheet} onPress={(e) => e.stopPropagation()} testID="city-modal">
              <View style={cst.handle} />
              <Text style={cst.title}>Change your city</Text>
              <Text style={cst.sub}>FUUSIC personalises stations, news and offers per market.</Text>
              <ScrollView style={{ maxHeight: 380 }} showsVerticalScrollIndicator={false}>
                {MARKETS.map((m) => {
                  const active = m.key === market;
                  return (
                    <TouchableOpacity key={m.key} disabled={!!cityBusy} onPress={() => pickCity(m.key)}
                      testID={`city-option-${m.key}`} activeOpacity={0.8}
                      style={[cst.row, active && cst.rowActive]}>
                      <View style={{ flex: 1 }}>
                        <Text style={[cst.rowLabel, active && { color: t.primary }]}>{m.label}</Text>
                        <Text style={cst.rowCountry}>{m.country}</Text>
                      </View>
                      {cityBusy === m.key
                        ? <ActivityIndicator size="small" color={t.primary} />
                        : active
                          ? <Ionicons name="checkmark-circle" size={20} color={t.primary} />
                          : <Ionicons name="chevron-forward" size={18} color={t.textMuted} />}
                    </TouchableOpacity>
                  );
                })}
              </ScrollView>
            </Pressable>
          </Pressable>
        </Modal>
      </SafeAreaView>
    );
  }

  /* ─── Preferences Editor ──────────────────────── */
  return (
    <SafeAreaView style={st.container} testID="profile-prefs">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        <TouchableOpacity onPress={() => setSection('menu')} style={st.backRow} testID="prefs-back">
          <Ionicons name="chevron-back" size={14} color={t.textDim} />
          <Text style={st.backText}>back to menu</Text>
        </TouchableOpacity>
        <Text style={st.prefsTitle}>Edit Preferences</Text>

        <View style={st.prefBlock}>
          <Text style={st.prefTitle}>Languages</Text>
          <ChipGrid options={LANGUAGES} selected={pv.languages || []} onToggle={toggle('languages')} testID="pref-languages" />
          <TouchableOpacity testID="pref-show-all-languages" activeOpacity={0.7}
            onPress={() => setPv((p: any) => ({ ...p, show_all_languages: !p.show_all_languages }))}
            style={st.showAllRow}>
            <Ionicons name={pv.show_all_languages ? 'checkbox' : 'square-outline'} size={20}
              color={pv.show_all_languages ? t.secondary : t.textDim} />
            <Text style={st.showAllText}>Show content in all languages (don’t filter to mine)</Text>
          </TouchableOpacity>
          <Text style={[st.scopeHint, pv.show_all_languages && { opacity: 0.4 }]}>Apply my language filter to:</Text>
          {([['music', 'Music & stations'], ['games', 'Games'], ['quiz', 'Quiz & trivia']] as [string, string][]).map(([k, label]) => {
            const on = (pv.content_lang_scopes || {})[k] !== false;
            return (
              <TouchableOpacity key={k} testID={`pref-scope-${k}`} activeOpacity={0.7}
                disabled={!!pv.show_all_languages}
                onPress={() => setPv((p: any) => ({ ...p, content_lang_scopes: { ...(p.content_lang_scopes || {}), [k]: !on } }))}
                style={[st.showAllRow, !!pv.show_all_languages && { opacity: 0.4 }]}>
                <Ionicons name={on ? 'checkbox' : 'square-outline'} size={18}
                  color={on ? t.secondary : t.textDim} />
                <Text style={st.showAllText}>{label}</Text>
              </TouchableOpacity>
            );
          })}
        </View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>Genres</Text><ChipGrid options={GENRES} selected={pv.genres || []} onToggle={toggle('genres')} testID="pref-genres" /></View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>Eras</Text><ChipGrid options={ERAS} selected={pv.eras || []} onToggle={toggle('eras')} testID="pref-eras" /></View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>Moods</Text><ChipGrid options={MOODS} selected={pv.moods || []} onToggle={toggle('moods')} testID="pref-moods" /></View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>When you listen</Text><ChipGrid options={ACTIVITIES} selected={pv.activities || []} onToggle={toggle('activities')} testID="pref-activities" /></View>

        <View style={st.prefBlock}>
          <Text style={st.prefTitle}>Home area</Text>
          <View style={st.areaGrid}>
            {DUBAI_AREAS.map(a => (
              <TouchableOpacity key={a} style={[st.areaChip, pv.home_area === a && st.areaChipOn]} onPress={() => setPv((p: any) => ({ ...p, home_area: a }))} testID={`pref-area-${a.toLowerCase().replace(/ /g, '-')}`}>
                {pv.home_area === a && <Ionicons name="checkmark" size={12} color={t.secondary} />}
                <Text style={[st.areaChipText, pv.home_area === a && { color: t.secondary }]}>{a}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={st.prefBlock}>
          <Text style={st.prefTitle}>RJ personality</Text>
          <View style={{ gap: SPACING.sm }}>
            {HOSTS.map(h => (
              <TouchableOpacity key={h.id} style={[st.hostCard, pv.host_personality === h.id && st.hostCardOn]} onPress={() => setPv((p: any) => ({ ...p, host_personality: h.id }))} testID={`pref-host-${h.id}`}>
                {pv.host_personality === h.id && <Ionicons name="checkmark" size={14} color={t.secondary} />}
                <Text style={[st.hostText, pv.host_personality === h.id && { color: t.secondary }]}>{h.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={st.prefBlock}>
          <Text style={st.prefTitle}>Explicit content</Text>
          <View style={st.toggleRow}>
            <Switch value={pv.explicit_ok} onValueChange={v => setPv((p: any) => ({ ...p, explicit_ok: v }))} trackColor={{ false: '#333', true: t.primary }} thumbColor="#fff" testID="pref-explicit-checkbox" />
            <Text style={{ color: t.textDim, fontSize: 13, flex: 1 }}>{pv.explicit_ok ? 'Explicit ON' : 'Explicit OFF'}</Text>
          </View>
        </View>

        <TouchableOpacity style={st.saveBtn} onPress={save} disabled={saving} testID="save-prefs-btn">
          {saving ? <ActivityIndicator size="small" color="#fff" /> :
            <><Ionicons name="save" size={16} color="#fff" /><Text style={st.saveBtnText}>SAVE PREFERENCES</Text></>}
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

function MenuItem({ icon, label, sub, color, onPress, loading: busy, testID }: {
  icon: string; label: string; sub?: string; color?: string; onPress: () => void; loading?: boolean; testID: string;
}) {
  const t = useThemeTokens();
  const st = makeStyles(t);
  return (
    <TouchableOpacity style={st.menuItem} onPress={onPress} testID={testID} activeOpacity={0.7}>
      <View style={[st.menuIconChip, color ? { backgroundColor: `${color}18` } : null]}>
        {busy ? <ActivityIndicator size="small" color={t.textDim} /> :
          <Ionicons name={icon as any} size={18} color={color || t.primary} />}
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text style={[st.menuItemLabel, color ? { color } : null]}>{label}</Text>
        {sub && <Text style={st.menuItemSub}>{sub}</Text>}
      </View>
      <Ionicons name="chevron-forward" size={14} color={t.textMuted} />
    </TouchableOpacity>
  );
}

const makeStyles = (t: ThemeTokens) => StyleSheet.create({
  container: { flex: 1, backgroundColor: t.bg },
  loadingWrap: { flex: 1, backgroundColor: t.bg, alignItems: 'center', justifyContent: 'center' },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  idCard: { flexDirection: 'row', gap: SPACING.md, backgroundColor: t.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: t.cardBorder, marginBottom: SPACING.lg },
  profileAvatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: t.primary, alignItems: 'center', justifyContent: 'center' },
  profileInitials: { fontSize: 24, fontWeight: '800', color: '#fff' },
  profileName: { fontSize: 18, fontWeight: '800', color: t.text },
  profileEmail: { fontSize: 12, color: t.textDim, marginTop: 2, letterSpacing: 0.5 },
  tagRow: { flexDirection: 'row', gap: 6, marginTop: 8 },
  profileTag: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full, borderWidth: 1, borderColor: t.surfaceBorder },
  profileTagText: { fontSize: 9, fontWeight: '700', color: t.textDim, letterSpacing: 1 },
  menuLabel: { color: t.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 2, textTransform: 'uppercase', marginBottom: SPACING.sm },
  apprRow: { flexDirection: 'row', gap: 10, marginBottom: 4 },
  apprChip: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 12, borderRadius: RADIUS.md, backgroundColor: t.card, borderWidth: 1, borderColor: t.cardBorder },
  apprChipActive: { backgroundColor: t.brand, borderColor: t.brand },
  apprChipText: { color: t.textDim, fontSize: FONT.sm, fontWeight: '800' },
  apprSubLabel: { color: t.textDim, fontSize: 11, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase', marginTop: SPACING.md, marginBottom: SPACING.sm },
  schedCard: { marginTop: SPACING.md, backgroundColor: t.card, borderWidth: 1, borderColor: t.cardBorder, borderRadius: RADIUS.lg, padding: SPACING.md },
  schedHeader: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm },
  schedTitle: { color: t.text, fontSize: FONT.md, fontWeight: '800' },
  schedSub: { color: t.textDim, fontSize: FONT.xs, marginTop: 2 },
  schedRows: { marginTop: SPACING.md, gap: SPACING.sm },
  schedRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  schedRowLabel: { color: t.textDim, fontSize: FONT.sm, fontWeight: '600' },
  stepper: { flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: t.inputBg, borderRadius: RADIUS.full, paddingHorizontal: 12, paddingVertical: 6 },
  stepperVal: { color: t.text, fontSize: FONT.sm, fontWeight: '800', minWidth: 72, textAlign: 'center' },
  menuItem: { flexDirection: 'row', alignItems: 'center', backgroundColor: t.card, borderRadius: RADIUS.md, padding: SPACING.sm + 2, borderWidth: 1, borderColor: t.cardBorder, marginBottom: 8 },
  menuIconChip: { width: 38, height: 38, borderRadius: 12, backgroundColor: t.inputBg, alignItems: 'center', justifyContent: 'center' },
  menuItemLabel: { color: t.text, fontSize: 14, fontWeight: '700' },
  menuItemSub: { color: t.textDim, fontSize: 11, marginTop: 2 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.sm },
  backText: { color: t.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  prefsTitle: { color: t.text, fontSize: 22, fontWeight: '900', marginBottom: SPACING.lg, letterSpacing: -0.5 },
  prefBlock: { marginBottom: SPACING.lg },
  prefTitle: { fontSize: 14, fontWeight: '700', color: t.text, marginBottom: SPACING.sm },
  showAllRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: SPACING.sm },
  showAllText: { flex: 1, fontSize: 12, color: t.textDim, fontWeight: '600' },
  scopeHint: { fontSize: 11, color: t.textDim, fontWeight: '700', marginTop: SPACING.md, marginBottom: 2, textTransform: 'uppercase', letterSpacing: 0.5 },
  areaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  areaChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderRadius: RADIUS.full, borderWidth: 1, borderColor: t.surfaceBorder, backgroundColor: t.surface },
  areaChipOn: { borderColor: t.secondary, backgroundColor: 'rgba(59,130,246,0.08)' },
  areaChipText: { color: t.textDim, fontSize: 12 },
  hostCard: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, padding: SPACING.md, borderRadius: RADIUS.md, borderWidth: 1, borderColor: t.surfaceBorder, backgroundColor: t.card },
  hostCardOn: { borderColor: t.secondary, backgroundColor: 'rgba(59,130,246,0.06)' },
  hostText: { color: t.textDim, fontSize: 13 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  saveBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm, backgroundColor: t.primary, paddingVertical: 14, borderRadius: RADIUS.md, marginTop: SPACING.md },
  saveBtnText: { color: '#fff', fontSize: 14, fontWeight: '800', letterSpacing: 0.5 },
});

const makeCst = (t: ThemeTokens) => StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: t.card, borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: SPACING.lg, paddingBottom: 34, borderWidth: 1, borderColor: t.cardBorder },
  handle: { alignSelf: 'center', width: 40, height: 4, borderRadius: 2, backgroundColor: t.surfaceBorder, marginBottom: SPACING.md },
  title: { color: t.text, fontSize: 20, fontWeight: '900' },
  sub: { color: t.textDim, fontSize: 12, marginTop: 4, marginBottom: SPACING.md },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, paddingHorizontal: 14, borderRadius: RADIUS.md, borderWidth: 1, borderColor: t.cardBorder, backgroundColor: t.surface, marginBottom: 8 },
  rowActive: { borderColor: t.primary, backgroundColor: 'rgba(168,85,247,0.08)' },
  rowLabel: { color: t.text, fontSize: 15, fontWeight: '700' },
  rowCountry: { color: t.textDim, fontSize: 11, marginTop: 2 },
});
