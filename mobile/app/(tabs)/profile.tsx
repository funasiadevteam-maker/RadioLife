import React, { useEffect, useState } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, ActivityIndicator,
  SafeAreaView, Alert, Switch, Platform,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/contexts/AuthContext';
import { COLORS, SPACING, FONT, RADIUS } from '../../src/constants/theme';
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
const HOSTS = [
  { id: 'auto', label: 'Auto (smart routing)' },
  { id: 'veer_dubai', label: 'Veer — late-night charm' },
  { id: 'monika_dubai', label: 'Monika — warm & natural' },
  { id: 'dj_dubai', label: 'DJ Charlie — club energy' },
];

export default function ProfileScreen() {
  const { user, refresh, logout } = useAuth();
  const router = useRouter();
  const [pv, setPv] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [section, setSection] = useState<'menu' | 'prefs'>('menu');
  const [creatorStatus, setCreatorStatus] = useState<string | null>(null);

  useEffect(() => {
    if (user?.preference_vector) setPv({ ...user.preference_vector });
    // Check creator approval status for gating
    getCreatorMe().then(me => {
      const c = me?.creator || me;
      if (c?.application_status) setCreatorStatus(c.application_status);
    }).catch(() => setCreatorStatus(null));
  }, [user]);

  if (!user) return null;
  if (!pv) return <View style={st.loadingWrap}><ActivityIndicator size="large" color={COLORS.primary} /></View>;

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
                  <View style={[st.profileTag, { borderColor: COLORS.secondary }]} testID="profile-admin-tag">
                    <Ionicons name="shield" size={10} color={COLORS.secondary} />
                    <Text style={[st.profileTagText, { color: COLORS.secondary }]}>ADMIN</Text>
                  </View>
                )}
                {user.is_premium && (
                  <View style={[st.profileTag, { borderColor: COLORS.gold }]} testID="profile-vip-tag">
                    <Ionicons name="diamond" size={10} color={COLORS.gold} />
                    <Text style={[st.profileTagText, { color: COLORS.gold }]}>VIP</Text>
                  </View>
                )}
              </View>
            </View>
          </View>

          {/* Menu Items */}
          <Text style={st.menuLabel}>ACCOUNT</Text>
          <MenuItem icon="person-outline" label="Edit Preferences" sub="Languages, genres, moods, RJ personality"
            onPress={() => setSection('prefs')} testID="menu-edit-prefs" />
          <MenuItem icon="card-outline" label="Billing & Plans" sub="Manage subscription, upgrade, payment"
            onPress={() => router.push('/billing')} testID="menu-billing" />
          <MenuItem icon="notifications-outline" label="Notifications" sub="Push notification preferences"
            onPress={() => router.push('/notifications')}
            testID="menu-notifications" />

          <Text style={[st.menuLabel, { marginTop: SPACING.lg }]}>GENERAL</Text>
          <MenuItem icon="megaphone-outline" label="Advertise on RadioLife" sub="Create ads, manage campaigns"
            onPress={() => router.push('/advertiser')}
            testID="menu-advertiser" />
          {creatorStatus === 'approved' && (
            <MenuItem icon="mic-outline" label="Creator Studio" sub="Manage channels, episodes, distribution"
              onPress={() => router.push('/creator')}
              testID="menu-creator-studio" />
          )}
          <MenuItem icon="refresh" label="Re-do Onboarding" sub="Reset preferences and restart setup"
            onPress={redoOnboarding} loading={resetting} testID="redo-onboarding-btn" />
          <MenuItem icon="help-circle-outline" label="Help & Support" sub="FAQ, contact support"
            onPress={() => Alert.alert('Help', 'Email: support@radiolife.app')} testID="menu-help" />
          <MenuItem icon="information-circle-outline" label="About RadioLife" sub="Version 1.0.0 · Phase 11.5"
            onPress={() => Alert.alert('RadioLife.app', 'AI-powered Hinglish internet radio for the Indian diaspora in Dubai/UAE.\n\nVersion 1.0.0')} testID="menu-about" />

          <Text style={[st.menuLabel, { marginTop: SPACING.lg }]}>DANGER ZONE</Text>
          <MenuItem icon="log-out" label="Sign Out" color={COLORS.orange}
            onPress={doLogout} testID="signout-btn" />
          <MenuItem icon="trash-outline" label="Delete Account" sub="Permanently delete all data" color={COLORS.red}
            onPress={confirmDelete} testID="menu-delete-account" />
          <FunAsiaFooter />
        </ScrollView>
      </SafeAreaView>
    );
  }

  /* ─── Preferences Editor ──────────────────────── */
  return (
    <SafeAreaView style={st.container} testID="profile-prefs">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        <TouchableOpacity onPress={() => setSection('menu')} style={st.backRow} testID="prefs-back">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={st.backText}>back to menu</Text>
        </TouchableOpacity>
        <Text style={st.prefsTitle}>Edit Preferences</Text>

        <View style={st.prefBlock}><Text style={st.prefTitle}>Languages</Text><ChipGrid options={LANGUAGES} selected={pv.languages || []} onToggle={toggle('languages')} testID="pref-languages" /></View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>Genres</Text><ChipGrid options={GENRES} selected={pv.genres || []} onToggle={toggle('genres')} testID="pref-genres" /></View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>Eras</Text><ChipGrid options={ERAS} selected={pv.eras || []} onToggle={toggle('eras')} testID="pref-eras" /></View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>Moods</Text><ChipGrid options={MOODS} selected={pv.moods || []} onToggle={toggle('moods')} testID="pref-moods" /></View>
        <View style={st.prefBlock}><Text style={st.prefTitle}>When you listen</Text><ChipGrid options={ACTIVITIES} selected={pv.activities || []} onToggle={toggle('activities')} testID="pref-activities" /></View>

        <View style={st.prefBlock}>
          <Text style={st.prefTitle}>Home area</Text>
          <View style={st.areaGrid}>
            {DUBAI_AREAS.map(a => (
              <TouchableOpacity key={a} style={[st.areaChip, pv.home_area === a && st.areaChipOn]} onPress={() => setPv((p: any) => ({ ...p, home_area: a }))} testID={`pref-area-${a.toLowerCase().replace(/ /g, '-')}`}>
                {pv.home_area === a && <Ionicons name="checkmark" size={12} color={COLORS.secondary} />}
                <Text style={[st.areaChipText, pv.home_area === a && { color: COLORS.secondary }]}>{a}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={st.prefBlock}>
          <Text style={st.prefTitle}>RJ personality</Text>
          <View style={{ gap: SPACING.sm }}>
            {HOSTS.map(h => (
              <TouchableOpacity key={h.id} style={[st.hostCard, pv.host_personality === h.id && st.hostCardOn]} onPress={() => setPv((p: any) => ({ ...p, host_personality: h.id }))} testID={`pref-host-${h.id}`}>
                {pv.host_personality === h.id && <Ionicons name="checkmark" size={14} color={COLORS.secondary} />}
                <Text style={[st.hostText, pv.host_personality === h.id && { color: COLORS.secondary }]}>{h.label}</Text>
              </TouchableOpacity>
            ))}
          </View>
        </View>

        <View style={st.prefBlock}>
          <Text style={st.prefTitle}>Explicit content</Text>
          <View style={st.toggleRow}>
            <Switch value={pv.explicit_ok} onValueChange={v => setPv((p: any) => ({ ...p, explicit_ok: v }))} trackColor={{ false: '#333', true: COLORS.primary }} thumbColor="#fff" testID="pref-explicit-checkbox" />
            <Text style={{ color: COLORS.textDim, fontSize: 13, flex: 1 }}>{pv.explicit_ok ? 'Explicit ON' : 'Explicit OFF'}</Text>
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
  return (
    <TouchableOpacity style={st.menuItem} onPress={onPress} testID={testID} activeOpacity={0.7}>
      <View style={[st.menuIconChip, color ? { backgroundColor: `${color}18` } : null]}>
        {busy ? <ActivityIndicator size="small" color={COLORS.textDim} /> :
          <Ionicons name={icon as any} size={18} color={color || COLORS.primary} />}
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <Text style={[st.menuItemLabel, color ? { color } : null]}>{label}</Text>
        {sub && <Text style={st.menuItemSub}>{sub}</Text>}
      </View>
      <Ionicons name="chevron-forward" size={14} color={COLORS.textMuted} />
    </TouchableOpacity>
  );
}

const st = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  loadingWrap: { flex: 1, backgroundColor: COLORS.bg, alignItems: 'center', justifyContent: 'center' },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  idCard: { flexDirection: 'row', gap: SPACING.md, backgroundColor: COLORS.card, borderRadius: RADIUS.lg, padding: SPACING.md, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: SPACING.lg },
  profileAvatar: { width: 56, height: 56, borderRadius: 28, backgroundColor: COLORS.primary, alignItems: 'center', justifyContent: 'center' },
  profileInitials: { fontSize: 24, fontWeight: '800', color: '#fff' },
  profileName: { fontSize: 18, fontWeight: '800', color: COLORS.text },
  profileEmail: { fontSize: 12, color: COLORS.textDim, marginTop: 2, letterSpacing: 0.5 },
  tagRow: { flexDirection: 'row', gap: 6, marginTop: 8 },
  profileTag: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: 8, paddingVertical: 3, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.surfaceBorder },
  profileTagText: { fontSize: 9, fontWeight: '700', color: COLORS.textDim, letterSpacing: 1 },
  menuLabel: { color: COLORS.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 2, textTransform: 'uppercase', marginBottom: SPACING.sm },
  menuItem: { flexDirection: 'row', alignItems: 'center', backgroundColor: COLORS.card, borderRadius: RADIUS.md, padding: SPACING.sm + 2, borderWidth: 1, borderColor: COLORS.cardBorder, marginBottom: 8 },
  menuIconChip: { width: 38, height: 38, borderRadius: 12, backgroundColor: COLORS.inputBg, alignItems: 'center', justifyContent: 'center' },
  menuItemLabel: { color: COLORS.text, fontSize: 14, fontWeight: '700' },
  menuItemSub: { color: COLORS.textDim, fontSize: 11, marginTop: 2 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.sm },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  prefsTitle: { color: COLORS.text, fontSize: 22, fontWeight: '900', marginBottom: SPACING.lg, letterSpacing: -0.5 },
  prefBlock: { marginBottom: SPACING.lg },
  prefTitle: { fontSize: 14, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.sm },
  areaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: SPACING.sm },
  areaChip: { flexDirection: 'row', alignItems: 'center', gap: 4, paddingHorizontal: SPACING.md, paddingVertical: SPACING.sm, borderRadius: RADIUS.full, borderWidth: 1, borderColor: COLORS.surfaceBorder, backgroundColor: COLORS.surface },
  areaChipOn: { borderColor: COLORS.secondary, backgroundColor: 'rgba(59,130,246,0.08)' },
  areaChipText: { color: COLORS.textDim, fontSize: 12 },
  hostCard: { flexDirection: 'row', alignItems: 'center', gap: SPACING.sm, padding: SPACING.md, borderRadius: RADIUS.md, borderWidth: 1, borderColor: COLORS.surfaceBorder, backgroundColor: COLORS.card },
  hostCardOn: { borderColor: COLORS.secondary, backgroundColor: 'rgba(59,130,246,0.06)' },
  hostText: { color: COLORS.textDim, fontSize: 13 },
  toggleRow: { flexDirection: 'row', alignItems: 'center', gap: SPACING.md },
  saveBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: SPACING.sm, backgroundColor: COLORS.primary, paddingVertical: 14, borderRadius: RADIUS.md, marginTop: SPACING.md },
  saveBtnText: { color: '#fff', fontSize: 14, fontWeight: '800', letterSpacing: 0.5 },
});
