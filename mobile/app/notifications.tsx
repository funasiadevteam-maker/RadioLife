import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, ScrollView, SafeAreaView,
  Switch, Platform, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, SPACING, FONT, RADIUS } from '../src/constants/theme';
import { useAuth } from '../src/contexts/AuthContext';
import {
  requestPushPermission, registerPushToken, deregisterPushToken, getCachedPushToken,
} from '../src/utils/pushNotifications';
import api from '../src/api/client';

const PREF_TOGGLES = [
  { key: 'new_games', label: 'New game drops', icon: 'game-controller' },
  { key: 'coupon_expiry', label: 'Coupon expiring soon', icon: 'pricetag' },
  { key: 'lobby_friends', label: 'Friends joined a lobby', icon: 'people' },
  { key: 'leaderboard', label: 'City leaderboard updates', icon: 'trophy' },
  { key: 'premium_offers', label: 'Premium offers', icon: 'diamond' },
];

export default function NotificationsScreen() {
  const router = useRouter();
  const { user, loading: authLoading } = useAuth();
  const [pushEnabled, setPushEnabled] = useState(false);
  const [registering, setRegistering] = useState(false);
  const [prefs, setPrefs] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(PREF_TOGGLES.map(t => [t.key, true]))
  );
  const cachedToken = getCachedPushToken();
  const isWeb = Platform.OS === 'web';

  useEffect(() => { if (!authLoading && !user) router.replace('/login'); }, [user, authLoading]);
  useEffect(() => { setPushEnabled(!!cachedToken); }, [cachedToken]);

  const togglePush = async (val: boolean) => {
    if (isWeb) return;
    setRegistering(true);
    try {
      if (val) {
        const token = await requestPushPermission();
        if (token) {
          await registerPushToken(api);
          setPushEnabled(true);
        }
      } else {
        await deregisterPushToken(api);
        setPushEnabled(false);
      }
    } catch {}
    finally { setRegistering(false); }
  };

  return (
    <SafeAreaView style={st.screen} testID="notifications-screen">
      <ScrollView contentContainerStyle={st.scroll} showsVerticalScrollIndicator={false}>
        <TouchableOpacity onPress={() => router.back()} style={st.backRow} testID="notif-back-btn">
          <Ionicons name="chevron-back" size={14} color={COLORS.textDim} />
          <Text style={st.backText}>back</Text>
        </TouchableOpacity>
        <Text style={st.title}>Notifications</Text>
        <Text style={st.sub}>Control what BigFM can notify you about.</Text>

        {/* Web info banner */}
        {isWeb && (
          <View style={st.webBanner} testID="notif-web-banner">
            <Ionicons name="information-circle" size={18} color={COLORS.secondary} />
            <Text style={st.webBannerText}>
              Push notifications are available on the BigFM mobile app for iOS/Android. This preview runs in a web browser where native push is not supported.
            </Text>
          </View>
        )}

        {/* Master toggle */}
        <View style={st.card} testID="notif-master-toggle">
          <View style={st.toggleRow}>
            <Ionicons name="notifications" size={20} color={pushEnabled ? COLORS.green : COLORS.textDim} />
            <View style={{ flex: 1, marginLeft: 12 }}>
              <Text style={st.toggleLabel}>Push notifications</Text>
              <Text style={st.toggleSub}>
                {isWeb ? 'Not available on web preview'
                  : pushEnabled ? 'Enabled — you will receive alerts'
                  : 'Disabled — turn on to get notified'}
              </Text>
            </View>
            {registering ? <ActivityIndicator size="small" color={COLORS.primary} /> :
              <Switch value={pushEnabled} onValueChange={togglePush} disabled={isWeb}
                trackColor={{ false: '#333', true: COLORS.green }} thumbColor="#fff"
                testID="notif-push-switch" />}
          </View>
        </View>

        {/* Status row */}
        {cachedToken && (
          <View style={st.statusRow} testID="notif-status">
            <Ionicons name="checkmark-circle" size={14} color={COLORS.green} />
            <Text style={st.statusText}>
              Registered as: {Platform.OS} · token …{cachedToken.slice(-8)}
            </Text>
          </View>
        )}

        {/* Category toggles */}
        <Text style={st.sectionLabel}>NOTIFICATION CATEGORIES</Text>
        <View style={st.card}>
          {PREF_TOGGLES.map((t, i) => (
            <View key={t.key} style={[st.prefRow, i < PREF_TOGGLES.length - 1 && st.prefBorder]}
              testID={`notif-pref-${t.key}`}>
              <Ionicons name={t.icon as any} size={16} color={COLORS.textDim} />
              <Text style={st.prefLabel}>{t.label}</Text>
              <Switch value={prefs[t.key]} onValueChange={v => setPrefs(p => ({ ...p, [t.key]: v }))}
                trackColor={{ false: '#333', true: COLORS.primary }} thumbColor="#fff"
                testID={`notif-toggle-${t.key}`} />
            </View>
          ))}
        </View>
        <Text style={st.hint}>Category preferences will take effect once the notification pipeline ships in Phase 12.</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  screen: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: SPACING.md, paddingBottom: 100 },
  backRow: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: SPACING.sm },
  backText: { color: COLORS.textMuted, fontSize: FONT.xs, fontWeight: '600' },
  title: { color: COLORS.text, fontSize: 24, fontWeight: '900', letterSpacing: -0.5 },
  sub: { color: COLORS.textDim, fontSize: FONT.sm, marginBottom: SPACING.lg },
  webBanner: { flexDirection: 'row', alignItems: 'flex-start', gap: 10, backgroundColor: 'rgba(59,130,246,0.06)', borderWidth: 1, borderColor: 'rgba(59,130,246,0.2)', borderRadius: RADIUS.lg, padding: SPACING.md, marginBottom: SPACING.lg },
  webBannerText: { color: COLORS.textDim, fontSize: 12, flex: 1, lineHeight: 18 },
  card: { backgroundColor: COLORS.card, borderRadius: RADIUS.lg, borderWidth: 1, borderColor: COLORS.cardBorder, padding: SPACING.md, marginBottom: SPACING.md },
  toggleRow: { flexDirection: 'row', alignItems: 'center' },
  toggleLabel: { color: COLORS.text, fontSize: 15, fontWeight: '700' },
  toggleSub: { color: COLORS.textDim, fontSize: 11, marginTop: 2 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: SPACING.md },
  statusText: { color: COLORS.textDim, fontSize: 11 },
  sectionLabel: { color: COLORS.textDim, fontSize: 10, fontWeight: '700', letterSpacing: 2, marginBottom: SPACING.sm, marginTop: SPACING.sm },
  prefRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12 },
  prefBorder: { borderBottomWidth: 1, borderBottomColor: COLORS.surfaceBorder },
  prefLabel: { color: COLORS.text, fontSize: 13, flex: 1 },
  hint: { color: COLORS.textDim, fontSize: 11, fontStyle: 'italic', marginTop: SPACING.sm, textAlign: 'center' },
});
